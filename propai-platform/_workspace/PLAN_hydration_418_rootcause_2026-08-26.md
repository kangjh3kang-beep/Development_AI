# PLAN — React #418 근본원인 재특정과 봉합 (2026-08-26)

> 전임 세션(SESSION-E)이 남긴 최대 미결(§2)이다. 그 세션은 **자기 예측이 반증된 것**을 정직히
> 적어 두고 원인을 "상관이지 인과가 아니다"로 넘겼다. 이 계획은 그 상관을 **인과로 확정하거나
> 기각**하는 것이 목표였고, 결과는 **기각 + 다른 원인 확정**이다.

## 0. 옵시디언 조회 결과

| 찾은 것 | 내용 |
|---|---|
| **이미 기각된 접근** | `#850`(피커 노드 유무 게이트) — 배포 후 예측(오류 0)이 **반증**됨. "왜인지 모른다"로 남음 |
| **같은 클래스의 앞선 결함** | 2026-08-13 `LifecycleProgressRail` — 진행도 배지 서버 0 / 클라 1 |
| **미결·부채** | `e2e/hydration-lifecycle-rail.spec.ts` 의 `test.fixme` — *"persist 파생값 잔여 소비처 스윕"*. `ContextHeader` 가 이름으로 적혀 있었다 |
| **이전 판단의 근거** | `errors/2026-08-26_내_예측이_반증됐다_…` · `…_측정도구가_지운다고_말하고_안_지운다_…` — 측정법(증분·대조군 2종)과 그 한계(소프트/하드 내비 미구분)까지 기록돼 있었다 |

★그 부채 목록의 **전제 자체가 틀렸다**는 것이 이번 조사의 결론이다(§2).

## 1. 전제 표 — 확인 방법과 **실제 측정값**

| # | 전제 | 확인 방법 | 실제 결과 |
|---|---|---|---|
| P1 | 인계서의 "4/4 상관"이 유효하다 | 각 라우트 HTTP 상태 실측 | **거짓** — `/ko/dashboard` 는 **404**(라우트 파일 부재). 음성 대조군 하나가 무효라 유효 3점 |
| P2 | persist 셀렉터 읽기가 불일치를 만든다 | `zustand@5.0.12/react.js` 원문 + 실행 테스트 | **거짓** — `useSyncExternalStore(subscribe, getState, **getInitialState**)`. 실행 확인: 스토어를 42로 채워도 셀렉터 서버렌더는 **0**, `getState()` 직접 읽기는 **42** |
| P3 | 라이브에 #418 이 아직 있다 | Playwright · 한 컨텍스트 연속 하드 내비 | **참** — `/ko/regulations` 1 · `/ko/permits` 1 · `/ko/mypage/profile` 0 · 재방문에서도 1(재현성) |
| P4 | 서비스워커 캐시가 원인이다 | `serviceWorkers:'block'` 대조 | **거짓** — 차단해도 1건 |
| P5 | 회차마다 새 컨텍스트로도 재현된다 | 새 컨텍스트 5회차 | **거짓** — 0건. 재현 조건은 **한 세션 안의 연속 내비** |
| P6 | 원인 컴포넌트를 특정할 수 있다 | 라이브 localStorage 를 로컬 `next dev` 에 이식 → React 개발 모드 diff | **참** — `<GlobalAddressSearch>` 안의 요약 배지 `+77필지 / -대기` |
| P7 | 수정 후 재현이 사라진다 | 같은 프로브 재실행 | **참** — 하이드레이션 오류 **1 → 0** |
| P8 | 기능이 보존된다 | 재수화 뒤 배지 텍스트 단언 | **참** — `77필지` 그대로 |
| P9 | 새 린트 경고가 없다(#858 래칫) | ★**전수** `npx eslint .` + `scripts/ci/lint_ratchet.py` | **참(정정 후)** — 경고 158/래칫 158 · **error 0** · 린트 파일 1073. ★초판은 **변경 파일만** 재서 이 PR 이 새로 만든 파일을 빼먹었고, 그 신규 파일이 **error 1**(`prefer-const`)을 내 필수 CI 를 빨갛게 만들 뻔했다(독립 리뷰 실측). 자기 검증에서 **자기가 선언한 "파생형" 원칙을 어긴 것**이다(§D-16) |
| P10 | 타입 안전 | `tsc --noEmit --incremental false` | **참** — EXIT=0 |

## 2. 변경 내용과 **회귀가 아닌 근거**

`apps/web/components/common/GlobalAddressSearch.tsx`
- 초기값 산출을 **순수 함수** `buildInitialAddressEntries(...)` 로 분리(스토어를 스스로 읽지 않는다).
- `useState` 지연 초기값은 **서버가 계산할 수 있는 것만**(`parcels: undefined`) 쓴다.
- 컨텍스트 다필지 시드는 **마운트 이펙트 1회**로 옮긴다(`prev.length >= 2` 면 덮지 않는다).

무회귀 근거:
- `addresses` 를 읽는 자리는 **전부 `useCallback`/`useMemo`** 이고 **마운트 이펙트 소비자가 없다**.
  ★초판은 *"dep 3곳"* 이라 적었는데 실제 **5곳**이다 — 패턴 `[addresses` 가 **배열 첫 원소일 때만**
  잡아서다(독립 리뷰 실측). **결론은 그대로 참**이지만 근거가 틀렸다: 다섯 곳 전부 콜백/메모이고,
  이 파일의 `useEffect` 는 이 PR 이 새로 넣은 **1개뿐**이다. *틀린 근거로 맞는 결론에 간 사례*로 남긴다.
- 렌더만 가리지 않고 **상태 자체를 서버와 맞췄으므로** `selectedSatongFeatures` 같은 다른 파생
  소비처까지 함께 안전해진다(부분 적용 회피 — 저장소 §D-20).
- 기능 보존은 라이브 재현 환경에서 **배지 값으로 단언**했다(P8).

문서 정정(`hooks/useHydrated.ts` · `e2e/hydration-lifecycle-rail.spec.ts`)
- *"persist 파생값을 SSR 경로에서 렌더하면 위험"* 이라는 **과잉 일반화**를 정정한다.
  그 문장이 `#850` 을 결함 아닌 곳으로 보냈다. 진짜 위험은 **스냅샷 우회 3종**이다.

## 3. ★검증하지 못한 것

- **클래스 ②(렌더 중 스토어 메서드 호출)** — 래칫으로 동결. **일부는 잰다:**
  · **실측**: `/ko/projects/<id>` · `…/finance` · `…/permit` = **하이드레이션 0건**.
    ★같은 하네스에서 결함을 되살리면 `regulations`·`finance`·`permit` 이 각 1건 →
    **대조군이 살아 있는 상태의 0** 이다. 그 라우트의 `NextStageCta`·`ProjectLifecyclePipeline` 은
    지금은 불일치를 내지 않는다(형제 e2e 주석의 *"스피너로 가려짐"* 가설과 일치하나 그 가설은 미검증).
  · **미측정**: 프로덕션 번들 · 나머지 소비 라우트 6종 · `ProjectHealthBoard` · `BoqAutoWorkspace` ·
    `FeasibilityEditorV2` · `OrchestratorPanel` · `InputResolveModal`(조작 뒤 렌더) ·
    `AuthWorkspaceClient`(시도 → 결론 불가).
- **왜 새 컨텍스트에서는 재현되지 않는가**(P5) — 모른다. 그럴듯한 설명을 붙이지 않는다.
- `#850` 본문의 *"로컬 프로덕션 빌드 변이로 1→0 확정"* 이 왜 그렇게 관측됐는지 — 여전히 미상.
  다만 그 수정 대상이 셀렉터 읽기였음은 이제 확정이므로 **그 주장은 성립하지 않는다.**
- 라이브 배포 후 재측정은 **배포 뒤에만** 가능하다(이 저장소는 배포를 요청만 한다).
- 프론트 전수 vitest 결과는 커밋 시점 로그로 첨부한다(별도 확인).

### 독립 리뷰가 추가로 드러낸 미검증(초판 §3 에 **빠져 있었다**)

1. **린트 측정 모집단이 신규 파일을 뺐다** → 위 P9 로 정정(전수 재측정).
2. **"전수"가 전수가 아니었다** — git pathspec `lib/**/*.ts` 는 **디렉토리 직속 파일을 강제로 제외**한다
   (`hooks/` 12개·`store/` 17개·`lib/` 직속 104개 등 **164파일**). 파생 방식을 `git ls-files '*.ts' '*.tsx'`
   로 바꾸고, 테스트 ①에 **명시 대조군 5파일**을 넣어 같은 구멍이 나면 시끄럽게 실패하도록 했다.
   (모집단 530 → **695**)
3. **전제 잠금이 persist 를 안 태웠다** — `create()` 만 썼다. persist 픽스처로 교체하고,
   `zustand/middleware` 의 `api.getInitialState = () => configResult` 를 지우는 변이로 **CAUGHT** 확인.
   ★그 전에는 그 한 줄을 지워도 초록이었다(= 전제가 무잠금). ★근거도 정정했다 —
   `useSyncExternalStore` 세 번째 인자는 **필요조건이지 충분조건이 아니다.**
4. **검출기가 알 수 없는 고차함수를 통째로 버렸다** — 조상 탐색 루프가 **한 번도 상승하지 않아**
   `.map` 콜백·중첩 화살표·모듈 헬퍼가 전부 위음성이었고, 그 사실을 **eslint `prefer-const` 가
   이미 신고**하고 있었다(린트 결함과 논리 결함이 같은 줄). 고친 뒤 **리뷰가 지목한 진짜 자리**
   `InputResolveModal.tsx:149`(`hasRealSlotValue`)가 실제로 잡혔다.
5. **다필지 시드의 기능 보존은 이 PR 의 락이 아니라 기존 테스트**(`GlobalAddressSearch.jibunLabel.test.tsx`)
   가 우연히 잡고 있다 — 변이로 CAUGHT 는 확인했으나 **의도된 잠금은 아니다.**
6. **미기재 동작 변경**: `parcels.length >= 2` 인데 `p.address || p.pnu` 필터 후 1건만 남는 경우,
   구코드는 그 1건을 채택했고 신코드는 `seeded.length >= 2` 게이트에서 걸러 `initialAddress` 로
   대체된다. **드문 경계**이고 그 상태는 애초에 "다필지"가 아니지만, **회귀가 아니라고 단정하지 않는다.**
7. **로그인 셸(`AuthWorkspaceClient`)의 `hasStoredRefreshToken()`** 라이브 측정 시도 → **결론 불가**.
   회차마다 새 컨텍스트로 재는 구성은 **알려진 양성도 재현하지 못한다**(같은 세션 실측).
   그러므로 그 "0건"은 부재의 근거가 아니다 — 래칫에만 등재했다.

## 4. 되돌리기

단일 커밋 revert. 되돌리면 `GlobalAddressSearch` 가 초기 렌더에서 다시 라이브 스토어를 읽고,
`lib/hydration/__tests__/render-path-store-reads.contract.test.ts` 의 **하드 게이트가 빨개진다**
(= 되돌림이 조용하지 않다).

## 5. 잠금 — 이 변경을 지키는 검사

| 검사 | 무엇을 잠그나 |
|---|---|
| `lib/hydration/__tests__/zustand-server-snapshot.contract.test.tsx` | **전제**: 셀렉터=서버 스냅샷 / `getState()`=라이브. 두 모집단이 갈리는지 대조군 포함 |
| `components/common/__tests__/GlobalAddressSearch.hydration.test.tsx` | **행위**: 스토어에 77필지가 있어도 서버 HTML 은 `대기`. 공허 진리 가드(배지 존재) 포함 |
| `lib/hydration/__tests__/render-path-store-reads.contract.test.ts` | **전수·파생형**: ①모집단(>600파일 + **명시 대조군 5파일**) ②탐지(양성 **11형태**) ③특이도(음성 **6형태**) ④**비성장 래칫**(파일→호출자→**건수**까지) + **증가·죽은 면제 모두 실패** ⑤고친 자리는 래칫에 없음(되돌리면 "새로 생김"으로 잡힌다) |
| `e2e/support/hydration-probe.mjs` | 다음 사람이 **같은 방법으로 다시 잴 수 있게** (대조군 2종 내장) |

★**정정(2026-08-27 · 독립 리뷰 F7)**: 초판은 여기에 *"전부 **필수 CI**(vitest)에서 돈다"* 라고 적었는데
**마지막 행(`e2e/support/hydration-probe.mjs`)에 대해서는 거짓**이었다 — `vitest.config.ts` 가
`e2e/**` 를 수집에서 제외하므로 **어떤 러너도 그 파일을 태우지 않는다.** 잠금표에 실으면서
"전부 CI"라고 쓴 것은 §C-11(면역을 거짓 주장하지 마라) 위반이다.

정확히는:
- 앞 세 행(`zustand-server-snapshot` · `GlobalAddressSearch.hydration` · `render-path-store-reads`)
  → **필수 CI(vitest)에서 돈다.** `#850` 의 잠금이 나이틀리 e2e 였던 것과 다르다.
- `e2e/support/hydration-probe.mjs` → **사람이 명령을 쳐야 도는 진단 도구**다. CI 게이트가 아니다.
  그 판정 순수부(`countHydration`·`samePath`·`pickMutableText`)는 `lib/hydration/probe-text.mjs` 로
  분리해 `lib/hydration/__tests__/probe-text.test.ts` 가 **필수 CI 에서** 잠근다(후속 PR).
  브라우저를 태우는 부분은 여전히 **무잠금**이며, 그 사실을 여기 남긴다.
