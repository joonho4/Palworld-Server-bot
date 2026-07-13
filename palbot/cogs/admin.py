"""운영 명령: /announce /backup /stop-in."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from .. import notifications
from ..ui import embeds
from .control import has_control_permission

log = logging.getLogger("palworld-bot.admin")


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._scheduled_stop: asyncio.Task | None = None

    async def _resolve_host(self, snap) -> str | None:
        s = self.bot.settings
        return s.rest_host or snap.internal_ip

    # ── /announce ────────────────────────────────────────────
    @app_commands.command(description="게임 안으로 전체 공지를 보냅니다.")
    @app_commands.describe(message="공지할 내용")
    async def announce(self, interaction: discord.Interaction, message: str) -> None:
        s = self.bot.settings
        if not has_control_permission(interaction, s.control_role):
            await interaction.response.send_message(
                embed=embeds.denied(s.control_role), ephemeral=True
            )
            return
        if not s.rest_enabled:
            await interaction.response.send_message(
                embed=embeds.players_not_configured(), ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        try:
            snap = await self.bot.vm.snapshot()
            if not snap.is_running:
                await interaction.followup.send(embed=embeds.server_off(snap.status))
                return
            host = await self._resolve_host(snap)
            if not host:
                await interaction.followup.send(embed=embeds.error("서버 내부 IP를 못 찾겠노."))
                return
            await self.bot.api.announce(host, message)
            await interaction.followup.send(embed=embeds.announce_ok(message))
        except Exception:
            log.exception("announce 실패")
            await interaction.followup.send(
                embed=embeds.error("공지 보내다 문제 생겼노. 서버가 준비 중일 수도 있노.")
            )

    # ── /backup ──────────────────────────────────────────────
    @app_commands.command(description="월드 저장 후 서버 디스크 스냅샷 백업을 만듭니다.")
    async def backup(self, interaction: discord.Interaction) -> None:
        s = self.bot.settings
        if not has_control_permission(interaction, s.control_role):
            await interaction.response.send_message(
                embed=embeds.denied(s.control_role), ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        try:
            snap = await self.bot.vm.snapshot()
            saved = False
            if snap.is_running and s.rest_enabled:
                host = await self._resolve_host(snap)
                if host:
                    saved = await self.bot.api.save(host)
                    await asyncio.sleep(3)   # 저장이 디스크에 반영될 시간
            name = await self.bot.vm.create_disk_snapshot()
            await interaction.followup.send(embed=embeds.backup_started(name, saved))
        except Exception:
            log.exception("backup 실패")
            await interaction.followup.send(
                embed=embeds.error(
                    "백업하다 문제 생겼노. 서비스 계정에 스냅샷 권한 있는지 확인해보라 이기."
                )
            )

    # ── /stop-in ─────────────────────────────────────────────
    @app_commands.command(
        name="stop-in", description="N분 뒤 저장하고 서버를 끕니다. 0을 주면 예약 취소."
    )
    @app_commands.describe(minutes="몇 분 뒤에 끌지 (0 = 예약 취소, 최대 360)")
    async def stop_in(
        self, interaction: discord.Interaction, minutes: app_commands.Range[int, 0, 360]
    ) -> None:
        s = self.bot.settings
        if not has_control_permission(interaction, s.control_role):
            await interaction.response.send_message(
                embed=embeds.denied(s.control_role), ephemeral=True
            )
            return

        # 취소
        if minutes == 0:
            if self._scheduled_stop and not self._scheduled_stop.done():
                self._scheduled_stop.cancel()
                self._scheduled_stop = None
                await interaction.response.send_message(embed=embeds.stopin_cancelled())
            else:
                await interaction.response.send_message(
                    embed=embeds.stopin_none(), ephemeral=True
                )
            return

        await interaction.response.defer(thinking=True)
        try:
            snap = await self.bot.vm.snapshot()
            if snap.is_stopped:
                await interaction.followup.send(embed=embeds.already_stopped())
                return

            # 기존 예약이 있으면 새 예약으로 교체
            if self._scheduled_stop and not self._scheduled_stop.done():
                self._scheduled_stop.cancel()

            # 게임 안에도 예고
            if s.rest_enabled:
                host = await self._resolve_host(snap)
                if host:
                    try:
                        await self.bot.api.announce(
                            host, f"{minutes}분 뒤 서버가 종료됩니다."
                        )
                    except Exception:
                        pass

            channel_id = s.notify_channel_id or interaction.channel_id
            self._scheduled_stop = self.bot.loop.create_task(
                self._delayed_stop(minutes, channel_id)
            )
            await interaction.followup.send(embed=embeds.stopin_scheduled(minutes))
        except Exception:
            log.exception("stop-in 실패")
            await interaction.followup.send(embed=embeds.error("예약 걸다 문제 생겼노."))

    async def _delayed_stop(self, minutes: int, channel_id: int | None) -> None:
        """예약 시간까지 대기 후 저장·종료. 1분 전 게임 내 최종 경고."""
        s = self.bot.settings
        try:
            if minutes > 1:
                await asyncio.sleep((minutes - 1) * 60)
                snap = await self.bot.vm.snapshot()
                if snap.is_stopped:
                    return
                if s.rest_enabled:
                    host = await self._resolve_host(snap)
                    if host:
                        try:
                            await self.bot.api.announce(host, "1분 뒤 서버가 종료됩니다!")
                        except Exception:
                            pass
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(minutes * 60)

            snap = await self.bot.vm.snapshot()
            if snap.is_stopped:
                return
            saved = False
            if s.rest_enabled and snap.is_running:
                host = await self._resolve_host(snap)
                if host:
                    try:
                        saved = await self.bot.api.save(host)
                    except Exception:
                        pass
            await self.bot.vm.stop()
            await notifications.send_embed(
                self.bot, channel_id, embeds.server_stopping(saved)
            )
        except asyncio.CancelledError:
            pass    # /stop-in 0 으로 취소됨
        except Exception:
            log.exception("예약 종료 실행 실패")
            await notifications.send_embed(
                self.bot, channel_id, embeds.error("예약 종료 실행하다 문제 생겼노.")
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
