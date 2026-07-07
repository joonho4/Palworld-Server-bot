"""팰월드 전용 서버 REST API 클라이언트.

서버 설정(PalWorldSettings.ini)에서 RESTAPIEnabled=True 로 켜야 사용 가능.
Basic 인증(username="admin", password=AdminPassword)을 사용한다.

주요 엔드포인트:
  GET /v1/api/players  -> {"players": [{"name": ..., "level": ...}, ...]}
  GET /v1/api/info     -> {"version": ..., "servername": ...}
"""

from __future__ import annotations

import aiohttp


class PalworldAPIError(Exception):
    pass


class PalworldAPI:
    def __init__(self, port: int, admin_password: str, timeout: float = 5.0) -> None:
        self._port = port
        self._auth = aiohttp.BasicAuth("admin", admin_password)
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    def _base(self, host: str) -> str:
        return f"http://{host}:{self._port}/v1/api"

    async def _get(self, host: str, path: str) -> dict:
        url = f"{self._base(host)}{path}"
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            async with session.get(url, auth=self._auth) as resp:
                if resp.status != 200:
                    raise PalworldAPIError(f"{path} -> HTTP {resp.status}")
                return await resp.json()

    async def is_ready(self, host: str) -> bool:
        """게임 서버가 REST API에 응답하면 True (부팅/로딩 완료 판정용)."""
        try:
            await self._get(host, "/info")
            return True
        except (aiohttp.ClientError, PalworldAPIError, TimeoutError):
            return False

    async def players(self, host: str) -> list[dict]:
        """접속 중인 플레이어 목록. 각 항목은 name/level 등을 포함."""
        data = await self._get(host, "/players")
        return data.get("players", [])

    async def info(self, host: str) -> dict:
        return await self._get(host, "/info")
