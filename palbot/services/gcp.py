"""GCP Compute Engine VM 제어.

google-cloud-compute 는 동기식이므로 모든 호출을 asyncio.to_thread 로 감싸
Discord 이벤트 루프를 막지 않도록 한다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from google.cloud import compute_v1

# 정지 상태로 간주하는 인스턴스 status 값들
STOPPED_STATES = frozenset({"TERMINATED", "STOPPED", "SUSPENDED"})


class VMController:
    def __init__(self, project: str, zone: str, instance: str, disk: str = "") -> None:
        self._project = project
        self._zone = zone
        self._instance = instance
        self._disk = disk or instance   # 부팅 디스크 이름은 기본적으로 인스턴스와 동일
        # 인증: 봇 VM에 연결된 서비스 계정(ADC)을 자동 사용. 키 파일 불필요.
        self._client = compute_v1.InstancesClient()
        self._disks = compute_v1.DisksClient()

    async def create_disk_snapshot(self) -> str:
        """부팅 디스크 스냅샷 생성을 시작하고 스냅샷 이름을 반환한다 (완료 대기 안 함)."""
        name = f"palworld-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
        # 저장 위치를 VM과 같은 리전으로 고정 — 기본값(멀티리전)보다 저장·업로드 비용이 ~40% 저렴
        region = self._zone.rsplit("-", 1)[0]
        await asyncio.to_thread(
            self._disks.create_snapshot,
            project=self._project,
            zone=self._zone,
            disk=self._disk,
            snapshot_resource=compute_v1.Snapshot(name=name, storage_locations=[region]),
        )
        return name

    async def _get(self) -> compute_v1.Instance:
        return await asyncio.to_thread(
            self._client.get,
            project=self._project,
            zone=self._zone,
            instance=self._instance,
        )

    async def status(self) -> str:
        inst = await self._get()
        return inst.status

    async def start(self) -> None:
        await asyncio.to_thread(
            self._client.start,
            project=self._project,
            zone=self._zone,
            instance=self._instance,
        )

    async def stop(self) -> None:
        await asyncio.to_thread(
            self._client.stop,
            project=self._project,
            zone=self._zone,
            instance=self._instance,
        )

    async def external_ip(self) -> str | None:
        return _external_ip(await self._get())

    async def internal_ip(self) -> str | None:
        inst = await self._get()
        for iface in inst.network_interfaces:
            if iface.network_i_p:
                return iface.network_i_p
        return None

    async def snapshot(self) -> "VMSnapshot":
        """상태·IP를 한 번의 조회로 함께 반환 (API 호출 절약)."""
        inst = await self._get()
        internal = None
        for iface in inst.network_interfaces:
            if iface.network_i_p:
                internal = iface.network_i_p
                break
        return VMSnapshot(
            status=inst.status,
            external_ip=_external_ip(inst),
            internal_ip=internal,
        )


def _external_ip(inst: compute_v1.Instance) -> str | None:
    for iface in inst.network_interfaces:
        for cfg in iface.access_configs:
            if cfg.nat_i_p:
                return cfg.nat_i_p
    return None


class VMSnapshot:
    __slots__ = ("status", "external_ip", "internal_ip")

    def __init__(self, status: str, external_ip: str | None, internal_ip: str | None):
        self.status = status
        self.external_ip = external_ip
        self.internal_ip = internal_ip

    @property
    def is_stopped(self) -> bool:
        return self.status in STOPPED_STATES

    @property
    def is_running(self) -> bool:
        return self.status == "RUNNING"
