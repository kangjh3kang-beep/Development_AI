# PropAI v30.0 구축안 — Codex 담당

> **역할**: 프론트엔드 (Next.js 14 App Router) + 스마트컨트랙트 (Solidity) + 웹 UI 통합
> **IDE**: VS Code + Copilot
> **작업 범위**: `apps/web/**`, `contracts/**`, `packages/ui/**`
> **문서 기준**: 상위 명세 `Part IX`의 `STEP 5`, `STEP 6`, `STEP 10`, `STEP 11`
> **전체 순서 요약**: `build-plan-overview.md`
> **모든 설명/주석/보고는 한국어로 작성**

---

## 번호 체계 정정

이 문서는 기존 초안의 내부 번호를 버리고 상위 명세 기준으로 다시 정렬한다.

| 기존 초안 번호 | 정정 번호 | 내용 |
|----------------|-----------|------|
| **10, 11, 12, 13** | **STEP 5** | 프론트엔드 완전 구현 |
| **7** | **STEP 6** | 스마트컨트랙트 구현 |
| **16** | **STEP 10** | 테스트 구조/Playwright 보조 |

추가 원칙:
- `STEP 5`는 웹 앱 전체 구현을 의미하며, 내부적으로 `5-1`~`5-5` 세부 구간으로 나눈다.
- `STEP 6`은 Solidity/Hardhat 패키지 전체를 의미한다.
- `.build-journal/` 기록 파일도 `step-05-*`, `step-06-*` 형식으로 통일한다.

---

## 담당 범위 요약

| STEP | 세부 구간 | 내용 | 역할 | 선행 조건 |
|------|-----------|------|------|----------|
| **5** | **5-1** | `apps/web` 스캐폴딩 + App Router + i18n 기본 구조 | 주 담당 | 모노레포 골격 준비 |
| **5** | **5-2** | 전역 Provider, 상태 관리, API/GraphQL 연동 껍데기 | 주 담당 | 5-1 완료 |
| **5** | **5-3** | `packages/ui` 공용 프리미티브 + 핵심 도메인 UI | 주 담당 | 5-2 완료 |
| **5** | **5-4** | 고급 UI (BIM/드론/에이전트/에스크로) | 주 담당 | Claude API 계약 초안 확보 |
| **5** | **5-5** | WCAG 2.1 AA + PWA + 접근성 마감 | 주 담당 | 5-3, 5-4 완료 |
| **6** | **6-1** | Hardhat 프로젝트 + `PropAIEscrow` 컨트랙트 + 배포/테스트 | 공동 담당 | 지갑/네트워크/env 정의 |
| **10** | **10-1** | Playwright E2E 시나리오 보조 | 보조 | 주 기능 구현 완료 |
| **11** | **11-1** | 접근성 자동 검증 연계 지원 | 보조 | STEP 5 접근성 구현 완료 |

---

## 착수 전 확인 사항

1. 작업 시작 전 `.build-journal/lock-files.json`에 잠금 파일을 등록한다.
2. `.build-journal/current-stage.json`의 Codex 상태를 `active`로 갱신한다.
3. 현재 워크스페이스에는 `apps/web`, `contracts`, `packages/ui`가 아직 없을 수 있으므로, 첫 작업은 디렉토리 생성과 패키지 초기화다.
4. `packages/types/`는 Claude Code 선행 정의 영역이므로 참조만 하고 수정하지 않는다.
5. GraphQL 실제 연결은 Gemini의 Hasura 준비 이후 활성화하고, 그 전에는 Apollo Provider와 캐시 구조만 준비한다.
6. API 의존 UI는 Claude Code의 API 라우터 완료 전까지 Mock 데이터 어댑터로 먼저 개발한다.
7. ABI 산출물은 다른 에이전트 영역을 직접 덮어쓰지 않고 `contracts/deployments/**`와 `contracts/artifacts/**`를 단일 소스로 사용한다.

---

## STEP 5: 프론트엔드 완전 구현

### 5-1. `apps/web` 스캐폴딩 + App Router + i18n

#### 목표
- `apps/web`를 pnpm 워크스페이스 패키지로 생성한다.
- Next.js 14 App Router 기반 구조를 만든다.
- 한국어/영어/중국어 간체 3개 로케일 라우팅을 구축한다.
- 루트 레이아웃과 로케일 레이아웃을 분리해 구조를 안정화한다.

#### 초기화 명령

```bash
pnpm dlx create-next-app@latest apps/web --ts --tailwind --eslint --app --use-pnpm --import-alias "@/*"
```

권장 패키지명:

- `apps/web/package.json` → `@propai/web`
- `packages/ui/package.json` → `@propai/ui`

#### 필수 파일

- `apps/web/app/layout.tsx`
  - Next.js 필수 루트 레이아웃
  - 전역 CSS, 기본 메타데이터, 공통 `<body>` 구조
  - 쿠키 또는 미들웨어 결과를 기준으로 `<html lang>` 동기화
- `apps/web/app/[locale]/layout.tsx`
  - locale 유효성 검사
  - `AccessibilityProvider`, `AppProviders` 래핑
  - locale별 메타데이터와 화면 구조 정의
- `apps/web/app/[locale]/page.tsx`
  - 로케일별 대시보드 진입 페이지 또는 `/projects` 리다이렉트
- `apps/web/middleware.ts`
  - `Accept-Language` + 쿠키 기반 로케일 감지
  - `/` 요청 시 `/{locale}`로 리다이렉트
- `apps/web/i18n/config.ts`
  - `defaultLocale`, `locales`, locale 유틸
- `apps/web/public/locales/ko/common.json`
- `apps/web/public/locales/en/common.json`
- `apps/web/public/locales/zh-CN/common.json`

#### 앱 라우트 구조

```text
apps/web/app/
├── layout.tsx
├── [locale]/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── (auth)/
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   └── (dashboard)/
│       ├── layout.tsx
│       ├── page.tsx
│       ├── projects/page.tsx
│       ├── projects/[id]/page.tsx
│       ├── projects/[id]/design/page.tsx
│       ├── projects/[id]/bim/page.tsx
│       ├── projects/[id]/finance/page.tsx
│       ├── projects/[id]/drone/page.tsx
│       ├── projects/[id]/blockchain/page.tsx
│       ├── projects/[id]/report/page.tsx
│       ├── agent/page.tsx
│       ├── tax/page.tsx
│       ├── auction/page.tsx
│       └── inspection/page.tsx
└── api/
    └── health/route.ts
```

#### 번역 카테고리

- `nav`
- `dashboard`
- `avm`
- `design`
- `finance`
- `construction`
- `tax`
- `errors`
- `agent`
- `drone`
- `blockchain`

### 5-2. Provider, 상태 관리, 데이터 연동 껍데기

#### 목표
- 웹 앱의 공통 Provider 계층을 정리한다.
- REST/GraphQL/실시간 협업용 클라이언트 초기 구조를 만든다.
- 백엔드 완성 전에도 Mock 기반 UI 개발이 가능하도록 어댑터 계층을 둔다.

#### 구현 파일

- `apps/web/lib/providers.tsx`
  - QueryClientProvider
  - ApolloProvider
  - locale/context provider
- `apps/web/lib/query-client.ts`
  - TanStack Query 기본 설정
- `apps/web/lib/apollo-client.ts`
  - HTTP link 기본 구성
  - Hasura 준비 전까지 subscription link는 TODO 또는 feature flag 처리
- `apps/web/lib/api-client.ts`
  - REST fetch wrapper
  - 에러 표준화
- `apps/web/lib/realtime.ts`
  - SSE 공통 유틸
- `apps/web/store/use-app-store.ts`
  - locale, sidebar, user preference
- `apps/web/store/use-project-store.ts`
  - 현재 프로젝트 선택 상태
- `apps/web/mocks/**`
  - 컴포넌트 개발용 Mock 데이터

#### 상태 관리 원칙

- Zustand: 로컬 UI 상태, locale, 사용자 선호도
- TanStack Query: REST API 서버 상태
- Apollo Client: GraphQL 쿼리/구독
- Y.js: 실시간 협업 커서/문서 동기화

#### 연계 원칙

- Claude API 미완료 상태에서는 `mocks/`로 UI를 먼저 만든다.
- Gemini GraphQL 미완료 상태에서는 Apollo 캐시와 Provider만 준비한다.
- 실제 API 전환 시 컴포넌트는 `props` 기반을 유지하고, 데이터 패칭은 page 또는 container 계층에서 수행한다.

### 5-3. `packages/ui` 공용 프리미티브 + 핵심 도메인 UI

#### 구조 원칙

- `packages/ui`: 재사용 가능한 저수준 UI 프리미티브
- `apps/web/components`: PropAI 도메인 특화 컴포넌트
- 중복을 막기 위해 `Button`, `Card`, `Dialog`, `Input`, `Select`, `Skeleton` 같은 기초 부품은 `packages/ui`에 둔다.

#### `packages/ui` 필수 파일

- `packages/ui/package.json`
- `packages/ui/tsconfig.json`
- `packages/ui/src/index.ts`
- `packages/ui/src/components/button.tsx`
- `packages/ui/src/components/card.tsx`
- `packages/ui/src/components/dialog.tsx`
- `packages/ui/src/components/input.tsx`
- `packages/ui/src/components/select.tsx`
- `packages/ui/src/components/skeleton.tsx`
- `packages/ui/src/styles/tokens.css`

#### `apps/web/components` 핵심 도메인 컴포넌트

| 컴포넌트 | 파일 | 기능 |
|----------|------|------|
| CadastralMap | `apps/web/components/map/CadastralMap.tsx` | VWORLD + Leaflet 기반 지적도 |
| ParcelsLayer | `apps/web/components/map/ParcelsLayer.tsx` | 다필지 레이어 시각화 |
| AVMWidget | `apps/web/components/finance/AVMWidget.tsx` | 시세 추정 결과 카드 |
| JeonseRiskCard | `apps/web/components/finance/JeonseRiskCard.tsx` | 전세 위험도 카드 |
| TaxCalculator | `apps/web/components/finance/TaxCalculator.tsx` | 세금 계산 폼 |
| FloorPlanViewer | `apps/web/components/design/FloorPlanViewer.tsx` | 평면도 이미지 뷰어 |
| FloorPlanGenerator | `apps/web/components/design/FloorPlanGenerator.tsx` | SDXL 생성 UI + 참조 이미지 업로드 |
| StreamingReport | `apps/web/components/design/StreamingReport.tsx` | SSE 보고서 렌더링 |
| CollaborationCursors | `apps/web/components/collaboration/CollaborationCursors.tsx` | CRDT 커서 오버레이 |
| SkeletonLoader | `apps/web/components/ui/SkeletonLoader.tsx` | 앱 전용 스켈레톤 |
| StreamingText | `apps/web/components/ui/StreamingText.tsx` | 스트리밍 텍스트 렌더러 |
| OfflineBanner | `apps/web/components/ui/OfflineBanner.tsx` | 오프라인 상태 배너 |
| LocaleSwitcher | `apps/web/components/ui/LocaleSwitcher.tsx` | 언어 전환 드롭다운 |

### 5-4. 고급 UI 구현

#### 목표
- BIM, 드론, AI 에이전트, 블록체인 상태를 웹에서 시각화한다.
- 무거운 UI는 Mock 데이터 우선으로 구축하고 API 연동은 뒤에 붙인다.
- 렌더링 실패 시 graceful fallback을 제공한다.

#### 구현 파일

- `apps/web/components/bim/BIMViewer3D.tsx`
  - Three.js 기반 IFC 뷰어
  - 조명, 그리드, OrbitControls, 선택 정보 패널
  - WebXR은 capability check 후 선택 활성화
- `apps/web/components/bim/IFCQuantityTable.tsx`
  - 물량산출 표
  - 숫자 포맷팅, 단위 표준화
- `apps/web/components/drone/DefectHeatmap.tsx`
  - 심각도별 색상 범례 포함
  - 색상 외 텍스트/아이콘 병행
- `apps/web/components/agent/AgentTimeline.tsx`
  - 7단계 상태 표시
  - SSE 수신 상태/재연결 UI
- `apps/web/components/blockchain/EscrowCard.tsx`
  - 에스크로 상태, 금액, 만료일, 트랜잭션 링크

#### 고급 UI 개발 원칙

- `page.tsx`는 데이터 주입과 로딩 분기만 맡는다.
- 실제 복잡한 렌더링 로직은 `components/**`로 분리한다.
- 무거운 컴포넌트는 동적 import를 사용해 초기 번들 크기를 제어한다.
- 3D, 지도, WebXR 기능은 SSR 대신 클라이언트 컴포넌트로 한정한다.

### 5-5. 접근성 + PWA 마감

#### 접근성 구현 파일

- `apps/web/hooks/useAccessibility.ts`
  - `trapFocus()`
  - `announceToScreenReader()`
- `apps/web/components/ui/AccessibilityProvider.tsx`
  - 라이브 리전
  - 고대비/동작감소 대응
  - `.sr-only` 유틸 스타일

#### 적용 항목

- 모든 버튼/링크/입력 요소에 적절한 `aria-*` 속성 부여
- 키보드만으로 주요 플로우 수행 가능해야 함
- 색상만으로 상태를 전달하지 않음
- 차트/히트맵/상태카드에는 텍스트 범례 포함
- 이미지에는 `alt` 텍스트 필수
- 모달, 드롭다운, 사이드바는 포커스 흐름 제어

#### PWA 구현 범위

- `apps/web/public/manifest.webmanifest`
- 앱 아이콘, 메타태그, 테마 컬러
- `inspection/page.tsx`에서 오프라인 상태 안내
- 네트워크 불가 시 마지막 캐시/안내 문구 제공

#### 참고

- 서비스 워커 고도화와 오프라인 데이터 동기화는 API 계약이 확정된 뒤 2차 작업으로 진행한다.

### STEP 5 품질 게이트

- [ ] `pnpm --filter @propai/web lint` 성공
- [ ] `pnpm --filter @propai/web build` 성공
- [ ] `pnpm --filter @propai/web exec tsc --noEmit` 성공
- [ ] `http://localhost:3000/ko`, `/en`, `/zh-CN` 라우팅 확인
- [ ] 핵심 페이지 렌더링 확인: 대시보드, 프로젝트 상세, 설계, BIM, 드론, 블록체인
- [ ] `npx @axe-core/cli http://localhost:3000/ko --tags wcag2aa` 위반 0건
- [ ] Lighthouse 접근성 점수 90점 이상 (`/ko`, `/en`, `/zh-CN`)
- [ ] `.build-journal/step-05-web.md` 기록

---

## STEP 6: 스마트컨트랙트 구현

### 6-1. Hardhat 패키지 구조

#### 목표
- `contracts`를 독립 워크스페이스 패키지로 구성한다.
- Escrow 컨트랙트, 배포 스크립트, 테스트, 배포 메타데이터를 한 곳에서 관리한다.
- ABI와 배포 주소를 공용 산출물로 남긴다.

#### 권장 디렉토리 구조

```text
contracts/
├── package.json
├── tsconfig.json
├── hardhat.config.ts
├── src/
│   └── PropAIEscrow.sol
├── scripts/
│   └── deploy.ts
├── test/
│   └── PropAIEscrow.test.ts
├── deployments/
│   ├── amoy/
│   └── polygon/
└── artifacts/
```

#### `contracts/package.json` 권장 의존성

```json
{
  "name": "@propai/contracts",
  "private": true,
  "scripts": {
    "build": "hardhat compile",
    "test": "hardhat test"
  },
  "devDependencies": {
    "@nomicfoundation/hardhat-ethers": "^4.0.0",
    "@nomicfoundation/hardhat-verify": "^2.0.0",
    "@openzeppelin/contracts": "^5.0.0",
    "ethers": "^6.11.0",
    "hardhat": "^2.22.0",
    "typescript": "^5.0.0"
  }
}
```

### 6-2. `PropAIEscrow.sol`

#### 구현 파일

- `contracts/src/PropAIEscrow.sol`

#### 핵심 요구사항

- Solidity `^0.8.20`
- OpenZeppelin `Ownable`, `ReentrancyGuard`, `Pausable` 활용
- 수수료 `0.3%` 자동 차감
- 이벤트:
  - `EscrowCreated`
  - `EscrowFunded`
  - `EscrowReleased`
  - `EscrowDisputed`
  - `EscrowRefunded`

#### 핵심 기능

- `createEscrow()`
  - 에스크로 생성
  - 참여자, 만료일, 지급 조건 해시 저장
- `fundEscrow()` 또는 `createEscrow()` 내 payable 처리
  - 실제 자금 예치
- `releaseEscrow()`
  - 조건 충족 시 지급
  - CEI 패턴 적용
- `directPaymentToSubcontractor()`
  - 하도급 대금 직불
- `autoRefundOnExpiry()`
  - 만료일 초과 시 자동 환불
- `initiateDispute()`
  - 분쟁 상태 전환

#### 구현 원칙

- `custom error` 우선 사용
- 상태 전이는 enum으로 명확히 관리
- 금액 계산은 basis points로 처리
- 재진입 방어와 pause 동작을 테스트로 보장

### 6-3. Hardhat 설정과 네트워크

#### 구현 파일

- `contracts/hardhat.config.ts`

#### 설정 항목

- **우선 적용:** `localhost` (Hardhat 로컬 네트워크) - 테스트넷 자금이나 Private Key 없이 프론트/백엔드 연동용 ABI 및 임시 Contract Address 추출을 위해 먼저 단독 배포
- **2차 적용:** `amoy` 테스트넷 (사용자가 `DEPLOYER_PRIVATE_KEY`와 MATIC 자금을 `.env`에 주입한 이후 실제 배포 진행)
- `polygon` 메인넷
- Polygonscan 검증
- 환경변수 (사용자 주입 대기):
  - `POLYGON_AMOY_RPC_URL`
  - `POLYGON_MAINNET_RPC_URL`
  - `DEPLOYER_PRIVATE_KEY`
  - `POLYGONSCAN_API_KEY`

### 6-4. 배포 스크립트와 ABI 산출물

#### 구현 파일

- `contracts/scripts/deploy.ts`

#### 산출물 규칙

- 배포 후 ABI는 `contracts/artifacts/`에서 생성
- 배포 메타데이터는 `contracts/deployments/{network}/PropAIEscrow.json`에 저장
- 다른 에이전트는 위 경로를 읽어 사용하고, Codex가 `apps/api/**`를 직접 수정하지 않는다

### 6-5. 테스트

#### 구현 파일

- `contracts/test/PropAIEscrow.test.ts`

#### 필수 테스트 시나리오

- 에스크로 생성
- 자금 예치
- 정상 지급
- 만료 후 환불
- 분쟁 전환
- 하도급 직불
- 수수료 계산 정확성
- 재진입 공격 방어
- pause 상태 제한
- 권한 없는 호출 거부

### STEP 6 품질 게이트

- [ ] `pnpm --filter @propai/contracts build` 성공
- [ ] `pnpm --filter @propai/contracts test` 전체 통과
- [ ] 로컬 네트워크 배포 통한 ABI 정상 산출 확인 (`npx hardhat run scripts/deploy.ts --network localhost` 또는 Hardhat 노드 띄운 후 배포)
- [ ] 테스트넷 배포는 사용자의 자금/키 주입 이후 진행 (현재는 dry-run이나 생략 합의로 갈음 가능)
- [ ] Slither 정적 분석 0건 또는 허용 사유 문서화
  - **※ Slither 미설치 시 해결책 (Docker 사용):** 환경 파편화로 Slither가 로컬에 없다면 당황하지 말고 아래 Docker 명령어로 우회 검증하세요.
  - `docker run --rm -v $(pwd)/contracts:/share trailofbits/eth-security-toolbox -c "slither /share"`
- [ ] `.build-journal/step-06-contracts.md` 기록

---

## STEP 10: 테스트 구조 보조

Codex는 Playwright 기준 프론트 시나리오를 보조한다.

### 10-1. 보조 범위

- 로케일 자동 라우팅 확인
- 로그인/대시보드 진입 smoke test
- 프로젝트 상세 화면 렌더링
- SSE 보고서 화면의 기본 상태 확인
- 접근성 smoke test
- 블록체인 상태 카드 Mock 렌더링

### 전제 조건

- Claude Code가 주요 API 시나리오를 고정해야 한다.
- Gemini가 CI에서 브라우저 실행 환경과 리포트 업로드를 준비해야 한다.

---

## STEP 11: 접근성 자동 검증 연계

Codex는 구현한 접근성 요소가 CI에서 검증 가능하도록 Gemini와 연계한다.

### 11-1. 보조 범위

- 접근성 검증 대상 URL 목록 제공
- axe-core 위반 기준 확인
- Lighthouse 대상 페이지 확정
- 프론트에서 필요한 테스트 훅/셀렉터 제공

### 전제 조건

- Gemini가 CI 워크플로와 Lighthouse/axe 실행 환경을 준비해야 한다.
- Claude Code가 테스트 환경에서 필요한 API mock 또는 고정 응답을 제공해야 한다.

---

## 에이전트 연계 포인트

### Claude Code 연계

- `packages/types/`의 타입을 기준으로 프론트 props와 API DTO를 맞춘다.
- `design`, `bim`, `drone`, `agent`, `blockchain` 관련 API 응답 예제를 먼저 받아야 한다.
- SSE 이벤트 포맷은 `StreamingReport`, `AgentTimeline` 구현 전에 고정한다.
- **[진행 순서 가이드]** 내(Codex)가 STEP 6(스마트 컨트랙트)를 로컬 배포하여 ABI와 주소를 성공적으로 산출해야만 Claude Code가 STEP 7 블록체인 연동을 이어나갈 수 있으므로, 결과물을 명확히 공유한다.

### Gemini 연계

- Hasura 준비 전까지 Apollo는 비활성 또는 mock 모드로 둔다.
- 접근성/Lighthouse/Playwright를 CI에 연결할 때 결과 형식을 합의한다.
- 루트 `turbo.json`의 `type-check`/`test` 파이프라인은 Gemini 리뷰 대상이다.
- **[진행 순서 가이드]** 내(Codex)가 웹앱의 모든 접근성 테스트(STEP 11)와 테스트 스크립트 기반을 닦아주어야만 Gemini가 STEP 14(GitHub Actions 파이프라인 전체 CI/CD)를 작성할 수 있으므로, 해당 과정 시 오류 없이 `pnpm test` 등이 돌아가게 보장한다.

---

## 공통 작업 원칙

1. `packages/ui`와 `apps/web/components`의 역할을 섞지 않는다.
2. API 미완성 상태를 이유로 화면 구현을 미루지 않고 Mock-first로 진행한다.
3. 3D, 지도, WebXR 기능은 SSR 안정성을 해치지 않도록 클라이언트 컴포넌트로 격리한다.
4. ABI, 배포 주소, 환경변수 키 이름은 문서와 코드에서 동일하게 유지한다.
5. **[필수 준수 사항] 각 STEP 작업 완료 시, 반드시 아래 5단계 품질 게이트를 스스로 실행 및 통과해야 한다:**
   - ① **[리뷰]** 구현 명세 완전성 확인 (접근성 트리 / 반응형 디자인 / UI 누락 점검)
   - ② **[린팅]** `pnpm lint` (ESLint 룰 준수)
   - ③ **[타입]** `tsc --noEmit` (TypeScript 타입 에러 없음을 확인)
   - ④ **[빌드]** `pnpm build` (Next.js App Build 성공 확인)
   - ⑤ **[테스트]** `pnpm test` (또는 Axe-core URL 접근성 점검 / Hardhat 테스트 통과)
6. **[기록 강제]** 위 품질 게이트를 모두 통과한 뒤에만 `.build-journal/step-XX.md` 에 결과와 명령어 출력 로그를 기록하고 작업을 완료 처리한다. 실패 시 재시도.
7. **[보안 강제]** 시크릿 노출 금지 및 취약점 방어를 위해 `.build-journal/security-policy.md`의 공통 보안 규칙을 선준수한다.
8. 상위 명세 `부동산개발 전주기 AI 자동화 플랫폼.md`의 `STEP 5`, `STEP 6`, `STEP 10`, `STEP 11`을 최종 기준으로 삼는다.
