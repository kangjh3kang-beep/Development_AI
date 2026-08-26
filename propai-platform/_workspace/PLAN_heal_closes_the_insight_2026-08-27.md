# PLAN — 자가치유가 **인사이트를 닫지 않는다**(피드백 고리의 마지막 한 줄)

- 날짜: 2026-08-27 · 브랜치 `fix/heal-closes-the-insight` · 베이스 `origin/main` = `0efda714`

## 0. 옵시디언 조회 결과

| 찾을 것 | 결과 |
|---|---|
| 이미 기각된 접근 | **없음** |
| 같은 클래스의 앞선 결함 | `agent-lessons:571` — *"「수집한다」와 「본다」는 다른 일이다"*. 이 건은 그 **행동판**: **조치하고도 기록하지 않는다** |
| 미결·부채 | `#880`(승계 정리)이 `superseded` 만 다루고 **`acted` 미접촉** — 계획서에 명시돼 있음 |
| 이전 판단의 근거 | 규율 §D-19 *"경계를 걸면 양방향으로"* — 이 변경의 (B) 근거 |

## 1. 전제 표 — *확인 방법* 과 **실측값**

| # | 전제 | 방법 | **결과** |
|---|---|---|---|
| P1 | 자가치유가 **실제로 돈다** | 라이브 `/growth/heal-log` | **520건** · 최신 `2026-08-24T18:50` · `threshold_relax` / `threshold_autotune` |
| P2 | 액션이 **대상 인사이트를 안다** | 로그 원문 | `params.insight_id` = `2e86008f-…` · `trigger_key` = `fallback_rate:site_analysis` |
| P3 | `acted` 를 **쓰는 코드가 없다** | 파생 전수 | `_INSIGHT_STATUSES` **정의 1곳뿐** · 쓰기 **0건** |
| P4 | 라이브 `acted` | API | **0건**(대조군 `fallback_rate open` **21** 로 조회기 생존) |
| P5 | 프론트 라벨은 **있다** | 소스 | `acted: "조치됨"` 실재 |
| P6 | ★안전망(`heal_escalation`)이 **발화한 적 없다** | 라이브 전 상태 | **0/0/0/0** — 520건이 쌓이는 동안 **한 건도 없음**(음성 대조군 `zzz_not_a_type`=0 으로 판별력 확인) |
| P7 | `threshold_relax` 는 **PRODUCT 에 닿는다** | 통합자 실측 인용 | `heal_actions` → `base_client` 에서 **실 HTTP 타임아웃을 곱함**(유일한 PRODUCT 이펙터) |
| P8 | `#880` 과 **겹치지 않는다** | PR diff | `superseded` 만 추가 · `acted` 미접촉 |
| P9 | 영역 **미점유** | 보드 | 관련 CLAIM 0건 |

## 2. 변경과 회귀가 아닌 근거

1. **단일 길목에서 닫는다** — `healing_rules:342`(성공 판정 직후) 한 곳. `heal_actions.execute` 는 **반환 지점이 다섯**이라 그 안에 붙이면 반드시 하나를 빠뜨린다.
2. **`open` 만 닫는다** — 사람이 이미 판단한 `acknowledged`·`dismissed` 는 안 건드린다.
3. **best-effort** — 닫기 실패가 치유 태스크를 죽이지 않는다(치유는 이미 일어났다).
4. **`acted → dismissed` 한 방향만** 연다 — `acted → open` 도 `dismissed → *` 도 여전히 막힌다.

★**제품 판단은 단독으로 하지 않았다.** (A) 종단 / (B) 탈출구 중 통합자가 **(B)** 를 골랐고, 근거는 **P6**(안전망이 실측 0건)이다. 내가 (A) 를 선호했던 이유가 라이브에서 거짓이었다.

## 3. ★검증하지 못한 것

- **라이브에서 `acted` 가 실제로 찍히는지 못 봤다.** heal 은 `fallback_rate` 인사이트가 있어야 발화하는데 그것이 **하한 미달로 08-24 이후 0건**이다 → 배포해도 **당분간 발화 안 할 수 있다.** 배포 확증은 그 점을 감안해야 한다.
- **`heal_escalation` 이 왜 0건인지 안 쟀다** — 임계 미달일 수도, 배선 결함일 수도. **별건**이고 미측정이다.
- `growth_pr_task` 는 `metrics_json.pr_status` 만 merge 하고 **status 컬럼을 안 바꾼다**(`improvement_proposal` 53건). **이 PR 범위 밖.**
- 스텁 기반 단위검증이라 **실제 SQL 이 Postgres 에서 도는 것**은 CI 통합 테스트에 맡긴다.
- ★`tests/integration/test_growth_loop_e2e.py::test_growth_loop_and_determinism` 은 **기준선에서도 실패**한다(내 변경 없는 브랜치 `61bf2a0a` 에서 동일 `assert v.get("verified") is True`). **내 회귀가 아니고, 고치지도 않았다.**

## 4. 되돌리기

`git revert <머지커밋>`. 부분: `allowed_from` 분기만 지우면 전이 가드는 종전과 동일.

## 5. 잠금 — 변이 5종 전부 CAUGHT

| 축 | 변이 | 결과 |
|---|---|---|
| 배선 | M1 호출 제거(헬퍼는 유지) | CAUGHT |
| 계약 | M2 `status='open'` 조건 제거 | CAUGHT |
| 두 모집단 | M3 미실행도 닫게 | CAUGHT |
| ③ 탈출구 | M4 `acted→dismissed` 재차단 | CAUGHT |
| ★④ 과열림 | M5 **전면 개방** | CAUGHT |

★④가 없으면 *"가드를 다 열어 버린"* 구현도 ③으로 초록이다(통합자 제안).
