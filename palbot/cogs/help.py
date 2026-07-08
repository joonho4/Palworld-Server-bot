"""도움말 명령: /help."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..ui import embeds


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="봇 명령어 도움말을 보여줍니다.")
    async def help_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=embeds.help_all(), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
