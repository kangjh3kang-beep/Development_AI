# 21 — 디지털트윈 AI 협업 고도화 + WARN 수정(백엔드)

계약: 20_digitaltwin_ai_contract.md. 커밋 `1b2cb2e`. SSH배포·push 미수행(로컬 구현+검증+커밋만).

## 1. 변경/신규 파일·엔드포인트
| 파일 | 종류 | 내용 |
|------|------|------|
| `propai-platform/apps/api/app/services/ai/digital_twin_interpreter.py` | 신규 | `DigitalTwinInterpreter(BaseInterpreter)` — 5섹션 해설 |
| `propai-platform/apps/api/routers/digital_twin.py` | 수정 | `POST /api/v1/digital-twin/interpret` 추가 + aerial-image CORS 헤더 |
| `propai-platform/apps/api/app/services/digital_twin/scene_service.py` | 수정 | `_aerial_proxy_url` 절대URL화(PUBLIC_API_BASE) |
| `propai-platform/apps/api/app/services/terrain/terrain_service.py` | 수정 | `bbox_m.size_m`(=half_m*2) 증분 |
| `propai-platform/apps/api/app/core/config.py` | 수정 | `PUBLIC_API_BASE` 설정 추가(기본 "") |

엔드포인트: `POST /api/v1/digital-twin/interpret`, `POST /scene`(기존), `GET /aerial-image`(기존+CORS).

## 2. A-1 / A-2 수정
- **A-1 항공 절대URL**: `config.PUBLIC_API_BASE`(예 `https://api.4t8t.net`) 설정 시 `_aerial_proxy_url`이 `{base}/api/v1/digital-twin/aerial-image?...` 절대URL 반환, 미설정이면 상대경로 유지(프론트 resolveApiOrigin 방어). 키는 서버 프록시라 비노출.
- **A-1 CORS**: `GET /aerial-image` 응답(PNG)에 `Access-Control-Allow-Origin: *` + `Cross-Origin-Resource-Policy: cross-origin` 추가 → Three.js TextureLoader `crossOrigin=anonymous` 대응. 기존 `Cache-Control` 유지.
- **A-2 size_m**: `terrain.bbox_m`에 `size_m`(=half_m*2, 예 300.0) 추가. 기존 키(x_min/x_max/z_min/z_max/half_m) 무파괴 증분. 검증: `{'half_m':150.0,'size_m':300.0,...}`.

## 3. AI 인터프리터 — 섹션·그라운딩·캐시 재사용
- **상속**: `BaseInterpreter` 그대로 상속 → 그라운딩 규칙 자동주입·prompt-caching·과금누적·L1/L2 캐시·키 정상화 전부 공통기반 재사용(중복구현 0). max_tokens=3072.
- **5섹션**: `design_rationale`, `context_fit`, `view_sunlight`, `development_implication`, `marketing_highlight`. 시스템 프롬프트에 "데이터 없으면 데이터 부족 명시·추측 금지", "매스=AI 절차생성·표고=SRTM 30m" 전제 명문화.
- **그라운딩 입력**: 라우터 `_summarize_scene`이 씬→요약(주소·pnu·terrain slope/relief/class·neighbor_count·neighbor_avg_height_m·has_building_mass) + context(roi/esg/permit/zone_type/design_summary). `used_fields`로 사용 데이터 정직 표기.
- **캐시**: 기존 `app.services.ai.interpretation_cache`(sha256 `cache_key("digital_twin", data)` / `get_cached` / `put_cached`) 재사용. interpretation_cache 테이블 idempotent DDL. 미스시 `DigitalTwinInterpreter` 호출(asyncio.wait_for 30s, 실패→ok:false), ok면 저장.
- **가드**: 엔드포인트 전체 build_scene 90초, 인터프리터 30초. address/pnu/scene 전부 없으면 422.
- **응답**: `{ok, sections{5}, cached, grounding:{used_fields:[...]}, note:"AI 해석·참고용..."}`. 실패시 sections{} + message.

## 4. 라이브 결과(역삼동 736, 루트=propai-platform/.env)
- **ok=True**, 5섹션 전부 생성. grounding.used_fields=`['address','pnu','terrain(slope/relief/class)','neighbors','building_mass']`.
- **그라운딩 정직성 확인**: terrain 실측값 인용(기복 61.0m·표고 52.0m), 주변 60동·평균 9.0m. 건물매스·용도지역·ROI 미제공 항목은 `design_rationale`/`development_implication`에서 "데이터 부족" 명시(추측 0). 할루시네이션 없음.
- **캐시**: 동일 scene 2회 호출 → R1 cached=False, R2 cached=True(적중). 422 가드 작동(locator/scene 전무 시 HTTPException 422).
- **A-1/A-2**: 절대URL/상대URL 분기·CORS 헤더·size_m=300.0 전부 확인.
- 주의: LLM 키는 `os.environ`에서 읽으므로 로컬 실행 시 `set -a; . ./.env` 필요(pydantic settings env_file는 settings 객체만 채움). 운영 컨테이너는 env 주입되어 무관.

## 5. 커밋 해시
`1b2cb2e` — `feat(digital-twin): 가상준공 AI 해설 인터프리터 + 항공 절대URL/CORS·size_m 수정` (5 files, +307/-2). footer: Co-Authored-By: Claude Opus 4.8 (1M context).

## 6. 프론트/QA 정합사항
- 프론트는 `terrain.bbox_m.size_m` 우선 사용, 없으면 cover_m→200 폴백.
- aerial `image_proxy_url`: 운영에서 `PUBLIC_API_BASE` 설정 시 절대URL로 옴(프론트 resolveApiOrigin은 이미 절대면 그대로). TextureLoader `crossOrigin='anonymous'` 사용 가능(CORS 허용됨).
- 신규 카드: `POST /api/v1/digital-twin/interpret` 호출 → `{ok, sections{design_rationale,context_fit,view_sunlight,development_implication,marketing_highlight}, cached, grounding.used_fields, note}`. ok:false/message·로딩·에러 처리, "AI 해석·참고용" 배지 + grounding 표기.
- 요청 바디: `{address?, pnu?, scene?, context?{roi,esg,permit,zone_type,design_summary}}`. scene 재사용 시 build_scene 응답을 그대로 scene에 전달하면 LLM만 호출(왕복 절감). 셋 다 없으면 422.
- 배포 시 운영 env에 `PUBLIC_API_BASE=https://api.4t8t.net` 설정 권장(미설정이면 상대경로 유지·프론트 절대화 의존).
