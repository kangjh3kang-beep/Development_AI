# 키 「테스트」가 **값만 있으면 초록**이었다 + 손목록이 두 언어에 각각

- 2026-09-02 · 세션 `development-ai-3c [8cabd7]` · 브랜치 `fix/secret-test-honesty` (base `86caf750`)

## 0. 옵시디언·저장소 조회 결과

| 찾을 것 | 결과 |
|---|---|
| 이미 기각된 접근 | **있음** — 부재 사유를 **파일마다 다른 모양**으로 적는 것은 기각됐다(`app/utils/withheld.py` 머리말: 어휘가 다섯 갈래라 «기계가 셀 수 없다»). → **새 어휘를 만들지 않고 `NOT_APPLICABLE` 을 쓴다.** |
| 같은 클래스의 앞선 결함 | **있음** — `#932`(동료 `88`)가 **화면**의 존재 배지에서 성공색을 걷어냈다. 이 PR 은 그 **API 응답 쪽 형제 미러**다. |
| 미결·부채 | **있음** — `88` 이 «제가 안 잡습니다» 로 넘긴 좌표 3건(canTest 손목록 · `MOLEG_API_KEY` 미등록 · `live_status()` 가 키 이름을 안 받음). |
| 이전 판단의 근거 | `#932` 의 근거(*"`is_set` 은 값이 저장돼 있다는 뜻뿐"*)를 **그대로 계승**한다. |

## 1. 전제 표 — 측정 방법과 실제 값

| 전제 | 방법 | 결과 |
|---|---|---|
| 카탈로그 크기 | `ast` 로 `CATALOG` 파생 | **41키** |
| 전용 테스트 지원 | 라우터 집합 리터럴 | **4키** |
| 나머지 | 41 − 4 | **37키** — 버튼 미렌더 + 백엔드 `ok: True` |
| 두 손목록이 지금 갈렸나 | 양쪽 비교 | **아니오, 일치** → **지금 결함이 아니라 잠금이 없는 것** |
| `MOLEG_API_KEY` 카탈로그 | `ast` 파생 | **미등록** |
| 그 키가 프로덕션에서 쓰이나 | **실행 중 컨테이너**에서 실호출 | **설정됨 · HTTP 200 `<OrdinSearch>` `resultCode 00`** ★대조군(틀린 키) → `<Response>` |
| `/test` 응답 소비처 | 파생형 조회 | **UI 1곳뿐**(`tests/test_80_percent_push.py` 매치는 **웹훅 시크릿 문자열** = 이름 충돌 오탐) |
| 열린 PR 겹침 | 전수 | **0건** |

★**추출기가 한 번 죽었고 그것이 드러났다**: 첫 `CATALOG` 파생이 `Assign` 만 봐서 실패했는데
(`CATALOG: list[...] =` 는 `AnnAssign`), **생존 가드가 조용한 0 대신 「조회기 사망」을 신고**했다.

## 2. 변경 내용과 회귀가 아닌 근거

1. **거짓 초록 제거** — 미지원 키 응답을 `withheld(NOT_APPLICABLE, …, field="ok")` 로.
   `ok: None` 은 truthy 가 아니라 화면이 성공으로 못 그린다. 사유 코드는 **기계가 센다**.
2. **손목록을 양쪽 모듈 상수로** — 백엔드 `_TESTABLE_SECRETS` · 프론트 `TESTABLE_SECRETS`.
   인라인이면 **기계가 파생시킬 수 없다.**
3. **`MOLEG_API_KEY` 카탈로그 등재** — IP 등록이 별도로 필요하다는 사실을 `desc` 에 적었다.

회귀 아님: 백엔드 **110 passed**(`-k "secret or admin_secret or withheld or catalog"`) ·
`tsc --noEmit` rc=0 · ruff(**0.16.3** = CI) clean · 응답 소비처가 UI 1곳뿐이고 그 UI 는
지원 4키에만 버튼을 그리므로 **사용자 가시 동작 변화 0**.

## 3. ★검증하지 못한 것 / 내가 틀린 것

1. **★내 첫 행위 락이 「복제본」을 태웠다.** 응답 구성을 테스트 안에 다시 만들어
   (`_unsupported_response()`), **원래 결함 두 변이(`ok: True` 복원 · `None`→`False`)가
   둘 다 SURVIVED** 했다. 동료가 오늘 가르쳐 준 자문(*"내 락이 태우는 것이 프로덕션 코드인가,
   복제본인가?"*)을 **독스트링에 인용해 놓고 그대로 어겼다.**
   → 실제 핸들러 `AS.test_secret` 을 호출하도록 고쳤고 그때서야 CAUGHT 다.
2. **`ok: True` 분기는 UI 에서 도달 불가**다(프론트가 4키에만 버튼을 그린다).
   즉 **사용자 가시 결함이 아니라 다음 사람이 손목록에 키를 더하는 순간 밟는 함정**이다.
3. **`88` 의 «배지 55개» vs 내 카탈로그 파생 41개** — 두 수의 차이를 **재지 않았다**.
4. **`RegistryService.live_status()` 가 키 이름을 안 받아 4키가 같은 집계를 낸다**(88 실측) —
   **손대지 않았다.** 별건이다.
5. **37키에 실제 테스트를 구현하지 않았다.** 이 PR 은 *"없는 것을 없다고 말한다"* 까지다.
6. **`MOLEG_API_KEY` 를 화면에서 실제로 저장·조회해 보지 않았다**(카탈로그 등재만 확인).

## 4. 되돌리기

세 파일의 diff 를 되돌리면 종전 동작. `withheld` 헬퍼·카탈로그 구조는 무변경.

## 5. 잠금

| 지킬 것 | 검사 |
|---|---|
| 미지원이 **성공으로 위장되지 않는다** | `test_unsupported_key_is_not_reported_as_success` — ★**실제 핸들러**를 태운다 |
| 「값 없음」과 「미지원」이 **다른 층** | `test_missing_value_is_a_failure_not_a_withheld` |
| 지원 키는 미지원 분기로 안 간다(**두 번째 모집단**) | `test_supported_key_does_not_take_the_unsupported_path` |
| 두 언어 손목록 **전수 일치** | `test_front_and_back_testable_lists_match_exactly`(ast + 3표기 정규식) |
| 상수가 **분기에 실제로 소비**된다 | `test_the_branch_actually_dispatches_on_the_constant` + 인라인 잔재 음성 대조군 |
| 테스트 대상 키가 **카탈로그에 있다** | `test_every_testable_key_is_in_the_catalog` |
| `MOLEG_API_KEY` 관리 가능 | `test_moleg_key_is_managed_because_production_depends_on_it` |
| 추출기 생존 | `test_extractors_are_alive_before_any_comparison` + **디스크 독립 재계수 결속** |

### 변이 — 기준선 rc=0 확인 후 · `__pycache__` 삭제 · 원복 바이트동일

    M1 ★거짓 초록 복원(원래 결함이 살던 자리)   CAUGHT  ← 복제본 락에서는 SURVIVED 였다
    M2 ★ok None → False(실패와 미지원을 뭉갬)   CAUGHT  ← 같음
    M3 사유 코드 교체                            CAUGHT
    M4 값 없음도 보류로 뭉갬                     CAUGHT
    M5 지원 키도 미지원 분기로                   CAUGHT
    M6 프론트에서만 키 제거                      CAUGHT
    M7 MOLEG 카탈로그 제거                       CAUGHT

---

# 6. 독립 적대 리뷰 — **REQUEST CHANGES(HIGH 2)** 를 받았고 봉합했다

## 6-1. ★HIGH-2 — 이 PR 이 **작동하지 않는 조작 수단**을 만들 뻔했다

`MOLEG_API_KEY` 를 카탈로그에 넣어 운영자가 화면에서 조회·저장할 수 있게 했는데,
**저장이 런타임에 반영되지 않는다**:

    PUT /admin/secrets/{name}  →  os.environ[name] = value   **만**
    소비처                      →  settings.MOLEG_API_KEY     ← 모듈 싱글턴 · @lru_cache
    재동기화 경로                →  **0건**(전수 조회 · 대조군 `object.__setattr__` 3건으로 조회기 생존 확인)

★**이 PR 이 고치겠다고 선언한 결함 클래스**(*"확인되지 않은 것을 확인된 것처럼 그린다"*)를
**이 PR 의 신규 코드가 재발**시킨 것이다(§D-16). 저장소는 그 갭을 **이미 두 곳에 적어 뒀다**
(`observability.py` · `test_base_interpreter_fewshot.py`).

**처방 — 문서화가 아니라 고침**: `moleg_oc_key()` 공용 함수를 만들어 **호출 시점에**
`os.environ` → `settings` 순으로 읽는다(저장소 선례 `_fewshot_enabled` 와 같은 순서).
**소비처 5곳 전부 배선**(ordinance 2 · regulation_monitor 1 · gosi_search 1 · deliberation 1)
— 한 곳을 고치면 전역이 따라오게(버그수정 기본정책).

락: **파생형**으로 «`settings` 에서 직접 읽는 소비처 0» + 음성 대조군(배선 3곳 이상) +
**행위**(런타임 갱신 즉시 반영 / 없으면 부팅 설정 / **빈 문자열이 부팅 설정을 가리지 않음**).

## 6-2. ★HIGH-1 — 「축을 소비까지」를 **한쪽에만** 적용했다

백엔드에는 «상수가 분기에 실제로 소비되는가» 락을 넣고 **프론트에는 안 넣었다** —
`canTest` 를 옛 인라인 배열로 되돌려도 **락 8개가 전부 초록**(리뷰가 변이로 실증).

★`#938` 에서 배운 *"파생형이어도 축이 한 단계 위면 그 아래는 무잠금"* 을
**대칭으로 적용하지 않은 것**이다.

처방: 형제 vitest(`ApiKeyBadge.presence-is-not-success.test.tsx`)에 **렌더 기반 두 모집단**
(`TILKO_API_KEY` 엔 「테스트」 **있고**, `VWORLD_API_KEY` 엔 **없다**) + 공허진리 방지
(두 카드가 실제로 버튼을 갖는지). 재판정 → **CAUGHT**.

## 6-3. 그 밖에

| 지적 | 처방 |
|---|---|
| **M-1** 응답이 저장소 표준 검증기(`validate_withheld_pair`)를 기본 호출로 통과 못 함 | 락에 `text_field="message"` 로 단언 추가 + 그 키를 쓴 이유를 호출부에 명시 |
| **M-2** ★프론트가 `ok: null` 을 **빨강**으로 그린다(`!!null === false`) — 거짓 초록을 고치고 **거짓 빨강**을 얻는 자리 | 타입을 `boolean \| null` 로 **정직하게** 적고 `msg` 를 **3상태**(`ok`/`fail`/`withheld`)로. ★`tsc` 가 나머지 호출부 **7건**을 즉시 잡았다 |
| **M-3** `secret: False` 라 OC 값이 **평문 노출** | `secret: True`. `export_scoped_secrets.py` 가 이미 스코프 시크릿으로 분류하던 것과 정합 |
| **M-4** 생존 가드가 **위양성 3종**(트레일링 콤마 제거·홑따옴표·배열 안 주석) | 재계수를 **같은 표기 집합**으로 통일 + **주석 제거 후** 파싱 |
| **L-1** `withheld()` 의 `ValueError` 가 `except Exception` 에 **조용히 강등** | 응답 구성을 `_unsupported()` 로 빼 **`try` 밖**으로 |

## 6-4. ★rebase — 하마터면 `#938` 을 되돌릴 뻔했다

이 브랜치 base 가 `86caf750` 이라 **`#938` 머지 이전**이었는데, 그 사실을 모르고
`ordinance_service.py`(#938 이 고친 파일)를 **구 버전 위에서** 편집했다.
→ 스냅샷 보관 → `git stash` → `git rebase origin/main` → **`#938` 포함 확증** 후 재적용.

★**가드가 나를 막았다**: `git checkout --` 를 쓰려다 `guard-destructive-restore.sh` 가
차단하고 **되돌릴 길을 남기는 `stash`** 를 권했다(§B-7). 내가 배치한 가드에 내가 걸렸고,
그 판단이 옳았다.

## 6-5. ★여전히 검증하지 못한 것 (§3 을 대체·확장)

1. **37키에 실제 테스트를 구현하지 않았다** — 이 PR 은 *"없는 것을 없다고 말한다"* 까지다.
2. **`RegistryService.live_status()` 가 키 이름을 안 받아 4키가 같은 집계를 낸다**(동료 실측) — 별건.
3. **`88` 의 «배지 55개» vs 내 카탈로그 파생 41개** — 차이를 재지 않았다.
4. **`MOLEG_API_KEY` 를 화면에서 실제로 저장해 조례 조회가 붙는지 라이브로 확인하지 않았다.**
   콜타임 읽기는 **단위 락으로만** 증명했다.
5. **`secret: True` 전환이 기존 운영 절차에 영향을 주는지** 재지 않았다(마스킹만 확인).
6. **다른 시크릿들도 같은 `settings` 갭을 갖는지** — MOLEG 만 봤다. **전역 스윕 미실시.**
