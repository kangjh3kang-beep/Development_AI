# Flagship A — 90초 AI PreCheck + 조닝 시그널 (API 계약)

라우터 prefix 신규: `/api/v1/precheck` (apps/api/routers/precheck.py 신규, main.py 마운트).
규칙기반 우선(90초 SLA), LLM은 선택적 1줄 요약만(타임아웃시 생략).

## A. 즉시 룰체크 — POST /api/v1/precheck/instant
### Request
{ "address": str, "pnu": str|null, "area_sqm": float|null, "use_llm": bool=false }

### Response (200)
{
  "ok": true,
  "address": str, "pnu": str|null, "zone_type": str, "area_sqm": float|null,
  "legal_limits": { "bcr_pct": float|null, "far_pct": float|null, "height_m": float|null, "source": str },
  "methods": [
    { "code": "M01", "name": str,
      "signal": "pass"|"warn"|"fail",
      "permitted": bool, "complexity": int(1~5), "complexity_label": str,
      "checks": [ { "rule": "용도지역 허용"|"건폐율"|"용적률"|"높이"|"주차"|"일조", "status": "pass"|"warn"|"fail", "detail": str } ],
      "reason": str } ,
    ... (M01~M15 중 해당 용도지역 후보)
  ],
  "summary": { "pass": int, "warn": int, "fail": int, "best": "Mxx", "llm_note": str|null },
  "elapsed_ms": int,
  "sources": [str]
}
### 로직(재사용)
- 주소→PNU→용도지역·면적: app/services/zoning/auto_zoning_service.py (analyze) 또는 land characteristics. routers/auto_zoning.py 패턴.
- 허용 개발방식·복잡도: app/services/feasibility/permit_validator.py — get_permitted_types(zone)/check_permit_feasibility(dev,zone)/DEVELOPMENT_TYPE_NAMES/PERMIT_COMPLEXITY.
- 법정 한도(건폐율/용적률/높이): routers/regulation.py /analyze (정량 한도 법정/조례) 재사용 — 반환 구조 확인 후 매핑.
- signal 산정: 용도지역 불허→fail. 허용+복잡도≤3→pass. 허용+복잡도4~5(심의)→warn. 정량룰(면적 있으면 건폐/용적 개략 검토; 없으면 해당 check status=warn "면적 미입력").
- 90초 SLA: 전부 규칙기반(외부 API 1~2회). use_llm=true면 summary.llm_note만 1회 LLM(asyncio.wait_for 25s, 실패시 null).

## B. 조닝 시그널(기회필지) — POST /api/v1/precheck/zoning-signals
### Request
{ "address": str|null, "pnu": str|null, "radius_m": int=300 }
### Response (200)
{ "ok": true, "target": {"pnu":str,"zone_type":str,"address":str},
  "signals": [
    { "type": "통합개발후보"|"용도상향기회"|"역세권개발"|"저밀재건축",
      "score": float(0~100), "level":"high"|"mid"|"low",
      "parcels": [ {"pnu":str,"zone_type":str,"adjacent":bool} ],
      "rationale": str } ],
  "geojson": {...}|null,  // parcel-boundaries 재사용 가능시
  "sources":[str] }
### 로직(재사용)
- 주변 필지/구획: routers/auto_zoning.py /parcel-boundaries, /nearby-map.
- 인접성: shapely 연결요소(개발방식 시뮬레이터 adjacency 패턴, app/services/.../development_methods 또는 dev_scenario). 인접 필지 동일/유사 용도→통합개발후보.
- 용도상향: 대상이 역세권/준주거/상업 인접→용도상향기회. 역세권 키워드→역세권개발.
- 데이터 부족(주변 필지 0)→signals=[] + ok:true + note.

## 빈/오류 경로
- 용도지역 미확인→ ok:false, message(빈 결과 금지).
- pnu/address 모두 없음→ 422.

## 프론트(frontend-dev)
- 신규 페이지/패널: 90초 AI PreCheck.
  - 입력: 주소(+선택 면적). 실행 버튼.
  - 결과: 개발방식 **신호등 그리드**(카드별 pass=초록/warn=주황/fail=빨강, 코드·이름·복잡도·사유·체크리스트). 상단 요약(pass/warn/fail 카운트·best·소요시간).
  - 조닝 시그널: 지도(Leaflet, 기존 NearbyTransactionsMap/ParcelBoundaryMap 패턴) + 시그널 카드 리스트(타입·점수·근거·필지).
  - 디자인 토큰 사용(하드코딩 hex 금지), 다크 기본, i18n 키(가능 범위), 검증 배지 결합 가능시.
  - apiClient(lib/api-client.ts) v1 경로 사용. 사이드바 진입점 추가(설계/인허가 그룹 적절 위치).
- 데이터흐름: 가능하면 useProjectContextStore에 precheck 결과 저장(프로젝트 컨텍스트 승계). 과설계 금지.
