# PropAI 통합자 인계 — 2026-08-27 (development-ai-9c → 후임)

> ★**이 문서의 모든 값은 낡았다고 가정하고 재측정하라.** 아래 §0 명령을 먼저 돌려라.
> ★**"그 세션에 물어보라"는 없다** — 세션 이름은 재사용되고(실측: `e6` 가 `[f8a5d0]`→`[f41363]`),
>   오늘 문서에 이름이 적힌 세션은 **전원 사라졌다**. 근거와 좌표만 신뢰하라.

## §0 착수 즉시 (순서대로)

```bash
cd /home/kangjh3kang/My_Projects/Development_AI
git rev-list --left-right --count HEAD...origin/main   # ★원격만>0 이면 낡은 트리 — 먼저 ff
bash propai-platform/scripts/monitor/integrator_dashboard.sh   # 0=이상없음 2=위반 3=검사기사망
scripts/coord.sh status | tail -80                     # ★자르지 마라 — NOTE 에 배포요청이 숨는다
```
**★exit 3 을 0 으로 읽으면 "안 재 봤다"가 "깨끗하다"가 된다.**

세션 시작 시 추가로:
1. `ListAgents` → 살아 있는 피어에게 인사. **보드만 쓰면 놓친다**
2. 전역 지침 `~/.claude/CLAUDE.md` 의 **「인수인계 공유 의무」**(2026-08-27 신설)대로
   **받은 내용을 보드에 요약**하라 — 직접 메시지는 공유가 아니다
3. `obsidian-brain` 으로 주제어 조회. 오늘 그 조회가 **중복 PR 을 두 번 막았다**

## §1 라이브 좌표 (★값이 아니라 **재는 법**)

```bash
# 168 api (백엔드) — ★배포는 ~/deploy.sh (safe-deploy 금지)
ssh -i ~/.oci.key ubuntu@168.110.125.89 'cd ~/Development_AI && git rev-parse --short HEAD'
# 158 web (프론트) — ★배포는 propai-platform/scripts/safe-deploy.sh web main
curl -s https://4t8t.net/sw.js | grep -m1 '^const CACHE_NAME'      # ★줄시작 앵커 필수
# 활성 스택(전환 중 head -1 은 유휴를 집는다)
ssh ... 'PORTS=$(grep -vE "^[[:space:]]*#" $HOME/caddy/Caddyfile | grep -oE "reverse_proxy[[:space:]]+localhost:80[0-9]+" | grep -oE "80[0-9]+" | sort -u); echo propai-api-$PORTS'
# 라이브 검증 계정
admin@4t8t.net / admin1234
```
★**IP 를 기억에서 쓰지 마라** — 저장소에서 파생하라(`git grep -ohE '1[0-9]{2}(\.[0-9]{1,3}){3}'`).
내가 없는 IP로 6종 프로브를 돌려 **"플랫폼 배포 정지"를 오보**했다(전부 일관됐고 전부 틀렸다).

## §2 미완 작업 (내 것)

| PR | 상태 | 무엇 |
|---|---|---|
| **#894** | OPEN · AM **off** | 성장루프 판정률 — 축 정지(`axis_idle`)와 표본 부족(`partial`)을 가른다. 독립 리뷰 5건 반영, **기계적 변이 11/11 CAUGHT** |
| **#873** | OPEN · AM off | `CLAUDE.md §G-27` 네 건(사용자 승인분) — 문서라 **영향 클래스 최하위**, 큐가 비면 올려라 |
| 미착수 | — | **`heal_escalation` 도달 불가** — 아래 §3 |

## §3 ★가장 값 있는 미착수 — 에스컬레이션이 구조적으로 발화 불가

```python
ESCALATION_THRESHOLD = 5
PER_TRIGGER_HOURLY_CAP = {cache_warm:1, threshold_relax:2, stale_reanalysis:3, circuit_observe:10}
```
`should_escalate(trigger_count)` 는 `>=5` 를 요구하는데 `_cap_exceeded` 가 `>=cap(1/2/3)` 에서
차단하고, 차단된 후보는 **`continue` 로 `execute()` 앞에서 빠져 이벤트를 안 남긴다** →
카운터가 캡에서 얼어붙어 **5 에 영원히 못 닿는다**.

- **라이브 증거**: `heal_escalation` **전 상태 0건**(대조군 `fallback_rate open=21` — 조회기 생존)
- **도달 가능한 유일한 액션이 `circuit_observe`** — 주석 그대로 *"부작용 없음"*.
  **에스컬레이션이 필요 없는 것만 에스컬레이션할 수 있다**
- **반증 3회 전부 실패**(다른 생산 경로 없음 · 차단 시 이벤트 없음 · 같은 것을 셈)
- **잠그는 테스트 0건**

**설계(내 것 — 검증됨)**: 세는 대상을 **차단된 시도**로 바꾼다. 상수는 안 건드린다
(캡↑ = 프로덕션 타임아웃 곱 증가 · 임계↓ = 한 번 막힌 것도 에스컬레이션).

**드라이런 실측**: heal-log 500건에서 캡 도달 조합 **24/472(5.1%)**,
그중 **18개가 `fallback_rate:site_analysis` 하나** — 08-02~08-24. 폭주가 아니라 **반복**이다.
→ **중복 억제(축 단위)** 를 반드시 넣어라. 없으면 한 트리거가 화면을 18줄 채운다.

**하류 위험은 낮다**(측정됨): `propose_pr` → `growth_pr_task.py:139` 가 `GH_TOKEN` 부재 시
`artifact_only` 로 마킹만 한다(라이브 `improvement_proposal` 53/53).

★**`#886`(자가치유가 인사이트를 닫는다)이 먼저 착지해야 한다** — 안 그러면 닫히지 않은
인사이트가 매 창 재발화해 **차단 시도가 부풀려진다.**

## §4 오늘 확정된 실무 규칙 (재파생 금지 — 값을 치렀다)

### 배포 표식
```
신뢰   빌드ID(sw.js ^const CACHE_NAME) — 커밋을 직접 인코딩
약함   named export function · 신규 한글 UI 문자열   ← ★반례 있음(70주기 resolveVerdictMeta 0)
사망   export const · export default function · 모듈 로컬
무효   이미 번들에 있는 문자열
```
★**파생 단계에 두 필터를 넣어라** — 테스트 제외 + **배포 전 커밋에서 0인 것만**:
```bash
for f in $(git diff --name-only $BEFORE..$AFTER -- <경로> | grep -vE '(__tests__|/tests/|test_)'); do
  git diff $BEFORE..$AFTER -- "$f" | grep -E '^\+' | grep -oE '<패턴>'
done | sort -u | while read s; do
  [ "$(git grep -l -- "$s" $BEFORE -- '<경로>' | wc -l)" -eq 0 ] && echo "★$s"
done
```
이 필터 없이 **여덟 주기 연속** 같은 함정에 걸렸다(후보 14개 중 13개가 이미 존재한 적도 있다).
★**0 이 나오면 그 0 이 설명되는지 봐라** — 테스트 전용·주석·minify 는 정상, 나머지는 결함.

### 배포 판정
- **`sw.js` 표식은 158 web 만** 말한다. 168 api 는 별도 호스트 — `merge-base --is-ancestor` 로 재라
  (오늘 다른 세션이 이걸로 **세 번** "미배포"라고 잘못 신고했다)
- **전환 중 측정 금지** — 45~55초 시점은 활성이 아직 **구스택**이고 로그가 `신앱 health 대기`
- **워커 경로 파일은 worker·beat 를 각각** 재고 정렬 완료까지 기다려라

### ★"배포됐다 ≠ 동작한다" 세 얼굴
```
① 호출부가 옛 것        → 영원히 동작 안 함   결함  (#865 — 네 번째 층)
② 도달 조건 불충족      → 구조적 불가         결함  (heal_escalation)
③ 스케줄 대기          → 곧 동작            정상  (#880 crontab 03:12 UTC)
```
갈라 주는 것은 **"그 코드를 부르는 것이 무엇인가"**.

### 큐 운영
**영향 클래스 순**(델타 크기 아님):
```
① 사용자가 보는 것/가진 것이 거짓·손실  →  ①-b 운영자가 읽는 값이 거짓  →  ② 도구·테스트·문서
```
strict 보호라 **한 번에 하나**: `gh api -X PUT repos/<slug>/pulls/<N>/update-branch`
★`close/reopen` 은 **auto-merge 를 끈다**. `Cloudflare Pages`·`Workers Builds` 는 **비필수·상시 실패**.
★**갇힌 CI**: `Detect changes` 가 `queued` 로 멈추면 의존 잡이 `skipped` 되고 런이 `failure` 가 된다.
`rerun`·`cancel`·`update-branch`·`close/reopen` **넷 다 실패**했고 **`gh workflow run CI --ref <브랜치>` 만** 통했다.

### 도구 함정
```
python3           시스템 3.10. ★프로젝트 venv 는 propai-platform/apps/api/.venv/bin/python (3.12)
git stash pop     ★워크트리 간 공유 — 남의 것이 나온다. 지웠으면 git fsck --unreachable 로 복구
reset --soft origin/main   origin 이 움직였으면 남의 파일을 되돌리는 커밋이 된다 → git show --stat 로 확인
git grep -c      출력이 rev:path:count — cut -f2 는 경로다
urllib 기본 UA    WAF 가 403. curl 은 200 → User-Agent: curl/8.5.0
성장루프 조회     기본 정렬이 severity. 최신은 sort=created_at 명시
토큰 만료         401 이 아니라 **빈 값/0건**이 온다 → 대조군 먼저
gh pr edit        Projects GraphQL 로 무성 실패 → gh api -X PATCH + 사후 확인
```

## §5 ★기각된 가설 (재생성 금지)

| 가설 | 판정 |
|---|---|
| *"판정률 100% 는 하한을 내리면 된다"* | **기각** — `threshold_relax` 가 프로덕션 HTTP 타임아웃을 곱한다(PRODUCT 도달 유일 이펙터). 볼트에 사고 기록 실재 |
| *"플랫폼 배포가 정지됐다"* | **거짓** — 내가 IP 를 지어냈다. 프로브 6종이 전부 일관됐고 전부 틀렸다 |
| *"critical 인사이트에 제목이 없다"* | **거짓** — `title`/`summary` 는 스키마에 없다. 실제는 `narrative`(값 정상) |
| *"커버리지 계측 없는 축 3개는 결함"* | **기각**(타 세션) — 그 축들은 표본 하한이 없다. `sev is None` 은 "판정 불가"가 아니라 "임계 미달" |
| *"`coverage_pct` 를 싣자"* | **기각**(독립 리뷰) — `total>0` 에서 상수이고 `state` 와 완전 중복 |
| *"`#880` 이 안 돈다"* | **거짓** — `crontab(hour=3,minute=12)` 스케줄 대기였다 |

## §6 미측정 (승계 말고 재라)

- `quality_drop` 이 `total=0` 인 **원인**(축이 안 도는지 데이터가 없는지)
- `selection_contamination` 2건 — `count=7 verdict=multi_region max_spread_km=290.33`. **소유 세션 없음**
- `#880` cleanup 이 실제로 도는지 — **03:12 UTC 이후** `status=open total` 을 재라(449 근처면 정상)
- 보류를 인사이트로 승격했을 때의 **누적 영향**(기존 독스트링이 키별 발행을 기각했다 · 내 축별 1건은 다른 제안)

## §7 협업

오늘 네 세션과 실질 협업했다. **양방향으로 오류를 잡았다** — 내 오류 여러 건을 동료가,
동료 오류 여러 건을 내가 잡았다. 자기승인이 아니었던 이유가 그것이다.

★**독립 리뷰 게이트가 내 PR 을 막았고 그게 옳았다.** 반증 임무 리뷰가 **CRITICAL 을 포함해 5건**을
찾았다(내 변경이 형제 테스트 5건을 깨서 CI 가 빨개질 상태였다). **자기승인했으면 나갔다.**

요청 형식을 이렇게 받으면 판정이 기계적이다:
**머지커밋(브랜치 sha 아님) + 런타임 델타 범위 + 배포전 실측 + 기대값 + 대조군 + 되돌리기 트리거**
