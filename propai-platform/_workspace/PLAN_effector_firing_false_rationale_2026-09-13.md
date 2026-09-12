# `effector_firing.py` 의 **거짓 근거** — 결론은 맞고 evidence 가 틀렸다

## §0. 옵시디언 조회 결과 (착수 전)

| 찾은 것 | 결과 |
|---|---|
| **이미 기각된 접근** | `2026-08-25_트래픽0인_스택이_프로덕션_임계를_바꾸고_있었다` — **임계 완화는 기각된 길**이다. 이 PR 의 핵심 위험이 정확히 그 재발이다 |
| **같은 클래스 앞선 결함** | `dev-tasks/2026-08-26_성장루프는_트래픽이_적을수록_눈이_먼다` — 결함①② 를 진단. ★**재서 보니 둘 다 낡았다**(아래 §1) |
| **미결·부채** | `effector_firing.py` 자신이 *"이 파일은 고치지 않는다 · 0건=결함 아님"* 을 선언. 이 PR 은 그 선언을 **지킨다**(0건을 결함으로 바꾸지 않는다) |
| **이전 판단의 근거** | 표의 `feature_toggle` 행이 **★진짜 발견**이라 적힌 근거 — 그 근거를 재서 **거짓**임을 확인 |

## §1. 전제 표 — **측정 방법과 실제 값**

| 전제 | 확인 방법 | 결과 |
|---|---|---|
| 생산처는 `down_pct > 20` 에서 발행한다 | `analyzer.py:459` + 상수 `:63` 원문 | `QUALITY_DOWN_PCT=20.0` · `severity="warn"` · **critical 분기 없음** |
| 소비처는 `down_pct >= 40` 을 요구한다 | `feature_flags.py:487` + 상수 `:83` | `FEATURE_DISABLE_ERROR_PCT=40.0` · `severity IN ('warn','critical')` · `ftotal+vtotal >= 10` |
| ★**두 임계가 모순인가** | 산수 | ✘ **아니다.** `> 20` 이 `>= 40` 을 **포함**한다 — `down_pct=45` 는 양쪽 통과 |
| ★표본 하한이 역방향으로 막나 | 두 상수 대조 | ✘ 생산 `>=5` · 소비 `>=10` — 소비가 **좁을 뿐** 도달 불가 아님(동료 sid=7af9eaa2 가 세운 적대 가설 · **기각**) |
| 생산처가 `quality_drop` 을 실제로 발행하나 | `analyzer.py:1083` | ✔ 발행한다 |
| 볼트 진단서(08-26) 결함② 자기정규화 | `analyzer.py` 원문 재측정 | ★**고쳐졌다** — `typical_p95(history)` 절대편차 축 신설 · `sev = ratio_sev or abs_sev` · `triggers` 기록 |
| 볼트 진단서(08-26) 결함① 폴백 하한 | 같은 파일 | ★**결함이 아니라 설계 결정** — `withheld_n` + `floor` = `judged_pct`↔`coverage_pct` 분리 |
| 라이브 치유 후보가 0인 이유 | `/growth/insights` 500건 실측 | `HANDLED_INSIGHT_TYPES=("fallback_rate","stale_reanalysis")` · `fallback_rate` 3건 **전부 비-open** · `stale_reanalysis` **0건** ⇒ **후보가 게이트에 도달조차 안 한다** |

## §2. 변경 내용과 회귀가 아닌 근거

1. **표의 evidence 문장 교체** — 「열」(`조건 미충족`)은 **맞으므로 그대로 둔다.** 거짓인 것은 설명뿐이다.
2. **낡는 파생값 제거** — `★66시간 휴면` 등 「휴면 N시간」 칸을 지우고 `await firing_status(db)` 로 대체.
   발화수·시각은 **기준(호스트·DB now·측정자)을 달아** 스냅샷으로 남긴다(불변 사실은 값이 정답).
3. `:235` 의 `66시간` 은 **역사적 근거**라 유지하고 **기준시각만 부여**한다(`# v2:` 변경이력과 같은 취급).
4. **새 락 1파일**(아래 §5).

**회귀 아님**: 런타임 코드 변경 **0줄**(주석·독스트링만) + 신규 테스트. 기존 `test_effector_firing_observability.py` **23 passed**.

## §3. ★검증하지 못한 것

- **`down_pct >= 40` 인 서비스가 실제로 없었는지**는 **미측정**이다(이유: **권한 차단** — 프로덕션 DB 읽기가 auto 모드 `Production Reads` 분류기에 막힌다. 허용 규칙 `settings.json:146` 은 **이미 있고** 그것으로도 막힌다).
  ⇒ 그래서 이 PR 은 *"데이터 조건이다"* 를 **코드 도달성**으로만 주장하고, *"그런 서비스가 없었다"* 는 **동료 관측으로 승계**한다(내 관측으로 적지 않는다).
- **산문 근거를 기계가 검증하지 못한다** — `xfail(strict=True)` 로 초록 안에 드러냈다.

## §4. 되돌리기 경로

`git revert <머지커밋>`. 런타임 0줄이라 되돌려도 동작 변화 없음.

## §5. 잠금 — `tests/test_feature_toggle_band_is_reachable.py`

| 락 | 무엇을 잠그나 |
|---|---|
| `test_consumer_accepts_every_severity_the_producer_can_emit` | ★**생산 severity ⊆ 소비 severity.** 생산은 `_classify_quality` 를 **태워서** 파생(소스 안 읽음), 소비는 **ast 로 실행 문자열만**(주석·독스트링 배제). 소비처를 `critical` 로 좁히면 **조용한 도달 불가** → 이 락이 빨개진다 |
| `test_the_down_pct_floor_actually_filters_two_populations` | **두 모집단** — 바닥 위는 후보가 되고 **중간대는 걸러진다**. 한쪽만 보면 「아무것도 안 하는 구현」과 구별 불가 |
| `test_producer_emits_the_insight_type_the_consumer_queries` | `quality_drop` 오타 잠금(생산↔소비 문자열 동일성) |
| `xfail(strict=True)` | ★**미잠금 부채를 초록 안에** — 표의 **산문 근거**가 코드와 어긋나는 것은 의미 판정이라 기계가 못 잡는다 |

★**공허 방지 선단언**을 각 락에 넣었다(생산 집합이 비면 실패 · 질의 문자열을 못 찾으면 실패).

---

## §6. 변이 검증 — ★**분모를 누가 골랐나: 기계는 하나도 고를 수 없었다**

손으로 고른 변이 셋(전부 **잠그려는 계약**을 겨눈다):

| 변이 | 뜻 | 판정 |
|---|---|---|
| 소비처 `severity IN ('warn','critical')` → `IN ('critical')` | **조용한 도달 불가** 만들기 | `::VERDICT=CAUGHT` |
| `FEATURE_DISABLE_ERROR_PCT` **40 → 20** | ★**거짓 근거가 지시하던 바로 그 처방** | `::VERDICT=CAUGHT` |
| 소비처 `quality_drop` → `quality_drpo` | 생산↔소비 문자열 절단 | `::VERDICT=CAUGHT` |

★★**그런데 「3/3 CAUGHT」를 그대로 인용하면 안 된다.** 기계 도구를 돌린 결과:

    python scripts/mutate_changed.py --tests tests/test_feature_toggle_band_is_reachable.py
      base: origin/main → 89fa2da46e32 (공통 조상 · 남의 커밋 제외)
      대상 파일 1개 · 변이 **0건**
      ★변이를 하나도 만들지 못했다 — 검증된 것이 **없다**(초록이 아니다).

**이 PR 의 런타임 변경이 주석뿐이라 기계의 분모가 비었다.** 그러므로 정직한 서술은
*"내가 N 을 골랐다"* 가 아니라 ***"기계는 단 하나도 고를 수 없었고, 커버리지 전부가 손 변이다"*** 이다.
그리고 그 손 변이는 **바뀐 파일이 아니라 락이 지키는 «안 바뀐» 파일**(`feature_flags.py`)을 겨눈다 —
기계는 원리적으로 거기에 도달하지 못한다(`.sh` 가 변이 모집단 밖이던 것과 같은 형태).
★도구가 **0건을 초록으로 읽지 못하게** 스스로 경고문을 내는 설계라 이 사실이 드러났다.

## §7. 회귀

파생 모집단(변경 3심볼을 참조하는 테스트) **13파일 · 205 passed · 2 xfailed · 실패 0**.
`ruff check .` 전체 통과(★`SIM300` 1건을 **커밋 전에** 적발 — #1042 는 바로 이 자리에서 CI 가 죽었다).

---

## §8. 독립 적대 리뷰 상환 (MAJOR 3 · MEDIUM 3 · MINOR 2 — REQUEST CHANGES)

### MAJOR-1 — 「3/3 CAUGHT」에 **대조군이 없었다.** 변이② 는 **이 PR 이전에 이미 잠겨 있었다**

형제 락을 **빼고** 다시 쟀다(내 새 락 제외):

| 변이 | 형제만 태웠을 때 | 판정 |
|---|---|---|
| ① `severity IN ('warn','critical')` → `IN ('critical')` | `SURVIVED` | **진짜 신규 커버리지** |
| ② `FEATURE_DISABLE_ERROR_PCT` 40 → 20 | ★`CAUGHT` | **내 기여 아님 — 이미 있었다** |
| ③ `quality_drop` → `quality_drpo` | `SURVIVED` | **진짜 신규 커버리지** |

⇒ 정직한 수치는 **3/3 이 아니라 2/3** 이다. §6 의 *"★거짓 근거가 지시하던 바로 그 처방"* 이라는
표현은 **내 락이 그것을 막는 것처럼** 읽히는데, 실제로 막고 있던 것은
`tests/test_l1_feature_toggle_closes_its_insight.py::test_the_gate_constants_are_pinned` 이다.
★그 형제의 독스트링은 **내가 「새로 발견」한 논지를 이미 적고 있었다**
(*"하한을 내리는 것이 언제나 가장 먼저 떠오르는 길이므로 그 길을 기계가 막는다"* + 같은 사고 인용).

★★**§0 의 사전조사 표가 이 형제를 한 줄도 언급하지 않았다** — §29 위반
(*"없는 것을 새로 만드는 것과 있는 것을 안 쓴 것은 처방이 다르다"*).
**근본원인**: 나는 `down_pct` 를 `app/services/growth` 로 **범위를 좁혀** 조회했고 **`tests/` 를 뺐다.**
⇒ 규율: ***락을 쓰기 전에, 그 락이 단언할 상수·심볼을 `tests/` 포함 전 범위로 먼저 조회한다.***

### MAJOR-2 — 내 두 모집단 테스트가 **소비처를 안 태우고 자기 재구현을 잠그고 있었다 → 삭제**

`_emits()` 가 게이트를 `(m.get("down_pct") or 0.0) >= floor` 로 **다시 구현**했다.
그래서 **진짜 게이트를 지워도 안 보였다**: `if down_pct >= … and (ftotal` → `if True and (ftotal`
⇒ 내 파일 `SURVIVED` / 형제 `CAUGHT`.
형제 `test_the_gate_decides_at_the_boundary` 는 **실물 `ff.evaluate()`** 를 4모집단 parametrize 로 태운다.
⇒ **내 것은 약체 중복이므로 지웠다.** (MINOR-1 의 `assert floor > QUALITY_DOWN_PCT` 상수-대-상수
단언도 함께 사라졌다 — `QUALITY_DOWN_PCT` 를 정당하게 40 이상으로 올리면 **위양성**이었다.)

### MAJOR-3 — 「미측정 · 권한 차단」이 **거짓**이었고, 재니 **답이 더 정확해졌다**

인증 붙은 **공개 엔드포인트 한 번**이면 됐다(프로덕션 DB 불필요):

    GET /api/v1/growth/insights?insight_type=quality_drop  → 4건
      전부 severity=warn · verify_total 38/25/29/29 · **feedback_total 0/0/0/0** · down_pct 0.0
      ⇒ 표본 축 ftotal+vtotal>=10 : **4/4 충족** ← 이미 통과
      ⇒ down_pct>=40              : **0/4**     ← 막는 건 이 축 하나
      ★대조군 fallback_rate → 30건(critical 포함) ⇒ 필터·조회기 생존

⇒ 내 1차 정정도 **두 축을 뭉뚱그려** 부정확했다. 정확히는 **피드백이 0행**이라
`enough_feedback=False` → `down_pct` 보류 → 소비처가 `None or 0.0` 으로 강등한다.
`feature_toggle` 은 **엄지내림 깔때기 뒤에 전부** 있고 그 깔때기가 **한 행도 만든 적이 없다**
(생산 경로 `routers/growth.py:758` 실재 ⇒ **장치 부재가 아니라 사건 미발생**).
★***「못 잰다」고 적기 전에 「이 축으로 잴 수 있나」를 물었어야 했다.*** 이 PR 의 주제가 **세 번째로 자기 자신에게 적용됐다.**

### MEDIUM-1 — `_sql_literals()` 가 **갖지 않은 면역을 주장**했다 → 참으로 만들었다

*"실행되는 문자열 상수"* 라 적고 **독스트링만** 걸렀다. 죽은 모듈 상수에 미끼를 넣으면 통과했다.
⇒ 이제 **`text()` 호출의 인자만** 본다. 재검증(리뷰어 프로브 재현):

    A 축소만                 종전 CAUGHT      | 수정 CAUGHT
    C 죽은 상수에 미끼        종전 ★SURVIVED   | 수정 **CAUGHT**
    ★대조군 원본 그대로       수정 accepted={'critical','warn'}  ⇒ 위양성 없음

### MEDIUM-2 — `_producible_severities()` 의 **전수 주장 철회**

15점 표본이다(`warn=0` 고정 · `fail ∈ {0, vtotal}`). `or`→`and` 는 CAUGHT 이나
**`>`→`>=` 는 SURVIVED**. ⇒ 독스트링에 **「생산 가능 집합의 하한이지 분기 전수가 아니다」**라고 적었다.

### MEDIUM-3 — 형제 스윕 누락(이 PR 자신의 결함 클래스) → 상환

형제 독스트링의 *"관측: 열린 quality_drop 4건 전부 down_pct=0.0"* 이 **기준(시각·주체·명령) 없이** 적혀 있었다.
오늘 재측정값으로 **스냅샷 기준을 달아** 고쳤다.

### MINOR-2 — `accepted` 토큰 하드코딩 → `severity IN (...)` 절에서 **파생**

### ★리뷰가 확인해 준 것(반증 실패)

핵심 논지(`>20 ⊇ >=40` · 경로 도달 가능 · `_classify_quality` 가 `warn` 만 발행 · 런타임 0줄)는
**전부 독립 재측정으로 확인**됐다. 발행 지점 1곳 · `UPDATE … SET severity` **0건** ·
`llm_narrative ∈ AUTO_TOGGLEABLE ∉ CRITICAL_FEATURES` 까지 태워 확인.

## §9. 리뷰 중 **동료가 찾은 더 큰 구멍** — `#1046` 계약에 반영

`.py` 판정에서 **docstring 을 「주석」으로 취급하면 위음성**이 난다.
동료(sid=7af9eaa2) 라이브 실측: **FastAPI 가 라우트 함수의 docstring 을 OpenAPI `description` 으로 서빙**한다
(`/openapi.json` **1,328,123 B** · 오퍼레이션 **1,041** 중 `description` 보유 **599**).
⇒ ***라우트 핸들러의 docstring 한 글자가 라이브 산출물을 바꾼다.*** 그리고 그 소비처는
저장소에 `__doc__` 이라고 **안 적혀 있다**(프레임워크가 읽는다) — `grep __doc__` 으로 **0건**이다.

**#1045 재판정(근거 교체 · 판정 동일)**: `effector_firing.py` 의 라우트 함수 수를 **AST 로 파생**했다 —
**0건**. 판정기 생존 대조군: `app/routers/growth.py` **12건** · `app/routers/land_price.py` **6건** ·
서비스 층 형제 `feature_flags.py`·`analyzer.py` **0건**. ⇒ **api 불요**(근거는 「docstring 미변경」이
아니라 「라우트 데코레이터 0건 ∧ `__doc__` 소비처 0건」).
