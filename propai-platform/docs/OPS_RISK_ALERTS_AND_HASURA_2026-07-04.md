# 운영 노트 — 위험알림(Telegram) 활성화 · Hasura 설정 정리 (2026-07-04)

플랫폼 키 배선 감사(건강도 9.3/10)의 후속 조치 2건. 배선은 이미 완비되어 있으며, 아래는
**운영 활성화 절차**와 **정리 근거**를 정직하게 기록한다.

---

## ① 위험알림(Telegram) — 배선 완비, 환경변수만 주입하면 즉시 작동

### 배선 확인(코드 정독으로 실증 — 코드 수정 불필요)
자동 위험알림은 분석 원장 append 이벤트에 이미 종단 배선되어 있다:

```
분석 append (ledger_adapters.py:183-184)
  → on_analysis_appended()            (risk_monitor.py:163)
  → evaluate_chain_risk() 로 체인 위험 평가
  → dispatch_risk_alert()             (risk_monitor.py:170 → :145 _NOTIFIERS 순회)
  → _telegram_notifier(alert)         (risk_monitor.py:177)
      settings.TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID 있으면
      POST https://api.telegram.org/bot{token}/sendMessage
```
등록은 앱 시작 시 `main.py:252-253` 의 `setup_default_notifiers()` 가 수행한다
(`register_notifier(_telegram_notifier)` + `_ws_notifier`, 둘 다 graceful·env-gated).
**두 환경변수 미설정 시 조용히 no-op**(정직) — 배포 blocker 아님. 설정하면 그 즉시 고위험
분석마다 텔레그램 메시지가 발송된다.

### 활성화 절차(발급 — 무료)
1. **봇 토큰 발급**: 텔레그램 앱에서 **@BotFather** 대화 → `/newbot` → 봇 이름·username 지정
   → `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` 형태 토큰 수령 → `TELEGRAM_BOT_TOKEN`.
2. **수신 chat_id 확인**(택1):
   - 개인 수신: 텔레그램에서 **@userinfobot** 에게 말 걸면 내 숫자 ID 표시.
   - 또는 만든 봇에게 아무 메시지 1개 보낸 뒤
     `https://api.telegram.org/bot<토큰>/getUpdates` 열어 `result[].message.chat.id` 확인.
   - 그룹 수신: 그룹에 봇을 추가하고 그룹에서 메시지 후 getUpdates 로 확인(`-100...` 형태).
   → `TELEGRAM_CHAT_ID`.
3. **환경변수 주입**(오라클 백엔드 A1): 서버 `.env`(또는 systemd Environment/컴포즈 env)에
   ```
   TELEGRAM_BOT_TOKEN=123456789:AA...
   TELEGRAM_CHAT_ID=987654321
   ```
   추가 후 API 재기동. (config.py 는 아니라 **app/core/config.py:113-114** 의 대문자 필드가 소비.)
4. **작동 확인**: 실제 위험 분석 발생 시 자동 발송. 즉시 점검은 봇 토큰으로
   `curl "https://api.telegram.org/bot<토큰>/getMe"` (200·봇 정보) 로 토큰 유효성만 확인
   (실 알림은 고위험 분석 이벤트에서 트리거 — 임의 발송 코드는 두지 않음).

### 참고: RISK_MODEL_PATH (별개 — API 키 아님)
`risk_predictor.py:52-64` 의 위험**예측**은 미설정 시 **휴리스틱(규칙기반) 폴백**으로 정직 동작.
`RISK_MODEL_PATH` 는 "발급받는 키"가 아니라 **데이터팀이 오프라인 학습한 XGBoost 모델 파일
경로**(`.json`/`.ubj`). 실제 학습 모델이 생겼을 때만 그 경로를 지정하면 자동 사용된다. 지금은
설정 불필요(휴리스틱으로 안전).

---

## ② Hasura 설정 정리 — FastAPI 앱의 사문 필드만 제거(인프라는 보존)

### 사실관계(감사 재확인)
- **인프라 레벨엔 Hasura 실재**: `infra/docker/docker-compose.prod.yml`·`docker-compose.dev.yml`
  에 `hasura/graphql-engine:v2.38.0` 서비스, `infra/hasura/metadata/*`, `infra/k8s/base/configmap.yaml`
  (`HASURA_URL`). 이 컨테이너는 `HASURA_GRAPHQL_ADMIN_SECRET` 환경변수를 **직접** 읽는다.
- **그러나 FastAPI 앱은 Hasura 를 소비하지 않는다**: 앱 코드 전수 grep 결과 `settings.hasura_*`
  소비처 0, 테스트 참조 0. `apps/api/config.py` 의 `hasura_admin_secret`·`hasura_url` 필드는
  **선언만 있고 아무도 읽지 않는 사문(dead)** 이었다.

### 조치
- `apps/api/config.py` 의 `hasura_admin_secret`·`hasura_url` **두 필드 선언 제거**(사유 주석 대체).
  pydantic `extra="ignore"` 라 해당 env 가 설정돼 있어도 무해히 무시된다.
- **인프라(docker-compose·k8s·hasura metadata)는 손대지 않는다** — 별도 GraphQL 서비스로 운영될
  수 있으므로 보존. Hasura 를 실제 쓰려면 그 admin secret 은 컴포즈 env(`HASURA_ADMIN_SECRET`)에서
  본인이 지정(`openssl rand -hex 32`)하며, "외부 발급"이 아니다.
- `app/core/config.py` 의 `_KNOWN_WEAK_SECRETS` 내 `"hasura_super_secret_key"` 항목은 **유지** —
  약한 시크릿 차단 블록리스트 항목이라 무해하고 방어적.

### 결론
앱 config 는 실제 사용하는 것만 남아 오해 소지 제거. Hasura 를 쓸지(인프라 컴포즈로) 여부는
데이터/GraphQL 트랙(`.build-journal/track-gql.md`)의 별도 결정 사항으로 남긴다.
