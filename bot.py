"""팰월드 서버 제어 Discord 봇 — 엔트리포인트.

설정 로딩 → 봇 구성(VM 컨트롤러/REST 클라이언트 주입) → cog 로딩 → 실행.
실제 명령 로직은 cogs/ 안에, 외부 연동은 gcp.py / palworld_api.py 에 있다.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from config import Settings
from gcp import VMController
from palworld_api import PalworldAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("palworld-bot")

INITIAL_COGS = ("cogs.control", "cogs.players")


class PalworldBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        # 슬래시 명령만 사용 → 메시지 내용 인텐트 불필요. command_prefix는 형식상 지정.
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.settings = settings
        self.vm = VMController(settings.gcp_project, settings.zone, settings.instance)
        self.api = PalworldAPI(settings.rest_port, settings.admin_password)
        # 백그라운드 태스크(준비 완료 폴링 등)가 GC로 사라지지 않도록 참조를 보관.
        self._bg_tasks: set = set()

    def spawn(self, coro) -> None:
        """백그라운드 태스크를 생성하고 완료 시 자동으로 참조를 정리한다."""
        task = self.loop.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def setup_hook(self) -> None:
        for ext in INITIAL_COGS:
            await self.load_extension(ext)
            log.info("cog 로딩: %s", ext)

        if self.settings.guild_id:
            guild = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("슬래시 명령을 길드 %s에 동기화했습니다.", self.settings.guild_id)
        else:
            await self.tree.sync()
            log.info("슬래시 명령을 글로벌 동기화했습니다 (최대 1시간 지연).")

    async def on_ready(self) -> None:
        log.info("로그인 완료: %s (id=%s)", self.user, self.user.id)


def main() -> None:
    settings = Settings.load()
    bot = PalworldBot(settings)
    bot.run(settings.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
