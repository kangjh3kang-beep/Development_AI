# UX 라이팅 감사 P0 적용 보고 (사이드바 라벨 직관화 + 명칭 통일)

날짜: 2026-06-06
범위: 하드코딩 한국어 라벨만. i18n 사전(common.json) 미수정. link/경로/아이콘/구조 무변경.

## 1. 변경 파일 · 교체 라벨 수
- `apps/web/app/[locale]/(dashboard)/layout.tsx` — 사이드바 라벨 12건 + 그룹명 1건 = **13건**
- `apps/web/components/operations/MarketInsightsWorkspaceClient.tsx` — h2 1건
- `apps/web/components/precheck/PreCheckWorkspace.tsx` — h1 1건 + 버튼 1건 = 2건
- `apps/web/components/operations/RegistryAnalysisWorkspaceClient.tsx` — h1 1건

총 4파일 / 17건 교체.

### layout.tsx 교체 내역
| Before | After |
|--------|-------|
| 90초 AI PreCheck | 90초 사업성 진단 |
| 마켓 분석 | 시장·시세 분석 |
| 인.허가분석 자동화 | 인허가 가능성 분석 |
| 부동산 규제 연동 | 개발 규제 한눈에 보기 |
| 토지조서 (편입토지) | 토지조서(매입 대상 토지) |
| └ 부동산등기 열람/분석 | └ 등기부등본 열람·권리분석 |
| └ 예상 시세 추정 보고서 | └ AI 시세추정 보고서 |
| └ 시행사 요약 현황 | └ 분양 요약(경영진용) |
| ESG / 탄소 경영 | ESG·탄소 평가(친환경 점수) |
| 경공매 AI 분석 | 경매·공매 AI 분석 |
| AI 자동설계 (CAD) | AI 설계도면(CAD) |
| BIM · 적산 | 3D 모델·공사물량(BIM·적산) |
| (그룹명) 입찰·자산 운영 | 공공입찰·경공매 |

## 2. 명칭 통일 적용/건너뜀
| 컴포넌트 | 대상 | 상태 |
|----------|------|------|
| MarketInsightsWorkspaceClient.tsx | "시장 동향 분석" → "시장·시세 분석" | 적용 |
| PreCheckWorkspace.tsx | "AI 즉시 진단"(h1) → "90초 사업성 진단" | 적용 |
| PreCheckWorkspace.tsx | "90초 즉시 진단"(버튼) → "90초 사업성 진단" | 적용 |
| RegistryAnalysisWorkspaceClient.tsx | "부동산 등기정보 분석"(h1) → "등기부등본 열람·분석" | 적용 |

- 참고: PreCheckWorkspace 162행 배지 "90초 PreCheck"는 명명 목록(AI 즉시 진단/90초 즉시 진단) 외라 과도변경 방지 차원에서 미수정.
- RegistryAnalysisWorkspaceClient 실제 h1 문구는 "부동산 등기정보 분석"(:161)이었음 → 사이드바 하위 라벨(등기부등본 열람·권리분석)과 정합되도록 "등기부등본 열람·분석"으로 통일.

## 3. tsc / eslint
- `npx tsc --noEmit` → **EXIT 0**
- 변경 4파일 eslint: 신규 오류 0. RegistryAnalysisWorkspaceClient.tsx:315 의 react/no-unescaped-entities 오류 2건은 **기존 결함**(stash 검증으로 확인, 본 편집 라인 161과 무관). 나머지 경고(unused vars 등)도 전부 기존.

## 4. 커밋
- 메시지: `feat(ux): 사이드바·메뉴 용어 직관화(전문가+일반인 이해) + 명칭 통일`
- add 경로 명시(4파일만), push 금지.
- 해시: (본문 하단 보고 참조)

## 5. 다국어(common.json) 후속 필요 메모 (P2)
- 본 작업은 하드코딩 라벨만. 동일 라벨의 i18n 키(ko/en/zh)는 미반영.
- 후속(P2)에서 `common.json` 의 nav/메뉴 키를 위 신규 한국어와 일치시키고, en/zh 번역도 동일 의미로 정렬 필요(예: precheck="90초 사업성 진단", market="시장·시세 분석", permits="인허가 가능성 분석", regulations="개발 규제 한눈에 보기", esg, auction, design/bim 등).
- 현재는 사이드바가 하드코딩 라벨을 직접 렌더하므로 화면-표시상 불일치 없음. i18n 전환 시 키 동기화 필수.
