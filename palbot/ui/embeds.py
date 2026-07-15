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


# ── 감시 루프 (접속/퇴장, 자동 종료) ──────────────────────────
def players_joined(names: list[str]) -> discord.Embed:
    who = ", ".join(f"**{n}**" for n in names)
    return _base("👋 누가 들어왔노", f"{who} 들어왔노. 반겨주라 이기!", ONLINE)


def players_left(names: list[str]) -> discord.Embed:
    who = ", ".join(f"**{n}**" for n in names)
    return _base("🚪 누가 나갔노", f"{who} 나갔노. 잘 가라 이기~", OFFLINE)


def idle_warning(minutes_left: int) -> discord.Embed:
    return _base(
        "⏰ 곧 자동 종료다 이기",
        f"아무도 없어서 **{minutes_left}분 뒤** 서버 자동으로 끄겠노.\n"
        "계속 쓸 거면 지금 들어가라 이기.",
        PENDING,
    )


def idle_stopped(idle_minutes: int, saved: bool) -> discord.Embed:
    e = _base(
        "💤 자동 종료했노",
        f"{idle_minutes}분 동안 아무도 없어서 서버 껐노. (돈 아꼈다 이기)\n"
        "`/start` 치면 다시 켜지노.",
        OFFLINE,
    )
    e.add_field(
        name="월드 저장",
        value="저장 완료했노 ✅" if saved else "오토세이브 믿는 수밖에 없노",
        inline=True,
    )
    return e


# ── /announce ─────────────────────────────────────────────────
def announce_ok(message: str) -> discord.Embed:
    e = _base("📢 공지 보냈노", "게임 안에 전체 공지 띄웠다 이기.", BRAND)
    e.add_field(name="내용", value=message[:1000], inline=False)
    return e


# ── /backup ───────────────────────────────────────────────────
def backup_started(snapshot_name: str, saved: bool) -> discord.Embed:
    e = _base(
        "💾 백업 시작했노",
        "서버 디스크 스냅샷 만들기 시작했노. 몇 분 걸리노.",
        BRAND,
    )
    e.add_field(name="스냅샷 이름", value=f"`{snapshot_name}`", inline=False)
    e.add_field(
        name="월드 저장",
        value="저장 완료했노 ✅" if saved else "서버 꺼져있거나 REST 미설정이라 디스크 그대로 백업했노",
        inline=False,
    )
    return e


# ── /stop-in ──────────────────────────────────────────────────
def stopin_scheduled(minutes: int) -> discord.Embed:
    return _base(
        "⏲️ 예약 종료 걸었노",
        f"**{minutes}분 뒤** 저장하고 서버 끄겠노.\n"
        "취소하려면 `/stop-in 0` 치라 이기.",
        PENDING,
    )


def stopin_cancelled() -> discord.Embed:
    return _base("✅ 예약 취소했노", "예약 종료 없던 걸로 했다 이기.", OFFLINE)


def stopin_none() -> discord.Embed:
    return _base("🤔 예약 없는데", "취소할 예약 종료가 없노.", OFFLINE)


# ── /update ───────────────────────────────────────────────────
def server_updating(saved: bool) -> discord.Embed:
    e = _base(
        "🔄 업데이트 중이다 이기",
        "월드 저장하고 서버 껐다 켜서 최신 버전으로 올리노.\n다시 준비되면 알려주겠노.",
        PENDING,
    )
    e.add_field(
        name="월드 저장",
        value="저장 완료했노 ✅" if saved else "오토세이브 믿는 수밖에 없노 (REST 미설정)",
        inline=True,
    )
    e.add_field(name="얼마나 걸리노", value="한 3~5분이다 이기", inline=True)
    return e


def update_stop_timeout() -> discord.Embed:
    return _base(
        "⚠️ 업데이트 실패했노",
        "서버가 제때 안 꺼져서 업데이트를 못 했노.\n`/status` 확인하고 다시 해보라 이기.",
        ERROR,
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
    e.add_field(name="🔄 /update", value="저장하고 재시작해서 팰월드 최신 버전으로 올리노.", inline=False)
    e.add_field(name="📢 /announce", value="게임 안에 전체 공지 보내노.", inline=False)
    e.add_field(name="⏲️ /stop-in", value="N분 뒤 예약 종료하노. 0 치면 취소노.", inline=False)
    e.add_field(name="💾 /backup", value="디스크 스냅샷으로 월드 백업하노.", inline=False)
    e.add_field(name="📖 /help", value="이 도움말 보여주노.", inline=False)
    e.add_field(
        name="🤖 자동으로 해주는 것",
        value="• 아무도 없으면 일정 시간 뒤 알아서 끄노 (돈 절약)\n"
              "• 누가 들어오고 나가면 알려주노\n"
              "• 봇 상태 메시지에 서버 상태 떠있노",
        inline=False,
    )
    return e


# ── 스팟 회수 감지 (감시 루프) ────────────────────────────────
def preempted() -> discord.Embed:
    return _base(
        "⚡ 서버 튕겼노 (스팟 회수)",
        "GCP가 스팟 서버를 회수해갔노. 서버 문제도 아니고 니 인터넷 문제도 아니다 이기.\n"
        "`/start` 치면 1~3분 안에 복구되노. (오토세이브라 피해는 거의 없노)",
        ERROR,
    )


# ── 상시 가동 모드 (오라클 무료 등) ───────────────────────────
def always_on(ip_addr: str | None) -> discord.Embed:
    e = _base(
        "♾️ 서버 24시간 켜져있노",
        "이 서버는 공짜라 끌 필요가 없노. 아무 때나 드가라 이기!",
        ONLINE,
    )
    if ip_addr:
        e.add_field(name="접속 주소", value=_addr(ip_addr), inline=False)
    return e


def power_unavailable() -> discord.Embed:
    return _base(
        "♾️ 그거 여기선 안 쓰노",
        "이 서버는 상시 가동이라 전원/스냅샷 조작이 없노.\n"
        "`/players` `/announce` 는 그대로 쓸 수 있다 이기.",
        OFFLINE,
    )


# ── 공통 ──────────────────────────────────────────────────────
def denied(role_name: str) -> discord.Embed:
    return _base(
        "⛔ 권한 없노",
        f"이 명령은 `{role_name}` 역할 있어야 쓸 수 있노.",
        ERROR,
    )


def error(message: str) -> discord.Embed:
    return _base("❌ 문제 생겼노", message, ERROR)
