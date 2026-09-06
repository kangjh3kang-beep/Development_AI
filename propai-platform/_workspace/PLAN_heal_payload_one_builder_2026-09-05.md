# `heal_action` payload 를 **만드는 코드**가 둘이라 한쪽만 고쳐졌다 (2026-09-05)

> **작성: `development-ai-c8` · sid=0a08a179 · 2026-09-05 · 절대형 서명**
> 선행: `#995`(무동작이 진짜 문제를 닫던 것) — 그 PR 의 **3차 적대 리뷰가 이 결함을 지목**했다.

## 0. 옵시디언·저장소 조회 결과 (★«없음» 아님)

| 찾을 것 | 결과 |
|---|---|
| **이미 기각된 접근** | 없음 |
| ★**같은 클래스의 앞선 결함** | ★**있다. 그리고 저장소가 이 자리를 정확히 경고하고 있었다.** `effector_firing.py` — *"발화 기록이 사는 곳 — L0(`heal_actions`)·L1(`feature_flags._emit_l1_event`) **공통**. 한쪽만 보면 **절반을 놓친다**."* · `feature_flags.py` — *"★공용 헬퍼를 **재사용**한다. **복제하면 한쪽만 고쳐지는 형제가 또 생긴다**."* |
| **미결·부채** | `#995` 가 남긴 부채 1번(리뷰가 준 우선순위) |
| **이전 판단의 근거** | 볼트 `feedback_one_marker_two_layers` — *"공용화는 「함수」가 아니라 **「입력을 만드는 코드」까지**"* |

★**경고는 산문이라 발화하지 않았다.** 이 PR 은 그 산문을 **락으로** 바꾼다.

## 1. 전제 표 — 전부 실측 (2026-09-05)

| # | 전제 | 확인 방법 | **결과** |
|---|---|---|---|
| 1 | `heal_action` 생산자 수 | ★**AST 파생**(INSERT 문 상수에 `'heal_action'` 이 있는 파일) | **2곳** — `heal_actions._emit_heal_event` · `feature_flags._emit_l1_event` |
| 2 | 두 번째 생산자의 규모 | 라이브 `platform_events` 집계 | ★**441행 / 524행 = 84.2%**(`threshold_autotune`) |
| 3 | `#995` 가 그 형제에 도달했나 | 라이브 payload 키 조회 | ★**도달 못 했다** — `executed` 키 보유 **0행** |
| 4 | 판정값이 emit **앞에** 있나 | 호출부 8곳 원문 | ★**전부 있다**(`ok`·`inserted`·`triggered`·`cleared`) — 배선이 단순하다 |
| 5 | 순환 임포트 위험 | `heal_actions` 모듈 레벨 임포트 | **없다** — 성장 모듈 임포트 **0건**(leaf). `feature_flags` 가 안전하게 임포트 가능 |
| 6 | ★`healing_rules` 도 생산자인가 | 첫 조회기가 그렇게 신고 | ★**아니다 — 내 조회기의 위양성**. 그 파일은 `heal_action` 을 **WHERE 절로만** 쓰고 INSERT 하는 것은 **`heal_blocked`**(다른 타입)다 |

★**6번이 이 계획서에서 가장 값진 줄이다.** 손목록으로 «생산자 2곳» 이라 썼으면 그냥 지나갔을
것을, **파생형 조회기가 3곳이라 신고**했고 그것을 **다시 재서** 위양성임을 갈랐다.
그리고 그 과정에서 조회기를 «파일에 낱말이 있는가» → **«INSERT 문 그 자체에 있는가»** 로
정밀화했다. ***파생형으로 바꾸는 것과, 그 파생의 축이 맞는 것은 다른 일이다.***

## 2. 변경 내용

1. `heal_actions.build_heal_payload(...)` — payload 의 **정본**을 함수 하나로 추출.
2. `_emit_heal_event`(L0) 와 `_emit_l1_event`(L1) 이 **둘 다 그것을 쓴다**(복제 제거).
3. `executed` 를 **호출부 8곳 전부**에 배선:
   `threshold_relax`→`ok` · `cache_warm`→`triggered` · `stale_reanalysis`→`inserted` ·
   `circuit_observe`→`True`(+`no_op_reason="observe_only_by_design"`) · `rollback`→`cleared` ·
   L1 3곳(`threshold_autotune`·`feature_toggle`·`prompt_ab_adopt`)→`ok`.
   ★`circuit_observe` 는 «관측을 기록했다»가 참이므로 `True` 가 맞다 — 다만 «조치했다»로
   오독되지 않게 **사유를 함께** 싣는다(리뷰가 의미 불일치로 지적한 자리).

**회귀가 아닌 근거**: payload 는 **키가 늘 뿐**이고(기존 소비자는 여분 키를 무시),
임계·트리거·주기·캡·SQL 문·`ON CONFLICT` 는 **무변경**이다.

## 3. ★검증하지 못한 것

- **과거 행은 고치지 않는다** — 이미 쌓인 524행은 `executed` 가 없다. `null` 은 앞으로
  **「이 필드가 없던 시기」로 좁혀지지만**, 그 경계 시각을 응답이 말해 주지는 않는다.
- **`apps/web` 은 여전히 두 필드를 렌더하지 않는다**(`#995` 리뷰의 부채 2번). 화면에서는
  아직 구별되지 않는다 — ★이 PR 도 그것을 고치지 않는다.
- **라이브 확증 미측정**(미배포). 배포 후 축: `/growth/heal-log` 에서 **새 행**의
  `executed` 가 `null` 이 아닌지. ★**기존 행의 null 비율 감소로 확증하지 마라** — 과거 행은
  안 고치므로 비율은 천천히만 움직인다.

## 4. 되돌리기

단일 커밋 revert. SQL·임계·트리거 무변경.

## 5. 잠금 — ★3차 적대 리뷰가 **이 PR 의 존재 이유가 무잠금**임을 실증했다

| 지키는 것 | 무엇이 지키나 | 리뷰 前 |
|---|---|---|
| **L1 이 `executed` 를 버리는 것**(라이브 84.2% 생산자) | `_emit_l1_event` 를 **실제로 호출**해 INSERT 파라미터 payload JSON 의 **값** 단언 · 세 모집단 | ★**무잠금**(되돌려도 전부 초록) |
| **payload 를 손조립하는 것** | `payload` 에 **대입되는 표현식**이 빌더 호출인지(`ast.Dict` 만 보면 `dict()`·`{}`+대입·`.copy()` 로 샌다) | ★**무잠금**(양쪽 생산자) |
| **호출부가 `executed=None` 인 것** | 키워드 **값 표현식**까지(`Constant(None)` 금지 · `True` 는 진짜 판정이라 허용) | ★**무잠금**(이름만) |
| **빌더가 다른 키를 버리는 것** | 8키 **전부** + **키 집합 고정** + 키마다 «반대 입력이 반대 값» | ★1키만 |
| **생산자가 넘기는 것이 죽는 것** | L1 의 `trigger_key`(가드가 세는 축) · `rollback` 의 `setting_key` | ★**무잠금** |
| **모집단이 함께 깎이는 것** | ★emit 호출부 **하한**(L0≥5 · L1≥3) — 호출을 지우면 파생 단언이 **공허하게 참** | ★**무잠금** |
| **사유가 무동작에만 붙는 것** | `executed=True` 호출이 `no_op_reason` 을 안 넘기는지(AST) | — |
| **바인드형 생산자를 침묵시키는 것** | 강제 불가 모집단을 **세어 고정** — 늘면 빨개진다 | ★**안 보였다** |

★**조회기 축을 세 번 고쳤다**: ①낱말 존재(→`healing_rules` 위양성) ②최상위만(→하위·타 패키지) ③리터럴만(→**바인드 파라미터 INSERT 를 원리적으로 못 봄**). ③이 결정적이다.

## 6. 변이

### ★기계 변이도구 (`scripts/mutate_changed.py` — 저장소가 의무화)

    1차(리뷰 시점)   생존 23건
    2차(1차 반영 후)  생존  9건 — 전부 빌더의 남은 키
    3차(최종)        ★**생존 0** — "추가한 줄이 전부 테스트에 걸린다"

★**손수 고른 변이만으로는 여기까지 못 왔다** — 9건은 전부 «내가 잠갔다고 생각한 층의 옆»이었다.

### 손수 고른 변이 (리뷰가 뚫었던 것 재판정)

| 변이 | 리뷰 시점 | **지금** |
|---|---|---|
| L1 이 `executed` 를 버림(**존재 이유**) | ★SURVIVED | ★**CAUGHT** |
| L0·L1 이 `dict()` 로 손조립 | ★SURVIVED ×2 | ★**CAUGHT** ×2 |
| L1 호출부가 `executed=None` | ★SURVIVED | ★**CAUGHT** |
| 빌더가 `params`/`rollbackable`/`actor` 를 버림 | ★SURVIVED ×2 | ★**CAUGHT** ×3 |
| ★**위양성**: `rollback()` 이 저장 payload 를 **읽는** 자리 | — | **SURVIVED**(정상) |
| ★**위양성**: `circuit_observe` 의 `executed=True` | — | **SURVIVED**(정상) |
| ★음성 대조군: 무해한 로거 문구 | SURVIVED | **SURVIVED**(정상) |

★**반영하다 내 락이 정상 코드를 세 번 막았다** — 위 둘, 그리고 **내 주석**이 부분문자열 단언에
걸린 것(**오늘 세 번째 같은 형태**). 셋 다 **파서로 바꾸고 축을 좁혀** 해소했다. ***위양성도 결함이다.***

## 7. 회귀 대조 (★분리 기준선)

    기준선  merge-base **40835276** 분리 트리   494 passed · deselected 11417
    브랜치                                       518 passed · deselected 11417   → Δ +24 정확
실패 집합 **이름까지 동일** → **회귀 0**.
★**재현 명령**(산문은 여러 구현을 허용한다 — 3차 리뷰어가 내 수치를 재현하지 못했다):

    git worktree add --detach /tmp/base996 $(git merge-base origin/main HEAD)
    <venv>/bin/python -m pytest propai-platform/apps/api/tests -k "heal or growth or feature" -q

## 8. ★이 PR 이 만든 것이 아닌, 그러나 이 PR 이 드러낸 것

`routers/growth.py` 의 `_ALLOWED_TYPES` 에 **`heal_action`** 이 있고 `POST /growth/events` 는
**익명 허용**이며 클라이언트 `payload` 가 그대로 컬럼에 들어간다. `_guard_counts` 는
`payload->>'action_type'` 을 **actor 필터 없이** 세므로 **자가치유 캡을 채워 봉쇄**할 수 있다.
★**실해 0건**(라이브 524행 전부 `actor=growth_engine · surface=worker`) · **별도 티켓**.
★이 PR 의 락은 그 바인드형 모집단을 **세어 고정**해 침묵시키지 않는다.
