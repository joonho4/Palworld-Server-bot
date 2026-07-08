"""Discord 메시지 디자인 (팰월드 테마 임베드).

모든 봇 응답의 디자인·말투를 이 파일 한곳에서 관리한다.
색상/문구를 바꾸고 싶으면 여기만 수정하면 된다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import discord

GAME_PORT = 8211

# ── 팰월드 테마 색상 ──────────────────────────────────────────
BRAND = 0x38BDF8      # 팰월드 하늘색 (정보/기본)
ONLINE = 0x4ADE80     # 켜짐 — 초록
OFFLINE = 0x94A3B8    # 꺼짐 — 회색
PENDING = 0xFACC15    # 전환 중 — 노랑
ERROR = 0xF87171      # 오류 — 빨강

FOOTER_TEXT = "Palworld Server Manager"


def _base(title: str, description: str, color: int) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text=FOOTER_TEXT)
    return embed


def _addr(ip: str | None) -> str:
    return f"`{ip}:{GAME_PORT}`" if ip else "주소 확인 중이노…"


# ── VM 상태 메타 (이모지/색상/한글 라벨) ──────────────────────
_STATE = {
    "RUNNING": ("🟢", ONLINE, "돌아가는 중"),
    "TERMINATED": ("⚫", OFFLINE, "꺼짐"),
    "STOPPED": ("⚫", OFFLINE, "꺼짐"),
    "SUSPENDED": ("⚫", OFFLINE, "잠깐 멈춤"),
    "STOPPING": ("🟠", PENDING, "끄는 중"),
    "STAGING": ("🟡", PENDING, "준비 중"),
    "PROVISIONING": ("🟡", PENDING, "준비 중"),
    "REPAIRING": ("🟠", PENDING, "고치는 중"),
}


def _state_meta(status: str) -> tuple[str, int, str]:
    return _STATE.get(status, ("⚪", BRAND, status))


# ── /start ────────────────────────────────────────────────────
def server_starting() -> discord.Embed:
    e = _base(
        "🟢 서버 켜는 중이다 이기",
        "팰월드 서버 키고 있노.\n준비되면 여따 알려주겠노 이기.",
        PENDING,
    )
    e.add_field(name="얼마나 걸리노", value="한 1~3분이다 이기", inline=True)
    return e


def already_running(ip: str | None) -> discord.Embed:
    e = _base("✅ 벌써 켜져있노", "서버 이미 돌아가고 있노. 바로 드가라노 이기!", ONLINE)
    e.add_field(name="접속 주소", value=_addr(ip), inline=False)
    return e


def server_busy(status: str) -> discord.Embed:
    _, _, label = _state_meta(status)
    return _base(
        "⏳ 좀 기다리라 봐라 이기",
        f"서버가 지금 **{label}** 상태노. 쪼매 있다 다시 해보라 이기.",
        PENDING,
    )


# ── /stop ─────────────────────────────────────────────────────
def server_stopping(saved: bool) -> discord.Embed:
    e = _base("🔴 서버 끄는 중이다 이기", "팰월드 서버 끄고 있노. 곧 정지되겠노.", OFFLINE)
    e.add_field(
        name="월드 저장",
        value="저장 완료했노 ✅" if saved else "오토세이브 믿는 수밖에 없노 (REST 미설정)",
        inline=True,
    )
    return e


def already_stopped() -> discord.Embed:
    return _base("💤 이미 꺼져있노", "서버 벌써 꺼져있노.", OFFLINE)


# ── /status ───────────────────────────────────────────────────
def status(snapshot) -> discord.Embed:
    emoji, color, label = _state_meta(snapshot.status)
    e = _base(f"{emoji} 서버 상태노", f"지금 상태는 **{label}** 노.", color)
    if snapshot.is_running and snapshot.external_ip:
        e.add_field(name="접속 주소", value=_addr(snapshot.external_ip), inline=False)
    elif snapshot.is_stopped:
        e.add_field(name="켜기", value="`/start` 치면 서버 켜지노.", inline=False)
    return e


# ── /ip ───────────────────────────────────────────────────────
def ip(address: str) -> discord.Embed:
    e = _base("🌐 접속 주소노", "여 주소로 팰월드 드가면 되노 이기.", BRAND)
    e.add_field(name="서버 주소", value=_addr(address), inline=False)
    return e


def ip_not_found() -> discord.Embed:
    return _base(
        "⚠️ IP 못 찾겠노 이기",
        "외부 IP를 못 찾았노. VM 네트워크 설정 확인해보라 이기.",
        ERROR,
    )


def server_off(status_str: str) -> discord.Embed:
    _, _, label = _state_meta(status_str)
    return _base(
        "💤 서버 꺼져있노",
        f"지금 **{label}** 상태노.\n`/start` 로 서버부터 켜라노.",
        OFFLINE,
    )


# ── 준비 완료 알림 (백그라운드) ───────────────────────────────
def ready(ip_addr: str | None) -> discord.Embed:
    e = _base("🎮 서버 준비 완료노!", "이제 팰월드 드가면 되노. 재밌게 놀다 오라노!", ONLINE)
    e.add_field(name="접속 주소", value=_addr(ip_addr), inline=False)
    return e


def ready_timeout() -> discord.Embed:
    return _base(
        "⚠️ 준비 확인 못했노",
        "서버 VM은 켜졌는데 5분 안에 게임 서버 응답이 없노.\n"
        "`/status` 로 확인하거나 쪼매 있다 다시 해보라노.",
        PENDING,
    )


# ── /players ──────────────────────────────────────────────────
def players(player_list: list[dict]) -> discord.Embed:
    lines = []
    for p in player_list:
        name = p.get("name", "누군지 모르겠노")
        level = p.get("level")
        lines.append(f"🧑‍🌾 **{name}**" + (f" · Lv.{level}" if level else ""))
    return _base(f"👥 접속자 {len(player_list)}명이노", "\n".join(lines), BRAND)


def no_players() -> discord.Embed:
    return _base("👤 아무도 없노", "지금 접속한 사람 아무도 없노.", OFFLINE)


def players_not_configured() -> discord.Embed:
    return _base(
        "⚙️ 설정부터 하라노",
        "접속자 조회 설정이 안 됐노.\n서버 REST API랑 `PALWORLD_ADMIN_PASSWORD` 설정해라노.",
        OFFLINE,
    )


# ── /help ─────────────────────────────────────────────────────
def help_all() -> discord.Embed:
    e = _base(
        "📖 명령어 도움말이노",
        "팰월드 서버는 내가 관리하노. 아래 명령어 쓰면 되노.",
        BRAND,
    )
    e.add_field(name="🟢 /start", value="팰월드 서버 켜노. 준비되면 알려주겠노.", inline=False)
    e.add_field(name="🔴 /stop", value="월드 저장하고 서버 끄노. (돈 아끼는 거노)", inline=False)
    e.add_field(name="📊 /status", value="서버 지금 뭐하고 있는지 알려주노.", inline=False)
    e.add_field(name="🌐 /ip", value="접속 주소 알려주노.", inline=False)
    e.add_field(name="👥 /players", value="지금 누가 접속해있는지 보여주노.", inline=False)
    e.add_field(name="📖 /help", value="이 도움말 보여주노.", inline=False)
    return e


# ── 공통 ──────────────────────────────────────────────────────
def denied(role_name: str) -> discord.Embed:
    return _base(
        "⛔ 권한 없노",
        f"이 명령은 `{role_name}` 역할 있어야 쓸 수 있노.",
        ERROR,
    )


def error(message: str) -> discord.Embed:
    return _base("❌ 문제 생겼노", message, ERROR)
