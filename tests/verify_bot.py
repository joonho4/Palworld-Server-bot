"""봇 오프라인 검증 스크립트.

GCP/Discord 실제 연결 없이(Mock) 다음을 확인한다:
  1. 모든 모듈 import
  2. 설정 로딩
  3. 봇 인스턴스화 + cog 로딩 + 슬래시 명령 5개 등록
  4. 모든 임베드 빌더가 유효한 Discord 임베드를 생성 (길이 제한 준수)
  5. 권한 체크 로직
  6. VMSnapshot 상태 판정
  7. REST 실패 시 save/is_ready 가 예외 없이 안전하게 처리

사용: python tests/verify_bot.py   (repo 루트에서)
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

# Windows 콘솔(cp949)에서도 이모지/한글 출력이 깨지지 않도록 UTF-8 강제
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# repo 루트를 import 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = "PASS"
FAIL = "FAIL"
_failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    mark = PASS if condition else FAIL
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        _failures.append(name)


EXPECTED_COMMANDS = {"start", "stop", "status", "ip", "players", "help", "update"}
# Discord 임베드 길이 제한
MAX_TITLE, MAX_DESC = 256, 4096


async def main() -> int:
    print("\n=== 팰월드 봇 검증 ===\n")

    # 1. 설정 로딩 (필수 env 없으면 테스트용으로 주입)
    os.environ.setdefault("DISCORD_TOKEN", "test-token")
    os.environ.setdefault("GCP_PROJECT", "test-project")
    os.environ.setdefault("PALWORLD_INSTANCE", "test-vm")
    os.environ.setdefault("PALWORLD_ZONE", "us-central1-a")

    print("[1] 모듈 import & 설정 로딩")
    from palbot import config
    from palbot.ui import embeds
    from palbot.services.gcp import VMSnapshot
    from palbot.services.palworld_api import PalworldAPI, PalworldAPIError
    settings = config.Settings.load()
    check("Settings.load()", settings.instance == os.environ["PALWORLD_INSTANCE"])
    check("rest_enabled 판정", settings.rest_enabled == bool(settings.admin_password))

    # 2. 봇 인스턴스화 + cog 로딩 (GCP 클라이언트는 Mock)
    print("\n[2] 봇 구성 & 명령 등록")
    with patch("google.cloud.compute_v1.InstancesClient", return_value=MagicMock()):
        from palbot import bot as botmod
        bot = botmod.PalworldBot(settings)
        for ext in botmod.INITIAL_COGS:
            await bot.load_extension(ext)
        registered = {c.name for c in bot.tree.get_commands()}
        check("cog 3개 로딩", len(bot.cogs) == 3, f"cogs={list(bot.cogs)}")
        check(
            f"슬래시 명령 7개 등록 {EXPECTED_COMMANDS}",
            EXPECTED_COMMANDS.issubset(registered),
            f"실제={registered}",
        )
        await bot.close()

    # 3. 임베드 빌더 검증
    print("\n[3] 임베드 디자인 (팰월드 테마)")
    snap_on = VMSnapshot("RUNNING", "34.10.20.30", "10.0.0.5")
    snap_off = VMSnapshot("TERMINATED", None, "10.0.0.5")
    samples = {
        "server_starting": embeds.server_starting(),
        "already_running": embeds.already_running("34.10.20.30"),
        "server_busy": embeds.server_busy("STAGING"),
        "server_stopping(saved)": embeds.server_stopping(True),
        "server_stopping(unsaved)": embeds.server_stopping(False),
        "already_stopped": embeds.already_stopped(),
        "status(on)": embeds.status(snap_on),
        "status(off)": embeds.status(snap_off),
        "ip": embeds.ip("34.10.20.30"),
        "server_off": embeds.server_off("TERMINATED"),
        "ready": embeds.ready("34.10.20.30"),
        "ready_timeout": embeds.ready_timeout(),
        "players": embeds.players([{"name": "철수", "level": 12}, {"name": "영희"}]),
        "no_players": embeds.no_players(),
        "denied": embeds.denied("palworld-admin"),
        "error": embeds.error("테스트 오류"),
        "help_all": embeds.help_all(),
        "server_updating(saved)": embeds.server_updating(True),
        "server_updating(unsaved)": embeds.server_updating(False),
        "update_stop_timeout": embeds.update_stop_timeout(),
    }
    import discord
    for name, e in samples.items():
        ok = (
            isinstance(e, discord.Embed)
            and e.title and len(e.title) <= MAX_TITLE
            and (e.description is None or len(e.description) <= MAX_DESC)
            and e.footer.text == embeds.FOOTER_TEXT
        )
        check(f"embed {name}", bool(ok))
    check("status(on) 색상=ONLINE", samples["status(on)"].color.value == embeds.ONLINE)
    check("status(off) 색상=OFFLINE", samples["status(off)"].color.value == embeds.OFFLINE)

    # 4. 권한 체크 로직
    print("\n[4] 권한 체크")
    from palbot.cogs.control import has_control_permission
    fake_it = MagicMock()
    fake_it.user = object()  # discord.Member 아님
    check("빈 역할 → 전체 허용", has_control_permission(fake_it, "") is True)
    check("역할 지정 + 비멤버 → 거부", has_control_permission(fake_it, "admin") is False)

    # 5. VMSnapshot 상태 판정
    print("\n[5] VMSnapshot 상태 판정")
    check("RUNNING is_running", snap_on.is_running and not snap_on.is_stopped)
    check("TERMINATED is_stopped", snap_off.is_stopped and not snap_off.is_running)

    # 6. REST 실패 시 안전 처리
    print("\n[6] REST API 예외 안전성")
    api = PalworldAPI(8212, "pw")

    async def _boom(*a, **k):
        raise PalworldAPIError("unreachable")

    api._post = _boom  # type: ignore[assignment]
    api._get = _boom   # type: ignore[assignment]
    saved = await api.save("10.0.0.5")
    ready = await api.is_ready("10.0.0.5")
    check("save() 실패 시 False 반환 (예외 없음)", saved is False)
    check("is_ready() 실패 시 False 반환 (예외 없음)", ready is False)

    # 결과
    print("\n=== 결과 ===")
    if _failures:
        print(f"❌ 실패 {len(_failures)}건: {_failures}")
        return 1
    print("✅ 모든 검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
