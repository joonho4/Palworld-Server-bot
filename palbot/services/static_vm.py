"""전원 제어가 없는 상시 가동 서버용 컨트롤러 (오라클 무료 티어 등).

VM_PROVIDER=none 일 때 VMController 대신 사용된다.
서버는 항상 켜져 있다고 간주하며, 전원 조작은 지원하지 않는다.
"""

from __future__ import annotations

from .gcp import VMSnapshot


class PowerControlUnavailable(Exception):
    """상시 가동 서버에서는 전원 제어를 지원하지 않는다."""


class StaticVM:
    def __init__(self, public_ip: str, rest_host: str) -> None:
        self._public_ip = public_ip or None
        # REST 호스트가 곧 서버 주소 — 내부 IP 조회 대신 그대로 사용
        self._host = rest_host or public_ip or None

    async def snapshot(self) -> VMSnapshot:
        return VMSnapshot(
            status="RUNNING",
            external_ip=self._public_ip,
            internal_ip=self._host,
        )

    async def status(self) -> str:
        return "RUNNING"

    async def external_ip(self) -> str | None:
        return self._public_ip

    async def internal_ip(self) -> str | None:
        return self._host

    async def start(self) -> None:
        raise PowerControlUnavailable

    async def stop(self) -> None:
        raise PowerControlUnavailable

    async def create_disk_snapshot(self) -> str:
        raise PowerControlUnavailable
