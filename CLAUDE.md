## 하네스: PropAI 부동산개발 플랫폼

**목표:** 부동산개발 전주기 AI 자동화 플랫폼의 개발 작업을 전문 에이전트 팀이 협업하여 수행

**트리거:** PropAI 관련 개발 작업(모듈 구현, STEP 구현, API 구현, UI 구현, AI 서비스 개발) 요청 시 `propai-orchestrator` 스킬을 사용하라. 단순 질문은 직접 응답 가능.

## 버그수정 기본정책 (기록 + 전역 전파방지) — 필수

오류·버그·개선을 수정할 때마다 **항상** 두 가지를 함께 수행한다(단발 국소 패치 금지):

1. **기록·저장·공유**: 증상·근본원인·수정과정·라이브검증 결과를 남긴다(커밋 메시지 + 세션 메모리 / `_workspace`).
2. **전역 전파방지(★핵심)**: 버그의 **패턴**을 일반화해, 같은 문제가 **다른 페이지·기능·분석폼·엔드포인트에서도 재발하는지 플랫폼 전역을 스윕**하고 발견한 진짜 오점을 함께 고친다. 수정은 **공용 함수/헬퍼·표준 계약으로 추출**해 한 곳을 고치면 전역이 따라오게 한다.

수정 워크플로우: 근본원인 확정(라이브 그라운드 트루스) → **정답 기준선**(올바르게 동작하는 경로)과의 격차로 패턴 정의 → 공용화 수정 → 전역 스윕(진짜/오탐 트리아지, 대규모는 병렬 오케스트레이션) → 라이브검증 → 기록. (예: 2026-06-19 산/임야 용적률 과대표시 버그 = 90초진단 카드뿐 아니라 `land_report` PDF에도 동일 결함 → 공용헬퍼 `_enrich_effective_and_special`(실효 `calc_effective_far`+`detect_special_parcel`)로 일원화.) 무목업·완결 게이트·실시간 기록공유와 함께 적용.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-05-27 | 초기 구성 | 전체 | 하네스 신규 구축 |
| 2026-05-27 | Mock→Live 전환 | api-client.ts | 프론트엔드 기본 모드를 Live로 변경 |
| 2026-05-27 | Tier1 WorkspaceClient 7개 신규 | Legal, Construction, ESG, SiteAnalysis, Permit, CostAnalytics, InvestmentAnalytics | ModulePlaceholder→실제 API 연동 |
| 2026-05-27 | Tier2 WorkspaceClient 6개 신규 | Permits, Regulations, Tenant, Safety, MarketInsights, Approvals | 운영 모듈 프로덕션 전환 |
| 2026-05-27 | 백엔드 스텁 보강 | drone_iot, regulation_monitor, energy, alris_service | Fallback 구조화, 법규 RAG 20개 확장 |
| 2026-05-27 | 13개 페이지 업데이트 | page.tsx 13개 파일 | WorkspaceClient 연동 |
| 2026-05-27 | Stage1: 모세혈관 네트워크 | useProjectContextStore, ProjectLifecyclePipeline | 모듈간 데이터 자동 흐름, 10단계 라이프사이클 |
| 2026-05-27 | Stage2: CAD 고도화 | CadCompliancePanel, CadBimSidePanel, CadExportPanel, design-to-cad-converter | 법규검증, BIM연동, 도면내보내기 |
| 2026-05-27 | Stage3: 디자인 퀄리티 | tokens.css, globals.css, SidebarNav, AnimatedCounter, TiltCard, GridBackground | 색상통일, 타이포강화, 동적UI |
| 2026-05-27 | Stage4: 미구현 보완 | ReportPdfDownload, AiTokenUsage, WebhookMgmt, OnboardingWizard | 기획서 갭 해소 |
| 2026-05-27 | Critical 계산오류 수정 | tax(취득세/양도세/종부세), finance(복합이자), revenue(임대수입), legal(건폐율), energy(BEEC), vworld(좌표계) | 7건 Critical 버그 수정 |
| 2026-05-27 | 공공데이터 실시간참조 기반구조 | validator.py, public_data_registry.py, calculation_metadata.py, data_integrity router | 할루시네이션 방지, 데이터 신선도 검증, 계산 메타데이터 |
| 2026-05-27 | Innovation1: 유닛믹스 최적화 | unit_mix_optimizer.py, UnitMixOptimizerPanel.tsx | SLSQP 기반 수익극대화 평형배분 (ArkDesign 벤치마크) |
| 2026-05-27 | Innovation2: 대화형 시장분석 AI | conversational_market_ai.py, ConversationalMarketPanel.tsx | 자연어→실거래 조회→차트 생성 (Deepblocks ChatDB 벤치마크) |
| 2026-05-27 | Innovation3: 자동 용도지역 감지 | auto_zoning_service.py, AutoZoningBadge.tsx | 주소→PNU→용도지역→법규한도 자동매핑 |
| 2026-05-27 | Innovation4: 은행제출용 보고서 | bank_ready_report_service.py, BankReadyReportBuilder.tsx | PF대출 심사용 10섹션 통합보고서 (Feasibly 벤치마크) |
| 2026-05-27 | Innovation5: GRESB ESG 스코어링 | gresb_scoring_service.py, GresbScoreCard.tsx | GRESB 2025 기준 자동 ESG 점수 산출 |
| 2026-05-28 | 킬러기능: Top3 자동추천 파이프라인 | permit_validator.py, auto_recommend_top3(), AutoRecommendPanel.tsx, BusinessModelRefineModal.tsx | 주소입력→15모델시뮬→인허가검증→Top3추천→수정→완성 |
| 2026-05-31 | 나라장터(G2B) 6엔진 연동 | bid_analyzer, schemas, routers, 프론트 모달 | 입찰 추정가격→QTO/수지/용도지역/인허가/ESG/시장 정밀분석 + 적정투찰가 |
| 2026-06-14 | 멀티세션 협업체계 수립 | WORKTREES.md, coordination/, scripts/ | 세션 간 브랜치 충돌 방지(워크트리 격리)+조율 보드 |

## 멀티세션 협업 (필수 — 여러 Claude 세션이 동시 작업)

이 저장소는 **여러 Claude 세션이 동시에** 개발한다. 충돌(특히 같은 워크트리에서 브랜치 전환→HEAD 충돌→엉뚱한 브랜치 커밋)을 막기 위해 **세션 시작 시 반드시**:

1. **공유 보드를 읽는다**: `scripts/coord.sh status` (보드는 우리 저장소의 공유 git 디렉토리 `.git/coordination/BOARD.md` — 모든 워크트리가 같은 한 부를 보고 이 저장소에만 스코프). 누가 어느 브랜치·영역을 작업 중인지 파악.
2. **브랜치당 전용 워크트리에서만 작업한다.** 공유 메인(`Development_AI/`)에서 feature 브랜치 `git checkout` 금지. 전용 워크트리 생성: `scripts/new-worktree.sh <branch>`. (git이 동일 브랜치 이중 checkout을 거부하므로, 한 번 전용 워크트리에 두면 충돌이 구조적으로 불가능.) 상세: `WORKTREES.md`.
3. **공유 파일(예: `main.py` 라우터 등록) 편집 전 claim**: `scripts/coord.sh claim <영역>` → 완료 후 `release`. 진행/완료는 `scripts/coord.sh note <내용>`.
4. **커밋 전 `git branch --show-current`로 자기 브랜치 확인.** main 직접 푸시 금지.
5. 명시적 인계는 `mcp__ccd_session_mgmt__send_message`(사용자 확인). 전체 규약: `coordination/PROTOCOL.md`.
