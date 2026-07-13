# 팰월드 서버 Discord 제어 봇

[![CI](https://github.com/joonho4/Palworld-Server-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/joonho4/Palworld-Server-bot/actions/workflows/ci.yml)

GCP에 배포된 팰월드 전용 서버를 Discord 슬래시 명령으로 켜고 끄는 봇입니다.
비용 절약이 핵심입니다 — 팰월드 VM은 필요할 때만 켜고, 평소엔 꺼둡니다.

---

## 목차
1. [아키텍처](#1-아키텍처)
2. [비용 개요](#2-비용-개요)
3. [사전 준비](#3-사전-준비)
4. [1단계 · 팰월드 서버 VM 만들기](#4-1단계--팰월드-서버-vm-만들기)
5. [2단계 · 봇 VM + 서비스 계정 + IAM](#5-2단계--봇-vm--서비스-계정--iam)
6. [3단계 · Discord 애플리케이션 등록](#6-3단계--discord-애플리케이션-등록)
7. [4단계 · 봇 배포 및 실행](#7-4단계--봇-배포-및-실행)
8. [봇 명령어](#8-봇-명령어)
9. [트러블슈팅](#9-트러블슈팅)

---

## 1. 아키텍처

```
Discord 사용자
    │  /start /stop /status /ip
    ▼
┌─────────────────────────────┐
│ 봇 VM  (e2-micro, 항상 켜짐)   │   ← 무료 티어, discord.py 게이트웨이 상주
│  · discord.py 봇 프로세스      │
│  · 서비스 계정 "연결"(attached) │
└──────────────┬──────────────┘
               │ google-cloud-compute API (start / stop / get)
               ▼
┌─────────────────────────────┐
│ 팰월드 VM (e2-standard-4)      │   ← 필요할 때만 켜짐 (비용 절약)
│  · SteamCMD + PalServer       │
│  · systemd 서비스로 자동 실행   │
└─────────────────────────────┘
```

**왜 VM을 2개로 나누나?**
- **팰월드 VM**은 RAM 16GB급이 필요해서 무료가 아니고, 켜두면 비쌉니다 → 필요할 때만 켬.
- **봇 VM**은 Discord 게이트웨이 웹소켓을 24시간 유지해야 하므로 항상 켜져 있어야 함 → 무료인 `e2-micro`로 상주.
- Cloud Run은 요청 기반(0으로 스케일)이라 상주 게이트웨이 봇에 부적합해서 제외.

**왜 서비스 계정 "키 파일" 대신 "연결(attached)"인가?**
- 봇 VM에 서비스 계정을 직접 붙이면 JSON 키 파일이 필요 없습니다.
- 키 파일이 없으니 유출 위험이 사라짐 (GCP 공식 권장 방식).
- 라이브러리가 VM에 붙은 계정을 자동 인식(ADC, Application Default Credentials).

---

## 2. 비용 개요

> 리전/환율에 따라 달라지므로 대략치입니다. 정확한 값은 [GCP 요금 계산기](https://cloud.google.com/products/calculator)로 확인하세요.

| 구성 | 사양 | 요금(대략) | 비고 |
|---|---|---|---|
| 봇 VM | `e2-micro` | **월 $0** | 무료 티어 리전(us-west1/us-central1/us-east1)에서 1대 무료 |
| 팰월드 VM (켜짐) | `e2-standard-4` (4vCPU/16GB) | 시간당 ≈ $0.13 | 24시간 켜두면 월 $95+ → **끄는 게 핵심** |
| 팰월드 VM (꺼짐) | 디스크만 유지 | 월 ≈ $2~4 | 정지 시 디스크 요금만 부과 |
| 고정 IP(선택) | Static IP | 월 ≈ $2~3 | 꺼진 VM에 고정 IP 붙이면 소액 과금 |

**비용 팁**
- 하루 4시간씩 주말만 켠다면 팰월드 컴퓨팅 비용은 월 $5~10 수준으로 떨어집니다.
- 스팟(Spot) VM을 쓰면 60~90% 저렴하지만 갑자기 종료될 수 있으니 초기엔 일반 VM 권장.
- 봇으로 `/stop`을 자주 눌러 끄는 습관이 곧 비용 절약입니다.

---

## 3. 사전 준비

- [ ] GCP 계정 + **결제 계정 연결**된 프로젝트 (무료 크레딧 $300 있으면 활용)
- [ ] 로컬에 `gcloud` CLI 설치 (선택 — 콘솔 웹 UI로만도 가능)
- [ ] Discord 계정 + 봇을 넣을 서버(길드)의 관리자 권한
- [ ] Steam 계정은 **불필요** (팰월드 전용 서버는 익명 SteamCMD로 설치 가능)

프로젝트 ID / 리전 / 존을 미리 정해두면 편합니다. 예시:
```
PROJECT_ID = palworld-bot-123456
GAME_ZONE  = asia-northeast3-a   # 팰월드 VM — 서울 (한국에서 핑 ~5-20ms)
BOT_ZONE   = us-central1-a       # 봇 VM — 무료 e2-micro는 미국 리전만
```

> 팰월드 VM과 봇 VM의 **리전이 달라도** 정상 동작합니다 — VM 제어는 글로벌 API고,
> default VPC는 글로벌 네트워크라 내부 IP REST 통신도 리전을 넘어 허용됩니다.
```
```

---

## 4. 1단계 · 팰월드 서버 VM 만들기

### 4-1. VM 생성 (콘솔 또는 gcloud)

콘솔: Compute Engine → VM 인스턴스 → 인스턴스 만들기
- 이름: `palworld-server`
- 리전/존: `asia-northeast3`(서울) / `asia-northeast3-a` — 한국에서 핑이 낮아야 하므로 서울 필수
- 머신 유형: `e2-standard-4` (4 vCPU / 16GB) — 인원 적으면 `e2-highmem-2`(2vCPU/16GB)도 가능
- 부팅 디스크: **Ubuntu 22.04 LTS**, 크기 30GB 이상 (SSD 권장)
- 방화벽: 아래에서 UDP 포트 별도 개방

gcloud 예시:
```bash
gcloud compute instances create palworld-server \
  --zone=asia-northeast3-a \
  --machine-type=e2-standard-4 \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB \
  --boot-disk-type=pd-ssd \
  --tags=palworld-server
```

### 4-2. 방화벽 규칙 (팰월드 기본 포트 UDP 8211)

```bash
gcloud compute firewall-rules create palworld-udp \
  --allow=udp:8211 \
  --target-tags=palworld-server \
  --description="Palworld game port"
```

> 콘솔에서 할 경우: VPC 네트워크 → 방화벽 → 규칙 만들기 → 대상 태그 `palworld-server`, 프로토콜/포트 `udp:8211`, 소스 `0.0.0.0/0`.

### 4-3. 팰월드 서버 설치 (VM에 SSH 접속 후)

```bash
# 32비트 라이브러리 + SteamCMD 준비
sudo dpkg --add-architecture i386
sudo apt update && sudo apt install -y software-properties-common
sudo add-apt-repository -y multiverse
sudo apt update
echo steam steam/question select "I AGREE" | sudo debconf-set-selections
echo steam steam/license note '' | sudo debconf-set-selections
sudo apt install -y steamcmd

# 전용 유저 생성 후 설치
sudo useradd -m -s /bin/bash palworld || true
sudo -u palworld bash -c '
  /usr/games/steamcmd +force_install_dir /home/palworld/server \
    +login anonymous +app_update 2394010 validate +quit
'
```

### 4-4. systemd 서비스 등록 (부팅 시 자동 실행)

`/etc/systemd/system/palworld.service` 파일 생성:
```ini
[Unit]
Description=Palworld Dedicated Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=palworld
WorkingDirectory=/home/palworld/server
ExecStartPre=/usr/games/steamcmd +force_install_dir /home/palworld/server +login anonymous +app_update 2394010 validate +quit
ExecStart=/home/palworld/server/PalServer.sh -useperfthreads -NoAsyncLoadingThread -UseMultithreadForDS
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

활성화:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now palworld
sudo systemctl status palworld
```

> **핵심**: `enable`을 해두면 봇이 VM을 켤 때(`start`) systemd가 팰월드 서버를 자동으로 실행합니다.
> 즉, 봇은 "VM 전원"만 제어하고 게임 서버 실행은 VM 스스로 처리합니다.

### 4-5. 서버 설정 + REST API 활성화

접속 인원/비밀번호, 그리고 **접속자 조회·준비 알림에 필요한 REST API**를 아래 파일에서 설정:
```
/home/palworld/server/Pal/Saved/Config/LinuxServer/PalWorldSettings.ini
```
(서버 최초 1회 실행 후 생성됩니다. 편집 전 서버를 잠시 끄고 하세요.)

`OptionSettings=(...)` 괄호 안에서 다음 값을 설정:
```ini
RESTAPIEnabled=True,
RESTAPIPort=8212,
AdminPassword="여기에_강력한_비밀번호",
```
- `AdminPassword`가 REST API의 인증 비밀번호가 됩니다 → 봇 `.env`의 `PALWORLD_ADMIN_PASSWORD`에 동일하게 입력.
- REST 포트(8212)는 **외부 방화벽을 열 필요 없음** — 봇 VM이 같은 VPC 내부 IP로만 접근합니다
  (GCP 기본 네트워크의 `default-allow-internal` 규칙이 내부 통신을 허용).
  커스텀 VPC를 쓴다면 봇 VM → 팰월드 VM `tcp:8212` 내부 허용 규칙을 추가하세요.
- 설정 후 서버 재시작: `sudo systemctl restart palworld`

### 4-6. VM 이름·존 메모

봇 설정에 쓸 값을 적어둡니다:
```
PALWORLD_INSTANCE = palworld-server
PALWORLD_ZONE     = asia-northeast3-a
GCP_PROJECT       = palworld-bot-123456
```

---

## 5. 2단계 · 봇 VM + 서비스 계정 + IAM

### 5-1. 봇 전용 서비스 계정 생성

```bash
gcloud iam service-accounts create palworld-bot-sa \
  --display-name="Palworld Discord Bot"
```

### 5-2. 최소 권한 부여 (start/stop/get 만)

`roles/compute.instanceAdmin.v1`은 넓으니, **커스텀 역할**로 딱 필요한 권한만 부여하는 것을 권장:

```bash
# 커스텀 역할 정의
gcloud iam roles create palworldBotControl \
  --project=palworld-bot-123456 \
  --title="Palworld Bot VM Control" \
  --permissions=compute.instances.start,compute.instances.stop,compute.instances.get,compute.instances.list

# 서비스 계정에 역할 부여
gcloud projects add-iam-policy-binding palworld-bot-123456 \
  --member="serviceAccount:palworld-bot-sa@palworld-bot-123456.iam.gserviceaccount.com" \
  --role="projects/palworld-bot-123456/roles/palworldBotControl"
```

> 간단히 가려면 `--role="roles/compute.instanceAdmin.v1"`을 써도 되지만 권한이 넓어집니다.

### 5-3. 봇 VM 생성 (서비스 계정 "연결")

```bash
gcloud compute instances create palworld-bot \
  --zone=us-central1-a \
  --machine-type=e2-micro \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=10GB \
  --service-account=palworld-bot-sa@palworld-bot-123456.iam.gserviceaccount.com \
  --scopes=https://www.googleapis.com/auth/cloud-platform
```

> `--service-account` + `--scopes`로 계정을 VM에 붙였기 때문에 **JSON 키 파일이 필요 없습니다.**
> 봇 코드는 `google.auth.default()`로 이 계정을 자동 인식합니다.

> 무료 티어 조건: `e2-micro` 1대, 리전 us-west1/us-central1/us-east1, 표준 디스크 30GB 이하.

---

## 6. 3단계 · Discord 애플리케이션 등록

1. https://discord.com/developers/applications → **New Application**
2. 좌측 **Bot** 탭 → **Add Bot** → **Reset Token**으로 토큰 발급 (이 토큰이 `DISCORD_TOKEN`)
   - ⚠️ 토큰은 비밀번호입니다. 절대 깃에 커밋하지 마세요.
3. **Privileged Gateway Intents**: 이 봇은 메시지 내용이 필요 없으므로 **Message Content Intent는 꺼도 됨** (슬래시 명령만 사용).
4. 좌측 **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Use Slash Commands` 정도면 충분
   - 생성된 URL로 봇을 내 서버에 초대
5. **서버 ID(길드 ID)** 확보: Discord에서 개발자 모드 켠 뒤 서버 우클릭 → ID 복사 (`GUILD_ID` — 슬래시 명령 즉시 등록용)

메모해둘 값:
```
DISCORD_TOKEN = (봇 토큰)
GUILD_ID      = (내 서버 ID)
```

---

## 7. 4단계 · 봇 배포 및 실행

> 봇 코드(`bot.py` 등)는 다음 단계에서 이 저장소에 생성합니다.
> 아래는 봇 VM에 올린 뒤의 실행 흐름 예고입니다.

봇 VM에 SSH 접속 후:
```bash
sudo apt update && sudo apt install -y python3-venv git
git clone <이 저장소 URL> palworld-bot && cd palworld-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 환경변수 설정 (.env)
cp .env.example .env
nano .env   # DISCORD_TOKEN, GUILD_ID, GCP_PROJECT, PALWORLD_INSTANCE, PALWORLD_ZONE 입력

# 실행
python main.py
```

24시간 상주는 systemd로:
```ini
# /etc/systemd/system/palworld-bot.service
[Unit]
Description=Palworld Discord Bot
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/<user>/palworld-bot
ExecStart=/home/<user>/palworld-bot/.venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now palworld-bot
```

---

## 8. 봇 명령어

| 명령 | 설명 |
|---|---|
| `/start` | 팰월드 VM을 켭니다. 준비되면 알림 채널로 접속 주소를 자동 안내 |
| `/stop` | 월드를 저장한 뒤 팰월드 VM을 끕니다 (비용 절약) |
| `/status` | VM 실행 상태(RUNNING/TERMINATED 등) + 접속 주소 확인 |
| `/ip` | 현재 접속용 외부 IP 표시 |
| `/players` | 현재 접속 중인 플레이어 목록/인원 (REST API 필요) |
| `/update` | 월드 저장 → 서버 재시작으로 팰월드 최신 버전 적용 (켤 때마다 자동 업데이트되므로, 켜진 채로 업데이트가 나왔을 때만 사용) |
| `/announce <내용>` | 게임 안으로 전체 공지 전송 (REST API 필요) |
| `/stop-in <분>` | N분 뒤 예약 종료 (1분 전 게임 내 경고). `0`이면 취소 |
| `/backup` | 월드 저장 + 서버 디스크 스냅샷 백업 (스냅샷 IAM 권한 필요, 아래 참고) |

**자동 기능 (감시 루프, 60초 주기)**
- **유휴 자동 종료**: 접속자 0명이 `IDLE_STOP_MINUTES`(기본 60분) 지속되면 5분 전 게임 내 경고 후 저장·종료. `0`이면 비활성
- **접속/퇴장 알림**: 누가 들어오고 나가면 `NOTIFY_CHANNEL_ID` 채널에 알림
- **봇 상태 표시**: 봇 프로필에 "🟢 3명 접속 중이노" / "💤 서버 꺼져있노" 실시간 표시

**`/backup`용 IAM 권한 추가** (스냅샷 생성 권한, 1회):
```bash
gcloud iam roles update palworldBotControl --project=<프로젝트ID> \
  --add-permissions=compute.disks.createSnapshot,compute.snapshots.create,compute.snapshots.get
```

- **권한 제한**: `.env`의 `CONTROL_ROLE`을 지정하면 해당 역할 보유자만 `/start` `/stop` 가능(비우면 전체 허용).
- **준비 완료 알림**: `/start` 후 봇이 REST API가 응답할 때까지 백그라운드로 폴링하다가, 게임 서버가 실제 접속 가능해지면
  `NOTIFY_CHANNEL_ID` 채널(미설정 시 명령 실행 채널)로 알립니다. REST API(`PALWORLD_ADMIN_PASSWORD`) 미설정 시 이 기능은 자동 비활성화.
- **끄기 전 저장(중요)**: `/stop`은 VM을 끄기 **직전에** REST API `POST /v1/api/save`로 월드를 즉시 저장합니다(성공 시 "월드 저장 완료 ✅" 표시).
  - REST API가 설정돼 있지 않으면 이 명시적 저장은 생략되고, **팰월드의 주기적 오토세이브**와 VM 종료 시 graceful 처리에만 의존합니다(최근 진행 유실 가능).
  - 안전을 위해 REST API 설정을 권장하며, 오토세이브 주기는 `PalWorldSettings.ini`의 `AutoSaveSpan`으로 조정할 수 있습니다.
  - 서버를 켤 때(`/start`)는 마지막 저장 데이터를 그대로 불러오므로 별도 저장이 필요 없습니다.

---

## 9. 트러블슈팅

| 증상 | 원인/해결 |
|---|---|
| 슬래시 명령이 안 뜸 | `GUILD_ID`로 길드 동기화했는지 확인. 글로벌 동기화는 최대 1시간 지연 |
| 봇이 VM 제어 실패 (403) | 서비스 계정 IAM 역할 확인, 봇 VM `--scopes=cloud-platform` 확인 |
| 팰월드 접속 안 됨 | 방화벽 `udp:8211` 규칙, VM 실행 상태, 게임 클라이언트에서 `IP:8211`로 직접 접속 시도 |
| VM 켰는데 게임 서버 안 뜸 | `sudo systemctl status palworld` 로그 확인, `enable` 되었는지 확인 |
| 메모리 부족으로 서버 크래시 | 머신 유형을 RAM 16GB급으로 상향, 스왑 추가 |
| `/players`가 안 됨 | `RESTAPIEnabled=True`, `PALWORLD_ADMIN_PASSWORD` 일치, 봇→팰월드 내부 `tcp:8212` 도달 확인. 서버 로딩 직후엔 잠시 응답 안 할 수 있음 |
| 준비 알림이 안 옴 | REST API 설정 확인. 봇이 채널에 메시지 보낼 권한 있는지, `NOTIFY_CHANNEL_ID`가 올바른지 확인 |

---

## 10. CI/CD

### CI (자동 검증)
`.github/workflows/ci.yml` — 모든 push/PR에서 **의존성 설치 → 컴파일 → `tests/verify_bot.py`** 를 Python 3.10·3.12로 실행합니다. 깨진 코드가 main에 들어오는 것을 막아줍니다. 별도 설정 불필요.

### CD (Pull 방식 자동 배포)
봇 VM이 **주기적으로 `main`을 확인**해서 새 커밋이 있으면 스스로 pull → 의존성 설치 → 검증 → 재시작합니다. GitHub Secrets·인바운드 포트가 필요 없어 안전합니다. (반영은 최대 ~3분 지연)

**흐름**: `git fetch` → `origin/main` 변경 감지 시 `reset --hard` → `pip install` → `verify_bot.py` **통과 시에만** `systemctl restart` (실패하면 기존 봇 유지).

**봇 VM에서 1회 설정** (clone·유저 경로에 맞게 수정):
```bash
# 1) deploy 유닛 설치
sudo cp deploy/palworld-deploy.service deploy/palworld-deploy.timer /etc/systemd/system/

# 2) 배포 스크립트가 봇만 재시작하도록 sudo 허용 (비밀번호 없이)
echo 'ubuntu ALL=(root) NOPASSWD: /usr/bin/systemctl restart palworld-bot' \
  | sudo tee /etc/sudoers.d/palworld-deploy

# 3) 타이머 활성화
sudo systemctl daemon-reload
sudo systemctl enable --now palworld-deploy.timer

# 확인
systemctl list-timers palworld-deploy.timer
journalctl -u palworld-deploy.service -f
```

> - 봇 VM은 `main` 브랜치를 clone 해두세요 (`git clone -b main ...`). CD는 `main`만 배포합니다.
> - **공개 저장소면** VM에서 인증 없이 pull 됩니다. **비공개면** 읽기 전용 deploy key를 VM에 등록하세요.
> - 개발은 `develop`에서 하고, 검증 끝나면 `main`으로 PR/머지 → VM이 자동 반영.

---

## 프로젝트 구조

```
palworld-bot/
├── main.py                     # 실행 진입점 (python main.py)
├── palbot/                     # 봇 패키지
│   ├── bot.py                  # 봇 구성 + 실행 (PalworldBot, main)
│   ├── config.py               # .env 로딩/검증 (Settings)
│   ├── notifications.py        # 채널 알림 + 준비 완료 폴링
│   ├── services/               # 외부 연동
│   │   ├── gcp.py              #   VM 제어 (start/stop/status/IP)
│   │   └── palworld_api.py     #   팰월드 REST API (접속자/저장/준비)
│   ├── cogs/                   # 슬래시 명령
│   │   ├── control.py          #   /start /stop /status /ip
│   │   └── players.py          #   /players
│   └── ui/
│       └── embeds.py           # 메시지 디자인 + 말투 (한곳에서 관리)
├── tests/
│   └── verify_bot.py           # 오프라인 검증 (GCP/Discord 없이 구조·로직 확인)
├── .github/workflows/ci.yml    # CI (push/PR 자동 검증)
├── deploy/                     # systemd 유닛 + 설치/배포 스크립트
│   ├── palworld.service        #   팰월드 VM
│   ├── palworld-bot.service    #   봇 상주
│   ├── palworld-vm-setup.sh    #   팰월드 VM 설치
│   ├── deploy.sh               #   Pull 방식 자동 배포 스크립트
│   ├── palworld-deploy.service #   배포 실행(oneshot)
│   └── palworld-deploy.timer   #   배포 주기 실행(3분)
├── requirements.txt
├── README.md                   # 전체 가이드
└── GCP-SETUP.md                # GCP 세팅 전용 가이드
```

- **메시지 디자인·말투 수정**은 `palbot/ui/embeds.py` 한 파일만 고치면 됩니다.
- **명령 추가**는 `palbot/cogs/`에 새 파일을 만들고 `palbot/bot.py`의 `INITIAL_COGS`에 등록.
- **배포 전 검증**은 `python tests/verify_bot.py` 로 언제든 가능합니다.
