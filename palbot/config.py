"""환경변수 로딩 및 검증.

.env 파일 또는 실제 환경변수에서 설정을 읽어 Settings 객체로 제공한다.
필수 값이 없으면 명확한 에러로 조기에 실패한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"필수 환경변수 {name} 가 설정되지 않았습니다. .env 를 확인하세요.")
    return value


@dataclass(frozen=True)
class Settings:
    # Discord
    discord_token: str
    guild_id: int | None
    control_role: str
    notify_channel_id: int | None

    # GCP
    gcp_project: str
    instance: str
    zone: str

    # Palworld REST API (접속자 수 / 준비 상태 조회용)
    rest_host: str          # 비우면 GCP에서 VM 내부 IP를 동적으로 조회
    rest_port: int
    admin_password: str

    # 자동 종료: 접속자 0명이 이 시간(분) 지속되면 저장 후 종료. 0이면 비활성
    idle_stop_minutes: int
    # /backup 스냅샷 대상 디스크. 비우면 인스턴스 이름과 동일한 부팅 디스크로 간주
    backup_disk: str

    @property
    def rest_enabled(self) -> bool:
        """REST API 기반 기능(/players, 준비 알림) 사용 가능 여부."""
        return bool(self.admin_password)

    @classmethod
    def load(cls) -> "Settings":
        guild = os.getenv("GUILD_ID")
        channel = os.getenv("NOTIFY_CHANNEL_ID")
        return cls(
            discord_token=_require("DISCORD_TOKEN"),
            guild_id=int(guild) if guild else None,
            control_role=os.getenv("CONTROL_ROLE", "").strip(),
            notify_channel_id=int(channel) if channel else None,
            gcp_project=_require("GCP_PROJECT"),
            instance=_require("PALWORLD_INSTANCE"),
            zone=_require("PALWORLD_ZONE"),
            rest_host=os.getenv("PALWORLD_REST_HOST", "").strip(),
            rest_port=int(os.getenv("PALWORLD_REST_PORT", "8212")),
            admin_password=os.getenv("PALWORLD_ADMIN_PASSWORD", "").strip(),
            idle_stop_minutes=int(os.getenv("IDLE_STOP_MINUTES", "0") or 0),
            backup_disk=os.getenv("PALWORLD_DISK", "").strip(),
        )
