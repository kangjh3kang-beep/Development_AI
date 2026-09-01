# 법제처 DRF **XML 호출부 형제 미러 누락** — 봉투 검사가 4곳 중 2곳뿐이었다

- 날짜: 2026-09-01 · 세션 `development-ai-3c [8cabd7]`
- 브랜치 `fix/moleg-drf-xml-envelope` (base `origin/main` `64f234e4`)

## 0. 옵시디언 조회 결과

| 찾을 것 | 결과 |
|---|---|
| 이미 기각된 접근 | **있음** — 오류 봉투를 **열거**하는 방식은 이미 기각됐다(`moleg_drf_envelope.py` 독스트링: 계열 ③ `{"Law": "…없습니다"}` 를 못 잡아 `regulation_monitor` 가 60건 전건 실패인데 「변경 없음」을 냈다). **기대 루트키** 방식이 정본이다 — 그대로 따른다. |
| 같은 클래스의 앞선 결함 | **있음** — 같은 저장소에서 *"검증기를 격리 테스트만 하면 배선이 무잠금"* 을 이미 겪었다(`test_ordinance_drf_failure_is_not_silent.py` 머리말). |
| 미결·부채 | **있음** — 인계서가 *"ordinance_service XML 도 200-오류 봉투"* 를 무주인 부채 ④ 로 남겼다. |
| 이전 판단의 근거 | 헬퍼의 `expect` 상수는 **라이브 실측**에서 왔다고 적혀 있다 → 이번에 **다시 재서 일치 확인**했다(아래 §1). |

## 1. 전제 표 — **측정 방법과 실제 값**

| 전제 | 확인 방법 | 결과 |
|---|---|---|
| DRF 는 실패를 200 으로 준다 | 틀린 `OC` 로 `lawSearch.do` 직접 호출 | **HTTP 200** · 루트 `<Response><result>사용자 정보 검증에 실패하였습니다.` |
| 정상 응답 루트(목록) | 정상 `OC` 로 호출 | `<OrdinSearch>` (자치법규ID 1건) |
| 정상 응답 루트(본문) | 위에서 얻은 ID 로 `lawService.do` | `<LawService>` |
| 본문 「대상 없음」 | 존재하지 않는 ID | `<Law>일치하는 자치법규가 없습니다.` |
| 배선된 `expect` 상수가 옳은가 | 위 실측과 대조 | `_ORDIN_LIST_ROOTS=("OrdinSearch",)` · `_ORDIN_TEXT_ROOTS=("LawService",)` — **일치** |
| XML 호출부 수 | `ast` 파생 (`params` 에 `"type": "XML"`) | **4곳** (716 · 747 · 1551 · 1567) |
| 그중 봉투 검사 보유 | 감싸는 함수에 `raise_unless_expected_xml` 있는가 | **2곳뿐** — `_fetch_ordinance_xml` 이 무방비 |
| 열린 PR 과 겹치나 | 열린 PR 27건 전수에 `ordinance_service.py` | **0건** |

★**내가 처음 낸 판정은 틀렸다** — 아래 §3 에 그대로 적는다.

## 2. 변경 내용과 그것이 회귀가 아닌 근거

- `_fetch_ordinance_xml` 의 **두 호출부**에 `raise_unless_expected_xml` 을 배선. **형제
  `_fetch_from_moleg_api` 와 동일한 형태**이고 상수도 그대로 재사용한다(새로 만들지 않는다).
- **반환 계약은 안 바뀐다** — 광범위 `except Exception → None` 이 그대로라 성공/실패 반환값은
  여전히 같다. 바뀐 것은 ①실패 **감지** ②파싱 **차단** ③**사유 로그**뿐이다.
  ★형제가 그 한계를 이미 주석에 적어 뒀고, **같은 문장을 여기에도 적었다**(호출부가
  *"조회 실패"* 와 *"조례 없음"* 을 구분하게 만드는 것은 **별건**).
- 회귀 아님 근거: 조례 관련 **561 passed**(`-k "ordinance or moleg or slope"`) · 정상 경로
  두 번째 모집단 락으로 **과잉 억제 아님**을 같은 실행에서 증명.

## 3. ★검증하지 못한 것 / 내가 틀린 것

1. **★내 첫 판정이 틀렸다 — 낡은 트리에서 읽었다.** 처음에 *"헬퍼가 JSON 전용이라 XML 경로를
   만들어야 한다"* 고 보드에 CLAIM 했는데 **거짓**이다. 공유메인 워크트리가 **8커밋 뒤처져**
   있었고(`e0df0551` vs `64f234e4`) XML 경로는 **이미 있었다**. 신선한 워크트리에서
   재측정하고서야 알았다. 보드에 정정을 올렸다.
   ★볼트에 *"도구가 「없다」고 답하면 트리 지연부터 의심하라"* 가 적혀 있고 **알면서 밟았다.**
2. **BCR/FAR 소비처 수 미측정** — 인계서는 11개라 적었으나 **내가 세지 않았다.**
3. **프로덕션 상태 미측정** — 168 컨테이너의 `MOLEG_API_KEY`/IP 등록 상태를 확인하지 않았다.
   즉 *"지금 라이브에서 이 경로가 실제로 실패 중인가"* 는 **모른다**.
4. **화면 폴백은 그대로다** — 이 PR 은 오귀속을 **관측 가능**하게만 만든다. 사용자가 보는
   *"국가기준 25도 폴백"* 문구는 여전히 조회 실패와 조례 부재를 **구별하지 않는다**.
5. **`gosi_search_service`·`regulation_monitor` 는 안 봤다** — 둘 다 JSON 이고 배선돼 있다는
   것만 확인했고, `expect` 상수가 옳은지는 **재측정하지 않았다**.

## 4. 되돌리기 경로

추가한 두 줄(`raise_unless_expected_xml(...)`)을 지우면 종전 동작. 상수·헬퍼는 무변경.

## 5. 잠금 — 이 변경을 지키는 검사

| 지킬 것 | 검사 |
|---|---|
| **모든** XML 호출부가 봉투를 검사한다 | `test_every_function_that_calls_drf_xml_checks_the_envelope` — **`ast` 파생**(다섯 번째가 생기면 자동 감시 · 변이 M5 로 확인) |
| 파생이 살아 있다 | `test_derivation_is_alive_before_any_assertion`(하한 4곳·2함수 + 음성 대조군) |
| Step1 실패가 사유를 남긴다 | `test_step1_auth_failure_surfaces_the_reason` |
| Step2 실패도 남긴다 | `test_step2_body_failure_also_surfaces_the_reason` |
| **정상은 막지 않는다**(두 번째 모집단) | `test_success_path_is_not_reported_as_failure` |
| 「대상 없음」이 본문으로 안 샌다 | `test_no_match_envelope_is_not_mistaken_for_a_body` |

### 변이 — 기준선 rc=0 확인 후 · `__pycache__` 삭제

    M1 형제 Step1 가드 제거(원래 결함 되살리기)   CAUGHT
    M2 형제 Step2 가드 제거                       CAUGHT
    M3 expect 를 오류봉투 루트(`Response`)로       CAUGHT
    M4 본문 expect 를 느슨하게(`Law`)              CAUGHT
    ★M5 **무가드 XML 호출부를 새로 추가**          CAUGHT ← 파생형의 값어치

★**M1 은 「원래 결함이 살던 자리」에 넣은 변이**다 — 그것이 CAUGHT 여야 봉합의 증거가 된다.
