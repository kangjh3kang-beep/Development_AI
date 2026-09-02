# 계획 — 수지 완성도 배지가 **서버와 클라에서 다른 말을** 했다 (2026-08-27 · development-ai-f8)

> 한 줄: `FeasibilityEditorV2` 가 persist 스토어 **메서드**를 렌더 중 호출해 서버 스냅샷을 우회했다.
> 서버 `0% · 부지 대기` / 클라 `60% · 부지 반영` → 프로덕션 `Minified React error #418 (args[]=text)`.

## 0. 옵시디언 조회 (착수 전)

| 찾은 것 | 결과 |
|---|---|
| 이미 기각된 접근 | `#850`(피커=노드 유무 수정)은 **반증**됨 — 에러가 `args[]=text` 라 노드 수정으로 안 없어진다 |
| 같은 클래스의 앞선 결함 | `2026-08-13` `LifecycleProgressRail` (스토어 메서드 렌더 중 호출) · `#866` `GlobalAddressSearch`(`useState` 지연 초기값의 `getState()`) — **이 건은 그 계보의 세 번째** |
| 미결·부채 | SESSION-H-web 인계 §3 「클래스② 13자리/8파일 — 래칫 동결만 · 최유력 `NextStageCta`」 |
| 이전 판단의 근거 | 그 「최유력」의 근거(**부분 게이트**)를 재보니 **도달 불가**였다(아래 전제 5) |

## 1. 전제 표 (확인 방법 + **실제 측정값**)

| # | 전제 | 확인 방법 | 실제 값 |
|---|---|---|---|
| 1 | 그 라우트에서 #418 이 **실재**한다 | 라이브 프로브 `run`(persist 채워진 상태) | ◎ `hydration:1` · `args[]=text` |
| 2 | 서버/클라 텍스트가 실제로 다르다 | `ctx.route` 로 서버 HTML 캡처 + DOM 대조 | 서버 `>0<!-- -->%` · `부지 대기` / 클라 `60%` · `부지 반영` |
| 3 | ★**귀속** — 원인이 그 블록인가 | 세 모집단(무개변 / **표적개변** / 무관개변) | **1 / 0 / 1** — 표적만 0, 음성 대조군 생존 |
| 4 | `feasibilityCompleteness` 소비처 | `grep -rn` 전수 | **1곳**(`FeasibilityEditorV2.tsx:156`) — 다른 표면 영향 없음 |
| 5 | 인계서의 「최유력 `NextStageCta`」 | `<NextStageCta` 소비처 전수 | **12곳 전부 `projectId` prop 미전달** → `if (!projectIdProp && !hydrated) return null` 이 **항상 완전 게이트** = 도달 불가 |
| 6 | 나머지 래칫 자리 | 소스 + 소비처 파생 | `AuthWorkspaceClient` 2건은 `{(false as boolean) && …}` **죽은 분기**(1066~1196) · `ProjectLifecyclePipeline` 6건은 **앱 렌더 소비처 0** · `ProjectHealthBoard` 2건은 `dynamic ssr:false` |
| 7 | 내 첫 가설(**payload 크기**가 재수화를 늦춘다) | A=2,323,716B / B=171B 두 모집단 | **둘 다 `hydration:1`** → **기각** |
| 8 | 두 번째 가설(**서비스워커**) | 2×2(진입경로 × SW) | 로그인흐름 0/0 · 심기 1/1 → **SW 무관 · 기각** |
| 9 | ★진짜 갈림 변수 | 같은 경로 3회 연속 `run` | **1회차 0 → 2회차 1 → 3회차 1** — 첫 방문이 persist 를 채우고 **둘째부터 재수화해 읽는다** |
| 10 | 수정 후 스캐너 적발 | 파생형 전수 재실행 | **19 → 18**(그 자리만 사라짐 · `isStale` 은 정당하게 잔존) |
| 11 | 타입 | `npx tsc --noEmit` | **EXIT 0** |

★9 번이 인계서 §2 가 *"이유는 모른다"* 고 남긴 재현 조건의 **측정된 답**이다(사후 설명이 아니라 **예측 → 검증**).

## 2. 변경 내용과 **회귀가 아닌 근거**

1. `store/useProjectContextStore.ts` — 판정을 모듈 스코프 순수 함수 `computeFeasibilityCompleteness(inputs)` +
   입력 셀렉터 `selectFeasibilityCompletenessInputs(s)` 로 추출. **스토어 메서드는 그 둘을 경유**한다.
   · 회귀 아님: 판정 로직은 **글자 그대로 이동**했고 `const siteDone` 선언은 저장소 전체에 **1건**(사본 없음).
     기존 메서드 시그니처·반환 타입 불변 → 다른 소비처(현재 0곳) 영향 없음.
2. `components/feasibility/FeasibilityEditorV2.tsx` — 메서드 호출 대신
   `useProjectContextStore(useShallow(selectFeasibilityCompletenessInputs))` + 순수 계산.
   · 회귀 아님: 하이드레이션 렌더에서는 서버와 **같은 입력**을 보고, 재수화 후에는 구독으로 **같은 값**을 그린다
     (실측 타임라인: 27ms `0%` → 1536ms `60%` 는 수정 전후 모두 동일한 사용자 경험).
   · `useShallow` 는 셀렉터가 매 렌더 새 객체를 만들어 **무한 리렌더**가 되는 것을 막는다(원시값 5개 비교).

## 2-4. 독립 리뷰가 찾은 것과 봉합 (반증 임무 · **REVISE** 판정)

★**자기 검증만으로는 아래 셋을 못 잡았다.** 특히 MAJOR-3 은 **내가 새로 쓴 주석이 거짓**임을
측정으로 보인 것이다.

| 등급 | 발견 | 봉합 |
|---|---|---|
| **MAJOR-3** | *"판정은 여기 한 곳뿐"* 이 **반증됨**. 면적 SSOT 는 `effectiveLandAreaSqm` 인데 이 판정만 **raw** 를 읽어, 다필지(7필지·164,823㎡)에서 **허브=「부지 완료」 / 수지=「부지 대기·0%」**. ★같은 컴포넌트가 baseline 은 통합면적으로 호출한다 — **분석은 돌면서 배지만 0%** | 입력 셀렉터가 `effectiveLandAreaSqm` 사용 · 주석의 단정을 **사실로 교정** · 다필지 대조군 테스트(두 모집단) |
| **MAJOR-1** | `useShallow` **완전 무잠금** — 지우면 화면이 무한 리렌더로 죽는데 `tsc`·vitest·lint 전부 초록(유일한 임포터가 `vi.mock` 으로 대체). **§3 에도 안 적혀 있었다** | 신규 `feasibility-completeness-wiring.test.tsx` — **원리**(파티션형 렌더: 있으면 정상/없으면 던짐) + **배선**(파생형 AST: 맨몸으로 넘기면 실패 · 양성 대조군 선행) |
| **MAJOR-2** | 래칫이 **셀렉터 형태에만** 참 — 같은 결함을 **구조분해**로 되살리면 SURVIVED(그게 이 컴포넌트의 지배적 스타일이다) | 스캐너에 `ObjectBindingPattern`+무인자 경로 · `POSITIVE` 에 **store-method 2종** 추가(기존 11종은 전부 `getState`/`localStorage` 라 이 형태에 대조군이 **0**이었다) |
| MINOR-1 | `ViaSelectorThenPure` 가 **스칼라 셀렉터**라 실제 처방을 한 번도 렌더하지 않았다(등재≠산출물) | 실제 형태(객체 셀렉터+`useShallow`)로 교체 |
| MINOR-2 | `partial` 은 **이 표면에 닿지 않는다**(칩은 `done` 만 읽는다) | 테스트 주석에 「판정의 계약이지 화면 표시가 아님」을 명시 |

**MAJOR-2 의 부수 소득**: 스캐너를 넓히니 **새 자리 2건**(`settings/page.tsx:419,422` `hasValidKey()`)이
보였다 — 전에는 사각이라 아예 안 보였다. **게이트는 실재**하므로(같은 파일 136줄 완전 조기 반환)
사유·부채와 함께 래칫에 등재했다. ★이름만 보고 `isMounted` 를 게이트로 인정하면 **가짜 게이트도
통과**하므로 검사기를 넓히지 않았다.

**전역 스윕**(§6): raw `landAreaSqm` 을 읽는 자리는 여럿이나 대부분 `|| address || zoneCode` 로
**OR** 되어 다필지에서도 참이 된다. **면적 단독으로 `done` 을 가르는 자리는 이 하나뿐**이었다.

## 3. ★검증하지 못한 것

- **수정본의 라이브 확증은 아직 없다** — 배포 전이다. 배포 후 프로브를 **같은 경로 2회**로 돌려
  `1 → 0` 을 확인해야 최종 확정이다(요청 형식은 §5).
- 나머지 래칫 18건 중 **`BoqAutoWorkspace`·`OrchestratorPanel`·`InputResolveModal`** 는 소스로
  「셀렉터 파생 조건 뒤라 하이드레이션 렌더에서 도달 불가」로 판정했으나 **라이브로는 안 쟀다**.
- 「1회차 0 / 2회차 1」의 **메커니즘**은 persist 재수화로 설명되지만, 재수화 완료 시점과 하이드레이션
  시점의 정확한 순서는 **재지 않았다**(설명은 예측·검증으로만 뒷받침된다).
- `projectCompleteness`·`stageCompletion` 계열은 이 PR 범위 밖이다(`ProjectHealthBoard` 는 `ssr:false`).
- ★**`settings/page.tsx` 의 새 등재 2건은 「지금」 게이트 뒤일 뿐**이다. 그 조기 반환을 지우면
  진짜 결함이 되는데 **래칫은 그 변화를 못 본다**(부채로 적어 둔다).
- ★전수 `vitest run` 이 이 저장소에서 **변이 없이도 `rc=1`**(RPC 타임아웃)이라 **변이 판정에 쓸 수 없다** —
  기준선 `rc=0` 인 타깃 테스트로만 판정했다.

## 4. 되돌리기 경로

`git revert` 한 번. 순수 함수 추출은 **행위 보존 리팩터**이고, 컴포넌트 변경은 두 줄(+import)이다.

## 5. 잠금 — 무엇이 이 변경을 지키는가

| 잠그는 것 | 어디서 | 필수 CI |
|---|---|---|
| **되돌리면 잡힌다**(배선) — 스토어 메서드를 렌더 중 다시 부르면 래칫의 「새로 생김」에 걸린다 | `lib/hydration/__tests__/render-path-store-reads.contract.test.ts` (해당 항목 **삭제** · 죽은 면제도 실패시키는 래칫) | ◎ vitest |
| **원리** — 셀렉터는 서버 스냅샷, **스토어 메서드는 라이브**(셀렉터로 꺼내도 **부르면** 라이브) | `lib/hydration/__tests__/zustand-server-snapshot.contract.test.tsx` — `ViaMethod` 대조군 + `ViaSelectorThenPure` 처방 | ◎ vitest |
| **판정 동작**(두 모집단 0%↔60% · 연속 누적 · partial 은 안 실림 · 단계/가중치 계약) | `store/__tests__/feasibility-completeness.test.ts` | ◎ vitest |
| 셀렉터가 **판정 입력 전부**를 덮는가(어느 축이라도 빠지면 pct 100 이 안 나온다) | 같은 파일 | ◎ |
| **면적 출처가 SSOT** — 다필지 통합면적으로 `done`(그리고 빈 부지는 여전히 `대기`) | 같은 파일 · 두 모집단 | ◎ |
| **`useShallow` 원리** — 없으면 던진다(파티션형 런타임) | `feasibility-completeness-wiring.test.tsx` | ◎ |
| **`useShallow` 배선** — 저장소 어디든 맨몸으로 넘기면 실패(파생형 AST · 양성 대조군 선행) | 같은 파일 | ◎ |
| **구조분해 형태의 되살림**(스캐너 사각이었다) | `render-path-store-reads.ts` + `POSITIVE` store-method 2종 | ◎ |
