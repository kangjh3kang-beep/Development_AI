# 인계 프롬프트 — 다음 세션이 그대로 붙여 쓰는 문서 (2026-08-16 작성)

> 이 파일은 **프롬프트**다. 다음 세션에 이걸 주면 바로 이어갈 수 있게 썼다.
> 배경 상세는 `_workspace/HANDOFF_PROMPT_i18n_honesty_e2e_2026-08-16.md`,
> 교훈 정본은 옵시디언 `AI-Sessions/wiki/errors/2026-08-16_*`.

---

## 0. 시작 전에 (건너뛰지 말 것)

1. `scripts/coord.sh status` — 다른 세션이 어느 브랜치·영역을 잡고 있는지 확인.
2. 옵시디언에서 **주제어로 조회**한다(SessionStart 훅 요약만으로는 부족).
3. **아래 "확정 사실"을 그대로 믿지 말고 재측정하라.** 이 저장소에서 인계문서의 전제가
   낡아 있던 사고가 반복됐다 — 실제로 직전 인계도 3건이 틀렸다(§4 참조).

---

## 1. 확정 사실 (2026-08-16 13:10 KST 기준 · 재측정 권장)

| 항목 | 값 | 재측정 명령 |
|---|---|---|
| main HEAD | `3bddbeb0` | `git rev-parse --short origin/main` |
| sw (main·프로덕션) | `propai-v505-charge-idempotency` **일치 = 배포 최신** | `curl -s https://4t8t.net/sw.js \| grep -m1 '^const CACHE_NAME'` |
| 나이틀리 e2e | **전체 17 통과 / 0 실패**(보류 4) | 아래 §5 재현 절차 |
| 프론트 유닛 | 232파일 2104 통과 | `npx vitest run` |
| 열린 PR | `#652`(플래키 판정기준 문서·BEHIND) | `gh pr view 652` |

직전 세션이 닫은 것: 나이틀리 e2e 실패 7건 전량 · 안내문구 48건 정직화(FALSE 22 교체) ·
내비 i18n 두 자리 봉합 · 제품 결함 3건 · **#632 비밀번호 URL 노출 봉합 배포**(라이브 확인).

---

## 2. 다음에 할 일 (우선순위 순)

### P1 — 컴포넌트층 i18n 캠페인 (실측 **134파일 · 341개**)

`/en`·`/zh-CN` 사용자에게 화면이 한국어로 나온다. 내비 SSOT(63개)와 시설예약(18개)만 닫혔다.

- **측정 명령**:
  `grep -rlE 'placeholder="[^"]*[가-힣]|aria-label="[^"]*[가-힣]' components --include="*.tsx" | grep -v __tests__ | wc -l`
- **패턴은 이미 있다** — 새로 만들지 마라. `components/operations/TenantWorkspaceClient.tsx` 의
  `type Labels` + `const LABELS: Record<Locale, Labels>` + 부모에서 `locale` 하향.
  실제 적용 예: `components/operations/FacilityReservationSection.tsx`(직전 세션 작업).
- **주의**: 형제 컴포넌트 중 `"zh-CN": KO_LABELS` 로 **중국어를 한국어에 폴백**시킨 것들이 있다.
  따라 하지 마라 — 실제 중국어를 채워라.
- **주의**: 테스트가 참조하는 한국어 문자열이 **7개** 있다. 건드리기 전에 확인:
  `grep -rohE 'getByPlaceholder\("[^"]*[가-힣][^"]*"\)|placeholder\^?="[^"]*[가-힣]' e2e __tests__`
- **★작게 쪼개 자주 머지하라**(§4 참조).

### P2 — `test.fixme` 3건 해제

| 위치 | 해제 조건 |
|---|---|
| `e2e/project-release.spec.ts:72` | 설계·BIM 워크스페이스가 로케일을 타면 |
| `e2e/design-3d-viewer.spec.ts:87` | 3D 툴바 토글 클릭 문제 확정 후 |
| `e2e/operations-release.spec.ts:65` | KDX 라우트 제품 결정 후 |

### P3 — 3D 툴바 토글 클릭 (환경/제품 **미확정**)

`bim3d-section` 등이 `toBeVisible` 은 통과하는데 `.click()` 이 60초 안에 actionability 를 못 넘는다.
툴바가 뷰포트 밖(y≈884)이고 R3F 렌더 루프가 돈다. **사람이 실브라우저에서 눌러 보고 확정하라** —
되면 환경(안정성 대기 우회), 안 되면 **제품 결함**(툴바 위치·레이어). `force:true` 로 초록을
만들지 마라 — 정말 못 누르는 결함을 덮는다.

### P4 — 별건 2건 (미수정, 보고만 됨)

- `GET /projects/{id}/operations/status` **인증 없음**(`Depends(get_current_user)` 부재).
  지금은 정적 "미가용" 페이로드라 유출은 없지만 **수집원이 연동되는 순간 무인증으로 실지표가 나간다**
  — 배선 전이 가장 싼 시점. 그 파일 소유 세션에 보드로 전달했다.
- `__tests__/password-form-method.contract.test.ts` 가 부하 중 **10초 타임아웃**으로 실패
  (단독 4.7s — 여유 2배뿐). CI 에서도 흔들릴 수 있다.

### P5 — 플래키 1건 (원인 미확정)

`digital-twin-scene:36` 이 1회 `/en/login?next=…` 로 리다이렉트되며 실패했고 **12회 재현에서
12/12 통과**(누적 13중 1 ≈ 7.7%). 브라우저 요청에 4xx/5xx 는 **0건**이었다.
★**CI 의 `retries: 2` 가 이걸 초록으로 가린다.** 나이틀리에서 **반복 실패하면 "알려진 플래키"로
뭉개지 말고 빈도가 올라간 것으로 보고 즉시 파라.**

---

## 3. e2e 를 손대기 전에 반드시 아는 것

### 로컬과 CI 는 **다른 앱을 태운다**

| | 로컬 기본 | CI |
|---|---|---|
| 서버 | `pnpm dev`(dev 빌드) | `build && start`(**prod**) |
| 포트 | 3100 | 3000 |
| 백엔드 | 없음 | **실제 uvicorn** |

### CI 동형 재현 절차

```bash
cd propai-platform && pnpm install --frozen-lockfile   # 워크트리 node_modules 가 깨진 심링크인 경우가 많다
pnpm --filter @propai/web build
cd apps/web && setsid nohup pnpm start -p 3100 -H 127.0.0.1 >/tmp/srv.log 2>&1 &
CI=1 BASE_URL=http://127.0.0.1:3100 npx playwright test --retries=0
```

★실패하면 **추정하지 말고** `test-results/<스펙>/error-context.md` 의 **DOM 스냅샷**을 봐라.

### 서비스워커가 가로채기를 우회한다

`page.route` 는 페이지가 직접 내는 요청만 잡는다. **SW 가 대신 내는 요청은 못 잡는다** —
그래서 같은 URL 이 404(해네스) 였다가 503(SW 합성)이 된다. `playwright.config.ts` 에
`serviceWorkers: "block"` 이 들어가 있다. **빼지 마라.**

---

## 4. 하지 말 것 — 직전 세션에서 **실제로 데인 것**

1. **"고쳤다"를 코드로 판단하지 마라.** 내비 i18n 을 레지스트리에서 봉합하고 회귀망도 초록이었는데
   **DOM 은 그대로 한국어**였다 — 진짜 출처가 다른 파일(`lifecycle-stages.ts`)이었다.
   e2e 를 **다시 돌려 DOM 을 본** 덕분에 알았다.
2. **증상 문구로 원인을 단정하지 마라.** Playwright 가 "visible, enabled and stable" 을 99회
   기다려 **무한 재렌더**로 의심했으나, 박스를 6회 재보니 **완전히 고정**이었다 —
   불안정이 아니라 **가림**이었다(`elementFromPoint` 로 판정, CLAUDE.md §D.18).
3. **테스트가 결함을 요구할 수 있다.** 2건 적발 — 세 로케일 **전부**에 한국어를 요구한 정직성
   테스트, `buildPrimaryNav("en")` 을 렌더하며 **한국어 라벨**을 단언한 내비 테스트.
   봉합 후 단언이 빨강이면 **단언이 틀린 것**일 수 있다.
4. **전체 스위트를 돌려라.** `GlobalAddressSearch` placeholder 를 호출부 prop 으로 덮은 변경이
   **다른 스펙의 층위 계약을 깨뜨렸다.** 대상 스펙만 돌렸으면 내가 만든 결함을 "고쳤다"고 보고했다.
   placeholder(형식 예시)와 **접근 가능한 이름**은 다른 것이다.
5. **`prettier` 를 파일 전체에 돌리지 마라.** 실변경 16줄이 서식 531줄에 묻힌다.
6. **커밋 전에 브랜치를 바꾸지 마라.** 인계문서 편집을 브랜치 전환으로 **날렸다**(§F-23).
   전환 후 `grep -c` 로 확인해 겨우 적발했다.
7. **큰 PR 은 이 환경에서 구조적으로 불리하다.** CI 1회 **≈16분**인데 **동시 CI 런이 5개**였다
   (다른 세션들이 main 을 빠르게 민다). 23커밋 PR 이 머지 루프 42회를 견뎠다.
   → **작게 쪼개 자주 머지.** `--admin`(브랜치보호 우회)은 **사용자 승인 없이 쓰지 마라.**
8. **한 번의 관측으로 결론내지 마라.** "백엔드가 있으면 깨진다"를 1회 실패로 결론낼 뻔했고
   12회 재현에서 반증됐다. 반대로 **"재현 안 됨"을 "없음"으로 읽어도 틀린다.**

---

## 5. 라이브 검증 스니펫 (배포 후 매번 쓸 것)

```bash
# 내비 로케일
for L in en zh-CN ko; do echo -n "/$L: "; curl -s "https://4t8t.net/$L" | grep -oE "Design Center|设计中心|설계 센터" | head -1; done
# 비밀번호 폼 method (보안)
curl -s https://4t8t.net/ko/login | grep -oE '<form[^>]{0,120}' | head -3
# sw 버전 (main 과 일치해야 배포 최신)
curl -s https://4t8t.net/sw.js | grep -E "^const CACHE_NAME"
```

테스트계정은 사용자에게 받아 쓰고 **문서·커밋에 남기지 마라**.

---

## 6. 협업 규약 (필수)

- 브랜치당 **전용 워크트리**에서만 작업(`scripts/new-worktree.sh <branch>`).
  공유 메인(`Development_AI/`)에서 feature 브랜치 checkout 금지.
- 공유 파일 편집 전 `scripts/coord.sh claim <영역>` → 완료 후 `release`.
- **sw 캐시 범프는 중복 채번 금지.** 직전 세션에서 `#637`/`#638` 이 **76초 차이로** 같은 번호를
  서로 다른 이름으로 채번했다. 보드 claim 이 경합을 못 막는다 — **채번 전 `origin/main` 실제
  상수를 확인하고, 이미 다른 PR 에 범프가 실려 있는지 먼저 보라.**
- 커밋 전 `git branch --show-current` 로 자기 브랜치 확인. main 직접 푸시 금지.
