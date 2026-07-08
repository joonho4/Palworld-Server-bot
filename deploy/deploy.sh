#!/usr/bin/env bash
# 봇 VM 자동 배포 (Pull 방식)
# origin/main 에 새 커밋이 있으면: pull → 의존성 설치 → 검증 → 봇 재시작.
# 검증(verify_bot.py)이 실패하면 재시작하지 않고 기존 봇을 유지한다.
#
# palworld-deploy.timer 가 주기적으로 실행하며, 봇을 clone 한 유저로 동작한다.
set -euo pipefail

REPO="${PALBOT_DIR:-$HOME/palworld-bot}"
BRANCH="main"
SERVICE="palworld-bot"

cd "$REPO"

git fetch --quiet origin "$BRANCH"
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ]; then
  exit 0    # 변경 없음 → 조용히 종료
fi

echo "[deploy] 업데이트 감지: ${LOCAL:0:7} -> ${REMOTE:0:7}"
git checkout --quiet "$BRANCH"
git reset --hard --quiet "origin/$BRANCH"   # 추적 파일만 갱신 (.env 등 untracked 는 보존)

./.venv/bin/pip install -q -r requirements.txt

# 안전장치: 검증 실패 시 재시작하지 않음
if ! ./.venv/bin/python tests/verify_bot.py > /tmp/palbot-verify.log 2>&1; then
  echo "[deploy] 검증 실패 — 재시작 취소. /tmp/palbot-verify.log 확인" >&2
  exit 1
fi

sudo systemctl restart "$SERVICE"
echo "[deploy] 재시작 완료 (${REMOTE:0:7})"
