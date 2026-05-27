---
name: propai-frontend
description: "PropAI 부동산개발 플랫폼 프론트엔드 개발 스킬. Next.js 16 App Router 페이지, React 19 컴포넌트, Three.js BIM 3D 뷰어, Zustand 상태관리, TanStack Query/Apollo Client API 연동, Tailwind CSS v4, Framer Motion 애니메이션, WCAG 2.1 AA 접근성, 한영중 i18n 구현. 프론트엔드 페이지 구현, UI 컴포넌트 작성, 3D 뷰어 개발, 상태관리, API 연동 요청 시 이 스킬을 사용. 수정, 보완, 재구현 요청에도 사용."
---

# PropAI Frontend Development Skill

PropAI 부동산개발 플랫폼의 프론트엔드 구현 가이드.

## 프로젝트 구조

```
apps/web/
├── app/
│   ├── api/                  # API Route Handlers
│   └── [locale]/             # 다국어 라우팅 (ko, en, zh)
│       ├── (dashboard)/      # 대시보드 그룹
│       ├── (project)/        # 프로젝트 관리 그룹
│       └── (analysis)/       # 분석 모듈 그룹
├── components/               # React 컴포넌트 (41개+)
│   ├── Dashboard/
│   ├── ProjectManagement/
│   ├── BIMViewer/            # Three.js 3D WebXR
│   ├── AccessibilityCore/
│   └── common/               # 공통 UI
├── features/                 # 기능별 모듈
├── hooks/                    # 커스텀 React 훅
├── lib/                      # 유틸리티, API 클라이언트
├── store/                    # Zustand 상태관리
├── i18n/                     # 다국어 설정
└── e2e/                      # Playwright 테스트
```

## 페이지 구현 패턴

### RSC (React Server Component) 우선

```tsx
// app/[locale]/(dashboard)/page.tsx — 서버 컴포넌트 (기본)
import { DashboardClient } from '@/components/Dashboard/DashboardClient'

export default async function DashboardPage() {
  // 서버에서 초기 데이터 fetch
  const stats = await fetchDashboardStats()
  return <DashboardClient initialStats={stats} />
}
```

```tsx
// components/Dashboard/DashboardClient.tsx — 클라이언트 컴포넌트 (최소 범위)
"use client"
import { useQuery } from '@tanstack/react-query'

export function DashboardClient({ initialStats }) {
  const { data } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: fetchDashboardStats,
    initialData: initialStats,
  })
  // 인터랙티브 UI 렌더링
}
```

**핵심:** `"use client"`는 인터랙션이 필요한 최소 범위에만 적용. 데이터 fetching은 서버 컴포넌트에서 처리.

### API 연동

**REST (TanStack Query):**
```tsx
import type { ProjectResponse } from '@propai/types/api'

const { data } = useQuery<ProjectResponse[]>({
  queryKey: ['projects'],
  queryFn: () => fetch('/api/projects').then(r => r.json()),
})
```

**GraphQL (Apollo Client):**
```tsx
const { data } = useQuery(GET_PROJECT_DETAILS, {
  variables: { id: projectId },
})
```

**타입 안전성:** `packages/types/api.ts`의 타입을 사용. `any` 캐스팅 금지. API 응답 shape과 타입이 불일치하면 backend-dev에게 알린다.

## 3D BIM 뷰어

```tsx
"use client"
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Environment } from '@react-three/drei'

export function BIMViewer({ ifcData }) {
  return (
    <Canvas camera={{ position: [10, 10, 10] }}>
      <Environment preset="studio" />
      <OrbitControls />
      <IFCModel data={ifcData} />
    </Canvas>
  )
}
```

대용량 IFC 모델은 `dynamic(() => import('./BIMViewer'), { ssr: false })`로 코드 스플리팅.

## 상태 관리 (Zustand)

```tsx
// store/projectStore.ts
import { create } from 'zustand'

interface ProjectStore {
  currentProject: Project | null
  setCurrentProject: (project: Project) => void
}

export const useProjectStore = create<ProjectStore>((set) => ({
  currentProject: null,
  setCurrentProject: (project) => set({ currentProject: project }),
}))
```

**규칙:** 전역 상태는 Zustand, 서버 상태는 TanStack Query/Apollo. 혼용하지 않는다.

## 접근성 (WCAG 2.1 AA)

- 모든 이미지에 `alt` 텍스트
- 인터랙티브 요소에 `aria-label` / `aria-describedby`
- 키보드 내비게이션: `tabIndex`, `onKeyDown` 핸들링
- 색상 대비 4.5:1 이상
- 포커스 인디케이터 visible

## 다국어 (i18n)

`[locale]` 동적 세그먼트로 한/영/중 지원. 번역 키는 `i18n/messages/{locale}.json`에 관리.

## 성능 최적화

- 이미지: `next/image` (자동 최적화, lazy loading)
- 폰트: `next/font` (FOUT 방지)
- 대형 라이브러리: `dynamic import` + `{ ssr: false }`
- 리스트: 가상화 (`@tanstack/virtual`) 적용
- 메모이제이션: `useMemo`/`useCallback`은 측정 후 필요할 때만
