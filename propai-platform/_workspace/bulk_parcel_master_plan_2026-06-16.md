# 대량 다필지 검색·분석 완벽구현 방안·계획 (반복수렴) — 2026-06-16

## 0. 목표
플랫폼의 **모든 주소·필지 검색**을 단일필지에서 **대량 다필지(구역·수백~수천 필지)** 로 확장(가산 교체)하고,
배선·병목을 반복수렴(분석→수정→재검증)으로 완벽 해결한다. 단일 경로 SLA는 불가침(F-Parcel INV-M1).

## 1. 현황 감사 결과 (전수)
### 이미 다필지 지원(자산)
- 프론트: `GlobalAddressSearch(single=false)`·`ParcelBoundaryMap`·`DevelopmentScenarioCard`·`PreCheckWorkspace`(parcels state)
- 백엔드: `/zoning/parcel-boundaries`·`/zoning/special-parcels`·`/development-methods/scenarios`(parcels)·`/zoning/parse-parcels`(엑셀)
- 신규: **F-Parcel 배치 파운데이션**(`/api/v1/parcels/batch` submit/poll/cancel, 비동기·부분성·완결성·집계보류·멱등)

### 갭(교체 대상)
- **프론트 공통바 `ProjectAddressInput` single 고정** — 여러 워크스페이스가 이를 통해 단일만.
- **단일 address:str 엔드포인트**: `/precheck/instant`, `/pipeline/run`, `/regulation/analyze`, `/market-report/*`, `/permits/check`, `/building-compliance/*`, `/environment`, `/expert-panel`, `/avm/vision`, `/digital-twin`, `/presale` 등.

### 병목 (🔴 우선)
1. 🔴 `vworld.merge_parcels_gis_union` PNU별 **순차 N+1** → 수백 필지 수십 초.  **[해결됨 Wave0]**
2. 🟠 `scenario_simulator._block_aging` 건축물대장 필지별 순차.
3. 🟠 `parcel_excel_service` 지오코딩 동시성 5.
4. 🟡 필지 캐시 부재(동일 PNU 반복 호출). **[Wave0 캐시로 해결]**
5. 🟡 다필지 시 LLM 토큰 N배(선택형 분석·과금 게이트 필요).

## 2. 기술 패턴(연구 근거)
- 캐시(필지 정적·TTL장기)·in-flight 디덥·Semaphore 동시성·TokenBucket·지수백오프+지터·서킷브레이커·asyncio.Queue 백프레셔.
- 구역→필지: VWorld bbox/polygon(ST_Intersects 의미) → shapely 필터. (PostGIS 미사용, 런타임 shapely+VWorld.)
- 비동기 잡: 청크+멱등키(job+pnu)+상태기계+부분성(HTTP 207식)+SSE/폴링 진행률+결과 스냅샷.
- UX 베스트프랙티스: 다중선택 3종(폴리곤/반경/행정동)·실행 전 카운트·요금 프리뷰·코로플레스+동기 테이블·결정적 진행률+부분실패 분리·통합개발 후보 자동윤곽·결과 영속/내보내기.
- (웹 출처는 환경 제약으로 [unverified] — 의사결정 전 실확인 권장.)

## 3. 구현 계획 (웨이브 — 반복수렴: 각 웨이브 후 라이브검증→다음)
- **Wave 0 (병목, 완료)**: `get_parcel_by_pnu` 프로세스 캐시 + `merge_parcels_gis_union` 동시성 gather. 전 다필지 경로 즉시 수혜.
- **Wave 1 (공통 컴포넌트)**: `ProjectAddressInput`에 opt-in `multi`/엑셀 prop 추가(기본 single 유지=회귀0). 부지분석·종합분석·수익성·인허가 워크스페이스에 multi 노출.
- **Wave 2 (핵심 엔드포인트 상위호환)**: `/precheck/instant`·`/pipeline/run` 등을 `addresses?: list[str]|address: str` 상위호환으로. 필지별 병렬 + 통합 요약(면적가중).
- **Wave 3 (병목 잔여)**: `_block_aging`·엑셀 지오코딩 gather/동시성 상향 + TokenBucket·백오프.
- **Wave 4 (대량 UX)**: 구역 다필지 선택기(폴리곤/반경/행정동)·코로플레스 등급 레이어·진행률 스택바·통합개발 후보 윤곽·결과 export. F-Parcel 배치 연동.
- **Wave 5 (과금·검증)**: 다필지 선택형 분석·관리자 과금 게이트·신뢰루프 이상치 플래그·원장 영속.

## 4. 검증 (반복수렴 게이트)
각 웨이브: py_compile + 단위/통합 테스트 + 라이브 E2E(실주소 다필지) + 단일경로 회귀0 + 병목 시간측정. 결함→재수정→재검증을 결함 0까지.

## 5. 진행
- [x] 감사·연구·계획
- [x] Wave 0 병목(캐시+gather)
- [ ] Wave 1~5 (순차)
