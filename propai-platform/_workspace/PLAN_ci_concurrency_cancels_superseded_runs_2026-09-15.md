# CI 가 **덮인 실행을 끝까지 돌고 있었다** — 8일에 980분

> 2026-09-15 · sid=7af9eaa2(통합자) · 정본 `origin/main = c9427bf13`
> 사용자 요청: *"최적화안으로 권고안을 수립해 진행하고 검증까지"*.

## §0 옵시디언·보드 조회 결과

| 찾을 것 | 결과 |
|---|---|
| **이미 기각된 접근** | ★**있다.** 보드 16343 / `#1029`(sid=dcb7a4f2)가 **배포 워크플로**에서 `cancel-in-progress` 를 **의도적으로 기각**했다. 사유: *«cancel-in-progress 가 `waiting`(승인대기)을 취소하는지 **미검증**»* — 그래서 트리거 정의(`on: push` 제거)만으로 성립하는 축으로 바꿨다 |
| **같은 클래스의 앞선 결함** | 볼트 `2026-09-10_자동배포가_20일째_죽어_있었고_승인은_롤백이었다.md` — concurrency 그룹이 **점유되면 그룹 전체가 막힌다**(`cancel-in-progress:false` + waiting 실행이 20일 점유) |
| **미결·부채** | `deploy-cloudflare.yml:30` 에 *«되살리기 전에 cancel-in-progress 가 waiting 을 취소하는지 먼저 재라»* 가 **주석으로 남아 있다** |
| **이전 판단의 근거** | 위 기각 사유는 **여전히 유효**하다. 이 계획은 그 미측정 축 **위에 올라타지 않고**, 그 축이 **발생하지 않는 대상**을 고른다 |

★**따라서 이 변경은 `deploy-cloudflare.yml` 을 건드리지 않는다.** 대상은 `ci.yml` 뿐이다.

## §1 전제 표 — **전부 실측** (2026-09-15T00:3x~00:5xZ · `gh api actions/runs` 600건 페이징)

| # | 전제 | 확인 방법 | 결과 |
|---|---|---|---|
| 1 | 덮인 실행이 실제로 많다 | 브랜치별 정렬 후 `다음 실행 시작 < 이전 실행 종료` | ✔ **CI(PR) 236회 3,595분 중 980분(27.3%)** · 8일 창 · 하루 122분 |
| 2 | 그 실행들이 취소되고 있나 | `conclusion` 전수 | ✘ **취소 0건**(success 258 · failure 21 · 진행 4) ⇒ **전부 완주** |
| 3 | 원인이 concurrency 부재인가 | 워크플로 5개 전수 `^concurrency:` | ✔ `ci.yml` **0** · 대조군 `deploy-cloudflare.yml` **1** ⇒ 조회기 생존 |
| 4 | ★주축이 update-branch 인가 | head 커밋 메시지로 두 축 분류 | ✘ **반증** — 저자푸시 **54회 819분** vs update-branch **10회 160분**. 종전 권고 ①은 **16%만** 겨냥했다 |
| 5 | ★main 푸시까지 취소하면 손실이 있나 | CI(push) 47건 인접 겹침 | ✔ **1건(2.2%)** — 드물지만 **회복 불가**(그 커밋의 초록 기록) ⇒ 가드 필요 |
| 6 | ★#1029 의 미측정 축이 여기서도 생기나 | `ci.yml` 의 `environment:` 선언 | ✘ **0건**(대조군: `deploy-cloudflare.yml:158` 실재) ⇒ 승인 게이트 없음 ⇒ `waiting` 불가 |
| 7 | 필수 체크가 이 워크플로 안인가 | 브랜치보호 contexts 파생 | ✔ 5개 중 4개가 `ci.yml` 잡 · 1개(`Deliberation Engine`)는 `deliberation-ci.yml` |
| 8 | 경합이 있나 | 열린 PR 9건의 파일 목록 | ✔ **`.github` 를 건드리는 PR 0건** |

★**전제 6 은 「상태 계수」가 아니라 「정의」로 갈랐다.** `waiting` 상태가 전 저장소 0건이라
상태만 세면 *「게이트가 없다」* 와 *「이 창에 안 잡혔다」* 가 구별되지 않는다.

## §2 변경 내용과 회귀가 아닌 근거

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

| 왜 이 형태인가 | 근거 |
|---|---|
| 그룹에 **PR 식별자** | `github.workflow` 만 쓰면 모든 PR 이 한 그룹 — 새 PR 이 **남의 실행을 취소**한다(멀티세션 저장소라 즉시 사고) |
| 취소를 **PR 에만** | 전제 5. push/dispatch 는 `github.ref` 로 그룹이 갈리고 `cancel-in-progress` 가 `false` 로 떨어져 **종전과 동일 동작** |
| **회귀가 아닌 근거** | 잡·스텝·필수 체크 이름 **무변경**(런타임 델타 0). PR 의 최종 상태는 같다 — 마지막 실행이 판정하고, 낡은 실행은 어차피 쓰이지 않았다 |

## §3 ★검증하지 못한 것

- **효과의 사후 실측 미완**: 머지 후 이 워크플로에서 `cancelled` 가 실제로 발생하는지는
  **머지 전에는 원리적으로 잴 수 없다**(이 저장소의 CI 정의를 바꿔야 발생한다).
  ⇒ 머지 후 `conclusion=cancelled > 0` 을 확인하는 것이 **본판정**이고, 그전까지는 **미측정**이다.
- **`Deliberation Engine (pytest)`** 은 `deliberation-ci.yml` 소속이라 이 변경의 **범위 밖**이다.
  그 워크플로도 concurrency 0 이지만 **실행량을 안 쟀다** — 별건.
- **취소가 필수 체크를 `cancelled` 로 남겨 PR 이 잠깐 막히는 시간**을 안 쟀다. 새 실행이
  즉시 시작되므로 순증은 아니라고 **추정**하나(반증 조건: 러너 대기열이 길면 늘어난다) 미측정.
- 종전 권고 ①(«update-branch 는 머지 직전에 한 번»)의 **효과**: 채택 후 표본이 **2건**뿐이라
  ***0% 라는 값은 근거가 아니다***. 이 PR 은 ①을 폐기하지 않고 **부차 축으로 강등**한다.

## §4 되돌리기 경로

`git revert <머지커밋>` 한 번. 런타임 델타 0(워크플로 + 테스트 + 계획서) — **배포 주기 불필요**.
되돌리면 concurrency 선언이 사라져 **종전과 정확히 같은 동작**(덮여도 완주)으로 돌아간다.

## §5 잠금 — `propai-platform/tests/test_ci_concurrency_cancels_only_pull_requests.py`

★**리터럴을 잠그지 않는다**(문자열을 박으면 리팩토링에 부서지고, 부서진 락은 지워진다).
판정을 `_classify()` **한 곳**에 두고 **속성**을 잠근다.

| 락 | 무엇을 막나 |
|---|---|
| `test_classifier_separates_every_failure_mode` | ★**판정기 자신** — 8모집단이 서로 다른 라벨(선언없음/형식오류/그룹공유/취소안함/무조건취소/조건불명/적합). 이 표가 죽으면 본판정은 무엇으로 재도 초록이다 |
| `test_classifier_labels_are_all_distinct` | 한 신호가 두 사건을 덮는 것(«없음»과 «틀림»이 같은 라벨) |
| `test_ci_cancels_superseded_pull_request_runs_only` | **본판정** — 그룹 공유 · 무조건 취소 · 효과 0 을 전부 잡는다 |
| `test_ci_has_no_approval_gate_so_no_run_ever_waits` | ★**처방의 전제를 같은 파일에서 잠근다.** `environment:` 가 생기면 #1029 의 미측정 축이 되살아나므로 **이 락이 먼저 빨개진다** |
| `test_required_checks_are_all_jobs_in_this_workflow` | 필수 체크가 이 워크플로 밖으로 나가면 «취소가 체크에 닿는다» 가정이 깨진다 |

★변이로 CAUGHT 를 확인하고 `scripts/mutate_manual.sh` 의 `::VERDICT=` 출력을 §6 에 싣는다.

## §6 변이 결과 — **4/4 CAUGHT, 그리고 기계는 0건을 골랐다**

`scripts/mutate_manual.sh` (base `c9427bf13`):

| 변이 | 무엇을 흉내내나 | `::VERDICT=` |
|---|---|---|
| M1 `cancel-in-progress: true` | main 푸시 기준선까지 취소 | **CAUGHT** |
| M2 `group: ${{ github.workflow }}` | 모든 PR 이 한 그룹 — 남의 실행 취소 | **CAUGHT** |
| M3 `cancel-in-progress: false` | 선언만 있고 효과 0 | **CAUGHT** |
| M4 잡에 `environment:` 추가 | 처방의 **전제** 파괴(승인 게이트) | **CAUGHT** |

★★**그런데 그 4개는 내가 골랐다.** 기계 변이는 **하나도 고를 수 없었다**:

    $ python scripts/mutate_changed.py --tests propai-platform/tests/test_ci_concurrency…py
      base: origin/main → c9427bf13423 (공통 조상 · 남의 커밋 제외)
      ★감사할 소스 변경이 없다 — 이 실행은 **아무것도 검증하지 않았다**.

원인은 확장자 게이트다 — `mutate_changed.py` 는 `(".py", ".ts", ".tsx", ".sh")` 만 본다.
***이 PR 의 런타임 산출물은 `.yml` 이라 기계 감사 분모에 아예 없다.***
즉 이 변경의 커버리지를 만든 것은 **손 변이와 리뷰뿐**이다. 「4/4 CAUGHT」를 머지 보증으로
읽지 말 것 — 그 분모를 정한 것이 나다.

★같은 결함 클래스가 지금 큐에 있다: **#1055** 가 `.sh` 를 그 분모에 넣는 PR 이고,
그것도 `.yml` 까지는 넓히지 않는다. **별건으로 남긴다**(처방 범위를 결함 범위에 맞춘다 —
여기서 `.yml` 지원을 끼워 넣으면 이 PR 이 두 가지를 하게 된다).

## §7 이 계획이 스스로 썩지 않게

★§5 가 선언한 락 5개가 **실제 테스트로 존재하는지** PR 에서 확인한다(이 저장소에
*「계획서 §5 의 락 이름 5개가 실재하지 않았다」* 는 실측 기록이 있다).
★그리고 §3 의 **본판정(머지 후 `cancelled > 0`)** 은 산문이라 잊힌다 — 보드에 후속 관측으로 남긴다.
