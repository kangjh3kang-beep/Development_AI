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
