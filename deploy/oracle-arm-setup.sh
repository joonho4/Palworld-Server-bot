#!/usr/bin/env bash
# 오라클 클라우드 ARM(Ampere A1) 팰월드 서버 설치 스크립트 — Ubuntu 22.04 (aarch64)
#
# 팰월드 전용 서버는 x86 전용이므로 에뮬레이터로 구동한다:
#   box86 → steamcmd(32비트 x86) 실행용
#   box64 → PalServer(64비트 x86) 실행용
# 두 패키지가 binfmt를 등록해서, 설치 후에는 x86 바이너리가 투명하게 실행된다.
#
# 사용:
#   sudo bash oracle-arm-setup.sh                 # 전체 설치
#   sudo bash oracle-arm-setup.sh rest <비밀번호>  # REST API 설정 (서버 1회 실행 후)
set -euo pipefail

INI=/home/palworld/server/Pal/Saved/Config/LinuxServer/PalWorldSettings.ini

# ── REST API 설정 서브커맨드 ─────────────────────────────────
if [ "${1:-}" = "rest" ]; then
  [ -n "${2:-}" ] || { echo "사용법: sudo bash $0 rest <비밀번호>"; exit 1; }
  systemctl stop palworld
  [ -s "$INI" ] || sudo -u palworld cp /home/palworld/server/DefaultPalWorldSettings.ini "$INI"
  sudo -u palworld sed -i 's/RESTAPIEnabled=False/RESTAPIEnabled=True/' "$INI"
  sudo -u palworld sed -i "s/AdminPassword=\"\"/AdminPassword=\"$2\"/" "$INI"
  systemctl start palworld
  echo "==> REST API 설정 완료 (포트 8212)"
  exit 0
fi

if [ "$(uname -m)" != "aarch64" ]; then
  echo "!! 이 스크립트는 ARM64(aarch64) 전용입니다. x86 VM은 palworld-vm-setup.sh 를 쓰세요."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "==> 1/6 box86 / box64 설치 (x86 에뮬레이터)"
dpkg --add-architecture armhf
apt-get update
apt-get install -y wget gnupg ca-certificates \
  libc6:armhf libstdc++6:armhf libncurses6:armhf

wget -qO- https://ryanfortner.github.io/box64-debs/KEY.gpg \
  | gpg --dearmor --yes -o /usr/share/keyrings/box64-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/box64-archive-keyring.gpg] https://ryanfortner.github.io/box64-debs/debian ./" \
  > /etc/apt/sources.list.d/box64.list

wget -qO- https://ryanfortner.github.io/box86-debs/KEY.gpg \
  | gpg --dearmor --yes -o /usr/share/keyrings/box86-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/box86-archive-keyring.gpg] https://ryanfortner.github.io/box86-debs/debian ./" \
  > /etc/apt/sources.list.d/box86.list

apt-get update
apt-get install -y box64-arm64 || apt-get install -y box64
apt-get install -y box86-generic-arm || apt-get install -y box86

echo "==> 2/6 palworld 유저 + steamcmd 설치"
id palworld &>/dev/null || useradd -m -s /bin/bash palworld
sudo -u palworld bash -c '
  mkdir -p ~/steamcmd && cd ~/steamcmd &&
  wget -qO- https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz | tar xz
'

echo "==> 3/6 팰월드 서버 다운로드 (에뮬레이션이라 오래 걸림 — 10분 이상 정상)"
sudo -u palworld bash -c '
  cd ~/steamcmd &&
  ./steamcmd.sh +@sSteamCmdForcePlatformType linux \
    +force_install_dir /home/palworld/server \
    +login anonymous +app_update 2394010 validate +quit
'

echo "==> 4/6 steamclient.so 링크 (팰월드가 요구)"
sudo -u palworld bash -c '
  mkdir -p ~/.steam/sdk64 &&
  ln -sf ~/steamcmd/linux64/steamclient.so ~/.steam/sdk64/steamclient.so
'

echo "==> 5/6 systemd 서비스 등록"
cat > /etc/systemd/system/palworld.service <<'UNIT'
[Unit]
Description=Palworld Dedicated Server (ARM via box64)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=palworld
WorkingDirectory=/home/palworld/server
# 시작 시 최신 버전으로 업데이트 (에뮬레이션이라 느려서 타임아웃 넉넉히)
ExecStartPre=/home/palworld/steamcmd/steamcmd.sh +@sSteamCmdForcePlatformType linux +force_install_dir /home/palworld/server +login anonymous +app_update 2394010 validate +quit
ExecStart=/home/palworld/server/PalServer.sh -useperfthreads -NoAsyncLoadingThread -UseMultithreadForDS
TimeoutStartSec=900
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now palworld

echo "==> 6/6 오라클 자체 방화벽(iptables) 개방"
# 오라클 Ubuntu 이미지는 OS 안에서도 iptables 로 대부분의 포트를 막아둔다.
# (OCI 콘솔의 보안 목록과 별개 — 둘 다 열어야 접속됨!)
iptables -I INPUT -p udp --dport 8211 -j ACCEPT
iptables -I INPUT -p tcp --dport 8212 -j ACCEPT
apt-get install -y iptables-persistent
netfilter-persistent save

echo ""
echo "==> 완료! 상태 확인:"
systemctl --no-pager status palworld || true
echo ""
echo "다음 할 일:"
echo "  1. OCI 콘솔 보안 목록(Security List)에 인그레스 추가: UDP 8211 (전체), TCP 8212 (봇 IP만)"
echo "  2. 서버 1회 실행 후 REST 설정:  sudo bash $0 rest <비밀번호>"
echo "  3. 세이브 이사는 ORACLE-MIGRATION.md 참고"
