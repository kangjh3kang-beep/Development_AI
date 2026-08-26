# 저장된 프로젝트가 있으면 화면이 통째로 다시 그려진다 — 하이드레이션 불일치

**2026-08-26 · SESSION-E · 브랜치 `fix/hydration-persist-picker`**

## 0. 옵시디언·보드 조회 결과

조회함.

- **보드 10:31 내 노트** — `regulations` 원인을 `ProjectAddressInput:166` 으로 특정하고
  로컬 프로덕션 빌드 변이로 확정한 기록이 이미 있었다.
  ★같은 노트에 `permits` 원인도 `GlobalAddressSearch.tsx:178` 의 **useState lazy 초기값**으로
  적혀 있었는데, 오늘 나는 그것을 잊고 다른 줄(1151 · 이벤트 핸들러)을 보고 *"미확정"* 이라
  말할 뻔했다. **내 기록에 답이 있었다.**
- **저장소 선례** — `hooks/useHydrated` 독스트링의 **2026-08-13 `LifecycleProgressRail` 사고**.
  그 사고로 만들어진 `e2e/hydration-lifecycle-rail.spec.ts` 의 `test.fixme` 가
  *"persist 파생값을 SSR 경로에서 렌더하는 잔여 소비처"* 를 **부채로 명시**하고 있다.
  **이 PR 은 그 스윕의 한 건이다.**

## 1. 전제 표 — 확인 *방법* 과 **실제 측정값**

| 전제 | 확인 방법 | 측정값 |
|---|---|---|
| 결함이 실재하는가 | 로컬 프로덕션 빌드에서 조건 무력화 변이 | `/ko/regulations` #418 **1→0** · 양성 대조군(다른 라우트) **1 유지** |
| 무엇에서 파생되나 | 소스 추적 | `useProjectStore.projects` = zustand **persist**(localStorage) |
| 서버가 그 값을 보나 | 센티널 로그 | `renderToString` 안에서 `pickerProjects.length === 0` |
| 영향 범위 | 공용 컴포넌트 소비처 전수 | **15곳** · `hideProjectPicker` 5곳 제외 → **10페이지** |
| 그중 실측 라우트 | 소비처 목록 대조 | `RegulationsWorkspaceClient` · `PermitAiWorkspaceClient` **둘 다 포함** |
| 집 관례가 있나 | 목적 조회 | `hooks/useHydrated` 실재(+ 사고 기록) · `BillingMeter` 등 형제 다수 |
| 유닛으로 잠기나 | **변이 2회** | **둘 다 SURVIVED**(§4 참조) |

## 2. 회귀가 아닌 근거

`ProjectAddressInput` 은 처음부터 이 조건을 갖고 있었고, `useProjectStore` 가 persist 로
바뀐 뒤 결함이 됐다. **표류이지 특정 커밋의 회귀가 아니다.** 그래서 원인 커밋을 찾지 않았다.

## 3. 처방과 경계

- 기존 `useHydrated` 로 **그 블록만** 게이트.
- ★컴포넌트 전체를 게이트하지 않는다 — 첫 페인트에 주소 입력이 사라지면 **결함보다 나쁘다.**
- ★**사용자 가시 동작은 바뀌지 않는다** — 서버 HTML 에 애초에 그 노드가 없었고 사용자가 보는
  것은 재수화 이후 화면이다. **제품 결정이 아니라 렌더 시점 교정이다.**
  (앞서 내가 이걸 *"제품 판단 필요"* 로 미뤘던 라벨은 **과잉이었다.**)

## 4. ★검증하지 못한 것 (승계 금지)

1. **★유닛 락이 없다. 두 번 시도해 두 번 다 공허했다.**
   - ①`renderToString(빈) === renderToString(채운)` → 변이 SURVIVED.
     zustand `persist` 가 `getServerSnapshot` 으로 초기 상태를 줘 **서버는 늘 빈 값**.
     단언이 **원리적으로 참**이었다.
   - ②`hydrateRoot` + `console.error` → 변이 SURVIVED.
     수정본·변이본 DOM 이 **완전히 동일**(`SSR:false | act 내부:false | act 이후:true`).
   → 행위 잠금은 `e2e/hydration-lifecycle-rail.spec.ts` 로 옮겼다.
2. **★그 e2e 는 `e2e-nightly.yml` 에서 돈다 — 필수 CI 가 아니다.**
   **머지 시점에 회귀망이 없다.** `it.todo` 로 초록 안에 남겼다.
   *"고쳤으나 미검증"* 과 *"미수정"* 을 섞지 않기 위해 명시한다.
3. **e2e 를 실제로 돌려 보지 않았다.** 작성만 했다(플레이라이트 브라우저·서버 기동 필요).
   시드 키(`propai-project-storage`)·버전(0)이 실물과 맞는지는 **미검증**이다.
4. **`permits` 라우트는 안 고쳤다.** 원인 후보(`GlobalAddressSearch` useState lazy 초기값)는
   보드에 적혀 있으나 **이 PR 범위 밖**이다.
5. **다른 소비처 8페이지의 화면을 눈으로 보지 않았다.** 같은 컴포넌트라 논리적으로 따라오지만
   **재지 않았다.**
6. **persist 스토어는 8개이고 `useProjectStore` 소비처만 38곳** — 전수 판정하지 않았다.
   형제 스펙의 `test.fixme` 부채가 그대로 남는다.

## 5. 되돌리기

한 줄(`hydrated &&`) 제거로 완전 복구. 백엔드·데이터·계약 변경 0.

## 6. 잠금

- e2e 형제 테스트 1건(공허 방지: **드롭다운이 실제로 보이는지 먼저 단언** 후 `pageerror` 검사).
- 유닛은 **범위만** — 게이트가 컴포넌트를 통째로 죽이지 않았는가.
- ★같은 브랜치에 남아 있던 **진단 변이**(`GlobalAddressSearch` 의 `if (false as boolean && …)`)를
  제거했다. 커밋됐으면 다필지 승격이 **조용히 죽었다.**
