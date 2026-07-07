"""서버 전원 제어 명령: /start /stop /status /ip."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

import notifications

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

    def _deny_message(self) -> str:
        return f"⛔ `{self.bot.settings.control_role}` 역할이 있어야 사용할 수 있어요."

    @app_commands.command(description="팰월드 서버(VM)를 켭니다.")
    async def start(self, interaction: discord.Interaction) -> None:
        s = self.bot.settings
        if not has_control_permission(interaction, s.control_role):
            await interaction.response.send_message(self._deny_message(), ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        try:
            snap = await self.bot.vm.snapshot()
            if snap.is_running:
                where = f"`{snap.external_ip}:8211`" if snap.external_ip else "서버"
                await interaction.followup.send(f"✅ 이미 켜져 있어요. 접속: {where}")
                return
            if not snap.is_stopped:
                await interaction.followup.send(
                    f"⏳ 지금 상태가 `{snap.status}`라 잠시 후 다시 시도해 주세요."
                )
                return

            await self.bot.vm.start()
            await interaction.followup.send(
                "🟢 서버를 켜는 중입니다. 게임 서버가 준비되면 알려드릴게요. (보통 1~3분)"
            )

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
            await interaction.followup.send("❌ 서버를 켜는 중 오류가 발생했어요. 로그를 확인해 주세요.")

    @app_commands.command(description="팰월드 서버(VM)를 끕니다. (비용 절약)")
    async def stop(self, interaction: discord.Interaction) -> None:
        s = self.bot.settings
        if not has_control_permission(interaction, s.control_role):
            await interaction.response.send_message(self._deny_message(), ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        try:
            snap = await self.bot.vm.snapshot()
            if snap.is_stopped:
                await interaction.followup.send("✅ 이미 꺼져 있어요.")
                return

            # 정지 전에 월드를 명시적으로 저장 (REST API가 설정된 경우, best-effort)
            saved = await self._save_world(s, snap)

            await self.bot.vm.stop()
            note = " (월드 저장 완료 ✅)" if saved else ""
            await interaction.followup.send(f"🔴 서버를 끄는 중입니다. 곧 정지돼요.{note}")
        except Exception:
            log.exception("stop 실패")
            await interaction.followup.send("❌ 서버를 끄는 중 오류가 발생했어요. 로그를 확인해 주세요.")

    async def _save_world(self, s, snap) -> bool:
        """정지 전 월드 저장. REST 미설정/도달 불가 시 조용히 False (오토세이브에 의존)."""
        if not s.rest_enabled or not snap.is_running:
            return False
        host = s.rest_host or snap.internal_ip
        if not host:
            return False
        return await self.bot.api.save(host)

    @app_commands.command(description="서버(VM) 상태를 확인합니다.")
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            snap = await self.bot.vm.snapshot()
            emoji = {
                "RUNNING": "🟢", "TERMINATED": "🔴", "STOPPING": "🟠", "STAGING": "🟡",
            }.get(snap.status, "⚪")
            msg = f"{emoji} 상태: **{snap.status}**"
            if snap.is_running and snap.external_ip:
                msg += f"\n접속: `{snap.external_ip}:8211`"
            await interaction.followup.send(msg)
        except Exception:
            log.exception("status 실패")
            await interaction.followup.send("❌ 상태 확인 중 오류가 발생했어요.")

    @app_commands.command(description="현재 접속용 외부 IP를 보여줍니다.")
    async def ip(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            snap = await self.bot.vm.snapshot()
            if not snap.is_running:
                await interaction.followup.send(
                    f"⚠️ 서버가 꺼져 있어요 (상태: `{snap.status}`). `/start`로 먼저 켜주세요."
                )
                return
            if snap.external_ip:
                await interaction.followup.send(f"🌐 접속 주소: `{snap.external_ip}:8211`")
            else:
                await interaction.followup.send("⚠️ 외부 IP를 찾지 못했어요. VM 네트워크 설정을 확인하세요.")
        except Exception:
            log.exception("ip 실패")
            await interaction.followup.send("❌ IP 확인 중 오류가 발생했어요.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Control(bot))
