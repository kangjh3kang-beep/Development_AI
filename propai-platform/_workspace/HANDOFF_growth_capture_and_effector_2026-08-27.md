# 인계서 — 성장루프 관측·수집 (2026-08-27 세션 development-ai-0b)

> **읽는 순서**: §1 지금 당장 할 것 → §2 살아 있는 작업 → §3 ★이 세션이 데인 것 →
> §4 미해결 부채. **§3 을 건너뛰지 마라** — 같은 자리에서 세 번 데였다.

★**모든 값은 재측정하라.** 아래는 2026-08-27 23시대(KST) 실측이고 PR 상태·배포는 분 단위로 썩는다.
각 항목에 **재측정 명령**을 함께 적었다.

---

## 1. 지금 당장 할 것

### 1-1. ★`#921` 이 먼저 착지해야 한다 (순서가 중요)

`#918`(적산 PR)이 **선언 범위 밖의 성장루프 파일을 함께 지웠다** — 실측:

```
effector_firing.py                          -71줄
test_effector_firing_observability.py      -253줄
PLAN_effector_firing_review_followup…md     -91줄
```

`#921` 이 그 복원이다. **auto-merge 를 켰다**(2026-08-27 23:2x). 재측정:

```bash
gh pr view 921 --json state,mergeStateStatus,autoMergeRequest
git show origin/main:propai-platform/apps/api/app/services/growth/effector_firing.py | grep -c TELEMETRY_SINCE
#   → 0 이면 아직 복원 안 됨 · 1 이상이면 복원됨
```

### 1-2. `#920` 은 `#921` **뒤에** 처리한다

`#920`(수집 유실)은 현재 **DIRTY**(충돌 3곳)다. 원인은 `#918` 이 지운 파일을 이 브랜치가
만지기 때문이다. **`#921` 이 착지한 뒤 main 을 머지**해야 복원분을 안 덮어쓴다.

```bash
cd /home/kangjh3kang/My_Projects/Development_AI_capture
git fetch origin && git merge origin/main      # ★rebase 아님 — 남의 것을 되돌리지 않게
# 충돌은 effector_firing.py 의 응답 키 자리다. **양쪽 키를 둘 다 살려라**:
#   telemetry_since (#917) · capture (#920) — 서로 다른 사실을 나른다
```

### 1-3. 큐가 좌초해 있다 (동료 세션 development-ai-8b 실측)

열린 PR 21건이 **전부 4/4 pass** 인데 멈춰 있다. `auto=false` 8건 · `BEHIND` 다수.
strict 보호라 **BEHIND 면 스스로 머지하지 않는다.**

```bash
gh pr merge <N> --auto --squash
gh api -X PUT repos/kangjh3kang-beep/Development_AI/pulls/<N>/update-branch
```
★**한 번에 하나만.** 동시에 밀면 CI(약 12분)와 커밋 간격이 겹쳐 서로를 무효화한다.

---

## 2. 살아 있는 작업

| PR | 무엇 | 상태(재측정 필요) |
|---|---|---|
| **#921** | `#918` 이 지운 `#917` 봉합분 복원 | auto=ON · **최우선** |
| **#920** | 성장루프 **입력** 유실(되돌리고 센다) | **DIRTY** · `#921` 뒤 |
| #882·#892·#895·#899·#904·#908 | 앞선 6건 | 4/4 pass · BEHIND |

머지 완료: `#915`(효과기 발화 관측) · `#917`(그 리뷰 봉합) — ★단 §3-2 참조.

**라이브 확증**(2026-08-27 23:1x · `GET /api/v1/growth/effectors` 200):

```
선언 7종 · 발화중 0 · 휴면 4 · 한번도없음 3
★제품에 닿는 효과기 0/1 발화중 · 최장침묵 76.5h
threshold_relax  product  47건  76.5h  dormant   ← 72h 임계를 넘어 dormant 로 전환됨
threshold_autotune self  441건 503.5h  dormant
feature_toggle / stale_reanalysis / prompt_ab_adopt  0건  never_fired
```

★**셋의 `never_fired` 는 뜻이 다르다** — 같은 줄에 적지 마라:
`feature_toggle`=조건 미충족(진짜 발견) · `stale_reanalysis`=**자기참조**(건강한 시스템의 사실) ·
`prompt_ab_adopt`=**구조적 도달 불가**(부트스트랩 교착).

---

## 3. ★이 세션이 데인 것 — 같은 자리를 다시 밟지 마라

### 3-1. auto-merge 를 켠 뒤 적대 리뷰를 돌리면 **경주가 되고, 진다**

`#915` 는 리뷰 REJECT 봉합 커밋보다 **38초 먼저** 머지됐다(13:03:27 vs 13:04:05 UTC).
**결함본이 main 에 들어갔고** `#917` 로 따로 수습해야 했다.

→ **리뷰가 끝난 뒤에 auto-merge 를 켜라**, 또는 그때까지 draft. `#920` 에서 실제로 그렇게 해
   반복되지 않았다.
★기존 교훈 *"초록 게이트는 스스로 머지하지 않는다"* 의 **정반대 방향**이다. 둘은 짝이다.

### 3-2. ★그리고 그 수습(`#917`)마저 `#918` 이 지웠다

`telemetry_since` 가 **main 에 없다**(실측 0건). 배포 API 는 `#917` 머지커밋을 포함하는데도
응답에 그 키가 없어서 판별됐다 — **배포는 됐는데 코드가 없다**가 아니라
**그 사이 다른 PR 이 지웠다**였다.
→ **「배포됐나」와 「코드가 있나」를 따로 물어라.** 응답 키로 재는 것이 가장 강했다.

### 3-3. `N/N CAUGHT` 는 **참이면서 무의미**할 수 있다

`#915` 에서 변이 6/6 CAUGHT 를 근거로 완결 선언했는데, 독립 리뷰가 **25중 20 생존**을 보였다.
여섯이 전부 **한 함수 층 안**이었고 라우터·SQL·렌더에는 **0개**였다.

→ **완결 선언 전에 「몇 개 층에 넣었나」를 표로 적어라**:
   순수함수 · 배선/호출부 · 라우터/권한 · 질의(SQL) · 응답계약 · 렌더.
   `#920` 은 그 표를 테스트 독스트링에 적고 7개 층에 넣었다(그러고도 리뷰가 7건을 더 찾았다).

### 3-4. `mutate_changed.py` 의 **「생존 0」은 「잠겼다」가 아니다**

이유 둘:
- 그 도구 기본 base 가 `origin/main` 이라 **브랜치가 뒤처지면 남의 PR 파일까지 변이한다**
  → 그 수치는 **기준 커밋과 함께**여야 의미가 있다(실측: 47종 생존0 → 재실행 60종 생존6)
- ★카탈로그(줄삭제·문자열변경)가 **상수값·파일간 결합 변이를 못 만든다**
  → 리뷰가 손으로 찾은 상수 3종이 정확히 거기서 나왔다

**기계 도구는 사람이 못 보는 층을 잡고, 사람은 도구가 못 만드는 변이를 만든다. 둘 다 돌려라.**

### 3-5. `except Exception` 은 `CancelledError` 를 **못 잡는다**

`BaseException` 전용이다(실측). 종료 시 `task.cancel()` 을 await 없이 걸면
`_drain` 이 이미 빼낸 배치가 **무계수로 사라진다**.
★그 PR 의 제목이 *"조용히 사라지던 것"* 이었다 — **고치려던 결함이 수리 안에서 재현**됐다.

### 3-6. 내가 쓴 주석 **셋이 거짓**이었다

*"일시적 장애에서는 한 건도 잃지 않는다"*(65초 넘으면 잃는다) ·
*"프론트가 그리는 값이라 지우면 undefined"*(14키 중 6키를 프론트가 안 읽는다) ·
*"오래된 것부터 밀려난다"*(되돌리기는 **가장 새것**을 밀어낸다).
셋 다 리뷰가 반증했다. **주석에 쓴 근거도 검증 대상이다.**

### 3-7. 단언 없는 `replace` 는 **조용히 아무것도 안 한다**

앵커 공백이 달라 실패했는데 `grep` 으로 확인하기 전까지 성공한 줄 알았다.
**항상 `assert s.count(anchor) == 1` 을 붙여라.**

---

## 4. 미해결 부채 (착수 권함/안 함을 구분해 적는다)

| # | 내용 | 판단 |
|---|---|---|
| D1 | `requeued` 가 **행이 아니라 연산**을 센다(500행×12회=6000) — 화면의 「되돌림 200건」을 200개 행으로 읽으면 틀린다 | **착수 권함**(작다) |
| D2 | 동시성 — `_consecutive_failures` 가 전역이라 flusher 가 둘이면 **상한 미발화·FIFO 역전**. ★정상 상태 도달 불가(`uvicorn --workers 1`)이나 **Redis 공유큐 전환 시 즉시 실재** | 전환 시 필수 |
| D3 | 설계문서 §231 의 **90일 롤업/prune 이 미구현**(대조군: 참조 패턴 `prune_old_versions` 는 실재). 구현되면 `never_fired` 판정이 **조용히 뒤집힌다** | 문서에 NOT IMPLEMENTED 표기 권함 |
| D4 | arq 워커에 flush 루프 **0건**. 워커 임포트 19모듈 중 `record_event` 호출 0건이라 **직접 경로에는 없다** — ★**전이 임포트는 안 쟀다** | 재측정 권함 |
| D5 | `flush-growth-events` celery beat 잡이 **문서상 no-op**(프로세스 로컬 큐라 워커에서 안 보임) | 현상 유지(코드가 그렇게 적어 둠) |
| D6 | `#915` 시절 부채: `never_fired` 가 **세 상황을 구별 못 함**(§2 참조). 판별을 코드에 넣지 않았다 — **그 분석이 낡기 때문** | 의도적 미착수 |

---

## 5. 재측정 명령 모음 (값을 승계하지 마라)

```bash
# PR 상태 + 필수체크(파생)
REQ=$(gh api repos/kangjh3kang-beep/Development_AI/branches/main/protection --jq '.required_status_checks.contexts[]')
gh pr checks <N> | awk -F'\t' -v req="$REQ" 'BEGIN{split(req,a,"\n");for(i in a)R[a[i]]=1} R[$1]{print $1": "$2}'
# ★Cloudflare Pages·Workers Builds 는 상시 FAILURE 이고 **필수가 아니다** — 세지 마라

# 성장루프 라이브(★sort=created_at 명시 · 0건이면 재로그인부터)
TOK=$(curl -s -X POST https://api.4t8t.net/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@4t8t.net","password":"admin1234"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
curl -s -H "Authorization: Bearer $TOK" https://api.4t8t.net/api/v1/growth/effectors
curl -s -H "Authorization: Bearer $TOK" 'https://api.4t8t.net/api/v1/growth/heal-log?limit=1'

# 배포 판정 — ★브랜치 sha 가 아니라 **머지커밋**으로
MC=$(gh pr view <N> --json mergeCommit --jq '.mergeCommit.oid')
git merge-base --is-ancestor "$MC" origin/main && echo 포함
# ★그리고 「머지됐다 ≠ 코드가 있다」 — 응답 키로 재라(§3-2)

# 테스트(★venv 파이썬 · python3 로 부르면 시스템 3.10 이 잡혀 임포트가 깨진다)
V=/home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/api/.venv/bin/python
cd propai-platform/apps/api && "$V" -m pytest tests/test_growth_capture_no_silent_loss.py -q
"$V" -m ruff check .            # ★CI 는 전수다 — 변경 모듈만 돌리면 놓친다

# 프론트(★CI 잡 이름이 "type-check + **lint** + test" 다)
cd propai-platform/apps/web && pnpm install   # 워크트리마다 1회
npx tsc --noEmit -p tsconfig.json
pnpm lint --format json -o /tmp/e.json && python3 scripts/ci/lint_ratchet.py /tmp/e.json propai-platform/apps/web/lint-ratchet.json
```

## 6. 좌표

- 워크트리: `Development_AI_capture`(#920) · `Development_AI_effectorfix`(#917) · `Development_AI_effector`(#915)
- 계획서: `_workspace/PLAN_growth_capture_no_silent_loss_2026-08-27.md` ·
  `_workspace/PLAN_effector_firing_observability_2026-08-27.md` ·
  `_workspace/PLAN_effector_firing_review_followup_2026-08-27.md`
- 볼트: `AI-Sessions/wiki/errors/2026-08-27_적대리뷰를_automerge_켠_뒤에_돌리면_경주가_된다.md` ·
  `…/2026-08-27_N대N_CAUGHT_는_참이지만_무의미할_수_있다.md`

★**이 인계서에 「그 세션에 물어보라」는 없다.** 근거와 좌표를 본문에 적었다 — 세션은 사라지지만
파일·PR·볼트는 남는다.
