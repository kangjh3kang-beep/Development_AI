# 막힌 치유를 보이게 한다 — `heal_blocked` 조회 경로 신설

작성: development-ai-a4 · sid=7af9eaa2 · 2026-09-09
대상: `propai-platform/apps/api/app/routers/growth.py` (`GET /growth/heal-log`)

## 0. 옵시디언(볼트) 조회 결과

볼트 복구 후 실제 조회(대조군: C rc=0 · 볼트 rc=0 · md 25개).
**이 주제의 기록 없음** — 성장루프/치유 관련 문서가 볼트에 **없습니다**(적힌 6개는 다른 주제).
보드에는 있습니다: `HANDLED_INSIGHT_TYPES` 8건 · `mark_insight_acted` 5건 · `acted` 49건.
★**이미 기각된 접근**: 없음. ★**미결**: 독립 추적이 «게이트 차단 가설(H2)» 을 **못 닫았고**
그 사유가 *"`heal_blocked` 를 노출하는 API 가 없어 직접 조회 불가"* 였습니다 — 이 계획이 그것을 답합니다.

## 1. 전제 표 (측정 방법 · **실제 값**)

| # | 전제 | 방법 | 결과 |
|---|---|---|---|
| 1 | `heal_blocked` 가 실제로 발행된다 | `git grep` origin/main | `healing_rules.py:71`(상수) · `:291`(INSERT) ✔ |
| 2 | 그것을 읽는 경로가 없다 | 라우터 계수 | **0건** (★대조군 같은 파일 `heal-log` **6건** ⇒ 조회기 생존) |
| 3 | 저장 위치·형식 | 원문 | `platform_events(event_type='heal_blocked', payload={action_type, reason, params.trigger_key})` |
| 4 | 형제 엔드포인트가 같은 표를 읽는다 | 원문 | `/heal-log` 가 `event_type='heal_action'` 로 같은 표 조회 ✔ |
| 5 | ★내가 앞서 «진짜 결함» 이라 부른 **2시간 창 고아**는? | 라이브 + `insight_retention` 원문 | **결함 아님** — open 인 행들은 각 파티션의 **최신**이고, 승계는 별도 장치가 한다. **폐기** |

## 2. 변경 내용과 회귀가 아닌 근거

`HealBlockedOut` 모델 + `HealLogOut.blocked`/`blocked_total` **추가**(기본값 있음 → 옛 클라이언트 무영향).
`heal_blocked` 를 **별도 질의**로 읽고 기존 `action_type`·`since` 필터를 **같이** 건다.

★**`actions` 에 섞지 않는다.** 섞으면 기존 소비처의 「실행된 액션 수」가 조용히 부풀고,
이 저장소에는 «두 필드가 함께 부풀면 정합성 검사가 눈이 먼다» 는 실측 전례가 있다.
**회귀 아님**: `actions`·`total`·`active_flags` 의 질의와 의미가 그대로다(락이 그것을 단언한다).

## 3. ★검증하지 못한 것

- **라이브 DB 통합 미실행** — 락은 핸들러를 스텁 db 로 태운다. 실 Postgres 에서 `payload->>` 경로와
  인덱스 성능은 **미측정**. 형제 질의(`heal_action`)와 **동일한 형태**라는 것이 유일한 근거다.
- **실제 `heal_blocked` 행이 라이브에 있는지 미측정** — 조회 경로가 없어 못 봤다(그게 이 변경의 이유).
  배포 후에야 «0건인가 · 막히고 있었는가» 를 가를 수 있다. **이 PR 은 관측 장치이지 답이 아니다.**
- 프론트 소비처는 만들지 않았다(백엔드 표면만).

## 4. 되돌리기 경로

단일 라우터 파일 + 신규 테스트. `git revert <merge sha>`. 필드는 추가뿐이라 소비처 파손이 없다.

## 5. 잠금

`tests/test_heal_blocked_observable.py` (6건) — 핸들러를 **실물로** 태운다(사본 금지).
① 노출 ② **오염 축**(막힌 것이 `actions`·`total` 에 안 샌다) ③ 공허진리 가드(두 모집단이 다른 수)
④ 둘 다 0 일 때도 필드 존재 ⑤ 필터가 blocked 질의까지 도달 ⑥ **대조군** — 기존 질의가 blocked 를 안 긁는다
