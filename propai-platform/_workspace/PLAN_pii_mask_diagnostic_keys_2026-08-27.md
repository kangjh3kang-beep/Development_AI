# 적재 마스킹이 **진단 필드를 지운다** — 계획서

- 세션 `development-ai-9d [088a1a]` · 브랜치 `fix/pii-mask-substring-false-positive`
- PR `#903` 후속 — 경계가 보고해도 payload 가 지워지면 반쪽이다

## 0. 옵시디언 조회 결과

| 찾을 것 | 결과 |
|---|---|
| 이미 기각된 접근 | **없음**(이 주제로 볼트에 기각 기록 0건) |
| 같은 클래스의 앞선 결함 | 있음 — `wiki/dev-tasks/2026-08-23_계측을_넣고도_읽지_못했다_F4a격리.md`(수집과 조회는 다른 일) · 오늘 쓴 `errors/2026-08-27_소스_배선_락은_死코드와_별칭을_구별하지_못한다.md` 가 이 결함을 **이미 실측 기록**해 두었다 |
| 미결·부채 | 위 문서 §Next Actions 3 이 이 건을 넘겨 두었다 |
| 이전 판단의 근거 | 없음(신규) |

## 1. 전제 표 — 확인 방법과 **실제 측정값**

★모두 **원본 함수를 AST 로 추출해 그대로 실행**해 잰 값이다(내 재구현이 아니다).

| # | 전제 | 확인 방법 | 실제 결과 |
|---|---|---|---|
| P1 | `mask_pii` 가 적재 경로에 실재하나 | 소비처 전수 grep | `capture_service.py:134` `props["payload"] = mask_pii(...)` · `growth.py:558`(피드백) · `learning_loop.py:76`(LLM 요약) |
| P2 | 판정이 부분일치인가 | 원문 `:108` | `any(p in key_l for p in _PII_KEYS)` — **부분일치** |
| P3 | `filename` 이 지워지나 | 원본 함수 실행 | `{"filename": …}` → **`{"filename": "[redacted]"}`** |
| P4 | 대조군(정당 PII)은 정상인가 | 같은 실행 | `owner_name`·`user_email`·`contact_phone`·`jumin` → 전부 `[redacted]` ◎ |
| P5 | 대조군(진단)은 보존되나 | 같은 실행 | `message`·`stack`·`route`·`scope`·`digest` → 전부 보존 ◎ |
| P6 | 위양성이 `filename` 뿐인가 | 프론트 `trackEvent(` 호출 인자에서 payload 키 **파생 전수** | 11키 중 **1건**(`filename`) |
| P7 | ★「토큰경계로 바꾸기」가 나은가 | 두 모집단(정당 PII 19 · 진단 16)을 양쪽 매처에 태움 | **아니다.** 위양성 12/16→8/16 로만 줄고 **PII 누출 5건**(`username`·`firstname`·`lastname`·`nickname`·`realname`) 발생 → **기각** |
| P8 | 백엔드가 주소를 지우나 | 원본 실행 | **안 지운다** — `{"note":"서울…테헤란로 152 3동 401호"}` **그대로 통과**. 그런데 `learning_loop.py:69` 주석은 *"주소 등 제거"* 라고 **선언**했다(선언≠구현) |
| P9 | 회귀 1건이 내 것인가 | **대조군**: `origin/main` 전용 워크트리에서 같은 테스트 실행 | **기준선 실패**(내 변경 없이도 FAILED) — `test_growth_loop_e2e::test_growth_loop_and_determinism`. 공유 DB 상태 의존 + 이벤트 루프 오류 |

## 2. 변경 내용과 회귀가 아닌 근거

1. `_DIAGNOSTIC_SAFE_KEYS = frozenset({"filename"})` — **정확일치** 면제를 부분일치 **앞**에 둔다.
2. `learning_loop.py` 의 **거짓 주석 교정**(주소는 값 안에서 안 지워진다는 사실을 명시).

**회귀가 아닌 근거**
- 면제는 **정확일치**라 `owner_filename` 같은 변형은 계속 redact 된다(테스트로 잠금).
- 면제된 키의 **값**도 `_mask_str` 을 계속 통과한다(이메일·전화·주민번호는 여전히 치환).
- 매처 자체는 **건드리지 않았다** — 미지의 키는 계속 fail-safe 로 redact.
- 관련 백엔드 회귀 **260 passed · 2 xfailed**, 실패 1건은 **P9 로 기준선 확증**.
- `ruff check` All checks passed.

## 3. ★검증하지 못한 것

- **`analysis_ledger` payload 키 모집단 미측정.** 면제 목록은 **프론트 이벤트 모집단**에서 파생했다.
  `learning_loop._summarize_payload` 가 태우는 부동산 분석 payload 에는 아직 위양성이 남아 있을 수 있다.
- **주소 마스킹 부재는 고치지 않았다 — 단독 판단하지 않았다.** 이 경로가 태우는 것은
  `analysis_ledger` 부동산 분석 payload 이고 **주소가 곧 분석 대상**이라, 지우면 학습 신호를
  파괴할 수 있다. 대신 **`xfail(strict=True)` 로 초록 안에 보이게** 남겼다 — 고쳐지면 XPASS 로 시끄럽게 알린다.
- **라이브 확증 미완.** 실제 적재된 `platform_events.payload` 에 `filename` 이 남는지는 배포 후에만 판정된다.
  (원본 이벤트를 event_type 별로 세는 GET 엔드포인트가 **없다** — 별건 부채)
- **`logging_config.py:26` 의 동명 `mask_pii`** 는 다른 함수다. 이 PR 은 건드리지 않았고 **미측정**이다.
- 이 워크트리에 **`.env` 가 없다** — 통합 테스트가 CI 와 다른 DB 로 떨어진다. P9 는 그래서 대조군으로만 판정했다.

## 3-b. ★독립 적대 리뷰가 찾은 것 — **내 처방이 보안 회귀를 만들고 있었다**

리뷰 판정은 **HIGH · 머지 반대**였다. 셋 다 봉합했다.

| # | 무엇 | 근거(리뷰 실측) | 봉합 |
|---|---|---|---|
| **C1** | ★**면제가 실제 노출을 만든다.** `ErrorEvent.filename` 은 **인라인 스크립트 오류에서 문서 URL 전체**(헤드리스 브라우저 실측)이고, 이 앱은 **지번을 쿼리에** 싣는다(`LandScheduleClient.tsx:460`). 프론트는 `message`·`stack` 만 `maskString` 하고 **`filename` 만 생것**이라, 백엔드가 마지막 층이었는데 **내 PR 이 그것을 걷어냈다**. 게다가 **퍼센트 인코딩이 `_mask_str` 정규식을 전부 비켜 간다**(`hong%40corp.co.kr`) | 6층 각각 실측 + 대조군 | ①프론트 `filename` 도 `maskString` 경유(2곳) ②백엔드 `_mask_diagnostic` — **URL 쿼리·프래그먼트 절단 + 퍼센트 디코드 검사**. 진단에는 경로만으로 충분하므로 목적 훼손 0 |
| **C2** | 「기각한 처방을 잠갔다」가 **거짓**. 손으로 고른 5개만 특례로 비켜 가는 토큰경계 리팩토링이 **SURVIVED**(새 누출 14건) | 변이 실측 | 목록이 아니라 **성질**을 잠근다 — `_PII_KEYS` **전수 × 변형 6종** |
| **C3** | (정)은 파생형인데 **(역)이 목록형** → 면제에 `contact_name`·`home_addr1` 을 넣어도 **락 17개 전부 초록** | 변이 실측 | 면제 ⊆ **파생된 프론트 payload 키** + **죽은 면제 금지** |
| **H1** | 같은 거짓 선언이 **내가 편집한 파일 포함 2곳에 더** 있었다 | `grep` 전수 | 둘 다 교정(사후 0건 확인) |
| **H2** | 수집기가 **간접 전달**(payload 를 변수로)을 못 봐 4키 누락. 그런데 **분모는 채워** 생존 단언이 공허했다 | 파생 집합 실측 | 축을 `TrackEventProps` 반환 함수까지 확장(11키 → **15키**) + **미해석 호출 0 단언** + 간접 키(`verdict`)를 **양성 대조군**으로 |
| **L1** | 내 `_EXCLUDE` 정규식이 `r"\\."` 라 `.next/`·`*.test.ts` 를 **하나도 배제 못 했다** | 실측 | 교정 |
| **L2** | 내 주석의 **「23개」가 재현 불가**(폐기된 축의 값) | 실측 | **15** 로 교정 + 왜 틀렸는지 명기 |

★**리뷰가 기각한 우려도 함께 남긴다**(다시 태우지 않도록): 대소문자·유니코드 합자·전각·PII 부모 아래 중첩·면제의 부분일치 누수·업로드 파일명·`xfail` 사유 정직성·`logging_config.mask_pii`(키 판정이 **없어** 같은 결함이 원리적으로 불가) — **전부 문제 없음으로 실측됨**.

## 3-c. 여전히 검증하지 못한 것 (추가)

- **백엔드 `record_event(` 직접 호출부 14곳**(`middleware/growth_telemetry.py` · `verification/verifier_service.py` ·
  `ai/base_interpreter.py` · `zoning/auto_zoning_service.py` 외)의 payload 키 모집단은 **미측정**이다 —
  프론트 파생 집합에 원리적으로 들어올 수 없으므로 같은 위양성이 남아 있을 수 있다.
- **라이브 확증 미완**: 프로덕션 `platform_events.payload->>'filename'` 의 값 분포를 못 쟀다
  (원본 이벤트 조회 엔드포인트가 **없다**). C1 의 전제(인라인 컨텍스트 오류 비율)는 **미측정**이다.
- `_mask_str` 의 **퍼센트 인코딩 우회**는 면제 경로에서만 막았다 — **일반 값에는 그대로 남아 있다**(별건 부채).

## 4. 되돌리기 경로

단일 커밋 revert. 상수 1개 + 분기 1개 + 주석 + 테스트 파일 1개뿐이고 스키마·계약 변경이 없다.
되돌리면 정확히 이전 동작(=`filename` 유실)으로 복귀한다.

## 5. 잠금

| 락 | 잠그는 것 |
|---|---|
| `test_deriver_is_alive` | 수집기·파서 생존(소스 ≥3 · 키 ≥5) + **양성 대조군**(`filename` 이 파생 집합에 실재) |
| `test_frontend_diagnostic_keys_survive_masking` | (정) 프론트 payload 키 **전수**가 보존된다 — 손 목록이 아니라 `trackEvent(` 호출 인자에서 파생 |
| ★`test_rejected_token_boundary_refactor_stays_rejected` | **기각한 처방을 기계로 잠근다** — 그 5개 키의 redact 를 못 박아, 누가 매처를 "개선"하면 즉시 빨개진다 |
| `test_genuine_pii_keys_still_redacted` | (역) 면제를 넓히다 보호를 뚫지 않았는가 |
| `test_safe_list_does_not_cover_a_genuine_pii_key` | 면제가 **민감 키 자체**를 덮지 않는다 + 면제가 **부분일치로 새지 않는다**(`owner_filename`) |
| `test_masking_still_scrubs_value_patterns` | 면제된 키의 **값**도 계속 치환된다 |
| `test_address_in_value_is_masked_debt` | **부채를 초록 안에 보이게**(`xfail(strict=True)`) |

★**파생의 축을 두 번 고쳤다**(정직하게): 초판은 파일 이름 목록 → `FileNotFoundError`(그 파일이 아직
미머지) · 2판은 파일 전체의 `payload:` → **경매 화면의 TypeScript 타입 선언**까지 집어 `name` 을
위양성으로 신고했다(그대로 갔으면 *"`name` 을 안전키로 면제하라"* 는 **정반대 처방**을 유도했을 것이다).
3판에서 축을 **`trackEvent(` 호출 인자 안**으로 정밀화했다. **위양성도 결함이다.**
