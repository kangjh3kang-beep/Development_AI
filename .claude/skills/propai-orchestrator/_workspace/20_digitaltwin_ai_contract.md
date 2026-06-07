# 디지털트윈 AI 협업 고도화 + WARN 수정 — 계약

기반: QA 19_qa_digitaltwin.md (조건부 GO). MVP 커밋 백엔드 5542262 / 프론트 5e94e6f 위에 증분.

## A. WARN 수정(배포 전 필수)
### A-1 항공 텍스처 오리진(WARN-1)
- 현재 scene_service가 `aerial.image_proxy_url`을 상대경로 `/api/v1/digital-twin/aerial-image?...` 반환 → Cloudflare 프론트 오리진에서 api.4t8t.net로 안 가 404(레이어 OFF·폴백이라 크래시는 없음).
- 수정: 백엔드가 **절대 API URL** 반환(설정된 공개 API 베이스 사용, 없으면 상대 유지). 동시에 프론트도 방어적으로 `resolveApiOrigin`(lib/api-client)으로 절대화. aerial-image 엔드포인트는 **CORS 허용**(TextureLoader crossOrigin=anonymous 기본) — 이미지 응답에 Access-Control-Allow-Origin. 키는 서버 프록시라 비노출 유지.
### A-2 카메라 size_m(WARN-2)
- terrain.bbox_m에 `size_m`(=half_m*2) 추가. 프론트는 size_m 우선, 없으면 cover_m→200 폴백 유지.

## B. AI 협업 — 가상준공 AI 해설(신규)
원칙: **데이터 그라운딩·할루시네이션 방지.** 실제 씬/컨텍스트 수치만 근거. 가짜 시각콘텐츠 생성 금지. "AI 해석·참고용" 라벨 + 검증배지. 기존 인터프리터 패턴 재사용.

### 백엔드
신규 `app/services/ai/digital_twin_interpreter.py` — 기존 base_interpreter(app/services/ai/base_interpreter.py 또는 avm_interpreter 패턴) 상속/모방. 그라운딩 규칙·캐시·prompt-caching·과금누적 공통기반 재사용.
신규 엔드포인트 `POST /api/v1/digital-twin/interpret` (routers/digital_twin.py에 추가):
- Req: { address?, pnu?, scene?(이미 받은 scene 페이로드 선택), context?{roi?, esg?, permit?, zone_type?, design_summary?} }
- 동작: scene 없으면 build_scene로 핵심 요약 구성 → interpretation_cache(sha256·기존) 조회 → 미스시 DigitalTwinInterpreter 호출(asyncio.wait_for 30s, 실패시 ok:false 메시지) → 캐시저장.
- 입력 그라운딩 요약: 주소·용도지역·필지면적·지형(slope/relief/class)·주변동수·평균높이·건물매스 유무·층수/GFA(가용시)·ROI/ESG/permit(context 제공시).
- Res: { ok, sections: { design_rationale, context_fit, view_sunlight, development_implication, marketing_highlight }, cached, grounding:{used_fields:[...]}, note }
  - 각 섹션 한국어 서술. 데이터 없으면 해당 섹션 "데이터 부족" 명시(추측 금지).
- 라우터: digital_twin 기존 라우터에 추가(prefix /api/v1/digital-twin). 422/ok:false 규칙 동일.

### 프론트
- DigitalTwinScene.tsx(또는 동반 카드 컴포넌트)에 **"가상준공 AI 해설" 카드**: 트윈 로드 후 버튼/온디맨드로 /digital-twin/interpret 호출 → 5섹션 표시. AnalysisVerdict/VerificationBadge 결합 가능. "AI 해석·참고용" 배지 + grounding(사용 데이터) 표기. 로딩/에러/ok:false 처리.
- 항공 url 절대화(resolveApiOrigin), size_m 사용.

## 검증/제약
- 데이터 그라운딩·정직성 비협상. 기존 인터프리터/캐시 재사용(중복금지). scene/terrain 무파괴(증분).
- 백엔드 로컬 .venv: import/라우트, 실주소(역삼동 736) /interpret 라이브 1회(섹션 생성 확인, LLM 키는 루트 .env). 프론트 tsc 0/eslint 0. git add 명시경로만(-A 금지). footer Co-Authored-By: Claude Opus 4.8 (1M context).
- 배포=Micro. 커밋 메시지: 백엔드 `feat(digital-twin): 가상준공 AI 해설 인터프리터 + 항공 절대URL/CORS·size_m 수정`, 프론트 `feat(digital-twin): 가상준공 AI 해설 카드 + 항공 텍스처 오리진 수정`.
