"""봇 구성 및 실행.

설정 로딩 → 봇 구성(VM 컨트롤러/REST 클라이언트 주입) → cog 로딩 → 실행.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .config import Settings
from .services.gcp import VMController
from .services.palworld_api import PalworldAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("palworld-bot")

INITIAL_COGS = (
    "palbot.cogs.control",
    "palbot.cogs.players",
    "palbot.cogs.help",
    "palbot.cogs.admin",
)


class PalworldBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        # 슬래시 명령만 사용 → 메시지 내용 인텐트 불필요. command_prefix는 형식상 지정.
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.settings = settings
        if settings.power_control:
            self.vm = VMController(
                settings.gcp_project, settings.zone, settings.instance,
                disk=settings.backup_disk,
            )
        else:
            # 상시 가동 서버 (오라클 무료 등) — 전원 제어 없음
            from .services.static_vm import StaticVM
            self.vm = StaticVM(settings.public_ip, settings.rest_host)
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

        # 서버 감시 루프 시작 (상태 표시 / 접속·퇴장 알림 / 유휴 자동 종료)
        from .watcher import ServerWatcher
        self.watcher = ServerWatcher(self)
        self.spawn(self.watcher.run())

    async def on_ready(self) -> None:
        log.info("로그인 완료: %s (id=%s)", self.user, self.user.id)


def main() -> None:
    settings = Settings.load()
    bot = PalworldBot(settings)
    bot.run(settings.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
