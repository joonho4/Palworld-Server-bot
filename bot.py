"""팰월드 서버 제어 Discord 봇.

슬래시 명령으로 GCP Compute Engine의 팰월드 VM을 켜고 끕니다.
봇은 VM 전원만 제어하고, 게임 서버 실행은 VM 안의 systemd(enable)가 처리합니다.
"""

import asyncio
import logging
import os

import discord
from discord import app_commands
from dotenv import load_dotenv
from google.cloud import compute_v1

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("palworld-bot")

# ── 설정 ──────────────────────────────────────────────────────
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = os.getenv("GUILD_ID")
CONTROL_ROLE = os.getenv("CONTROL_ROLE", "").strip()

GCP_PROJECT = os.environ["GCP_PROJECT"]
INSTANCE = os.environ["PALWORLD_INSTANCE"]
ZONE = os.environ["PALWORLD_ZONE"]

GUILD = discord.Object(id=int(GUILD_ID)) if GUILD_ID else None

# google-cloud-compute 클라이언트는 동기식이라 to_thread로 감싸 호출한다.
_instances = compute_v1.InstancesClient()


# ── GCP 헬퍼 (블로킹 → to_thread로 실행) ──────────────────────
def _get_instance() -> compute_v1.Instance:
    return _instances.get(project=GCP_PROJECT, zone=ZONE, instance=INSTANCE)


def _start_instance() -> None:
    _instances.start(project=GCP_PROJECT, zone=ZONE, instance=INSTANCE)


def _stop_instance() -> None:
    _instances.stop(project=GCP_PROJECT, zone=ZONE, instance=INSTANCE)


def _external_ip(inst: compute_v1.Instance) -> str | None:
    for iface in inst.network_interfaces:
        for cfg in iface.access_configs:
            if cfg.nat_i_p:
                return cfg.nat_i_p
    return None


# ── 권한 체크 ─────────────────────────────────────────────────
def has_control_permission(interaction: discord.Interaction) -> bool:
    """CONTROL_ROLE이 설정돼 있으면 해당 역할 보유자만 허용."""
    if not CONTROL_ROLE:
        return True
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    return any(r.name == CONTROL_ROLE for r in member.roles)


# ── 봇 ────────────────────────────────────────────────────────
class PalworldBot(discord.Client):
    def __init__(self) -> None:
        # 슬래시 명령만 쓰므로 기본 인텐트로 충분 (메시지 내용 인텐트 불필요)
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        if GUILD:
            self.tree.copy_global_to(guild=GUILD)
            await self.tree.sync(guild=GUILD)
            log.info("슬래시 명령을 길드 %s에 동기화했습니다.", GUILD_ID)
        else:
            await self.tree.sync()
            log.info("슬래시 명령을 글로벌 동기화했습니다 (최대 1시간 지연).")

    async def on_ready(self) -> None:
        log.info("로그인 완료: %s (id=%s)", self.user, self.user.id)


client = PalworldBot()
tree = client.tree


@tree.command(description="팰월드 서버(VM)를 켭니다.")
async def start(interaction: discord.Interaction) -> None:
    if not has_control_permission(interaction):
        await interaction.response.send_message(
            f"⛔ `{CONTROL_ROLE}` 역할이 있어야 서버를 켤 수 있어요.", ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)
    try:
        inst = await asyncio.to_thread(_get_instance)
        if inst.status == "RUNNING":
            ip = _external_ip(inst)
            await interaction.followup.send(
                f"✅ 이미 켜져 있어요. 접속: `{ip}:8211`" if ip else "✅ 이미 켜져 있어요."
            )
            return
        if inst.status not in ("TERMINATED", "STOPPED", "SUSPENDED"):
            await interaction.followup.send(
                f"⏳ 지금 상태가 `{inst.status}`라 잠시 후 다시 시도해 주세요."
            )
            return

        await asyncio.to_thread(_start_instance)
        await interaction.followup.send(
            "🟢 서버를 켜는 중입니다. 게임 서버가 완전히 뜨기까지 1~3분 정도 걸려요.\n"
            "잠시 후 `/ip`로 접속 주소를 확인하세요."
        )
    except Exception:
        log.exception("start 실패")
        await interaction.followup.send("❌ 서버를 켜는 중 오류가 발생했어요. 로그를 확인해 주세요.")


@tree.command(description="팰월드 서버(VM)를 끕니다. (비용 절약)")
async def stop(interaction: discord.Interaction) -> None:
    if not has_control_permission(interaction):
        await interaction.response.send_message(
            f"⛔ `{CONTROL_ROLE}` 역할이 있어야 서버를 끌 수 있어요.", ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)
    try:
        inst = await asyncio.to_thread(_get_instance)
        if inst.status in ("TERMINATED", "STOPPED", "SUSPENDED"):
            await interaction.followup.send("✅ 이미 꺼져 있어요.")
            return

        await asyncio.to_thread(_stop_instance)
        await interaction.followup.send("🔴 서버를 끄는 중입니다. 곧 정지돼요.")
    except Exception:
        log.exception("stop 실패")
        await interaction.followup.send("❌ 서버를 끄는 중 오류가 발생했어요. 로그를 확인해 주세요.")


@tree.command(description="서버(VM) 상태를 확인합니다.")
async def status(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True)
    try:
        inst = await asyncio.to_thread(_get_instance)
        emoji = {"RUNNING": "🟢", "TERMINATED": "🔴", "STOPPING": "🟠", "STAGING": "🟡"}.get(
            inst.status, "⚪"
        )
        msg = f"{emoji} 상태: **{inst.status}**"
        if inst.status == "RUNNING":
            ip = _external_ip(inst)
            if ip:
                msg += f"\n접속: `{ip}:8211`"
        await interaction.followup.send(msg)
    except Exception:
        log.exception("status 실패")
        await interaction.followup.send("❌ 상태 확인 중 오류가 발생했어요.")


@tree.command(description="현재 접속용 외부 IP를 보여줍니다.")
async def ip(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True)
    try:
        inst = await asyncio.to_thread(_get_instance)
        if inst.status != "RUNNING":
            await interaction.followup.send(
                f"⚠️ 서버가 꺼져 있어요 (상태: `{inst.status}`). `/start`로 먼저 켜주세요."
            )
            return
        addr = _external_ip(inst)
        if addr:
            await interaction.followup.send(f"🌐 접속 주소: `{addr}:8211`")
        else:
            await interaction.followup.send("⚠️ 외부 IP를 찾지 못했어요. VM 네트워크 설정을 확인하세요.")
    except Exception:
        log.exception("ip 실패")
        await interaction.followup.send("❌ IP 확인 중 오류가 발생했어요.")


if __name__ == "__main__":
    client.run(DISCORD_TOKEN, log_handler=None)
