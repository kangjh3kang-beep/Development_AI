# 계획 — 사통맵 레이어 컨트롤 **영속** (2026-09-04)

★사용자 요구의 잔여분. `#954` 가 「끌 수 있게」를, `#960` 이 「기본 화면 가독성」을 줬다.
그런데 **끈 것이 새로고침하면 되돌아온다** — 206필지 작업 중 페이지를 다시 열면 다시 켜져 있다.

## 0. 옵시디언 조회 결과 (§계획게이트 0)

조회기 생존: 영속 관련 문서 **49건** · 대조군(PropAI) 443 · 음성 대조군 **0**.

| 찾을 것 | 결과 |
|---|---|
| 이미 기각된 접근 | **있다** — *"persist 파생값을 SSR 경로에서 렌더하면 위험"* 이라는 **과잉 일반화**가 `#850` 을 **결함이 아닌 것**으로 보냈다. 그 분류는 **기각됐다** |
| 같은 클래스의 앞선 결함 | `GlobalAddressSearch` 의 `useState` **지연 초기값**이 `getState()` 를 읽어 **React #418** 실화 |
| 미결·부채 | 없음(이 주제) |
| 이전 판단의 근거 | **셀렉터 읽기는 원리적으로 불일치 불가** — `zustand/middleware` 가 `api.getInitialState` 를 덮어쓰기 때문(필요조건이 아니라 **그 대입**이 진짜 이유) |

## 1. 전제 표 — 확인 방법과 **실제 측정값**

| # | 전제 | 확인 방법 | **결과(실측)** |
|---|---|---|---|
| P1 | 현재 상태의 형태 | `origin/main` 869행 | `useState<…>(initialLayerControls)` — `#959` 가 값으로 뺀 그 형태 |
| P2 | persist 스토어 규칙 | `lib/__tests__/persist-key-coverage.test.ts` | **와이프되거나 계정별**, 아니면 **사유를 지닌 면제부** |
| P3 | 계정별 저장 재료 | `lib/account-scoped-storage.ts` | `createAccountScopedStorage<S>()` — 실저장키는 `<name>__<uid>` |
| P4 | 선례 | `store/useRegistryAnalysisStore.ts` | `persist(fn, { name, storage: createAccountScopedStorage<State>() })` |
| P5 | 하이드레이션 위험 | `lib/hydration/render-path-store-reads.ts` | **셀렉터 읽기는 안전**. 위험은 **우회 3종**(렌더 중 `getState()`·스토어 메서드·`localStorage`) |
| P6 | ★`useState` 지연 초기값은? | 같은 파일 | ★**「렌더 중」에 포함**된다 — 지금 형태를 그대로 두고 안에서 스토어를 읽으면 **위험 ①** |
| P7 | 겹치는 열린 PR | 열린 PR | ★`#960` 이 **같은 테스트 파일**을 연다 → **착지 후 착수** |

## 2. 변경 내용과 **회귀가 아닌 근거**

`layerControls` 를 **계정별 persist 스토어**로 옮기고 **셀렉터로만** 읽는다.

    store/useSatongMapPrefsStore.ts
      persist((set) => ({ controlsByLayer: initialLayerControls(), setControlsByLayer, resetControls }),
              { name: "propai-satong-map-prefs", storage: createAccountScopedStorage<State>() })

    SatongMapShell
      const layerControls   = useSatongMapPrefs((s) => s.controlsByLayer);      // 셀렉터
      const setLayerControls = useSatongMapPrefs((s) => s.setControlsByLayer);  // 셀렉터

- **회귀 아님**: 초기 상태가 `initialLayerControls()` 그대로다. 저장된 값이 없으면 **지금과 동일**.
- **하이드레이션 안전**: 셀렉터 전용(P5). `useState` 지연 초기값을 **없앤다**(P6 회피).
- **계정 격리**: P2·P3 — 실저장키가 `__<uid>` 라 계정 전환 시 섞이지 않는다.

## 3. ★검증하지 못할 것 / 미리 정할 것

- **저장 스키마 변경 시 마이그레이션** — 컨트롤 id 어휘가 두 벌인 것(`selected` ↔ `selected-parcel`)이
  저장분에 들어간다. 어휘 통합을 나중에 하면 **저장된 옛 id 를 어떻게 할지**가 남는다.
  → `version` 을 두고 **미정임을 명시**한다.
- **브라우저 눈 확인** — 배포 후에만.
- ★**「기본으로 되돌리기」가 없으면 갇힌다**(유료·비가역 규율 §5 의 형제). 저장된 상태가
  나쁘면 사용자가 초기화할 길이 필요하다 → `resetControls` 를 **UI 에 노출할지**는 이 PR 범위 밖으로
  두되, **스토어에는 둔다**(없으면 나중에 추가가 배선까지 필요해진다).

## 4. 되돌리기 경로

스토어 읽기를 `useState(initialLayerControls)` 로 되돌리면 종전 동작. 저장분은 남지만 무해.

## 5. 잠금

| 축 | 락 |
|---|---|
| **영속** | 값을 바꾸고 **재마운트**하면 그 값이 살아 있다(두 모집단: 바꾼 것 ↔ 안 바꾼 것) |
| **기본값** | 저장분이 없으면 `initialLayerControls()` 와 **값이 같다** |
| **계정 격리** | `persist-key-coverage` 가 **파생형으로 이미 강제** — 새 키가 등재되는지 |
| ★**하이드레이션** | `render-path-store-reads` 계약에 **새 위반이 안 생긴다**(파생형 · 이미 존재) |
| ★**우회 금지** | `SatongMapShell` 이 렌더 중 `getState()`·`localStorage` 를 안 쓴다 |
| ★**끄면 꺼진 채로** | `#954` 의 토글을 끄고 재마운트 → 여전히 꺼져 있다(사용자 요구 그 자체) |
