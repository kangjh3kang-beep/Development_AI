# P2 수지분석 점진모델 — 부지직후 시장표준 baseline 엔드포인트 (백엔드)

## 개요
부지분석 직후(설계·공사비 입력 전) 부지 데이터+시장표준만으로 1차 수지(baseline)를 자동 산출하는
신규 엔드포인트 `POST /api/v2/feasibility/baseline`. 이후 단계 정밀화의 출발점.
**무목업**: 추정값은 "시장표준/추정" 정직 라벨, 실데이터(자동감지 시세·공시지가) 있으면 우선 사용.

## 변경 파일 (백엔드만, 220 insertions / 0 deletions, 신규 의존성 0)
- `app/routers/v2_feasibility.py` — `POST /baseline` 신설 + import(`logging`, `typing.Any`, baseline 스키마) + `logger` 정의
- `app/schemas/feasibility_v2.py` — `FeasibilityBaselineRequest`, `FeasibilityBaselineResponse(FeasibilityResultResponse 상속)` 신설

## 요청 스키마 — FeasibilityBaselineRequest (부지 데이터만)
| 필드 | 타입 | 기본 | 설명 |
|------|------|------|------|
| address | str | "" | 주소. zone_type/면적/공시지가 자동감지에 사용 |
| zone_type | str | "" | 용도지역명(예: 자연녹지지역). 미입력 시 주소로 자동감지 |
| zone_code | str | "" | 용도지역 코드(라벨용) |
| land_area_sqm | float | 0 | 부지면적(㎡). 미입력 시 자동감지 |
| pnu | str | "" | 필지고유번호(자동감지 보조) |
| region | str | "서울" | 시도명(분양가 시드 폴백) |
| official_price_per_sqm | float | 0 | 공시지가(원/㎡). 미입력 시 자동감지/표준 |
| development_type | str | "" | 강제 개발유형. 미입력 시 용도지역 대표유형 자동선택 |
| equity_won | int | 0 | 자기자본. 미입력 시 토지비 추정액 가정 |

## 응답 스키마 — FeasibilityBaselineResponse
`FeasibilityResultResponse`(=`/calculate` 응답)를 **상속** → 프론트 동일 렌더 재사용.
- /calculate 공통: development_type, module_name, total_revenue_won, total_cost_won, net_profit_won,
  profit_rate_pct, roi_pct, npv_won, grade, cost_breakdown_won, tax_detail, special_detail
- **baseline 추가 필드**:
  - `is_baseline: bool = True`
  - `confidence: str` — "보통"(추정페널티≤1) / "낮음"(>1)
  - `sources: dict` — 각 입력값 출처 라벨(자동감지·사용자입력·시장표준·표준폴백)
  - `assumptions: dict` — 역산 GFA·적용 FAR/BCR·추정 층수·표준단가·평형 등 가정 명시

## 처리 로직 (기존 계산엔진 100% 재사용, 새 계산로직 최소)
1. **부지 데이터 확보(실데이터 우선)**: zone_type/면적/공시지가 중 누락 시 `AutoZoningService.analyze_by_address(address)`로 자동감지(공공데이터). 출처를 sources에 기록.
2. **면적 필수 가드**: 입력·자동감지 모두 실패 시 422(정직한 한국어 에러).
3. **개발유형 선택**: `permit_validator.get_permitted_types(zone_type)`에서 대표유형 — 일반분양(M06) 우선, 없으면 첫 허용유형. 용도지역 미상/개발제한이면 M06 보수가정(+페널티).
4. **GFA 역산**: 적용 FAR = min(조례/법정 상한, 개발유형 표준). 조례/법정 없으면 유형표준(+페널티). `GFA = 부지면적 × FAR/100`. 층수 = round(FAR/BCR).
5. **세대수·평형**: `total_gfa / 유형평균세대면적`, 평형 = 세대면적/3.305785.
6. **분양가 시드(시장표준)**: `regional_pricing.get_regional_sale_price_per_pyeong(dev_type, region, address)` — 시군구→시도 시세 테이블(SSOT, 추천·파이프라인 공유). 라벨="지역 시세 테이블(시장표준)".
7. **토지비/공시지가**: 자동감지 공시지가 우선, 없으면 표준 150만원/㎡(+페널티). price_multiplier=1.1(공시→실거래 보수보정).
8. **공사비**: 엔진이 `DEFAULT_DIRECT_COST_PER_SQM`(SSOT 표준 개산단가)+간접비 자동적용. 라벨만 표기.
9. **자기자본**: 미입력 시 토지비 추정액(`공시가×1.1×면적`).
10. **계산엔진 재사용**: `ModuleInput` 구성 → `FeasibilityServiceV2().calculate(inp)` → 매출·원가·세금·ROI·NPV·grade 산출. 응답을 baseline 메타필드와 함께 반환.

### 출처/표준 근거
- **표준단가**: `construction_cost_engine.DEFAULT_DIRECT_COST_PER_SQM`(apartment 240만, officetel 260만, office 250만, house 등) + `DEFAULT_INDIRECT_RATIOS`(설계4%·감리3%·예비5%·일반관리3%). repository SSOT 조회, 실패 시 상수 폴백(회귀0).
- **분양가**: `regional_pricing` 시군구/시도 시세 테이블(만원/평) × 유형보정계수.
- **FAR/BCR**: `auto_zoning_service` zone_limits(조례 우선·법정 폴백). 자동감지 실패 시 `FeasibilityServiceV2._get_type_typical_far`(유형표준).

## 신뢰도/가정 표기 (할루시네이션 방지)
- 추정 데이터(유형표준 FAR, 공시지가 표준폴백, 용도지역 미상)마다 confidence_penalty 누적 → 보통/낮음.
- 모든 역산·가정은 assumptions에 한국어 수식/라벨로 노출. 출처는 sources에 항목별 라벨.
- 실데이터(자동감지 시세·공시지가) 확보 시 해당 항목은 "자동감지(공공데이터/공시지가)" 라벨로 우선.

## 인증/게이트
`/calculate`와 동일하게 `dependencies=[Depends(enforce_llm_quota)]` 적용. LLM은 미사용(규칙기반 시드+엔진).

## 라이브 검증 (TestClient, 실 앱 부팅 — 라우트 등록 확인 + 실제 VWorld 도달)
| 케이스 | 입력 | 결과 |
|--------|------|------|
| 자연녹지 1520 | zone=자연녹지지역, area=1520, region=경기, addr=경기도 파주시 | 200. dev=M10(단독주택), GFA=1520㎡(FAR100% 역산), 분양가 1320만원/평(시장표준), 공시지가 자동감지(VWorld 200), revenue=5,270,760,197 / cost=5,131,485,155 / ROI=29.22% / grade=E, is_baseline=true, confidence=보통 |
| 면적 누락 | zone=제3종일반(area/주소 없음) | 422 "부지면적을 입력하거나, 주소로 자동감지 가능한 주소를 제공하세요." |
| 제3종일반 1000 | zone=제3종일반주거지역, area=1000, region=서울, addr=서울 강남구 | 200. dev=M06(일반분양 대표선택), grade=A, confidence=보통 |

- py_compile: 두 파일 OK. lsp diagnostics: 0 errors(typing.Any·logger 추가로 해소).
- git diff: 220 insertions / 0 deletions, import 삭제 0건, 대상 2개 파일만.
- 로컬 환경이 실제 VWorld에 도달 → 케이스1에서 공시지가 자동감지로 ROI가 표준폴백 대비 개선됨(실데이터 우선 동작 확인).

## 검증 메모(직접 엔진 경로)
자동감지 미사용(zone_limits 없음) 시 자연녹지 M10은 유형표준 FAR 100% 사용 → GFA 1520㎡, 표준공사비/시세로
적자(grade F) 산출. 저밀도 자연녹지 부지의 정직한 보수 baseline으로 의도대로 동작.

## 미진/후속
- 자동감지 zone_limits(조례 FAR/BCR)는 외부 API 의존 — 국외IP 차단 환경에선 유형표준 폴백(+페널티 표기됨). Oracle 배포 환경에선 정상.
- 분양가는 시세 테이블(SSOT) 기반. MOLIT 실거래 API 연동은 regional_pricing의 향후 과제(현 baseline은 테이블 시드).
- 프론트 렌더 연동은 병렬 executor 담당(본 작업 범위 외). 응답이 /calculate 구조 동일이라 동일 렌더 재사용 가능.
- push/배포 금지 준수 — 코드 변경만. 백엔드 변경은 SSH 배포 필요(메모리 참조).
