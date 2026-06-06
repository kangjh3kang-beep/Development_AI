# 42. UX 멜트인 — 상세탭 다이어트 + 블록체인/환경3D 녹여내기 + 용어 한글화/AI토글

①(d8f9c3d 사이드바 재편) 위 증분. 루트: propai-platform/apps/web. push 금지.

## A. 프로젝트 상세 탭 17 → 10개 다이어트
대상: `components/projects/LifecycleNavigator.tsx` (8 스테이지 × 서브탭).

| 스테이지 | 변경 전 서브탭 | 변경 후 | 비고 |
|---|---|---|---|
| 개요 | 1 | 1 | 유지 |
| 입지 분석 | 1 | 1 | 유지 |
| 법규 검토 | 1 | 1 | 유지 |
| 건축 설계 | 설계AI+도면+BIM (3) | 설계AI + BIM·도면 (2) | 도면(CAD)을 BIM 탭으로 통합 라벨링(`/bim`). `/cad` 라우트 보존 |
| 사업성 검토 | 수지+재무+ESG/LCA (3) | 수지+재무+ESG(친환경) (3) | LCA → ESG에 흡수(라벨 단일화) |
| 인허가/계약 | 인허가+블록체인+전자계약 (3) | 인허가+전자계약 (2) | **블록체인 탭 제거** |
| 시공 관리 | 시공원가+드론 (2) | 시공원가 (1) | **드론 탭 숨김**(라우트 보존) |
| 운영 | 자산운영+보고서 (2) | 보고서 (1) | 스테이지명 "보고서", 자산운영 단독탭 비노출(라우트 보존) |

서브탭 합계 **17 → 10**. 제거/숨김: 블록체인(제거), 드론(숨김), 자산운영(숨김), CAD(BIM 통합). 사용하지 않게 된 아이콘 정의(Cad/Chain/Drone/Operations) 제거 → eslint no-unused 0. 라우트 파일·콘텐츠 컴포넌트는 모두 보존(탭 정의만 제거) → tsc 깨진 참조 0.

## B. 블록체인 → "위변조 방지 신뢰검증"으로 녹여내기
- 신규 `components/common/TrustBadge.tsx`: 순수 표식(추가 네트워크 호출 0). 라벨 "블록체인 기반 위변조 방지 검증" + 해시체인 원장 무결성 근거 설명(title). 실제 변조탐지/계산검증은 기존 VerificationBadge가 담당.
- 결합 위치 2곳(과설계 금지 — 핵심 보고서·사업성 결과):
  - `components/report/BankReadyReportBuilder.tsx` 헤더(은행제출용 보고서).
  - `app/.../projects/[id]/feasibility/page.tsx` 히어로(사업성 핵심 결과).
- 별도 "블록체인" 메뉴/탭/STO 노출 제거(A에서 탭 제거). STO(조각투자)는 라우트 보존·메뉴/탭 비노출(이번 미노출).

## C. 환경3D(일조/조망/스카이라인) → 의사결정 단계 보조카드로 녹여내기
- 신규 `components/environment/EnvironmentSummaryCard.tsx`: `POST /api/v1/environment/analyze` 재사용. `focus` prop으로 단계별 요약만 표출. graceful — 실패/데이터부족 시 `return null`(섹션 숨김), 추가 호출이 기존 화면 무파괴.
  - `focus="solar"`: 정북 일조사선·동지 일조시간(법정 요건) → **인허가 화면**(`projects/[id]/permit/page.tsx`). north_setback.applies 시 강조(amber).
  - `focus="view"`: 조망 개방도·스카이라인(분양가 근거) → **사업성**(`FeasibilityEditorV2.tsx` result 탭, FeasibilityResultView 직하).
- 주소/PNU는 `useProjectContextStore().siteAnalysis`에서 취득. 부지분석의 기존 전체 `EnvironmentAnalysisPanel`은 그대로 유지(상세는 한 곳, 단계에는 컴팩트 요약). 두 카드 모두 "상세는 부지분석 환경 패널 참조" 안내.

## D. 용어 한글화 + AI카드 토글
- 용어(하드코딩만; common.json은 범위 외):
  - LifecycleNavigator: "ESG / LCA" → "ESG(친환경)".
  - ESG 페이지 헤더: "Carbon Life-Cycle Analysis" → "전과정 탄소분석 (LCA · Life-Cycle Analysis)".
  - ProjectEsgWorkspaceClient(ko): LCA → "전과정 탄소산출(LCA)", EPD → "자재 환경성적(EPD)".
  - BillingDashboard: "기성·EVM" → "기성·성과측정(EVM)".
- AI 해석 카드 자동펼침 → 기본 접힘(토글). `AnalysisVerdict` `defaultOpen` 제거 3곳:
  - ProjectFinanceWorkspaceClient(AVM 해석), ProjectEsgWorkspaceClient(탄소 해석), DigitalTwinAiCard(가상준공 해설).
  - 검증 배지는 AnalysisVerdict 상단에서 `open`과 무관하게 항상 표시 → 검증배지 상시 노출 유지.

## E. 핵심 무손상
- 깔때기·정상화면 무파괴: 라우트/콘텐츠 컴포넌트 보존(탭 정의만 축약), apiClient import 보존, 다크·토큰색만 사용, 추가 호출 전부 graceful.

## F. 검증
- `npx tsc --noEmit` → **EXIT 0**.
- 변경/신규 12파일 eslint → **EXIT 0**(0 error). 단, `ProjectEsgWorkspaceClient.tsx`의 `CardTitle` no-unused 경고 1건은 **사전 존재**(stash 비교 확인) — 이번 변경과 무관, 범위 외.

## G. 메모(후속)
- common.json(i18n)의 전문용어는 이번 범위 외 — 필요 시 별도 작업.
- STO(조각투자) 라우트는 보존만 됨 — 노출 정책 결정 시 별도.
