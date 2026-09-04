# 인계 — i18n 봉합 · 안내문구 정직화 · e2e 트리아지 (2026-08-16)

브랜치 `fix/ops-intelligence-honesty` (PR **#634, 미머지**) · 최신 `ffb70623`

> ※ 이 문서는 저장소 산출물이다. 옵시디언 Vault(`/mnt/d/…`)가 세션 종료 시점에 **장치
> 분리 상태**여서 그쪽 기록은 남기지 못했다 — 다음 세션에서 Vault 복구 후
> `AI-Sessions/conversations/` 에 옮겨 적을 것.
>
> ※ 2026-08-13 인계문서가 참조한 `_workspace/HANDOFF_PROMPT_e2e_triage_2026-08-13.md` 는
> **어느 브랜치에도 존재한 적이 없다**(`git log --all` 0건). 그 매달린 참조를 이 문서로 대체한다.

## Summary

- e2e 나이틀리 **7건 실패 → 3건 통과 전환**(prod 빌드 로컬 재현 기준).
- **i18n 결함**: `/en`·`/zh-CN` 에서 내비게이션이 한국어. 원인이 **두 자리**였고 형태가 같았다.
- **안내문구 48건 전수 감사**: BACKED 11 · OVERSTATED 11 · **FALSE 22** · UNVERIFIABLE 4
  → 3개 로케일 정직화 + 소비처 0 죽은키 10개 삭제.
- 검증: 프론트 **230파일 2084케이스 통과** · `tsc --noEmit` 클린 · 회귀 0.

## ★로컬 e2e 재현 방법 (이게 없어서 종전엔 추정만 했다)

로컬 기본값과 CI 가 **다른 앱을 태운다**:

| | 로컬 기본 | CI |
|---|---|---|
| 서버 | `pnpm dev`(dev 빌드) | `build && start`(**prod**) |
| 포트 | 3100 | 3000 |
| 백엔드 | 없음 | **실제 uvicorn** |

CI 와 같은 형태로 재현하려면:

```bash
cd propai-platform && pnpm install --frozen-lockfile
pnpm --filter @propai/web build
cd apps/web && setsid nohup pnpm start -p 3100 -H 127.0.0.1 >/tmp/srv.log 2>&1 &
CI=1 BASE_URL=http://127.0.0.1:3100 npx playwright test --retries=0 e2e/project-release.spec.ts
```

★워크트리 `node_modules` 가 **삭제된 다른 워크트리의 pnpm 스토어를 가리키는 깨진 심링크**인
경우가 많다 — 그때 `pnpm install --frozen-lockfile` 로 복구된다.
★실패 시 `test-results/<스펙>/error-context.md` 에 **DOM 스냅샷**이 남는다. 추정하지 말고 이걸 봐라.

## e2e 상태 — **전체 16 통과 / 0 실패**

나이틀리 실패 7건이 전량 닫혔다. 보류 5건은 `test.fixme` 로 사유·해제조건과 함께 노출한다.

| 스펙 | 근본원인 |
|---|---|
| `project-release:8` | 해네스 `/projects` 폴백이 **앱이 안 읽는 키**(`projects`)에만 픽스처를 담았다 → `items` 병기 |
| `digital-twin-scene:36` | 내비 i18n 봉합으로 자동 해소 |
| `operations-release:7` | 해네스 픽스처를 기다렸으나 **앱이 그 API 를 안 부른다**(로컬 산술) → 제품 산출물(정직 고지)로 교체 |
| `project-release:66` | **서비스워커**가 가로채기를 우회해 같은 URL 이 404→503 → `serviceWorkers:"block"` |
| `collaboration-room:42` | 모달이 포털 없이 인라인 렌더라 **닫기 버튼이 페이지 요소에 덮임** → `createPortal`+`z-[1000]` |
| `design-3d-viewer:12` | 조건부 렌더 전제 누락 — `view==="draw"` 전환이 있어야 패널이 보인다(§A.1) |
| `auth-dashboard:7` | `withSession:false` 가 **세션 없음을 뜻하지 않았다**(`/auth/me` 200) + 삭제된 UI 를 기다리는 죽은 단언 4건 |

### 보류 5건(`test.fixme`)

- `/en/tenant` · `/en/design` · `/en/bim` — 화면 전체가 한국어(컴포넌트층 i18n 캠페인)
- 3D 툴바 토글 **클릭** — actionability 미달. **환경 아티팩트인지 실제 클릭 불가인지
  확정하지 못했다.** `force:true` 로 초록을 만들면 정말 못 누르는 결함을 덮으므로 하지 않았다.

## 고친 것

### 제품 결함 (스펙이 옳았다)

1. **`GlobalAddressSearch` 가 `placeholder` prop 을 받고도 안 썼다** — 선언·전달은 되는데
   렌더는 한국어 하드코딩. 정의는 있고 **소비처 0**. 봉합 후 `/en/…/finance` DOM 에서
   `placeholder="Address"` 실측 확인.
2. **라벨-입력 미연결(a11y)** — `DigitalTwinControlTowerWorkspaceClient` 의 `<label>` 에
   `htmlFor` 없음 + `<Input>` 에 `id` 없음 → 스크린리더에 이름 없는 입력.
3. **i18n 두 자리** — `buildPrimaryRegistrySections(locale)` 이 `locale` 을 `href` 에만 쓰고
   `label` 에 안 씀 / `lib/lifecycle-stages.ts` 의 `STAGE_META[].label` 도 동일 형태.
   → `lib/navigation/nav-i18n.ts` 로 일원화(항목 44 + 섹션 8 + 단계 11).

### 스펙 드리프트 (제품이 옳았다)

- `operations-release` 가 해네스 픽스처 문자열을 기다렸는데 이 화면의 "분석"은
  **서버를 부르지 않는다**(로컬 산술) → 제품이 내는 것(정직 고지)을 잠그도록 교체.
- 디지털트윈 버튼 재설계(`COMMIT SNAPSHOT`·`EXECUTE_RISK_AI`·`INIT_LIFECYCLE`).
- UUID 입력은 placeholder 가 아니라 **라벨**로 이름이 붙는다.

### 제품 i18n 결함에 막혀 `test.fixme` 로 남긴 것

`/en/tenant` · `/en/design` · `/en/bim` 은 `/en` 인데 화면이 **전부 한국어**다.
한국어 기대로 바꾸면 통과하지만 **결함을 굳히므로** 하지 않았다.

★**컴포넌트층 i18n 캠페인 실측 규모: 134파일 · 341개**
(`placeholder`/`aria-label` 한국어 하드코딩. 버튼 표시문구는 미집계 — 실제로는 더 크다.)

## 안내문구 감사 요약

- **`construction`·`operations`·`drone` 은 3줄 전부 FALSE.**
  `operations` 의 유일한 백엔드 호출은 `apps/api/routers/projects.py:91-106` 로
  **리터럴 dict 반환**(`occupancy_rate_pct: 92.5` 하드코딩).
- **`blockchain` 은 FALSE 가 아니라 OVERSTATED** — 에스크로 계약은 실재하나
  **Polygon Amoy 테스트넷**·비실시간. 없는 것과 과장한 것을 섞지 말 것.
- **`permit` 은 코드가 스스로 오칭을 적어놨다** — `seumter_permit_service.py:3` 이
  *"★오칭 주의: 세움터 API 를 호출하지 않는다"*.
- ★**최대 오염원은 복사된 보일러플레이트**였다 — 같은 3줄이 11개 모듈에 있었고
  생성 스크립트(`fix-dict.js:45`)가 일괄 주입했다. 한 곳을 걷어내니 11개가 동시에 정직해졌다.
- 표기 규약은 `maintenance`(#634)가 세운 것을 따랐다 — `· <하는 일> — <상태>`, `— 미연결`.


## ★플래키 1건 — 판정 기준을 미리 정하고 쟀다

`digital-twin-scene:36` 이 **백엔드가 뜬 상태의 1회차**에서 `/en/login?next=…` 로 리다이렉트되며
실패했다(문서화된 401→`handleSessionExpired`→토큰삭제→로그인 형태). 그런데 브라우저 요청에
**4xx/5xx 는 0건**이었다 — 서비스워커 때와 같은 계측 사각지대 계열로 보이나 **원인 미확정**.

재현 시도: **12회 반복 → 12/12 통과**(누적 13회 중 1회 ≈ 7.7%).

- 말할 수 있는 최대치는 **"재현 시도 12회에서 나타나지 않았다"** 이지 **"없다"가 아니다.**
- 지금 원인 규명에 더 쓰지 않는다 — CI 는 `retries: 2` 라 이 빈도는 흡수된다.
- ★**그런데 그게 위험한 지점이다.** `retries` 는 이런 걸 **초록으로 가린다** —
  게이트가 죽은 것보다 **가려진 플래키가 더 나쁘다**(살아 있는 것처럼 보이며 신호를 흘린다).
- **해야 할 일**: 나이틀리에서 **이 스펙이 반복 실패하면 위 관측을 근거로 즉시 파라.**
  그때 "알려진 플래키"로 뭉개지 마라 — 빈도가 올라갔다는 뜻이다.

## Next Actions

1. **#634 머지** → **sw 범프**(이 브랜치의 프론트 런타임 포함 필수) → **158 배포**(통합자)
   → 라이브 재검증: 로그인 폼 `method=post`(#632) · 신규 라우트 200
2. `project-release:66` 503 규명 — 해네스 분기는 있는데 요청이 안 잡히는 이유
3. `auth-dashboard`(온보딩 마법사 오버레이) · `collaboration-room` · `design-3d-viewer` 트리아지
4. **컴포넌트층 i18n 캠페인**(134파일·341개) — `fixme` 3건이 그 티켓이다
5. 미수정(보고만): `GET /projects/{id}/operations/status` 에 **인증 없음**

## 하지 말 것 (이 세션에서 실제로 데인 것)

- **"고쳤다"를 코드로 판단하지 마라.** 레지스트리를 고치고 회귀망까지 초록이었는데
  **DOM 은 그대로 한국어**였다 — 진짜 출처가 다른 파일이었다. e2e 를 다시 돌려서야 알았다.
- **`prettier` 를 파일 전체에 돌리지 마라.** 실변경 16줄이 서식 531줄에 묻히고
  변이감사가 소음으로 찬다.
- **변이 결과를 믿기 전에 대상이 대상인지 확인하라.** 3회 중 2회가 무효였고
  둘 다 내가 만든 오염이었다(전체 prettier · 브랜치 뒤처짐).
- **테스트가 결함을 요구할 수 있다.** 이 세션에서 2건 적발 —
  세 로케일 전부에 한국어를 요구한 정직성 테스트, `en` 을 렌더하며 한국어를 단언한 내비 테스트.
