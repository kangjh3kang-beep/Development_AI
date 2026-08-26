# PLAN — 종합 리스크 배지가 **「중간」을 초록(안전)으로** 칠한다

- 날짜: 2026-08-27
- 브랜치: `fix/risk-level-label-parity` · 워크트리 `Development_AI_risklabel`
- 베이스: `origin/main` = `5a79f510`

---

## 0. 옵시디언 조회 결과 (착수 전 · 계획 게이트 §0)

`obsidian-brain` query — 주제어: 표시계층 / 라벨 표 / enum 정합 / 영문 raw 노출.

| 찾을 것 | 결과 |
|---|---|
| **이미 기각된 접근** | **없음.** 이 결함(리스크 배지 색)에 대한 기각 기록 0건 |
| **같은 클래스의 앞선 결함** | ★**있다.** `AI-Sessions/wiki/errors/2026-08-24_라벨표가_11종을_7종으로_알고_있었다.md` — `GrowthDashboard` 의 `insight_type` 라벨표가 백엔드 11종을 7종으로 알고 있었고 **7종이 영문 raw** 로 떴다. 처방은 **카탈로그 SSOT + 양방향 락**(`app/services/growth/insight_types.py`). ★그 처방은 **그 한 표에만** 적용됐다 — 형제 표는 스윕되지 않았다 |
| **미결·부채** | 위 문서 「잔여 한계(명시)」: 신규 타입을 함수 안 bare `return "x"` 로만 만들면 방향① 스윕이 놓친다 |
| **이전 판단의 근거** | `agent-lessons.md:81` — ★**「라벨 맵의 정합성을 라벨 맵으로 검사하면 동어반복이다 — 라벨과 무관한 목적으로 유지되는 별개 자료구조를 오라클로 써라」**. 이 계획의 오라클 선택 근거다 |
| | `agent-lessons.md:577` — **전수 대조는 방향마다 엄격도가 다르다**(역방향을 엄격 패턴으로 하면 없는 유령을 만든다) |
| | `agent-lessons.md:576` — `type X = … \| (string & {})` 유니온은 **`tsc` 가 안 잡는다** |

★**신선도 재확인(실측)**: 위 문서가 인용한 `insight_types.py` 는 `origin/main` 에 **실재**한다.

---

## 1. 전제 표 — 각 전제의 *확인 방법* 과 *실제 측정값*

| # | 전제 | 확인 방법 | **실측 결과** |
|---|---|---|---|
| P1 | 백엔드 severity 사다리는 **5종** | `git show origin/main:…/protection_zone_severity.py \| sed -n '41p'` | `SEVERITY_ORDER = ("낮음","보통","중간","높음","극히 높음")` — **5종** |
| P2 | 프론트 `RISK_LEVEL_STYLE` 는 **4종** | 같은 방법으로 138~143행 | `낮음`·`보통`·`높음`·`극히 높음` — **4종. `중간` 없음** |
| P3 | `중간` 은 **실제로 산출된다**(유령 아님) | `grep -nE '"중간"' protection_zone_severity.py` | `49: ("제한보호구역", "중간")` — 군사기지법 제한보호구역 |
| P4 | 그 값이 **이 배지로 흐른다** | 생산자 원문 1808~1827행 + 소비 1386행 | 생산: `risk_level = max_severity(risk_level, sev)` → `return {"risk_level": risk_level}` / 소비: `RISK_LEVEL_STYLE[devPlans.risk_level as string] \|\| RISK_LEVEL_STYLE["낮음"]` |
| P5 | 폴백 `낮음` 이 **안전색**이다 | 138~143행 원문 | `"낮음": bg-[var(--status-success)]/20 text-[var(--status-success)]` — **success(초록)** |
| P6 | `제한보호구역` 이 **테스트/픽스처에 실재**한다 | `git grep -rl '제한보호구역' origin/main` | **7파일** — 그중 `tests/…/fixtures/landattr/dae__planning_mgmt__na/G1b_limited_protection_negotiable.json` |
| P7 | **기존 락이 없다** | `git grep -rln 'RISK_LEVEL_STYLE\|SEVERITY_ORDER' origin/main \| grep -E 'test'` | 히트 **1건**(`tests/test_dominant_constraint.py`) — 백엔드 전용. **프론트 표를 SSOT 에 결속하는 락 0건** |
| P8 | 이 저장소에 **정답 기준선이 있다** | `DesignChangePredictPanel.tsx` `severityMeta()` 원문 | `SEVERITY_META[key] ?? { label: key, cls: <중립 토큰> }` — **미지값을 중립색 + raw 라벨**로 표시. 안심시키지 않는다 |
| P9 | 대상 파일이 **미점유**다 | `scripts/coord.sh status` grep | `ComprehensiveAnalysisPanel` CLAIM 은 **2026-08-01·08-19·08-22** 뿐(전부 이력). 현재 활성 세션 4곳이 신고한 소유 파일에 없음 |

### 결함 요약 (관측)

**★라벨과 색이 서로 모순된다.** 배지 글자는 `종합 리스크 중간` 으로 **원값 그대로** 나가는데,
색은 폴백을 타서 **`낮음` 의 초록**이 된다. 사용자는 색을 먼저 읽고 글자를 나중에 읽으므로
*"낮음과 똑같이 칠해진다"* 보다 이쪽이 정확하고 **더 나쁘다** — 한 배지가 두 말을 한다.
(이 정확한 서술은 동료 세션(통합자)의 검토에서 왔다.)

★이것은 이 저장소가 이미 명문화한 규율의 위반이다 — 보드 `2026-08-20 #712` 기록:
> **모르는 값은 낮추지 않습니다** — `conflict === "접함"` **화이트리스트**입니다.
> `!== "포함"` 블랙리스트로 쓰면 **미지의 새 상태가 전부 "안전"으로 분류**됩니다.

여기서는 화이트리스트조차 아니고 **미지값의 기본이 최저 위험**이다.

---

## 2. 변경 내용과 **회귀가 아닌 근거**

1. `RISK_LEVEL_STYLE` 에 **`중간`** 추가(warning ↔ 높음 사이 색). — 기존 4키의 값은 **한 글자도 안 바꾼다** → 기존 4종의 표시는 바이트 동일.
2. 폴백을 `RISK_LEVEL_STYLE["낮음"]` → **중립 토큰**으로 교체. — `낮음` 자체는 여전히 초록. **바뀌는 것은 「표에 없는 값」의 표시뿐**이고, 그 집합은 현재 `중간` **하나**이며 1번이 그것을 표에 넣으므로 **오늘 렌더 결과가 달라지는 입력은 `중간` 뿐**이다.
3. 판정을 **순수 함수 `riskLevelStyle(level)` 로 분리**해 export. — 렌더 결과 동일(같은 표를 같은 키로 조회).

★**공용화**: 3번이 이 저장소 규율(*"공용 함수·표준 계약으로 추출"*)의 최소 형태다. 다만 **다른 컴포넌트로의 확산은 이 PR 범위 밖**이다(§3 참조).

---

## 3. ★검증하지 못한 것

- ~~라이브 표본 미측정~~ → **★해소됨(동료 세션 실측 · 2026-08-27).** 통합자 세션이 무과금
  (`include_interpretation:false`)으로 태워 **두 모집단을 갈랐다**:
  · 파주 문산읍 선유리 1 → `risk_level='중간'`(제한보호구역 전방지역 25km · UNE121)
  · 연천 전곡읍 전곡리 1 → `risk_level='중간'`(제한보호구역 UNE120)
  · **음성 대조군** 강화 강화읍 관청리 1 → `risk_level='낮음'`(제한보호구역 없음)
  → **0건이 아니므로 「잠재」로 강등할 근거가 없다.** ★이 측정은 **내가 한 것이 아니다** —
  출처를 밝혀 둔다(내 기여는 강등 조건을 미리 적어 무엇을 재면 되는지 좁힌 것까지다).
- **경쟁 생산자 가설 — 기각됨(동료 실측).** `project_pipeline.py:1377` 은 로컬 `interp_input`
  (키 2개·`risk_level` 없음), `:2748` 은 `state.stages["report"].data`,
  `risk_monitor`·`bid_analyzer`·`disaster_risk`·`lifecycle/risk` 는 전부 별도 응답 키다.
  도달 경로 확정: `:678 sec7=_research_dev_plans` → `:707 "development_plans": sec7`
  → 프론트 `result?.development_plans` → 배지.
- **다른 9곳의 「안심 폴백」 트리아지 미완.** 파생 수집으로 10곳을 찾았고 그중 5곳을 원문으로 판정했다:
  · `LEVEL_CHIP ?? low`(PreCheck) — **오탐.** 여기 `low` 는 위험도가 아니라 **신호 강도 약함**이고 색도 중립 회색이다
  · `LEVEL_COLOR ?? low`(ZoningSignalMap) — **오탐.** 위와 동일 의미
  · `APP_STYLE ?? "불가"` — **오탐.** 보수적 방향
  · `PRESALE_STATUS_COLORS ?? "미정"` — **오탐.** 정직한 방향
  · `CONFIDENCE_META ?? low` — **오탐.** 낮은 신뢰는 보수적 방향
  → **10곳 중 진짜는 현재까지 1건**(위양성 5·미판정 4). ★남은 4곳(`VERDICT_META ?? warn` · `SEVERITY_META ?? P2` · `RISK_LEVEL_STYLE` 외 2)은 **이 PR 에서 판정하지 않았다.**
- **`SEVERITY_META[finding.severity] ?? SEVERITY_META.P2`(FieldAuditNotice)** — `AuditSeverity` 가 `"P0"|"P1"|"P2"` **닫힌 유니온**이라 타입상 도달 불가지만, 네트워크 응답이 캐스팅되면 런타임 이탈이 가능하다. **백엔드 산출 집합을 재지 않았으므로 판정 보류.** P2 는 `holdValue: false` 라 이탈 시 **「사용 보류 권고」가 사라지는** 방향이므로 **후속 조사 대상**으로 남긴다.
- **수집 축의 한계.** 모집단을 `표[값] ?? 기본` **정규식**으로 팠다. 삼항(`x === "a" ? … : …`)·`switch`·`Map.get` 으로 쓴 표는 **안 잡힌다.** 즉 **10곳은 하한**이다.

---

## 4. 되돌리기 경로

단일 파일 3곳 + 신규 테스트 2개. `git revert <머지커밋>` 으로 완전 복구.
부분 되돌리기: `중간` 키만 지우면 P2 이전 상태(단, 그 순간 락 2개가 빨개진다 — 의도).

---

## 5. 잠금 — 이 변경을 지키는 검사

| 축 | 산출물 | 무엇을 잠그나 |
|---|---|---|
| **탐지(파생형)** | `propai-platform/apps/api/tests/test_risk_level_label_parity.py` | 파이썬 SSOT `SEVERITY_ORDER` 를 **파싱해** 프론트 표의 키 집합과 대조. 사다리에 값이 늘면 **자동으로** 표를 강제한다(목록을 테스트에 적지 않는다) |
| **특이도(역방향·느슨)** | 같은 파일 | 표에만 있고 SSOT 에 없는 **유령 키** 적발. ★볼트 §577 대로 **역방향은 느슨한 언급 검사**로 분리한다 |
| **판정(순수 함수)** | `propai-platform/apps/web/components/analysis/__tests__/RiskLevelStyle.test.tsx` | **두 모집단을 가른다** — 알려진 값은 각자 다른 색, **미지값은 `낮음` 과 달라야 한다** |
| **배선** | 같은 파일 | 컴포넌트가 실제로 `riskLevelStyle` 를 태우는지(렌더 경로) |

★**오라클 선택 근거**(볼트 §81): 정합성을 **라벨표 자신**으로 검사하면 동어반복이다.
여기서는 **`protection_zone_severity.py` 의 `SEVERITY_ORDER`** 를 오라클로 쓴다 —
그것은 **라벨과 무관한 목적**(리스크 사다리 비교 `severity_rank`)으로 유지되므로,
등급을 추가하려면 **반드시** 그 튜플을 건드려야 하고, 그러면 락이 표를 강제로 묻는다.

★**공허한 초록 방지**: 추출 실패는 **`ScannerDeadError`(RuntimeError)** 로 즉시 죽는다 —
`AssertionError`(진짜 위반)와 **다른 예외**다. 뭉치면 *"검사기가 죽었다"* 가 *"깨끗하다"* 로 읽힌다.

---

## 6. ★적대 검토에서 나온 보강 (insight-loop · 동료 세션 3곳)

자기승인을 피하려고 **살아 있는 다른 세션들에게 서로 다른 렌즈**를 배정했다. 결과:

| 렌즈 | 판정 | 조치 |
|---|---|---|
| ① 오라클이 동어반복인가 | **통과** — `SEVERITY_ORDER` 는 `severity_rank`·`max_severity`(순서 비교)로 유지된다. 판별 기준: *"표시를 전부 지워도 이 튜플이 필요한가?"* → 필요하다 | 없음 |
| ② 등급 추가가 SSOT 를 반드시 거치는가 | ★**진짜 구멍** — 거치지 **않는다.** `_ZONE_SEVERITY` 에 새 등급을 적으면 사다리를 안 건드리고 API 로 나가고, `severity_rank` 는 예외가 아니라 **`-1` 을 조용히** 돌려준다(실측). 그러면 **표 파리티 락의 전제 자체가 거짓**이 된다 | `test_every_grade_producer_stays_inside_the_ssot_ladder` 추가 — 생산지(`_ZONE_SEVERITY`·`_flight_safety_severity`) 리터럴을 ast 로 전수해 사다리 안인지 단언. 변이 M6 **CAUGHT** |
| ③ 추출 실패가 충분히 시끄러운가 | **절반** — `()` 를 돌려주면 부분집합 단언이 **공허한 참**이 되어 소비 테스트가 전부 초록이었다(실측 확인) | `ScannerDeadError` 로 즉시 죽인다. 변이 M7 **CAUGHT** |
| ④ 형제 스윕(자체) | ★**정답 기준선을 찾았다** — `DominantConstraintBanner.severityColor()` 는 **5등급을 전부** `switch` 로 처리하고 default 가 **중립**(`--text-hint`)이다. 같은 저장소 안에 옳은 패턴이 이미 있었고, 배지 표만 뒤처져 있었다 | 배너는 무변경(이미 옳음). ★내 파생 수집이 그것을 **놓친 이유**가 §3 에 선언한 한계(`switch` 는 안 잡힘) 그대로였다 |

★**부수 발견(미조치)**: `project_pipeline.py:2731~2748` 에 **다른 3종 사다리**
(`낮음/보통/높음`)가 있다. `development_plans` 로는 안 흐르지만, 그것을 표시하는 표가
5종 사다리용으로 만들어져 있으면 **같은 클래스**다. **이 PR 범위 밖 — 재지 않았다.**
