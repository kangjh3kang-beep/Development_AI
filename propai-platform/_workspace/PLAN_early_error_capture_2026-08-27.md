# 계획 — 전역 오류 수집이 **초기 렌더 오류를 구조적으로 못 잡았다** (2026-08-27 · development-ai-f8)

> 한 줄: 오류가 **핸들러 등록보다 70ms 먼저** 난다. 그래서 성장루프가 `js_error` 를 볼 준비를
> 갖추고 있는데도 라이브에서 #418 이 나는 동안 **`js_error` 는 0건**이었다.
> **이 결함 클래스는 피드백루프가 영원히 신고할 수 없었다** — 사람이 프로브를 돌려야만 보인다.

## 0. 옵시디언 조회 (착수 전)

| 찾은 것 | 결과 |
|---|---|
| 이미 기각된 접근 | *"계측 헬퍼가 0건"*(2026-08-24) — **거짓**이었다. `trackEvent` 는 이미 있고 `api-client` 에 배선돼 있다. 이번에도 그 라벨을 승계하지 않고 **직접 쟀다** |
| 같은 클래스의 앞선 결함 | `#797` — *"1:1 일치라고 **선언**만 하고 강제가 0건"*. 이번 건은 그 형제: **수집은 되는데 그 창에서 안 보낸다** |
| 미결·부채 | 같은 세션의 `2026-08-27_대조군이_증명하는_것과_결론이_필요로_하는_것이_다르다` §9 |
| 이전 판단의 근거 | 내가 §9 에 *"추론"* 이라 적었고, **이 계획서를 쓰기 전에 관측으로 바꿨다**(아래 전제 3) |

## 1. 전제 표 (확인 방법 + **실제 측정값**)

| # | 전제 | 확인 방법 | 실제 값 |
|---|---|---|---|
| 1 | analyzer 가 `js_error` 를 **본다** | `git grep` — `analyzer.py:513` | ◎ `WHERE event_type IN ('js_error','api_error')` |
| 2 | 라이브에서 `js_error` 가 **안 온다** | `sendBeacon`/`fetch` **본문째** 가로채기 | 가로챈 요청 10 · **본문없음 0** · `#418` 1건 · **`js_error` 0건** · ★대조군 `api_call` **28건**(조회기 생존 증명) |
| 3 | ★**왜** 안 오는가 | `window.addEventListener` 를 감싸 등록 시각을, **가장 먼저 붙인 리스너**로 오류 시각을 같은 타임라인에서 측정 | **`#418` = 237ms** / **`addEventListener(error)` = 307ms** — **오류가 70ms 먼저** |
| 4 | 등록이 왜 늦나 | 소스 | `initEventCollector()` 호출이 `hooks/useGrowthEvents.ts` 의 **`useEffect`** 안(`lib/providers.tsx:37` 마운트) |
| 5 | `api_call` 은 왜 실리나 | 소스 | `lib/api-client.ts` 가 `trackEvent` 를 **직접** 부른다 → **수집기의 일부만 살아 있었다** |
| 6 | 형제 패턴이 있는가 | `grep dangerouslySetInnerHTML app/` | ◎ `app/layout.tsx:50` `themeBootstrap` — **문서 파싱 시점 인라인**(FOUC 방지). 같은 자리·같은 방식을 쓴다 |
| 7 | 백엔드가 payload 를 받는가 | `routers/growth.py` | `payload: dict \| None` — 자유 dict ◎ |
| 8 | ★이벤트 **타입 이름** | 형제 훑기 | `handleWindowError`=**`js_error`** / `handleRejection`=**`promise_rejection`** — **둘 다** 화이트리스트에 있다. 조기 flush 도 **갈라서** 보낸다 |
| 9 | 재현 조건 | 같은 라우트 2회 방문 | 1회차는 persist 가 비어 오류가 안 난다 — **2회차부터** |
| 10 | lint 래칫 | `npx eslint . --no-cache` | **error 0 · warning 158** = `lint-ratchet.json` 합계 158(증가 0) |

## 2. 변경 내용과 **회귀가 아닌 근거**

1. `lib/growth/early-error-bootstrap.ts`(신규) — 인라인 부트스트랩 문자열. 버퍼 상한 **20**.
   · 회귀 아님: 순수 상수 모듈. `try/catch` 로 감싸 실패해도 앱에 영향 0.
   · ★`app/layout.tsx` 안에 두지 않은 이유: 그 파일은 CSS 를 import 해 **vitest 에서 로드되지 않는다** —
     상수를 분리해야 **실제로 실행해서** 태울 수 있다(아래 잠금).
2. `app/layout.tsx` — `themeBootstrap` **바로 옆**에 `<script dangerouslySetInnerHTML>` 하나 추가.
   · 회귀 아님: 기존 스크립트와 같은 위치·같은 방식이고 DOM 을 건드리지 않는다(리스너만 등록).
3. `lib/growth/event-collector.ts` — `drainEarlyErrors()` export + `initEventCollector()` 가
   **정식 핸들러를 붙인 뒤** 버퍼를 비우고 **닫는다**.
   · 회귀 아님: 기존 핸들러·전송 경로 불변. 닫기 때문에 **이중 전송이 구조적으로 불가**하다.

## 3. ★검증하지 못한 것

- **라이브 확증은 배포 후**다. 배포 후 같은 라우트를 **2회** 방문해 `js_error`(`payload.early=true`)가
  실제로 전송되는지 beacon 본문으로 확인해야 최종 확정이다.
- 부트스트랩이 **실제 브라우저에서** 하이드레이션보다 먼저 실행되는지는 **구조로만** 논증했다
  (`themeBootstrap` 과 같은 자리 · 문서 파싱 시점). jsdom 실행 락은 *"이 스크립트가 오류를 잡는다"* 를
  증명하지만 *"프로덕션에서 더 빨리 실행된다"* 는 **배포 후 라이브**에서만 확정된다.
- 상한 20건을 **넘는** 초기 오류 폭주 시 버려지는 분량은 측정하지 않았다(상한 자체는 잠갔다).
- `web_vital` 등 `initEventCollector` 가 등록하는 **다른 수집**도 같은 창에 빠지는지는 **미측정**이다
  (이 PR 은 오류 두 종만 다룬다).

## 4. 되돌리기 경로

`git revert` 한 번. 세 파일 전부 **추가**이고 기존 경로를 바꾸지 않는다.

## 5. 잠금 — 무엇이 이 변경을 지키는가

| 잠그는 것 | 어디서 | 필수 CI |
|---|---|---|
| 부트스트랩이 **실제로 오류를 잡는다**(문자열 검사가 아니라 `new Function` 으로 **실행**) | `lib/growth/__tests__/early-error-capture.test.ts` | ◎ vitest |
| **음성 대조군** — 부트스트랩을 안 돌리면 아무것도 안 담긴다(위 검사가 공허하지 않다) | 같은 파일 | ◎ |
| 상한(20) · `unhandledrejection` 도 담김 | 같은 파일 | ◎ |
| `drainEarlyErrors` 가 **비우고 닫는다** — 닫힌 뒤엔 더 안 쌓인다(**이중 전송 차단**) | 같은 파일 · 두 모집단 | ◎ |
| **배선(런타임)** — `initEventCollector()` 가 그 버퍼를 실제로 비운다(“부른다”가 아니라 **효과**) | 같은 파일 · 전제 가드 선행 | ◎ |
| **이벤트 타입 정합** — error→`js_error` / rejection→`promise_rejection` 이 **둘 다** 나간다(전송 본문 파싱) | 같은 파일 · 전제 가드 선행 | ◎ |
| **배선(소스)** — 루트 layout 이 그 스크립트를 렌더한다(AST · 양성 대조군 `themeBootstrap` 선행) | 같은 파일 | ◎ |

★**한계를 적어 둔다**: 마지막 항목은 *"계약이 코드에 남아 있는지"* 만 본다. 브라우저에서 실제로
실행되는지는 §3 대로 **배포 후 라이브**에서 확인한다.
