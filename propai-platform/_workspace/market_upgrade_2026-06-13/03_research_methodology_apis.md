# 초정밀 인구·소득·이동 기반 수요분석 — 학술/기술 근거 + 공공·민간 API 기술사양 + 견고화 베스트프랙티스

> 작성일 2026-06-13 · 부동산개발 분양기획 수요분석 고도화 리서치
> 원칙: 추측 금지. 모든 핵심 주장에 출처 URL 명시. 웹 조사(WebSearch/WebFetch) 기반.
> 코드 수정 없음 — 본 문서는 조사·권고 산출물.

---

## 0. 요약 (Executive Summary)

- **방법론(A)**: ① 인구이동 OD + **중력모형**으로 배후수요 권역과 주 이주 연령층을 추정하고, **허프모델**로 경쟁단지 대비 흡인확률을 산출, **등시선(isochrone)** 으로 도달권역 인구를 정량화한다. ② **DSR(40%)·LTV·PIR** 3중 역산으로 적정 분양가 밴드를 도출한다. ③ **가구원수별 최저주거기준 + 1인가구·고령화 통계**로 평형 MD(unit mix)를 결정한다. ④ 가명정보 결합은 **개인정보보호법 제28조의2/28조의3 + 결합전문기관** 경유가 필수이며, 직접 마케팅 목적 개인단위 프로파일링은 불가 — 최종 산출은 집계 단위 페르소나여야 한다.
- **공공 API(B)**: **SGIS OpenAPI3** 인증은 `consumer_key/secret → accessToken`(만료 4시간), 통계는 `/OpenAPI3/stats/*.json`. **KOSIS OpenAPI** 는 `statisticsData.do?method=getList` + `orgId/tblId/itmId/objL1`. 지역코드는 **법정동 10자리 / 행정동 10자리 / SGIS 8자리 / 시군구 5자리 / 집계구 13자리** 로 자릿수·기준이 다르며 행정동↔법정동은 N:M.
- **견고화(C)**: 토큰 재발급은 **single-flight(asyncio.Condition + double-checked)**, 외부호출은 **httpx hard timeout + 서킷브레이커 + tenacity(지수백오프+지터)**, 응답은 **Pydantic v2 model_validate 가드(부분실패 허용)**, 캐싱은 **Redis TTL+지터+분산락+SWR** 로 cache stampede 방지.

---

# A. 방법론 · 논문/기술자료

## A1. 인구이동(전입·전출, OD matrix) → 배후수요·마케팅 타깃 권역

### A1-1. 중력모형 (Gravity Model)

기본형:

```
T_ij = α · ( m_i^β · m_j^γ ) / d_ij^δ
```

- `T_ij`: i→j 이동량(인구이동·주택수요), `m_i,m_j`: 출발/목적지 규모(인구·고용·소득), `d_ij`: 거리/이동비용
- `δ`(거리감쇠 지수): 통상 0.5~3, 인구이동 실증은 0.52~1.0 수준. 멱함수형(`d^-γ`)·지수형(`e^{-r/R}`) 모두 사용
- Poisson 형태가 실증 표준. OECD(2021) 지역간 이동 중력모형은 인구·1인당 GDP·실업률·**주택가격**을 핵심 변수로 포함 → 주택가가 높으면 유입 억제 방향 작용(경쟁지 분석에 직접 적용 가능)

출처:
- https://en.wikipedia.org/wiki/Gravity_model_of_migration
- https://one.oecd.org/document/ECO/WKP(2021)42/en/pdf  (OECD, A Gravity Model of Inter-Regional Migration)
- https://arxiv.org/abs/1503.02915  (Distance-Decay Function of Geographical Gravity Model)
- https://arxiv.org/pdf/1710.00004  (Human Mobility: Models and Applications)

국내 OD 데이터 소스:

| 데이터 | 기관 | 세분화 | 경로 |
|---|---|---|---|
| 인구이동통계(전입·전출) | 행정안전부 | 시군구·연령·성별 | https://www.data.go.kr/data/15108093/openapi.do |
| 시군구별 이동자수 | 통계청 KOSIS | 시군구 | https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1B26001_A01 |
| OD 마이크로데이터 | 경기도 | 성·연령·목적·수단 | https://www.data.go.kr/data/15128446/fileData.do |
| MDIS 마이크로데이터 | 통계청 | 가구단위 원시자료 | https://mdis.mods.go.kr/ |

### A1-2. 허프모델 (Huff Model) — 확률적 상권 흡인

```
P_ij = ( S_j / d_ij^λ ) / Σ_k ( S_k / d_ik^λ )
예상수요 Q_ij = C_i · r_i · P_ij
```

- `P_ij`: 수요자 i가 단지 j를 선택할 확률, `S_j`: 매력도(세대수·브랜드·커뮤니티 면적), `d_ij`: 거리/이동시간, `λ`: 거리 마찰계수(통상 2)
- `C_i`: 권역 i 주거인구(등시선으로 산출), `r_i`: 상품군 이용률
- 분양 적용: `S_j`=총세대수·브랜드프리미엄·시설면적, `d_ij`=도로 이동시간(등시선 대체). 복수 경쟁단지 흡인확률 비교 → 마케팅 선순위 권역 선정
- 한계: 가격·설계품질을 `S_j` 단일변수로 단순화. ESRI 확장모형은 인구·심리변수 추가로 보완

출처:
- https://www.passcbt.kr/concept/g1/huff-probabilistic-model
- https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE01647814  (Huff 확장 상권분석모델, 대한건축학회)
- https://kiss.kstudy.com/Detail/Ar?key=2899140  (GIS 기반 상권분석모형)
- https://en.wikipedia.org/wiki/Huff_model

### A1-3. Isochrone(등시간선) · 접근성

- 분양지 기준 15·30·60분 도달권역(자동차/대중교통) 경계를 등시선으로 생성 → 권역 내 인구·소득·연령(SGIS overlay) 합산 → 허프 `C_i`/흡수율 분모로 사용
- 도구: **OSRM**(오픈소스), AWS Location Service isoline, **TravelTime**(대중교통 시간표 반영·부동산 사례 다수), QGIS+OSRM 플러그인

출처:
- https://traveltime.com/blog/what-is-an-isochrone
- https://traveltime.com/blog/catchment-area-analysis-site-selection
- https://traveltime.com/case-study/invesco-uses-traveltime-to-perform-geospatial-real-estate-analysis
- https://cran.r-project.org/web/packages/osrm/refman/osrm.html
- https://docs.aws.amazon.com/ko_kr/location/latest/developerguide/calculate-isolines.html

> 워크플로 권고: ① 등시선으로 권역 정의 → ② SGIS 권역별 인구/연령/가구 통계 overlay → ③ 중력모형으로 주 이주 연령층 추정 → ④ 허프로 경쟁단지 대비 흡인확률 → ⑤ 흡수율·MD에 반영.

---

## A2. 소득·지불여력(payment capacity) → 적정 분양가 밴드

### A2-1. LTV · DSR (한국 규제 정의·산식)

```
LTV = 대출금액 / 담보주택 가치 × 100        → 최대대출 = 감정가 × LTV상한
DSR = 연간 모든 대출 원리금 합계 / 연소득 × 100   (DTI: 주담대 원리금 + 기타대출 이자만)
```

2025~2026 한도(금융위 기준, 출처 시점 값 — 운영 시 재확인):

| 구분 | LTV | DSR |
|---|---|---|
| 규제지역 생애최초 | 70% | 40% |
| 규제지역 서민·실수요 | 60% | 40% |
| 기타지역 생애최초 | 80% | 40% |
| 은행권 일반 | 40~50% | 40% |
| 캐피탈·저축은행 | — | 50% |

- **스트레스 DSR 3단계**(2026 전면시행): 금리변동 가산금리를 DSR에 반영 → 차입가능액 축소. **분양가 밴드 산정 시 스트레스 가산금리 적용 필수**

출처:
- https://kbthink.com/main/asset-management/wealth-manage-tip/kbthink-original/202408/LTV-DTI-DSR.html
- https://www.cwtr.co.kr/news/articleView.html?idxno=16741
- https://www.molit.go.kr/policy/faq/view.jsp?insa_id=79

### A2-2. PIR (Price to Income Ratio)

```
PIR = 주택 중위(또는 평균)가격 / 가구 연소득   (연소득 전액저축 시 구입 소요연수)
```

| 기관 | 데이터 | 주기 | 링크 |
|---|---|---|---|
| KB부동산 | 소득분위·지역별 PIR | 월 | https://data.kbland.kr/kbstats/pir |
| 국토부 주거실태조사 | 전국 PIR | 연 | https://www.index.go.kr/unity/potal/indicator/IndexInfo.do?idxCd=F0188 |
| 한국주택금융공사 | 지역별 PIR·LIR | 분기 | https://houstat.hf.go.kr/research/portal/stat/easyStatPage/T188183126881844.do |

- 2023 주거실태조사: **전국 PIR 6.3배** (출처: https://eiec.kdi.re.kr/policy/materialView.do?num=261725 )
- 주의: 중위 vs 평균, 자가 vs 전체가구에 따라 값 차이 큼 → 동일 출처 내 비교 원칙. 타깃은 소득 3~7분위
- 산정방식 논문: https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART001715687

### A2-3. 지불여력 → 분양가 밴드 역산 로직(권고)

```
1) 타깃 소득분위 연소득 설정 (예: 수도권 4~6분위 5,000만~8,000만)
2) DSR 40% → 연 최대 원리금 = 연소득 × 0.40
3) 대출액 역산 = PMT 역함수(월상환액, 만기 30년, 스트레스금리)
4) LTV 적용 → 최대 분양가 = (대출액 / LTV) + 자기자금
5) PIR 교차검증 = PIR × 연소득  → 4)와 5) 중 낮은 값을 보수적 상한
6) 밴드 = [PIR×소득(보수), DSR/LTV 역산(낙관)]
```

---

## A3. 인구·가구 구조(연령·1인가구) → 평형/상품 MD

### A3-1. 통계 근거

| 지표 | 값 | 출처 |
|---|---|---|
| 1인가구 비율 | 34.5% (750.2만 가구, 2022) | https://kostat.go.kr/board.es?mid=a10301010000&bid=10820&list_no=428414&act=view |
| 1인당 주거면적 | 36.0㎡ (2023) | https://eiec.kdi.re.kr/policy/materialView.do?num=261725 |
| 자가보유율 | 60.7% (2023) | 〃 |
| 전국 PIR | 6.3배 (2023) | 〃 |

- 1인가구 거처: 단독(41.0%) > 아파트(34.0%) > 연립·다세대(11.7%) → 아파트 분양 전환 여지 큼
- 1인가구 증가(청년 비혼·고령 단독)가 수도권 소형주택 수요를 견인(연구: https://scienceon.kisti.re.kr/srch/selectPORSrchArticle.do?cn=DIKO0013089679 )

### A3-2. 가구원수별 최저주거기준(국토부 고시, 현행)

| 가구원수 | 최저면적 | 방수 |
|---|---|---|
| 1인 | 14㎡ | 1 |
| 2인 | 26㎡ | 1 |
| 3인 | 36㎡ | 2 |
| 4인 | 43㎡ | 3 |
| 5인 | 46㎡ | 3 |
| 6인 | 55㎡ | 4 |

- 출처: https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2000000059613  (최저주거기준)
- 1인 14㎡는 2011년 이후 동결, 상향 추진 보도: https://www.hankyung.com/politics/article/202207122036i
- **주의**: 최저주거기준은 공급 하한선. 실수요 적정면적은 그 2~3배가 국내 관행

### A3-3. 평형 MD 프레임워크(권고)

```
1인           → 전용 33㎡ 이하 소형
2~3인(신혼·딩크) → 전용 59~75㎡ 중소형
4인(핵가족)    → 전용 84㎡ (3베드 표준)
4인+(다자녀)   → 전용 99~115㎡ 중대형
고령 단독(60+) → 전용 43~59㎡ + 베리어프리
```
권역별 전입 연령·가구원수 OD 분포 → 가구유형 비율 → 전용면적 밴드별 공급배분(unit mix)에 직접 반영. (PropAI 기존 `unit_mix_optimizer.py` 입력 분포로 활용 가능)

---

## A4. 가명정보 결합 · 마이크로 타깃팅 + 개인정보보호법 한계

- **제28조의2(가명정보 처리 특례)**: 통계작성·과학적 연구·공익적 기록보존 목적 시 정보주체 동의 없이 가명정보 처리 가능
- **제28조의3(결합 제한)**: 서로 다른 처리자 간 가명정보 결합은 **개인정보보호위/관계부처 지정 결합전문기관**만 수행
- 신용정보법: 상업적 통계·산업적 연구도 동의 없이 허용 → 금융·카드사 데이터 활용 시 일부 근거
- 결합 절차(5단계): 결합키 생성(KISA) → 연계정보 전달 → 결합전문기관 결합 → 반출심사위 적정성 심사 → 추가 가명처리 후 반출(서면 승인)
- 한계:
  - 허용목적 한정 — **순수 영업·분양 마케팅은 3대 목적에 직접 해당 X**(개인정보보호법만 적용되는 일반데이터는 불허, 신용정보법 적용 데이터는 상업적 통계 허용)
  - **재식별 금지**(위반 5년 이하 징역/5천만원 이하 벌금), 재식별 가능시 즉시 중단·파기
  - 제3자(대행사) 제공 시 재식별 가능정보 포함 금지
  - 추가정보 결합 시 재식별 위험(external DB cross-link)
- **실무 결론**: ① 분양사·금융사·통신사 결합은 결합전문기관 경유 필수, ② 최종 출력은 **집계 단위 페르소나**(개인 식별 불가), ③ 개인단위 직접 마케팅 프로파일은 개별 동의 없이 사용 불가

출처:
- https://www.pipc.go.kr/np/default/page.do?mCode=D040010000  (개인정보보호위 가명처리·결합)
- https://www.privacy.go.kr/front/contents/cntntsView.do?contsNo=16  (가명정보 결합)
- https://www.privacy.go.kr/cmm/fms/FileDown.do?atchFileId=FILE_000000000843428&fileSn=0  (가명정보 처리 가이드라인)
- https://casenote.kr/법령/개인정보_보호법/제28조의2
- https://www.samsungsds.com/kr/insights/pseudonymization2.html

---

# B. 한국 공공/민간 데이터 API 기술 사양

## B1. SGIS OpenAPI3 (통계청 통계지리정보서비스)

> 도메인: `https://sgisapi.kostat.go.kr`. 개발센터 페이지는 `sgis.kostat.go.kr → sgis.mods.go.kr` 로 302 리다이렉트(WebFetch 시 리다이렉트 URL 재요청 필요).
> 출처: https://sgis.kostat.go.kr/developer/html/openApi/api/data.html  (리다이렉트 후 동일 내용)

### B1-1. 인증 (4시간 만료)

```
GET https://sgisapi.kostat.go.kr/OpenAPI3/auth/authentication.json
  ?consumer_key={서비스ID}&consumer_secret={보안키}
```
- 응답 envelope(SGIS 공통): `{ "id": "...", "errCd": 0, "errMsg": "Success", "result": { "accessToken": "...", "accessTimeout": "..." } }`
- `errCd: 0` = 성공. `result.accessToken` 발급, `result.accessTimeout` = 만료시각. **토큰 만료 4시간** (재발급 필요)
- 출처(인증·만료): https://sgis.kostat.go.kr/developer/html/openApi/api/intro.html  / 데이터 페이지 인증 섹션

### B1-2. 통계 엔드포인트 (필수: accessToken, year / 공통 옵션: adm_cd, low_search)

> `low_search`: 하위행정구역 검색 깊이 0/1/2 (default 1). `adm_cd`: 행정구역코드(SGIS 체계, 아래 B3 참조).

| 통계 | 경로 | 필수 | 주요 옵션 | 주요 응답필드 |
|---|---|---|---|---|
| 총조사 주요지표 | `/OpenAPI3/stats/population.json` | accessToken, year | adm_cd, low_search | tot_ppltn, avg_age, ppltn_dnsty, aged_child_idx, tot_family, tot_house |
| 인구 조건검색 | `/OpenAPI3/stats/searchpopulation.json` | accessToken, year | gender(0/1/2), adm_cd, low_search, age_type, edu_level, mrg_state | population, avg_age (행정구역별) |
| 가구통계 | `/OpenAPI3/stats/household.json` | accessToken, year | adm_cd, low_search, household_type, ocptn_type | household_cnt, family_member_cnt, avg_family_member_cnt |
| 주택통계 | `/OpenAPI3/stats/house.json` | accessToken, year | adm_cd, low_search, house_type, const_year, house_area_cd | house_cnt |
| 사업체통계 | `/OpenAPI3/stats/company.json` | accessToken, year | adm_cd, low_search, class_code, theme_cd | corp_cnt, tot_worker |
| 가구원통계 | `/OpenAPI3/stats/householdmember.json` | accessToken, year, data_type(1/2/3/4) | adm_cd, low_search, gender, age_from, age_to | population(인구통계 기준별) |
| 산업분류코드 | `/OpenAPI3/stats/industrycode.json` | accessToken, class_deg | class_code | class_code, class_nm (계층) |

### B1-3. 주소/좌표/경계

| 기능 | 경로 | 필수 | 비고 |
|---|---|---|---|
| 지오코딩 | `/OpenAPI3/addr/geocode.json` | accessToken, address | X,Y 좌표 + 행정구역 |
| 리버스 지오코딩 | `/OpenAPI3/addr/rgeocode.json` | accessToken, x_coor, y_coor | addr_type 10/20/21 → sido/sgg/emdong/road |
| 좌표변환 | `/OpenAPI3/transformation/transcoord.json` | accessToken, src, dst, posX, posY | EPSG 코드 변환 |
| 행정구역경계 | `/OpenAPI3/boundary/hadmarea.geojson` | accessToken, year, adm_cd | GeoJSON, low_search |
| 집계구경계 | `/OpenAPI3/boundary/statsarea.geojson` | accessToken, adm_cd(7자리) | 집계구 GeoJSON |

> **주의(인구이동)**: SGIS 데이터 API 문서에는 **별도의 "인구이동(전입·전출)" 통계 엔드포인트가 명시되어 있지 않다.** 인구이동 OD는 SGIS 지도 서비스(시각화)로 제공되거나, **행정안전부 인구이동통계 API(data.go.kr 15108093)** 또는 **KOSIS DT_1B26001_A01** 등에서 별도 수집해야 한다(A1-1 표 참조). PropAI에서는 OD 데이터원을 KOSIS/행안부로 분리 설계할 것.

## B2. KOSIS OpenAPI (국가통계포털)

> 출처: https://kosis.kr/openapi/devGuide/devGuide_0201List.do  / 개발가이드 PDF https://kosis.kr/openapi/file/openApi_manual_v1.0.pdf

### B2-1. statisticsData.do (통계자료 조회)

```
GET https://kosis.kr/openapi/statisticsData.do?method=getList
  &apiKey={인증키}
  &orgId={기관ID}            예: 101(통계청)
  &tblId={통계표ID}          예: DT_1B41, DT_1B26001_A01
  &objL1={분류1코드}|ALL     (필수) — objL2~objL8 선택
  &itmId={항목ID}|ALL
  &prdSe={D|M|Q|H|Y|F|IR}    수록주기
  &startPrdDe={YYYY..}&endPrdDe={YYYY..}   또는 &newEstPrdCnt={최근 N개}
  &format=json&jsonVD=Y
```

- 통계표선택 방식 대안: `https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList`
- 자료등록(즐겨찾기) 방식: `userStatsId` 사용 + `newEstPrdCnt`

### B2-2. 응답 구조 (JSON)

각 데이터 row가 아래 필드를 가진 배열:
```
ORG_ID, TBL_ID, TBL_NM, C1_NM, C1_NM_ENG, ITM_ID, ITM_NM,
UNIT_NM, UNIT_NM_ENG, PRD_SE, PRD_DE(YYYYMMDD), DT(값), LST_CHN_DE
```

### B2-3. 에러 응답 / 흔한 에러

- **errCd 20** = "필수요청변수값이 누락되었습니다" → 해결: `objL2="ALL"`로 변경, 그래도 발생 시 `objL3="ALL"` 추가(분류레벨 누락이 원인)
- 에러는 `{ "err": "...", "errMsg": "..." }` 형태 JSON 반환. 공식 매뉴얼 PDF에 코드표 존재(20=파라미터 누락 등). **인증키 미등록/오류, 호출한도 초과**도 별도 코드로 반환되므로 errMsg 텍스트 기반 분기 권장
- 출처: https://velog.io/@bcl0206/국가통계포털-KOSIS-openAPI-사용-요령-심플  / 매뉴얼 PDF(상기)

### B2-4. 소득/임금 관련 통계표ID 후보

- 통계표 검색 API로 동적 탐색 권장: `통계청_KOSIS 통계목록 조회` https://www.data.go.kr/data/15056860/openapi.do
- 소득·임금 관련 후보군(운영 전 통계목록 조회로 tblId 확정 필수): 가계동향조사(소득), 가계금융복지조사(가구 소득·자산·부채 분위), 지역소득(시도), 고용형태별근로실태조사(임금)
  - ※ tblId는 통계표 개편 시 변경되므로 **하드코딩 금지**, 통계목록 API로 조회·캐시할 것

## B3. 지역코드 변환 표준

| 코드 | 관리기관 | 자릿수 | 구성 | 기준 |
|---|---|---|---|---|
| 법정동코드 | 행안부 | **10** | 시도2+시군구2+읍면동3+리2+예비1 | 법정동(지적·등기) |
| 행정동코드 | 행안부 | **10** | 시도2+시군구3+읍면동3+리(항상00)2 | 행정동(행정편의) |
| SGIS 행정구역코드(adm_cd) | 통계청 | **8** | 시도2+시군구3+읍면동3 | 행정동(통계) |
| 시군구코드 | 공통 | **5** | 시도2+시군구3 | 법정/행정 앞5자리 |
| 집계구코드(tot_oa_cd) | 통계청 | **13** | 시도2+시군구3+읍면동3+집계구순번5 | 집계구(~500명) |

예시(서울 종로구): 법정동 종로구=`1111000000`, 청운동=`1111010100`, 시군구코드=`11110`.

핵심 주의:
- **SGIS adm_cd는 2021.12.28 이전 7자리 → 이후 8자리로 확대**. 구버전 데이터와 직접 비교 불가
- **집계구는 인구총조사 5년 주기로 경계·코드 재편** → 연도 기준 코드 필수
- **행정동↔법정동은 N:M**(행정동은 조례로 수시 분동/합동, 법정동은 법령개정 없이 불변). 통계(SGIS)=행정동 기준, 토지/건물=법정동 기준이라 결합 시 매핑테이블 필수
  - 사례: 미성아파트 = 법정동 압구정동 / 행정동 신사동

변환 자원:
- 행안부 법정동코드 전체 다운로드: https://www.code.go.kr/stdcodesrch/codeAllDownloadL.do
- 법정동코드 OpenAPI: https://www.data.go.kr/data/15077871/openapi.do
- 통계청 법정동 연계정보: https://www.data.go.kr/data/15136368/fileData.do
- SGIS 행정구역 통계 및 경계(집계구 포함): https://www.data.go.kr/data/15129688/fileData.do
- **PublicDataReader(Python)**: `pdr.code_hdong()`, `pdr.code_bdong()`, `pdr.code_hdong_bdong()` → https://wooiljeong.github.io/python/pdr-code/
- 연도별 행정동 GeoJSON: https://github.com/vuski/admdongkor

## B4. 민간 결합데이터 API (공개정보 한도)

> 공통: 셋 다 **공개 가격표 없음 → 견적/계약 협의**. 개인 식별 불가 통계·가명 처리 형태로 제공.

### KCB(코리아크레딧뷰로) — K-Atlas / 데이터스토어
- 제공: 소득 추정, 신용, 카드소비, 이주·통근, 거주/상주 인구
- 공간단위: 행정동(60인↓ 마스킹), K-Block(전국 28만, 블록당 ~200명, 5인↓ 마스킹), 집계구, 100m/50m 격자, 국가기초구역(우편번호 5자리)
- 연동: KCB 데이터스토어 신청→자격심사→API. K-Atlas는 부동산114 결합 GIS 입지분석 웹툴
- 출처: https://datastore.koreacb.com/api/index.do / https://www.r114.com/?_c=solution&_m=solutiondefault&_a=katlas

### NICE지니데이터 / NICE평가정보
- 제공: 카드결제 기반 상권 소비(업종별 매출·점포수·결제단가·고객비중·경쟁밀집도), 유동인구
- 공간단위: 행정동(~3,600~4,000개), 블록(42만)
- 서비스: 나이스비즈맵(웹 상권분석), NICE API 플랫폼(기업 신용·사업자 API)
- 출처: http://nicezinidata.com/index.html / https://m.nicebizmap.co.kr/ / https://www.niceapi.co.kr/

### SKT 지오비전 퍼즐 (Geovision)
- 제공: 유동인구(기지국 기반 시간대별), 지하철·장소 혼잡도, 국내여행, 주거생활(아파트 거주자 특성), 공유킥보드
- 연동: SK open API(REST, openapi.sk.com), KDX 한국데이터거래소 상품. 무료 제공량 + 초과 유료
- 처리: "통계화된 익명정보"(개별 식별 불가 집계). 행정동/집계구 집계 여부 공식 명시 미확인
- 출처: https://puzzle.geovision.co.kr/ / https://openapi.sk.com/products/detail?svcSeq=2 / https://kdx.kr/data/view?product_id=34094 / https://www.sktenterprise.com/product/detail/192

---

# C. 견고화 베스트프랙티스 (Python / FastAPI / httpx / asyncio / Pydantic v2 / Redis)

## C1. 토큰 재발급 동시성 — Single-Flight

핵심: ① 잠금 없이 1차 유효성 확인(빠른 경로) → ② 락 획득 후 2차 확인(double-checked) → ③ 재발급 중이면 대기, 아니면 단일 재발급 후 `notify_all`. **I/O(HTTP 호출)는 락 밖에서 수행.**

```python
import asyncio, time, httpx
from dataclasses import dataclass
from typing import Optional

@dataclass
class TokenState:
    access_token: Optional[str] = None
    expires_at: float = 0.0

class SGISTokenManager:
    def __init__(self, ck: str, cs: str):
        self._ck, self._cs = ck, cs
        self._state = TokenState()
        self._refreshing = False
        self._cond = asyncio.Condition()
        self._SKEW = 300  # 만료 5분 전 갱신

    def _valid(self) -> bool:
        return (self._state.access_token is not None
                and time.monotonic() < self._state.expires_at - self._SKEW)

    async def get_token(self) -> str:
        if self._valid():                       # 1차(락 없음)
            return self._state.access_token
        async with self._cond:
            if self._valid():                   # 2차(double-checked)
                return self._state.access_token
            if self._refreshing:                # 진행 중이면 대기(single-flight)
                await self._cond.wait_for(lambda: not self._refreshing)
                return self._state.access_token
            self._refreshing = True             # 내가 담당
        try:
            tok, ttl = await self._fetch()      # I/O는 락 밖
            async with self._cond:
                self._state.access_token = tok
                self._state.expires_at = time.monotonic() + ttl
                self._refreshing = False
                self._cond.notify_all()
            return tok
        except Exception:
            async with self._cond:
                self._refreshing = False
                self._cond.notify_all()
            raise

    async def _fetch(self) -> tuple[str, float]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as c:
            r = await c.get(
                "https://sgisapi.kostat.go.kr/OpenAPI3/auth/authentication.json",
                params={"consumer_key": self._ck, "consumer_secret": self._cs})
            r.raise_for_status()
            d = r.json()["result"]
            return d["accessToken"], float(d.get("accessTimeout", 14400))  # 4h
```
출처: https://docs.python.org/3/library/asyncio-sync.html / https://www.python-httpx.org/advanced/authentication/

## C2. Hard Timeout + 서킷브레이커 + tenacity 재시도

```python
import httpx, logging
from tenacity import (retry, stop_after_attempt, wait_exponential,
                      wait_random, retry_if_exception_type, before_sleep_log)
from aiocircuitbreaker import circuit, CircuitBreakerError

log = logging.getLogger(__name__)
SGIS_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0)

@circuit(failure_threshold=5, recovery_timeout=60, expected_exception=Exception)
async def _call(client, url, params):
    r = await client.get(url, params=params, timeout=SGIS_TIMEOUT)
    r.raise_for_status()
    return r.json()

@retry(reraise=True, stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=1, max=10) + wait_random(0, 1),
       retry=retry_if_exception_type(httpx.TransportError),
       before_sleep=before_sleep_log(log, logging.WARNING))
async def fetch_sgis(url, params):
    async with httpx.AsyncClient() as c:
        return await _call(c, url, params)   # Timeout + CB + retry 3겹
```
- 상태기계: Closed(fail_max 초과→Open) / Open(즉시 차단, reset_timeout 후→Half-Open) / Half-Open(테스트 1개: 성공→Closed, 실패→Open)
- 라이브러리 선택: `aiocircuitbreaker`(asyncio 네이티브, 단일프로세스), `pybreaker`(동기·Redis 상태공유). FastAPI 단일워커면 aiocircuitbreaker 권장. 멀티워커 공유 상태가 필요하면 pybreaker+Redis
- 엔드포인트에서 `CircuitBreakerError → 503`, `httpx.TimeoutException → 504`로 매핑

출처: https://github.com/GenyaSol/aiocircuitbreaker / https://github.com/danielfm/pybreaker / https://oneuptime.com/blog/post/2025-01-06-python-retry-exponential-backoff/view / https://medium.com/@sparknp1/8-httpx-asyncio-patterns-for-safer-faster-clients-f27bc82e93e6

## C3. Pydantic v2 응답검증 가드

```python
from pydantic import BaseModel, Field, ValidationError, model_validator
from typing import Optional, Any
import logging
log = logging.getLogger(__name__)

class SGISItem(BaseModel):
    cd: str
    addr_name: str
    x_coor: Optional[float] = None
    y_coor: Optional[float] = None
    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> Any:           # 숫자가 문자열로 와도 변환
        if isinstance(v, dict):
            for k in ("x_coor", "y_coor"):
                s = v.get(k)
                if isinstance(s, str) and s.strip():
                    try: v[k] = float(s)
                    except ValueError: v[k] = None
        return v

class SGISResp(BaseModel):
    errCd: int = 0
    errMsg: Optional[str] = None
    result: list[SGISItem] = Field(default_factory=list)

def parse(raw: dict) -> SGISResp | None:        # 실패해도 앱 안 죽음
    try:
        return SGISResp.model_validate(raw)
    except ValidationError as e:
        log.warning("SGIS parse fail n=%d %s", e.error_count(),
                    e.errors(include_url=False))
        return None

def parse_partial(items: list[dict]) -> list[SGISItem]:  # 부분 실패 허용
    out = []
    for it in items:
        try: out.append(SGISItem.model_validate(it))
        except ValidationError as e: log.debug("skip %s", e.errors(include_url=False))
    return out
```
원칙: 누락필드 기본값, `model_validate`, 부분실패 허용(항목별 try). 출처: https://docs.pydantic.dev/latest/errors/errors/ / https://docs.pydantic.dev/latest/concepts/models/

## C4. Redis 캐싱 TTL — Cache Stampede 방지

TTL 기준(데이터 갱신주기 연동):

| 데이터 | 갱신주기 | 권장 TTL | 지터 |
|---|---|---|---|
| SGIS 행정구역코드 | 연 1회 | 24h | ±30분 |
| KOSIS 통계지표 | 월/분기 | 6h | ±20분 |
| MOLIT 실거래 | 일 | 2h | ±10분 |
| AVM 시세 | 실시간 | 30분 | ±3분 |

```python
import asyncio, json, random, hashlib
import redis.asyncio as aioredis
r = aioredis.from_url("redis://localhost:6379", decode_responses=True)

def jitter_ttl(base: int, ratio=0.1) -> int:    # 동시 만료 분산
    s = int(base * ratio); return base + random.randint(-s, s)

async def get_or_compute(key, compute, ttl=3600):   # 분산락=단일 재계산
    cached = await r.get(key)
    if cached: return json.loads(cached)
    lock = f"lock:{key}"
    if await r.set(lock, "1", nx=True, ex=30):
        try:
            v = await compute()
            await r.setex(key, jitter_ttl(ttl), json.dumps(v)); return v
        finally: await r.delete(lock)
    for _ in range(15):                          # 락 실패→폴링 후 캐시
        await asyncio.sleep(0.2)
        cached = await r.get(key)
        if cached: return json.loads(cached)
    return await compute()                       # 마지막 보루

async def get_swr(key, compute, ttl=3600, stale=300):  # stale-while-revalidate
    p = r.pipeline(); p.get(key); p.ttl(key)
    cached, rem = await p.execute()
    if cached:
        if rem != -1 and rem < stale:
            asyncio.create_task(_bg(key, compute, ttl))  # 비동기 갱신
        return json.loads(cached)
    return await get_or_compute(key, compute, ttl)

async def _bg(key, compute, ttl):
    if not await r.set(f"swr:{key}", "1", nx=True, ex=ttl): return
    try: await r.setex(key, jitter_ttl(ttl), json.dumps(await compute()))
    except Exception: pass
    finally: await r.delete(f"swr:{key}")

def cache_key(prefix, **p) -> str:               # 키 설계(긴 키는 해시)
    raw = ":".join(f"{k}={v}" for k, v in sorted(p.items()))
    if len(raw) > 200: raw = hashlib.md5(raw.encode()).hexdigest()
    return f"{prefix}:{raw}"
```
기법: ① TTL 지터, ② 분산락(단일 재계산), ③ SWR(만료 임박 시 낡은 값 반환+백그라운드 갱신), ④ 키 설계. 출처: https://redis.io/blog/how-to-tame-the-thundering-herd-problem/ / https://redis.antirez.com/fundamental/cache-stampede-prevention.html

전체 흐름:
```
요청 → Redis 히트? ─(TTL 임박)→ SWR 백그라운드 갱신 → 즉시 반환
        └ 미스 → single-flight 락 → 외부호출(Timeout+CB+tenacity) → Pydantic 검증 → setex(지터 TTL)
                 └ CB Open → 즉시 503
```

---

# D. PropAI 구현에 직접 반영할 권고

1. **데이터원 분리 설계**: 인구이동 OD는 SGIS가 아닌 **행안부 API(data.go.kr 15108093)** 또는 **KOSIS DT_1B26001_A01**에서 수집(SGIS stats엔 인구이동 엔드포인트 없음). 인구·가구·주택 구조는 SGIS `/OpenAPI3/stats/{population,searchpopulation,household,house}.json`.
2. **SGIS 토큰 매니저**: 4시간 만료 → C1의 single-flight `SGISTokenManager`를 단일 인스턴스로 주입(앱 lifespan). 만료 스큐 5분.
3. **지역코드 정규화 레이어**: SGIS adm_cd(8자리, 2021 이후)·법정동(10)·시군구(5)·집계구(13) 변환 유틸 + **PublicDataReader** 매핑테이블 캐시. 행정동↔법정동 N:M은 매핑테이블 join(이름 매칭 금지). 기존 PropAI의 PNU/시군구 도출 로직과 통합.
4. **KOSIS tblId 동적 조회**: 소득/임금 통계표 ID 하드코딩 금지 → 통계목록 API(15056860)로 조회·24h 캐시. `errCd 20` 발생 시 `objL2/objL3="ALL"` 폴백.
5. **분양가 밴드 엔진**: A2-3 역산 로직(DSR 40% + 스트레스금리 + LTV + PIR 교차) 구현, 결과를 기존 수지/ROI 컨텍스트에 단일 데이터원으로 연결.
6. **평형 MD**: 권역별 전입 연령·가구원수 분포 → 가구유형 비율 → 기존 `unit_mix_optimizer.py` 입력으로 연결(최저주거기준은 하한 검증용).
7. **견고화 적용**: 모든 외부 통계호출에 C2(Timeout+CB+tenacity) + C3(Pydantic 가드, 부분실패 허용) + C4(Redis SWR, 표의 TTL/지터). 기존 키오염 가드·서킷 구조와 정합.
8. **가명정보 컴플라이언스 게이트**: 민간 결합데이터(KCB/NICE/SKT)는 **집계 단위만** 사용. 개인단위 프로파일 금지, 결합전문기관 경유 필수임을 데이터 거버넌스 문서에 명시. 직접 마케팅 타깃은 동의 기반만.

---

# E. 통합 출처 목록

방법론 A
- https://en.wikipedia.org/wiki/Gravity_model_of_migration
- https://one.oecd.org/document/ECO/WKP(2021)42/en/pdf
- https://arxiv.org/abs/1503.02915 · https://arxiv.org/pdf/1710.00004
- https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE01647814 · https://en.wikipedia.org/wiki/Huff_model
- https://traveltime.com/blog/what-is-an-isochrone · https://traveltime.com/blog/catchment-area-analysis-site-selection
- https://kbthink.com/main/asset-management/wealth-manage-tip/kbthink-original/202408/LTV-DTI-DSR.html
- https://data.kbland.kr/kbstats/pir · https://www.index.go.kr/unity/potal/indicator/IndexInfo.do?idxCd=F0188
- https://eiec.kdi.re.kr/policy/materialView.do?num=261725
- https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2000000059613
- https://kostat.go.kr/board.es?mid=a10301010000&bid=10820&list_no=428414&act=view
- https://www.pipc.go.kr/np/default/page.do?mCode=D040010000 · https://www.privacy.go.kr/front/contents/cntntsView.do?contsNo=16

API B
- https://sgis.kostat.go.kr/developer/html/openApi/api/data.html · https://sgis.kostat.go.kr/developer/html/openApi/api/intro.html
- https://kosis.kr/openapi/devGuide/devGuide_0201List.do · https://kosis.kr/openapi/file/openApi_manual_v1.0.pdf
- https://www.data.go.kr/data/15056860/openapi.do (KOSIS 통계목록) · https://www.data.go.kr/data/15108093/openapi.do (행안부 인구이동)
- https://www.code.go.kr/stdcodesrch/codeAllDownloadL.do · https://www.data.go.kr/data/15077871/openapi.do
- https://www.data.go.kr/data/15129688/fileData.do · https://wooiljeong.github.io/python/pdr-code/ · https://github.com/vuski/admdongkor
- https://datastore.koreacb.com/api/index.do · http://nicezinidata.com/index.html · https://puzzle.geovision.co.kr/ · https://openapi.sk.com/products/detail?svcSeq=2

견고화 C
- https://docs.python.org/3/library/asyncio-sync.html · https://www.python-httpx.org/advanced/authentication/
- https://github.com/GenyaSol/aiocircuitbreaker · https://github.com/danielfm/pybreaker
- https://oneuptime.com/blog/post/2025-01-06-python-retry-exponential-backoff/view
- https://docs.pydantic.dev/latest/errors/errors/ · https://docs.pydantic.dev/latest/concepts/models/
- https://redis.io/blog/how-to-tame-the-thundering-herd-problem/ · https://redis.antirez.com/fundamental/cache-stampede-prevention.html

> 검증 메모: SGIS 개발센터 데이터/인증 페이지는 `sgis.kostat.go.kr → sgis.mods.go.kr` 302 리다이렉트(동일 콘텐츠). 본 문서의 SGIS 엔드포인트·파라미터·응답필드는 해당 데이터 API 문서 기준. 2026-06 규제수치(LTV/DSR)·통계수치(PIR 6.3 등)는 조사 시점 출처값이며 운영 반영 전 원출처 재확인 권장.
