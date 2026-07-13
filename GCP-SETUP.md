# GCP 세팅 가이드 (팰월드 봇)

이 문서는 **GCP를 처음부터** 세팅해서 봇을 무료로 배포하는 전 과정을 순서대로 정리합니다.
전체 개념은 [README.md](README.md)에, 여기서는 **복붙 가능한 명령 중심**으로 다룹니다.

> 💡 **명령은 [Cloud Shell](https://console.cloud.google.com)에서 실행하세요.** 우측 상단 `>_` 아이콘을 누르면
> gcloud가 이미 설치·인증된 터미널이 브라우저에 열립니다. 로컬에 아무것도 안 깔아도 됩니다.

---

## 0. 비용 요약 (무료로 시작 가능)

| 항목 | 비용 |
|---|---|
| 계정·프로젝트 생성 | 무료 |
| 신규 가입 크레딧 | $300 / 90일 |
| 봇 VM (`e2-micro`, 미국 리전) | 항상 무료 티어 → **$0** |
| 팰월드 VM | **켜져 있을 때만** 과금 (봇으로 꺼서 절약) |

봇 자체는 계속 $0. 돈은 "팰월드 서버가 실제 켜져 있는 시간"에만 듭니다.

---

## 1. 프로젝트 생성 + 결제 연결

1. https://console.cloud.google.com 접속 → Google 로그인
2. **무료로 시작(Start free)** → 결제 정보(카드) 등록 → $300 크레딧 활성화
   - 카드는 신원 확인용이며, 직접 업그레이드하지 않는 한 자동 청구되지 않습니다.
3. 상단 프로젝트 드롭다운 → **새 프로젝트** → 이름 `palworld-bot` → 만들기
4. 생성된 **프로젝트 ID**를 확인 (예: `palworld-bot-481203`)

Cloud Shell을 열고 프로젝트를 기본값으로 지정 (이후 명령에서 `--project` 생략 가능):
```bash
gcloud config set project <프로젝트ID>
```

이 가이드 전체에서 쓸 변수를 미리 설정하면 편합니다:
```bash
export PROJECT=<프로젝트ID>
# 팰월드 VM은 핑 때문에 서울, 봇 VM은 무료 티어 때문에 미국 (리전 분리!)
export GAME_ZONE=asia-northeast3-a   # 서울 — 한국에서 핑 ~5-20ms
export BOT_ZONE=us-central1-a        # 무료 e2-micro: us-west1 / us-central1 / us-east1 만 해당
```

> **왜 리전을 나누나?** 게임 서버는 핑이 중요해서 서울(`asia-northeast3`),
> 봇은 핑이 무관하고 무료 e2-micro가 미국 리전에만 있어서 `us-central1`.
> 리전이 달라도 VM 제어(글로벌 API)와 내부 IP REST 통신(default VPC는 글로벌)이 모두 정상 동작합니다.

---

## 2. 필요한 API 사용 설정

```bash
gcloud services enable compute.googleapis.com --project=$PROJECT
```
(콘솔에서 Compute Engine 메뉴를 처음 열면 자동으로 켜지기도 합니다. 몇 분 걸릴 수 있어요.)

---

## 3. 팰월드 서버 VM 생성

> 팰월드는 RAM 16GB급이 필요해 무료 티어가 아닙니다. **필요할 때만 켜서** 비용을 아낍니다.

```bash
# VM 생성 (서울 리전 — 한국에서 낮은 핑)
gcloud compute instances create palworld-server \
  --project=$PROJECT --zone=$GAME_ZONE \
  --machine-type=e2-standard-4 \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB --boot-disk-type=pd-ssd \
  --tags=palworld-server

# 게임 포트(UDP 8211) 방화벽 개방
gcloud compute firewall-rules create palworld-udp \
  --project=$PROJECT --allow=udp:8211 --target-tags=palworld-server
```

### 서버 설치
```bash
gcloud compute ssh palworld-server --project=$PROJECT --zone=$GAME_ZONE
```
접속되면 VM 안에서 [deploy/palworld-vm-setup.sh](deploy/palworld-vm-setup.sh)의 내용을 실행합니다
(SteamCMD 설치 → 서버 다운로드 → systemd 등록). 자세한 단계는 README §4-3, §4-4 참고.

### REST API 켜기 (접속자 조회·저장·알림용)
서버 1회 실행 후 생성되는 설정 파일을 편집:
```
/home/palworld/server/Pal/Saved/Config/LinuxServer/PalWorldSettings.ini
```
`OptionSettings=(...)` 안에:
```ini
RESTAPIEnabled=True,
RESTAPIPort=8212,
AdminPassword="강력한_비밀번호",
```
- 이 `AdminPassword` → 나중에 봇 `.env`의 `PALWORLD_ADMIN_PASSWORD`에 동일 입력
- REST 포트(8212)는 외부 개방 불필요 (봇이 같은 VPC 내부 IP로 접근)
- 편집 후: `sudo systemctl restart palworld`

---

## 4. 봇용 서비스 계정 + 최소 권한

```bash
# 서비스 계정 생성
gcloud iam service-accounts create palworld-bot-sa \
  --project=$PROJECT --display-name="Palworld Discord Bot"

# 딱 필요한 권한만 담은 커스텀 역할
gcloud iam roles create palworldBotControl --project=$PROJECT \
  --title="Palworld Bot VM Control" \
  --permissions=compute.instances.start,compute.instances.stop,compute.instances.get,compute.instances.list

# 서비스 계정에 역할 부여
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:palworld-bot-sa@$PROJECT.iam.gserviceaccount.com" \
  --role="projects/$PROJECT/roles/palworldBotControl"
```

> 이렇게 하면 이 계정은 **팰월드 VM을 켜고/끄고/조회**만 할 수 있고 그 외엔 아무것도 못 합니다.

---

## 5. 봇 VM 생성 (무료 e2-micro, 서비스 계정 연결)

```bash
gcloud compute instances create palworld-bot \
  --project=$PROJECT --zone=$BOT_ZONE \
  --machine-type=e2-micro \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud \
  --boot-disk-size=10GB \
  --service-account=palworld-bot-sa@$PROJECT.iam.gserviceaccount.com \
  --scopes=https://www.googleapis.com/auth/cloud-platform
```

> `--service-account`로 계정을 VM에 **연결(attach)** 했기 때문에 JSON 키 파일이 필요 없습니다.
> 봇 코드는 이 계정을 자동 인식(ADC)합니다.

---

## 6. 봇 코드 배포

```bash
gcloud compute ssh palworld-bot --project=$PROJECT --zone=$BOT_ZONE
```
VM 안에서:
```bash
sudo apt update && sudo apt install -y python3-venv git
git clone https://github.com/joonho4/Palworld-Server-bot.git palworld-bot
cd palworld-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env      # 아래 값 채우기
```

`.env` 채울 값:
```
DISCORD_TOKEN=봇토큰
GUILD_ID=772087456610254850
CONTROL_ROLE=
NOTIFY_CHANNEL_ID=
GCP_PROJECT=<프로젝트ID>
PALWORLD_INSTANCE=palworld-server
PALWORLD_ZONE=asia-northeast3-a
PALWORLD_ADMIN_PASSWORD=아까_ini에_넣은_값
PALWORLD_REST_HOST=
PALWORLD_REST_PORT=8212
```

---

## 7. 봇 24시간 상주 (systemd)

```bash
sudo cp deploy/palworld-bot.service /etc/systemd/system/
# 필요 시 유닛의 User/WorkingDirectory 경로를 실제 clone 위치로 수정
sudo systemctl daemon-reload
sudo systemctl enable --now palworld-bot
journalctl -u palworld-bot -f      # "로그인 완료" 로그 확인
```

---

## 8. 배포 검증 체크리스트

- [ ] Discord에서 봇이 온라인으로 보임
- [ ] `/status` → VM 상태 임베드가 뜸 (GCP 연동 OK)
- [ ] `/start` → 1~3분 뒤 준비 완료 알림, `/ip`로 주소 확인
- [ ] `/stop` → "월드 저장 완료" 표시 후 정지
- [ ] `/players` → (REST API 설정 시) 접속자 목록

봇 코드 자체가 정상인지는 배포 전에도 로컬에서 확인 가능:
```bash
python tests/verify_bot.py      # GCP/Discord 없이 구조·임베드·로직 검증
```

---

## 9. 자주 겪는 문제

| 증상 | 해결 |
|---|---|
| 봇이 VM 제어 실패 (403) | 4단계 IAM 역할 부여 확인, 봇 VM `--scopes=cloud-platform` 확인 |
| `DefaultCredentialsError` | 봇 VM에 서비스 계정이 연결됐는지 확인 (5단계) |
| 슬래시 명령이 안 보임 | 봇 초대 시 `applications.commands` 스코프 포함, `.env`의 `GUILD_ID` 확인 |
| `/players` 안 됨 | `RESTAPIEnabled=True`, `AdminPassword` 일치, 서버 로딩 완료 여부 |
| 팰월드 접속 불가 | 방화벽 `udp:8211`, VM RUNNING 상태, 클라이언트에서 `IP:8211` 직접 접속 |

---

## 비용 절약 팁

- 안 쓸 땐 `/stop` 습관화 → 팰월드 VM 컴퓨팅 비용 0.
- 팰월드 VM에 고정 IP를 붙이면 꺼져 있어도 소액 과금되니, 초기엔 기본(임시 IP)으로 두고 `/ip`로 확인.
- 더 절약하려면 팰월드 VM을 Spot 인스턴스로 (단, 갑자기 종료될 수 있음).
