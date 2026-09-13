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
| `test_consumer_accepts_every_severity_the_producer_can_emit` | ★**생산 severity ⊆ 소비 severity.** 생산은 `_classify_quality` 를 **태워서** 파생(소스 안 읽음), 소비는 **`text()` 인자만**(★종전 「ast 로 실행 문자열만」은 §10 MEDIUM-1 이 **철회한 문구**인데 §5 에 남아 있었다 — R3 MEDIUM-E). 소비처를 `critical` 로 좁히면 **조용한 도달 불가** → 이 락이 빨개진다 |
| ~~`test_the_down_pct_floor_actually_filters_two_populations`~~ | ★**R1 MAJOR-2 로 삭제**(§8) — 게이트를 **재구현**해 진짜 게이트를 `if True` 로 바꿔도 SURVIVED 였다. 그 축은 형제 `test_l1_...::test_the_gate_decides_at_the_boundary` 가 **실물 `ff.evaluate()`** 로 잠근다 |
| `test_producer_emits_the_insight_type_the_consumer_queries` | ★**생산 배선** 잠금 — 「동일성」이 아니라 **일방 포함 + 살아 있는 호출부**(R3 MEDIUM-B/MINOR-3 정정). 다른 **생산되는** 타입으로 바꿔치기는 **못 잡는다**(의미 판정) |
| `test_the_candidate_window_is_pinned_against_loosening` | ★**결정적 축**(`timedelta(hours=6)`)을 느슨해지는 방향으로 핀 — AST 리터럴 핀이라 **런타임 0줄** 유지(R3 MAJOR-3) |
| `xfail(strict=True)` | ★**미잠금 부채를 초록 안에** — 표의 **산문 근거**가 코드와 어긋나는 것은 의미 판정이라 기계가 못 잡는다 |

★**공허 방지 선단언**을 각 락에 넣었다(생산 집합이 비면 실패 · 질의 문자열을 못 찾으면 실패).

---

## §6. 변이 검증 — ★**분모를 누가 골랐나: 기계는 하나도 고를 수 없었다**

손으로 고른 변이 셋(전부 **잠그려는 계약**을 겨눈다):

| 변이 | 뜻 | 판정 |
|---|---|---|
| 소비처 `severity IN ('warn','critical')` → `IN ('critical')` | **조용한 도달 불가** 만들기 | `::VERDICT=CAUGHT` |
| `FEATURE_DISABLE_ERROR_PCT` **40 → 20** | ★거짓 근거가 지시하던 그 처방 | `CAUGHT` — ★**그러나 내 기여 아님**. 형제만 태운 대조군에서도 `CAUGHT`(§8 MAJOR-1). **이 PR 의 신규 커버리지는 2/3** |
| 소비처 `quality_drop` → `quality_drpo` | 생산↔소비 문자열 절단 | `::VERDICT=CAUGHT` |

★★**이 표를 「3/3」으로 인용하면 안 된다 — 실제 신규는 2/3 이다**(위 표 ② 참조 · 근거는 §8 MAJOR-1 의 대조군).
그리고 기계 도구를 돌린 결과:

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

파생 모집단 — ★**값이 아니라 명령**으로 적는다:

    grep -rlE "_classify_quality|quality_drop|effector_firing|firing_status" tests/

결과(head `60a06de40` 이후 · R2 상환 반영): **15파일 · 204 passed · 1 xfailed · 실패 0**.
★종전엔 *"13파일 · 205 passed · 2 xfailed"* 라고 **명령 없이** 적어 재현이 안 됐다(R2 MINOR-2).
숫자 차이의 원인은 **내가 쓴 파생 축이 달랐던 것**이다 — 그래서 명령을 박는다.
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

---

## §10. R2 적대 리뷰 상환 (MAJOR 4 · MEDIUM 2 · MINOR 3 — REQUEST CHANGES)

★R2 는 **핵심 논지를 전부 독립 재확인**했다(`>20 ⊇ >=40` · 도달 가능 · `warn` 단독 발행 ·
`UPDATE … SET severity` 0건 · 런타임 0줄). 지적은 전부 **락과 그 락을 정당화한 근거**에 대한 것이다.

| 지적 | 상환 | 재검증 |
|---|---|---|
| **MAJOR-A** §5 가 삭제된 락을 선언 | §5 행을 취소선+사유로 교체 | `git grep` 유일 히트가 계획서였다 → 해소 |
| **MAJOR-B** 오타 락이 **존재 검사**라 생산처 파괴가 SURVIVED | 발행 dict 의 `insight_type` 값을 **AST 로 파생**해 소비 파싱값과 `⊇` 대조 | 생산 리터럴 변이 **SURVIVED → CAUGHT** |
| **MAJOR-C** 독스트링의 「실측」이 재현 불가 + 한계 오진 | *"15점 표본"* 철회 → **구조적 한계**로 교체(severity 대입이 **`_classify_quality` 안에서** 유일이라 술어 변이는 원리적으로 `⊆{"warn"}` 를 못 벗어난다 — ★R3 MEDIUM-C 로 **범위 정정**: 모듈 전체로는 **8곳**이고 `:1005` 는 `'critical'` 을 낸다) + **그 축은 형제가 잡는다**고 명시 | — |
| **MAJOR-D** 「막는 건 `down_pct` 하나」가 거짓 | 세 표면 전부 정정 | 아래 실측 |
| **MEDIUM-A** `accepted` 합집합이 제2 `text()` 로 뭉개짐 | 게이트 질의를 **유일 특정**(`quality_drop` ∧ `status='open'`) + `len==1` 단언 | 살아 있는 미끼 **SURVIVED → CAUGHT** · ★위양성 대조군(미끼만) **SURVIVED** 유지 |
| **MEDIUM-B** 「보류→None→강등」 기제가 측정행과 모순 | 추론/측정을 갈라 적음(그 4행은 **보류 도입 이전 생산자** 산출) | — |
| **MINOR 1·2** §6 「3/3」· §7 명령 부재 | 제자리 정정 + 파생 명령 명기 | — |
| **MINOR 3** 선재 무기준 주장 5곳 | ★**이 PR 범위 밖**(전부 선재)이라 손대지 않고 **좌표만 남긴다**: `analyzer.py:654·725·1153` · `healing_rules.py:208·229` | — |

### ★MAJOR-D 실측 — 게이트는 **네 술어의 곱**이다

    [라이브 2026-09-13 · insight_type 필터 · total=4=len(items) **비절단**]
    ftotal+vtotal>=10   **4/4 통과**
    status='open'       **2/4**
    created_at>=now-6h  **0/4**   ← ★이 축 하나가 전부를 떨어뜨린다(나이 461~479h ≈ 19~20일)
    down_pct>=40        **0/4**

⇒ ***`down_pct` 를 100 으로 만들어도 게이트는 0행이다.*** 더 상위 사실은
**`quality_drop` 이 약 19일째 생산되지 않았다**는 것이다.
★***두 축을 갈라 놓고 질의문의 나머지 두 축을 뭉뚱그렸다*** — 이 PR 이 고치러 온 그 형태를
**상환문 안에서** 재발시켰다. R1 MAJOR-3 정정(1차)→2차→**3차**로 세 번 고쳤다.

### ★남는 한계(정직 표기)

- ~~`hours=6` 창 축 미잠금(미측정 · 내 락 축 아님)~~ → ★**라벨이 틀렸다**(R3 MAJOR-3): 같은 커밋이 그 축을 **0/4 로 측정**하고 **결정적 축으로 승격**시켜 놓고 «내 축 아님»이라 적었다 — **잠글 수 있는데 안 잠근 것**이었다. ⇒ 신설 락으로 **CAUGHT**.
- ~~`status='open'` 축은 형제가 잡는다~~ → ★**틀린 귀속**(R3 MINOR-1): 새 파일만 태워도 `CAUGHT` 다. ***겸양이라도 틀린 귀속은 다음 사람의 커버리지 지도를 망친다.***

---

## §11. R3 상환 (MAJOR 3 · MEDIUM 5 · MINOR 3 — 델타만 공격 · REQUEST CHANGES)

★R3 는 **논지를 재검증하지 않았다**(두 번 확인됐으므로). 표적은 `9a03497a8..7fd5a1787` 델타였고,
**세 MAJOR 가 전부 R2 상환에서 새로 쓴 코드**에 있었다. **세 라운드 연속 같은 자리다.**

| 지적 | 상환 | 재검증 |
|---|---|---|
| **MAJOR-1** 수집기가 **여전히 존재 검사** — 생산자 **호출부**를 지워도 초록 | `_producer_of()` + `_producer_functions_with_live_call_sites()` 로 **배선**을 단언 | 호출부 삭제 **SURVIVED → CAUGHT** · ★위양성 대조군(무관 주석) **SURVIVED** |
| **MAJOR-2** 수집기가 `Call` 발행을 못 봐 **거짓 메시지**를 낼 수 있었다 | 「발행 안 함」과 **「판정 불가」**를 분리 — 파생 불가 발행식이 있으면 **단정하지 않는다** | 파생 집합에 `latency_*` 부재 ↔ 라이브 438/49건(최신 0.0h·5.6h) |
| **MAJOR-3** 결정적 축 `hours=6` 이 **느슨해지는 방향 무잠금** | `test_the_candidate_window_is_pinned_against_loosening` 신설(**AST 리터럴 핀** — 런타임 0줄 유지) | `hours=600` **SURVIVED → CAUGHT** |
| **MEDIUM-A** 두 락이 게이트를 **다른 축**으로 골랐다 | `_gate_sql()` 로 **한 곳 통일** | — |
| **MEDIUM-B/MINOR-3** 「동일성」이 아니라 **일방 포함** | §5 표기 정정 + 락 독스트링에 **못 잡는 것** 명시 | — |
| **MEDIUM-C** 새 전제가 **과대 범위**(`analyzer.py` → 실제 8곳, `'critical'` 포함) | 범위를 **`_classify_quality` 안**으로 좁힘 | — |
| **MEDIUM-D** 「19일째 생산 정지」가 고유 현상처럼 읽힘 | **형제 축 실측**을 함께 적음(latency 최신 **0.0h** — 배치는 돈다) | — |
| **MEDIUM-E** §5 1행이 **철회된 문구**를 싣고 있었다 | 교체 | — |
| **MINOR-1** 「형제가 잡는다」가 **틀린 귀속** | 취소선 + 정정 | 새 파일만으로 **CAUGHT** |

### ★상환 중에 **또 결함을 만들었고, 기계가 잡았다**

`test_producer_…` 를 다시 쓰면서 **파일 끝의 `xfail` 부채 표식을 통째로 지웠다.**
드러난 경로 둘: ①테스트 수가 `2 passed·1 xfailed` → **`3 passed`** 로 바뀐 것
②`ruff` 의 **`F401 pytest imported but unused`**.
⇒ **테스트 이름 집합을 차집합으로 대조**해 확인하고 복원했다(사라진 것 **0건**).
★***순증이 순삭제를 덮는다*** — 이 저장소의 기록된 실패 형태이고, 이번엔 **두 기계 신호**가 잡았다.

### ★R3 가 재현해 준 것(저자 보고 검증 — 전부 일치)

라이브 4축 수치 한 자리도 안 틀림(`total`↔`len(items)` 비절단 · 역대조군 `zzz_nope`=0 ·
정대조군 `fallback_rate`=30) · `_sql_literals()` 의 `text()` 좁히기는 **실제 면역** ·
삭제한 약체 중복의 **잔재 0건** · 「3/3→2/3」 자진 정정.
