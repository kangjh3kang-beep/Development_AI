# 통합 단일창 워크스페이스 리팩토링·업그레이드 계획 (2026-06-26)

> OMC 기획 워크플로(whurqmtvh, 5에이전트) 종합 + 사장님 2-Tier 스토리라인 steer 반영.
> 목표: 분석마다 페이지를 옮겨다니는 파편화 워크플로우 → **첫 방문 통합 요약 캔버스(Tier1) + 전문 심화 전용 창(Tier2)** 의 2단 스토리라인으로 재편해, jootek式 단일창을 넘어 디벨로퍼 전주기 의사결정 단일창으로 **독보적 격상**.
> 코드 무변경(기획) 단계. 전 작업 additive·기존 자산 재배치(재구현 아님)·전용 라우트 무손상.

---

## 0. 핵심 골격 — 2-Tier 스토리라인 (★사장님 확정 방향)

```
주소 1회 입력 → [Tier1 통합 요약 캔버스]  각 항목 시각 요약(지도·텍스트·그래프·3D썸네일·AI Go/NoGo)
                      │   비전문가도 한눈에 가치·기회·리스크 파악 (대행)
                      └─ 항목별 "전문 분석 열기 →" ─→ [Tier2 전용 창]
                                                      상세분석·시뮬·설계·BIM·상세적산·상세수지·보고서
                                                      (전문가 심화, 자체 URL·풀캔버스, 새 창/탭)
```

- **Tier1 = 진입 디폴트·요약 허브(단일창)**: 경량·고속·시각적. 페이지 이동 0.
- **Tier2 = 전문 심화 전용 창**: 중량 도구는 **모달로 욱여넣지 않고 전용 창 유지**(자원 격리·기존 투자 보존). Tier1의 해당 요약 항목 CTA로 진입.
- **경량/중량 분리 원칙**: 요약 가능한 경량 분석만 Tier1로 흡수, 6대 중량 도구(상세분석·시뮬·설계·BIM·상세적산·상세수지)는 Tier2 전용 창.

> ※ 종합안 초안의 "전용페이지를 전부 슬라이드오버/모달로 흡수" → **경량만 인-패널, 중량 6대는 전용 창**으로 교정(사장님 steer). 이유: BIM WebGL·설계 스튜디오·5D 적산·수지 편집기는 메인스레드/메모리 점유가 커 단일창에 박으면 요약창이 느려져 첫인상을 해침(과거 설계패널 자동마운트 WebGL 진입멈춤 이력, b5f216e).

---

## 1. 현행 진단 (증거 기반)

- **page-hopping ~24 라우트**: 프로젝트 1건당 `projects/[id]/*` 서브라우트 실측 24개(site-analysis/legal/permit/design/bim/cad/esg/finance/construction/feasibility/cost/report/multi-parcel/operations/supervision/agent/orchestrate/boq/contracts/drone/blockchain/collaboration/canvas). 한 부지 종합판단에 최소 10페이지 이동.
- **단일창 시도(canvas)조차 점프 유발**: 8탭이 전부 `DrillCta(상세 →)`로 전용페이지 이탈(land→site-analysis, regulation→legal, development→permit, solar→design, feasibility→feasibility+cost, summary→report). 요약만 보여주고 실작업은 다시 점프.
- **중복 분석 surface 3중화**: `/analysis`(ComprehensiveAnalysisPanel 7섹션·projectId 무관) vs `site-analysis`(1281줄 메가페이지 단일스크롤 10+카드) vs `canvas`(요약탭). 정본 불명확.
- **얇은 셸 라우트**: legal/feasibility/finance/report/cost/esg page.tsx = WorkspaceClient 1개 래핑 → 불필요한 라우트 전환 양산.
- **지도 분절**: `mapMode`가 구획도(ParcelBoundaryMap)↔실거래(NearbyTransactionsMap) **배타 전환** — jootek式 다레이어 동시 토글 아님. 우측 본맵 직접 클릭선택 부재(onParcelClick 콜백은 존재하나 미배선).
- **발견성 부재**: `/projects/[id]/canvas`가 사이드바/nav 미등록 → 단일창이 진입동선에서 숨겨져 디폴트가 못 됨.
- **AI 빈약**: AiInsightCard가 가장 풍부한 comprehensive(7카테고리)가 아니라 `/zoning/analyze`만 호출 → 단일창 AI 해석이 빈약한 데이터원.
- **고아 땜질**: ExtensionModulesGrid + ProjectToolIndex가 둘 다 '도달불가 서브라우트 링크 카드'를 렌더 = 통합 실패를 링크로 땜질한 구조적 증거.

---

## 2. 목표 IA — Tier1 통합 요약 캔버스 (SiteCanvas 승격)

3영역 레이아웃(SiteCanvas 기반):
1. **상단 히어로 바**: GlobalAddressSearch(SSOT 단일입력)·다필지 통합배지·**★Decision Brief Go/CONDITIONAL/HOLD 종합판정**·진행률(LifecycleProgressRail 흡수).
2. **좌측 맥락형 탭 rail(~400px, `grid-cols-[400px_1fr] min-w-0`)** — jootek 맥락 + 우리 차별 탭:
   - 토지 / 규제 / 입지·학군 / 개발방식·Top3 / 설계·일조 / 수지·금융 / **시니어 자문** / 통합·보고서 / 구획도
   - 각 탭 = **컴팩트 요약 카드(상시) + "전문 분석 열기 →" CTA**(중량) 또는 인-패널 확장(경량).
3. **우측 통합 카카오 지도(1fr)**: KakaoMapControls 단일 툴바 — **레이어 토글로 원하는 항목만 표시**(이동 없이 한 창). 토글 그룹:
   - [부지] 필지경계·통합외곽 / [거래] 실거래·추정가(총액·평당 토글) / **[기회] 경매(온비드)·분양(청약·매물)** / [분석] 3D건물 미리보기·건축가능땅·산 / [베이스] 일반·항공·지적편집도·지형도·노후도 / [행정] 법정동경계·개발사업지구·학군마커·POI / 로드뷰
   - 동작: 항목별 다중 on/off(기본 경계+실거래). 한 지도에서 토글만으로 경매·분양·실거래·규제 등을 골라봄.
- 반응형: `<lg`는 지도 상단 collapse·탭 전폭·탭바 가로스크롤. **전용 라우트 24개 무손상**(딥링크 가능), 단 1차 동선은 단일창.

---

## 3. 기능 배치 — Tier1 흡수(경량) vs Tier2 전용 창(중량)

### 3-A. Tier1 요약 캔버스로 흡수(경량·인-패널)
| 기존 | Tier1 배치 |
|---|---|
| ComprehensiveAnalysisPanel(7섹션 완결형) | **단일창 데이터 정본** — comprehensive 1콜로 토지/규제/시장/입지/개발방식 탭 동시 채움. projectId 바인딩 추가 |
| DecisionBriefPanel(GO/CONDITIONAL/HOLD) | 상단 히어로 종합판정 배지(주소 시 자동 실행) |
| LandIntelligence/Profile/SiteScore/InfraPoi/Terrain/Environment 카드 | 토지·입지 탭 컴팩트 요약(스크롤 누적 메가페이지 → 탭 분산) |
| AutoZoningBadge·BuildableEnvelope·RegulationDigest·LegalDiscovery·PermitGuide | 규제·개발방식 탭 요약 |
| SolarPlacementCard(일조 요약) | 설계·일조 탭 요약 |
| SeniorVerdictCard / senior_consultation | **신규 '시니어 자문' 탭** 요약(9전문가 PASS/WARN/BLOCK) |
| auto_recommend_top3 / DevelopmentScenarioCard | 개발방식·Top3 탭 요약(허용용도·인허가 로드맵) |
| 등기 권리분석·대지지분·AVM·가격 시계열 | 토지 탭 드릴다운(소유자 지분·말소기준권리·추정가) + 신규 경량 가격차트(jootek 패리티) |
| 우측 지도(Parcel/Nearby/KakaoControls) | 배타 mode → 레이어 동시 토글·총액평당·우측 본맵 직접 클릭선택 |

### 3-B. Tier2 전용 창 유지(중량·CTA 연결) ★사장님 명시
| 기존 전용 도구 | Tier2 처리 |
|---|---|
| **상세분석**(comprehensive 전체·심층) | 전용 창 유지, 토지/통합 탭 요약에서 "상세분석 →" |
| **상세 시뮬레이션** | 전용 창, 개발방식·수지 탭 CTA |
| **설계 스튜디오(CAD)** | 전용 창(`design`/`cad`), 설계·일조 탭 "설계 스튜디오 열기 →"(WebGL 게이트 유지) |
| **BIM 풀 3D** | 전용 창(`bim`/threejs), 설계 탭 CTA. Tier1엔 **경량 매스 미리보기**(ProposalMassPreview·frameloop=demand)만 |
| **상세 적산(5D QTO)** | 전용 창(`cost`/`boq`), 수지 탭 CTA |
| **상세 수지(민감도 편집)** | 전용 창(`feasibility`/`finance`), 수지·금융 탭 CTA |
| **은행제출 보고서(10섹션 PDF)** | 통합 탭 'PDF 생성' CTA → report 전용 창 |
| 9노드 오케스트레이션 DAG | 통합 탭 'AI 통합실행' 패널(경량 트리거) → 상세는 orchestrate 창 |
| **토지조서 관리**(land-schedule·다필지 매입가·구획도) | 별도 **관리 페이지** 유지. 토지 탭 요약(필지수·통합면적·적정매입가)에서 "토지조서 관리 →" |
| **등기부 관리**(registry·등기열람·다필지 누적) | 별도 **관리 페이지**. 토지 탭 요약(소유자·말소기준)에서 "등기부 관리 →" |
| **권리분석**(법무사 그라운딩·인수/소멸·인수율) | 별도 **관리 페이지**(등기 연계). 토지 탭 "권리분석 →" |
| **시세추정(AVM)**(desk-appraisal·다필지) | 별도 관리 페이지. 토지 탭 추정가 요약에서 "시세추정 →" |

> 경량(legal/esg 요약 등)은 Tier1 탭 인-패널, **중량 6대 + 보고서 + 자산·권리 관리(토지조서/등기/권리분석/AVM)는 Tier2 전용 페이지**. 모달 흡수 ❌. Tier1 토지 탭엔 핵심 요약만, 관리·편집·다필지 누적은 전용 관리 페이지.

---

## 4. jootek 패리티 (기존 자산 재사용 경로 — 재구현 0)
- **3D 건물**: ProceduralBuilding(정북일조 단계후퇴 Three.js)+ProposalMassPreview(frameloop=demand 가드)를 우측지도 '건물' 레이어/설계탭 경량 미리보기. 정밀 BIM은 Tier2 `/bim/threejs` 창.
- **로드뷰**: KakaoMapControls에 Roadview+RoadviewClient+PiP **이미 구현** → 우레일 모드 노출만. ★선결: `NEXT_PUBLIC_KAKAO_MAP_KEY` 실 JS키(현재 더미 → 라이브 미작동).
- **지도 레이어 토글**: 항공/위성·지적편집도 보유 → 지형도·노후도·법정동경계·개발사업지구·건축가능땅/산·학군 green마커를 KakaoMapControls 단일헬퍼에 추가(데이터소스 단계적). 한 곳 추가=전 카카오맵 전파.
- **총액·평당 토글**: NearbyTransactionsMap InfoWindow 보유 → 우레일 글로벌 토글 승격.
- **가격 시계열 차트**: 미보유 → comprehensive transaction_prices/land_prices+AVM으로 신규 경량 차트 1종.
- **경매·분양 지도 레이어(★보강·우리 우위)**: 경공매 온비드 연동(순위/공고/유찰·낙찰가율 getInqRnkClg·getPbancList2·getCltrBidRsltList2)·분양정보(청약홈 5유형·관심지역 모니터링) **이미 보유** → 지도 토글 레이어로 surface(경매 물건 마커·분양 단지 마커). jootek 미보유 — 시장 기회까지 한 지도에서 토글로 확인하는 우리 우위.

---

## 5. ★독보적化 — jootek 미보유 AI 자산을 단일창 전면 배치
1. **상단 Go/NoGo 배지**(decision_brief): 특이부지·법규 BLOCK 자동강등(가짜 GO 차단). jootek엔 결론 판정 자체가 없음.
2. **comprehensive 1콜 통합해석**(실효용적률·종상향 잠재·건축가능항목·특이부지 게이트·근거/법령링크·LLM 해석). jootek은 정보 열람, 우리는 통합 해석+판정.
3. **시니어 자문 탭**(9전문가 정량 PASS/WARN/BLOCK+법조문 citation). jootek '추천 전문가'는 프로필 카탈로그뿐.
4. **규제탭 심의엔진 PASS/BLOCK**(다조항 준수·해시체인 무결성) — 건축심의 통과가능성 사전계산. jootek 전무.
5. **개발방식 Top3**(인허가검증×수익×복잡도 랭킹·특이부지 게이트).
6. **설계 자동생성**(IFC4 절차생성·평형믹스·일조준수 배치) → 인허가·적산까지 연결.
7. **통합·보고서**: 은행제출 10섹션 PDF + 9노드 오케스트레이션. jootek 미보유 B2B 산출물.
8. **다필지 통합분석** 지도 내장·**GRESB ESG**·**등기 권리분석**·**근거/법령링크 표준계약**(verified URL만).

---

## 6. UX 원칙 (웹디자이너)
- **컴팩트 요약 + 온디맨드 드릴다운**: 탭은 1화면 컴팩트 카드(핵심 수치·배지)만 상시, 상세는 확장/전용창. 현 FULL카드 `max-h-[60vh] overflow` 안티패턴 제거 → 카드에 `compact` prop.
- **정보위계 3단**: ①히어로(Go/NoGo·주소·진행률) ②탭 컴팩트 요약(스캔) ③드릴다운/전용창 상세. **한 화면 한 결론**.
- **디자인 토큰 100%**: 하드코딩 색 금지(surface/line/text/accent-strong·chart-1~6). @propai/ui 프리미티브(Tabs/Card/Dialog/Table) 재사용.
- **반응형 + bare grid 금지**: 모든 grid 래퍼 `min-w-0`(토지조서 오버플로우 82곳 교훈).
- **지도/3D 견고성**: MapShell(ErrorBoundary+Suspense) 격리, 3D는 게이트+성능가드(frameloop=demand·no-autoRotate·HDR 금지, b5f216e 회귀방지).
- **근거 기본노출·점진적 공개**: 모든 수치 '근거보기'(verified만). 주소 입력 즉시 Tier1 자동채움(Once-and-Done).

---

## 7. 단계 로드맵 (전부 additive·전용 라우트 무손상·멀티세션 claim 필수)

| 단계 | 목표 | 핵심 작업 | 노력 | 위험 |
|---|---|---|---|---|
| **P0** 발견성·Go/NoGo 히어로 | 단일창을 진입 디폴트로, 최상위 차별자 즉시 노출 | canvas 라우트 nav 등록 · 히어로 DecisionBriefPanel 마운트 · AiInsightCard 데이터원 `/zoning/analyze`→comprehensive 교체 | S | 낮음(자급식 마운트) |
| **P1** comprehensive 단일 데이터원 + 컴팩트화 | 주소 1콜로 전 탭 자동채움·FULL카드 제거 | comprehensive 1콜→탭 분배 · 카드 `compact` prop · 원장→SSOT 복원 공유 | M | 중(공유카드 다소비처 회귀) |
| **P2** 경량 인-패널 + 중량 CTA 정비 | 경량은 탭 흡수, 중량 6대는 Tier2 전용창 CTA로 명확화 | 경량(legal/esg 요약) 인-패널 · 8탭 DrillCta를 '요약+전문창 CTA'로 정리 · 시니어자문 탭 신설 | L | 중(SSOT projectId 바인딩) |
| **P3** 통합 지도 패리티 | 배타 mode→다레이어 동시 토글·총액평당·**우측 본맵 클릭선택** | KakaoMapControls 동시토글 · onParcelClick 캔버스 배선(Leaflet picker 제거) · 지형도/법정동경계 오버레이 | M | 중(지도 엔진 단일화·다필지 동기) |
| **P4** 3D·로드뷰·시계열 차트 | jootek 소비자 패리티 마감 | ProposalMassPreview 경량 임베드(게이트) · **KAKAO 실 JS키**→로드뷰/지적편집도 · 가격 시계열 차트 + 토지탭 소유자지분/말소기준 | M | 중(WebGL·실키 인프라) |
| **P5** 추천·학군 오버레이·정본 정리 | jootek 추천/학군 패리티 + 중복 정본화 | 추천 건축모델(design retrieval)·전문가(senior) surface · 학군 green마커(Kakao Local POI) · 3중 중복 정본=canvas, /analysis·site-analysis는 딥링크로 정리 | M | 중(데이터소스·동선 안내) |

**권장 착수 = P0**(노력 S·위험 낮음·자급식 마운트만 — 즉시 가시성과: 진입 디폴트 + Go/NoGo + comprehensive 연결).

---

## 8. 측정지표
- page-hopping 라우트 이동 ~10(또는 24) → **1**(단일창 탭전환·전문창 CTA).
- 주소입력→첫 결론(Go/NoGo) 클릭수/시간 단축.
- Tier1 단일창 완결률(전문창 이동 없이 요약으로 끝낸 비율).
- comprehensive 1콜 커버리지(자동채움 탭 수, 목표 5+).
- 지도 레이어 동시 토글 수(jootek 패리티 충족 개수).
- 차별자 surface 가시성(Go/NoGo·심의·senior·Top3·은행보고서·다필지·GRESB 직접 노출 개수).
- **회귀 0**: 전용 라우트 24개 무손상(딥링크)·공유카드 빌드/타입/eslint PASS.

---

## 9. 리스크 / 멀티세션 주의
- **핫스팟 동시편집**: nav-config·layout·canvas·KakaoMapControls·comprehensive는 다세션 핫스팟 → 편집 전 `scripts/coord.sh claim`·전용 워크트리·커밋 전 branch 확인.
- **공유카드 회귀**: `compact` prop 기본값 보수적·소비처 스윕·빌드 검증.
- **WebGL 진입멈춤 재발**: 3D는 반드시 '열기' 게이트+성능가드(b5f216e).
- **KAKAO 더미키**: 로드뷰/지적편집도 라이브는 P4 실키 발급(인프라·코드 외 선결).
- **과적재 가독성**: 단일창에 다 박으면 site-analysis 메가페이지 안티패턴 재현 → **컴팩트+드릴다운 위계 엄수, 중량은 Tier2 전용 창**(본 계획 코어).
- **정본 전환 혼란**: 중복 3surface canvas 정본화 시 기존 동선 안내(딥링크 유지·리다이렉트 신중).
- **additive 원칙**: 기존 라우트·컴포넌트 무손상, 신규는 자급식(SSOT 소비). 삭제/재구현 금지.

---

## 10. 다음 액션
- **P0 착수 제안**(S·저위험): ① canvas 사이드바/진행률 nav 등록 ② 히어로 DecisionBriefPanel ③ AiInsightCard→comprehensive 데이터원 교체. origin/main 기반 전용 워크트리·claim 후 additive 구현·완결게이트(tsc/eslint)·적대리뷰.
- 결정 필요(선택): Tier1 좌측 탭 최종 구성 / 첫 방문 자동분석 범위(무료·경량) vs 온디맨드(과금) 경계.

---

## 11. ★슬림 사이트맵 + 스토리라인 (전역 IA 최적화 — 보강)

### 11-1. 현행 IA 비대(슬림화 대상)
- 프로젝트 내부 ~24 서브라우트 평면 노출(ProgressRail 11 + ToolIndex 8 + extraRoutes 3) + 전역 분석 라우트 분산(/analysis·/precheck·/market-insights·/permits·/regulations·/analytics/cost·/analytics/investment·/land-schedule·/registry-analysis·/desk-appraisal) → **진입점이 30+ 평면 나열**, 어디가 정본인지 불명.

### 11-2. 슬림 사이트맵 (3계층 · 진입점 30+ → 4블록)
```
[홈/대시보드]  프로젝트 목록 · 주소검색(신규 진입)
   │
   ▼
[Tier 1 · 통합 단일창]  /projects/[id]/canvas   ★진입 디폴트·정본 (1개)
   ├ 상단 히어로: Go/NoGo · 주소 · 진행률
   ├ 좌 맥락 탭: 토지 / 규제 / 입지·학군 / 개발방식·Top3 / 설계·일조 / 수지·금융 / 시니어자문 / 통합·보고서
   └ 우 통합 지도(레이어 토글): 경계·실거래·경매·분양·3D·로드뷰 / 항공·지적·지형·노후도 / 법정동·개발지구·건축가능·학군·POI
   │
   └─ 각 항목 "전문 분석/관리 열기 →"
        ▼
[Tier 2 · 전문 심화 전용 창]  (CTA 진입 · 그룹 메뉴)
   ├ 설계·시뮬: 상세분석 · 시뮬레이션 · 설계 스튜디오(CAD) · BIM 3D
   ├ 사업성: 상세 적산(QTO/BOQ) · 상세 수지(수지/금융)
   ├ 자산·권리 관리: 토지조서 · 등기부 관리 · 권리분석 · 시세추정(AVM)
   ├ 산출물: 은행제출 보고서 · AI 오케스트레이션
   └ 후방 운영: 시공 · 감리 · 드론 · 협업 · 분양관리(ERP)

[전역 모니터링]  (프로젝트 무관)
   ├ 시장 인텔리전스
   └ 경매·분양 모니터링 ──(데이터)──▶ Tier1 지도 경매/분양 레이어로 환류
```

### 11-3. 사이드바 슬림 (평면 30+ → 4블록)
1. **대시보드**(프로젝트·주소검색)
2. **통합 단일창**(Tier1 — 진입 디폴트)
3. **전문 도구**(Tier2 — 그룹 접이식: 설계·시뮬 / 사업성 / 자산·권리관리 / 산출물 / 운영)
4. **전역 모니터링**(시장·경매·분양)
- 프로젝트 내부 ProgressRail(11단계)은 **Tier1 상단 진행률로 흡수**, ToolIndex/ExtensionModulesGrid(고아 링크 카드)는 **제거**(Tier2 그룹 메뉴로 대체).

### 11-4. 정본화(중복 제거)
- 분석 정본 = **Tier1 단일창 1개**. `/analysis`(독립 종합패널)·`site-analysis`(메가페이지)는 Tier1으로 흡수 또는 **딥링크 진입점**으로 강등(무손상·리다이렉트 신중).
- 토지 관련 관리(토지조서·등기·권리·AVM)는 **Tier2 자산·권리관리 그룹**으로 묶어 토지 탭 CTA 단일 진입.

### 11-5. 스토리라인 (슬림)
```
주소 1회 입력
  → Tier1 요약(전 항목 자동 요약 · 지도 토글로 경매/분양/실거래/규제 등 원하는 것만)
  → "전문 분석/관리 열기 →"
  → Tier2 전용 창(설계·BIM·적산·수지·토지조서·등기·권리·보고서)
```
원칙: **한 부지 = 한 진입(Tier1)**, 심화·관리는 CTA 1클릭. 접근성(진입동선 단순)·가독성(컴팩트+위계)·편의성(이동 0·토글 탐색) 극대화.

### 11-6. 로드맵 반영(보강 항목)
- **P3(통합 지도)**: 레이어 토글 셋에 **경매(온비드)·분양(청약/매물)** 추가(기존 데이터 재사용). 항목별 다중 on/off.
- **P2/P5(관리 연동)**: 토지 탭 요약 → **토지조서·등기부·권리분석·AVM 전용 관리 페이지** CTA 배선(별도 페이지 유지).
- **P0/P5(사이트맵 슬림)**: 사이드바 4블록 재편 + ProgressRail 흡수 + ToolIndex/ExtensionModulesGrid 제거 + 중복 3surface 정본화.

---

## 12. ★P3.5 워크스트림 — 3D 매스 데이터 백본 (②③⑤ 상세 구현계획)

> 관점: jootek 3D는 건축물대장 기반 **고립 박스**. 우리 매스는 설계→BIM→적산→수지→일조→ESG→심의로 흐르는 **데이터 백본**. 빌딩블록은 보유(분산) → 백본 배선 + 맥락·법규 그라운딩 + 학습 축적이 "확대활용". 착수=가시성·차별·자산보유 높은 ②③⑤.
> 공용 SSOT: 신규 `MassEnvelope` 계약 = {footprint(폴리곤), max_floors, max_height_m, setback_steps[], far_pct, bcr_pct, max_gfa_sqm, max_footprint_sqm, basis(근거/법령)}. 한 번 산출→지도·3D·설계·적산이 공유.

### 12-② 법적 건축가능 볼륨(buildable envelope) 3D ★1순위
- 목표: `capacity_envelope`(far/bcr) + 정북일조 단계후퇴 + 도로사선을 **반투명 3D 볼륨**으로, 제안 매스를 그 안에 → "얼마나 더" 한눈.
- 백엔드(재사용+소량신규): 심의엔진 `capacity_envelope`(max_gfa/footprint·근거) + `solar_placement_service`(정북 단계후퇴 step·orientation) → 신규 엔드포인트 `POST /site-score/buildable-envelope`가 `MassEnvelope` 반환(footprint=구획도 폴리곤 from parcel-boundaries, max_floors=max_gfa/footprint, setback_steps=정북 단계). 수치 결정론·근거 동반.
- 프론트(재사용): `ProposalMassPreview`/`ProceduralBuilding`(Three.js·frameloop=demand·게이트) 확장 — envelope 반투명 mesh + 제안 매스 solid를 겹쳐 렌더. Tier1 지도 토글 '건축가능 볼륨' + 설계·일조 탭 미리보기.
- 데이터흐름: parcel-boundaries(footprint) + capacity(far/bcr) + solar(단계후퇴) → MassEnvelope → 3D. 단계: BE 엔드포인트 → MassEnvelope 계약 → 프론트 mesh.

### 12-③ 맥락 일조·경관·조망 ★jootek 대비 최대 우위
- 목표: **실측 주변 건물** + 제안 매스로 동지 일조시간·돌출/조화/매몰·조망·일조침해 양방향.
- 백엔드(재사용): `environment_service._compute_skyline`(주변 평균/최고 vs 대상→돌출/조화/매몰) + `collect_surrounding`(VWORLD lt_c_bldginfo 주변 footprint/높이) + `solar_placement` sun_position(천문식 동지). 신규: 주변 footprint+높이 + 태양고도/방위 → **그림자 폴리곤/면별 일조시간**. 엔드포인트 `POST /site-score/contextual-solar`.
- 프론트(재사용): ProceduralBuilding 씬에 주변 건물 매스 + 제안 매스 + 그림자(동지 정오/시간대 슬라이더). Tier1 지도 '일조·그림자' 토글.
- 단계: collect_surrounding 배선 확인 → 그림자 산식(BE) → 3D 씬 주변+그림자. (한계 정직: v1 직사각형 근사·3D 음영 후속 BIM.)

### 12-⑤ 유사건축물 retrieval 추천 (근거기반 — jootek 카탈로그 초월)
- 목표: 부지 envelope·용도지역에 맞는 실제 건물 매스/평면/**사업성**을 검색 → "이 부지엔 이 매스 적합(유사 N건·평균 수익률)".
- 백엔드(재사용): `design_ingest`(search_service·vector_store·design_geometry) — 쿼리=zone/면적/far·envelope → 유사 design_drawings top-k + 사업성 메타. 엔드포인트 `POST /design/recommend-models`(없으면 search_service 래핑).
- 프론트(신규 경량): 설계·일조 / 개발방식 탭에 '추천 건축모델' 썸네일 카드(매스 미리보기 + envelope-fit 점수 + 유사사례 사업성). Tier2 설계 스튜디오로 "이 모델로 설계 시작" 연계.
- 단계: search_service 쿼리 계약 확인 → recommend 엔드포인트 → 추천 카드. ★자가학습: 생성 매스+결과를 design_ingest 적재(성장 뇌 폐루프)는 후속.

### 12-기타(후속): ① 현황↔제안 delta · ④ 매스→BIM→적산→수지 5D 백본 · ⑥ 에너지·ESG(외피) · ⑦ 다필지 통합매스 · ⑧ 자가학습 축적.

### 로드맵 위치
**P3.5**(P3 통합지도 직후): ②(envelope 3D)→③(맥락 일조)→⑤(추천). 노력 M·M·M, 위험 중(3D 성능가드 b5f216e·BE 신규 엔드포인트·데이터소스). 전부 additive·MapShell/성능가드 준수.
- ★구현 진척: **②는 구현·커밋(d7660780)** — `BuildableMassPreview`(검증된 ProposalMassPreview 재사용·SSOT far/bcr/면적 파생·`floor(far/bcr)` 법정한도 보장·보기 게이트·근사 정직). ③⑤는 3D 시각 라이브검증/신규 BE 엔드포인트 필요로 후속.

### 12-Data ★건축물종류별 매스 레퍼런스 DB (사장님 제안 — 매스 백본 데이터 자산화)
> ②의 procedural 근사(far/bcr 박스)를 **실측 기반 종류별 실 템플릿**으로 승격하고 ⑤(유사 추천)·설계자동생성을 그라운딩하는 **데이터 레이어**. "토지이음 건축물종류별·신도시 위주 DB화" 아이디어를 정식화.
> ★소스 정정: 토지이음(eum/LURIS)=토지이용·지구단위 지침·규제(매스 직접 제공 X). 실 매스=**건축물대장(건축HUB API·보유)**. 정확한 조합 = **토지이음 지구단위 지침(근거·높이/용도/배치) + 건축물대장 실측(건폐/층수/GFA) + design_ingest 도면(형태), 신도시 위주.**
- **왜 신도시**: 지구단위 지침 명확·일관·구조화 쉬움(구도심 난개발 대비)·신축 대장 품질↑ → 종류별 표준 매스 추출 깨끗·추천/생성 신뢰도↑.
- **DB 스키마(신규)**: `mass_templates`(키: 신도시/법정동·용도지역/지구단위·**건축물종류** → 표준 건폐/층수/GFA·배치타입·footprint패턴·façade refs·**provenance**[대장 N건·지구단위 고시]). 무목업·출처 표기·신선도 검증.
- **단계 P3.5-Data**: **D0** 스키마·신도시 타깃 확정(3기신도시·세종·동탄·위례 등) → **D1**(1차·빠른가치) 건축HUB 대장 신도시 법정동별 대량 수집→종류별 통계 집계(API 보유·구조화 쉬움) → **D2** ⑤ 추천 배선(부지 envelope/용도/종류 → DB 매칭 "유사 N건·평균") → **D3** auto-design/IfcGenerator 종류별 표준 매스 시드 주입(절차생성 품질↑). 지구단위 지침 파싱(PDF/고시)은 비용커 **2차**.
- **연결/재사용**: design_ingest(vector_store·design_geometry — 다른 세션 소유·조율)·건축HUB(보유)·토지이음(보유)·② 폴백(DB 미가용 시 graceful 유지·채워지면 실 템플릿 승격).
- **현실체크**: 데이터 엔지니어링(백엔드 배치+DB+Qdrant 인프라 deploy-pending)·멀티세션 조율 필요 → 프론트 빠른증분(P0~P2) 아님. 1차=대장 집계로 가치, 지구단위 지침은 후속.
