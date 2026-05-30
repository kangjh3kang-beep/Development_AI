---
name: propai-g2b-integration
description: PropAI 나라장터(G2B) 공공입찰 연동 스킬. 조달청 입찰공고/낙찰정보 API 수집, AI 입찰 분석(적정 투찰가·사업성·리스크), 6개 엔진(수지/QTO/시장동향/용도지역/인허가/ESG) 유기 연동을 구현한다. '입찰분석', '나라장터', 'G2B', '투찰가', '공고 수지분석', '공공입찰', '낙찰가율' 요청 시 사용. 입찰 데이터 수집·정밀분석·대시보드 구현/수정/보완에도 사용.
---

# PropAI 나라장터(G2B) 입찰 연동 스킬

조달청 나라장터 입찰/낙찰 정보를 사통팔땅 플랫폼에 통합하여 "공고 클릭 → AI 수지분석·BIM 공사비(QTO) → 마진·최적 투찰가 자동 산출"을 제공한다.

## 라이브 검증된 API 명세 (data.go.kr 1230000, 키=MOLIT_API_KEY 공용)

**입찰공고** `GET http://apis.data.go.kr/1230000/ad/BidPublicInfoService/{op}`
- op: `getBidPblancListInfoCnstwk`(공사)/`...Servc`(용역)/`...Thng`(물품)/`...Frgcpt`(외자)
- params: `serviceKey, type=json, pageNo, numOfRows, inqryDiv=1, inqryBgnDt(YYYYMMDDHHMM), inqryEndDt`
- 응답: `response.body.items`(리스트), `.totalCount`
- 실필드: `bidNtceNo, bidNtceNm, presmptPrce(추정가), bdgtAmt(예산), bidNtceDt, bidClseDt, opengDt, cntrctCnclsMthdNm, cnstrtsiteRgnNm(현장지역), bidNtceDtlUrl`

**낙찰정보** `GET http://apis.data.go.kr/1230000/as/ScsbidInfoService/{op}` — op `getScsbidListSttus{공종}`, params 동일(`inqryDiv=1`).
- 실필드: `bidNtceNo, bidwinnrNm(낙찰자), sucsfbidAmt(낙찰금액), sucsfbidRate(낙찰가율%), prtcptCnum(참가업체수), rlOpengDt`

⚠️ `inqryDiv=1` 누락 시 0건. 구버전 `/BidPublicInfoService04`·baroApi는 오류.

## 핵심 파일 (apps/api, G2B는 app.* 트리·app.core.database.Base)
- `app/integrations/g2b_client.py` — G2BClient(BID_OPERATIONS/AWARD_OPERATIONS dict, fetch_all_bid_notices/fetch_all_award_results)
- `app/services/g2b_bid_service.py` — 수집·저장·필터(_is_relevant_bid 건설키워드), list_bids/get_dashboard_stats/get_award_stats
- `app/services/ai_services/bid_analyzer.py` — BidAnalyzer.analyze(경량)/analyze_feasibility(6엔진), reverse_estimate_spec, BidFeasibilityIntegrator
- `app/models/g2b_bid.py`, `app/schemas/g2b_bid.py`, `app/routers/g2b_bid.py`(8라우트)
- `app/tasks/g2b_sync_task.py` + `apps/worker/main.py`(arq cron)
- 프론트 `apps/web/components/g2b/`(G2BBidDashboard/G2BBidAnalysisModal/G2BAwardStats), `app/[locale]/(dashboard)/g2b/page.tsx`

## 추정가격 역산 (입찰엔 연면적/주소 없음)
공고명 정규식 분류 → `CONSTRUCTION_COST_PER_PYEONG`(아파트6.5M/공동주택6.2M/오피스텔6.8M/다세대5.5M/근생5.8M 원/평) × 구조보정 × 지역보정 → `연면적 = estimated_price/평당공사비 × 3.3058`. 수동보정(req.total_gfa_sqm 등) 우선. source=auto/notice/manual + confidence.

## 6엔진 연동 체인 (analyze_feasibility)
```
역산spec → [QTO]StandardQuantityEstimator → [원가]OriginCostCalculator
→ [원가MC]CostMonteCarlo → [수지MC]run_monte_carlo(낙찰가×낙찰가율 − QTO실원가)
→ [민감도]run_sensitivity_analysis → [용도지역]AutoZoningService(async)
→ [법규]permit_validator → [ESG]GresbScoringService → [시장]G2BAwardStat 피드
```
각 단계 독립 try/except(실패 시 섹션 None + analysis_warnings). 적정투찰가 = max(손익분기 BEP, 지역평균) 결합으로 흑자 보장.

## 부족 입력 처리
| 모듈 | 부족분 | 처리 |
|------|--------|------|
| QTO/원가 | 연면적·구조 | 역산/수동보정. 용역·물품은 미적용(간이) |
| AutoZoning | 정확주소 | cnstrtsiteRgnNm 근사, zone_type None 허용 |
| 법규/ESG | 설계상세 | 추정 연면적 기반 "참고용" |

## 검증
- 역산: estimated_price=5e9 "○○아파트" → building_type="아파트", gfa>0, 층수 추출.
- 원가체인: QTO len>0 → total_project_cost>0 → CostMonteCarlo base_total>0(base 키 계약: direct_material_cost/total_labor_cost/direct_expense_cost/total_project_cost).
- 검증 실행: `PYTHONPATH=apps/api:.` 필요(models가 apps.api.database.models import). Bash 출력이 한글에서 깨지면 파일/base64로 우회.

## 주의
- 모델 레지스트리 이원화(G2B=app.core.database.Base, 운영=apps.api.database.models.Base) → 마이그레이션 수동(database/migrations/020_g2b_bid.py).
- 라우터는 main.py에 `apps.api.app.routers.g2b_bid`로 등록(bank_report 선례).
