"""서버 감시 루프.

60초마다 한 번씩 서버 상태를 확인해서 세 가지 일을 한다:
  1. 봇 프로필 상태에 서버 상태 표시 ("🟢 3명 접속 중이노" 등)
  2. 접속/퇴장 감지 → 알림 채널에 알림
  3. 접속자 0명이 idle_stop_minutes 지속되면 경고 후 저장·자동 종료

REST API 미설정 시에는 1번(켜짐/꺼짐 표시)만 동작한다.
"""

from __future__ import annotations

import asyncio
import logging

import discord

from . import notifications
from .ui import embeds

log = logging.getLogger("palworld-bot.watcher")

_INTERVAL = 60          # 폴링 주기(초)
_WARN_BEFORE_MIN = 5    # 자동 종료 몇 분 전에 경고할지


class ServerWatcher:
    def __init__(self, bot) -> None:
        self.bot = bot
        self._prev_names: set[str] | None = None
        self._idle_since: float | None = None
        self._warned = False
        self._last_presence: str | None = None

    async def run(self) -> None:
        await self.bot.wait_until_ready()
        log.info("서버 감시 시작 (주기 %ds, 자동종료 %d분)",
                 _INTERVAL, self.bot.settings.idle_stop_minutes)
        while not self.bot.is_closed():
            try:
                await self._tick()
            except Exception:
                log.exception("감시 루프 오류 (계속 진행)")
            await asyncio.sleep(_INTERVAL)

    # ── 내부 동작 ────────────────────────────────────────────
    def _reset_idle(self) -> None:
        self._idle_since = None
        self._warned = False

    async def _set_presence(self, text: str) -> None:
        if text == self._last_presence:
            return
        try:
            await self.bot.change_presence(activity=discord.CustomActivity(name=text))
            self._last_presence = text
        except Exception:
            log.exception("상태 표시 변경 실패")

    async def _tick(self) -> None:
        s = self.bot.settings
        snap = await self.bot.vm.snapshot()

        if not snap.is_running:
            self._reset_idle()
            self._prev_names = None
            await self._set_presence("💤 서버 꺼져있노")
            return

        if not s.rest_enabled:
            await self._set_presence("🟢 서버 켜져있노")
            return

        host = s.rest_host or snap.internal_ip
        if not host:
            return

        try:
            players = await self.bot.api.players(host)
        except Exception:
            # 부팅 직후 등 REST 미응답 — 준비 중으로 표시하고 넘어감
            await self._set_presence("🟡 서버 준비 중이노")
            return

        names = {p.get("name", "?") for p in players}

        # 접속/퇴장 알림 (최초 관측 사이클은 기준선만 잡음)
        channel_id = s.notify_channel_id
        if self._prev_names is not None and channel_id:
            joined = names - self._prev_names
            left = self._prev_names - names
            if joined:
                await notifications.send_embed(
                    self.bot, channel_id, embeds.players_joined(sorted(joined))
                )
            if left:
                await notifications.send_embed(
                    self.bot, channel_id, embeds.players_left(sorted(left))
                )
        self._prev_names = names

        await self._set_presence(
            f"🟢 {len(names)}명 접속 중이노" if names else "🟢 서버 켜져있노 (0명)"
        )

        # 유휴 자동 종료
        limit = s.idle_stop_minutes
        if not limit:
            return
        if names:
            self._reset_idle()
            return

        loop = asyncio.get_running_loop()
        if self._idle_since is None:
            self._idle_since = loop.time()
            return
        idle_min = (loop.time() - self._idle_since) / 60

        if not self._warned and idle_min >= max(limit - _WARN_BEFORE_MIN, 0):
            self._warned = True
            remaining = max(int(limit - idle_min), 1)
            try:
                await self.bot.api.announce(
                    host, f"{remaining}분 뒤 서버가 자동 종료됩니다."
                )
            except Exception:
                pass
            await notifications.send_embed(
                self.bot, channel_id, embeds.idle_warning(remaining)
            )

        if idle_min >= limit:
            log.info("유휴 %d분 경과 — 자동 종료 실행", limit)
            saved = False
            try:
                saved = await self.bot.api.save(host)
            except Exception:
                pass
            await self.bot.vm.stop()
            self._reset_idle()
            self._prev_names = None
            await notifications.send_embed(
                self.bot, channel_id, embeds.idle_stopped(limit, saved)
            )
            await self._set_presence("💤 서버 꺼져있노")
