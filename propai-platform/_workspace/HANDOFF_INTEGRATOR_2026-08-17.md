# 통합자 인수인계 — 2026-08-17

**역할**: 배포 감시·수행·검증·기록. 타 세션의 작업을 상시 모니터링하고, 배포가 필요할 때 배포한다.

> ★**이 문서는 값을 최소한만 적는다.** 오늘 "값을 적었더니 42분 만에 썩고, 그것을 고친 정정
> 문서가 또 썩는" 3중 재감염을 겪었다. **휘발성은 명령으로 남긴다.** 불변 사실(머지 해시·
> 측정 기준)만 값으로 적는다.

---

## 0. 지금 상태를 재는 명령 (문서를 믿지 말고 이걸 돌려라)

```bash
# 배포된 커밋 — 캐시명 끝 8자리가 그 커밋이다(#658 이 빌드 시 sed 로 박는다)
curl -s https://4t8t.net/sw.js | grep -m1 '^const CACHE_NAME'
#   ★반드시 '^const' 앵커를 줘라. 앵커 없이 patterns 로 읽으면 340행 **주석의 예시값**을 집는다
#     (2026-08-17 에 한 세션이 그렇게 읽고 "#658 고장·사용자에게 수정이 안 닿는다"를 오보했다)

git fetch origin -q && git log --oneline -1 origin/main       # main
gh pr list --state open --limit 20 \
  --json number,mergeStateStatus,headRefName,autoMergeRequest \
  --template '{{range .}}#{{.number}} {{.mergeStateStatus}} auto={{if .autoMergeRequest}}O{{else}}-{{end}} {{.headRefName}}{{"\n"}}{{end}}'

# 서버 HEAD (SSH 는 반드시 -i, .ssh/ 의 키는 거부된다)
for h in 168.110.125.89 158.179.174.207; do
  ssh -i ~/.oci.key ubuntu@$h 'cd ~/Development_AI && git log --oneline -1'
done

scripts/coord.sh status | tail -80      # 공유 보드
```

---

## 1. 배포 판정 — **커밋 수가 아니라 런타임 델타**

```bash
DEP=<캐시명 끝 sha>   # 위 명령으로 얻는다
M=$(git rev-parse origin/main)
git diff --name-only $DEP..$M -- propai-platform/apps/api | grep -vc '/tests/'          # 백엔드 런타임
git diff --name-only $DEP..$M -- propai-platform/apps/web | grep -vcE '__tests__|\.test\.'  # 프론트 런타임
```

- **둘 다 0 이면 배포하지 않는다.** 문서·테스트·CI 커밋은 그 자체로 배포 사유가 아니다.
- 오늘 실제로 `#668`(배포스크립트 2파일+CLAUDE.md)이 머지됐지만 **런타임 0 이라 배포 불요**로 판정했다.
- 반대로 한 세션이 *"커밋 1개 밀렸으니 168 도 대상"* 이라 했는데, 그 커밋 착지가 `apps/web` 뿐이라
  **158 만** 필요했다(그 세션도 실측 후 정정 수용).

---

## 2. 배포 절차 — **서버마다 다르다. 틀리면 조용히 성공을 찍는다**

```bash
# 168 백엔드 (블루그린 8000↔8001 · caddy 프록시)
ssh -i ~/.oci.key ubuntu@168.110.125.89 \
  'setsid bash ~/deploy.sh </dev/null >/tmp/deploy168.log 2>&1 &'
#   ~/deploy.sh 는 얇은 래퍼 → infra/deploy-zero-downtime.sh 를 exec 한다
#   ★168 에 safe-deploy.sh 를 쓰면 **트래픽 없는 compose 스택**만 갱신하고 "성공"을 찍는다
#     (실서비스는 compose 밖 propai-api-800x). 한 세션이 그렇게 배포하고 "완료" 보고했다가 전면 정정했다

# 158 프론트 (저장소 정본 · 홈 사본 쓰지 말 것)
ssh -i ~/.oci.key ubuntu@158.179.174.207 \
  'cd ~/Development_AI && setsid bash propai-platform/scripts/safe-deploy.sh web main </dev/null >/tmp/deploy158.log 2>&1 &'

# 진행 확인 — ★프로세스를 세지 말고 **상태파일의 전이**로 판정한다
#   상태값: PREFLIGHT SYNC DEPENDENCIES BUILD RECREATE NGINX VERIFY DONE / FAIL WARN ABORT
ssh -i ~/.oci.key ubuntu@158.179.174.207 'cat /tmp/deploy_status.txt'

#   ★`pgrep -f safe-deploy` 를 쓰지 마라 — **자기매칭 함정**이다(CLAUDE.md 의 덫 표).
#     그 패턴 문자열이 **이 명령을 나른 ssh 원격 명령줄에** 들어 있어 스스로 매칭한다.
#     2026-08-19 실측: 배포가 `DONE` 인데도 결과가 `1` 이었다(실제 프로세스는 0).
#     즉 **영원히 0 이 되지 않아** 끝난 배포를 무한정 기다리게 된다(실제로 4분 헛돌았다).
#     프로세스를 꼭 봐야 하면 대괄호로 자기를 비껴간다:
ssh -i ~/.oci.key ubuntu@158.179.174.207 'ps -ef | grep -c "[s]afe-deploy.sh"'

#   ★멈춤 판별은 상태문자열이 아니라 **로그 갱신 + CPU** 로 한다
#     (`BUILD` 는 몇 분씩 머문다 — 상태만 보면 hang 과 구분되지 않는다):
ssh -i ~/.oci.key ubuntu@158.179.174.207 \
  'echo "경과 $(( $(date +%s) - $(stat -c %Y /tmp/deploy.log) ))초"; tail -3 /tmp/deploy.log; docker stats --no-stream --format "{{.Name}} {{.CPUPerc}}" | head -3'
```

### ★스크립트 자체가 바뀐 배포 — **선갱신을 먼저**

배포 스크립트가 자기 repo 를 `git reset --hard` 해도 **이미 실행 중인 bash 는 구 내용을 돌린다**
("한 판 지연"). 그런 배포는 **직전에 선갱신**한다:

```bash
ssh -i ~/.oci.key ubuntu@<ip> 'cd ~/Development_AI && git fetch origin main -q && git reset --hard FETCH_HEAD -q'
    # 적용 확인 — ★판별력을 검증한 표식만 쓴다
    ssh -i ~/.oci.key ubuntu@<ip> 'cd ~/Development_AI && grep -c "exit 10" propai-platform/scripts/safe-deploy.sh'
    #   1 이상이면 적용됨. ★"caddy/Caddyfile" 로 확인하지 마라 — 판별력이 없다:
    #     deploy-zero-downtime.sh 는 원래 caddy 를 reload 하므로 #668 **이전**에도 4건 나온다(실측).
    #     'exit 10' 은 #668 전 0 · 후 1 로 갈린다.
    #   ★대조군도 함께: grep -c docker ...safe-deploy.sh → 20 (0 이면 조회기가 죽은 것)
# 그 다음 평소 절차대로
```

**현재 미적용 건**: `#668`(서버 역할 가드)이 main 에 있으나 두 서버 스크립트엔 아직 없다.
**다음 런타임 배포 때 선갱신을 먼저 태우면 그 배포부터** 가드가 걸린다.

---

## 3. 배포 검증 — 오늘 세 번 고쳤다

### ① 호스트 소스 grep 은 **근거가 아니다**
배포 스크립트가 `git reset --hard` 하므로 호스트 경로는 **무엇을 배포하든 최신**이다.
`git merge-base --is-ancestor` 도 **pull 만 증명**한다.
→ **`docker exec <실행컨테이너>`** 로 본다. 호스트 소스는 **대조 항목**으로만 쓴다.

```bash
ssh -i ~/.oci.key ubuntu@158.179.174.207 \
  'docker exec propai-platform_web_1 grep -m1 "^const CACHE_NAME" /app/apps/web/public/sw.js'
```

### ② 대조군 없이 "0건"을 결론내지 않는다
양성(반드시 있어야 할 것) + 음성(절대 없어야 할 것)을 **함께** 찍는다.
파이썬 테스트에는 도구가 있다 — `propai-platform/tests/_scan_guard.py` 의
`assert_absent(..., positive_control=…, reason=…)`. 두 인자가 **필수**라 대조군 없는 호출이
문법적으로 불가능하다.

### ③ ★판정은 **2단계**다 — ①만 보면 더 그럴듯한 오판을 한다

```
① 대조군이 살아 있는가          (조회기 판별력)
② 이 층이 이 변경을 담는가      (호출이 남는가 · 문자열이 남는가 · 순수 로직인가)
```

| 변경의 성질 | 컨테이너 grep | 정본 증거 |
|---|---|---|
| **호출이 남는** 변경(`charge_guard` 등) | 통한다 | 심볼 존재 + 음성대조 |
| **순수 로직 모듈**(`lib/pnu.ts` 등) | **통하지 않는다** — 번들러가 인라인하며 이름을 없앤다 | **빌드 sha** 또는 **기능 재현** |

### ④ ★**수렴은 증거가 아니다. 방법이 다를 때만 증거다**
한 세션이 **4개 관측점 일치**로 오보했는데, **네 번 다 같은 깨진 추출기**였다.
관측점을 늘리는 것과 방법을 바꾸는 것은 다르다.

---

## 4. 저장소 설정 — 오늘 바뀐 것

| 설정 | 값 | 의미 |
|---|---|---|
| `allow_auto_merge` | **true**(오늘 켬) | `gh pr merge <N> --squash --auto` → 초록 되는 순간 머지 |
| `allow_update_branch` | **true**(오늘 켬) | "Update branch" 상시 활성 |
| `strict` (브랜치보호) | true | main 이 앞서면 초록이어도 막힌다 |
| `enforce_admins` | true | **`--admin` 우회는 원천 불가** — 탈출구로 기대하지 말 것 |
| 머지큐 | **사용 불가** | GA 공지: EC 플랜 또는 **조직 소유** public. 이 저장소는 개인 계정 |

★**auto-merge 는 리베이스 사이클을 없애지 못한다**(관측: BEHIND 브랜치를 자동 갱신하지 않고
기다리기만 한다 · force-push 후에도 auto 는 **유지**된다). **리베이스는 손으로.**

★**sw 범프 PR 을 만들지 마라.** `#658` 로 빌드가 커밋마다 캐시명을 만든다(누적 85개였던 작업이 사라졌다).

---

## 5. 남은 일

### 사용자 결정 대기 (3건)
1. **조직 이전** — 머지큐가 열린다(오늘 `#649` 5사이클·`#658` 3사이클의 직렬 재실행이 근본적으로 사라진다). 소유·URL·권한이 바뀐다.
2. **배포 시크릿** — 자동배포는 `ORACLE_SSH_HOST`·`ORACLE_SSH_KEY` 부재 하나로 죽어 있다(최근 실행 전부 실패·성공 0). ★**키는 이미 발급돼 있다**(`~/.ssh/propai_oracle_deploy`, ed25519) — 등록만 남았다. 다만 **public 저장소에 개인키**를 넣는 판단이 사용자 몫이다.
3. (해소됨) `allow_auto_merge` — 오늘 켰다.

### 배포 대기 PR
- `#673` 토지조서 **지번 칸에 주소**가 들어감(77행 전부) — 엑셀·등기분석·다필지 매트릭스로 전파. 로컬 3축 통과, BEHIND
- `#671` 멱등키 생산자 — 로컬 3축 통과, BEHIND
- 리베이스 후 `gh pr merge <N> --squash --auto` 를 걸면 자동 착지한다

### 미검증·미해결
- **`#672` 기능 재현 X** — 라이브 UI 로 "불러오기 (3)" → 3건 확인했으나 **셋 다 다른 동**이라 결함 조건(같은 동 주소 충돌)을 **못 태웠다**. 77필지는 사용자 계정 프로젝트라 접근 불가.
  → 같은 동 지번 2건 이상을 `/quote` 의 "필지 지번 입력"으로 수동 추가하면 조건이 만들어진다.
- **사통맵 VWorld 타일 502** — 릴레이 폴백 미설정 가설은 **기각됨**(컨테이너에 `NEXT_PUBLIC_API_BASE_URL`·`VWORLD_API_KEY` 둘 다 존재). 프록시 `lib/vworld-wms-proxy.ts:306` · `wmts:236`, 화면 문구 `SatongMultiMap.tsx:674`(기본지도)·`:1141`(지적). 진단 프로브 경로 `/tiles/vworld/wms`.
- **`propai-platform/tests` 린트 사각지대** — CI ruff 는 `apps/api` 에서만 돈다. 실측 79건 누적.
- **Security Scan 성공 0** — bandit 은 검사 결과로 exit 1, pip-audit 은 `-r` 이 의존성을 해석하며 gdal 빌드 실패. 그 단계 주석("설치 없이 스캔")이 **실제 동작과 다르다**.
- **★내가 남긴 덫** — `sw.js` 340행 주석의 형식 예시가 실재 sha(`propai-v002612-e527b6e8`)라 패턴 매칭에 걸린다. `propai-vXXXXXX-XXXXXXXX` 로 바꿀 것.

---

## 6. 상시 모니터링 (선택)

`Monitor` 로 걸어 두면 배포 격차와 PR 전환을 알려 준다. 핵심은 **런타임 델타로 판정**하는 것 —
격차가 있어도 런타임 0 이면 "배포 불요"로 구분해 알리게 짠다. 배포된 커밋은 **캐시명 끝 sha 에서
매번 읽어** 기준선이 썩지 않게 한다.

---

## 7. 함께 읽을 것

- `CLAUDE.md` A-8(대조군 강제) · A-9(파이프 종료코드) — 오늘 추가
- 옵시디언 `AI-Sessions/wiki/errors/2026-08-17_조회기가_멀쩡한데도_0건인_경우가_있다`
- 옵시디언 `AI-Sessions/wiki/dev-tasks/2026-08-17_통합자_상시모니터링_배포체제`
- 옵시디언 `AI-Sessions/wiki/decisions/2026-08-16_파이프라인_근본안정화_방안`
- 저장소 `_workspace/HANDOFF_PROMPT_2026-08-17.md` (다른 세션 작성 · PR #674)
