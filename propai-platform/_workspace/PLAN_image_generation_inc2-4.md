# PLAN: 이미지 생성 모델 화면 배선 (INC2~4) — 통합자 인계

작성: feat-tmp 세션 / 2026-06-28. 대상: 통합자(integrator) — 단계별 머지·배포·라이브검증.
요청 출처: 사용자 "제미나이 나노바나나 + ChatGPT 이미지를 쓸 수 있게 해줘" → 기반(INC1) 라이브 완료, 화면 노출(INC2~4) 잔여.

---

## 0. 현재 상태 (DONE — INC1 라이브, main 973a46ce)

- **공용 프로바이더 `app/services/ai/image_provider.py`** (배포·검증됨):
  - `async generate_image(provider, prompt, *, model=None, size="1024x1024", n=1, input_image_b64=None, timeout=120.0, **kwargs)` → `{"provider","model","images":[<b64>],"image_urls":[<url>],"mime"}`.
  - 프로바이더: `openai`(gpt-image-1)·`google`(Gemini 이미지="나노바나나", google-genai)·`replicate`.
  - 키+SDK패키지 가드 `get_available_image_providers()`(반쪽출하 방지), 모델 env 오버라이드(`OPENAI_IMAGE_MODEL`/`GEMINI_IMAGE_MODEL`/`REPLICATE_IMAGE_VERSION`).
  - 무목업: 미설정/SDK부재/API오류/빈응답 → `ImageGenerationError(error_type=...)` (가짜 이미지 0).
  - 반환 통일계약: openai/google은 `images`(base64) 채움·`image_urls`=[]; replicate는 `image_urls`(URL)·`images`=[]. **소비처는 `images` 우선, 없으면 `image_urls`.**
- **진단 `GET /api/v1/admin/secrets/image-health?provider=openai|google`** (super_admin) — 실제 1회 생성으로 모델 ID 라이브 확정.
- **라이브 검증 완료**: openai `gpt-image-1` ok:true/generated:1, google `gemini-2.5-flash-image` ok:true/generated:1. GOOGLE_API_KEY·OPENAI_API_KEY 모두 라이브. (env 모델 오버라이드 불요 — 기본값이 동작)
- 의존성: `google-genai==1.2.0`(requirements.txt+requirements.oracle.txt 양쪽). ★1.3.0+는 httpx>=0.28.1 요구로 openai/qdrant의 httpx==0.27.2와 ResolutionImpossible → 1.2.0 핀.

---

## 목표 (INC2~4)
포토리얼 렌더·평면도·조감도/투시도 화면에서 사용자가 **프로바이더/모델(gpt-image·Gemini 나노바나나·Replicate)을 선택**해 이미지를 생성. 무목업·정직강등·과금게이트·라이브검증 준수.

## 아키텍처 결정 (난립 방지)
1. **단일 진입 확장**: 기존 `POST /api/v1/design/{project_id}/render-photoreal`을 프로바이더 선택형으로 확장(신규 엔드포인트 최소화). `photoreal_render_service`가 `image_provider`로 라우팅.
2. **가용 프로바이더 노출 엔드포인트 신설**: `GET /api/v1/design/image-providers` → `get_available_image_providers()`. 프론트 드롭다운이 **라이브 가용분만** 표시(UI에서도 반쪽출하 방지 — 키/패키지 없는 프로바이더는 옵션에 안 뜸).
3. **반환 계약 일원화**: 프론트는 `images`(base64) 우선, 없으면 `image_urls`(replicate URL).

---

## INC2 — 백엔드: render-photoreal 프로바이더 선택형 + 가용목록 엔드포인트

### 변경 파일
**A. `app/routers/design_v61.py`**
- `PhotorealRenderRequest`(현 105행: image_base64/style/strength)에 필드 추가:
  ```python
  provider: str | None = None   # None=서버 기본(replicate 유지·후방호환). "openai"|"google"|"replicate"
  model: str | None = None      # None=프로바이더 기본(resolve_model)
  ```
- `render_photoreal`(1179행)에서 `photoreal_render_service.render_photoreal(req.image_base64, style=req.style, strength=req.strength, provider=req.provider, model=req.model)` 전달.
- **신규 엔드포인트** (같은 라우터, 인증 불요 또는 optional):
  ```python
  @router.get("/image-providers")
  async def list_image_providers():
      from app.services.ai.image_provider import get_available_image_providers
      return {"providers": get_available_image_providers()}
  ```
  - 주의: design_v61 라우터 prefix 확인(현재 `/design` 계열). 경로 충돌 없게 `/design/image-providers` 또는 별도. (drawing 라우터에 둬도 무방 — 프론트가 부르기 쉬운 곳)

**B. `app/services/drawing/photoreal_render_service.py`** (`render_photoreal` 시그니처 확장)
- 현재: REPLICATE REST(ControlNet)만, 키 없으면 status="no_key", 실패 status="error", 성공 status="ok"+image_url. **이 정직계약 유지.**
- 변경: `provider`(기본 None=replicate 기존경로 유지·**후방호환**) 분기 추가.
  - `provider in ("openai","google")` → `image_provider.generate_image(provider, prompt=_style_prompt(style), model=model, input_image_b64=image_base64, size=..., timeout=...)` 호출(img2img: 3D 캡처를 input으로 구조 보존).
    - 성공: openai/google은 base64 반환 → `{"status":"ok","image_base64": images[0]}` (또는 data URI). ★기존은 image_url만 줬으나 base64도 허용(프론트 INC4가 양쪽 처리). 
    - 실패(ImageGenerationError): error_type별 status 매핑 — `key_not_configured`/`package_missing`→"no_key", 그 외→"error"+사유. **가짜 이미지 금지.**
  - `provider in (None,"replicate")` → 기존 REST 경로 그대로(회귀 0).
- 프롬프트: 기존 `_style_prompt(style)`(주간/야간/실사) 재사용 + 건물 외관/맥락 보강. img2img라 구조는 입력이미지가 보존.

### 과금
- `billing_service.charge_service(db, user.id, "photoreal_render")` 기존 코드 유지(프로바이더 무관 동일 요율). 성공시에만 과금(기존 로직). 
- (선택·후속) 프로바이더별 요율 차등이 필요하면 billing config에 `photoreal_render_openai`/`_google` 코드 추가(관리자 설정 기반·미설정 무료 정책 준수). INC2 기본은 단일 코드.

### 테스트 (`tests/`)
- render_photoreal 서비스: provider="openai"/"google" 분기가 image_provider.generate_image를 호출하고, ImageGenerationError→status 매핑(monkeypatch로 generate_image stub), provider=None이면 기존 replicate 경로(회귀). 
- list_image_providers 엔드포인트: get_available_image_providers monkeypatch → providers 반환.

### 게이트
ruff(신규/변경 클린)·py_compile·pytest → code-reviewer ≥9.5 → PR → 통합자 머지 → 백엔드 deploy.sh → 라이브검증(아래).

---

## INC3 — 조감도/투시도 (viewport2img + text2img)

**중요 사실**: 프론트 3D에 **조감도(aerial)·투시도(perspective) 카메라 프리셋이 이미 존재**(CadBimIntegrationPanel `CAM_PRESETS` 317–348행, 좌상단 프리셋 바 1245–1273행). 즉 "신규 시점"은 불필요 — 그 시점에서 3D 뷰포트를 캡처해 INC2의 render-photoreal(provider 선택)로 보내면 **조감도/투시도 포토리얼**이 곧바로 됨.

따라서 INC3 = 두 갈래:
1. **viewport2img(주 경로)**: INC4에서 "조감도/투시도 프리셋으로 카메라 이동 → 캡처 → render-photoreal(provider=gpt-image|gemini)" 흐름을 버튼화. **백엔드 신규 없음**(INC2로 충분).
2. **text2img(신규·옵션)**: 3D가 아직 없거나 컨셉 이미지가 필요할 때, 부지/건물 설명 텍스트만으로 조감도/투시도 생성.
   - 신규 `POST /api/v1/design/{project_id}/render-concept` (또는 render-photoreal에 image_base64 optional化):
     ```python
     class ConceptRenderRequest(BaseModel):
         prompt: str            # "5층 공동주택, 벽돌 외관, 가로변, 조감도" 등(프론트가 부지 컨텍스트로 합성)
         view: str = "aerial"   # aerial|perspective|street
         provider: str | None = None
         model: str | None = None
     ```
   - `image_provider.generate_image(provider, prompt=<view 프리픽스+prompt>, model=)` (input_image 없음=text2img). 성공시 과금("concept_render" 코드·관리자 설정), 정직강등.
   - view→프롬프트 프리픽스: aerial="aerial bird's-eye view architectural rendering of", perspective="eye-level street perspective photorealistic rendering of".

### 게이트/테스트: INC2와 동일 패턴(서비스 stub 테스트 + 엔드포인트).

---

## INC4 — 프론트: 프로바이더/모델 드롭다운 + 조감도/투시도 + 결과표시

### 변경 파일: `apps/web/components/design/CadBimIntegrationPanel.tsx`
1. **가용 프로바이더 로드**: 마운트 시 `apiClient.get("/design/image-providers")` → `providers` state. 드롭다운은 **가용분만** 표시(없으면 기존 replicate/no_key 흐름). 무 가용 시 드롭다운 숨김(graceful).
2. **드롭다운 추가**(렌더모달 confirm 구간, `renderStyle` 셀렉터 1806–1820행 바로 아래 — 동일 패턴 미러):
   - `renderProvider` state(가용목록의 default 또는 첫 항목), `renderModel` state(선택 provider의 models[].id, default_model).
   - 모델 옵션은 provider별 동적(providers[i].models).
3. **호출 바디 확장**: `runPhotorealRender()`(956–1042행)의 `apiClient.post("/design/{id}/render-photoreal",{body})` 바디에 `provider: renderProvider, model: renderModel` 추가.
4. **결과 표시(★계약 처리)**: 응답이 `image_url`(replicate) 또는 `image_base64`(openai/google) 둘 다 올 수 있음 → `const src = result.image_base64 ? \`data:image/png;base64,${result.image_base64}\` : result.image_url;` 로 `<img src={src}>`. 기존 status(no_key/error/ok)·과금(charged) 처리 유지.
5. **조감도/투시도 퀵액션**(INC3-1): 렌더모달 또는 3D 프리셋 바에 "조감도로 렌더"/"투시도로 렌더" 버튼 — 해당 CAM_PRESET로 카메라 이동(camControlsRef) → 1프레임 후 `gl.domElement.toDataURL` 캡처 → render-photoreal(provider 선택) 호출. (캡처는 기존 `gl:{preserveDrawingBuffer:true}` 활용)
6. (옵션·INC3-2) text2img 컨셉: 3D 없을 때 "컨셉 조감도 생성"(prompt 입력 → render-concept).

### 게이트: tsc(0)·eslint(신규 클린)·next build → code-reviewer ≥9.5 → PR → 통합자 머지 → A1 safe-deploy web(★sw CACHE_NAME bump 잊지 말 것 — 안 올리면 재방문자 미반영) → 라이브검증.

---

## 과금 / 비용 (주의)
- 이미지 생성은 **실비용**(gpt-image-1·Gemini·Replicate 각 과금). 성공시에만 차감(기존 정책). 관리자 미설정 시 무료(billing_admin_default_free 정책).
- gpt-image-1는 size·quality에 따라 비용 차등(기본 1024x1024). 대량 호출 게이트는 기존 charge_service로.
- image-health 진단도 실 1회 생성(소액)이라 super_admin 전용 유지.

## 시퀀싱 / 게이트 (각 증분 공통)
구현 → **code-reviewer ≥9.5/10** → ruff/eslint·py_compile/tsc·pytest/build → ≥95% 완결 → PR → **통합자 머지(self-merge 금지·정책)** → 배포(backend deploy.sh / frontend A1 safe-deploy) → **라이브검증**. 순서: INC2(백엔드) → INC3(백엔드 옵션) → INC4(프론트, INC2 배포 후).

## 리스크 / 함정 (★ 필독)
1. **requirements 이원화**: 신규 백엔드 의존성은 `requirements.txt`+`requirements.oracle.txt` **둘 다**(prod=Dockerfile.oracle). INC2~3는 이미 INC1의 google-genai/openai로 충분 — 신규 dep 없을 듯(추가 시 dry-run 검증).
2. **deploy.sh cascade**: pip 실패해도 옛 이미지로 스왑 후 "✅ 완료" 출력(은폐). 배포 후 반드시 라이브검증.
3. **반환 계약**: gpt-image-1=base64만(url 없음), replicate=url만. 프론트가 둘 다 처리(INC4-4). 혼동 금지.
4. **img2img 방식차**: openai=`images.edit(image=)`, google=`generate_content(contents=[prompt, Part.from_bytes])`. image_provider가 추상화하므로 서비스는 `input_image_b64`만 넘기면 됨.
5. **Gemini n/size**: google는 요청당 1장·size 미지원(aspect_ratio 후속). 다장 필요시 openai/replicate.
6. **프론트 sw bump**: A1 safe-deploy는 sw CACHE_NAME 자동 bump 안 함 → 프론트 변경 시 `apps/web/public/sw.js` CACHE_NAME 올릴 것.
7. **모델 ID 변동**: "나노바나나 Pro" 등 신모델은 `GEMINI_IMAGE_MODEL` env(또는 관리자 시크릿)로 교정 — image-health로 확정.

## 라이브검증 명령 (배포 후)
```bash
BASE=https://api.4t8t.net/api/v1
TOK=$(curl -s -X POST $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@4t8t.net","password":"admin1234"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
# 가용 프로바이더(INC2)
curl -s "$BASE/design/image-providers" -H "Authorization: Bearer $TOK" | python3 -m json.tool
# 모델 동작 재확인(INC1 진단)
curl -s "$BASE/admin/secrets/image-health?provider=google" -H "Authorization: Bearer $TOK" | python3 -m json.tool
# render-photoreal provider 선택(INC2) — 작은 base64 또는 text 경로로 1회
# 프론트(INC4): /ko/design-studio → 3D 탭 → 렌더모달에서 프로바이더=Gemini 선택 → 조감도 렌더 결과 확인
```

## 참고 코드 좌표
- 백엔드 진입: `app/routers/design_v61.py:105`(PhotorealRenderRequest), `:1179`(render_photoreal). 서비스: `app/services/drawing/photoreal_render_service.py`(render_photoreal·_style_prompt·get_render_api_key). 과금: `app/services/billing/billing_service.py:501`(photoreal_render).
- 프로바이더: `app/services/ai/image_provider.py`(generate_image·get_available_image_providers·resolve_model·ImageGenerationError). 진단: `app/routers/admin_secrets.py`(image-health).
- 프론트: `apps/web/components/design/CadBimIntegrationPanel.tsx` — runPhotorealRender(956–1042)·렌더모달(1775–1900)·renderStyle 셀렉터(1806–1820)·CAM_PRESETS(317–348)·프리셋바(1245–1273)·뷰포트 캡처(537·972 `gl.domElement.toDataURL`). apiClient: `apps/web/lib/api-client.ts`.
- 메모리: `project_llm_integration.md`(Gemini 활성화·requirements 함정), `project_oracle_deploy.md`(배포·deploy.sh cascade), `feedback_billing_admin_default_free.md`(과금정책), `feedback_no_mockup_verify.md`(무목업).
