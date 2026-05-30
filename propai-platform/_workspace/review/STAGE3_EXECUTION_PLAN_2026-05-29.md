# Stage 3 상세 구현계획 및 실행기록 (2026-05-29)

## 1) 목적
- 성능목표 중 미자동화 구간을 즉시 운영 가능한 벤치 파이프라인으로 전환한다.
- 목표 항목:
  - IFC 물량산출 정확도: MAE < 2%
  - Monte Carlo 10,000회: p95 < 30초

## 2) 범위
- 구현
  - `scripts/perf/run_stage3_benchmarks.py`
  - `scripts/perf/onboard_real_ifc_fixtures.py`
  - `scripts/perf/refresh_real_ifc_pipeline.py`
  - `scripts/perf/validate_real_ifc_incoming.py`
  - `tests/fixtures/ifc/golden_quantity_reference.v1.json`
  - `tests/unit/test_stage3_benchmark_pipeline_contract.py`
  - `tests/unit/test_stage3_real_ifc_onboarding_contract.py`
  - `tests/unit/test_stage3_refresh_real_ifc_pipeline_contract.py`
  - `tests/unit/test_stage3_ifc_incoming_validation_contract.py`
  - `tests/benchmarks/bench_stage3_pipeline.py`
- 산출물
  - `_workspace/review/perf/stage3_benchmark_report.json`
  - `_workspace/review/perf/stage3_benchmark_report.md`
  - (옵션) `_workspace/review/perf/stage3_monte_carlo.prof`

## 3) 구현 전략
### A. IFC 정확도 자동검증
- 골든셋(JSON) 기준으로 `expected` vs `actual`를 비교.
- 케이스별 면적/체적 절대오차율을 계산하고 평균(MAE%) 산출.
- 목표값 2% 이하를 pass/fail로 판정.

### B. Monte Carlo 10,000회 성능측정
- `apps/api/app/services/feasibility/monte_carlo_engine.py` 엔진으로 측정.
- `n=10,000` 기준 다회 반복 실행시간 측정, p95 계산.
- 목표값 30초 이하를 pass/fail로 판정.
- 필요 시 `--profile` 옵션으로 cProfile 파일 생성.

### C. 보고서 자동화
- JSON: CI 연계/머신 파싱용
- Markdown: 리뷰 공유/사람 확인용
- 공통 필드: 실행시각, 목표값, 실측값, pass/fail, overall 판정

## 4) 실행 명령
- Stage 3 벤치 실행:
  - `python scripts/perf/run_stage3_benchmarks.py --attempts 3 --n-simulations 10000`
- pytest 계약/벤치 검증:
  - `pytest -q tests/unit/test_stage3_ifc_incoming_validation_contract.py tests/unit/test_stage3_refresh_real_ifc_pipeline_contract.py tests/unit/test_stage3_real_ifc_onboarding_contract.py tests/unit/test_stage3_benchmark_pipeline_contract.py tests/benchmarks/bench_stage3_pipeline.py`

## 5) 검증 게이트
- 기본 게이트
  - 스크립트 실행 성공 + 리포트 파일 생성
  - IFC MAE 목표 통과
- 엄격 게이트(선택)
  - 환경변수 `PROPAI_STRICT_PERF_GATE=1`에서 `overall_pass == true`
  - 옵션 `--require-real-ifc-min N`으로 실 IFC 최소 파싱 개수 강제

## 6) 리스크 및 후속
- 로컬/CI 성능 편차로 Monte Carlo 시간 결과가 달라질 수 있음.
- 후속 액션:
  1. CI 러너 스펙 고정 후 stage3 스케줄러 잡으로 주기 실행 (**완료: workflow 추가**)
  2. IFC 실파일(ifcopenshell) 기반 골든셋으로 확장 (**진행중: manifest/샘플 디렉터리 + 온보딩/익명화 자동화 완료, 실 프로젝트 원본 교체 대기**)
  3. p95 악화 시 cProfile 상위 hot path 기반 튜닝

## 7) 실행 결과 (2026-05-29)
- pytest:
  - `pytest -q tests/unit/test_stage3_ifc_incoming_validation_contract.py tests/unit/test_stage3_refresh_real_ifc_pipeline_contract.py tests/unit/test_stage3_real_ifc_onboarding_contract.py tests/unit/test_stage3_benchmark_pipeline_contract.py tests/benchmarks/bench_stage3_pipeline.py`
  - 결과: `21 passed, 1 warning`
- 통합 회귀/벤치:
  - `pytest -q tests/unit/test_stage2_dynamic_rules.py tests/unit/test_kdx_stream_security_contract.py tests/unit/test_platform_p0_regressions.py tests/unit/test_stage3_benchmark_pipeline_contract.py tests/unit/test_stage3_real_ifc_onboarding_contract.py tests/unit/test_stage3_refresh_real_ifc_pipeline_contract.py tests/unit/test_stage3_ifc_incoming_validation_contract.py tests/benchmarks/bench_ifc.py tests/benchmarks/bench_graphql.py tests/benchmarks/bench_stage3_pipeline.py`
  - 결과: `42 passed, 1 warning`
- Stage 3 벤치 리포트:
  - `python scripts/perf/run_stage3_benchmarks.py --attempts 3 --n-simulations 10000`
  - 결과: `overall PASS` (IFC MAE 0.9032%, Monte Carlo p95 0.067초)
- 실 IFC strict pass 검증:
  - `python scripts/perf/run_stage3_benchmarks.py --attempts 3 --n-simulations 10000 --require-real-ifc-min 3 --fail-on-target-miss`
  - 결과: `overall PASS` (parsed_count=3, real IFC MAE=0.0%)
- 실 IFC 교체 오케스트레이션 검증:
  - `python scripts/perf/refresh_real_ifc_pipeline.py --incoming /tmp/stage3_refresh_incoming --output-dir tests/fixtures/ifc/real_samples --manifest tests/fixtures/ifc/real_ifc_manifest.v1.json --keep-original-name --mode copy --source-label generated-local-sample --attempts 3 --n-simulations 10000 --require-real-ifc-min 3`
  - 결과: `overall PASS` (incoming gate pass + IFC MAE 0.9032%, Monte Carlo p95 0.0578초, real IFC parsed_count=3)
- incoming dropzone consume 리허설:
  - `python scripts/perf/refresh_real_ifc_pipeline.py --incoming tests/fixtures/ifc/incoming --output-dir tests/fixtures/ifc/real_samples --manifest tests/fixtures/ifc/real_ifc_manifest.v1.json --keep-original-name --mode move --source-label generated-local-sample --attempts 3 --n-simulations 10000 --require-real-ifc-min 3`
  - 결과: `overall PASS` (incoming gate pass + IFC MAE 0.9032%, Monte Carlo p95 0.0617초, real IFC parsed_count=3, 실행 후 incoming 폴더 비움 확인)
- 온보딩 경로 호환성 검증:
  - `python scripts/perf/onboard_real_ifc_fixtures.py --incoming tests/fixtures/ifc/real_samples --output-dir /tmp/stage3_onboard_out --manifest /tmp/stage3_onboard_manifest.json --keep-original-name --mode copy`
  - 결과: `output-dir`가 저장소 외부여도 정상 완료 (manifest는 절대경로 저장)
- manifest 저장소 경로 정규화:
  - `python scripts/perf/onboard_real_ifc_fixtures.py --incoming tests/fixtures/ifc/real_samples --output-dir tests/fixtures/ifc/real_samples --manifest tests/fixtures/ifc/real_ifc_manifest.v1.json --keep-original-name --mode move`
  - 결과: `real_ifc_manifest.v1.json`이 최신 scrub/element_count 포맷 + 저장소 내부 경로로 갱신
- strict fail-path 검증:
  - `python scripts/perf/run_stage3_benchmarks.py --attempts 1 --n-simulations 1000 --require-real-ifc-min 99 --fail-on-target-miss`
  - 결과: `exit code 2` (실 IFC 최소요구 미충족 시 의도된 실패)
- 프로파일 샘플:
  - `python scripts/perf/run_stage3_benchmarks.py --attempts 1 --n-simulations 10000 --profile`
  - 산출물: `_workspace/review/perf/stage3_monte_carlo.prof`

## 8) CI 연계 상태 (2026-05-29)
- 워크플로우 추가: `.github/workflows/stage3-benchmark.yml`
- 스케줄: 매주 월요일 01:30 UTC
- strict gate:
  - `PROPAI_STRICT_PERF_GATE=1`
  - `python scripts/perf/run_stage3_benchmarks.py --fail-on-target-miss`
  - `python scripts/perf/run_stage3_benchmarks.py --require-real-ifc-min N` (workflow 기본값 3)
- workflow_dispatch 추가 입력:
  - `run_refresh_rehearsal` (true/false, 기본 false)
  - `refresh_mode` (copy/move, 기본 move)
- 온보딩:
  - `python scripts/perf/onboard_real_ifc_fixtures.py --mode copy --source-label internal-anonymized`
  - 기본값: `--scrub-owner-data` 활성화 (필요 시 `--no-scrub-owner-data`)
- 통합 갱신:
  - `python scripts/perf/refresh_real_ifc_pipeline.py ...` (온보딩+strict 벤치 일괄 수행)
  - 기본값: incoming 품질게이트 선행 실행 (`--no-validate-incoming`으로 비활성화 가능)
- 아티팩트 업로드:
  - `_workspace/review/perf/*` (JSON/MD/prof + incoming validation report)

## 9) Stage4 연계 (2026-05-30)
- `.github/workflows/stage3-benchmark.yml`를 Stage3-4 통합 게이트로 확장
- 추가 테스트:
  - `tests/unit/test_stage4_api_latency_pipeline_contract.py`
  - `tests/benchmarks/bench_stage4_api_latency.py`
- 추가 strict gate:
  - `python scripts/perf/run_stage4_api_latency_benchmarks.py --fail-on-target-miss`
