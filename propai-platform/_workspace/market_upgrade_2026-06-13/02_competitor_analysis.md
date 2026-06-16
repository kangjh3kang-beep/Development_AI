# 시장·인구·소득 분석 기능 관점 — 국내외 프롭테크 플랫폼 비교분석

> 목적: PropAI 부동산개발 플랫폼의 "시장·인구·소득 분석" 기능 고도화를 위한 경쟁/벤치마크 조사
> 조사 기준일: 2026-06-13 · 수집 기간: 2024~2026 공개자료 · 원칙: 추측 금지, 확인된 사실만, 출처 URL 명기
> 조사 대상: 국내 8개(디스코·밸류맵·랜드북·랜드업·크레마오·부동산플래닛·호갱노노·직방/다방), 해외 9개(ARGUS·TestFit·Deepblocks·CoStar·Cherre·Reonomy·HouseCanary·Local Logic·PlaceILive)

---

## 0. 핵심 요약 (Executive Summary)

- **원클릭 사업성 워크플로우(주소→규모→분양가→ROI)**의 대표주자는 국내 **랜드북(스페이스워크)** / **랜드업** / **밸류맵+텐일레븐**, 해외 **TestFit**(생성형 설계) / **Deepblocks**(용도지역+사업성+인구 통합). 다만 "건축규모+적정분양가+ROI"를 한 화면에서 끝까지 자동으로 잇는 곳은 국내가 더 앞서 있고, 해외(TestFit)는 규모·yield 중심이며 분양가/시장수요는 외부 데이터에 의존한다.
- **인구이동(전입·전출)·소득 데이터를 사업성/마케팅에 직접 결합**하는 플랫폼은 의외로 드물다. 대부분의 사업성 툴(TestFit·ARGUS·밸류맵·랜드북)은 **공급측(무엇을 지을 수 있나)만** 다루고, 수요측(누가 살 것인가)은 사용자가 외부에서 가져온다. → **PropAI의 최대 차별화 공백.**
- **소득·지불여력(PIR/DSR/affordability)으로 분양가 밴드를 산출**하는 자동화 사례는 국내에서 공개 확인되지 않음(KB PIR·HF HAI는 지표 제공까지). 해외 HouseCanary가 ZIP 단위 affordability 예측을 제공하나 분양가 밴드 자동산출은 아님. → **PropAI가 선점 가능한 빈 공간.**
- **선택형(모듈러) 크레딧 과금 UX**는 국내 공개 사례가 거의 없고, 해외는 BatchData(API pay-as-you-go), HouseCanary(리포트 건수 티어), Deepblocks(딜 건수 티어)가 근접. PropAI는 이미 LLM 토큰 계측·과금 인프라를 보유 → 모듈 선택형 크레딧 UX로 차별화 여지 큼.

---

## 1. 종합 비교표 (플랫폼 × 6항목)

### 1-A. 국내 플랫폼

| 플랫폼 | 1) 핵심기능·타깃 | 2) 데이터소스·해상도 | 3) 사업성 자동산출 | 4) 인구이동·수요·페르소나 | 5) UX·시각화·차별점 | 6) 과금모델 |
|---|---|---|---|---|---|---|
| **디스코** | 비주거(토지·빌딩·상가·공장) 실거래·등기·매물 / 투자자·중개사·시행사 | 국토부 실거래 ~3,000만건, 토지·건물 ~4,000만 필지, 등기·경매·공시지가 / 필지 단위. 인구·소득 미노출 | "AI 기획설계" 메뉴 존재(세부 비공개), 인근 실거래 기반 예상가 / 규모→ROI 자동산출 **확인불가** | **확인불가**(상권 일부) | 지도클릭→필지→실거래/등기 패널, 로드뷰·위성 | 정보조회 무료, 등기열람 건당, 멤버십(가격 비공개) |
| **밸류맵** | 비주거 실거래+AI건축설계+AVM+사업성 컨설팅 / 토지·건물 거래자, 소규모 건축사업자, 시행사 | 국토부 실거래(비주거 전유형), 자체 3세대 AVM, 대장 / 필지 단위. 인구·소득 미노출 | **있음** — 텐일레븐 공동 AI건축설계(6유형, 합필 최대 3,300㎡, 설계조건 직접/AI추천, 최대 10안, 3D·CAD). B2B 사업성 컨설팅 별도 | **확인불가** | 지도→필지→AVM→AI설계 의뢰→10안 3D→CAD. "30분 규모검토" | AI설계 **1회 5만원**(출시기준)+멤버십(가격 비공개) |
| **랜드북**(스페이스워크) | 소형 신축개발 특화 AI 원스톱(토지탐색→AI설계→사업성). LBDeveloper=도시정비 B2B / 소규모 건축주·시행사·공공기관(LH·SH) | 실거래·대장·인허가·건축법규·도시계획공고·분양/임대시세 / 심층강화학습. 인구·소득 미확인 | **있음(핵심)** — 주소→법규자동적용→심층강화학습 설계안→AVM+건축비+인근시세→예상수익·수익률→원클릭 리포트. 매개변수(매입비·건축비) 조정 재계산 | 임대시세 간접평가만, **전용 분석 확인불가** | 필지클릭→법규+설계 즉시→3D→수치→리포트. "30분 사업성검토" | 개인 일부무료+구독화 진행. LBDeveloper 연 2,000만(500만이하 도시)~5,000만(수도권)~1억(전국) |
| **랜드업** | "주소→사업성 보고서 즉시생성" 자동화 / 시행사·시공사·PF금융·중개·개인 | 국가공간정보·실거래 등 30개+ 항목 자동수집 / 인구·소득 미포함 | **있음** — 주소→13~15p 보고서(사업개요·사업지·시공·사업환경·**적정분양가(통계기법)+사업수지**). PDF | **확인불가** | 주소 1회→자동보고서→PDF. "수십 필지 입력→상위 3~4개 추림" | B2B SaaS(가격 비공개). '24.7 출시, TIPS 선정 |
| **크레마오** | 상업용 개발 사업성 자동화+AI 적정분양가 / 상업용 개발사·시행사 | 자체 HXD(인간행동 데이터)·실거래·상권 / 상세 비공개 | **있음** — 거래사례비교법+**수익환원법** 병행, AI 부지 스크리닝, 타당성 보고서 자동, 수지+대화형 AI봇, Excel | HXD로 상권·유동인구 가능성, **명시 확인불가** | 지도 AI필터→부지→보고서→Excel/모바일 | 가입시 20회 무료 후 유료(추정), 가격 비공개 |
| **부동산플래닛** | 전유형 실거래+AI추정가+상권+학군 / 개인 투자자·중개사·비즈니스 | 국토부 실거래(일일), 공시지가, 대장, 상권, 학군, 자체 AVM(2024.4) / 필지·반경. 인구·소득 미확인 | 부분 — "영역그리기" 재개발·재건축 요건 자동분석, 건물탐색 필터, 마켓리포트. **규모→수지 자동산출 확인불가** | **확인불가**(상권만) | 지도→필터→필지→실거래/AI가, 공시지가 히트맵, 영역그리기 | 멤버십 3종(탐색플러스·임장플러스·자산관리비즈), 가격 비공개 |
| **호갱노노** | 아파트 실거래 특화(직방 그룹) / 아파트 매수·전세·분양 수요자 | 국토부 아파트 실거래(최다), **인구이동(전입·전출, 행안부 추정)**, 분양/입주물량, 학군, 3D일조, 상권 / 단지 단위 | **없음**(가격분석 특화, 개발 사업성 미제공) | **인구이동 일부** — 단지별 전입·전출 현황 표시. 분양 수요예측은 공급·거래·가격 복합지표. 페르소나·소득 확인불가 | 지도→단지→실거래/인구이동/학군/일조 탭, 인기랭킹 | 기본 무료, 일부 기능(안심알리미 등) 유료 |
| **직방/다방** | 매물 중개+직방RED(B2B 데이터) / 임차인·매수자 + (RED)건설·금융 | (RED) 공공데이터+직방 이용자 거래·행동 데이터, 분양/입주, **타깃 소비자 인구통계 특성** / 미상세. 소득·이동 확인불가 | **없음** | (RED) **이용자 인구통계 기반** 타깃 소비자층 분석(건설·금융 활용). 전용 이동·소득 확인불가 | RED=Tableau 임베드 대시보드, B2B | 일반=광고료, RED=B2B 계약(가격 비공개, 베타) |

### 1-B. 해외 플랫폼

| 플랫폼 | 1) 핵심기능·타깃 | 2) 데이터소스·해상도 | 3) 사업성 자동산출 | 4) 인구이동·수요·페르소나 | 5) UX·시각화·차별점 | 6) 과금모델 |
|---|---|---|---|---|---|---|
| **ARGUS Enterprise**(Altus) | CRE 현금흐름·밸류에이션 표준엔진(→ARGUS Intelligence 통합) / 투자자·자산운용·감정평가·대주 | 사용자 입력(임대료·OpEx/CapEx)+SFTP/S3 연동, 익명 포트폴리오 벤치마크 / 자산 단위. 공공 실거래·인구 미수집 | 수익형 자산 한정 — DCF·Cap·IRR/NPV. **개발 프로포마(FAR→규모→공사비→개발이익)는 미지원** | **없음**(임대성장·공실 수기입력) | 모델구축→플랫폼 업로드→대시보드·시나리오·벤치마크→리포트(40+) | Contact sales(연 $5K~$30K/seat 추정) |
| **TestFit** | 생성형 부지 사업성(필지→수천 매싱 3초 생성·KPI순위) / 개발사·건축가·시공사 | 필지지오메트리+**zoning 내장(2024)**·ESRI위성·지형(cut/fill)·토양·전력 / 필지 단위. 실거래·인구 미수집 | **있음(핵심, 공급측)** — 필지→파라미터→~3,000안/3초→KPI순위. Pro Forma 애드온(+$2,000/yr): 유닛×단가=매출, 물량×단가=공사비→**Yield on Cost**. IRR/NPV는 Excel 임포트 | **없음**(수요·인구·이동 전무, 외부 의존) | 필지→파라미터→생성(3초)→필터/순위→정제→프로포마→Export(DXF·Revit 등). 3D·2D·유닛표 | Site Solver $10,000+/yr, Portfolio $15,000+/yr, Site Intel +$1,800, Pro Forma +$2,000 |
| **Deepblocks** | AI 용도지역+사업성+딜소싱+ChatDB / 개발사·투자자·인수담당 | 자체 zoning DB(미국 최대 주장)·필지·리스팅·**인구/경제(센서스트랙트·ZIP·동네)** / 트랙트~도시. 이동·유닛별 수요 미확인 | **있음(통합)** — 기준설정→파셀 스캔·zoning로직→개발용량→3D매싱+프로포마(수입·비용·공사비)+PDF. Algorithms는 사전분석 딜 자동배달 | **부분(ChatDB)** — 자연어로 인구·경제 데이터 질의(트랙트/ZIP/동네). 인구추이·구성·소득 탐색. 전용 catchment·이동모델은 미확인 | 기준→AI스캔→딜스터디 메일(리스팅+스터디+PDF+프로포마)→Developer 조정→ChatDB 질의 | Developer $99/mo, Deal Finder $499, Pipeline $1,499, Daily Flow $5,999/mo |
| **CoStar** | 최대 CRE 데이터·애널리틱스 / 브로커·투자자·자산운용·감정·대주·개발사(시장조사) | 리서처 검증 임대·매매 comp, 가용리스팅, 소유, **서브마켓 인구·경제(3,000+ 서브마켓)**, 공급 파이프라인 / 서브마켓. 이동 전용·foot-traffic 미보유 | **없음**(사업성 툴 아님) — 시장임대·공실·토지 comp로 프로포마 가정 지원만 | **부분** — Market Analytics가 인구·고용 예측 제공. 2025 국내이동 흐름을 멀티패밀리 수요동인으로 추적(전용 이동시각화·catchment 모델링은 아님) | 주소/서브마켓/반경 검색→comp→리포트→연동. 지도·히트맵·추세차트 | Contact sales(연 $3K~$23K+) |
| **Cherre** | RE 데이터 통합·커넥티비티(분석 인프라층)+Agent.STUDIO(2025) / 기관 자산·투자운용·REIT·대주 | 50+ 소스 엔티티 해소(CoStar·Yardi·Trepp·MSCI/RCA·세무·등기), 로드맵: 위성·**모바일 위치** / 자산 그래프 | **없음**(통합층, 다운스트림이 계산) | **로드맵('25~26)** — 모바일 위치데이터 편입 예정(현재 라이브 아님) | 소스연결→정규화·중복제거·엔티티해소→대시보드/API/BI→Agent.STUDIO NL질의 | Contact sales(기관 전용, 누적펀딩 $427M) |
| **Reonomy**(Altus) | CRE 물건 인텔리전스·딜 프로스펙팅(LLC 관통→실소유 연락처) / 브로커·투자자·인수담당 | 세무·신용·등기·모기지 / 5,000만+ 물건, 주간 갱신, 미국만. 인구·이동 미보유 | **없음** | **없음**(소유·프로스펙팅 특화) | 필터검색→예측 매도점수→연락처 export→CRM 연동. 지도 검색 | **$4,800/yr/user**($400/mo), 7일 무료. (콘텐츠 2021 이후 정체, 소형시장 정확도 한계) |
| **HouseCanary** | 주거 AVM·예측 데이터(1.36억 물건)+CanaryAI / 대주·서비서·기관 주거투자자·iBuyer | 물건특성·매매이력·리엔, 블록/블록그룹, **ZIP HPI·affordability·수급·Market Action Score**, MSA/주 예측 / 블록~주. foot-traffic 미보유 | **없음**(주거 밸류·애널리틱스) — 분양 프로포마에 ㎡당 comp·HPI 예측 input 제공 | **제한적** — ZIP affordability/HPI 예측이 수요 타깃 근접. 이동추이는 리포트 논평 수준(셀프서비스 이동·catchment 툴 아님) | 주소/포트폴리오 입력→AVM·밸류리포트→Data Explorer(75+)→CanaryAI→모니터링 | Basic $190/yr(2리포트/mo), Pro $790(15), Teams $1,990(40), API $0.30~$6.00/call |
| **Local Logic** | 위치 인텔리전스(동네 점수·인구·POI)·API/위젯 / 브로커리지·MLS·포털·프롭테크·대주 (B2B 데이터) | 인프라·토지이용·zoning, POI(28종), **센서스 인구·소득·가구**, 학군, 기후 / 블록~메트로(미·캐). 원시 GPS 아닌 인프라 추론 | **없음**(위치 컨텍스트 데이터) | **부분** — 블록~동네 인구·소득(정적)+walkability·transit 점수=수요동인 프록시. 전용 이동흐름·소득티어 타깃은 미확인. NeighborhoodMatch/Intel(2024) | 위젯/API 임베드→리스팅 옆 동네점수→Lifestyle Search→Neighborhood Report | Local SDK $250/mo+, Neighborhood SDK $500+, API $1,500+, Agent Reports $20/mo |
| **PlaceILive** | 소비자용 동네 비교(LQI 0~100) / 거주지 탐색 개인 | 센서스·NYPD·MTA·Foursquare·Socrata·Breezometer / 주소 단위 점수, 블록 인구 | **없음** | **없음**(정적 센서스 스냅샷) | 주소→LQI 7개 카테고리→동네 비교→지도 오버레이 | 무료(오픈데이터). **단, 2014~15 이후 갱신 정체, 2024~26 업데이트 미확인** |

---

## 2. 플랫폼별 상세

### 2-1. 국내

#### 디스코 (Disco) — disco.re
- 비주거(토지·빌딩·상가·공장) 실거래·등기·매물 통합. 2024.1 손익분기 달성, 월 50만 활성·누적 400만. 전문가(중개사) 1.8만+.
- 데이터: 실거래 ~3,000만건(RTMS), 토지·건물 ~4,000만 필지, 등기·경매·공시지가. 인구·소득·이동 미노출.
- "AI 기획설계" 메뉴는 존재하나 로그인 필요로 세부(규모→ROI 자동산출) **확인불가**.
- 과금: 정보조회 무료, 등기열람 건당 유료, 멤버십(가격 비공개).
- 출처: https://disco.re/ · http://www.kglobaltimes.com/news/articleView.html?idxno=26908 · https://www.venturesquare.net/969254 · https://disco.re/b/f3thqybw/

#### 밸류맵 (ValueMap) — valueupmap.com
- 비주거 실거래+AI건축설계+AVM+사업성 컨설팅. 월 100만 방문, 토지·건물 부문 점유율 1위 자칭.
- AI 건축설계(텐일레븐 공동, 2022 출시): 6유형, 합필 최대 3,300㎡, 설계조건 직접설정+AI 자동추천(국내 유일 주장), 현행 건폐율·용적률·주차 자동계산, 최대 10안 동시, 3D·층별 평면, CAD 다운로드. "30분 규모검토".
- 데이터: 국토부 실거래(비주거 전유형), 자체 3세대 AVM(토지형상·연접토지·연접도로 인식+가격생성/판별 이중검증), 대장. 인구·소득 미노출.
- 과금: AI설계 1회 5만원(출시기준), 실거래 일부 무료, B2B 컨설팅(solution.valueupmap.com) 별도.
- 출처: https://www.valueupmap.com/ · https://www.hankyung.com/realestate/article/202209135806i · https://www.sedaily.com/NewsView/269WR2ODMG · https://www.valueupmap.com/tech · https://solution.valueupmap.com/

#### 랜드북 (Landbook) — landbook.net / spacewalk.tech ★원클릭 워크플로우 대표
- 소형 신축개발 특화 AI 원스톱. LBDeveloper=도시정비(가로주택·소규모 재건축) B2B. LH·SH·경기도시공사 실사용.
- **원클릭 워크플로우 상세**:
  1. 지도 필지 클릭/주소 검색 → 대상 토지 선택
  2. 법규 자동분석: 용도지역·건폐율·용적률·높이제한·지자체 조례 (심층강화학습)
  3. AI 설계안 생성: "수십만 가지 설계 대안 분석→최적안"
  4. 사업성 산출: 토지 추정가(AVM)+건축비+인근 분양·임대시세 → 예상수익·수익률
  5. 매개변수 조정(매입비·건축비) → 시나리오 재계산
  6. 원클릭 리포트(대장·사업수지·서류 패키지)
- LBDeveloper 추가: 세대유형·주택비율 입력→조례충족 최적설계, 종전자산 추정+근거 실거래, 세대별 추정 분담금, 정비사업 가능여부 판별.
- 데이터: 실거래·대장·인허가·건축법규·도시계획변경공고·분양/임대시세 (심층강화학습). 인구·소득 미확인.
- 과금: 개인 일부 무료+구독화 진행. LBDeveloper 연 2,000만(인구 500만 이하 도시)/5,000만(서울·경기)/1억(전국), VAT 별도.
- 출처: https://spacewalk.tech/19 · https://www.landbook.net/ · https://www.landbook.net/service/ai-analytics · https://info-lbdeveloper.landbook.net/ · https://m.dnews.co.kr/m_home/view.jsp?idxno=202503102255455410537 · (KCI) https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART002582270

#### 랜드업 (Landup) — lan-dup.com
- 삼성물산 출신 창업(엘엔디씨). "주소→사업성 보고서 즉시생성". 시행사·시공사·PF금융·중개·개인. '24.7 출시, 1개월 3,000명/3개월 1만명, '24.10 인포뱅크 투자, '24.11 TIPS.
- 주소 입력 → 13~15p 보고서 자동생성: 사업개요(유형별)·사업지 분석·시공 분석·사업환경 분석·**적정분양가(통계기법)+사업수지(매출·사업비)**. 커스터마이즈·PDF. '24.12 지구단위계획 구역별 분석 추가 예정.
- 데이터: 국가공간정보·실거래 등 30개+ 항목 자동수집. 인구·소득 미포함.
- 과금: B2B SaaS(가격 비공개).
- 출처: https://zdnet.co.kr/view/?no=20240704105140 · https://www.unicornfactory.co.kr/article/2024112516360614326 · https://www.venturesquare.net/972016

#### 크레마오 (Cremao) — oasisbusiness.co.kr
- 상업용 개발 사업성 자동화+AI 적정분양가(오아시스비즈니스).
- **거래사례비교법+수익환원법 병행**(업계 비교법 단독 대비 차별), AI 부지 스크리닝, 타당성 보고서 자동, 수지+대화형 AI봇(2023.6), Excel·모바일.
- 데이터: 자체 HXD(인간행동 데이터)·실거래·상권(비정형 포함). 상세 비공개.
- 과금: 가입시 타당성 보고서 20회 무료(프로모션) 후 유료 추정.
- 출처: https://oasisbusiness.co.kr/home/?bmode=view&idx=14148927 · https://www.startupn.kr/news/articleView.html?idxno=32263

#### 부동산플래닛 (BDS Planet) — bdsplanet.com
- 전유형 실거래+AI추정가+상권+학군. 개인·중개사·비즈니스.
- "영역그리기" 재개발·재건축 요건 자동분석, 건물탐색 필터, 마켓리포트(탐색플러스 무제한). AI추정가 2024.4 출시. 규모→수지 자동산출은 확인불가.
- 데이터: 국토부 실거래(일일), 공시지가, 대장, 상권(500m+), 학군, 자체 AVM. 인구·소득 미확인.
- 과금: 멤버십 3종(탐색플러스·임장플러스·자산관리비즈), 가격 비공개.
- 출처: https://www.bdsplanet.com/ · https://www.bdsplanet.com/premium/productServiceDetail.ytp?cc=PREMIUM_PRODUCT01 · https://news.nate.com/view/20240418n04679

#### 호갱노노 (HoGaengNoNo) — hogangnono.com (직방 그룹) ★인구이동 관점
- 아파트 실거래 특화. 2018 직방 인수. 개발사업자 기능 없음.
- **인구이동 기능**: 단지별 전입·전출 현황 표시(아파트 단지별 인구 유출입). 행안부 주민등록 이동 통계 추정. 분양 수요예측은 공급량·거래량·가격변동 복합지표. 페르소나·소득 분석 확인불가.
- 데이터: 국토부 아파트 실거래(최다), 인구이동, 분양/입주, 학군(특목고 진학률), 3D 일조, 상권.
- 과금: 기본 무료, 일부(안심알리미·중개라이브) 유료 추정.
- 출처: https://hogangnono.com/ · https://www.sedaily.com/article/11875708

#### 직방 (Zigbang) / 다방 — 데이터 관점
- 매물 중개 중심. **직방 RED**가 B2B 데이터 수익화(Tableau 임베드): 공공데이터+직방 이용자 거래·행동 데이터 통합, 분양/입주, **타깃 소비자 인구통계 특성**(앱 사용자 행동 기반 연령·성별 추정). 건설·금융이 타깃 소비자층 분석에 활용. 베타 ~190명(2024).
- 사업성 자동산출 없음. 소득·이동 전용 데이터 확인불가.
- 과금: 일반=광고료, RED=B2B 계약(가격 비공개, 베타). 2024 매출 전년비 21.8% 감소.
- 출처: https://www.tableau.com/ko-kr/solutions/customer/zigbang-expands-b2b-tableau-embedded-real-estate-solution · https://demoday.co.kr/bm-analysis/110

### 2-2. 해외

#### ARGUS Enterprise / ARGUS Intelligence (Altus Group)
- CRE 현금흐름·밸류에이션 표준엔진. 2024~25 ARGUS Intelligence 플랫폼으로 통합(클라우드·포트폴리오 대시보드·시나리오·ARGUS Assist AI). 200+ 대학 사용.
- 수익형 자산 한정 DCF·Cap·IRR/NPV·부채모델. **개발 프로포마(FAR→규모→공사비→개발이익) 미지원**, 인구·수요 미내장(임대성장·공실 수기입력).
- 데이터: 사용자 입력(임대료·OpEx/CapEx)+SFTP/S3 연동+익명 벤치마크. 공공 실거래·인구 미수집.
- 과금: Contact sales(연 $5K~$30K/seat 제3자 추정).
- 출처: https://www.altusgroup.com/solutions/argus-enterprise/ · https://www.altusgroup.com/solutions/argus-intelligence/ · https://www.altusgroup.com/product-releases/argus-intelligence-release-1-4/

#### TestFit ★생성형 사업성 대표(공급측)
- 생성형 부지 사업성. 필지→파라미터→~3,000 매싱 3초 생성→KPI 순위. 주당 3,200+ 딜, 7,700+ 유저(2024). 멀티패밀리·산업·데이터센터·주차·타운홈.
- **워크플로우**: (1)필지 그리기/임포트 (2)zoning·setback·FAR·주차·유닛믹스·유형 설정 (3)생성·KPI순위(유닛·yield·FAR·주차) (4)Pro Forma 애드온(+$2,000/yr): 유닛×단가=매출, 물량×단가=공사비 → **Yield on Cost(NOI/총원가)**. IRR/NPV는 Excel 임포트. 오차 10~15%, 기존 주 단위→30~60분.
- 데이터: 필지+zoning 내장(2024)·ESRI위성·지형(cut/fill)·토양·전력. **수요·인구·이동 전무**(외부 의존).
- 과금: Parking Solver $2,100/yr, Site Solver $10,000+/yr, Portfolio $15,000+/yr, Site Intel +$1,800, Pro Forma +$2,000.
- 출처: https://www.testfit.io/pricing · https://www.testfit.io/news/testfit-launches-groundbreaking-generative-design-130000031.html · https://www.testfit.io/blog/2025-testfit-year-in-review · https://illustrarch.com/articles/design-softwares/74579-testfit-review.html

#### Deepblocks ★용도지역+사업성+인구 통합
- AI 용도지역+사업성+딜소싱+ChatDB. 미국 최대 zoning DB 주장. 개발사·투자자·인수담당. 3개 제품(Developer/Algorithms/ChatDB).
- **워크플로우**: 기준설정(지리·면적·zoning·가격·유닛·유형)→파셀 스캔·zoning 로직→개발용량→3D 매싱+프로포마(수입·비용·공사비)+PDF→Developer 조정 자동반영. Algorithms는 사전분석 딜 자동배달.
- **ChatDB(인구/경제 데이터 자연어 질의)**: 센서스트랙트·ZIP·동네 단위 인구추이·구성·소득 탐색. 전용 catchment·이동모델은 미확인.
- 과금: Developer $99/mo, Deal Finder $499, Pipeline $1,499, Daily Flow $5,999/mo (딜 건수 티어).
- 출처: https://deepblocks.com/ · https://www.aecplustech.com/tools/deepblocks · https://deepblocks.com/blog/category/chatdb/embracing-ai-in-zoning-the-evolution-of-chatdb/ · https://refreshmiami.com/news/deepblocks-is-using-ai-to-make-site-selection-more-efficient-and-effective/

#### CoStar
- 최대 CRE 데이터·애널리틱스. 600만+ 물건, 1,100만+ comp, 3,000+ 시장/서브마켓. 리서처 검증 comp가 차별점.
- 사업성 툴 아님(FAR→ROI 미산출). Market Analytics가 인구·고용 예측 제공, 2025 국내이동 흐름을 멀티패밀리 수요동인으로 추적(전용 이동시각화·catchment 모델링은 아님). 토지 comp로 프로포마 가정 지원.
- 과금: Contact sales(연 $3K~$23K+).
- 출처: https://www.costar.com/products/market-analytics · https://www.vendr.com/buyer-guides/costar · https://www.pricelevel.com/vendors/costar

#### Cherre
- RE 데이터 통합·커넥티비티(인프라층, 분석제품 아님). 단일 물건 지식그래프(Universal Data Model+Semantic Layer). 2025.7 Agent.STUDIO(에이전틱 AI). $3.3조 AUM 관리.
- 사업성 미계산(다운스트림이 계산). 인구·이동은 **로드맵('25~26 위성·모바일 위치 편입 예정)**.
- 데이터: 50+ 소스 엔티티 해소(CoStar·Yardi·Trepp·MSCI/RCA·세무·등기).
- 과금: Contact sales(기관 전용, 누적펀딩 $427M).
- 출처: https://cherre.com/products/platform/ · https://blog.cherre.com/2025/04/03/cherre-data-solution-of-the-year-for-real-estate-in-2025/ · https://www.businesswire.com/news/home/20250714233347/en/Cherre-Launches-Agent.STUDIO

#### Reonomy (Altus Group)
- CRE 물건 인텔리전스·딜 프로스펙팅. LLC 관통→실소유 연락처. 2021.11 Altus 인수($202M). 5,000만+ 물건, 주간 갱신, 미국만.
- 사업성·인구·이동 없음. 소유·프로스펙팅 특화. 콘텐츠 2021 이후 정체, 소형시장 정확도 한계.
- 과금: **$4,800/yr/user**($400/mo), 7일 무료(투명 공개가).
- 출처: https://www.credaily.com/reviews/reonomy-review/ · https://www.reonomy.com/solutions/web-application/

#### HouseCanary ★AVM+affordability 예측
- 주거 AVM·예측(1.36억 물건). 산업 벤치마크 AVM. 대주·서비서·기관 주거투자자·iBuyer. CanaryAI(GenAI).
- 사업성 미산출. 분양 프로포마에 ㎡당 comp·HPI 예측 input 제공. **ZIP affordability/HPI 예측이 수요 타깃 근접**. 이동추이는 리포트 논평 수준(셀프서비스 이동·catchment 툴 아님).
- 데이터: 물건·블록/블록그룹·ZIP(HPI·affordability·수급·Market Action Score)·MSA/주.
- 과금: Basic $190/yr(2리포트/mo), Pro $790(15), Teams $1,990(40), Enterprise 커스텀, API $0.30~$6.00/call.
- 출처: https://www.housecanary.com/pricing · https://www.housecanary.com/products/data-explorer · https://www.housecanary.com/products/canary-ai

#### Local Logic ★위치/인구 인텔리전스
- 위치 인텔리전스 B2B(API/위젯). 미·캐 2.5억 위치·100B+ 데이터포인트. 18개 위치점수(walkability·transit 등), POI(28종), 센서스 인구·소득·가구, 학군, 기후.
- 사업성 미계산. 블록~메트로 인구·소득(정적)+점수=수요동인 프록시. 전용 이동흐름·소득티어 타깃은 미확인. NeighborhoodMatch/Intel(2024). 2025 "미국 홈소비자 4명 중 1명 타주 주택 탐색"은 제품 인게이지먼트(이동 데이터 제품 아님).
- 과금: Local SDK $250/mo+, Neighborhood SDK $500+, API $1,500+, Agent Reports $20/mo.
- 출처: https://locallogic.co/pricing/ · https://locallogic.co/blog/year-in-review-2025/ · https://locallogic.co/applications/data-delivery/

#### PlaceILive
- 소비자용 동네 비교(LQI 0~100, 7개 카테고리). 센서스·NYPD·MTA·Foursquare·Breezometer. 개인 대상.
- 사업성·인구이동 없음(정적 센서스 스냅샷). **2014~15 이후 갱신 정체, 2024~26 업데이트 미확인** → B2B 개발/사업성 용도엔 부적합.
- 과금: 무료(오픈데이터).
- 출처: https://www.newswire.com/news/placeilive-com-launches-new-free-platform-for-neighborhood · https://www.crunchbase.com/organization/place-i-live

---

## 3. 집중 주제 4선 (사례·구현방식)

### ① 주소 한 번 입력 → 건축가능규모 + 적정분양가 + ROI 즉시 도출

| 구분 | 랜드북/LBDev | 빌드잇(텐일레븐) | 밸류맵 | 랜드업 | TestFit | Deepblocks |
|---|---|---|---|---|---|---|
| 입력 | 토지 주소·필지 | 부지 정보 | 필지 | **주소(텍스트 1회)** | 필지 경계·파라미터 | 도시·필지 선택 |
| 규모 산출 | 건폐율·용적률·층수(심층강화) | 용적률·일조·조망 최적화 | 6유형 10안·CAD | 보고서 내 규모 | FAR·유닛수·주차(3,000안/3초) | 3D 매싱 자동 |
| 재무·분양가 | AVM+건축비+인근시세→수익·수익률 | 타당성 검토 | B2B 컨설팅 | **적정분양가(통계)+수지** | Yield on Cost(Pro Forma) | ROI 즉시 투영 |
| 소요 | "30분" | "5일→30분" | "30분" | "즉시" | 3초 생성 | 수분 |
- **핵심 인사이트**: 국내(랜드북·랜드업·밸류맵)는 "규모+분양가+수지"를 한 흐름에 통합, 해외(TestFit)는 규모·yield 중심·분양가/수요는 외부 의존, Deepblocks는 규모+프로포마+인구(ChatDB)를 분리된 도구로 제공. **"규모+적정분양가+ROI"를 한 화면에서 근거와 함께 끝까지 잇는 곳은 사실상 없음**(랜드업이 보고서로 근접하나 가설계 3D·매개변수 재계산은 약함).
- 출처: 위 플랫폼 출처 + https://m.dnews.co.kr/m_home/view.jsp?idxno=202503102255455410537 · https://www.testfit.io/blog/2025-testfit-year-in-review

### ② 인구이동(전입·전출)을 마케팅 타깃팅에 쓰는 사례

- **국내 통계청+SKT 유동인구 지도**: 기지국 모바일 빅데이터로 시·군·구 유동인구 시각화. 통계데이터센터(SDC)에서 농협카드 카드매출('23.1~'25.12) 제공. 2024 국내 인구이동자 628.3만명(+2.5%).
- **분양 실무 간접 적용**: 광고대행사가 메타 광고에서 "모델하우스 주변 거주자+부동산 앱 이력+고가 결제 이력"을 교차 타깃(35~65세). 전입인구→페르소나 자동설정 전문 플랫폼은 국내 공개 사례 **확인불가**.
- **해외 Local Logic+PropStream**: PropStream이 Local Logic 인구통계(소득·가구·교육·통근)를 1.55억 물건에 레이어(2024.6).
- **해외 Esri Tapestry**: 미국 67 세그먼트×14 LifeMode(센서스·ACS·MRI-Simmons). ArcGIS Business Analyst Target Marketing Wizard로 신규지역 진출 시 유사 세그먼트 거주지 자동식별. 2024.6 빈티지.
- **해외 Claritas PRIZM Premier**: 미 전가구 68 세그먼트(소득·교육·직업·주택가치). 세그먼트 캠페인 ROI 4~6배 주장. 2025 MADA 다중소스 결합.
- **국내 호갱노노**: 단지별 전입·전출 현황(소비자용, 마케팅 타깃 자동화는 아님).
- 출처: https://m.boannews.com/html/detail.html?idx=85085 · https://data.kostat.go.kr/sbchome/index.do · https://kostat.go.kr/board.es?mid=a10301010000&bid=205&list_no=434904&act=view · https://inside.ampm.co.kr/insight/12861 · https://www.businesswire.com/news/home/20240614005992/en/PropStream-Announces-New-Insights-Dataset-Demographics · https://doc.arcgis.com/en/esri-demographics/latest/esri-demographics/esri-tapestry.htm · https://claritas.com/prizm-premier/

### ③ 소득·지불여력으로 분양가 밴드 산출

- **국내 KB부동산 PIR**: 대출자 연소득 중위 vs 담보평가 중위로 PIR(분기). 2025 1Q 서울 10.2/경기 8.9/인천 8.2. → 지표 제공까지, 분양가 밴드 역산 자동화는 민간 공개 사례 **확인불가**.
- **국내 HF HAI/PIR/LIR**: 주택금융통계시스템 지역별 PIR·LIR·HAI(100=감당 가능). 분양가 밴드 역산 기준 활용 가능.
- **해외 HouseCanary**: 주·MSA·ZIP 단위 Affordability Time Series Forecast(월별 지불여력 예측). AVM+소득으로 price band 역산(기관·대주 커스텀).
- **확인된 방법론(역산 공식)**:
  - PIR 기반: `적정 분양가(최대) = 타깃 가구 연소득 중위 × 목표 PIR` (예: 7,000만 × 10 = 7억)
  - DSR 기반: `월 최대상환 = 월소득 × DSR한도(40%)` → `감당 대출액 = 월상환 × 기간계수` → `적정 분양가 = 대출액 + 자기자본`
- 출처: https://data.kbland.kr/kbstats/pir · https://www.index.go.kr/unity/potal/indicator/IndexInfo.do?idxCd=F0188 · https://houstat.hf.go.kr/research/portal/stat/easyStatPage/T188183126881844.do · https://www.housecanary.com/solutions/data-analytics-valuations · https://www.macrotrends.net/3080/housing-affordability-index

### ④ 선택형(모듈러) 분석 + 크레딧 과금 UX

- **BatchData**: 월정액 구독(Property Data Growth $1,000/mo·100만 레코드 ~ Scale $5,000) + **API 호출당 $0.01~ pay-as-you-go**. Skip Tracing $2,000~$20,000/mo. Crexi가 PAYG로 소유권 데이터 제공.
- **HouseCanary**: **리포트 건수 티어**(Basic 2 / Pro 15 / Teams 40 리포트·월) + API call당 과금($0.30~$6.00).
- **Deepblocks**: **딜 건수 티어**(Developer 무제한 $99 / Deal Finder 2건 $499 / Pipeline 6건 $1,499 / Daily ~22건 $5,999).
- **Reonomy/CoStar**: 연 구독 무제한·기능 티어(크레딧 미채택).
- **PropStream**: 기본 구독 + Local Logic Demographics 등 **모듈형 데이터셋 add-on**.
- **국내**: 크레딧/리포트 단위 과금 공개 사례 **확인불가**(크레마오 20회 무료·밸류맵 AI설계 건당 5만원·디스코 등기 건당이 가장 근접).
- 출처: https://batchdata.io/pricing · https://batchdata.io/case-studies/crexi-case-study · https://www.housecanary.com/pricing · https://www.aecplustech.com/tools/deepblocks · https://www.credaily.com/reviews/reonomy-review/ · https://www.propstream.com/news/propstream-announces-new-insights-dataset-demographics

---

## 4. PropAI가 벤치마킹·차별화할 5가지 시사점

### 시사점 1 — "원클릭 사업성"은 이미 레드오션, PropAI는 "수요측 결합"으로 초격차
랜드북·랜드업·밸류맵·TestFit·Deepblocks 모두 "주소→규모→수지"를 한다. 그러나 **거의 전부가 공급측(무엇을 지을 수 있나)에 갇혀 있고 수요측(누가·얼마에 살 것인가)을 외부에 떠넘긴다**(TestFit·ARGUS는 인구·수요 전무, Deepblocks는 ChatDB로 분리). PropAI는 이미 보유한 SGIS/KOSIS·실거래·상권·G2B를 한 파이프라인으로 묶어 **"건축가능규모 + 배후수요 검증 + 소득기반 적정분양가 + ROI"를 한 화면에서 근거와 함께** 도출하면, 국내외 누구도 완결하지 못한 워크플로우를 선점한다.
- 벤치마크: 랜드북의 매개변수 재계산 UX, TestFit의 3초 생성·KPI 순위, Deepblocks의 "딜 자동배달".

### 시사점 2 — 인구이동(전입·전출)을 "마케팅 타깃 페르소나"로 자동 전환 (국내 공백)
국내에서 전입인구 특성→분양 타깃 페르소나를 자동 산출하는 플랫폼은 **확인되지 않았다**(호갱노노는 단지별 표시까지, 광고대행은 수기 메타 타깃팅). 해외 Esri Tapestry/Claritas PRIZM이 세그먼트 자동매칭을 하지만 국내 미진출. PropAI가 **통계청 인구이동통계+SKT/KT 유동인구+카드매출(SDC)**을 결합해 "이 부지 배후의 전입 세대 = 30~40대 유자녀 고소득" 식 페르소나를 자동 생성하면 분양대행·시행사에게 강력한 차별점이 된다.
- 벤치마크: Esri Tapestry(67세그먼트), Claritas PRIZM(MADA 다중소스), Local Logic(블록 단위 인구·소득 API).

### 시사점 3 — 소득·지불여력 기반 "적정 분양가 밴드" 자동산출 (국내 미개척, 방법론 확정 가능)
국내 KB PIR·HF HAI는 지표 제공까지일 뿐, **PIR/DSR 역산으로 분양가 밴드를 자동 산출하는 상용 사례가 없다**. 방법론은 명확(연소득 중위×목표 PIR, DSR 한도 역산)하고 데이터(KB·HF·통계청)도 공개. PropAI가 "이 입지 배후 가구소득 중위 × 지역 PIR = 감당 가능 분양가 X억~Y억, 현재 시행 분양가가 밴드 내/초과" 판정을 제공하면 **할루시네이션 방지 + 분양가 리스크 경고**라는 PropAI 강점과도 정합.
- 벤치마크: HouseCanary ZIP affordability 예측. 단, PropAI는 "밴드+적정성 판정"까지 진전.

### 시사점 4 — "선택형 모듈 + 크레딧" 과금 UX로 진입장벽 낮추고 LTV 확대
해외는 BatchData(API PAYG), HouseCanary(리포트 건수 티어), Deepblocks(딜 건수 티어), PropStream(데이터셋 add-on)으로 **"필요한 것만 사는" UX**가 정착. 국내는 건당 과금(밸류맵 5만원·디스코 등기)이 최선. PropAI는 **이미 LLM 토큰 계측·마진(50/40/30)·코인 분리·402 게이트 인프라를 보유** → 분석 모듈(부지·수지·인구수요·분양가밴드·인허가·ESG)을 크레딧 카탈로그로 노출하고 등급별 차감하면, 풀구독 부담 없이 단건 진입→상위 전환을 유도할 수 있다.
- 벤치마크: Deepblocks 딜 티어, HouseCanary 리포트 티어, PropStream 모듈 add-on.

### 시사점 5 — "근거 가시화 + 검증 게이트"를 데이터 신선도와 함께 전면화 (신뢰 차별화)
경쟁사 대부분은 결과 수치만 보여주고 **데이터 출처·신선도·신뢰구간을 숨긴다**(TestFit 오차 10~15% 자체 고지가 예외적, HouseCanary는 confidence range 제공). PropAI는 이미 public_data_registry·calculation_metadata·검증에이전트·해시체인 원장을 갖춰 **"이 분양가는 2025-Q1 KB PIR + 인근 6개월 실거래 N건 기준, 신뢰 87%"** 식의 근거·신선도·검증을 모든 수치에 노출할 수 있다. 이는 PF 금융·은행 제출용 보고서에서 결정적 신뢰 우위.
- 벤치마크: HouseCanary confidence range, CoStar 리서처 검증 comp, Cherre 엔티티 해소(데이터 신뢰).

---

## 5. 조사 한계 (정직 표기)
1. 랜드북 LBDeveloper의 분양가·ROI 수치 자동산출 여부는 JS 렌더·로그인으로 직접 데모 확인 필요("개발비·수익 추정" 텍스트까지 확인).
2. 디스코 "AI 기획설계", 밸류맵/부동산플래닛/크레마오/랜드업 정확한 현행 가격은 로그인·문의 필요로 일부 비공개.
3. 국내 "전입인구→분양 페르소나 자동" 전문 플랫폼, "PIR 역산 분양가 밴드 자동" 상용 사례, "크레딧/모듈 과금" 국내 사례는 공개 문헌에서 미발견(확인불가).
4. PlaceILive는 2014~15 이후 갱신 정체로 2024~26 정보 미확인 → 벤치마크 가치 낮음.
5. Reonomy 콘텐츠는 2021(인수 시점) 이후 정체.

---

> 작성: 2026-06-13 · 자료수집 도구: WebSearch/WebFetch (3개 병렬 리서치 에이전트 종합) · 모든 출처 URL 본문 명기
