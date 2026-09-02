# 효과기 발화 관측 — 계획서 (2026-08-27)

> **한 문장**: `effector_reach` 는 「어디까지 닿는가」를 선언하는데
> **「언제 마지막으로 닿았는가」는 코드·화면 어디에도 없었다.**

---

## 0. 옵시디언 조회 결과 (계획 게이트 §0)

주제어 `effector_reach · 효과기 발화 · 발화한 적 없 · heal_actions 0건`.

| 찾을 것 | 결과 |
|---|---|
| 이미 기각된 접근 | **없음** |
| 같은 클래스의 앞선 결함 | **있음** — `feedback_a_safety_net_that_never_fired_is_not_a_safety_net`: *"존재 ≠ 발화 — 소비처 0 의 **거울상 = 생산 0**"*. **이 작업의 설계 원칙이 그것이다** |
| 미결·부채 | `2026-08-25_모세혈관은_배선이_아니라_표면의_문제였다` — 같은 계열(배선은 됐는데 표면이 없다) |
| 이전 판단의 근거 | `2026-08-25_조회기가_여섯_번_다른_질문에_답했다` — 측정 매체를 먼저 확인하라 |

★대조군: 같은 방법으로 `성장루프` 조회 시 **105파일** — 조회기 생존.

---

## 1. 전제 표 — 확인 방법과 **실측값**

| # | 전제 | 확인 방법 | 결과(실측) |
|---|---|---|---|
| P1 | 효과기 선언 표가 있다 | `effector_reach.py` 원문 | `EFFECTORS` 7종 · `reach` ∈ {PRODUCT, SELF, NONE} |
| P2 | 제품에 닿는 효과기 수 | 같은 파일 | **1종**(`threshold_relax`)뿐 |
| P3 | ★발화 이력이 어디 사는가 | `heal_actions.py:5` · `feature_flags._emit_l1_event` | **둘 다** `platform_events(event_type='heal_action')` — L0·L1 **같은 매체** |
| P4 | ★그 매체가 L1 도 담는가 | 라이브: `threshold_autotune`(L1) **441건** | **담는다.** 이것이 **양성 대조군**이다 |
| P5 | 실제 발화 현황 | 라이브 `/growth/heal-log?action_type=…&limit=1` 의 `total` | 아래 표 |
| P6 | 조회기 생존 | 대조군 `action_type=zzz_nope` | `total=0` — **판별력 있음** |
| P7 | 발화를 보는 표면·검사가 있나 | `git grep 'last_fired|fired_at|never_fired'` 전수 | **0건**(대조군: `analysis_coverage` 는 실재) |
| P8 | 같은 주제를 다른 세션이 잡았나 | 보드 살아 있는 claim 310건 조회 | `healer-fetches-only-handled-types`(b8) — **다른 층**(그쪽은 후보 굶주림 메커니즘) |

### P5 실측 (2026-08-27 12:33 UTC)

| 효과기 | 선언 reach | 총 발화 | 최신 | 경과 |
|---|---|---|---|---|
| `threshold_relax` | **PRODUCT** | 47 | 08-24T18:50 | **66h** |
| `threshold_autotune` | SELF | 441 | 08-06T23:46 | **493h** |
| `circuit_observe` | NONE | 30 | 07-24T11:55 | 817h |
| `cache_warm` | NONE | 2 | 08-03T18:30 | 570h |
| `feature_toggle` | SELF | **0** | ★**한 번도 없음** | — |
| `stale_reanalysis` | NONE | **0** | ★**한 번도 없음** | — |
| `prompt_ab_adopt` | NONE | **0** | ★**한 번도 없음** | — |

---

## 2. 변경 내용과 회귀가 아닌 근거

| 파일 | 역할 | 회귀 아님의 근거 |
|---|---|---|
| `app/services/growth/effector_firing.py` (신규) | 선언 × 실측 조인 | 신규. 기존 경로 미변경 |
| `app/routers/growth.py` **추가** `GET /growth/effectors` | 관리자 전용 조회 | 순수 추가. 기존 라우트 불변 |
| `apps/web GrowthDashboard` **탭 추가** | 화면 소비처 | 기존 두 탭의 분기 조건 불변(`insights`/`heal` 동등비교) |

★**진단하지 판정하지 않는다.** `reach=NONE` 인 효과기가 영원히 발화하지 않는 것이
정상일 수 있다. 사실과 판단 근거를 주고 판단은 사람이 한다 — `effector_reach` 가
도달범위에 대해 그렇게 하듯이.

★**임계를 관측에 맞추지 않았다.** 촉발 관측이 66시간인데 `DORMANT_HOURS=72` 라
그 사례는 `active` 로 분류된다. 66 아래로 내리면 그 하나는 잡히지만 **다음 관측에서
또 내려야 한다**(굿하트). 대신 `product_reaching_max_hours_since` 라는 **임계 없는
사실**을 요약에 실었고, 락이 *"66h → active 이지만 원값은 보인다"* 를 명시적으로 잠근다.

---

## 3. ★검증하지 못한 것

1. **라이브 라우트 미호출** — `/growth/effectors` 는 배포 전이라 실호출을 못 했다.
   설계 근거인 발화 수치는 **기존 `/growth/heal-log` 로 실측**했으므로 데이터는 확증됐지만,
   **새 라우트의 응답 형태는 단위 테스트로만** 검증했다.
2. **`DORMANT_HOURS=72` 의 적정성 미측정** — 운영 판단이지 측정이 아니다(코드에 그렇게 적었다).
   효과기마다 자연 주기가 다르므로 임계 하나로 옳게 가를 수 없다.
3. **왜 발화하지 않는지 미규명** — 이 PR 의 범위가 아니다. 원인 중 하나(후보 굶주림)는
   `development-ai-b8` 이 `healer-fetches-only-handled-types` 로 별도 진행 중이다.
4. **`platform_events` 보존기간 미확인** — `total` 이 전체 이력인지 보존창 이내인지 안 쟀다.
   따라서 *"한 번도 없음"* 은 **보존창 안에서** 0건이라는 뜻이다. 표현을 그렇게 좁혀야 한다.
5. **프론트 e2e 미실행** — jsdom 단위 테스트만.

---

## 4. 되돌리기 경로

PR revert. 신규 파일 2개 + 순수 추가 라우트 1개 + 대시보드 탭 1개.
기존 동작 경로를 건드리지 않으므로 되돌려도 종전과 동일하다.

---

## 5. 잠금

| # | 무엇을 | 검사 |
|---|---|---|
| L1 | **파생형** — 선언 표 전수, **0건도 행으로** | `test_every_declared_effector_appears_even_with_zero_firings` |
| L2 | 세 상태가 **서로 다른 값** | `test_three_states_split` · `test_never_fired_is_not_dormant` |
| L3 | **양방향** — 표에 없는데 이벤트에 있는 액션 | `test_undeclared_action_surfaces_the_other_direction` |
| L4 | 경계를 **양방향**으로 | `test_dormant_boundary_is_inclusive_both_ways` |
| L5 | 라벨과 **원값** 동시 | `test_hours_since_is_always_present_when_fired` · `test_declared_and_measured_sit_in_the_same_row` |
| L6 | **L0·L1 같은 매체** | `test_query_reads_the_medium_that_both_layers_write` |
| L7 | 선언≠실제를 **구별** | `test_product_reaching_active_differs_from_declared`(두 모집단) |
| L8 | 임계의 성격이 코드에 | `test_dormant_threshold_is_documented_as_a_judgment_not_a_measurement` |
| L9 | **라벨 정합**(프론트 ↔ 파이썬 원본) | `EffectorFiring.test.tsx` 양방향 |

**변이 6/6 CAUGHT** — 0건 버리기 · never/dormant 뭉개기 · 양방향 제거 ·
경계 한쪽만 · product_active 를 declared 와 동일화 · 원값 제거.
