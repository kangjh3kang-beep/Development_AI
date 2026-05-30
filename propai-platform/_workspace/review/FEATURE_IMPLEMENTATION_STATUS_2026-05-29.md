# 플랫폼 기능별 구현현황 비교분석 및 단계별 구현계획 (2026-05-29)

## A. 목표 기준
- API 평균 응답시간 <= 200ms (LLM 제외)
- LLM 응답시간 <= 5초
- Monte Carlo 10,000회 <= 30초
- 가용성 >= 99.9%
- IFC 물량산출 정확도 MAE < 2%

근거: `PropAI_v58_마스터인덱스.md:881`, `:882`, `:883`, `:899`, `:116`

## B. 현재 구현 규모(코드 기준)
- API 라우터 등록: 64개 (`apps/api/main.py`)
- 서비스 모듈: 62개 (`apps/api/services/*.py`)
- 테스트: unit 76 / benchmarks 7 / load 2

## C. 기능군별 비교 매트릭스
| 기능군 | 라우터 | 서비스 | 테스트연결 항목수 | 이슈표식 항목수 | 구현성숙도 점수(0-100) | 판정 |
|---|---:|---:|---:|---:|---:|---|
| BIM/공사비/리스크 | 6 | 9 | 12 | 0 | 80.0 | 양호 |
| ESG/에너지 | 5 | 6 | 6 | 0 | 54.5 | 개선필요 |
| 금융/세무/계약 | 6 | 4 | 7 | 0 | 70.0 | 보통 |
| 기타 | 8 | 15 | 16 | 4 | 37.6 | 개선필요 |
| 디지털트윈/IoT/운영 | 6 | 7 | 8 | 0 | 61.5 | 보통 |
| 법규/인허가 | 4 | 5 | 6 | 1 | 58.7 | 개선필요 |
| 설계/CAD | 3 | 4 | 3 | 0 | 42.9 | 개선필요 |
| 에이전트/보고 | 4 | 4 | 7 | 0 | 87.5 | 양호 |
| 인증/권한 | 4 | 2 | 5 | 0 | 83.3 | 양호 |
| 입지/AVM/시장 | 8 | 6 | 10 | 1 | 63.4 | 보통 |
| 프로젝트/대시보드 | 4 | 0 | 4 | 0 | 100.0 | 양호 |

점수 산식: `(테스트연결/항목수)*100 - 이슈표식*8` (정량 우선순위 산정용 내부 지표)

## D. 핵심 갭(우선순위)
1. 벤치마크 테스트 일부가 목표 증명형이 아니라 계약검증 위주 -> 실데이터 벤치 인프라 필요 (Stage 4 API p95 게이트 1차 해소)
2. 인허가/ESG 일부 로직이 정적 규칙/상수 의존 -> 동적 규정/지표 피드 연동 확대 필요
3. IFC/Monte Carlo 목표(정확도/처리시간)의 CI 자동 측정 파이프라인 부재 (Stage 3 1차 해소)
4. 전체 백엔드 테스트는 로컬 의존성(casbin 등) 정비가 필요

## E. 이번 턴 구현 완료사항
- 대시보드 KPI 동적화: `apps/api/routers/dashboard.py`
- KDX 스트림 실데이터화: `apps/api/routers/kdx.py`
- 수요예측 Redis DSN 환경변수화: `apps/api/services/demand_forecast_service.py`
- 벤치마크 계약테스트 활성화: `tests/benchmarks/bench_ifc.py`, `tests/benchmarks/bench_graphql.py`
- P0 회귀테스트 추가: `tests/unit/test_platform_p0_regressions.py`
- KDX 스트림 보안계약 테스트 추가: `tests/unit/test_kdx_stream_security_contract.py`
- 인허가 규칙 외부화(JSON+ENV): `apps/api/services/seumter_permit_service.py`, `apps/api/config_data/seumter_permit_rules.default.json`
- GRESB 벤치마크 외부화(JSON+ENV): `apps/api/app/services/esg/gresb_scoring_service.py`, `apps/api/config_data/gresb_benchmarks_2025.default.json`
- IFC 탄소계수 외부화(JSON+ENV): `apps/api/services/carbon_calculation_service.py`, `apps/api/config_data/carbon_factors_ifc.default.json`
- Stage 2 동적규칙 테스트 추가: `tests/unit/test_stage2_dynamic_rules.py`
- Stage 3 벤치 스크립트 추가: `scripts/perf/run_stage3_benchmarks.py`
- Stage 3 IFC 골든셋 추가: `tests/fixtures/ifc/golden_quantity_reference.v1.json`
- Stage 3 계약/벤치 테스트 추가: `tests/unit/test_stage3_benchmark_pipeline_contract.py`, `tests/benchmarks/bench_stage3_pipeline.py`
- Stage 3 strict 게이트 옵션 추가: `scripts/perf/run_stage3_benchmarks.py --fail-on-target-miss`
- Stage 3 실 IFC 최소요구 게이트 추가: `scripts/perf/run_stage3_benchmarks.py --require-real-ifc-min`
- 실 IFC 온보딩 자동화 스크립트 추가: `scripts/perf/onboard_real_ifc_fixtures.py`
- 실 IFC 교체 오케스트레이션 스크립트 추가(온보딩+strict 벤치): `scripts/perf/refresh_real_ifc_pipeline.py`
- incoming IFC 품질게이트 검증기 추가: `scripts/perf/validate_real_ifc_incoming.py`
- 실 IFC 온보딩 계약 테스트 추가: `tests/unit/test_stage3_real_ifc_onboarding_contract.py`
- 실 IFC 교체 오케스트레이션 계약 테스트 추가: `tests/unit/test_stage3_refresh_real_ifc_pipeline_contract.py`
- incoming IFC 품질게이트 계약 테스트 추가: `tests/unit/test_stage3_ifc_incoming_validation_contract.py`
- 컷오버 안전성 fail-path 테스트 추가: `tests/unit/test_stage3_ifc_incoming_validation_contract.py`(max-file-size), `tests/unit/test_stage3_refresh_real_ifc_pipeline_contract.py`(move 후 잔존 IFC 실패)
- 실 IFC 온보딩 익명화 강화 + 외부 경로 호환성 수정: `scripts/perf/onboard_real_ifc_fixtures.py`
- ifcopenshell 설치 및 실 IFC 샘플 생성: `scripts/perf/generate_real_ifc_samples.py`, `tests/fixtures/ifc/real_samples/*.ifc`
- Stage 3 CI 스케줄 워크플로우 추가: `.github/workflows/stage3-benchmark.yml`
- Stage 3 workflow_dispatch 컷오버 리허설 입력 추가: `run_refresh_rehearsal`, `refresh_mode`
- 실 IFC 확장 manifest/샘플 디렉터리 추가: `tests/fixtures/ifc/real_ifc_manifest.v1.json`, `tests/fixtures/ifc/real_samples/`
- Stage 3 상세계획 문서화: `_workspace/review/STAGE3_EXECUTION_PLAN_2026-05-29.md`
- Stage 4 API 레이턴시 벤치 스크립트 추가: `scripts/perf/run_stage4_api_latency_benchmarks.py`
- Stage 4 계약/벤치 테스트 추가: `tests/unit/test_stage4_api_latency_pipeline_contract.py`, `tests/benchmarks/bench_stage4_api_latency.py`
- Stage 3 CI 워크플로우를 Stage 3-4 게이트로 확장: `.github/workflows/stage3-benchmark.yml`
- Stage 4 상세계획 문서화: `_workspace/review/STAGE4_EXECUTION_PLAN_2026-05-30.md`

## F. 목표달성 단계별 구현계획 (실행순서)
### Stage 1 (이번 주)
- KDX WebSocket 액세스토큰 검증 + 테넌트 범위 질의 강제 (완료)
- KPI 하드코딩 제거 완료 및 회귀테스트 상시화 (완료)
- 결과검증: unit/benchmark 계약테스트 green 유지

### Stage 2 (2~3주)
- 인허가(Seumter) 규정/기간 동적화(지역/조건 기반) 1차 완료
- ESG/GRESB 외부 기준 벤치마크 연동 1차 완료
- 탄소계수(EPD) 외부 기준 연동 1차 완료(JSON+ENV)
- 결과검증: 규정정합 테스트 + 샘플 프로젝트 회귀 테스트

### Stage 3 (4~6주)
- IFC 골든셋 기반 MAE<2% 자동검증 파이프라인 구축 (1차 완료)
- Monte Carlo 10,000회 성능 측정 및 p95 리포트 자동화 (1차 완료)
- 결과검증: JSON/Markdown 리포트 자동생성 및 pytest 벤치 연계 완료
- CI 스케줄 + strict gate + 리포트 아티팩트 업로드 구성 완료
- 실 IFC 파싱 루프/MAE 계산 로직 1차 반영(파일 존재 시 자동 계산)
- 실 IFC 원본 온보딩 자동화(파일수집/manifest/비식별화) 완료
- 잔여작업: generated 샘플을 실 프로젝트 원본(비식별 완료본)으로 교체

### Stage 4 (지속운영)
- API p95(<=200ms) 자동측정 스크립트/리포트/strict gate 1차 완료
- Stage3-4 통합 워크플로우에 계약/벤치 테스트 포함 완료
- 잔여작업: 인증 필요 엔드포인트/실운영 경로 기반 레이턴시 샘플셋 확장

## G. 검증 결과 (이번 턴)
- `pytest -q tests/unit/test_stage2_dynamic_rules.py tests/unit/test_kdx_stream_security_contract.py tests/unit/test_platform_p0_regressions.py tests/unit/test_stage3_benchmark_pipeline_contract.py tests/unit/test_stage3_real_ifc_onboarding_contract.py tests/unit/test_stage3_refresh_real_ifc_pipeline_contract.py tests/unit/test_stage3_ifc_incoming_validation_contract.py tests/benchmarks/bench_ifc.py tests/benchmarks/bench_graphql.py tests/benchmarks/bench_stage3_pipeline.py`
- 결과: **42 passed, 1 warning** (오케스트레이션+incoming gate 계약 테스트 포함)
- `python scripts/perf/run_stage3_benchmarks.py --attempts 3 --n-simulations 10000`
- 결과: **overall PASS** (IFC MAE 0.9032%, Monte Carlo p95 0.067초)
- `python scripts/perf/refresh_real_ifc_pipeline.py --incoming /tmp/stage3_refresh_incoming --output-dir tests/fixtures/ifc/real_samples --manifest tests/fixtures/ifc/real_ifc_manifest.v1.json --keep-original-name --mode copy --source-label generated-local-sample --attempts 3 --n-simulations 10000 --require-real-ifc-min 3`
- 결과: **overall PASS** (incoming gate pass + IFC MAE 0.9032%, Monte Carlo p95 0.0578초, real IFC parsed_count 3)
- `python scripts/perf/refresh_real_ifc_pipeline.py --incoming tests/fixtures/ifc/incoming --output-dir tests/fixtures/ifc/real_samples --manifest tests/fixtures/ifc/real_ifc_manifest.v1.json --keep-original-name --mode move --source-label generated-local-sample --attempts 3 --n-simulations 10000 --require-real-ifc-min 3`
- 결과: **overall PASS** (incoming gate pass + IFC MAE 0.9032%, Monte Carlo p95 0.0617초, real IFC parsed_count 3, 실행 후 incoming 비움 확인)
- `PROPAI_STRICT_PERF_GATE=1 python scripts/perf/run_stage3_benchmarks.py --attempts 2 --n-simulations 10000 --fail-on-target-miss`
- 결과: **exit code 0 (strict gate pass)**
- `python scripts/perf/onboard_real_ifc_fixtures.py --incoming tests/fixtures/ifc/real_samples --output-dir /tmp/stage3_onboard_out --manifest /tmp/stage3_onboard_manifest.json --keep-original-name --mode copy`
- 결과: **exit code 0** (`output-dir` 저장소 외부 경로 호환성 검증)
- `python scripts/perf/run_stage3_benchmarks.py --attempts 1 --n-simulations 1000 --require-real-ifc-min 99 --fail-on-target-miss`
- 결과: **exit code 2 (실 IFC 최소요구 미충족 시 strict fail 정상동작)**
- `python scripts/perf/run_stage3_benchmarks.py --attempts 3 --n-simulations 10000 --require-real-ifc-min 3 --fail-on-target-miss`
- 결과: **overall PASS** (실 IFC parsed_count 3, real IFC MAE 0.0%)
- `pytest -q tests/unit/test_stage2_dynamic_rules.py tests/unit/test_kdx_stream_security_contract.py tests/unit/test_platform_p0_regressions.py tests/unit/test_stage3_benchmark_pipeline_contract.py tests/unit/test_stage3_real_ifc_onboarding_contract.py tests/unit/test_stage3_refresh_real_ifc_pipeline_contract.py tests/unit/test_stage3_ifc_incoming_validation_contract.py tests/unit/test_stage4_api_latency_pipeline_contract.py tests/benchmarks/bench_ifc.py tests/benchmarks/bench_graphql.py tests/benchmarks/bench_stage3_pipeline.py tests/benchmarks/bench_stage4_api_latency.py`
- 결과: **45 passed, 1 warning** (Stage4 API latency 계약/벤치 포함)
- `apps/api/.venv/bin/python scripts/perf/run_stage4_api_latency_benchmarks.py --attempts 20 --warmup 2 --fail-on-target-miss`
- 결과: **overall PASS** (`/api/v1/system/integration/status` p95 0.0014초, `/api/latest` p95 0.0012초)
- 제한: `tests/unit/test_kdx_feasibility_live_modules.py`는 로컬 `casbin` 의존성 부재로 수집 실패
