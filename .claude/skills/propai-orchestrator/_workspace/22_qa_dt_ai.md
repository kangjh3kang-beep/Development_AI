# QA 교차검증 보고 — 디지털트윈 AI 해설 + 항공 오리진/size_m 수정 증분

- 대상: 백엔드 `1b2cb2e`, 프론트 `101e049` (MVP 5542262/5e94e6f 위 증분)
- 계약: `20_digitaltwin_ai_contract.md` / 직전 QA: `19_qa_digitaltwin.md`(WARN-1 항공, WARN-2 size_m)
- 방식: 읽기 전용 교차검증 + tsc 직접 실행(exit 0) + Python AST 파싱. 코드 수정/배포/push 없음.

## 종합 판정: **GO**

치명(FAIL) 없음. 직전 QA의 WARN-1(항공 split-origin)·WARN-2(size_m) 모두 해소. AI 인터프리터는 계약·정직성 가드·재사용 원칙 충족. tsc 0 / Python 파싱 OK / 재사용 API 시그니처 정합 / 무파괴 증분.

단, 항공 텍스처 프로덕션 동작은 **운영 조건부**(아래 1항 참조): 절대화·CORS·폴백은 코드상 완비되었으나, 실제 로드 성공은 (a) 백엔드 `PUBLIC_API_BASE` 설정 또는 프론트 `resolveApiOrigin` 정상 + (b) 항공 원본(VWorld PHOTO) 가용에 의존. 코드 레벨에서는 WARN-1 해소 확정, 라이브 1회 토글 확인만 배포 후 권고.

---

## 항목별 판정표

| # | 항목 | 판정 | 근거(file:line) |
|---|------|------|----------------|
| 1 | WARN-1 해소(항공 절대URL/CORS/폴백) | **PASS** | 백엔드 절대화+CORS, 프론트 absolutize+회색폴백 모두 확인 |
| 2 | WARN-2 해소(size_m) | **PASS** | bbox_m.size_m 추가(무파괴), 프론트 camSpan 폴백체인 |
| 3 | AI 인터프리터 계약(응답↔types) | **PASS** | 5섹션·grounding·cached·note·message 정합 |
| 4 | 할루시네이션 방지(그라운딩) | **PASS** | 실수치만 근거·"데이터 부족" 규칙·used_fields·context 키 일치 |
| 5 | 재사용/중복 아님 | **PASS** | BaseInterpreter·interpretation_cache 시그니처 정합 |
| 6 | 엣지/가드 | **PASS** | 422·ok:false·wait_for·캐시·resolveApiOrigin export 무파괴 |
| 7 | 회귀/품질 | **PASS** | scene/terrain/MVP/라우터 무파괴·tsc0·apiClient 보존 |

---

## 1. WARN-1 해소 — 항공 텍스처 프로덕션 split-origin (PASS)

직전 WARN-1 핵심: `aerial.image_proxy_url`이 상대경로 → 프론트 오리진(Cloudflare) 기준 해석 → api.4t8t.net 미도달 404. 4중 방어로 해소:

1. **백엔드 절대화**: `scene_service.py:84-98` `_aerial_proxy_url`이 `settings.PUBLIC_API_BASE` 설정 시 `{base}{path}` 절대 URL 반환, 미설정 시 상대 유지(폴백). `config.py:71` `PUBLIC_API_BASE: str = ""` 기본 안전(미설정=상대=프론트 절대화에 위임). settings import 실패 시 except로 상대 폴백(`scene_service.py:93-95`).
2. **프론트 방어적 절대화**: `DigitalTwinScene.tsx:35-40` `absolutizeAerialUrl` — 이미 `^https?://`면 그대로, `/`로 시작하면 `resolveApiOrigin()+url`. `TerrainMesh`가 `AerialMaterial`에 넘기기 전 적용(`:129`). 백엔드가 상대를 주든 절대를 주든 둘 다 api 오리진으로 향함.
3. **CORS(이미지 응답)**: `routers/digital_twin.py:358-362` `/aerial-image` 응답에 `Access-Control-Allow-Origin: *` + `Cross-Origin-Resource-Policy: cross-origin` 추가. TextureLoader는 apiClient를 안 거치므로 CORSMiddleware(Authorization 등 자격증명 경로)와 별개로 이미지 자체에 CORS 헤더 필요 — 정확히 해결. `*`라도 키 비노출(서버가 VWorld 대리, 프록시 URL에 키 없음).
4. **crossOrigin + 폴백**: `AerialMaterial`(`DigitalTwinScene.tsx:140-171`)이 `useLoader`(Suspense throw) → 명령형 `TextureLoader.load`로 교체. `loader.setCrossOrigin("anonymous")`(`:151`), 성공 시 `setTexture`, **실패 콜백에서 무시 → 회색 머티리얼(`#1e293b`) 유지**(`:166-169`). 텍스처 null이면 회색 반환(`:166`). useLoader Suspense throw 제거로 **ErrorBoundary 크래시 경로 자체가 사라짐** — 404/CORS 실패가 컴포넌트를 깨지 않음.

키 비노출: 프록시 URL 쿼리는 lat/lon/zoom만(`scene_service.py:90`), VWorld 키는 서버 라우터 내부 사용 → 유지.

**프로덕션 split-origin 동작**: 코드상 해소 확정. 실로드는 `PUBLIC_API_BASE` 또는 프론트 `resolveApiOrigin`(env/호스트 기반 → `https://api.4t8t.net`)이 올바른 오리진을 내면 성공. 실패해도 회색 폴백으로 무크래시. → WARN→PASS.

## 2. WARN-2 해소 — 카메라 size_m (PASS)

- 백엔드: `terrain_service.py:458` `bbox_m`에 `"size_m": round(half_m*2.0, 1)` 추가. 기존 키(x_min/x_max/z_min/z_max/half_m) 무변경 → 무파괴.
- 프론트: `DigitalTwinScene.tsx:441` `camSpan = payload?.terrain?.bbox_m?.size_m ?? payload?.aerial?.cover_m ?? 200` — size_m 우선→cover_m→200 폴백체인. 카메라 position 3축이 camSpan 사용(`:513-516`). 직전 QA의 "size_m 영원히 미사용" 해소.
- types: `types.ts:19-23` `DigitalTwinBbox{ size_m?:number; [key:string]:number|undefined }` 신규, `terrain.bbox_m` 타입 교체(`:32`). 인덱스시그니처로 기존 키 접근 무파괴.

## 3. AI 인터프리터 계약 정합 (PASS)

응답 형태(`routers/digital_twin.py` interpret_digital_twin):
- 성공: `{ok:true, sections:{5키}, cached, grounding:{used_fields}, note}` (`:312-319` 캐시히트 / `:336-343` 신규생성).
- 실패: `ok:false`, `sections:{}`, `message` 동봉(`:286-294` 씬실패 / `:341-342` LLM실패).
- 5섹션 키: design_rationale/context_fit/view_sunlight/development_implication/marketing_highlight — 인터프리터 `expected_keys`(`digital_twin_interpreter.py:73-79`)·USER_PROMPT(`:48-56`)·types(`types.ts:83-89`)·프론트 SECTION_LABELS(`DigitalTwinAiCard.tsx:30-36`) 4곳 모두 일치.
- types `DigitalTwinInterpretResponse`(`types.ts:92-99`): ok/sections?/cached?/grounding?{used_fields}/note?/message? — 백엔드 응답과 정합.
- 프론트 렌더: 5섹션은 `AnalysisVerdict`에 `sectionLabels`로 위임(`DigitalTwinAiCard.tsx:160-168`), grounding 칩(`:142-156`), "AI 해석·참고용" 배지(`:108-110`), 캐시 배지(`:112-116`). AnalysisVerdict props(analysisType/context/interpretation/sectionLabels/interpretationTitle/defaultOpen/autoRunVerification) 시그니처 일치(AnalysisVerdict.tsx:50-57).

## 4. 할루시네이션 방지 (PASS)

- 시스템 프롬프트 출력규칙(`digital_twin_interpreter.py:42-46`): 제공 수치만 인용, 없으면 "데이터 부족" 명시·추측 금지, 매스=AI절차생성·표고=SRTM30m 전제, JSON only.
- `_extract_compact_data`(`:106-135`): 값이 None이 아닌 키만 compact에 포함 → LLM에 빈값 미전달(없는 데이터 환각 차단).
- `_summarize_scene`(`routers/digital_twin.py:207-258`): 실제 scene 필드(address/pnu/terrain slope·relief·class/neighbor_count·avg_height/building_mass)만 추출하며 추출 즉시 used_fields 누적 → **grounding.used_fields가 실제 사용 데이터와 1:1**. building_mass는 항상 bool 산출·추가(`:243-245`)로 used_fields에 상시 포함(정직).
- context 키 일치: 백엔드 수용 키 roi/esg/permit/zone_type/design_summary(`DigitalTwinInterpretContext` `:192-198`, `_extract_compact_data:128`) ↔ 프론트 생성 ctx 키 roi/esg/zone_type/design_summary(`DigitalTwinAiCard.tsx:62-77`). 프론트는 store 값 존재 시에만 주입(없으면 생략=과설계 금지). 스토어 필드명(profitRatePct/totalCarbonPerSqm/zoneCode/buildingType/totalGfaSqm/floorCount/bcr/far) 모두 useProjectContextStore 정의와 일치.
- 데이터 미확보 시: 씬 빌드 실패→`ok:false`+"데이터 미확보 시 해석 생성 안 함" note(`:286-294`). LLM 실패→빈 dict→`ok:false`(`:340-342`). 가짜 생성 없음.

## 5. 재사용/중복 아님 (PASS)

- `DigitalTwinInterpreter(BaseInterpreter)` 상속(`digital_twin_interpreter.py:60`). `generate_interpretation`이 `self._invoke(user_prompt, cache_data=compact, evidence_data=data)` 호출(`:99`) — BaseInterpreter `_invoke(self, user_prompt, *, cache_data=None, evidence_data=None)`(base_interpreter.py:234-239) 시그니처 정확 일치.
- `_evidence` 오버라이드로 `_regional_benchmark` 재사용(`:101-103`), expected_keys/fallback_key/max_tokens(3072)/system_prompt 클래스속성 패턴 = 기존 인터프리터 동일.
- 캐시: 라우터가 `interpretation_cache.cache_key/get_cached/put_cached` 재사용(`routers/digital_twin.py:301-339`). 함수 시그니처 `cache_key(stage, data)`/`get_cached(key)`/`put_cached(key, stage, sections)` 모두 정의와 일치(interpretation_cache.py:25/30/46). 중복 캐시 구현 없음. (BaseInterpreter 내부 _invoke도 자체 캐시가 있으나 라우터 레벨 캐시는 used_fields/note 래핑 응답 단위 캐시 — 이중캐시 무해, ok 검증 후에만 put.)

## 6. 엣지/가드 (PASS)

- 422: address/pnu/scene 전무 시 `HTTPException(422)`(`routers/digital_twin.py:277-280`).
- ok:false: 씬 빌드 실패(`:286-294`), LLM 빈 응답(`:340`).
- wait_for: build_scene 90s(`:271-275`), 인터프리터 30s(`:329-334`) — 계약(인터프리터 30s) 준수. build_scene 90s는 MVP /scene 가드(88s)와 정합.
- 캐시 적중: get_cached 히트 시 `cached:true` 즉시 반환(`:303-319`).
- resolveApiOrigin export: `api-client.ts:31` `export function`로 1줄 변경. 기존 내부 호출(`:47, :88, :291`)은 동일 함수 그대로 → 무파괴. 외부 신규 사용은 DigitalTwinScene 한 곳(`:37`).
- 프론트 요청 타임아웃 60000ms(`DigitalTwinAiCard.tsx:91`) — 백엔드 30s+오버헤드 수용. busy/err/ok:false 모두 UI 분기 처리(`:118-178`).

## 7. 회귀/품질 (PASS)

- scene_service: `_aerial_proxy_url`만 절대화 분기 추가(기존 상대 동작은 PUBLIC_API_BASE 미설정 시 보존), 그 외 무변경.
- terrain_service: bbox_m에 size_m 1키 추가만(기존 키·verts/indices/elev0 무변경).
- digital_twin 라우터: 기존 IoT 4라우트 + /scene + /aerial-image 무파괴. /interpret 신규 추가, /aerial-image는 헤더 2개만 추가(content/media_type 무변경).
- config: PUBLIC_API_BASE 기본 "" 안전(미설정 시 기존 상대 동작 유지).
- main.py 마운트: 기존 prefix `/api/v1/digital-twin` 유지 → /interpret 풀패스 정상(신규 라우트 자동 포함).
- tsc: **exit 0, error TS 0건**(직접 `npx tsc --noEmit` 실행). 
- Python AST: 5개 변경파일 전부 파싱 OK.
- apiClient import 보존: `DigitalTwinScene.tsx:19` `import { apiClient, resolveApiOrigin }`, `DigitalTwinAiCard.tsx:14` `import { apiClient }` 존재.
- CORS(JSON /interpret): apiClient.post(fetch+Authorization)는 CORSMiddleware(`middleware.py:100-106`, allow_methods에 POST·allow_headers에 Content-Type/Authorization) 경유 — 기존 /scene과 동일 경로라 신규 위험 없음. 프론트 도메인이 `CORS_ORIGINS` env에 등재돼 있어야 함(기존 운영 전제, 본 증분이 바꾸지 않음).

---

## FAIL/WARN 요약

- FAIL: 없음.
- WARN: 없음(직전 WARN-1·WARN-2 모두 해소).
- 운영 메모(비차단): ① 항공 실로드 최적화를 위해 백엔드 `PUBLIC_API_BASE=https://api.4t8t.net` 설정 권고(미설정 시 프론트 resolveApiOrigin 폴백으로도 동작). ② 배포 후 디지털트윈 진입→항공 레이어 토글 1회 라이브 확인(텍스처 로드 또는 회색 폴백 무크래시), /interpret 실주소(역삼동 736) 1회 호출로 5섹션·used_fields 생성 확인. ③ `Access-Control-Allow-Origin: *`는 항공 이미지(키 비노출)에만 적용돼 보안 무영향.

## 검증 산출물
- tsc: exit 0, error TS 0건.
- Python AST: digital_twin_interpreter / scene_service / terrain_service / digital_twin(router) / config 파싱 OK.
- 재사용 시그니처: BaseInterpreter._invoke(cache_data/evidence_data) / interpretation_cache(cache_key/get_cached/put_cached) 정합 확인.
- 계약 5섹션 키: 인터프리터·프롬프트·types·프론트 라벨 4곳 일치.
- 라이브 /interpret 1회·항공 토글은 서버/키 의존으로 배포 후 1회 확인 권고(읽기검증 범위 밖).
