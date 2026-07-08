"""Discord 메시지 디자인 (팰월드 테마 임베드).

모든 봇 응답의 디자인을 이 파일 한곳에서 관리한다.
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
    return f"`{ip}:{GAME_PORT}`" if ip else "주소 확인 중…"


# ── VM 상태 메타 (이모지/색상/한글 라벨) ──────────────────────
_STATE = {
    "RUNNING": ("🟢", ONLINE, "실행 중"),
    "TERMINATED": ("⚫", OFFLINE, "꺼짐"),
    "STOPPED": ("⚫", OFFLINE, "꺼짐"),
    "SUSPENDED": ("⚫", OFFLINE, "일시정지"),
    "STOPPING": ("🟠", PENDING, "종료 중"),
    "STAGING": ("🟡", PENDING, "준비 중"),
    "PROVISIONING": ("🟡", PENDING, "프로비저닝"),
    "REPAIRING": ("🟠", PENDING, "복구 중"),
}


def _state_meta(status: str) -> tuple[str, int, str]:
    return _STATE.get(status, ("⚪", BRAND, status))


# ── /start ────────────────────────────────────────────────────
def server_starting() -> discord.Embed:
    e = _base(
        "🟢 서버를 켜는 중",
        "팰월드 서버를 시작하고 있어요.\n게임 서버가 준비되면 이 채널로 알려드릴게요.",
        PENDING,
    )
    e.add_field(name="예상 소요", value="약 1~3분", inline=True)
    return e


def already_running(ip: str | None) -> discord.Embed:
    e = _base("✅ 이미 실행 중", "서버가 이미 켜져 있어요. 바로 접속하세요!", ONLINE)
    e.add_field(name="접속 주소", value=_addr(ip), inline=False)
    return e


def server_busy(status: str) -> discord.Embed:
    _, _, label = _state_meta(status)
    return _base(
        "⏳ 잠시만요",
        f"서버가 지금 **{label}** 상태예요. 잠시 후 다시 시도해 주세요.",
        PENDING,
    )


# ── /stop ─────────────────────────────────────────────────────
def server_stopping(saved: bool) -> discord.Embed:
    desc = "팰월드 서버를 종료하고 있어요. 곧 정지됩니다."
    e = _base("🔴 서버를 끄는 중", desc, OFFLINE)
    e.add_field(
        name="월드 저장",
        value="완료 ✅" if saved else "오토세이브에 의존 (REST 미설정)",
        inline=True,
    )
    return e


def already_stopped() -> discord.Embed:
    return _base("💤 이미 꺼짐", "서버가 이미 꺼져 있어요.", OFFLINE)


# ── /status ───────────────────────────────────────────────────
def status(snapshot) -> discord.Embed:
    emoji, color, label = _state_meta(snapshot.status)
    e = _base(f"{emoji} 서버 상태", f"현재 상태: **{label}**", color)
    if snapshot.is_running and snapshot.external_ip:
        e.add_field(name="접속 주소", value=_addr(snapshot.external_ip), inline=False)
    elif snapshot.is_stopped:
        e.add_field(name="켜기", value="`/start` 로 서버를 켤 수 있어요.", inline=False)
    return e


# ── /ip ───────────────────────────────────────────────────────
def ip(address: str) -> discord.Embed:
    e = _base("🌐 접속 주소", "아래 주소로 팰월드에서 접속하세요.", BRAND)
    e.add_field(name="서버 주소", value=_addr(address), inline=False)
    return e


def ip_not_found() -> discord.Embed:
    return _base(
        "⚠️ IP를 찾지 못함",
        "외부 IP를 확인하지 못했어요. VM 네트워크 설정을 확인해 주세요.",
        ERROR,
    )


def server_off(status_str: str) -> discord.Embed:
    _, _, label = _state_meta(status_str)
    return _base(
        "💤 서버가 꺼져 있어요",
        f"현재 상태는 **{label}** 예요.\n`/start` 로 먼저 서버를 켜주세요.",
        OFFLINE,
    )


# ── 준비 완료 알림 (백그라운드) ───────────────────────────────
def ready(ip_addr: str | None) -> discord.Embed:
    e = _base("🎮 서버 준비 완료!", "팰월드 서버에 이제 접속할 수 있어요. 즐거운 모험 되세요!", ONLINE)
    e.add_field(name="접속 주소", value=_addr(ip_addr), inline=False)
    return e


def ready_timeout() -> discord.Embed:
    return _base(
        "⚠️ 준비 확인 실패",
        "서버 VM은 켜졌지만 5분 안에 게임 서버 응답을 확인하지 못했어요.\n"
        "`/status` 로 확인하거나 잠시 후 다시 시도해 주세요.",
        PENDING,
    )


# ── /players ──────────────────────────────────────────────────
def players(player_list: list[dict]) -> discord.Embed:
    lines = []
    for p in player_list:
        name = p.get("name", "알 수 없음")
        level = p.get("level")
        lines.append(f"🧑‍🌾 **{name}**" + (f" · Lv.{level}" if level else ""))
    e = _base(f"👥 접속자 {len(player_list)}명", "\n".join(lines), BRAND)
    return e


def no_players() -> discord.Embed:
    return _base("👤 접속자 없음", "현재 접속 중인 플레이어가 없어요.", OFFLINE)


def players_not_configured() -> discord.Embed:
    return _base(
        "⚙️ 설정 필요",
        "접속자 조회가 설정되지 않았어요.\n서버의 REST API와 `PALWORLD_ADMIN_PASSWORD` 를 설정해 주세요.",
        OFFLINE,
    )


# ── 공통 ──────────────────────────────────────────────────────
def denied(role_name: str) -> discord.Embed:
    return _base(
        "⛔ 권한 없음",
        f"이 명령은 `{role_name}` 역할이 있어야 사용할 수 있어요.",
        ERROR,
    )


def error(message: str) -> discord.Embed:
    return _base("❌ 오류", message, ERROR)
