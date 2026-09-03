# 인계서 — 통합자 레인 (2026-09-03)

★**이 문서의 모든 상태 값은 낡았다고 가정하라.** 각 항목에 **재측정 명령**을 붙였다.
오늘 여러 세션이 값을 서로 전달하다 잘못된 판단으로 갈 뻔했다(한 세션은 몇 시간 낡은 배포
목록으로 배포를 요청했고, 나는 중간 상태에서 만든 프로브로 최종 상태를 재려 했다).

★**「그 세션에 물어보라」고 쓰지 않는다** — 근거와 좌표를 본문에 적는다.

---

## 0. 먼저 돌릴 것 (3분)

```bash
git fetch origin main -q

# ① 배포 잔여 — ★캐시명은 줄시작 앵커 필수
SW=$(curl -s https://4t8t.net/sw.js | grep -m1 '^const CACHE_NAME' \
     | grep -oE 'propai-v[0-9]+-[0-9a-f]+' | grep -oE '[0-9a-f]+$')
git rev-list --count "$SW"..origin/main -- propai-platform/apps/web

# ★api 는 컨테이너 이름을 고정하지 말고 caddy 에서 파생 (오늘 8000↔8001 로 바뀌었다)
ssh -i ~/.oci.key ubuntu@168.110.125.89 \
 'P=$(grep -vE "^[[:space:]]*#" $HOME/caddy/Caddyfile \
      | grep -oE "reverse_proxy[[:space:]]+localhost:80[0-9]+" | grep -oE "80[0-9]+" | sort -u)
  [ $(echo "$P" | wc -l) -ne 1 ] && { echo "★포트 여러 개 — 판정 거부"; exit 1; }
  sudo docker exec propai-api-$P python -c \
    "from app.services.growth import stale_build_guard as g; print(g.running_build_id())"'

# ② 큐
gh pr list --state open --limit 40 --json number,title,mergeStateStatus,autoMergeRequest
scripts/coord.sh status | tail -20
```

**쓸 때의 값(2026-09-03 · 참고만)**: api `50054773` 잔여 0 · web `6c6270bb` 잔여 0 ·
열린 PR 6건.

---

## 1. 즉시 이어받을 일

| PR | 상태(당시) | 무엇 | 다음 행동 |
|---|---|---|---|
| **`#955`** | BEHIND · AM=off | 관리자 과금 화면이 **요율 5개를 못 바꿨다**(셋은 실제 돈) | `update-branch` → 초록 → 머지 → **158 web 배포** |
| **`#953`** | AM=off | 무주인 부채 문서 | 초록이면 머지(문서 전용) |
| `#954` | 다른 세션(23) 소유 | 사통맵 선택 필지 토글 | **손대지 않는다** |
| `#939` | **내 것** · 리뷰 대기 | 계기판 유휴↔사망 | 독립 리뷰 후 |
| `#243` `#218` | 2026-07 | 문서 PR | 필수 체크가 완료되지 않는 상태 |

★**`AM=off` 는 「작성자가 통제를 유지한다」는 뜻이다.** 배수 대상이 아니다.
예외를 열려면 **네 조건이 다 맞을 때만**(작성자 세션 부재 · 무갱신 · 필수 4/4 · 본문에
「소유자 판단이 필요한 것」 절 없음) 이고, **예외를 쓴 사실을 머지 커밋에 적는다.**

★**무갱신은 `updatedAt` 으로 재지 마라** — 통합자의 `update-branch` 가 그것을 갱신한다
(실측 `#914`: `updatedAt` 0일 vs 진짜 **5일**). PR 안 **마지막 비머지 커밋**을 쓴다:

```bash
gh api repos/kangjh3kang-beep/Development_AI/pulls/<N>/commits \
  --jq '[.[] | select((.parents|length)==1)] | last | .commit.committer.date'
# ★커밋 250개면 엔드포인트 상한 → 판정 거부. committer.date 는 리베이스로 바뀐다.
```

---

## 2. ★비가역 배포의 백업 (지우지 말 것)

`#952`(배치 중복행 접힘)는 **전방 비가역**이다 — 접힘이 저장되면 `save()` 가 job 행을
DELETE 후 재삽입하므로 **코드 revert 로 복구되지 않는다.**

    영향 잡 9건 · 행 4,605건(record_ref 원본 포함) · 사라질 행 2,733/11,032(24%)
    sha256 앞16 = 2b8a46c2c0ed304d · 1,397,656 bytes

**3중 보관**:

    168 호스트   ~/batch_item_backup_20260903.json
                 ~/batch_item_backup_20260903_predeploy.json
    로컬 볼트    AI-Sessions/attachments/batch_item_backup_20260903*.json

```bash
ssh -i ~/.oci.key ubuntu@168.110.125.89 'sha256sum ~/batch_item_backup_20260903.json | cut -c1-16'
# 2b8a46c2c0ed304d 여야 한다
ssh -i ~/.oci.key ubuntu@168.110.125.89 'sha256sum ~/zzz_nope.json'   # ★음성 대조군: 실패해야 함
```

★**「되돌리기 경로」 칸은 revert 로 채울 수 없다 — 코드가 아니라 데이터로 채운다.**

---

## 3. 무주인 부채 (재측정 명령 포함)

정본: `_workspace/DEBT_open_items_2026-09-03.md`(PR `#953`). 요약:

1. **배치 잡 오염** — `counts` 가 최대 2.8배. `#952` 가 읽는 이음매에서 접는다.
   ★**남는 것**: 이미 화면에 틀린 수를 본 사용자 · 중복 행만큼 **VWorld 쿼터** 중복.
   ★**「counts ≠ 행수」로 세지 마라** — 오염 잡은 counts 도 함께 부풀어 9건 중 8건이 안 걸린다.
   옳은 축은 **중복 `(job_id, pnu)`**.
2. **큐 슬롯 예약 장치 부재** — 주체가 둘이면 「각자 한 번에 하나」로 부족하다(실측: 3회 러닝머신).
   ★기아는 **값과 무관**하다(델타 18도 델타 0도 똑같이 굶었다).
   ★현재 유일한 조정 기제는 **「상대가 알아채고 말을 거는 것」**.
3. **`#884` 꼬리 실행 관측 부재** — `tail_included` 소비처 0. 조용히 멈추면 아무도 모른다.
4. **`settings.X` 직접 읽기 5키/13곳** — `PUT /admin/secrets` 가 `os.environ` 만 바꾼다.
5. **`analysis_modules`·`budget_ratio` 가 관리자 화면에 0건** — `#955` 가 `it.todo` 로 남겼다.
6. **`RegistryService.live_status()` 가 키 이름을 안 받아 4키가 같은 집계** (동료 88 재측정).
7. **사용자 승인 대기** — 동료가 **자기 세션에서 권한 차단된** 조회를 대신 요청했다.
   ★**권한 세탁이라 수행하지 않았다.** 사용자 승인이 있으면 돌린다:

   ```sql
   SELECT count(*) FROM batch_item_result WHERE pnu IS NULL OR btrim(pnu)='';
   SELECT count(*) FROM batch_item_result WHERE pnu !~ '^[0-9]{19}$';
   ```

---

## 4. ★오늘 값을 치른 것 (같은 길 두 번 가지 말 것)

- **`testpaths` 함정** — 로컬 `propai-platform/tests/` 와 CI 의 `apps/api/tests/` 는 **다른 모집단**이다.
  «20 passed» 로 봉합을 선언했는데 CI 는 **72 failed** 였다. CI 명령·cwd·커밋 후 **셋 다** 맞춘다.
- **변이 판정 전에 기준선 rc 를 재라.** `pytest exit 4`(사용법 오류)를 CAUGHT 로 읽어 3건을 거짓 판정했다.
  ★**rc 는 1 만 진짜 CAUGHT**(2=수집 · 4=사용법 · 5=수집 0건).
- **락 단독 실행으로 판정하라.** 전체 CAUGHT 는 **형제 락**이 낸 것일 수 있다(오늘 두 세션이 각각 실측).
- **파생의 축이 결함이 사는 층과 같은가.** `#955` 에서 축이 「헬퍼」인데 결함은 「렌더」에 있어
  **원결함 복귀 변이 두 종이 SURVIVED** 였다(적대 리뷰가 잡음).
- **문자열 상수는 기억이 아니라 원문에서.** 오늘 6번 지어냈다 —
  화면 문구 · 컨테이너 경로 · 라우트 · 작업 상태값 · 세션 팩토리명 · 요청 스키마. **전부 「없음」으로 보고할 뻔했다.**
- **커밋 메시지는 인용 heredoc 으로.** `-m "…\`x\`…"` 의 백틱이 실행돼 문구가 사라진다.
  ★`#910`·`#905` 머지 커밋은 **보호 브랜치라 영구 오염**됐다.
- **공유 메인에서 커밋하지 마라.** 한 번 했고, **백업을 먼저 뜬 순서** 덕에 85줄을 살렸다.
  ★`reset --hard` 는 파괴 가드에 **안 걸린다**.
- **대조군을 본판정보다 먼저 찍어라.** 조회기가 죽으면 본판정도 대조군도 똑같이 빈다 —
  그 「같음」이 유일한 신호다.

---

## 5. 협업 중인 세션 (이름은 재사용된다 — `ListAgents` 로 재확인)

| 이름(당시) | 레인 |
|---|---|
| `development-ai-8f` | 배치 중복행(`#952`) · 토지·임야 공부 배선 |
| `development-ai-23` | 사통맵 선택 필지(`#954`) · 성장루프 왕복 락 |
| `development-ai-3c` | 변이 도구(`#946` 머지됨) · 감시기 |
| `development-ai-88` | 개발방식 판정(`#950` 머지·배포됨) |

★**보드가 정본이다**: `scripts/coord.sh status`. 이름으로 생존을 판정하지 마라 —
이름 부재는 사망이 아니고(개명), 이름 재사용은 오배송을 만든다.
