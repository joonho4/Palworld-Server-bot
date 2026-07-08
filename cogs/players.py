"""접속자 조회 명령: /players."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

import embeds
from palworld_api import PalworldAPIError

log = logging.getLogger("palworld-bot.players")


class Players(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _resolve_host(self) -> str | None:
        """REST 호스트: 설정값 우선, 없으면 VM 내부 IP를 동적으로 조회."""
        s = self.bot.settings
        if s.rest_host:
            return s.rest_host
        return await self.bot.vm.internal_ip()

    @app_commands.command(description="현재 접속 중인 플레이어를 보여줍니다.")
    async def players(self, interaction: discord.Interaction) -> None:
        s = self.bot.settings
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

            host = await self._resolve_host()
            if not host:
                await interaction.followup.send(
                    embed=embeds.error("서버 내부 IP를 찾지 못했어요.")
                )
                return

            player_list = await self.bot.api.players(host)
            if not player_list:
                await interaction.followup.send(embed=embeds.no_players())
                return
            await interaction.followup.send(embed=embeds.players(player_list))
        except PalworldAPIError:
            log.exception("players REST 오류")
            await interaction.followup.send(
                embed=embeds.error("서버 REST API 응답 오류예요. 서버가 아직 로딩 중이거나 설정을 확인해 주세요.")
            )
        except Exception:
            log.exception("players 실패")
            await interaction.followup.send(
                embed=embeds.error("접속자 조회 중 오류가 발생했어요. 서버가 아직 준비 중일 수 있어요.")
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Players(bot))
