# 전역 오류 경계가 **자기 오류를 배달하지 못했다** — 계획서

- 세션: `development-ai-9d [088a1a]` · 브랜치 `fix/global-error-event-orphan`
- 인계: SESSION-F8 「배달 경로 갭」의 **범위를 좁혀** 실측한 결과
- 작성 시각: 2026-08-27 16:2x KST (★아래 라이브 수치는 **그 시점의 사실**이다)

---

## 0. 옵시디언 조회 결과 (착수 전)

| 찾을 것 | 결과 |
|---|---|
| **이미 기각된 접근** | **없음.** 「배달 경로 갭」은 `AI-Sessions/conversations/2026-08-27_…SESSION-F8.md:123-125` 에 **미착수 후보**로만 있고 기각 이력 0건 |
| **같은 클래스의 앞선 결함** | 있음 — `errors/2026-08-27_대조군이_증명하는_것과_결론이_필요로_하는_것이_다르다.md:277` 이 `drainEarlyErrors` 가 버퍼를 **닫는다**는 것을 이미 적어 뒀다. 그리고 메모리 `feedback_a_safety_net_that_never_fired_is_not_a_safety_net`(존재 ≠ 발화)·`feedback_lock_the_behavior_not_the_call`(「부른다」를 잠그면 아무것도 안 잠긴다)가 **이 결함의 정확한 형태**를 예보하고 있었다 |
| **미결·부채** | `promise_rejection` analyzer 소비처 0건(별건, 이 PR 범위 밖) |
| **이전 판단의 근거** | 인계 문장의 출처는 `_workspace/PLAN_early_error_capture_2026-08-27.md:72` 의 **「★검증하지 못한 것」** 항목이었다. ★즉 **미검증 라벨이 다음 세션에서 「구조적 사실」로 승격**됐다(§증거 규율 7). 그래서 승계하지 않고 다시 쟀다 |

---

## 1. 전제 표 — **확인 방법과 실제 측정값**

| # | 전제 | 확인 방법 | **실제 결과** |
|---|---|---|---|
| P1 | `flush()` 를 구동하는 것이 무엇인가 | `event-collector.ts` 에 `flush(` **파생형 전수** grep | **4곳뿐**: `:253`(임계 `ring>=20`) · `:285`(정의) · `:482` `handleVisibility` · `:544` `teardown` |
| P2 | 그 구동자들이 어디서 등록되나 | 같은 파일 `addEventListener`/`setInterval` 위치 | `visibilitychange :527` · `pagehide :528` · `setInterval :532` — **전부 `initEventCollector()` 안** |
| P3 | 모듈 로드만으로 등록되는 것이 있나 | 모듈 스코프 부작용 grep | **0건** — import 만으로는 아무것도 안 붙는다 |
| P4 | `global-error.tsx` 가 루트 레이아웃을 대체하나 | 원문 확인 | **그렇다** — `<html><body>` 를 **직접 렌더**한다(`:35-36`). 즉 `AppProviders→AppStateBridge→useGrowthEvents→initEventCollector` 가 없다 |
| P5 | 그래서 실제로 배달이 안 되나 | **3모집단 vitest**(손 `flush()` 금지, 타이머 30초 + `pagehide` + `visibilitychange` 전부 발화) | 양성 대조군 **PASS** / ①초기로드 크래시 **0건** / ②teardown 뒤 **0건** |
| P6 | ②의 순서가 실제로 그러한가 | `teardownEventCollector` 원문 | `flush()` 로 링을 **비운 뒤**(`:544`) 리스너 제거·`clearInterval` → 그 **뒤에** 경계가 1건 push |
| P7 | 다른 경계들은 계측하고 있나 | `app/**/error.tsx` **파생형 전수** `grep -c trackEvent` | **9곳 중 8곳이 0건**(`(dashboard)/error.tsx` 만 2건) |
| P8 | 경계가 없는 라우트군이 있나 | `app/[locale]/*` 그룹별 `error.tsx` 개수 | `(auth)` **0** · `(fieldapp)` **0** · `legal` **0** · `(dashboard)` 9 |
| P9 | 샘플링·화이트리스트·인증이 막지 않나 | `SAMPLE_RATES`(`:80-86`) · 백엔드 `_ALLOWED_TYPES` · `ingest_events` 의존성 | `js_error` **미등재 → 기본 1.0(전수)** · 화이트리스트 등재 · **익명 허용** — 셋 다 원인 아님 |
| P10 | `#898` 이 라이브에 있나(선행 캠페인 마무리) | `sw.js` `^const CACHE_NAME` + `merge-base --is-ancestor` | 16:07:37 **배포 확인**(`live=4be45f90`). 라이브 프로브 **3회 전부 `exit 0 · verdict true`** |

★**P5 가 이 계획서의 핵심이다.** P1~P4 는 구조 논증이고, 그것만으로 결론냈다면 추론이다. 실제로 태워서 **0건**을 봤고, **양성 대조군을 같은 실행에 두어** 「프로브가 죽어서 0」을 배제했다.

---

## 2. 변경 내용과 **회귀가 아닌 근거**

1. **신규** `lib/growth/report-boundary-error.ts` — 경계 공용 보고기.
   `initEventCollector()`(멱등) → `trackEvent("js_error", …)` → `flush()`.
2. **배선** 경계 **10곳 전부**(`global-error.tsx` + `app/**/error.tsx` 9개)가 이 보고기를 부른다.
   `scope` 는 **파일 경로에서 파생**했다(손으로 나열하면 그 목록이 곧 상한이 된다).
3. `(dashboard)/error.tsx` 의 기존 `trackEvent` 직접 호출은 보고기로 **교체**했다.

**회귀가 아닌 근거**
- `initEventCollector()` 는 `if (initialized) return` 으로 **멱등**이다(`:494`). 정상 마운트 경로에서 이미 초기화돼 있으면 아무 일도 하지 않는다.
- 보고기 전체가 `try/catch` 다 — 계측 실패가 **오류 화면을 다시 깨뜨리지 않는다**.
- 8곳은 원래 계측이 **0건**이었으므로 이벤트가 늘 뿐 줄지 않는다.
- 회귀 실측: `lib/growth/__tests__/` + `lib/__tests__/` + `lib/hydration/__tests__/` = **66파일 675 passed · 실패 0**(기준선 `rc=0`).
- `pnpm type-check`(**CI 명령 그대로**) `EXIT=0` · `eslint` `EXIT=0`(경고 8건은 전부 **내가 손대지 않은** `page.tsx` 들의 기존 `react-hooks/*`).

---

## 3. ★검증하지 못한 것 (정직하게)

- **라이브 확증 미완.** 이 수정이 프로덕션에서 실제로 `scope=global-error` 이벤트를 실어 오는지는 **배포 후에만** 판정된다. 배포 전 판정 수단이 없다 — `#893` 이 정확히 그 자리에서 났다.

- ★★**이 PR 이 덮지 못하는 경로가 있고, 그것이 실측으로 확인됐다.**
  독립 렌즈(내 관측 아님 — 출처를 밝힌다)가 라이브에서 A/B 를 돌렸다(각 6회, 새 컨텍스트):

  | | A 정상 | B `_next/static/chunks/**.js` 전면 `route.abort()` |
  |---|---|---|
  | `__propaiEarly.closed` | `true` **6/6** | `false` **6/6** |
  | beacon 호출 | ≥1 **6/6** | **0건 6/6**(`api_call`·`page_view` 포함 **전부**) |

  **두 모집단이 잡음 0으로 완전 분리**됐다. 그런데 **B 는 이 PR 이 고칠 수 있는 경로가 아니다** —
  청크가 없으면 React 가 아예 부팅하지 않고, 그러면 `global-error.tsx`(클라이언트 컴포넌트)도
  **렌더되지 않는다**. 즉 이 PR 은 **「React 가 떴다가 깨지는」 경로**를 닫고,
  **「React 가 아예 안 뜨는」 경로**는 열린 채로 둔다. 그 경로의 유일한 처방은 인라인 부트스트랩
  안의 전송인데, 독립 적대 리뷰가 그것을 **REJECT** 했다(오리진·마스킹·세션키·이벤트타입 SSOT 를
  전부 복제해야 하고 전부 무잠금이며, 빌드 산출물을 태우는 CI 게이트가 **없다** — `#893` 이 난 자리).
  ★**B 는 인위적 상한 시뮬레이션이다**(청크를 강제로 전부 끊었다). **자연발생 빈도는 미측정**이며,
  그것을 재기 전에는 그 처방의 비용/편익을 판정할 수 없다.

- ★**독립 리뷰가 잡은 것 — 내 자기평가가 틀렸다.** 초판에서 *"변이 6/6 CAUGHT(두 층)"* 이라고
  썼는데, **내가 고른 변이에만 참**이었다. 리뷰가 넣은 변이 6종 중 **5종이 생존**했다:
  死코드(`if (String(1)==="2") report(…)`) · **별칭 임포트**(`trackEvent as trackEventAlias`) ·
  `message`/`severity`/`digest` 삭제. 근본은 **경계 컴포넌트를 임포트·렌더하는 테스트가 0건**이라
  그 층이 어떤 변이든 자동 생존이었던 것이다.
  → 봉합: `boundary-render-delivery.test.tsx`(경계를 **실제로 렌더**) 신설 · (역) 락을
  **임포트 선언**으로 전환(별칭 우회 차단) · payload 3필드 못 박음.
  ★**남는 교훈**: 「N/N CAUGHT」를 말하기 전에 **몇 개 층에 넣었는지**를 먼저 답해야 한다.

- ★**파생 축이 「에러 경계」가 아니라 「파일명 `error.tsx`」였다**(독립 리뷰 적발).
  목적 기반으로 다시 조회하니(`getDerivedStateFromError|componentDidCatch` 전수) 클래스 경계
  **2개가 축 밖**이었다 — `components/common/MapShell.tsx`(오류를 **가둔다** → 상위 `error.tsx` 가
  구조적으로 볼 수 없다 · 소비처 8곳 · 지도/타일은 최빈 파손면) ·
  `components/projects/HubErrorBoundary.tsx`(`console.error` 만 = 브라우저 밖으로 안 나감).
  → 봉합: 둘 다 배선하고 **락의 파생 축을 「경계 훅을 가진 파일 ∪ `error.tsx`」로 넓혔다.**
  축이 좁아지면 즉시 실패하도록 **전제 케이스**를 따로 뒀다.

- **첫 청크 오류는 여전히 텔레메트리 0건**(리뷰 M4 · **미수정 부채**). 경계 10곳 모두
  `if (tryRecoverFromChunkError(error)) return;` 이 보고기 **앞**에 있어, 배포 직후 열린 탭의
  첫 청크 404 는 한 건도 안 남는다. `#893`·`#898` 이 정확히 그 자리였다.

- **`registerWebVitals()` 익명 `visibilitychange` 리스너 누수**(리뷰 M2 · **선행 결함이나 이 PR 이
  도달 경로를 넓힌다**). `teardownEventCollector` 는 `handleVisibility` 만 제거하고 익명 3개는
  영구 잔존한다. 케이스 ②(teardown 뒤 보고기가 `initEventCollector()` 재실행)에서 3개가 더 붙는다.
  **미수정** — 이 PR 범위 밖이나 부채로 명시한다.

- **`promise_rejection` analyzer 소비처 0건**(독립 렌즈가 목적 기반 전수로 확증 — `analyzer.py` 의
  분석함수 6종 `WHERE event_type IN (…)` 전수에 부재. 진입점 `main.py:665` 는 실재하므로
  *"라우터만 보고 미배선"* 함정은 아니다). **별건 부채** — 이 PR 범위 밖.
- **유실 비중 미측정.** 「경계가 뜨는 빈도」와 「그중 몇 %가 유실됐나」를 잴 조회 수단이 없다. `GET /growth/insights` 는 **집계**만 주고 원본 `platform_events` 조회 라우트가 없다. 따라서 이 결함의 **영향 규모는 미측정**이다(구조적 확실성과 규모는 다른 명제다).
- **경계가 아예 없는 라우트군**(`(auth)`·`(fieldapp)`·`legal`, P8)에 경계를 **추가하지 않았다.** 그 라우트의 실패는 `global-error` 로 떨어지므로 이 PR 로 **배달은 살아나지만**, 어느 화면이었는지는 `scope=global-error` 하나로 뭉친다. 별건 부채.
- **큐 적재 층 미측정.** `ingest_events` 는 큐 push 만 하고 DB 적재는 워커가 한다(`routers/growth.py:9` 자체 주석). 200 을 받아도 워커가 실패하면 안 남는다 — **이 PR 이 닿지 않는 다른 층**이다.
- **`sendBeacon` 64KiB 예산 미측정.** 조기 버퍼 최악치(20건 × 10,000자 ≈ 200KB)가 예산을 넘으면 통째로 안 나갈 수 있다. **기존 drain 경로에 이미 있는 형제 결함**이며 이 PR 은 그것을 고치지도 악화시키지도 않는다.
- **백엔드 마스킹 비대칭 미수정.** 프론트 `maskString` 은 주소를 지우는데 백엔드 `_mask_str` 에는 주소 정규식이 없다(독립 리뷰 실측). 별건.
- **`filename` 이 백엔드에서 `[redacted]` 될 가능성** — `_PII_KEYS` 의 `"name"` 이 **부분일치**로 `filename` 을 잡는다는 지적이 있었다. **내가 직접 재지 않았다 — 미측정.**

---

## 4. 되돌리기 경로

단일 커밋 revert 로 끝난다. 신규 파일 2개(보고기·락)와 경계 10곳의 한 줄 배선뿐이고,
런타임 계약·스키마·DB 변경이 **없다**. 되돌리면 정확히 이전 동작(=계측 누락 + 배달 실패)으로 복귀한다.

---

## 5. 잠금 — 이 변경을 지키는 검사

| 락 | 파일 | 무엇을 잠그나 |
|---|---|---|
| **행위** | `lib/growth/__tests__/global-error-delivery.test.ts` | 「불렸다」가 아니라 **「그래서 나갔다」**. `flush()` 를 **손으로 부르지 않고** 제품이 가진 구동자만으로 배달되는지. 양성 대조군 + 결함 2모집단 + **조기 버퍼 배달**(인계서의 원래 갭) |
| **배선(정)** | `lib/__tests__/error-boundary-report-wiring.test.ts` | `app/**/error.tsx`+`global-error.tsx` **파생형 전수**가 실행되는 줄에서 보고기를 부른다(주석 제거 후 검사) |
| **배선(역)** | 같은 파일 | ★**어떤 경계도 `trackEvent` 를 직접 부르지 않는다** — 결함이 살던 자리. 한 방향만 걸면 반대 방향이 원리적으로 탐지 불가다 |
| **식별** | 같은 파일 | `scope` 가 경계마다 **서로 다르다**(복붙 방지) + 파생 개수 == 파일 개수(공허 진리 가드) |

★**공허 진리 가드**: 배선 락은 단언 **전에** `files.length > 5` 를 먼저 단언한다 — 「위반 0」이 「대상 0」때문에 참이 되는 것을 막는다.
