#!/usr/bin/env bash
# 배포용 키 생성 — ★**키는 화면에도 로그에도 찍지 않는다.** 주소만 보여 준다.
#
# 왜 이렇게 만드나
#   개인키가 터미널에 한 번이라도 찍히면 그 키는 **셸 히스토리·스크롤백·세션 기록**에 남는다.
#   AI 세션이나 CI 로그를 거치면 더 그렇다. ***찍힌 키는 그 순간 오염된 것으로 취급한다.***
#   그래서 이 스크립트는 키를 **`.env` 파일로 바로 흘려보내고** 출력은 **주소만** 한다.
#
# 쓰는 법
#   bash scripts/new-deployer-key.sh            # .env 에 DEPLOYER_PRIVATE_KEY 를 만든다
#   bash scripts/new-deployer-key.sh --anchor   # DRAW_ANCHOR_PRIVATE_KEY 를 만든다(권한 분리용)
#
# ★배포키와 앵커키를 **나눠라**. 배포키는 컨트랙트 owner 라 운영자 목록을 바꿀 수 있고,
#   앵커키는 공약·공개만 올린다. 앵커키가 새도 **owner 는 무사**하다.
set -euo pipefail

VAR="DEPLOYER_PRIVATE_KEY"
[ "${1:-}" = "--anchor" ] && VAR="DRAW_ANCHOR_PRIVATE_KEY"

cd "$(dirname "$0")/.."
ENV_FILE=".env"

if [ ! -x node_modules/.bin/hardhat ]; then
  echo "★node_modules 가 없습니다. 먼저: npm install" >&2
  exit 1
fi

if [ -f "$ENV_FILE" ] && grep -q "^${VAR}=" "$ENV_FILE"; then
  echo "★${VAR} 가 이미 .env 에 있습니다 — 덮어쓰지 않습니다." >&2
  echo "  바꾸려면 그 줄을 직접 지우고 다시 실행하십시오(기존 키로 배포한 컨트랙트가 있다면" >&2
  echo "  그 owner 권한을 잃습니다)." >&2
  exit 2
fi

# ★키 생성과 주소 파생을 **한 프로세스 안에서** 끝낸다 — 중간에 파이프로 흘리지 않는다.
ADDR=$(node -e '
const { Wallet } = require("ethers");
const fs = require("fs");
const w = Wallet.createRandom();
const varName = process.argv[1];
// ★키는 파일로만 나간다. stdout 으로는 주소만.
fs.appendFileSync(".env", `${varName}=${w.privateKey}\n`, { mode: 0o600 });
try { fs.chmodSync(".env", 0o600); } catch (e) {}
process.stdout.write(w.address);
' "$VAR")

echo "✔ ${VAR} 를 .env 에 만들었습니다(권한 600 · git 무시됨)"
echo "  주소: ${ADDR}"
echo
echo "다음 단계"
echo "  1) 이 주소로 **테스트넷 가스**를 받으십시오(Polygon Amoy):"
echo "       https://faucet.polygon.technology  (네트워크: Amoy · 주소: ${ADDR})"
echo "  2) .env 에 RPC 를 넣으십시오. ★기본값 rpc-amoy.polygon.technology 는 막히는 곳이 있습니다:"
echo "       POLYGON_AMOY_RPC_URL=https://polygon-amoy-bor-rpc.publicnode.com"
echo "  3) 배포:  DEPLOY_CONTRACT=DrawRegistry npm run deploy:amoy"
echo
echo "★키는 출력하지 않았습니다. .env 를 열어 보지 말고 그대로 두십시오."
echo "★이 주소가 컨트랙트 **owner** 가 됩니다 — 잃어버리면 운영자 목록을 못 바꿉니다."
