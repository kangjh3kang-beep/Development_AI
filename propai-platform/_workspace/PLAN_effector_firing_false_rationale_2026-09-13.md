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
