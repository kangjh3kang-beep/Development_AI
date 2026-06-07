# 07 — Flagship A 백엔드 구현 보고 (90초 AI PreCheck + 조닝 시그널)

커밋: `f446bc6` feat(precheck): 90초 AI PreCheck 즉시 룰체크 + 조닝 시그널 백엔드
(주의: 동일 커밋에 frontend-dev의 사전 스테이징 파일 4종이 함께 포함됨 — 백엔드 변경은 아래 4파일)

## 1. 신규/변경 파일 · 엔드포인트 · 마운트
신규:
- `apps/api/routers/precheck.py` — 얇은 라우터(스키마 + 위임)
- `apps/api/app/services/precheck/precheck_service.py` — 로직 본체
- `apps/api/app/services/precheck/__init__.py`
변경:
- `apps/api/main.py:80` import에 `precheck` 추가, `main.py:402` 마운트
  `app.include_router(precheck.router, prefix="/api/v1/precheck", tags=["AI PreCheck"])` (auto_zoning 직후)

엔드포인트(풀경로):
- `POST /api/v1/precheck/instant`
- `POST /api/v1/precheck/zoning-signals`

## 2. 재사용 함수(파일:라인) 및 매핑 근거
- `app/services/feasibility/permit_validator.py`
  - `get_permitted_types(zone)`(:54), `PERMIT_COMPLEXITY`(:28), `get_permit_complexity`(:67),
    `DEVELOPMENT_TYPE_NAMES`(:46) → 용도지역 허용 여부·복잡도·신호 산정.
- `app/services/zoning/auto_zoning_service.py`
  - `AutoZoningService.analyze_by_address`(:38) → 주소→PNU→용도지역·면적·좌표(외부 1회).
  - `ZONE_LIMITS`(:12) → **legal_limits** 매핑(국토계획법 제78조). 계약 bcr_pct/far_pct/height_m/source ←
    `max_bcr`/`max_far`/`max_height_m`/법적근거 문자열.
- `app/services/external_api/vworld_service.py`
  - `geocode_address`(:70) 좌표 폴백, `get_parcels_in_bbox`(:210) 반경 bbox 주변 필지(연속지적도).
- `routers/auto_zoning.py`
  - `_parcel_adjacency(geoms)`(:264, shapely 연결요소) → 통합개발 인접성(contiguous) 판정 재사용.

> legal_limits는 RegulationAnalysisService(무거운 collect_comprehensive 경로) 대신 ZONE_LIMITS 직매핑.
> 90초 SLA·외부호출 최소화를 위해 AutoZoning 단일 경로 채택(계약 31행 "면적 있으면 개략 검토" 충족).

## 3. signal 로직(계약 준수)
- 용도지역 불허 → `fail` (정량 검토 생략).
- 허용 + 복잡도 ≤3 → `pass`.
- 허용 + 복잡도 4~5(심의/조합) → `warn`.
- 면적 있으면 건폐율·용적률 개략 check(법정한도×면적 안내), 없으면 해당 check `warn`("면적 미입력").
- 주차·일조: 배치설계 전 단계라 정보성 `warn`(데이터 없음).
- 후보군: 허용 코드 우선, 전부 불허(녹지 등)면 대표 4종을 fail로 노출(변별).
- 정렬: pass 우선 + 복잡도 오름차순. best = 1순위(fail 아닐 때).

## 4. 로컬 검증 로그 요약(.venv)
- py_compile: OK
- import + 라우트: `['/instant','/zoning-signals']` (POST) 등록 확인.
- 단위호출(더미 '제3종일반주거지역'): legal_limits bcr50/far300, permitted 10종,
  M06 pass·M01 warn(cx5)·M10 pass·M03 fail(불허). 1종전용에서 M06 fail 확인.
- E2E run_instant_precheck('서울 강남구 역삼동 123', area 600):
  ok=true, zone=일반상업지역(키워드 폴백, VWorld 더미키), pass7/warn1/fail0, best M06, **elapsed 173ms**.
- zoning-signals: 좌표 미확보(더미키)→ ok:true + signals=[] + note(빈 결과 금지 충족).
- _derive_signals 단위: 제2종+인접→통합개발65/용도상향60/저밀재건축55, 준주거+비인접→역세권70/통합40.
- 422 검증: ZoningSignalsRequest(address·pnu 모두 없음)→ValidationError(FastAPI 422). pnu-only 통과.
- main.app 마운트 확인: `/api/v1/precheck/instant`, `/api/v1/precheck/zoning-signals`.
- ruff --select F,E9,B: All checks passed(잔여는 style UP045 Optional→X|None, 코드베이스 미강제).

## 5. 프론트/QA 확정사항(계약 대비)
계약 스키마 **그대로 준수**. 추가/명확화 포인트:
- `/instant` 오류 응답에도 `elapsed_ms`, `sources` 포함(ok:false 케이스).
- `/zoning-signals` 정상이나 데이터 부족 시: `ok:true` + `signals:[]` + `note:str`(+ `geojson:null`).
  좌표 미확보 시에도 동일 note 경로(VWorld 키 없을 때 흔함).
- `/zoning-signals` 응답에 `adjacency`(contiguous/components/note) 추가 동봉(지도 보조용, 계약 외 부가).
- `geojson`은 주변 필지 FeatureCollection(properties: pnu, jimok). 대상 필지 용도지역을 주변 parcel zone_type에
  가정 주입(연속지적도는 지목만 제공) — 프론트 표기 시 "추정" 라벨 권장.
- signals[].parcels는 최대 12개로 절단.
- VWorld 운영키 설정 시 zoning-signals 실데이터 활성화(현재 더미키라 note 경로).
- LLM note: use_llm=true & ANTHROPIC_API_KEY 있을 때만 summary.llm_note 채움, 그 외 null.
