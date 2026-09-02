# 마스킹 락의 모집단을 **백엔드까지** — 계획서

- 세션 `development-ai-9d [088a1a]` · 브랜치 `test/pii-mask-backend-population`
- `#906` 이 계획서 §3 에 **「미측정」으로 남긴 항목**의 해소. **런타임 무변경 · 락만.**

## 0. 옵시디언 조회 결과

| 찾을 것 | 결과 |
|---|---|
| 이미 기각된 접근 | **없음** |
| 같은 클래스의 앞선 결함 | `errors/2026-08-27_기각한_처방을_목록으로_잠갔더니_그_목록이_상한이_됐다`(=`#906` 본체) · `errors/2026-08-25_…내가_말한_집합과_내_도구가_센_집합`(이름 충돌) |
| 미결·부채 | ★**이 건이 그 부채다** — `#906` §3 *"프론트 이벤트 모집단에서 파생했다 … 다른 모집단은 미측정"* |
| 이전 판단의 근거 | `#906` 은 매처를 약화시키지 않고 **정확일치 면제**만 두기로 했다. 그 결정은 유지한다 |

## 1. 전제 표 — 확인 방법과 **실제 측정값**

★모두 **원본 `mask_pii` 를 AST 로 추출해 그대로 실행**해 잰 값이다(재구현 아님).

| # | 전제 | 확인 방법 | 실제 결과 |
|---|---|---|---|
| P1 | 백엔드 모집단이 얼마인가 | `record_event(` **AST 파생** | ★세 번 갈렸다 — 아래 P2·P3 |
| P2 | **이름만**으로 매칭하면? | AST(`Call.func.attr/id == "record_event"`) | **25건 — 과다.** `api/endpoints/sales/referral.py:199` 가 **동명의 다른 함수**를 정의하고 `mh.py:46`·`referral.py:360,373` 이 그것을 부른다. `capture_service.py:213` 은 **정의 자신** |
| P3 | **모듈 별칭만**으로 매칭하면? | 모듈레벨 import 스캔 | **15건 — 과소.** `design_ingest/orchestrator.py:873`·`ingest_service.py:175` 가 **함수 안 지역 import** 라 안 잡힌다 |
| P4 | 둘 다 처리하면 | `ast.walk` + `defines_own` 제외 | **17건 · payload 키 54종 · 미해석 2건** |
| P5 | 미해석 2건은 무엇인가 | 원문 | `routers/growth.py:98`(프론트 적재 — 프론트 파생이 덮는다) · `ai/base_interpreter.py:410`(동적 조립 — 키 6종을 손으로 해소) |
| P6 | ★**위양성이 있는가** | 57종(54 + 동적 6, 중복 제외)을 원본 `mask_pii` 에 전수 | **0종.** `_PII_KEYS` 와 부분일치하는 **위험 근접 키도 0종** |
| P7 | 대조군은 정상인가 | 같은 실행 | 정당 PII(`owner_name`·`user_email`·`contact_phone`) → 전부 `[redacted]` ◎ / 진단(`message`·`stack`·`error`·`reason`) → 전부 보존 ◎ |
| P8 | 회귀 1건이 내 것인가 | 변경 범위 + 임포트 관계 | **아니다** — 내 변경은 **단일 테스트 파일**이고 그 실패 테스트가 **임포트하지 않는다**(`grep -c` = 0) · `conftest` 무변경 · 같은 실패를 오늘 `origin/main` **대조군 워크트리**에서 확인했다 |

## 2. 변경 내용과 회귀가 아닌 근거

**런타임 코드는 한 줄도 안 고쳤다** — P6 이 **위양성 0** 이므로 고칠 것이 없다.
락의 **파생 축에 백엔드 모집단을 추가**해, *앞으로* 추가될 백엔드 키가 부분일치에 걸리면 즉시 빨개진다.

- `test_backend_deriver_is_alive` — 하한을 **실측값에 붙였다**(호출 ≥17 · 키 ≥54) + 양성 대조군 3종
- `test_backend_unresolved_calls_are_documented` — ★**이름충돌 대조군을 겸한다**(아래 §5)
- `test_backend_payload_keys_survive_masking` — (정) 백엔드 키 전수가 보존된다

**회귀가 아닌 근거**: 런타임 무변경 · 관련 백엔드 **278 passed · 2 xfailed** · `ruff check` All checks passed ·
실패 1건은 P8 로 귀속 확정.

## 3. ★검증하지 못한 것

- **`analysis_ledger` payload 키 모집단은 여전히 미측정**이고 **정적 파생이 불가**하다
  (`learning_loop._summarize_payload` 가 태우는 것은 분석이 DB 에 쓴 임의 키다). `#906` 과 같은 공백.
- **동적 payload 6종은 손으로 해소했다** — `base_interpreter.py:410` 이 조건부로 조립하므로
  AST 로 파생되지 않는다. 그 6종이 바뀌면 **이 락은 모른다**(미해석 목록에는 남아 시끄럽지만,
  키 자체의 변화는 감시 밖이다).
- **위양성 0 은 「오늘의」 사실이다.** 이 락의 가치는 *미래* 방어이지 현재 결함 수정이 아니다.
- 라이브 확증 불필요(테스트 전용 변경).

## 3-b. ★독립 리뷰가 잡은 것 — **내 처방을 내 락이 막고 있었다**

리뷰 판정 **REQUEST CHANGES**(치명 1 · 중대 2). 전부 봉합했다.

| # | 무엇 | 근거 | 봉합 |
|---|---|---|---|
| **C1** | ★**교착**: `test_backend_payload_keys_survive_masking` 이 빨개지면 그 실패 메시지가 *"`_DIAGNOSTIC_SAFE_KEYS` 에 정확일치로 추가하라"* 고 지시하는데, `test_exemptions_are_derived_not_invented` 는 **여전히 `FRONTEND_PAYLOAD_KEYS` 만** 모집단으로 써서 백엔드 전용 면제를 **"발명"으로 신고**한다. 남는 길이 **락을 지우는 것뿐**이었다. ★`#906` 리뷰가 잡은 *"(정)은 파생형인데 (역)이 목록형"* 의 **거울상 재발** | 변이 M12(위양성 상황 재현 + PR 이 지시한 처방 적용) → `FAILED …invented` | 역방향 모집단을 `FRONTEND ∪ BACKEND ∪ DYNAMIC`(모듈 상수 `DERIVED_PAYLOAD_KEYS`)으로 |
| **H1** | ★**래퍼 경유가 모집단 밖이고 조용했다**: `capture_service.record_fallback(service, kind, *, severity, **meta)` 이 `payload: {"kind": kind, **meta}` 로 **임의 키를 그대로** 싣는데, 그 호출은 `capture_service.py` 안이라 `direct=False` 로 걸러져 **모집단에도 `unresolved` 에도 안 들어갔다** | 변이 M9(생산자에 `owner_name="X"` 주입) → **SURVIVED** | 파생 축에 `record_fallback` 편입(`kind` + 명시 kwargs, `severity` 제외) · `**meta` 전달은 **`unresolved` 로 신고** |
| **H2** | ★**`**` 언패킹·비상수 키가 조용히 버려졌다** — `unresolved` 로도 안 갔다. 같은 파일이 `strict=True` 로 *"조용히 잘리지 않고 터진다"* 고 적어 놓고 **이 줄이 조용히 잘랐다** | 변이 M8(`**{"owner_name": …}` 주입) → **SURVIVED** | payload·props **두 층 모두** 신고로 전환 |
| **L1** | §3 이 불완전하고 **한 항목은 틀린 라벨** | 리뷰 실측 | 아래 §3-c |
| **L2** | 하한만 걸려 **과대수집을 못 잡았다**(그 방어를 미해석 단언이 *오늘의 우연*으로 대신) | 리뷰 지적 | `19 <= BACKEND_CALLS <= 26` **양방향** + 실패 메시지에 **두 가능성**(수집기 사망 / 정당한 삭제)을 명시 |
| **L3** | 양성 대조군 `cache_hit` 이 **단일 출처** | 리뷰 실측 | 세 대조군의 **두께 차이**를 주석에 명시 |

★**봉합이 새로 찾아낸 것**: `base_interpreter.py:410` 의 **props 층에 실제 `**` 언패킹**이 있었다
(`**({"latency_ms": …} if … else {})`). payload 키가 아니라 형제 필드지만, 초판 파서는 그것을
**보지도 신고하지도 못했다.** 이제 사유와 함께 예외에 오른다.

## 3-c. 여전히 검증하지 못한 것 (리뷰 반영 · **틀린 라벨 정정 포함**)

- ★**정정**: 초판 §3 이 *"동적 payload 6종은 … **AST 로 파생되지 않는다**"* 라고 적었는데
  **틀린 라벨**이다. `base_interpreter.py:399-408` 은 리터럴 대입·`update()`·subscript 뿐이라
  **정적 파생은 가능**하고, **이 파생기의 현재 형태**(인라인 dict 리터럴만)로는 안 잡힐 뿐이다.
  두 문장은 다음 사람에게 **다른 결정**을 유도한다(§증거 규율 7 · §C10).
- **`mask_pii` 소비처는 `record_event` 만이 아니다 — 셋이다**: ①`record_event`(+`record_fallback`)
  ②`routers/growth.py:558` `mask_pii(fb.payload)`(`POST /growth/feedback` · `payload: dict | None`
  이라 **모집단이 임의** · 오늘 `payload` prop 을 넘기는 프론트 소비처 0개라 **실질 공집합**)
  ③`learning_loop._summarize_payload`(`analysis_ledger` — **정적 파생 불가**). ②③ 은 **미측정**이다.
- **2단 래퍼 `_record_engine_fallback(kind, **meta)`** 는 정적으로 못 따라간다. 오늘 싣는 키는
  `reason`·`path` 이나 **시그니처가 `**meta` 라 모집단이 열려 있다** — 값이 아니라 **그 사실**을 기록했다.
- `/growth/events` 는 **임의 HTTP 클라이언트**의 임의 키를 받는다 — *"우리 앱 `trackEvent` 가 유일한
  생산자"* 라는 **전제 하에서만** 프론트 파생이 그것을 덮는다(예외 주석에 전제를 명시했다).
- **위양성 0 은 「오늘의」 사실**이다. 이 락의 가치는 *미래* 방어다.

## 4. 되돌리기 경로

단일 커밋 revert. **테스트 파일 하나**뿐이고 런타임·계약·스키마 변경이 없다.

## 5. 잠금 — 그리고 ★대조군이 어디에 숨어 있는가

`test_backend_unresolved_calls_are_documented` 는 미해석 목록이 **문서화된 2건뿐**임을 단언한다.
★이것이 **이름충돌 대조군을 겸한다**: 동명의 다른 함수(`referral.record_event(db, code, event, …)`)를
잘못 포함하면 그 호출들은 payload dict 가 없어 **미해석이 2 → 5 로 늘어난다**. 즉 여기가 빨개진다.
그리고 **죽은 예외**(이미 해소됐는데 목록에 남은 것)도 실패시킨다.

★`zip(..., strict=True)` 로 바꿨다 — 길이가 어긋나면 **조용히 잘리지 않고 터진다**(파서 사망 노출).
