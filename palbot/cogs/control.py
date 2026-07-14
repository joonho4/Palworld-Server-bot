"""서버 전원 제어 명령: /start /stop /status /ip."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from .. import notifications
from ..ui import embeds

log = logging.getLogger("palworld-bot.control")


def has_control_permission(interaction: discord.Interaction, role_name: str) -> bool:
    """role_name 이 설정돼 있으면 해당 역할 보유자만 허용."""
    if not role_name:
        return True
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    return any(r.name == role_name for r in member.roles)


class Control(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(description="팰월드 서버(VM)를 켭니다.")
    async def start(self, interaction: discord.Interaction) -> None:
        s = self.bot.settings
        if not has_control_permission(interaction, s.control_role):
            await interaction.response.send_message(
                embed=embeds.denied(s.control_role), ephemeral=True
            )
            return
        if not s.power_control:
            await interaction.response.send_message(embed=embeds.always_on(s.public_ip))
            return

        await interaction.response.defer(thinking=True)
        try:
            snap = await self.bot.vm.snapshot()
            if snap.is_running:
                await interaction.followup.send(embed=embeds.already_running(snap.external_ip))
                return
            if not snap.is_stopped:
                await interaction.followup.send(embed=embeds.server_busy(snap.status))
                return

            await self.bot.vm.start()
            await interaction.followup.send(embed=embeds.server_starting())

            # REST API가 설정돼 있으면 준비 완료를 백그라운드로 감시 → 채널 알림
            if s.rest_enabled:
                self.bot.spawn(
                    notifications.watch_until_ready(
                        self.bot,
                        self.bot.vm,
                        self.bot.api,
                        s.rest_host,
                        s.notify_channel_id or interaction.channel_id,
                    )
                )
        except Exception:
            log.exception("start 실패")
            await interaction.followup.send(
                embed=embeds.error("서버 켜다가 문제 생겼노. 로그 확인해보라노.")
            )

    @app_commands.command(description="팰월드 서버(VM)를 끕니다. (비용 절약)")
    async def stop(self, interaction: discord.Interaction) -> None:
        s = self.bot.settings
        if not has_control_permission(interaction, s.control_role):
            await interaction.response.send_message(
                embed=embeds.denied(s.control_role), ephemeral=True
            )
            return
        if not s.power_control:
            await interaction.response.send_message(embed=embeds.power_unavailable())
            return

        await interaction.response.defer(thinking=True)
        try:
            snap = await self.bot.vm.snapshot()
            if snap.is_stopped:
                await interaction.followup.send(embed=embeds.already_stopped())
                return

            # 정지 전에 월드를 명시적으로 저장 (REST API가 설정된 경우, best-effort)
            saved = await self._save_world(s, snap)

            await self.bot.vm.stop()
            await interaction.followup.send(embed=embeds.server_stopping(saved))
        except Exception:
            log.exception("stop 실패")
            await interaction.followup.send(
                embed=embeds.error("서버 끄다가 문제 생겼노. 로그 확인해보라노.")
            )

    async def _save_world(self, s, snap) -> bool:
        """정지 전 월드 저장. REST 미설정/도달 불가 시 조용히 False (오토세이브에 의존)."""
        if not s.rest_enabled or not snap.is_running:
            return False
        host = s.rest_host or snap.internal_ip
        if not host:
            return False
        return await self.bot.api.save(host)

    @app_commands.command(description="월드 저장 후 서버를 재시작해 팰월드를 최신 버전으로 업데이트합니다.")
    async def update(self, interaction: discord.Interaction) -> None:
        s = self.bot.settings
        if not has_control_permission(interaction, s.control_role):
            await interaction.response.send_message(
                embed=embeds.denied(s.control_role), ephemeral=True
            )
            return
        if not s.power_control:
            await interaction.response.send_message(embed=embeds.power_unavailable())
            return

        await interaction.response.defer(thinking=True)
        try:
            snap = await self.bot.vm.snapshot()
            if snap.is_stopped:
                # 꺼져 있으면 그냥 켜면 됨 — 부팅 시 ExecStartPre가 자동 업데이트
                await self.bot.vm.start()
                await interaction.followup.send(embed=embeds.server_starting())
                if s.rest_enabled:
                    self.bot.spawn(
                        notifications.watch_until_ready(
                            self.bot, self.bot.vm, self.bot.api, s.rest_host,
                            s.notify_channel_id or interaction.channel_id,
                        )
                    )
                return
            if not snap.is_running:
                await interaction.followup.send(embed=embeds.server_busy(snap.status))
                return

            # 실행 중: 저장 → 정지 → (정지 확인 후) 재시작. 부팅 때 자동 업데이트됨.
            saved = await self._save_world(s, snap)
            await self.bot.vm.stop()
            await interaction.followup.send(embed=embeds.server_updating(saved))
            self.bot.spawn(
                self._restart_when_stopped(s.notify_channel_id or interaction.channel_id)
            )
        except Exception:
            log.exception("update 실패")
            await interaction.followup.send(
                embed=embeds.error("업데이트하다 문제 생겼노. 로그 확인해보라 이기.")
            )

    async def _restart_when_stopped(self, channel_id: int | None) -> None:
        """VM이 완전히 꺼질 때까지 기다렸다가 다시 켠다 (/update 후반부)."""
        s = self.bot.settings
        for _ in range(60):          # 최대 ~5분 대기
            await asyncio.sleep(5)
            snap = await self.bot.vm.snapshot()
            if snap.is_stopped:
                break
        else:
            await notifications.send_embed(self.bot, channel_id, embeds.update_stop_timeout())
            return

        await self.bot.vm.start()
        if s.rest_enabled:
            await notifications.watch_until_ready(
                self.bot, self.bot.vm, self.bot.api, s.rest_host, channel_id
            )

    @app_commands.command(description="서버(VM) 상태를 확인합니다.")
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            snap = await self.bot.vm.snapshot()
            await interaction.followup.send(embed=embeds.status(snap))
        except Exception:
            log.exception("status 실패")
            await interaction.followup.send(embed=embeds.error("상태 확인하다 문제 생겼노."))

    @app_commands.command(description="현재 접속용 외부 IP를 보여줍니다.")
    async def ip(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            snap = await self.bot.vm.snapshot()
            if not snap.is_running:
                await interaction.followup.send(embed=embeds.server_off(snap.status))
                return
            if snap.external_ip:
                await interaction.followup.send(embed=embeds.ip(snap.external_ip))
            else:
                await interaction.followup.send(embed=embeds.ip_not_found())
        except Exception:
            log.exception("ip 실패")
            await interaction.followup.send(embed=embeds.error("IP 확인하다 문제 생겼노."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Control(bot))
