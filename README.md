# 팰월드 서버 Discord 제어 봇

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
REGION     = us-central1
ZONE       = us-central1-a
```

---

## 4. 1단계 · 팰월드 서버 VM 만들기

### 4-1. VM 생성 (콘솔 또는 gcloud)

콘솔: Compute Engine → VM 인스턴스 → 인스턴스 만들기
- 이름: `palworld-server`
- 리전/존: `us-central1` / `us-central1-a`
- 머신 유형: `e2-standard-4` (4 vCPU / 16GB) — 인원 적으면 `e2-highmem-2`(2vCPU/16GB)도 가능
- 부팅 디스크: **Ubuntu 22.04 LTS**, 크기 30GB 이상 (SSD 권장)
- 방화벽: 아래에서 UDP 포트 별도 개방

gcloud 예시:
```bash
gcloud compute instances create palworld-server \
  --zone=us-central1-a \
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

### 4-5. 서버 설정 (선택)

접속 인원/비밀번호 등은 아래 파일에서 조정:
```
/home/palworld/server/Pal/Saved/Config/LinuxServer/PalWorldSettings.ini
```
(서버 최초 1회 실행 후 생성됩니다.)

### 4-6. VM 이름·존 메모

봇 설정에 쓸 값을 적어둡니다:
```
PALWORLD_INSTANCE = palworld-server
PALWORLD_ZONE     = us-central1-a
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
python bot.py
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
ExecStart=/home/<user>/palworld-bot/.venv/bin/python bot.py
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

## 8. 봇 명령어 (예정)

| 명령 | 설명 |
|---|---|
| `/start` | 팰월드 VM을 켭니다 (부팅 후 systemd가 게임 서버 자동 실행), 서버 IP 표시 |
| `/stop` | 팰월드 VM을 끕니다 (비용 절약) |
| `/status` | VM 실행 상태(RUNNING/TERMINATED 등) 확인 |

권한 제한(특정 역할만 켜고 끄기)도 봇 코드 단계에서 추가할 예정입니다.

---

## 9. 트러블슈팅

| 증상 | 원인/해결 |
|---|---|
| 슬래시 명령이 안 뜸 | `GUILD_ID`로 길드 동기화했는지 확인. 글로벌 동기화는 최대 1시간 지연 |
| 봇이 VM 제어 실패 (403) | 서비스 계정 IAM 역할 확인, 봇 VM `--scopes=cloud-platform` 확인 |
| 팰월드 접속 안 됨 | 방화벽 `udp:8211` 규칙, VM 실행 상태, 게임 클라이언트에서 `IP:8211`로 직접 접속 시도 |
| VM 켰는데 게임 서버 안 뜸 | `sudo systemctl status palworld` 로그 확인, `enable` 되었는지 확인 |
| 메모리 부족으로 서버 크래시 | 머신 유형을 RAM 16GB급으로 상향, 스왑 추가 |

---

## 다음 단계

이 문서 확인 후, 다음을 만들면 됩니다:
1. `bot.py` — discord.py 봇 + GCP 제어 로직
2. `requirements.txt` — `discord.py`, `google-cloud-compute`
3. `.env.example` — 환경변수 템플릿
4. `.gitignore` — `.env`, `.venv` 등 제외
5. 팰월드/봇 VM용 systemd 유닛 파일

> 준비되면 "봇 코드 만들어줘"라고 말해주세요.
