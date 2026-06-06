# 75 — 지목·소유구분 "분석 전" 버그 근본수정 (백엔드)

## 1. 변경 파일
- `propai-platform/apps/api/app/services/pipeline/project_pipeline.py` — _run_site_analysis 병합부(라인 ~280)에 land_category·owner_type 전파 추가(+16줄)
- `propai-platform/apps/api/app/services/land_intelligence/land_info_service.py` — Phase-1 폴백 owner_type 하드코딩 "" → zoning_result 제공 시 사용(±5줄)

## 2. 근본원인 & 수정
- 근본원인: `_run_site_analysis`(project_pipeline.py:279-303) comprehensive→pre_collected 병합 시
  land_area_sqm·infrastructure·coordinates·building_info·land_use_plan·special_districts·
  nearby_transactions·official_land_price·pnu는 복사하나 **`comprehensive["land_register"]["land_category"]·["owner_type"]`를 복사 안 함**.
  → 라인 380/382 `pre_collected.get("land_category"/"owner_type","")`가 빈값 → basic 공백 → 프론트
  `PipelineResultDetail.tsx:106-107` "분석 전".
- 수정1(병합 추가): `_clr = comprehensive.get("land_register")`(line280 기존 변수)에서
  `land_category`·`owner_type` 추출해 pre_collected에 backfill. land_category가 비면
  `comprehensive["land_characteristics"]["land_category"]`로 백필(land_info_service:428-429 패턴 일관).
- 수정2(owner_type 소스): owner_type의 **권위 소스는 토지대장**
  `_fetch_land_register`(land_info_service:591) → VWORLD `LP_PA_CBND_BUBUN`의 `own_gbn_nm`
  (vworld_service.py:168). Phase 2에서 `result["land_register"]`를 실값으로 교체하므로
  comprehensive에 owner_type이 채워져 있고, 이를 그대로 pre_collected로 전파.
  Phase-1 폴백 라인의 하드코딩 ""는 zoning_result 제공 시 사용하도록 변경(없으면 빈값 유지).
- 토지특성(NED getLandCharacteristics)은 소유구분(ownership)을 반환하지 않음 → owner_type 추가 소스 없음.

## 3. 무목업 준수
- 실제 수집값(land_register own_gbn_nm·jimok, land_characteristics land_category)만 전파.
- 소스 없으면 빈값 유지. **가짜 소유구분/지목 생성 없음.** 기존 필드 병합 무영향(land_area_sqm 등 그대로).

## 4. 단위검증(전파 확인) — PASS
- CASE1 land_register{land_category:"대",owner_type:"개인"} → basic{대,개인} ✅
- CASE2 land_register 지목 비고 land_characteristics{land_category:"전"} 백필 → basic{전, owner=""} ✅(owner 소스없음=빈값)
- CASE3 빈 comprehensive → basic{"",""} ✅
- CASE4 기존 pre_collected{임야,국공유지} 무파괴 ✅
- py_compile 2파일 OK / import-boot(PYTHONPATH=repo+api) IMPORT_OK
- 외부호출·프로덕션DB 변경 없음.

## 5. 커밋 해시
- (아래 커밋 결과 참조)

## 6. 라이브 재검증 기대
- 재분석(파이프라인 재실행) 시 부지분석 보고서 basic.land_category(지목)·owner_type(소유구분)이
  VWORLD 토지대장/토지특성에서 채워져 "분석 전" 대신 실값 표시 기대.
- 단, VWORLD own_gbn_nm 미반환 필지는 owner_type 빈값 정상(무목업).

## 7. 미진
- VWORLD가 own_gbn_nm을 비워 반환하는 필지의 소유구분은 무료 API로 보강 불가(등기부 IROS 유료).
  지목은 토지특성 백필로 커버되나, 소유구분은 토지대장 own_gbn_nm 의존.
- 라이브 E2E(실주소 재분석 화면 확인)는 SSH배포 금지 제약상 미수행 — 로컬 단위전파만 검증.
