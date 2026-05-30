## 하네스: PropAI 부동산개발 플랫폼

**목표:** 부동산개발 전주기 AI 자동화 플랫폼의 개발 작업을 전문 에이전트 팀이 협업하여 수행

**트리거:** PropAI 관련 개발 작업(모듈 구현, STEP 구현, API 구현, UI 구현, AI 서비스 개발) 요청 시 `propai-orchestrator` 스킬을 사용하라. 단순 질문은 직접 응답 가능.

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
