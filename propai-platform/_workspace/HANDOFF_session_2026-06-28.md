# 세션 인수인계 (2026-06-28) — PropAI 이미지생성 + C2R 통합계획

> 다음 세션이 이어받는 단일 진입점. 상세는 각 PR/계획서/메모리 참조. 멀티세션 규약: 시작 시 `bash scripts/coord.sh status`(repo 루트) 먼저 읽고 전용 워크트리에서 작업.

---

## A. 완료·라이브 (재작업 불요)

1. **매스 시드 → 설계 스튜디오 ①②** — 라이브. seed-design regional이 실측 median 층수(target_floors) 반영 + 프론트 `SeedDesignMassComparison`(법정최대 vs 지역실측전형)·`zoningToCode` 공용. PR#94·#96 머지·배포·검증. 메모리 `project_mass_seed_design_studio`.
2. **이미지 생성 프로바이더 INC1** — 라이브. `app/services/ai/image_provider.py`(openai gpt-image·google Gemini "나노바나나"·replicate, 키+SDK가드·무목업·모델 env오버라이드) + `GET /admin/secrets/image-health`. PR#114 머지·백엔드 배포. **라이브 검증됨**: `image-health?provider=openai`→ok(gpt-image-1), `?provider=google`→ok(gemini-2.5-flash-image). 메모리 `project_llm_integration`.
3. **Gemini(google) LLM 텍스트 프로바이더** — 라이브. `langchain-google-genai==2.1.5`(langsmith 충돌로 2.1.12→2.1.5 다운핀), GOOGLE_API_KEY 라이브. providers=anthropic/openai/google.

## B. 인계됨 — 계획 수립 완료·실행 대기 (다음 세션 진행 대상)

### B1. 이미지 생성 화면 배선 INC2~4 → **PR #117** (`docs/image-gen-inc2-4-plan`)
파일 `propai-platform/_workspace/PLAN_image_generation_inc2-4.md`.
- **INC2(백엔드)**: `POST /design/{id}/render-photoreal`을 프로바이더 선택형으로 확장(PhotorealRenderRequest+provider/model, photoreal_render_service→image_provider) + `GET /design/image-providers`.
- **INC3(백엔드·옵션)**: 조감도/투시도 — 카메라 프리셋 이미 존재 → viewport2img는 INC2로 충분, text2img 컨셉만 옵션.
- **INC4(프론트)**: `CadBimIntegrationPanel.tsx` 렌더모달에 프로바이더/모델 드롭다운(renderStyle 패턴 미러)+base64/url 결과처리+프리셋 캡처.

### B2. C2R/HITL BIM 자동화 v1.5 통합계획 → **PR #125** (`docs/c2r-v15-integration-plan`)
파일 `propai-platform/_workspace/PLAN_c2r_v15_integration.md`. **정밀 재검증 완료(부록B, 가짜경로/함수 0건)**.
- **그린필드 금지**: 기존 엔진 위에 얇게. reuse_asis 42%·extend 35%.
- **★C2R는 신규 아님**: origin `feat/c2r-foundation`(PR#82)·`feat/c2r-render-guard`(PR#107) 라이브·**feat-tmp 미머지** → P0=머지 정렬. (P0 첫 게이트: `git ls-remote --heads origin '*c2r*'`+merge-base 재확인)
- **★area_119 재구현 금지**: `far_tier_service.calc_effective_far`+`special_parcel._aggregate_integrated_zoning` 조립. 4번째 구현=250%폴백 재발.
- 플랫폼 최적화: Oracle DB23ai→Postgres/PostGIS+Qdrant, OCI→R2/Supabase, Revit/.NET·APS·NIM 보류(IFC4/glTF).
- 재정의 P0~P7·게이트루브릭(9.5 수치화)·첫4주 E2E·리스크11·멀티세션규약·통합자 착수경로.
- 실행은 `feat/c2r-p{N}-{slug}` 후속 PR(≤600 LOC).

## C. ★배포 2-경로 (혼동주의 — 정밀 재검증 정정)
- **백엔드**(public `api.4t8t.net`=**168.110.125.89**): `ssh -i ~/.oci.key ubuntu@168.110.125.89 'bash ~/deploy.sh'` = **blue-green(8000↔8001·Caddy)**. C2R/이미지 등 백엔드 작업의 주 경로.
- **프론트/A1**(`www.4t8t.net`=**158.179.174.207**): `bash propai-platform/scripts/safe-deploy.sh web`(compose·nginx·락+재생성+헬스롤백). ★신규 프론트 배포 시 `apps/web/public/sw.js` CACHE_NAME bump.
- ⚠️ safe-deploy `api` 타깃=A1 standby(공개 api 무영향) → 백엔드를 safe-deploy로 올리면 "성공인데 prod 미반영". **배포 후 반드시 라이브검증**(deploy.sh cascade가 빌드실패 은폐).

## D. 공통 게이트·규약
- 각 증분: **code-reviewer ≥9.5** → `ruff`/`eslint`/`tsc`·`pytest`/`build` → 무목업·라이브검증 → PR → **통합자 머지(self-merge 정책상 차단됨)** → 배포 → 라이브검증.
- **requirements 이원화**: 신규 백엔드 의존성은 `apps/api/requirements.txt`+`requirements.oracle.txt` **둘 다**(prod=oracle). ★ifcopenshell 0.8.0↔0.8.4 모순은 C2R P0에서 단일화.
- 멀티세션: `scripts/coord.sh {status|claim|release|note}`(repo 루트), 전용 워크트리 `scripts/new-worktree.sh`, main 직접 푸시 금지.
- 키: 관리자 시크릿은 platform_secrets(Fernet)→부팅 `load_into_env`로 os.environ. `image-health`/`llm-health`로 라이브 진단. GOOGLE/OPENAI/ANTHROPIC 라이브.

## E. 다음 세션 착수 권장 순서
1. `bash scripts/coord.sh status` + PR #117·#125 읽기.
2. **이미지 INC2(백엔드)** 또는 **C2R P0(정렬)** 중 택1로 시작(둘 다 백엔드·독립).
3. 전용 워크트리·게이트·통합자 머지·2-경로 배포·라이브검증 준수.
