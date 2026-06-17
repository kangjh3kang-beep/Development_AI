# 실 API 키 발급·주입 가이드 (실연동)

> ⚠️ **키는 비밀입니다.** 채팅/이슈/커밋에 붙여넣지 마세요(로그·캐시에 남음). 오직 로컬 `.env`(gitignore됨)에만 둡니다.

## 0. ★ 플랫폼 관리자 키 연결 — 방식 C: 플랫폼이 스코프 키만 내보내기 (권장)

관리자가 플랫폼에 입력한 키는 `propai_db.platform_secrets`(Fernet 암호화)와 플랫폼 `.env`에 있습니다
(VWORLD/ANTHROPIC/OPENAI 등). 이 엔진은 **별도 서비스**라, 엔진이 플랫폼 마스터키로 금고 전체를
복호화하면 *한 서비스가 다른 서비스 자격증명 보관소에 접근*하는 신뢰 경계를 넘습니다.

대신 **플랫폼(금고의 정당한 소유자)** 이 자기 마스터키로 복호화하고, 엔진이 실제 필요한
**허용목록 키만** 엔진의 `.env.secrets`로 내보냅니다. 엔진은 자기 `.env(.secrets)`만 읽습니다
(마스터키·금고 접근 0).

**1) 플랫폼에서 스코프 키 내보내기**(플랫폼 운영자가 `propai-platform/apps/api`에서, venv 활성):
```
python scripts/export_scoped_secrets.py \
  --target /절대경로/propai-review/.env.secrets --with-db
```
- 출처: 플랫폼 `.env` 베이스라인 + (`--with-db` 시) `platform_secrets`를 플랫폼과 **동일 로직**으로 복호화 오버레이.
- 기록 대상: 허용목록(`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`VWORLD_API_KEY`/`MOLIT_API_KEY`, `--allow`로 확장).
- 마스터키·인프라 키(DATABASE_URL/JWT/SECRET 등)는 **하드 디나이**로 절대 미포함. 파일 권한 `0600`.
- 출력 요약은 키명·설정여부·마스킹값만(평문 미노출).

**2) 엔진 측 `.env`**(이미 기본값):
```
SHEET_CLASSIFIER=vllm        # ANTHROPIC 키가 .env.secrets에서 채워지면 VLLM live
JURISDICTION_ADAPTER=vworld  # VWORLD 키가 채워지면 관할 live
LOAD_PLATFORM_SECRETS=false  # 크로스서비스 금고 복호화 비활성(방식 C는 불필요)
```
- 엔진 `settings`가 `.env` 위에 `.env.secrets`를 오버레이 → 어댑터가 즉시 사용. `.env.secrets`는 gitignore됨.
- 검증: `curl localhost:8801/api/v1/doctor` → `sheet_classifier.live:true`, `jurisdiction.live:true`,
  `platform_secrets.master_key_present:false`(경계 안 넘음).

> 보안: 복호화는 **마스터키를 가진 플랫폼 운영자만** 수행. 키 값은 로그/응답/요약에 노출되지 않습니다(마스킹).

<details><summary>대안(비권장): 엔진이 직접 금고 복호화 — 신뢰 경계 이슈</summary>

엔진 `.env`에 `LOAD_PLATFORM_SECRETS=true` + 플랫폼과 동일한 마스터키(`SECRET_STORE_KEY`/`APP_SECRET_KEY`/
`JWT_SECRET_KEY`) 또는 `PLATFORM_ENV_FILE=<플랫폼 .env 경로들>`을 주면, 엔진이 `platform_secrets`를
직접 복호화→`os.environ` 오버레이합니다. 후보 마스터키를 순차 시도해 실제 복호화되는 키를 선택하며
(가정 대신 검증), 위험 키는 DENYLIST 차단. 단, **별도 서비스가 플랫폼 금고 전체에 접근**하는 구조라
방식 C 대비 권장하지 않습니다. 커넥터 단위검증: `tests/services/test_platform_secret_loader.py`.
</details>

## 1. VLLM (설계도서 멀티모달 자동해석) — Anthropic
- 발급: <https://console.anthropic.com> → 로그인 → **API Keys** → Create Key → `sk-ant-…`
- 주입(`apps/api/.env` 또는 셸):
  ```
  SHEET_CLASSIFIER=vllm
  ANTHROPIC_API_KEY=sk-ant-...
  VLLM_MODEL=claude-sonnet-4-6
  ```
- 대안: OpenAI 비전(추후 어댑터 추가 시) <https://platform.openai.com/api-keys>.

## 2. 관할(용도지역) — VWORLD (국토교통부 공간정보 오픈플랫폼)
- 발급: <https://www.vworld.kr> → 회원가입 → **오픈API → 인증키 신청**(데이터 API) → 키 발급.
- 주입:
  ```
  JURISDICTION_ADAPTER=vworld
  VWORLD_API_KEY=...
  VWORLD_API_URL=https://api.vworld.kr/req/data
  ```
- ⚠️ 용도지역 데이터 레이어ID(`LT_C_UQ111` 등)·속성명은 VWORLD 문서로 확정 후 `adapters/jurisdiction/vworld.py`에서 보정.

## 3. 기타(향후)
- 토지이음(LURIS) <https://www.eum.go.kr>, 국가법령정보(ELIS/law.go.kr) — 기관 개발자 등록 필요. 동일 어댑터 패턴으로 추가.
- API 인증 토큰(엔진 보호): `API_TOKEN=<임의 토큰>` → 모든 /analyze 호출에 `Authorization: Bearer <토큰>` 필요.

## 4. 주입 후 실연동 검증 (사용자가 직접 실행)
```bash
cd apps/api
export $(grep -v '^#' .env | xargs)              # .env 로드(또는 셸에 export)
../../.venv/bin/python -m uvicorn app.main:app --port 8801 &
# (1) 통합 상태 — live=true 인지 확인(키 값은 노출 안 됨)
curl -s localhost:8801/api/v1/doctor | python3 -m json.tool
# (2) 실 분석 — VLLM/VWORLD가 실제로 호출되는지(도면 이미지/실 PNU로)
curl -s -X POST localhost:8801/api/v1/analyze -H 'Content-Type: application/json' -d @sample.json
```
- `doctor`의 `sheet_classifier.live` / `jurisdiction.live` 가 `true`면 실연동 활성.
- 키 없으면 정직하게 `false`(mock/degraded) — 은폐하지 않음.

## 5. 현재 환경 실측 진단 (2026-06-16)
| 키 | 상태 | 앱(자식 프로세스) 사용 가능? |
|----|------|------------------------------|
| ANTHROPIC_API_KEY | `~/.bashrc`에 값 있음(len 108) | ❌ **`export` 누락**(line 236) → 미전달. `export` 추가하면 가능. **라이브 호출 200·단면도→SECTION 검증 완료.** |
| OPENAI_API_KEY | `~/.bashrc`에 `export`됨(len 164) | ✅ 전달됨 |
| GOOGLE_API_KEY | `~/.bashrc`에 값 있음(len 39) | ❌ `export` 누락(line 237) |
| VWORLD_API_KEY | 미설정 | ❌ 없음 — VWORLD 관할 실연동하려면 발급 필요 |

**즉시 활성화 방법(택1):**
- (A) `~/.bashrc` 236/237행에 `export ` 접두 추가 → 새 셸부터 앱이 Anthropic/Google 키 수신.
- (B) `propai-review/.env`에 직접 추가(이제 apps/api에서 실행해도 로드됨):
  ```
  SHEET_CLASSIFIER=vllm
  ANTHROPIC_API_KEY=sk-ant-...
  ```
- (C) 실행 시 1회: `export ANTHROPIC_API_KEY SHEET_CLASSIFIER=vllm` 후 uvicorn.

- 코드 경로 검증: `tests/services/test_live_integration.py`(httpx 모킹 8). 라이브 VLLM: HTTP 200 + 단면도→SECTION(실측).
- VWORLD: 키 발급 후 (B)/(C)로 `JURISDICTION_ADAPTER=vworld`+`VWORLD_API_KEY` 주입.
