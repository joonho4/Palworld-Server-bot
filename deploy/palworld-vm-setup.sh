#!/usr/bin/env bash
# 팰월드 VM 최초 설치 스크립트 (Ubuntu 22.04 기준)
# 사용: 팰월드 VM에 SSH 접속 후  sudo bash palworld-vm-setup.sh
set -euo pipefail

echo "==> SteamCMD 설치"
dpkg --add-architecture i386
apt update
apt install -y software-properties-common
add-apt-repository -y multiverse
apt update
echo steam steam/question select "I AGREE" | debconf-set-selections
echo steam steam/license note '' | debconf-set-selections
DEBIAN_FRONTEND=noninteractive apt install -y steamcmd

echo "==> palworld 유저 생성 및 서버 설치"
id palworld &>/dev/null || useradd -m -s /bin/bash palworld
sudo -u palworld /usr/games/steamcmd \
  +force_install_dir /home/palworld/server \
  +login anonymous +app_update 2394010 validate +quit

echo "==> systemd 서비스 등록"
# 이 스크립트와 같은 폴더의 palworld.service 를 복사한다고 가정
if [ -f "$(dirname "$0")/palworld.service" ]; then
  cp "$(dirname "$0")/palworld.service" /etc/systemd/system/palworld.service
else
  echo "!! palworld.service 파일을 찾지 못했습니다. 수동으로 /etc/systemd/system/ 에 배치하세요."
fi
systemctl daemon-reload
systemctl enable --now palworld

echo "==> 완료. 상태 확인:"
systemctl --no-pager status palworld || true
echo "게임 포트(UDP 8211) 방화벽 규칙이 GCP에 설정돼 있는지 확인하세요."
