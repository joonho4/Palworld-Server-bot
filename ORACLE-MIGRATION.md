# 오라클 클라우드 이주 가이드 (무료 24시간 서버)

GCP 팰월드 서버를 **오라클 Always Free ARM VM**(4 OCPU / 24GB, 월 0원)으로 옮기는 절차입니다.
봇 VM은 GCP 무료 e2-micro에 그대로 둡니다 (크레딧과 무관한 영구 무료).

> ⚠️ 팰월드 서버는 x86 전용이라 ARM에서는 **box86/box64 에뮬레이션**으로 돌립니다.
> 소규모(2~5인)는 커뮤니티에서 검증됐지만, 대형 패치 직후 며칠 불안정할 수 있어요.
> **GCP 서버는 검증 끝날 때까지 지우지 마세요** (플랜 B).

---

## 1. 오라클 계정 + PAYG 전환

1. https://www.oracle.com/kr/cloud/free/ 가입 (카드는 본인확인용)
2. **홈 리전: 춘천(ap-chuncheon-1) 추천** — 서울보다 ARM 재고가 잘 잡히고 핑 차이는 무의미. ⚠️ 홈 리전은 나중에 못 바꿈
3. 가입 후 **PAYG(Pay As You Go) 전환** (콘솔 → Billing → Upgrade):
   - Always Free 자원은 전환 후에도 **계속 무료**
   - ARM 재고 우선 배정 + 유휴 인스턴스 회수 안 함
4. 과금 사고 방지: 콘솔 → Budgets → **월 $1 예산 알림** 설정

## 2. ARM VM 생성

Compute → Instances → Create Instance:
- Shape: **Ampere → VM.Standard.A1.Flex → 4 OCPU / 24GB** (이게 무료 한도 최대)
- Image: **Ubuntu 22.04 (aarch64)**
- Boot volume: 100GB 이하 (무료 한도 총 200GB)
- SSH 키 저장 필수

"Out of capacity" 뜨면 시간대 바꿔 재시도 (PAYG면 보통 금방 잡힘).

## 3. OCI 네트워크 개방 (보안 목록)

VCN → 해당 서브넷의 Security List → Ingress Rules 추가:

| 소스 | 프로토콜 | 포트 | 용도 |
|---|---|---|---|
| `0.0.0.0/0` | UDP | 8211 | 게임 접속 |
| `<봇VM외부IP>/32` | TCP | 8212 | 봇 REST API (봇 IP만!) |

> ⚠️ OCI 보안 목록 + **VM 내부 iptables** 둘 다 열어야 합니다. iptables는 설치 스크립트가 처리해요.

## 4. 팰월드 설치

VM에 SSH 접속 후:
```bash
# 이 저장소의 스크립트 받기
wget https://raw.githubusercontent.com/joonho4/Palworld-Server-bot/main/deploy/oracle-arm-setup.sh
sudo bash oracle-arm-setup.sh          # box86/64 + steamcmd + 팰월드 + systemd + iptables

# 서버 1회 실행 확인 후 REST API 설정
sudo bash oracle-arm-setup.sh rest <관리자비밀번호>
```

## 5. 세이브 이사 (GCP → 오라클)

**GCP Cloud Shell에서:**
```bash
# GCP 서버에서 세이브 압축
gcloud compute ssh palworld-server --zone=asia-northeast3-a \
  --command="sudo tar czf /tmp/palworld-save.tar.gz -C /home/palworld/server/Pal Saved && sudo chmod 644 /tmp/palworld-save.tar.gz"

# Cloud Shell 로 다운로드
gcloud compute scp palworld-server:/tmp/palworld-save.tar.gz . --zone=asia-northeast3-a

# 오라클 VM 으로 전송 (SSH 키 필요 — 콘솔에서 받은 키를 Cloud Shell 에 업로드)
scp -i <오라클키> palworld-save.tar.gz ubuntu@<오라클IP>:/tmp/
```

**오라클 VM에서:**
```bash
sudo systemctl stop palworld
sudo tar xzf /tmp/palworld-save.tar.gz -C /home/palworld/server/Pal
sudo chown -R palworld:palworld /home/palworld/server/Pal/Saved
sudo systemctl start palworld
```
게임에서 접속해 캐릭터/월드가 그대로인지 확인하세요.

## 6. 봇 연결 전환 (봇 VM에서)

`.env` 수정:
```bash
nano ~/Palworld-Server-bot/.env
```
```
# 상시 가동 모드로 전환
VM_PROVIDER=none
PALWORLD_PUBLIC_IP=<오라클_공인IP>
PALWORLD_REST_HOST=<오라클_공인IP>
PALWORLD_ADMIN_PASSWORD=<4단계에서_설정한_비밀번호>
IDLE_STOP_MINUTES=0
```
```bash
sudo systemctl restart palworld-bot
```

상시 가동 모드에서 봇 동작:
- `/status` `/ip` `/players` `/announce` + 접속/퇴장 알림 + 상태 표시 → **그대로 동작**
- `/start` → "♾️ 24시간 켜져있노" + 접속 주소 안내
- `/stop` `/update` `/backup` `/stop-in` → 상시 가동이라 불필요하다고 안내
- 유휴 자동 종료 → 자동 비활성 (공짜니까)

## 7. 검증 후 GCP 정리 (2주 뒤)

오라클이 안정적이면:
```bash
# 만약을 위한 최종 스냅샷
gcloud compute disks snapshot palworld-server --zone=asia-northeast3-a \
  --snapshot-names=palworld-final-backup

# 팰월드 VM 삭제 (봇 VM 은 남김!)
gcloud compute instances delete palworld-server --zone=asia-northeast3-a
```

완성: **팰월드(오라클 무료) + 봇(GCP 무료) = 월 0원** 🎉

---

## 트러블슈팅

| 증상 | 해결 |
|---|---|
| A1 "Out of capacity" | PAYG 전환 확인, 시간대 바꿔 재시도, OCPU 줄여서(2개) 시도 후 나중에 리사이즈 |
| 게임 접속 안 됨 | OCI 보안 목록 **그리고** VM iptables 둘 다 확인 (`sudo iptables -L INPUT -n \| head`) |
| 서버 시작이 매우 느림 | 에뮬레이션 특성상 첫 부팅 5~10분 정상. `journalctl -u palworld -f` 로 진행 확인 |
| 대형 패치 후 크래시 | box64 업데이트: `sudo apt update && sudo apt install --only-upgrade box64-arm64` 후 재시작 |
| 봇 /players 타임아웃 | 보안 목록 TCP 8212 소스가 봇 VM IP 인지, REST 설정(4단계) 했는지 확인 |
