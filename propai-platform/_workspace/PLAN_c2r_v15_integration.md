# PropAI C2R/HITL BIM 자동화 v1.5 — 최종 통합 구현계획 (비판 반영본)

> 출처: 첨부 v1.4 계획 분석 → PropAI 기존자산 실측 매핑(워크플로 13에이전트: 9영역 조사+합성+적대검토+최종) → 비판 반영. 작성 2026-06-28, feat-tmp 세션 → 통합자 인계용.

> **버전 사유**: v1.4 초안에 적대적 비판(치명 5·권고 10)을 전량/선별 반영한 통합자 실행본. 핵심 변경: ① **C2R는 신규가 아니라 origin에 라이브(PR#82/#107) → P0를 "머지/리베이스 정렬"로 재정의**, ② **area_119는 monolithic 추출이 아니라 기존 `calc_effective_far`+`_aggregate_integrated_zoning` 조립**, ③ ifcopenshell 버전 모순·envelope.glb 의존체인·다필지 대표필지·coord 인프라 소재·게이트 루브릭 수치화 명문화.

---

## 0. 그라운드 트루스 (착수 전 확정된 사실 — 라이브 검증 완료)

| 비판 항목 | 검증 결과 (이번 세션 실측) | 계획 반영 |
|---|---|---|
| [치명1] C2R 신규 여부 | **C2R는 origin `feat/c2r-foundation`(PR#82)·`feat/c2r-render-guard`(PR#107)에 라이브. `feat-tmp`에는 미머지** (`git merge-base --is-ancestor 44de12c7 HEAD` → NO). 커밋 565974b0/040130c1/b4127b18/b863a648/d4561827/a0de079f 존재 | P0 = **신규 아님. 정렬+확장.** §4-P0 첫 게이트 = 머지 |
| [치명2] area_119 SSOT 누락 | `calc_effective_far` = `apps/api/app/services/land_intelligence/far_tier_service.py`. `_aggregate_integrated_zoning` = `apps/api/app/services/zoning/special_parcel.py`(소비처: `persona/runner.py`, `routers/auto_zoning.py`, 테스트 2종) | area_119 = **두 순수함수 어댑트** |
| [치명3] ifcopenshell 모순 | root `requirements.txt`=`0.8.0`, `requirements.oracle.txt`=`0.8.4`(+"제거" 주석 모순) | P0 게이트 = 버전 단일화 + Oracle import 라이브검증 |
| [치명5] coord 인프라 부재 | **부재 아님**: `scripts/coord.sh`·`scripts/new-worktree.sh`·`WORKTREES.md`·`.git/coordination` 모두 **repo 루트에 실재**. 비판의 find는 하위 워크트리만 스캔한 오탐 | coord 규약 유지(루트 기준 경로 명시), 폴백 규약 보조 |
| [권고10] safe-deploy 메커니즘 | blue-green 아님. **단일배포자 락 + 컨테이너 선제거·재생성 + 헬스검증 실패시 옛이미지 자동롤백**. 사용법 `bash propai-platform/scripts/safe-deploy.sh [web|api|both]` | §3·§7 배포절 정정 |

---

## 1. Executive Summary

### 1.1 핵심 명제 (불변)

**그린필드 금지.** v1.x의 가치는 "제약기반 BIM 컴파일러"이며 PropAI는 그 핵심 엔진(법규 SSOT·결정론 매스솔버·정북일조·special_parcel 게이트·IFC/glTF·evidence 계약·해시체인 원장·deliberation/expert-panel·orchestration DAG·billing/secret)을 production 보유. **게다가 C2R 토대 자체가 이미 라이브**(PR#82/#107). 따라서 이번 작업 = ① **origin C2R를 작업 브랜치로 정렬** ② 추적계층(run_id·hash·rule_trace·artifact URI) ③ HITL 승인계층 ④ 도면 초안계층 ⑤ 검증 오버레이 ⑥ 렌더 가드를 **얇게** 얹기.

### 1.2 v1.4 대비 보유 현황 (정정판)

| 컴포넌트 | 보유 | 부분 | 없음 | 우리 자산 |
|---|:--:|:--:|:--:|---|
| **C2R 네임스페이스/게이트렌더/render guard** | ● | | | **origin `feat/c2r-*` (PR#82/#107) — feat-tmp 미머지** |
| 법규 한도 SSOT(BCR/FAR/높이) | ● | | | `legal_zone_limits.py`, `auto_zoning_service.py` |
| **실효FAR SSOT** | ● | | | **`far_tier_service.calc_effective_far`** |
| **다필지 통합 SSOT** | ● | | | **`special_parcel._aggregate_integrated_zoning`** |
| area_119(면적·높이·층수) | | ● | | 위 둘을 조립할 **어댑터 미존재** |
| solar_61_86(정북일조) | | ● | | `solar_envelope_service.py`, `compute_north_step_profile` |
| special_parcel 게이트 | ● | | | `special_parcel.py` (BLOCKED~POSSIBLE) |
| 결정론 매스/코어/복도/유닛/주차 | ● | | | `auto_design_engine.py`, `unit_mix_optimizer.py` |
| envelope 3D solid(차감 GLB) | | | ○ | (수치만, 솔리드 차감 없음) |
| rule_trace.json export | ● | | | **이미 라이브**(b863a648 rule_trace+rule_set_hash) — 계약 확장만 |
| evidence 계약 | ● | | | `evidence_contract.py` |
| IFC4 생성/glTF | ● | | | `ifc_generator_service.py`, `ifc_to_gltf_service.py` |
| 도면 초안(SVG/DXF/PDF) | ● | | | `svg_drawing_service.py`, `parametric_cad_service.py` |
| HITL 승인 | | ● | | `hitl_queue.py`, `expert_panel`, `deliberation-review` |
| 해시체인 audit | ● | | | `audit_ledger.py`, `analysis_ledger.py` |
| run_state enum 통일 | | ● | | 3개 분산(`job_state`, `pipeline`, `useOrchestrationStore`) |
| idempotency/run_execution | | ● | | `parcel_batch.idempotency_key`(배치만) |
| Render guard | ● | | | **이미 라이브**(d4561827 geometry_hash 필수) — enforce 확장 |
| Celery/Redis·billing·secret | ● | | | `celery_app.py`, `billing_service`, `secret_store.py` |
| Oracle SDO/VECTOR, OCI, Revit, NIM | | | ○ | PostGIS+Qdrant+R2/Supabase로 대체 / 보류 |

집계: **reuse_asis 42% · extend 35% · wrap 10% · new(얇은계약/게이트) 8% · 보류 5%.** C2R 토대 라이브 반영으로 신규 비중이 v1.4 추정보다 더 낮아짐.

### 1.3 핵심 전략

1. **컴파일러 중심** — LLM은 검색·랭킹·법규텍스트 구조화·도면오류 설명·redline·prompt 생성에만. 법규최종판정/구조/방화/geometry 원천은 결정론 커널.
2. **★조립 우선(추출 아님)** — area_119는 `calc_effective_far`+`_aggregate_integrated_zoning`을 얇게 어댑트. solar_61_86은 `solar_envelope_service` 흡수. **실효FAR 4번째 구현 금지**(메모리 `design_studio_refactor` 250%폴백 재발 차단).
3. **C2R 정렬 우선** — origin C2R 토대를 작업 브랜치로 머지/리베이스한 뒤 그 위에 증분(INC). 절대 재구현 금지.
4. **추적 얇게** — `run_execution` 1테이블 + `RunStateEnum` 1개 + `artifact_uri` 규칙 + 기존 rule_trace 계약 확장.
5. **HITL 재사용** — deliberation + expert_panel + verify + audit_ledger를 S-phase 게이트로 래핑(새 엔진 금지).
6. **Render≠Buildable enforce** — 기존 render guard(geometry_hash 필수)에 `HUMAN_APPROVED(S8)` 전 최종렌더 금지 추가.
7. **보류 명시** — Revit .NET·APS/Forma·NIM·Oracle 관리형 DB·본격 IDS·full LOD300 제외, IFC/glTF 경유.

---

## 2. 자산 재사용 매트릭스 (P0~P7 × 자산 × reuse수준 × 작업)

> 풀패스 prefix: `/home/kangjh3kang/My_Projects/Development_AI/propai-platform/`

### P0 — Foundation / **C2R 정렬** / Reality Reset

| 컴포넌트 | 우리 자산 | reuse | 작업 |
|---|---|---|---|
| **C2R 토대 정렬** | origin `feat/c2r-foundation`·`feat/c2r-render-guard` | **merge/rebase** | feat-tmp(또는 신규 integration 브랜치)로 정렬. **충돌·회귀 검증이 P0 첫 게이트** |
| /c2r namespace·flag | 정렬된 C2R 라우터 + `apps/api/config.py`, `app/main.py` | extend | `C2R_ENABLED`·`C2R_RENDER_GUARD_ENFORCE` 설정 확인/추가 |
| automation boundary | `app/services/data_validation/evidence_contract.py` | extend | 산출물에 `disclaimer:"검토용 초안"`+`automation_boundary` |
| run_state SSOT | `foundation/parcel/batch/job_state.py`, `useOrchestrationStore.ts`, `project_pipeline` | extend | `packages/schemas/run_state.py` 신규 → 3곳 배선 |
| run_execution/artifact | `models/parcel_batch.py`(idempotency_key), `object_store.py`(R2 content-hash), `storage_service.py` | extend+wrap | `run_execution` 테이블 + `artifact_store`(기존 content_hash=sha256 canonical **동일해시 통일** — 권고5) |
| IaC/배포 | `scripts/safe-deploy.sh`, `requirements.oracle.txt` | reuse_asis | 락+재생성+자동롤백 유지. **ifcopenshell 버전 단일화**(치명3) |

### P1 — Legal Envelope / Parcel Kernel

| 컴포넌트 | 우리 자산 | reuse | 작업 |
|---|---|---|---|
| PNU/지번 검증+confidence | `zoning/auto_zoning_service.py`, `routers/auto_zoning.py` | extend | `pnu_validation_result{pnu,status,confidence_score,remarks}` 정식화 |
| **area_119(조립)** | **`land_intelligence/far_tier_service.calc_effective_far`** + **`zoning/special_parcel._aggregate_integrated_zoning`** + `auto_design_engine`(면적분해) | **wrap(어댑터)** | `legal/area_119_service.py` = 위 순수함수 호출 조립(공급/전용/연면적/코어/복도·높이·층수). **전역스윕**: precheck·land_report·design_audit가 동일 어댑터 경유 |
| **solar_61_86** | `site_score/solar_envelope_service.py` + `compute_north_step_profile` | extend→module | `legal/solar_61_86_service.py` 흡수(정북 step-back+envelope_gfa+binding) |
| apartment_spacing | `solar_envelope_service.row_distance_rule`(0.8H/0.5H) | extend | advisory→active constraint |
| parking_precheck | `auto_design_engine._compute_parking`, `PARKING_RULES` | wrap | 조례 지역·전용면적별 세부 |
| local_ordinance | `legal_zone_limits.applicable_limits_for`, `precheck_service._legal_limits` | extend | 오프라인 조례 fallback + `ordinance_confirmed`·`far_source` |
| **envelope.glb 의존체인** | shapely 차감 → **`ifc_generator_service`(IfcExtrudedAreaSolid)** → `ifc_to_gltf_service` | rebuild | **권고1: ifc_to_gltf는 IFC→GLB tessellator(shapely solid 직출력 불가). 반드시 IFC4 솔리드 경유** 또는 trimesh 직출력 보조경로 |
| rule_trace | **이미 라이브**(b863a648) + `legal_reference_registry.py`·`legal_quantity.CalcTrace` | extend | 계약에 area_119/solar origin 부착(verified 키만) |
| special_parcel 게이트 | `zoning/special_parcel.py` | reuse_asis | BLOCKED→차단. **POSSIBLE 확정도·대표필지 반영**(치명4) |

### P2 — Data Schema / Asset Dictionary (★P4와 병렬/후행 — 권고4)

| 컴포넌트 | 우리 자산 | reuse | 작업 |
|---|---|---|---|
| 공간 스키마 | `models/parcel.py`(PostGIS POLYGON), `spatial_service.py` | reuse_asis | SDO→ST_*/shapely |
| VECTOR | `init_qdrant.py`, `design_ingest/vector_store.py` | reuse_asis | Qdrant 1536-dim |
| family/type/material | `cad/template_assembly_service.py`, `cost/ifc_work_map.py`(27 codes) | extend | `family_mapping` 룩업 |
| golden corpus | `models/reference_image.py`, design_references+precedent_case | extend | **P4 이후/병렬로 강등**(권고4) |
| drawing template | `drawing/svg_drawing_service.py`, `parametric_cad_service.py` | extend | `drawing_code` taxonomy + sheet/title catalog |

### P3 — Orchestration + P3b Governance

| 컴포넌트 | 우리 자산 | reuse | 작업 |
|---|---|---|---|
| orchestration | `agents/propai_orchestrator.py`, `pipeline/project_pipeline.py` | reuse_asis | 7/10단계 재사용 |
| Celery/Redis | `tasks/celery_app.py` | reuse_asis | 장기 BIM task 추가만 |
| SSE | `packages/schemas/events.py`(AgentStepEvent) | reuse_asis | stage_count 파라미터화 |
| 4-track DAG | `web/lib/orchestration/node-registry.ts`, `dependency-graph.ts` | reuse_asis+extend | Buildable/Drawing/Render/Approval 트랙 |
| **render guard** | **이미 라이브**(d4561827 geometry_hash 필수) | extend | `C2R_RENDER_GUARD_ENFORCE` + **S8 미승인 차단 추가**(소유=P3b, 상태=P6 — 권고8) |
| Intent vs Render Card | `routers/drawing.py`(parse_intent), `photoreal_render_service.py` | wrap | 두 카드 schema 분리 |
| LLM 로그 | `ai_usage_log` ORM, `propai_orchestrator.get_llm` | extend | `design_intent_flag`, render에 generic LLM 금지 |
| budget guard | `billing/billing_service.charge_service` | reuse_asis | per-phase(미설정 무료) |

### P4 — BIM Draft Generator

| 컴포넌트 | 우리 자산 | reuse | 작업 |
|---|---|---|---|
| typology/solver | `auto_design_engine.MASSING_FORMS`·`compute_core_layout`·`compute_unit_layout`·`_compute_parking`, `floor_type_generator.py`, `unit_plan_generator.py` | reuse_asis | family_mapper로 직렬화 전달 |
| unit_mix(SLSQP) | `feasibility/unit_mix_optimizer.py` | reuse_asis | 그대로 |
| family_mapper | `template_assembly_service.py`, `cost/ifc_work_map.py` | new(룩업) | 기하→IFC 표준 패밀리 |
| **bim_packet**(구 revit_packet) | `bim/ifc_generator_service.py`(IfcWall/IfcSlab) | rebuild | **키 `bim_packet.json`으로 리네임**(권고3). `revit_adapter`는 옵션필드만 |
| LOD200~250 | `auto_design_engine`+`ifc_generator_service` | reuse_asis | 목표 LOD |

### P5 — Validation Overlay

| 컴포넌트 | 우리 자산 | reuse | 작업 |
|---|---|---|---|
| validation 8엔진 | `design_audit/design_audit_orchestrator.py`, `permit/building_code_rules.py`, `cad_auto_correction_service.py` | extend | `validation_report.json` 형식화 |
| IFC 차원 reconcile | `bim_ifc_service.py`(ifcopenshell) | extend(경량) | 본격 IDS 보류 |
| area_reconciliation | `cad_auto_correction_service`, `design_spec.validate_spec` | extend | 자동산출 vs 입력/도면 대조표 |

### P6 — Guided Run (S0~S9) + HITL

| 컴포넌트 | 우리 자산 | reuse | 작업 |
|---|---|---|---|
| S0~S9 UI+HITL | `web/components/orchestration/*`, `deliberation/DeliberationConsole.tsx`, `use-review-comment-store.ts`, `expert_panel_service.py`, `hitl_queue.py`, `audit_ledger.py` | wrap | S-phase navigator + 승인 게이트 |
| approval state | `audit_ledger.py`(해시체인) | new(얇은상태머신) | `approval_service.py`(append-only) — **render enforce는 P3b 가드 소유, 상태는 여기**(권고8) |
| drawing/bim packet | `svg_drawing_service.py`, `parametric_cad_service.py`, `ifc_to_gltf_service.py` | extend | `drawing_packet`·`bim_packet` export |
| redline | `use-review-comment-store.ts` | extend | `redline_suggestion` 영속 |

### P7 — Runbook / Ops / Feedback

| 컴포넌트 | 우리 자산 | reuse | 작업 |
|---|---|---|---|
| runbook.zip | `apps/worker/tasks/generate_report_pdf.py`, object_store | new(경량) | 입력·파라미터·산출 URI·rule_trace·validation·redline |
| telemetry/cost | `platform_event.py`, billing | reuse_asis | render cost·승인 SLA |
| redline learning | `tasks/growth_*`, `expert_panel` RAG | extend | redline→few-shot |

---

## 3. 플랫폼 최적화 결정표 (v1.4 가정 → 우리 현실)

| v1.4 가정 | 결정 | 근거·작업 |
|---|---|---|
| Oracle SDO_GEOMETRY | **Postgres+PostGIS** | `parcel.boundary`(POLYGON,4326), `spatial_service.py`. SDO→ST_Difference/Intersection. **정밀 사선차감은 shapely 메모리 연산 병행** |
| Oracle VECTOR | **Qdrant**(1536-dim, text-embedding-3-small) | `init_qdrant.py` production |
| OCI Object Storage | **R2 + Supabase Storage** | `object_store.py`(content-hash dedup), `storage_service.py` |
| artifact URI=oci:// | **`propai://{tenant_id}/{project_id}/{run_id}/{artifact_name}#sha256={hash}`** | 논리URI DB저장, 물리매핑은 `artifact_store`. **기존 content_hash와 동일 sha256으로 통일**(권고5) |
| OCI Resource Manager | **Oracle VM + `safe-deploy.sh`(락+재생성+자동롤백)** | **blue-green 아님**(치명·권고10 정정). 백엔드 168.110.125.89, 프론트 158.179.174.207 재빌드. `bash propai-platform/scripts/safe-deploy.sh [web\|api\|both]` |
| Celery/Redis | 재사용 | 장기 BIM task만. run-state=`run_execution`+`RunStateEnum` |
| run-state enum | `packages/schemas/run_state.py` SSOT | `DRAFT/PASS/PASS_WITH_WARNINGS/FAIL/MANUAL_REVIEW_REQUIRED/HUMAN_APPROVED/LOCKED` → 3곳 배선 |
| HITL 인프라 | deliberation+expert_panel+verify+audit_ledger 재사용 | 새 엔진 금지. 승인은 `audit_ledger` 해시체인 append |
| Render(Firefly/NIM) | `photoreal_render_service`(Replicate/SDXL)+provider tiering+**기존 geometry_hash 가드**+S8 enforce | LLM 메시 생성 금지 |
| Revit Add-in | **IFC4 native+glTF** | `ifc_generator_service`·`ifc_to_gltf_service`. 향후 IFC import 옵션 |
| IDS | 경량 차원 reconcile | 본격 IDS 보류 |
| NIM | **Claude(`get_llm`)** | render generic LLM 금지 |
| **ifcopenshell 버전** | **0.8.x 단일화 + Oracle import 라이브검증**(치명3) | root 0.8.0 ↔ oracle 0.8.4 모순 해소, "제거" 주석 정정 |

---

## 4. 재정의 단계 (P0~P7) — 단계별 실행 사양

> **공통 게이트(전 단계)**: C2R 게이트 루브릭(§6.3) ≥9.5 · `ruff`/`eslint`/`tsc` · `pytest`/`build` · **무목업**(provider 미설정→`provider_unconfigured` 정직강등) · 라이브검증 · **전용 워크트리**(`scripts/new-worktree.sh`, repo 루트 기준) · 공유파일 `scripts/coord.sh claim/release` · 통합자 머지 · `requirements.txt`↔`requirements.oracle.txt` **양쪽 반영** · 배포 `safe-deploy.sh`. 커밋에 증상·근본원인·수정·라이브검증 + 전역스윕(공용헬퍼).
> **브랜치**: `feat/c2r-p{N}-{slug}`. **PR ≤~600 LOC**(스키마/마이그레이션·추출·배선·회귀는 분리 — 권고7).

### 산출물 공통 메타 계약
```
_meta: { run_id, parent_run_id|null, artifact_name, version,
         hash:"sha256:...",            // = artifact_store content_hash와 동일(권고5)
         created_at, state(RunStateEnum), disclaimer:"검토용 초안",
         automation_boundary:{ ai_used:[...], deterministic:[...], human_required:[S3,S4,S6,S8] },
         evidence:{ value, basis, source, provenance, legal_link, confidence } }  // rule_trace와 단일계약(권고6)
```

---

### P0 — Foundation / **C2R 정렬** / Reality Reset
- **목표**: origin C2R 토대를 작업 브랜치로 정렬 + 추적 인프라(run_state·run_execution·artifact_store) + 버전 모순 해소.
- **재사용**: origin `feat/c2r-foundation`·`feat/c2r-render-guard`, `config.py`, `app/main.py`, `evidence_contract.py`, `safe-deploy.sh`, `object_store.py`.
- **신규 최소구현**:
  - `packages/schemas/run_state.py` — `RunStateEnum`.
  - `database/migrations/versions/0NN_run_execution.py` — `run_execution(run_id PK, parent_run_id, project_id, tenant_id, track, s_phase, state, input_hash, artifact_uri, approval_gate_json, created_at, updated_at)` + `idempotency_key UNIQUE`.
  - `app/services/c2r/artifact_store.py` — `put/get/hash_canonical`(R2/Supabase 위임, **content_hash=sha256 canonical 통일**).
- **산출물 계약**: `run_execution` row + `propai://...#sha256=` URI.
- **게이트(순서)**:
  1. **★C2R 정렬 게이트**: `git merge-base --is-ancestor <c2r tip> HEAD` = YES. 머지 충돌 0, 기존 `/api/v1/c2r/*`(S0~S4b·render guard) 회귀 통과.
  2. ifcopenshell 0.8.x 단일화 + **Oracle VM에서 `python -c "import ifcopenshell, pygltflib"` 실제 성공**(치명3).
  3. 마이그레이션 라이브 적용·롤백 검증. flag OFF 시 기존 경로 무영향.
  4. enum 단일화 import 3곳 컴파일 OK. artifact_store R2/Supabase round-trip.
  5. **coord 인프라 소재 확인**: `scripts/coord.sh status` 동작(루트 기준). 부재 워크트리면 폴백 규약(§8) 적용.
- **라이브검증**: `POST /api/v1/c2r/ping` 200, `run_execution` insert/조회, artifact put/get 해시 일치.
- **완료정의**: C2R 토대가 작업 브랜치에서 라이브 + 추적 3종 동작 + Oracle import 성공.
- **PR**: ①C2R 정렬(머지/회귀) ②run_state+migration ③artifact_store.

### P1 — Legal Envelope / Parcel Kernel
- **목표**: PNU검증 → **area_119(조립)**·solar_61_86 → special_parcel 게이트(POSSIBLE·대표필지) → envelope solid(IFC경유 GLB) → rule_trace → validated_parcel.
- **재사용**: `auto_zoning_service.py`, **`far_tier_service.calc_effective_far`**, **`special_parcel._aggregate_integrated_zoning`**, `special_parcel.py`, `solar_envelope_service.py`, `compute_north_step_profile`, `precheck_service._prov`, `legal_reference_registry.py`, `ifc_generator_service.py`, `ifc_to_gltf_service.py`.
- **신규 최소구현**:
  - `app/services/legal/area_119_service.py` — **`calc_effective_far`+`_aggregate_integrated_zoning` 얇은 어댑터**(추출 아님). 면적분해(공급/전용/연면적/코어/복도)·높이·층수. **전역스윕**: precheck·land_report·design_audit 일원화.
  - `app/services/legal/solar_61_86_service.py` — `solar_envelope_service` 흡수.
  - `app/services/c2r/buildable_envelope_service.py` — shapely 차감 → **`ifc_generator_service`로 IfcExtrudedAreaSolid** → `ifc_to_gltf_service`로 `envelope.glb`(권고1 의존체인).
  - rule_trace 계약 확장(기존 라이브 rule_trace에 area_119/solar origin).
- **산출물 계약**:
  - `validated_parcel.json`: `{pnu, pnu_validation:{status,confidence_score,remarks}, address, area_sqm, **effective_land_area_sqm**, land_category, zone_type, zone_confirmation:{source,confidence}, applicable_limits:{legal:{bcr_pct,far_pct,height_m}, ordinance:{...,ordinance_confirmed,far_source}, plan:{...}}, special_parcel:{is_special, developability, **developability_confidence**, resolvable, factors[], resolution_paths[]}, **representative_pnu**, **member_parcels[]**, legal_refs[]}` — **치명4: 대표필지·통합면적·POSSIBLE 확정도 필수. envelope/mass는 `effective_land_area_sqm`(통합) 입력 강제, raw 금지**(메모리 `multiparcel_area_parity`).
  - `rule_trace.json`: `{traces:[{rule_id, basis_article, legal_ref_key(verified만), condition, applied_value, measured_value, excluded_elements[], evidence:{...단일계약}, run_id}]}`
  - `envelope.json`+`envelope.glb`: `{envelope_gfa_sqm, binding_constraint(far|height|sunlight|setback|road_sline), daylight_loss_pct, north_step_profile[], glb_uri, rule_trace_ref}`
- **게이트**: special_parcel=BLOCKED→설계 차단(정직표기) · POSSIBLE→확정도 표기 · envelope_gfa ≤ 법정GFA(sanity) · 모든 값 rule_trace origin 보유 · **실효FAR는 `calc_effective_far` 단일경로**(250%폴백 0건).
- **라이브검증**: 의정부224 등 실주소 → `POST /api/v1/c2r/p1/envelope` → validated_parcel+rule_trace+envelope.glb. **산/임야 용적률 과대 미발생**(공용헬퍼). **다필지 1건**: 통합면적 기준 envelope, 단일분석 덮어쓰기 없음.
- **완료정의**: area_119/solar 일원화 후 precheck·land_report·design_audit 회귀 통과 + envelope.glb 3D 로드.
- **PR**: ①area_119 어댑터(추출) ②소비처 배선(precheck·land_report·design_audit) ③회귀 ④buildable_envelope+glb ⑤rule_trace+validated_parcel(대표필지·통합면적) — **추출/배선/회귀 분할로 ≤600 LOC**(권고7).

### P2 — Data Schema / Asset Dictionary (★P4와 병렬/후행 — 권고4)
- **목표**: family/type/material dict + drawing template + corpus(후행).
- **재사용**: `template_assembly_service.py`, `cost/ifc_work_map.py`, `reference_image.py`, `init_qdrant.py`.
- **신규**: `app/services/c2r/family_mapping.py`(룩업), drawing template 카탈로그(JSON). **golden corpus는 P4 이후 병렬**.
- **산출물 계약**: `family_mapping.json`: `{mappings:[{propai_element(wall|floor|door|window|core), ifc_type, std_category, material_key, params{}}]}`
- **게이트**: family_mapping이 P4 IFC 생성에 소비됨 · Qdrant 검색 정확.
- **완료정의**: family_mapping live 소비. (corpus 큐레이션은 별 트랙 완료정의.)
- **PR**: ①family_mapping ②template catalog ③corpus(후행).

### P3 — Orchestration + P3b Governance
- **목표**: 4-track DAG·idempotency·run_execution 영속·렌더 가드 enforce·승인 게이트 토대.
- **재사용**: `propai_orchestrator.py`, `project_pipeline.py`, `celery_app.py`, `events.py`, `node-registry.ts`, `dependency-graph.ts`, `billing_service`, `ai_usage_log`, `hitl_queue.py`, **기존 render guard(d4561827)**.
- **신규 최소구현**:
  - `node-registry.ts` 확장: track(Buildable/Drawing/Render/Approval)+`run-mode='c2r'`.
  - `app/services/c2r/run_service.py` — idempotency enforce + SSE.
  - `app/services/c2r/governance.py` — Intent Card vs Render Prompt Card schema + **render guard enforce 확장**(geometry_hash 필수 + S8 미승인 차단). **enforce 소유=P3b, 승인상태 조회=P6 approval_service**(권고8).
- **산출물 계약**: `design_intent_card.json`(용도/층수/세대/법규 — LLM 허용), `render_prompt_card.json`(외관/재료/조명 — generic LLM 금지, 템플릿+human-approved).
- **게이트**: 동일 input_hash 재실행 중복산출 방지 · render는 geometry_hash 없거나 state≠HUMAN_APPROVED면 거부 · LLM 호출 전부 `ai_usage_log`.
- **라이브검증**: c2r SSE 단계 스트리밍, idempotency 재요청 캐시 hit, render guard live 차단(미승인 시 거부 응답).
- **완료정의**: 4-track DAG OrchestratorPanel 시각화 + guard enforce 라이브.
- **PR**: ①run_service+idempotency ②DAG track ③governance/guard enforce.

### P4 — BIM Draft Generator
- **목표**: typology→mass_graph→layout_graph→family_mapping→IFC native(LOD200~250).
- **재사용**: `auto_design_engine`(core/corridor/unit/parking), `unit_mix_optimizer.py`, `floor_type_generator.py`, `unit_plan_generator.py`, `ifc_generator_service.py`.
- **신규**: mass_graph 직렬화, layout_graph 토폴로지, family_mapping 소비 IFC 생성.
- **산출물 계약**:
  - `mass_graph.json`: `{candidates:[{id, building_width, depth, num_floors, bcr_pct, far_pct, gfa_sqm, profit_rate, pareto_rank}], selected_id}`
  - `layout_graph.json`: `{nodes:[{id,type(core|unit|corridor),pos,area}], edges:[{from,to,type}]}`
  - **`bim_packet.json`**(구 revit_packet 리네임 — 권고3): `{ifc_uri, glb_uri, family_mapping_ref, base_quantities{}, lod:"200-250", revit_adapter:null, run_id, hash}`
- **게이트**: BCR/FAR/높이 법정한도 내 · envelope 내포(차감매스 침범 금지) · far_pct는 `calc_effective_far` 기준.
- **라이브검증**: 실부지→mass_graph Top3→선택→IFC4+glTF 생성·뷰 로드.
- **완료정의**: IFC 적산(`bim_ifc_service`)이 mass와 정합.
- **PR**: ①mass_graph ②layout_graph ③bim_packet+family.

### P5 — Validation Overlay
- **목표**: geometry/legal/BIM/drawing/area 검증 → validation_report.
- **재사용**: `design_audit_orchestrator.py`(8엔진), `building_code_rules.py`, `cad_auto_correction_service.py`, `design_audit_pdf.py`.
- **신규**: `validation_report.json` formatter + area_reconciliation.
- **산출물 계약**: `validation_report.json`: `{checks:[{check_id, engine, status(PASS|WARNING|FAIL|N/A), current, limit, legal_basis, hash}], area_reconciliation:[{floor, gfa, nfa, core, corridor, delta_to_legal}], overall(RunStateEnum)}`
- **게이트**: FAIL→`MANUAL_REVIEW_REQUIRED` · 모든 check legal_basis 보유 · report audit_ledger append.
- **라이브검증**: 위반 케이스 주입→FAIL+근거.
- **PR**: ①validation_report ②area_reconciliation.

### P6 — Guided Run (S0~S9) + HITL
- **목표**: S0~S9 UI·승인 게이트(S3/S4/S6/S8)·drawing/bim packet·redline.
- **재사용**: `web/components/orchestration/*`, `DeliberationConsole.tsx`, `use-review-comment-store.ts`, `expert_panel_service.py`, `hitl_queue.py`, `audit_ledger.py`, `svg_drawing_service.py`, `parametric_cad_service.py`, `ifc_to_gltf_service.py`.
- **신규 최소구현**:
  - `app/services/c2r/approval_service.py` — S-phase 상태머신(append-only `approval_event`), `POST /api/v1/c2r/{run_id}/approve`. **render enforce는 P3b 가드가 이 상태를 조회**(권고8 단일화: enforce=가드, 상태소유=approval_service).
  - `redline_suggestion` 모델.
  - `GET /api/v1/c2r/{run_id}/drawing-packet`·`/bim-packet` export.
- **산출물 계약**:
  - `drawing_packet.json`: `{views:[{drawing_code, type, floor_level, scale, svg_uri, dxf_uri}], sheets:[], schedules:[], approval_state, run_id, hash}`
  - approval event: `{run_id, s_phase, status, approver_id, role, rationale, verification_report_ref, ledger_hash, ts}`
- **게이트**: S8 미승인→최종 렌더/lock 금지(가드 enforce) · 승인에 expert_panel verification_report 첨부 · 모든 승인 audit_ledger 해시체인.
- **라이브검증**: S3→S4→S6→S8 통과 후에만 lock, 거부 시 redline 루프, **미승인 render 거부 확인**.
- **PR**: ①approval state machine+ledger ②S0~S9 UI ③drawing/bim_packet+redline.

### P7 — Runbook / Ops / Feedback
- **목표**: runbook.zip·telemetry·redline learning.
- **재사용**: `generate_report_pdf.py`, `object_store`, `platform_event.py`, `growth_*`, `expert_panel` RAG.
- **신규**: runbook 패키저, redline→few-shot 적재.
- **산출물 계약**: `runbook.zip`(입력·파라미터·산출 URI·rule_trace·validation_report·redline 요약).
- **게이트**: 재현가능(동일 input_hash→동일 결정론 산출).
- **PR**: ①runbook ②telemetry ③learning loop.

---

## 5. 보류 / 대안 (1차 제외 — 명시)

| 항목 | 결정 | 대안/향후 |
|---|---|---|
| Revit Add-in(.NET8) | 보류 | IFC4 native + glTF. `bim_packet.json`(리네임). 향후 IFC import 옵션 |
| DirectShape native 복원 | 보류 | IFC native 표준. Revit가 IFC import |
| Autodesk APS/Forma | 보류 | 미계약. SVG/DXF/PDF/IFC 충분 |
| NVIDIA NIM | 보류 | Claude(`get_llm`)+Replicate/SDXL. render generic LLM 금지 |
| Oracle SDO/VECTOR | 대체 | PostGIS+shapely+Qdrant |
| OCI Object/Resource Manager | 대체 | R2/Supabase + `safe-deploy.sh`(락+재생성+롤백) |
| buildingSMART IDS 본격 | 1차 제외 | 경량 차원 reconcile. IDS는 P5+ 후속 |
| LOD300 full shell/core | 1차 제외 | LOD200~250 우선 |
| **golden corpus 게이트 선행** | 강등(권고4) | P4 이후/병렬 |

---

## 6. 첫 4주 + 첫 E2E + 게이트 루브릭

### 6.1 첫 E2E (전부 기존 엔진 재사용)
```
PNU/부지검증(auto_zoning_service)
 → validated_parcel.json (대표필지·통합면적·POSSIBLE 확정도)
 → area_119_service(=calc_effective_far + _aggregate_integrated_zoning 조립) + solar_61_86_service
 → buildable_envelope_service (shapely 정북·도로사선 차감 → ifc_generator IfcExtrudedAreaSolid → ifc_to_gltf) → envelope.glb
 → auto_design_engine (mass/core/corridor/unit/parking) → mass_graph.json
 → rule_trace.json (각 값 origin, verified 키)
 → design_audit_orchestrator → validation_report.json
 → ifc_generator_service + ifc_to_gltf_service → IFC4 + glb (LOD200~250) → bim_packet.json
 → (전 산출물 run_execution + artifact_uri + audit_ledger append)
```

### 6.2 4주 일정
- **W1 (P0)**: **★C2R origin 정렬(머지/회귀)** → run_state·run_execution·artifact_store → ifcopenshell 단일화+Oracle import 검증 → `/api/v1/c2r` flag. 라이브: ping 200·run round-trip·Oracle import OK.
- **W2 (P1-a)**: area_119 어댑터(`calc_effective_far`+`_aggregate_integrated_zoning`)+solar_61_86 + **전역스윕**(precheck·land_report·design_audit) + 회귀(추출/배선/회귀 PR 분할). 라이브: 산/임야 과대 미발생·250%폴백 0건.
- **W3 (P1-b)**: buildable_envelope(차감 solid → IFC → GLB) + rule_trace + validated_parcel(대표필지·통합면적). 라이브: 실주소 envelope 3D·다필지 통합면적.
- **W4 (E2E)**: P1→auto_design_engine mass→validation_report→IFC/glTF(bim_packet)→audit_ledger. 라이브: 의정부224 풀 E2E 1패스(검토용 초안 표기).

### 6.3 ★C2R 게이트 루브릭(권고9 — "9.5" 수치화)
코드리뷰 9.5/10 = 아래 가중 합산, 각 항목 만점 전제:
- **무날조/무목업(3.0)**: 모든 값 실데이터/정직강등. envelope·면적·층수 날조 0건.
- **rule_trace origin 100%(2.0)**: 산출 모든 법규값이 verified `legal_ref_key` 보유. 할루시네이션 URL 0건.
- **geometry sanity(2.0)**: envelope_gfa ≤ 법정GFA, 매스 envelope 내포, far_pct=`calc_effective_far` 단일경로(250%폴백 0).
- **SSOT 일관성(1.5)**: 다필지 통합면적 사용, 단일분석 덮어쓰기 0, area_119가 기존 SSOT 호출.
- **추적/멱등(1.0)**: run_id·hash·state 부착, idempotency 재실행 중복 0.

### 6.4 운영 게이트(공통): lint(`ruff`/`eslint`/`tsc`)·build·`pytest` 통과 · requirements 이원화 양쪽 반영 · 통합자 머지 · `safe-deploy.sh`.

---

## 7. 리스크 / 함정

1. **★C2R origin 분기(치명1)** — C2R는 `feat/c2r-foundation`·`feat/c2r-render-guard`(fork `kangjh3kang-beep`)에 있고 `feat-tmp` 미머지. **재구현 금지. P0 W1 머지가 첫 일.** 메모리 `ai_assistant_agent` "로컬main stale→origin분기" 함정.
2. **★실효FAR 4번째 구현(치명2)** — area_119가 `calc_effective_far`·`_aggregate_integrated_zoning` 미호출 시 250%폴백 재발(`design_studio_refactor`). **어댑트만, 재구현 금지.**
3. **★ifcopenshell 버전 모순(치명3)** — root 0.8.0 ↔ oracle 0.8.4 + "제거" 주석 모순. **0.8.x 단일화 + Oracle VM 실 import 검증 P0 게이트.** 의존성(shapely 2.0.6·pygltflib) 양쪽 반영. 더미키·인라인 주석 오염 금지(`g2b_env_key_loading`).
4. **★다필지 면적 SSOT(치명4)** — validated_parcel에 `representative_pnu`·`effective_land_area_sqm` 필수. envelope/mass는 통합면적 입력 강제(raw 금지 — `multiparcel_area_parity`). POSSIBLE 확정도 표기(`special_parcel_detect`).
5. **envelope.glb 의존체인(권고1)** — `ifc_to_gltf`는 IFC→GLB tessellator. shapely solid 직출력 불가. **IFC4 솔리드 경유** 또는 trimesh 보조경로.
6. **배포(치명·권고10 정정)** — **blue-green 아님**. `safe-deploy.sh`=락+컨테이너 선제거·재생성+헬스실패 자동롤백. compose v1 버그·api 네트워크 유실 502 주의. 마이그레이션은 배포 전 별도 검증. 사용: `bash propai-platform/scripts/safe-deploy.sh both`.
7. **sw bump / CORS** — 프론트 변경 시 service worker 버전 bump. 신규 헤더(X-Run-Id 등) 추가 시 CORS `allow_headers` 필수(`sales_cors_503`).
8. **render≠buildable enforce 소유(권고8)** — enforce=P3b governance 가드, 승인상태=P6 approval_service. S8 전 최종렌더/LLM 메시 생성 금지.
9. **artifact 해시 이중화(권고5)** — `artifact_store` content_hash = `_meta.hash` = rule_trace evidence_hash 동일 sha256 canonical. 기존 `object_store` content-addressable 키와 통일.
10. **PR 크기(권고7)** — P1 area_119는 추출/배선/회귀 3 PR 분할로 각 ≤600 LOC.
11. **Postgres geometry 한계** — 정밀 사선차감 shapely 메모리 병행. 대규모 다필지 병렬.

---

## 8. 멀티세션 / PR 규약

- **coord 인프라 실재(치명5 정정)**: `scripts/coord.sh`·`scripts/new-worktree.sh`·`WORKTREES.md`·`.git/coordination`가 **repo 루트에 존재**. 비판의 "부재"는 하위 워크트리만 스캔한 오탐. **반드시 repo 루트 기준 실행**: `bash scripts/coord.sh status`.
- **세션 시작**: `scripts/coord.sh status` → 작업영역 파악. 브랜치당 전용 워크트리 `scripts/new-worktree.sh feat/c2r-p{N}-{slug}`. 공유메인에서 feature checkout 금지.
- **공유파일 claim**: `main.py` 라우터 등록, `node-registry.ts`, `run_state.py` 등 편집 전 `scripts/coord.sh claim <영역>` → 완료 `release`. 진행 `note`.
- **커밋 전** `git branch --show-current` 확인. main 직접 푸시 금지. 명시 인계 `mcp__ccd_session_mgmt__send_message`.
- **폴백 규약(coord 부재 워크트리일 때)**: ① `git branch --show-current`로 자기 브랜치 확인 ② PR 라벨 `c2r-p{N}` ③ 공유파일은 1 PR 1 파일 원칙 + PR 설명에 claim 메모.
- **PR 규약**: `feat/c2r-p{N}-{slug}`, 단계당 1~3 PR, **≤~600 LOC**(스키마/추출/배선/회귀 분리). 본문에 증상·근본원인·수정·라이브검증 + 전역스윕 결과. 통합자 머지.

---

### 통합자 착수용 핵심 경로
- **C2R 정렬**: origin `feat/c2r-foundation`(PR#82)·`feat/c2r-render-guard`(PR#107) → 작업 브랜치 머지
- 추적/오케스트레이션: `apps/api/agents/propai_orchestrator.py`, `apps/api/app/services/pipeline/project_pipeline.py`, `apps/api/app/tasks/celery_app.py`, `apps/web/lib/orchestration/node-registry.ts`, `apps/api/app/models/parcel_batch.py`
- **법규/envelope(★조립 SSOT)**: `apps/api/app/services/land_intelligence/far_tier_service.py`(calc_effective_far), `apps/api/app/services/zoning/special_parcel.py`(_aggregate_integrated_zoning), `apps/api/app/services/site_score/solar_envelope_service.py`, `apps/api/app/services/zoning/{legal_zone_limits,auto_zoning_service}.py`, `apps/api/app/services/legal/legal_reference_registry.py`, `apps/api/app/services/cad/auto_design_engine.py`
- BIM/도면/렌더: `apps/api/app/services/bim/{ifc_generator_service,ifc_to_gltf_service}.py`, `apps/api/app/services/drawing/{svg_drawing_service,photoreal_render_service}.py`, `apps/api/app/services/cad/parametric_cad_service.py`
- HITL/감사: `apps/api/app/services/ledger/audit_ledger.py`, `apps/api/app/routers/analysis_ledger.py`, `apps/api/app/services/expert_panel/expert_panel_service.py`, `services/deliberation-review/apps/api/app/supply/hitl/hitl_queue.py`
- 저장/과금/시크릿: `apps/api/app/services/design_ingest/object_store.py`, `apps/api/services/storage_service.py`, `apps/api/app/services/billing/billing_service.py`, `apps/api/app/services/secrets/secret_store.py`
- 배포/의존성: `scripts/safe-deploy.sh`(락+재생성+롤백), `apps/api/requirements.txt`(ifcopenshell 0.8.0), `apps/api/requirements.oracle.txt`(0.8.4 — **단일화 대상**)
- 멀티세션: `scripts/coord.sh`, `scripts/new-worktree.sh`, `WORKTREES.md`, `.git/coordination/`(repo 루트)
- 신규 생성: `packages/schemas/run_state.py`, `apps/api/app/services/c2r/{artifact_store,buildable_envelope_service,run_service,governance,family_mapping,approval_service}.py`, `apps/api/app/services/legal/{area_119_service,solar_61_86_service}.py`, `apps/api/database/migrations/versions/0NN_run_execution.py`

---

# 부록 A — 적대적 검토(반영 근거)

> 아래 비판(치명 5·권고 10)은 위 v1.5 본문에 전량/선별 반영됨. 통합자 참고용 원본.

## 적대적 비판: PropAI C2R/HITL v1.4 통합계획

## ① 기존자산 재사용 누락 (rebuild/new로 잡았으나 실재)

**[치명 1] `/api/v1/c2r` 네임스페이스를 P0 "신규"로 잡았으나, 메모리(`project_c2r_foundation`)는 이미 `/api/v1/c2r` + S0~S4b + 게이트 렌더가 PR#82로 라이브라고 기록.** 그런데 실코드 검증 결과 현재 브랜치 `feat-tmp`에는 `routers/c2r`·`services/c2r`·`/api/v1/c2r` 엔드포인트가 **전혀 없다**(`grep` 결과 .venv만 매치). → 즉 계획의 P0가 "신규"인지 "재사용"인지조차 그라운드 트루스가 안 잡혀 있다. **수정지시:** 착수 전 `git log --all --oneline | grep -i c2r`로 PR#82가 어느 브랜치/origin에 있는지 확정하고, `feat-tmp`로의 머지/리베이스 상태를 P0 W1 첫 게이트로 박아라. C2R 토대가 origin에 살아있으면 P0는 "재사용+확장"이지 신규가 아니다. 메모리 `ai_assistant_agent`의 "로컬main stale→origin분기" 함정 그대로 재현 중.

**[치명 2] `area_119_service` 분리 시 기존 `calc_effective_far`(`land_intelligence/far_tier_service.py`)와 `_aggregate_integrated_zoning`(`special_parcel.py:583`)을 누락.** 계획은 `auto_design_engine`만 분리원천으로 지목했으나, 실효FAR 산정의 SSOT는 이미 `far_tier_service.calc_effective_far`이고 다필지 통합은 `_aggregate_integrated_zoning`이다(`persona/runner.py:291`이 소비 중). 분리 모듈이 이들을 호출하지 않으면 **실효FAR 4번째 구현체**가 생겨 메모리 `design_studio_refactor`의 "실효FAR 미전달→250% 폴백" 버그가 정확히 재발한다. **수정지시:** area_119는 `calc_effective_far`+`_aggregate_integrated_zoning`을 **얇게 어댑트**하는 것으로 재정의. "monolithic 추출"이 아니라 "기존 순수함수 조립".

**[권고 1] `ifc_to_gltf_service`를 envelope.glb 산출에 "wrap"으로 잡았으나 실제론 IFC→GLB 전용 tessellator**(`ifcopenshell.geom.iterator` 기반, mesh 없으면 ValueError). shapely 차감 solid를 직접 GLB로 못 내보낸다 — IFC4 솔리드를 먼저 만들어야 통과. **수정지시:** P1 envelope.glb 경로를 "shapely solid → ifc_generator로 IfcExtrudedAreaSolid 생성 → ifc_to_gltf"로 명시하거나, trimesh 직출력 경로를 별도 추가. 현 계획의 "rebuild"는 맞으나 의존 체인이 누락.

**[권고 2]** `audit_ledger`·`expert_panel`·`hitl_queue` 재사용 판정은 정확(경로 실재 확인). `special_parcel` reuse_asis도 타당.

## ② 과설계 / 우리현실 초과

계획은 보류 섹션(§5)에서 Revit Add-in·APS/Forma·NIM·Oracle 관리형을 명시 제외했고 이는 **올바른 판단**. 다만:

**[권고 3] `revit_packet.json` 이름을 끝까지 유지하는 것이 부채.** "우리 버전=IFC packet"이라 주석 달았으나, 키 이름이 `revit_packet`이면 미래 누군가 Revit 복원을 가정한 코드를 붙인다. **수정지시:** 산출물 키를 `bim_packet.json`으로 리네임하고 `revit_adapter`는 향후 옵션 필드로만 남겨라.

**[권고 4]** P2의 "golden corpus 20 typology 큐레이션"은 1차 E2E에 불필요한 선행 과설계. 첫 E2E(§6)는 corpus 없이 도는데 P2를 P4 앞에 게이트로 두면 일정만 늘어난다. **수정지시:** P2 corpus를 P4와 병렬/후행으로 강등.

## ③ 플랫폼 불일치 오류

§3 매핑 테이블은 대체로 정확(Postgres+PostGIS/Qdrant/R2+Supabase/blue-green). 검증 결과 shapely 2.0.6·ifcopenshell·pygltflib가 양쪽 requirements에 이미 존재 — 의존성 가정 OK. 다만:

**[치명 3] `requirements.oracle.txt`는 `ifcopenshell ~174MB 제거` 주석과 동시에 `ifcopenshell==0.8.4`를 포함하는 모순 상태**(실파일 확인). 두 버전(루트 0.8.0 vs oracle 0.8.4)도 불일치. C2R이 IFC 풀스택을 쓰는데 Oracle 빌드의 ifcopenshell 포함 여부가 불확실하면 배포 시 import 실패. **수정지시:** P0 게이트에 "Oracle VM에서 ifcopenshell+pygltflib 실제 import 성공" 라이브검증을 추가하고 버전 0.8.x 단일화. §7-1 함정에 이 모순을 명시.

**[권고 5]** `propai://...#sha256=` 논리 URI는 좋으나, 기존 `object_store`는 이미 `design/{tenant_id}/{content_hash}` content-addressable. 새 URI 스킴이 기존 dedup 키와 충돌/이중화되지 않는지 미검토. **수정지시:** artifact_store가 기존 content_hash를 sha256 canonical과 **동일 해시로 통일**하는지 P0에서 확인.

## ④ 핵심 원칙 누락

대부분 반영됨(HITL S3/4/6/8·hash/version·무목업·evidence·render≠buildable·area_119/solar_61_86 분리·source/version verified키). 그러나:

**[치명 4] special_parcel "확정%는 POSSIBLE" + "다필지 분석주소=대표 개발가능필지" 규칙(메모리 `special_parcel_detect`) 미반영.** 계획 P1 게이트는 "BLOCKED→차단"만 다루고, POSSIBLE 등급의 확정도 표기·다필지 대표필지 선정 로직이 validated_parcel 계약에 없다. envelope/mass를 어느 필지 기준으로 산출하는지 불명확 → 다필지에서 면적 SSOT 붕괴(메모리 `multiparcel_area_parity` "raw 금지") 재발 위험. **수정지시:** validated_parcel.json에 `representative_pnu`·`developability_confidence` 필드 추가, envelope는 `effectiveLandAreaSqm`(통합면적) 입력 강제.

**[권고 6]** evidence 계약 6필드 중 `confidence`·`provenance`가 rule_trace 계약(`evidence_hash`만)과 분리됨. 둘을 한 계약으로 통일하지 않으면 추적성 이원화.

## ⑤ 단계 의존성 / 게이트 / PR 크기 / 멀티세션

**[치명 5] 멀티세션 규약이 작동 불가능 — `scripts/coord.sh`·`scripts/new-worktree.sh`·`WORKTREES.md`·`coordination/`가 현 워크트리에 모두 부재**(find 결과 0건). CLAUDE.md와 계획 §4/§6이 전제하는 도구가 이 브랜치에 없다. 계획대로 `coord.sh claim` 하라고 지시하면 첫 명령에서 실패. **수정지시:** P0 W1에서 coord 인프라의 소재(다른 워크트리/공유 .git) 확인 또는 부트스트랩을 명문화. 부재 시 멀티세션 절은 "수동 git branch 확인 + PR 라벨"로 폴백 규약 제시.

**[권고 7]** "각 PR ≤600 LOC"인데 P1 PR①(area_119+solar 분리 + 4경로 회귀)은 회귀 포함 시 600 초과 확실. **수정지시:** 분리 PR과 소비처 배선 PR을 명시 분할(추출→배선→회귀 3단).

**[권고 8]** P6 approval_service가 P3b governance의 render guard와 상태enum을 공유하는지 의존성 불명. S8 미승인→렌더금지 enforce가 P3b(가드)와 P6(상태머신) 어느 쪽 소유인지 단일화 필요.

## ⑥ 우리 게이트와의 정합성

**[권고 9] "코드리뷰 ≥9.5"는 분양앱 9.5게이트(메모리 `sales_app_growth_loop`)에서 차용했으나 C2R 도메인 기준 미정의.** 점수 루브릭 없이 9.5는 무의미. **수정지시:** C2R용 게이트 기준(geometry sanity·rule_trace origin 100%·무날조)을 수치화.

**[권고 10] safe-deploy.sh 실내용 미검증 상태로 "blue-green" 가정.** grep이 origin/main·blue·green 매치 0건 — 스크립트가 실제 어떤 메커니즘인지 계획이 확인 안 함. 메모리 `oracle_deploy`는 "SSH 수동·`deploy.sh origin/main`"이라 안내. **수정지시:** 배포 절차를 safe-deploy.sh 실독 후 확정(P0 게이트).

---

치명결함 5건 / 권고 10건