# 계획 — 하이드레이션 프로브의 **측정 모드가 실행 불가**였다 (2026-08-27 · development-ai-f8)

> 한 줄: `control`(대조군) 모드는 통과하는데 **`run`(측정) 모드가 `ReferenceError` 로 즉시 죽는다.**
> 그래서 **도구가 살아 있어 보였다** — 대조군이 증명한 것은 "이 프로브가 #418 을 잡는다" 뿐이고
> **"측정 경로가 실행된다"** 는 아무도 증명하지 않았다.

## 0. 옵시디언 조회 (착수 전)

| 찾은 것 | 결과 |
|---|---|
| 이미 기각된 접근 | `#850` 의 *"피커(노드 유무) 수정"* 이 **반증**됨(에러는 `args[]=text`) — 승계하지 않음 |
| 같은 클래스의 앞선 결함 | `2026-08-27_경고는_산문이고_판정이_산출물이다` — **도구가 못 믿는 값으로 판정을 발행**한 사례. 이번 건은 그 형제(**측정 경로가 아예 죽었는데 대조군 경로만 통과**) |
| 미결·부채 | SESSION-H-web 인계 §3 의 「클래스② 13자리/8파일 — 래칫 동결만」 |
| 이전 판단의 근거 | 인계서가 `run` 명령을 *"그대로 쓸 것"* 으로 넘겼다 — **그 명령이 돌지 않는다**(§1 실측) |

★신선도: 인용한 파일·함수·명령은 전부 이 PR 브랜치(`origin/main` = `0efda714`)에서 **재실행해 확인**했다.

## 1. 전제 표 (확인 방법 + **실제 측정값**)

| # | 전제 | 확인 방법 | 실제 값 |
|---|---|---|---|
| 1 | `run` 모드가 실행된다 | `node e2e/support/hydration-probe.mjs run <경로…>` | ✘ **`ReferenceError: NOISE_RE is not defined` (hydration-probe.mjs:164)** · 종료코드 1 |
| 2 | `control` 모드는 산다 | `… control /ko/permits` | ◎ `hydration:1` · `args[]=text` · exit 0 |
| 3 | 음성 대조군도 산다 | `PROBE_NO_MUTATE=1 … control /ko/permits` | ◎ `hydration:0` · exit 0 |
| 4 | `NOISE_RE` 의 실제 소재 | `grep -rn NOISE_RE e2e/ lib/` | `lib/hydration/probe-text.mjs:12` — **export 되지 않은 모듈 지역 상수** |
| 5 | eslint 가 이 파일을 보는가 | `npx eslint e2e/support/hydration-probe.mjs` | 파일은 봄 · **위반 0 · exit 0** |
| 6 | 왜 못 봤나 | `npx eslint --print-config <파일>` → `rules["no-undef"]` | **`(미설정)`** |
| 7 | `tsc` 가 보는가 | `.mjs` 는 `tsconfig` 대상 아님 | 미대상 |
| 8 | 순수부 테스트가 태우는가 | `lib/hydration/__tests__/probe-text.test.ts` | **스크립트 자체를 import 하지 않는다**(순수 함수만) |
| 9 | `.mjs` 모집단 | `git ls-files '*.mjs'` | **5건**(hydration-probe · probe-text · eslint.config · next.config · postcss.config) |
| 10 | 새 규칙의 기존 위반 | `npx eslint '**/*.mjs'`(수정 후) | **0건 · exit 0** — 래칫 부담 없음 |
| 11 | ★그 규칙이 **원결함을 잡는가** | 원결함 재주입 후 같은 명령 | ◎ **`164:38 error 'NOISE_RE' is not defined no-undef` · exit 1** |

★11 번이 이 계획의 중심이다 — **수정 전 상태에서 락이 빨간 것**을 확인했다(초록만 보면 공허할 수 있다).

## 2. 변경 내용과 **회귀가 아닌 근거**

1. `lib/hydration/probe-text.mjs` — `relevantErrors(lines)` 를 **export** 하고 `countHydration` 이
   그것을 경유하게 한다. **필터는 하나**가 되어 계수와 진단 표시가 갈리지 않는다.
   · 회귀 아님: `countHydration` 의 **동작이 동일**하다(같은 `NOISE_RE`·`HYDRATION_RE`). 기존 26건 초록 유지.
2. `e2e/support/hydration-probe.mjs` — import 에 `relevantErrors` 추가, 164줄이 그것을 쓴다.
   · 회귀 아님: 그 줄은 **진단 `sample` 출력에만** 쓰인다. `hydration` 계수는 이미 `countHydration` 독립.
3. `eslint.config.mjs` — `**/*.mjs` 에 **`no-undef: error`**.
   · 회귀 아님: 전제 10(기존 위반 0). globals 목록이 부족하면 **위양성으로 시끄럽게** 드러난다(조용한 위음성 아님).

## 3. ★검증하지 못한 것

- **왜 `run` 모드가 한 번도 실행되지 않은 채 머지됐는지**는 재지 않았다(추정하지 않는다).
- ★**정정**: 초판은 `globals` 18개를 손으로 나열하고 그 옆에 *"목록형의 한계를 알고 쓴다"* 고
  적었다. **변이 M6(`document` 제거)이 SURVIVED** 해서 재보니 `--print-config` 기준 이미
  **1174개**가 상위 config(`eslint-config-next`)에서 오고 있었다 — 내 목록은 **전부 중복**이었고
  그 주석은 **거짓 전제**였다. 목록을 걷어냈다. **변이가 아니었으면 거짓이 그대로 남았다.**
- `next.config.mjs`·`postcss.config.mjs` 는 이 규칙 아래에서 **지금** 초록일 뿐, 그 파일들이 쓰는
  전역이 늘어날 때의 거동은 **미측정**이다.
- 이 PR 은 **프로브를 고칠 뿐** 하이드레이션 결함 자체를 고치지 않는다(그 트리아지는 별건).

## 4. 되돌리기 경로

세 파일 전부 순수 추가/치환이라 `git revert` 한 번으로 원복된다. 런타임 코드(앱 번들) 변경 **0**
— `e2e/`·`lib/hydration/probe-text.mjs`(앱 import 0건)·eslint 설정뿐이다.

## 5. 잠금 — 무엇이 이 변경을 지키는가

| 잠그는 것 | 어디서 | 필수 CI |
|---|---|---|
| **스크립트의 미정의 참조**(이번 결함 클래스 전체) | `eslint.config.mjs` `no-undef` on `**/*.mjs` | ◎ Frontend(lint) — 차단 게이트 |
| `relevantErrors` 가 **두 모집단을 가른다**(잡음은 지우고 나머지는 남긴다 · 양방향) | `lib/hydration/__tests__/probe-text.test.ts` | ◎ Frontend(vitest) |
| `countHydration` 이 `relevantErrors` 와 **정합**(기대값을 다른 경로로 파생) | 같은 파일 · 공허진리 가드 포함 | ◎ |
| **`no-undef` 가 꺼지거나 `warn` 으로 낮춰지는 것**(선언이 아니라 **동작**을 태운다) | `__tests__/eslint-mjs-undef.contract.test.ts` | ◎ Frontend(vitest) |

★**같은 규율을 두 곳에 두지 않는다** — "실행 가능성"은 `no-undef` 가 잠그고, vitest 는
그 위의 **동작 계약**만 본다.
