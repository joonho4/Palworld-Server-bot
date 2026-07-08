"""채널 알림 및 서버 준비 완료 폴링.

/start 이후 백그라운드에서 REST API가 응답할 때까지 기다렸다가,
게임 서버가 실제로 접속 가능해지면 알림 채널에 준비 완료 임베드를 보낸다.
"""

from __future__ import annotations

import asyncio
import logging

import discord

from .services.gcp import VMController
from .services.palworld_api import PalworldAPI
from .ui import embeds

log = logging.getLogger("palworld-bot.notify")

# 준비 완료 폴링 설정
_POLL_INTERVAL = 10       # 초
_POLL_TIMEOUT = 300       # 초 (5분 안에 안 뜨면 포기)


async def send_embed(
    bot: discord.Client, channel_id: int | None, embed: discord.Embed
) -> None:
    """설정된 알림 채널로 임베드 전송. 채널 미설정/조회 실패 시 조용히 무시."""
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            log.warning("알림 채널 %s 를 찾지 못했습니다.", channel_id)
            return
    if isinstance(channel, discord.abc.Messageable):
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            log.exception("알림 채널 전송 실패")


async def watch_until_ready(
    bot: discord.Client,
    vm: VMController,
    api: PalworldAPI,
    rest_host: str,
    channel_id: int | None,
) -> None:
    """서버가 REST API에 응답할 때까지 폴링 후 준비 완료 알림을 보낸다.

    rest_host 가 비어 있으면 VM 내부 IP를 동적으로 조회한다.
    """
    host = rest_host
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _POLL_TIMEOUT

    while loop.time() < deadline:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            if not host:
                host = await vm.internal_ip() or ""
                if not host:
                    continue
            if await api.is_ready(host):
                ip = await vm.external_ip()
                await send_embed(bot, channel_id, embeds.ready(ip))
                return
        except Exception:
            log.exception("준비 상태 폴링 중 오류 (계속 재시도)")

    await send_embed(bot, channel_id, embeds.ready_timeout())
