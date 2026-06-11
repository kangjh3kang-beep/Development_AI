# PropAI 업그레이드 인수인계·실행계획 (2026-06-11)

> 다른 모델(Opus 4.8 등)·새 세션·다른 개발자가 그대로 이어받을 수 있는 실행 문서.
> 각 항목에 "실행 프롬프트"가 포함되어 있어 복사-붙여넣기로 작업을 재개할 수 있다.

---

## 0. 보안정책 분류 결과 (요청에 대한 정직한 답)

**Fable 5(또는 어떤 Claude 모델) 보안정책에 걸리는 작업: 없음.**
본 프로젝트의 모든 작업(계산엔진·CAD/BIM·워크플로우·인증·빌드)은 정상적인 소프트웨어 개발로 정책 제한 대상이 아니다. 진행 중 중단됐던 지점들의 실제 원인과 해법:

| 중단 원인 | 정책 여부 | 해법 (적용됨) |
|---|---|---|
| 서브에이전트의 셸(Bash/PowerShell) 실행 거부 | ❌ 권한 설정 문제 | 에이전트는 파일 도구(Read/Edit/Grep)만 사용, 컴파일·테스트는 메인 루프가 중앙 실행 |
| API rate limit (서버 일시 제한) | ❌ 인프라 문제 | Workflow resume(캐시 재개)으로 실패분만 재실행 |
| 키 로테이션 (Supabase·Anthropic·지갑) | ❌ 사람 전용 작업 | docs/SECURITY_KEY_ROTATION.md 절차서 — **사용자 직접 수행 필요** |

→ Opus 4.8로 넘길 "정책 차단분"은 없다. 이 문서는 정책이 아니라 **세션 연속성**을 위한 인수인계다.

---

## 1. 현재 상태 스냅샷 (2026-06-11)

### 완료 (이 세션)
- **보안·시크릿**: .env.example 유출 키 제거, 운영 가드, bcrypt 4.x 호환 전환(passlib 제거), 무인증 엔드포인트 인증, SSRF/XSS 수정
- **Critical 계산버그 4 + 세법 고도화 9**: 양도세 이중차감, 취득세 이중계상, equity 이익 합산, 토큰 배당 DoS, 재건축환수 2024법, 단기중과, 취득세 슬라이딩, 등록면허세, 인지세, 분양자부담 분리, PF 분할실행 이자, MC 수렴판정, 유닛믹스 전용률
- **CI 복구**: 루트 ci.yml + 배포 전 테스트 게이트 (기존: 무테스트 즉시배포)
- **3대 분석 문서**: PLATFORM_FEATURE_AUDIT / COMPETITIVE_RESEARCH / UPGRADE_BLUEPRINT (27개 워크패키지 정의)
- **웨이브 1 (WP-01~13) 구현·검증 완료**: 파이프라인 재분석 루프, SSOT provenance, CAD DXF 직변환, 경매/G2B CTA, 적산-수지 연동, 스텁 오케스트레이터 청산, AI SSE 스트리밍 — 신규 테스트 55+8+12개 통과
- **웨이브 2 (WP-14~22)**: WP-17·18·21·22 완료, WP-14·15·16·19·20 재실행 중

### 남은 작업 (우선순위순)
1. 웨이브 2 잔여 5개 (재실행 중 — 아래 §2 프롬프트로 재개 가능)
2. 웨이브 3: WP-23(rerun pytest)·24(패널 환류)·25(CAD 프론트 통합)·26(구스택 삭제)
3. 통합 검증: 백엔드 전체 pytest + 프론트 type-check + vitest + next build
4. 사용자 액션: 키 로테이션 (docs/SECURITY_KEY_ROTATION.md)

---

## 2. 작업 재개 프롬프트 (복사해서 사용)

### 2-1. 마스터 재개 프롬프트 (어느 세션이든 첫 입력)
```
PropAI 플랫폼(WSL: ~/My_Projects/Development_AI/propai-platform, Windows UNC:
\\wsl$\Ubuntu\home\kangjh3kang\My_Projects\Development_AI\propai-platform) 업그레이드를 이어받아라.
필독 문서(순서대로):
1. docs/HANDOFF_EXECUTION_PLAN_2026-06-11.md  ← 이 문서 (현재 상태)
2. docs/UPGRADE_BLUEPRINT_2026-06-11.md       ← 27개 워크패키지 스펙 (구현 계약)
3. docs/PLATFORM_FEATURE_AUDIT_2026-06-11.md  ← 갭 분석 근거
원칙: additive·하위호환, 기존 스타일 준수, 가짜값 대신 정직한 '데이터 없음', 모든 수정에 정답값 회귀 테스트.
검증 명령:
- 백엔드: cd apps/api && .venv/bin/python -m pytest tests/ -q (단, test_auction_demock_court.py·test_molit_client.py는 기존 깨짐 — 제외)
- 프론트: cd apps/web && pnpm type-check && npx vitest run && pnpm build
완료 기준: 블루프린트 WP-27 체크리스트 전체 통과 + next build 성공.
```

### 2-2. 웨이브 2 잔여 5개 (각각 독립 실행 가능)
각 프롬프트 공통 머리말: *"docs/UPGRADE_BLUEPRINT_2026-06-11.md ⑤ 워크패키지 목록에서 해당 WP 행과 관련 설계 섹션을 읽고 구현하라. 수정 허용 파일 외 수정 금지."*

| WP | 한 줄 스펙 | 파일 |
|---|---|---|
| WP-14 | StageRerunRequest에 stage_overrides(다단계)·previous_result.stages→options['previous_stage_data'] 주입·응답 summary 추가. WP-01이 양형(list/dict) 수용 완료 | apps/api/app/routers/pipeline.py |
| WP-15 | provenance vitest 6케이스 — WP-02 구현 주의: costData user stamp는 "이전값과 달라진 비null 키만" 기록 | apps/web/lib/useProjectContextStore.provenance.test.ts (신규) |
| WP-16 | save/load 인증+tenant 소유권(403), CADSaveRequest 매스치수 3필드, GET export-edited-dxf(WP-04의 create_dxf_from_edited_points 사용, 저장본 없으면 404), mc_results dict 교정, drawing_type 5종, footprint_sqm. 테스트 401/404/echo/section/footprint | apps/api/app/routers/design_v61.py, tests/test_design_v61_router.py |
| WP-19 | lib/runtime-mode.ts 신설(mock 판정 SSOT `==="true"`), api-client에 apiV1BaseUrl 공개, designApiBase()+4t8t.net 하드코딩 삭제→호출 7곳 교체 | runtime-mode.ts(신규), api-client.ts, CadBimIntegrationPanel.tsx, (dashboard)/layout.tsx 외 직독 페이지 |
| WP-20 | 미마운트 app/routers/drawing.py 경로 diff 후 필요분 정본 포팅→삭제 보고, test_export_endpoints repoint(현재 test_site_plan 실패 중 — 함께 해결), in-memory version_control.py(+테스트) 삭제 보고, ComplianceBuildingModel 리네임+alias | drawing.py, test_export_endpoints.py, version_control.py+테스트, cad_auto_correction_service.py, parametric_cad_service.py |

### 2-3. 웨이브 3 (웨이브 2 완료 후)
| WP | 한 줄 스펙 | 파일 |
|---|---|---|
| WP-23 | rerun pytest 6항목: payload 복원(500/60/200 미사용), stage_overrides·applied_overrides, cost 재계산, sale_price_source="user", report SKIPPED+data, 하위호환 | apps/api/tests/test_project_pipeline_rerun.py (신규) |
| WP-24 | handleRerun→/pipeline/rerun-stage 전환(flat→per-stage 파싱, STAGE_ORDER 최초 단계, previous_result.stages 동봉), saveToStore 환류(cost·compliance·design unit), assumed_fields SSOT 시드 제외 | apps/web/components/pipeline/ProjectPipelinePanel.tsx |
| WP-25 | CADEditor undo/redo(스냅샷 MAX50, Ctrl+Z)+매스치수 bbox 저장+apiClient 인증+편집본 DXF 버튼+onMetricsChange / LiveProFormaStrip 신규(400ms 디바운스 unit-mix/simulate+footprint_sqm, 읽기전용) / CadBimIntegrationPanel 스트립 마운트+3단계 스테퍼+도면다듬기 CTA+DXF 종류 셀렉트 | CADEditor.tsx, LiveProFormaStrip.tsx(신규), CadBimIntegrationPanel.tsx |
| WP-26 | 구세대 CAD 스택 삭제 — 블루프린트 §3-6 목록. 각 파일 grep 잔존 import 0건 검증 후 삭제. GenerativeDesignPanel(WP-21로 의존 제거됨)·types.ts 보존 | §3-6 목록 |
| WP-27 | 통합 검증 — §2-1 마스터 프롬프트의 검증 명령 + 블루프린트 WP-27 행 수동 체크리스트 | (소스 무수정) |

### 2-4. 전체 테스트 잔여 실패 트리아지 (별도 트랙, 병렬 가능)
직전 전체 실행(20 failed/2506 passed) 중 이 세션에서 13건 수정 완료. 잔여 추정 ~7건:
```
test_v2_feasibility_router.py::TestVCSEndpoints (2건 — 무인증 TestClient로 인증 보호 VCS 호출, 사전 존재. 인증 픽스처 추가로 해결)
test_workers/test_parse_large_ifc.py (2건 — 워커 태스크, 사전 존재)
test_80_percent_push.py::TestKakaoHandler (1건), test_billing_metering.py (1건), test_celery_tasks.py (2건 — beat_schedule/task_names 카운트 단언이 스텁 삭제로 변동 가능 → 카운트 갱신)
test_coverage_80_final.py·test_deep_coverage.py·test_heavy_services.py (드론 키 부재 — 사전 존재)
test_design_v61_router.py 2건 → WP-16이 해결
```
프롬프트: *"위 목록을 하나씩: ①현재 코드로 재실행 ②실패 원인이 사전존재(스펙 드리프트/환경)인지 이번 변경인지 git stash 비교로 판정 ③사전존재면 현행 스펙에 맞게 테스트 교정, 이번 변경이면 코드 수정. 전부 정답값 고정으로."*

---

## 3. 사용자(사람) 전용 액션 — 모델이 대신 못 함
1. **키 로테이션** (docs/SECURITY_KEY_ROTATION.md): JWT(GitHub 유출분)·Supabase DB 비번·배포자 프라이빗키·ANTHROPIC_API_KEY
2. **git 커밋·푸시 결정**: 변경분 검토 후 커밋 (정리 파일 40+개는 스테이징 완료 상태)
3. **Cloudflare/Railway 환경변수**: POSTGRES_PASSWORD·JWT_SECRET_KEY 주입 (compose가 이제 미주입 시 기동 거부)

---

## 4. 차기 로드맵 (빌드 완료 후 — 혁신 차별화)
경쟁 리서치(docs/COMPETITIVE_RESEARCH_2026-06-11.md) 기반 우선순위:

| # | 기능 | 근거 (경쟁 공백) | 실행 프롬프트 요지 |
|---|---|---|---|
| R1 | **세후 IRR 통합 현금흐름** | 한국 플랫폼 0개, ARGUS는 한국세제 모름 | 38종 세금 산출을 cashflow_generator 타임라인에 시점별(취득=month0, 보유=연차, 양도=정산) 주입 → after-tax IRR/ROE 산출 + 회귀 테스트 |
| R2 | **법령 시행일 버전드 룰엔진** | 랜드북도 미보유 | regional_tax_data의 세율·구간을 (effective_from, effective_to) 메타로 외부화(JSON/DB), 거래일 기준 자동 선택, 2026-05-09 중과배제 종료 케이스 테스트 |
| R3 | **K-RPLAN 유닛플랜 생성** | Maket(단독주택)↔랜드북(편집불가) 사이 공백 | LH/SH 표준평면+분양공시 평면 수집 파이프라인 → 기존 design_spec JSON 스키마에 한국 유닛 문법(베이수·코어타입·발코니) 확장 → 법규 검증기를 생성 루프에 통합 |
| R4 | **web-ifc 실 IFC 내보내기** | 국내 최초 가능 | @thatopen/components v3.4(MIT)+web-ifc로 IfcProject→Storey→Wall/Slab 조립, 설계사 Revit 직결 |
| R5 | **AVM 실모델** | 현재 휴리스틱 폴백 | MOLIT 실거래 수집→XGBoost 학습→MLflow 등록→폴백 탈출 (ml/ 디렉터리 신설) |

---

*작성: 2026-06-11 세션. 질문 발생 시 블루프린트 ⑤ 워크패키지 표가 단일 진실 출처(SSOT)다.*
