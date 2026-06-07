# Flagship B — 이미지융합 AVM (PoC, API 계약)

원칙: **정직·할루시네이션 방지.** 이미지 취득/cv2 가용 시 영상특징, 불가 시 공간컨텍스트 프록시로 폴백. 융합은 **상한 제한된 실험적 보정**(experimental=true 라벨). 검증된 CNN/MAPE 주장 금지.

라우터 신규: `/api/v1/avm-vision` (apps/api/routers/avm_vision.py + app/services/avm_vision/avm_vision_service.py).

## POST /api/v1/avm-vision/analyze
### Request
{ "address": str|null, "pnu": str|null, "base_value_won": number|null, "base_value_per_sqm_won": number|null }
- base 미제공시 desk_appraisal로 기준값 산출(재사용). pnu/address 모두 없으면 422.

### Response (200)
{
  "ok": true,
  "address": str, "pnu": str|null, "coordinates": {"lat":float,"lon":float}|null,
  "image": { "available": bool, "source": "VWorld-PHOTO"|null, "bbox":[...]|null, "thumbnail_url": str|null },  // 취득시 프론트 표시용(가능범위)
  "features": {
     "source": "image"|"proxy",         // image=cv2 영상분석 / proxy=기존데이터 추론
     "green_ratio": float|null,          // 0~1 식생비율
     "built_ratio": float|null,          // 0~1 건폐/시가화
     "edge_density": float|null,         // 개발강도 프록시
     "road_frontage": "good"|"normal"|"poor"|null,
     "terrain": str|null,                // NED 지세/형상(프록시시)
     "poi_density": float|null,          // 주변 POI 밀도(프록시 가능시)
     "detail": str
  },
  "base_value_won": number|null, "base_value_per_sqm_won": number|null,
  "adjustment_pct": float,               // 상한 제한(예: -8 ~ +8). 근거 없으면 0
  "adjusted_value_won": number|null,
  "confidence": float,                   // 0~1 (image>proxy>none)
  "rationale": str,                      // 보정 근거 서술(어떤 특징이 ±에 기여)
  "experimental": true,                  // 항상 true(실험적)
  "sources": [str],
  "note": str                            // 이미지 미취득/프록시 폴백시 명시
}
### 빈/오류
- 기준값·좌표 모두 불가 → ok:false + message(빈결과 금지).
- 이미지 미취득 → ok:true, image.available=false, features.source="proxy", note 명시.

## 로직(재사용/신규)
1. 좌표/PNU: auto_zoning_service.analyze_by_address 또는 vworld geocode(app/services/external_api/vworld_service.py). PNU 미확인시(=precheck와 동일 정책) 좌표만으로 진행 가능하면 진행, 불가시 ok:false.
2. 기준값: base 미제공시 desk_appraisal(app/services/land_intelligence/desk_appraisal_service.py) 호출.
3. **이미지 취득(신규)**: VWorld 정사영상/항공사진 취득 시도 — VWorld image/WMS getmap(api.vworld.kr, LAYERS/basemap=PHOTO·Satellite, bbox=필지중심±반경, format=png). **라이브로 실제 취득 가능여부 확인**(키 권한 별도승인 필요할 수 있음 — 403/빈응답시 폴백). 취득 성공시 PNG bytes.
4. **특징 추출**:
   - cv2 가용 + 이미지 취득 → HSV 식생 마스크(green_ratio), 그레이/에지(built_ratio·edge_density). features.source="image".
   - 아니면 프록시: 필지 기하(parcel)·NED 토지특성(지세/형상=terrain)·주변 POI/상권(있으면 poi_density)·도로접면(접도). features.source="proxy".
   - cv2 import는 try/except(미설치 graceful).
5. **융합(보정)**: 특징→adjustment_pct(상한 ±8% 권장, 과신 금지). 예: 식생과다(저개발)·접도불량→하향, 시가화·양호접도·POI고밀→상향. confidence=image 0.5~0.7 / proxy 0.3~0.45 / none 0. rationale에 기여 특징 명시. adjusted_value_won = base*(1+adjustment_pct/100).

## 90초/가드
- 외부호출(이미지·desk_appraisal) asyncio.wait_for 가드, 전체 빠르게. 무거운 ML 모델 로드 금지(cv2 기초연산만).

## 프론트(별도 에이전트)
- 패널/섹션: 항공 썸네일(가능시) + 추출 특징 카드 + AVM 보정 전/후(base→adjusted, adjustment_pct) + **실험적(EXPERIMENTAL) 배지** + confidence + note. 예상시세(desk) 화면 또는 신규 섹션에 결합. 토큰색·다크. apiClient v1.
