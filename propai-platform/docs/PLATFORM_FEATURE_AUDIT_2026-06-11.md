# PropAI 플랫폼 기능 실사 종합 보고서

> **실사일**: 2026-06-11
> **범위**: 웹 구조·내비게이션 / CAD·BIM 프론트엔드 / CAD·설계 백엔드 / 전주기 파이프라인 데이터 흐름 / 수지분석·적산·공사비 / AI 서비스·오케스트레이션 (6개 영역)
> **방법**: 6개 영역 병렬 코드 실사 결과를 수석 아키텍트 관점에서 종합

---

## 1. 전체 요약

PropAI는 **"계산 엔진은 충실하나 연결 고리가 끊긴 플랫폼"** 이다. 개별 모듈의 깊이는 상용 수준에 근접해 있다 — 38종 4단계 세금엔진, 12단계 법정요율 원가계산, S-커브 DCF 현금흐름, SLSQP 유닛믹스 최적화, LLM 의도파싱+결정론 커널+검증 게이트의 Hypar식 설계 파이프라인, ifcopenshell 절차생성 IFC4→glb, DB 영속 수지 VCS까지 실제 코드로 동작한다. 프론트의 SSOT(useProjectContextStore) 기반 staleness 캐스케이드(부지분석→설계→공사비→수지 자동 재계산)도 설계가 우수하고 회귀 테스트로 고정돼 있다.

그러나 **핵심 차별화 가치 3가지가 모두 "외형만 있고 배선이 끊긴" 상태**다:

1. **다이나믹 워크플로우(수정값 재분석)**: 오버라이드 편집 UI·rerun-stage API가 양쪽 다 존재하지만, 백엔드는 `stage_overrides`를 읽지 않고 프론트는 그 엔드포인트를 호출조차 안 한다. 부분 재실행 시 단계간 payload가 복원되지 않아 기본값(대지 500㎡/BCR 60/FAR 200)으로 왜곡 계산된다.
2. **적산 기반 정밀 공사비**: 실 IFC 물량(ifcopenshell)·BOQ 3중단가·기하 QTO가 모두 구현돼 있으나, 수지에 실제로 주입되는 공사비는 여전히 ₩/㎡ 개산값이다. `bim_quantities` 테이블은 DDL만 있고 INSERT하는 코드가 저장소 전체에 없다.
3. **전주기(준공 후 포함) 여정**: 라이프사이클 레일이 시공계획→보고서에서 끝나고, 감리·드론·디지털트윈·운영·유지보수·임차인으로 가는 경로가 전무하다. 토지 확보 수단(경매·공매·공공입찰)도 프로젝트 여정에 합류하지 못한다.

구조적 부채 패턴은 3가지로 요약된다: **(a) 고아 코드 대량 잔존** — 프로젝트 서브라우트 9종 도달 불가, 구세대 Konva CAD 스택 약 3,000라인 미마운트, 스텁 오케스트레이터 2종(가짜값 반환), **(b) 이원화** — 수지 계산 2벌(파이프라인 약식 vs v2 모듈엔진), LLM 진입점 2벌, 레거시 `services/` vs 신 `app/services/` 트리 병존, mock 게이트 3종 혼재, **(c) 하드코딩 데이터** — 법규 ZONE_LIMITS 7존, 단가 42개 시드(경기도 단일), 분양가 정적 테이블, KCCI '시뮬레이션' 시장가.

**결론**: 신규 엔진 개발보다 **기존 부품의 배선 복원(rewiring)이 최우선**이다. 아래 퀵윈 목록의 상위 항목 대부분이 "양쪽 부품이 이미 존재하고 연결 코드만 부재"한 케이스로, 소규모 변경으로 핵심 스토리(수정→재분석, 적산→수지, 준공 후 운영)를 완성할 수 있다.

---

## 2. 영역별 성숙도 표

### 2.1 영역 종합

| # | 영역 | 종합 판정 | 성숙도 분포 (전체 12 기준) | 핵심 강점 | 핵심 약점 |
|---|------|----------|---------------------------|-----------|-----------|
| 1 | 웹 구조·내비게이션 | **양호(functional)** | production 1 / functional 8 / partial 2 / stub 1 | 6섹션 IA·역할 게이팅, precheck→프로젝트 승계, 부지분석→설계→수지 데이터 연속성 | 오펀 라우트 13종(대시보드 4+프로젝트 서브 9), 준공 후 경로 전무, mock 게이트 3종 혼재 |
| 2 | CAD·BIM 프론트엔드 | **부분(partial)** | functional 4 / partial 6 / stub 1 / missing 1 | CadBimIntegrationPanel(2D SVG+3D R3F) 실연동, 자연어·음성 생성형 설계, 비전문가 배려 UX | 구세대 CAD 스택 전체 고아, 마운트된 편집기에 undo/redo 부재, 가짜 3D 목업·가짜 AI 잔존, 협업(Y.js) 전무 |
| 3 | CAD·설계 백엔드 | **양호(functional)** | functional 9 / partial 2 / stub 1 | LLM 파싱+결정론 커널+4렌즈 검증 일관 구현, SVG 8종·DXF 5종·IFC4→glb 생성 | 편집 좌표→DXF/IFC 변환 부재, 법규 7존 하드코딩, drawings save/load 무인증, CNN 설계 명목 스텁 |
| 4 | 파이프라인 데이터 흐름 | **부분(partial)** | functional 7 / partial 1 / stub 3 / missing 1 | 7단계 서버 파이프라인 payload 체인, SSOT staleness 캐스케이드, 분석원장 | **오버라이드 재분석 루프 전면 단절**, cost/tax/compliance store 환류 누락, 출처 추적 부재 |
| 5 | 수지·적산·공사비 | **양호(functional)** | functional 10 / partial 2 | 세금 38종·원가 12단계·DCF·MC·VCS 등 엔진 깊이 최상, 회귀테스트(세금·현금흐름) | 실 IFC QTO↔공사비 완전 단절, 수지 공사비가 ₩/㎡ 개산, 단가·분양가 하드코딩, 수지 계산 이원화 |
| 6 | AI 서비스·오케스트레이션 | **양호(functional)** | production 2 / functional 7 / partial 2 / stub 1 | BaseInterpreter 공통기반(4층 캐시·그라운딩·과금), 인터프리터 11종, CAD form-filling 실동작 | AI 스트리밍 프론트 소비자 0, 검증관 실경로 OFF, 스텁 오케스트레이터 2종(허위 메시지), '대화형 시장 AI'는 비LLM |

### 2.2 주요 기능 성숙도 상세

| 기능 | 영역 | 성숙도 | 비고 |
|------|------|--------|------|
| 사이드바 IA(6섹션·역할 게이팅) | 웹 구조 | production | adminOnly/assetOpsOnly 클라이언트 게이팅 |
| LLM 멀티프로바이더·BaseInterpreter | AI | production | 3사 폴백, 4층 캐시, 토큰 과금, 그라운딩 규칙 |
| 라이프사이클 내비(10단계 레일) | 웹 구조 | functional | 순차 진행 강제, 단 직접 URL 우회 가능(비일관) |
| CAD/BIM 통합 스튜디오 | CAD FE | functional | 2D SVG 9종+3D GLB+포토리얼 렌더 실연동 |
| 생성형 설계(자연어·음성→Top3) | CAD FE / AI | functional | parse-intent→DesignSpec→결정론 커널, 법규 하드캡 |
| 결정론 자동설계 커널 | CAD BE | functional | 정북일조 단계후퇴, 위반 시 20회 축소 보정 |
| SVG 도면 8종·절차 IFC4→glb | CAD BE | functional | 인허가 도서 수준은 아닌 파라메트릭 다이어그램+ |
| 7단계 서버 파이프라인 | 파이프라인 | functional | Pydantic payload 체인, 단 서버 영속 없음 |
| SSOT staleness 캐스케이드 | 파이프라인 / 수지 | functional | MODULE_UPSTREAM 그래프+1회 자동재계산, 단 브라우저 세션 한정 |
| 수지 v2 모듈엔진(M01~M15)·세금 38종·DCF·VCS | 수지 | functional | 특화모듈 4종+범용 11종, 회귀테스트 고정 |
| 적산(QTO) 3경로 | 수지 | partial | 실 IFC 파싱은 공사비와 완전 단절 |
| 몬테카를로 | 수지 | partial | 공사비 MC 실연동, v2 라우터 MC는 토이 목적함수 |
| 마운트된 2D 편집기(design/CADEditor) | CAD FE | partial | undo/redo 없음, 단일 폴리곤 한정 |
| DXF 내보내기 | CAD BE | partial | 치수가 정식 DIMENSION 아님, 편집 기하 미반영 |
| IFC 업로드 파싱 | CAD BE | partial | IfcElementQuantity 속성 의존, 기하 기반 물량 없음 |
| saveToStore 환류 | 파이프라인 | partial | cost/tax/compliance·unit 필드 미반영 |
| 7단계 에이전트 오케스트레이터(SSE/WS) | AI | partial | 백엔드 실재, 프론트 소비자 0 |
| 대화형 시장분석 | AI | partial | LLM 미사용 — 키워드 규칙+f-string 템플릿 |
| 오버라이드 편집 UI / rerun-stage / 프론트 재실행 | 파이프라인 | **stub** | 3종 모두 외형만 — 실효 0 |
| 오펀 프로젝트 서브라우트 9종 | 웹 구조 | stub | agent·cad·drone·blockchain·contracts·cost·multi-parcel·operations·supervision |
| LangGraph 오케스트레이터 2종 | AI | stub | 하드코딩 빈값, '인허가 자동 신청 완료' 허위 메시지 |
| CNN 참조이미지 설계 | CAD BE | stub | 이미지가 설계에 실질 무영향 |
| 3D 뷰어 목업(BIMViewer3D·ThreeScene) | CAD FE | stub | CSS 회전 div / canvas 2D 가짜 3D |
| 필드 단위 출처(자동/수동) 추적 | 파이프라인 | **missing** | last-write-wins로 수동 수정값 덮어쓰기 |
| Y.js 실시간 협업 | CAD FE | **missing** | 의존성 자체 전무 |

---

## 3. 전주기 사용자 스토리라인 현재 상태

이상적 여정: **토지 발굴 → 진단 → 프로젝트 생성 → 부지분석 → 설계 → 적산·공사비 → 수지·세금 → ESG → 보고서 → 인허가 → 시공 → 감리·드론·트윈 → 준공 → 운영·임대·유지보수**

| 구간 | 상태 | 현재 배선 |
|------|------|-----------|
| 90초진단 → 프로젝트 생성 | ✅ 연결 | PreCheckWorkspace가 sessionStorage로 진단 결과 승계, 생성 폼 선채움 |
| **경매·공매 / 공공입찰 → 프로젝트** | ❌ **끊김** | AuctionWorkspace·G2BBidDashboard에 프로젝트 생성 CTA 없음(useProjectContextStore·projects/new 참조 0) — 토지 확보 수단이 개발 여정에 합류 못함 |
| 주소 입력 → 부지분석 자동 수집 | ✅ 연결 | GlobalAddressSearch→/zoning/comprehensive로 PNU·면적·용도지역·조례·공시지가·건축물대장 자동 주입 |
| 부지분석 → 설계 → 수지 | ✅ 연결 | SSOT store(MODULE_UPSTREAM 의존성 그래프+staleness)로 자동 시드·1회 자동재계산, 분석원장 서버 영속+localStorage 폴백 |
| 자연어·음성 → 설계 폼·CAD 편집 | ✅ 연결 | parse-intent/design-operate→DesignSpec→결정론 커널→2D/3D 재생성 (단, useCadStore 캔버스 반영분은 미마운트로 죽은 경로) |
| **CAD 편집 → DXF/IFC 내보내기** | ❌ **끊김** | 편집 좌표(points/lines)→DXF/IFC 직변환 코드 부재 — 내보내기는 파라미터 기반 '재생성'이라 편집이 무시됨 |
| **CAD 편집본 → 3D(glb)** | ❌ **끊김** | 편집본에 매스 치수 미저장 → GLB 복원 시 기본값 12×9m 폴백 |
| 설계 매스 → 기하 QTO → 공사비 개산 | ✅ 연결 | design_versions 매스 자동참조(qto_source=bim), /cost/estimate-overview |
| **실 IFC 물량 → 공사비 / BOQ·유닛믹스 → 수지** | ❌ **끊김** | analyze_ifc 결과는 metadata에만 저장, bim_quantities INSERT 코드 전무. BOQ 총액·유닛믹스 최적화 결과의 수지 자동 주입 경로 없음 — 수지 공사비는 ₩/㎡ 개산 |
| 공사비 → 수지(override) → 세금 | ✅ 연결 | construction_cost_override_won 주입, 전 모듈이 세금엔진 38종 경유, 이중계상 방지 |
| **수정값(오버라이드) → 재분석** | ❌ **끊김** | UI 수정→handleRerun→/pipeline/run(키 무시), rerun-stage는 stage_overrides 미소비+payload 미복원+프론트 호출 0 — **다이나믹 워크플로우 핵심 루프 미완** |
| **파이프라인 cost/tax/compliance → SSOT store** | ❌ **끊김** | saveToStore에 updateCostData·updateComplianceData 호출 없음 → 완성도 지표·finance staleness 체인 미작동 |
| ESG → 보고서(원장 PDF) | ✅ 연결 | design→esg payload, 원장 단일출처 PDF(/report/pdf-from-ledger) |
| **보고서(레일 종착) → 감리·드론·트윈·운영** | ❌ **끊김** | lifecycle-stages가 보고서로 종료. supervision·drone·digital-twin·operations·tenant·maintenance로 가는 링크 전무 — **'전주기 플랫폼' 후반부 단절** |
| 분양 ↔ 프로젝트 | ✅ 연결 | 분양 현장 생성 시 project_id 필수 |
| **프로젝트 개요 → 확장 모듈(cad·drone·blockchain·contracts 등 9종)** | ❌ **끊김** | 링크 보유 컴포넌트(ProjectSummaryClient·LifecycleNavigator)가 미마운트 데드코드 — 라우트는 완성돼 있으나 도달 불가 |
| AI 비서 ↔ 화면 데이터 | ⚠️ 부분 | pathname 힌트만 주입, SSOT 실데이터·도구호출·스트리밍 없음(백엔드 SSE/WS는 실재하나 프론트 소비자 0) |

**요약**: 여정의 **전반부(진단→부지분석→설계→공사비→수지→보고서)는 자동 흐름이 실동작**하지만, ① 입구(토지 확보 채널), ② 중간 정밀화(편집·적산의 하류 반영), ③ 되감기(수정값 재분석), ④ 출구(준공 후 운영)의 4개 관절이 모두 끊겨 있다.

---

## 4. 통합 갭 Top 10 (우선순위순)

| 순위 | 갭 | 영향 | 근거 위치 |
|------|----|------|-----------|
| **1** | **오버라이드 재분석 루프 전면 단절** — 백엔드 `project_pipeline.py`가 `stage_overrides`를 읽지 않고(사일런트 무시), rerun-stage의 previous_result는 표시용 data만 복원해 전달 payload가 None→기본값(500㎡/BCR60/FAR200) 왜곡 계산, 프론트 handleRerun은 미지원 키로 잘못된 엔드포인트 호출(rerun-stage 호출처 0건) | 핵심 차별화 기능('수정값으로 재분석')이 사용자에게 거짓 동작 — 수정값 없는 전체 재실행+외부 API 재호출 | `apps/api/app/services/pipeline/project_pipeline.py`, `apps/api/app/routers/pipeline.py:601-664`, `apps/web/components/pipeline/ProjectPipelinePanel.tsx:862-892` |
| **2** | **적산→공사비→수지 정밀 연동 단절** — 실 IFC 물량(analyze_ifc)이 공사비와 완전 단절(bim_quantities INSERT 코드 전무), BOQ 총액·유닛믹스 결과 수지 미주입, 수지에 들어가는 공사비는 ₩/㎡ 개산 | "BIM 기반 정밀 적산" 가치제안이 수지 수치에 미반영 — 정밀화해도 결과 동일 | `apps/api/services/bim_ifc_service.py`, `apps/api/app/services/cost/ifc_work_map.py`, `apps/api/app/routers/cost.py` |
| **3** | **CAD 편집 기하의 하류 단절** — 편집 좌표→DXF/IFC 직변환 부재(내보내기는 파라메트릭 재생성), 편집본 매스 치수 미저장으로 3D 복원 시 12×9m 폴백 | "생성→편집→내보내기/3D" 사슬이 끊겨 편집 작업이 무의미해짐 | `apps/api/routers/drawing.py:159`, `apps/api/app/routers/design_v61.py:549, 797-808` |
| **4** | **준공 후 사용자 여정 단절** — 라이프사이클 레일이 보고서에서 종료, supervision·drone·digital-twin·operations·tenant·maintenance 진입 경로 전무 + 경매·공매/공공입찰→프로젝트 승계 CTA 부재 | '전주기 플랫폼' 스토리의 입구·출구가 모두 막힘 — 자산운영 섹션·게이팅 구조는 이미 존재 | `apps/web/lib/lifecycle-stages.ts`, `apps/web/components/auction/AuctionWorkspace.tsx`, `apps/web/components/g2b/G2BBidDashboard.tsx` |
| **5** | **파이프라인 결과→SSOT 환류 누락** — saveToStore가 cost/compliance를 store에 미반영(updateCostData 미호출), design의 unit_count·unit_types·sellable_efficiency 미매핑, tax는 store 필드 자체가 없음 | 완성도 지표(공사비 85%·법규 단계) 도달 불가, finance staleness 체인 미작동, 세금이 cross-module에서 고립 | `apps/web/components/pipeline/ProjectPipelinePanel.tsx:498-570`, `apps/web/store/useProjectContextStore.ts` |
| **6** | **고아 코드·오펀 라우트 대량** — 프로젝트 서브라우트 9종 도달 불가, 구세대 Konva CAD 스택(커맨드라인·레이어·undo 50단계 포함 ~3,000라인) 미마운트, GenerativeDesignPanel→useCadStore 죽은 데이터 경로, 미마운트 중복 라우터·BuildingModel 2벌 | 완성된 기능이 사용자에게 미노출 + 유지보수 혼선·회귀 위험 | `apps/web/components/cad/*`, `apps/web/components/projects/ProjectSummaryClient.tsx`, `apps/api/app/routers/drawing.py` |
| **7** | **가짜값·무목업 원칙 위배 폴백** — 파이프라인 사이트 폴백(제2종일반주거·500㎡·FAR250을 실데이터처럼 주입), 스텁 오케스트레이터의 '인허가 자동 신청 완료' 허위 메시지·esg 850.5 고정값, DrawingAnalysisPanel의 setTimeout 가짜 AI, KCCI '시뮬레이션' 시장단가, 비LLM '대화형 시장 AI' | 신뢰성 리스크 — 그럴듯한 가짜 결과가 다운스트림 전 단계로 전파될 수 있음 | `project_pipeline.py:736-743`, `apps/api/app/services/agents/orchestrator.py`, `apps/web/components/cad/DrawingAnalysisPanel.tsx`, `kcci_material_price_service.py`, `conversational_market_ai.py` |
| **8** | **필드 단위 출처(자동/수동) 추적 부재 + 오버라이드 비영속** — store는 전역 dataSource 문자열뿐, 사용자 수정값이 자동 갱신에 소리 없이 덮임(last-write-wins). 'user: 사용자 입력' 라벨은 설정 경로 없는 데드코드. PipelineResultDetail 오버라이드는 로컬 state뿐(이탈 시 소실) | 사용자 입력 신뢰 훼손 — 수정한 값이 사라지거나 덮어써짐, 원장 가정버전 철학과 불일치 | `apps/web/store/useProjectContextStore.ts`, `apps/web/components/pipeline/PipelineResultDetail.tsx` |
| **9** | **법규·단가 데이터 하드코딩(신선도)** — ZONE_LIMITS 7존(조례·토지이음 API 미연동), 세율 코드 내 매트릭스, 단가 42개 시드(경기도 단일)+동기 경로는 DB 단가를 아예 안 읽음, 분양가 정적 테이블(~40개 시군구) | 법령 개정·시장 변동 미반영 — 수동 갱신 의존, 지역 정밀도 한계 | `auto_design_engine.py:35-45`, `unit_price_repository.py`, `regional_pricing.py` |
| **10** | **보안·일관성 부채** — drawings/save·load 무인증(프로젝트 UUID만 알면 타인 도면 접근), designApiBase() 프로덕션 호스트 하드코딩, mock 게이트 3종 혼재, LLM 진입점·오케스트레이터 3종 병존, 수지 계산 이원화(파이프라인 약식 vs v2 모듈엔진이 서로 다른 총사업비 산출 가능), VCS 커밋 서버 재계산 검증 없음 | 보안 취약 + 동일 프로젝트 수치 불일치 가능 + 정본 불명확 | `design_v61.py:423-546`, `CadBimIntegrationPanel.tsx`, `apps/web/lib/api-client.ts`, `project_pipeline._run_feasibility` vs `feasibility_service_v2.py` |

---

## 5. 퀵윈 목록

"양쪽 부품이 이미 존재하고 연결 코드만 부재"한 항목 위주, 효과/비용 순.

### A. 다이나믹 워크플로우 복원 (갭 #1·#5·#8 — 최우선 세트)

| # | 퀵윈 | 규모 | 효과 |
|---|------|------|------|
| A1 | `project_pipeline.run()`에 `stage_overrides` 소비 추가 — 각 `_run_*` 진입부에서 `opts.get('stage_overrides',{}).get(stage)`를 payload에 merge | 3~5행 | 기존 rerun-stage 라우터 즉시 활성화 |
| A2 | rerun-stage에서 previous_result로 전달 payload(state.site_to_design 등) 재구성 | 소 | 기본값(500㎡/60/200) 왜곡 제거 |
| A3 | `ProjectPipelinePanel.handleRerun`을 `/pipeline/rerun-stage`(stage·overrides·previous_result) 호출로 전환 | 함수 1개 | 부분 재계산 UX 완성 |
| A4 | saveToStore에 `updateCostData` 환류 + design 환류에 unitCount·unitTypes·efficiencyPct 매핑 추가 | ~10행 | 완성도 지표·finance staleness 체인 즉시 연결 |
| A5 | SiteAnalysisData에 `manualFields`(또는 필드별 {value, source}) + `isUserEdit` 플래그 — 자동 수집이 수동 필드를 덮지 않게 가드 | 소 | 출처 추적 최소 구현 |

### B. 전주기 여정 연결 (갭 #4·#6)

| # | 퀵윈 | 규모 | 효과 |
|---|------|------|------|
| B1 | AuctionWorkspace·G2BBidDashboard에 '이 물건으로 프로젝트 생성' CTA — precheck의 sessionStorage 승계 패턴(PreCheckWorkspace 161~177행) 재사용 | 소 | 토지 확보→개발 여정 입구 연결 |
| B2 | `lib/lifecycle-stages.ts`에 '운영' 단계 추가 또는 보고서 단계 뒤 NextStageCta에 자산운영 CTA | 소 | 준공 후 여정 단절 해소 |
| B3 | tenant·maintenance·digital-twin을 '자산 운영' 섹션(assetOpsOnly)에 메뉴 추가 — layout.tsx 배열에 3줄 | 3줄 | 오펀 라우트 3종 구제 |
| B4 | 프로젝트 개요에 '확장 모듈' 카드 그리드 복원(ProjectSummaryClient 재연결 또는 경량 링크 목록) | 소 | 도달 불가 서브라우트 9종 진입점 제공 |
| B5 | `/{locale}/agent` 죽은 링크(ApprovalOperationsWorkspaceClient 677행) 수정 또는 데드코드와 함께 삭제 | 1행 | 404 제거 |

### C. CAD 편집 사슬 완성 (갭 #3)

| # | 퀵윈 | 규모 | 효과 |
|---|------|------|------|
| C1 | 편집 좌표→DXF 직변환 엔드포인트(저장된 points/lines를 ezdxf LWPOLYLINE 출력) — ParametricCADService 메서드 1개 | 소 | '생성→편집→내보내기' 완성 |
| C2 | CADEditor 저장 페이로드에 building_width/depth_m·floor_height_m 포함 | 소 | 편집본 GLB 12×9m 폴백 즉시 해소 |
| C3 | design_v61 export-dxf를 drawing_type 분기로 확장(상세/단면/입면/배치 DXF 기 구현) | 라우팅만 | 도면 5종 DXF 제공 |
| C4 | ezdxf `add_linear_dim`으로 정식 DIMENSION 엔티티화 | 소 | CAD 호환성 개선 |
| C5 | design/CADEditor에 undo/redo 이식 — use-cad-store 스냅샷 패턴(MAX 50) 검증 완료 | 중 | 편집 UX 체감 효과 큼 |

### D. 적산→수지 정합 (갭 #2)

| # | 퀵윈 | 규모 | 효과 |
|---|------|------|------|
| D1 | BOQ/items_qto 합계→수지 override 선택 주입 옵션(프론트 costData에 'QTO 합계' 필드) | 소 | 적산-수지 정합 한 단계 상승, 백엔드 변경 거의 없음 |
| D2 | bim_quantities 배선 완성: analyze_ifc→ifc_work_map 공종 매핑→INSERT→OriginCostCalculator — 테이블·매핑·계산기 모두 존재, 연결 코드만 부재 | 중 | 'IFC→공사비' 단절 해소 |
| D3 | estimate-overview·표준물량 경로를 async 단가조회(UnitPriceRepository.get_price)로 전환 | 소 | DB 단가 갱신이 전 경로 반영 |
| D4 | v2 /monte-carlo를 ModuleInput 기반 실수지 함수로 교체(calculate_fn 콜백 인터페이스 기 보유), 죽은 import를 /sensitivity 엔드포인트로 전환 | 소 | 토이 목적함수 제거+민감도 API 노출 |
| D5 | 회귀테스트 보강: construction_cost_override_won 주입, /baseline·/cashflow 정답값, boq_builder=OriginCostCalculator 정합 | 중 | 적산·v2 라우터 테스트 공백 해소 |

### E. AI 품질·신뢰성 (갭 #7·#10)

| # | 퀵윈 | 규모 | 효과 |
|---|------|------|------|
| E1 | `/pipeline/interpret` 호출 body에 `use_verification_retry: true` 1행(PipelineResultDetail.tsx:399) | 1행 | 기 구현된 할루시네이션 게이트·재생성 루프 실경로 활성화 |
| E2 | PropAIOrchestrator._step_report의 ChatAnthropic 하드코딩(claude-sonnet-4-5-20250929)을 `get_llm()`으로 교체 | 1행 | 모델 단일출처 회복 |
| E3 | 스텁 오케스트레이터 2종(langgraph_orchestrator.py, app/services/agents/orchestrator.py) 삭제 또는 PropAIOrchestrator로 일원화 | 삭제 | 가짜값·허위 메시지 노출 리스크 제거 |
| E4 | AI 비서에 SSOT 요약(주소·용도지역·설계 spec) 컨텍스트 동봉 + llm.astream·createSseSubscription(미사용 기존 부품) 재사용 스트리밍 도입 | 중 | pathname 힌트→실데이터 그라운딩, 체감 응답성 개선 |
| E5 | ConversationalMarketAI에 get_llm 1회 요약 호출(MOLIT 통계 근거 주입) | 소 | '대화형 AI' 명칭에 걸맞은 최소 격상 |
| E6 | DrawingAnalysisPanel 가짜 AI를 기존 /cad-correction/check 호출로 교체, 하드코딩 법규값 제거 | 소 | 가짜 AI 제거 |

### F. 정리·보안 (갭 #6·#10)

| # | 퀵윈 | 규모 | 효과 |
|---|------|------|------|
| F1 | drawings/save·load에 get_current_user+프로젝트 소유권 검사 추가 | 소 | **무인증 도면 접근 차단(보안)** |
| F2 | 구세대 components/cad/ 스택 결단(편집모드 통합 마운트 or 삭제) — 죽은 loadDesignPayload 경로 동시 해소 | 중 | ~3,000라인 정리 |
| F3 | BIMViewer3D·ThreeScene 가짜 3D 목업 삭제 또는 ProceduralBuilding 재사용 교체 | 소 | '가짜 3D' 리스크 제거 |
| F4 | CadExportPanel 하드코딩 파라미터(parking_count:50 등)를 designData 역산값으로 대체, DXF를 res.blob() 방식 통일 | 소 | 실설계와 무관한 도면 생성 차단 |
| F5 | mock 게이트 3종을 공용 훅(useCanUseLiveApi)으로 통일, designApiBase() 하드코딩 호스트를 apiClient 런타임 설정으로 일원화 | 소 | mock 동작·API 베이스 일관화 |
| F6 | 미마운트 중복 라우터(app/routers/drawing.py)·BuildingModel 2벌·in-memory VCS 잔존물 정리 | 소 | 정본 명확화, 회귀 혼선 제거 |

---

### 권장 실행 순서

1. **1주차 (배선 복원)**: A1~A4 + E1·E2 + F1 — 합계 수십 행 수준으로 "수정값 재분석"과 검증관이 실동작, 보안 구멍 봉합
2. **2주차 (여정 연결)**: B1~B5 + C1~C3 — 입구(토지 확보)·출구(운영)·편집 사슬 연결
3. **3~4주차 (정밀화·정리)**: D1~D3 + E3~E6 + F2~F6 — 적산-수지 정합, 가짜값·고아 코드 청산
4. **이후 (구조 과제)**: 수지 계산 이원화 통합, 법규·단가 외부 API 연동, 서버측 이벤트 재계산, 파이프라인 상태 서버 영속, 협업(Y.js) 검토

*본 보고서는 2026-06-11 기준 6개 영역 병렬 코드 실사 결과를 종합한 것이다.*
