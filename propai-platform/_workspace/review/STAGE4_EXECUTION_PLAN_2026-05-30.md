# Stage 4 API Latency 상세 구현계획 및 실행기록 (2026-05-30)

## 1) 목적
- 플랫폼 핵심 목표 중 `API 평균/상위지연` 측정 공백을 해소한다.
- 목표 항목:
  - API p95 latency <= 200ms

## 2) 범위
- 구현
  - `scripts/perf/run_stage4_api_latency_benchmarks.py`
  - `tests/unit/test_stage4_api_latency_pipeline_contract.py`
  - `tests/benchmarks/bench_stage4_api_latency.py`
  - `.github/workflows/stage3-benchmark.yml` (Stage4 테스트/게이트 포함 확장)
- 산출물
  - `_workspace/review/perf/stage4_api_latency_report.json`
  - `_workspace/review/perf/stage4_api_latency_report.md`

## 3) 구현 전략
### A. 엔드포인트 p95 자동 측정
- ASGITransport 기반 in-process 호출로 네트워크 외부요인 제거
- 기본 측정 엔드포인트:
  - `/api/v1/system/integration/status`
  - `/api/latest`

### B. 성능 게이트
- 엔드포인트별 상태코드 정상성(`2xx/3xx`) + p95 목표 동시 검증
- 옵션:
  - `--p95-max-sec` (기본 0.2초)
  - `--fail-on-target-miss`
  - `PROPAI_STRICT_API_GATE=1`

### C. 리포트 자동화
- JSON: CI 파싱/게이트 판정
- Markdown: 리뷰 공유용 요약

## 4) 실행 명령
- Stage4 벤치 실행:
  - 기본(안전모드, public only):
    - `apps/api/.venv/bin/python scripts/perf/run_stage4_api_latency_benchmarks.py --attempts 20 --warmup 2 --fail-on-target-miss`
  - 인증 엔드포인트 포함(옵트인):
    - `apps/api/.venv/bin/python scripts/perf/run_stage4_api_latency_benchmarks.py --include-authenticated --authenticated-endpoints /api/v1/system/version --request-timeout-sec 1 --attempts 2 --warmup 0`
- Stage4 계약/벤치 테스트:
  - `pytest -q tests/unit/test_stage4_api_latency_pipeline_contract.py tests/benchmarks/bench_stage4_api_latency.py`

## 5) 실행 결과 (2026-05-30)
- Stage4 계약/벤치:
  - `pytest -q tests/unit/test_stage4_api_latency_pipeline_contract.py tests/benchmarks/bench_stage4_api_latency.py`
  - 결과: `4 passed, 1 warning`
- Stage3-4 게이트 세트:
  - `PROPAI_STRICT_PERF_GATE=1 PROPAI_STRICT_API_GATE=1 pytest -q tests/unit/test_stage3_benchmark_pipeline_contract.py tests/unit/test_stage3_real_ifc_onboarding_contract.py tests/unit/test_stage3_refresh_real_ifc_pipeline_contract.py tests/unit/test_stage3_ifc_incoming_validation_contract.py tests/unit/test_stage4_api_latency_pipeline_contract.py tests/benchmarks/bench_stage3_pipeline.py tests/benchmarks/bench_stage4_api_latency.py`
  - 결과: `25 passed, 1 warning`
- Stage4 리포트:
  - overall: `PASS`
  - `/api/v1/system/integration/status` p95: `0.0024초`
  - `/api/latest` p95: `0.0022초`

## 6) 후속
- 운영 환경 실측용 엔드포인트 셋을 `workflow_dispatch` 입력으로 확장
- 인증 경로 hang의 근본 원인(`SlowAPIMiddleware + BaseHTTPMiddleware + auth dependency` 체인) 분석 후 tenant-aware 측정 기본 활성화

## 7) 안정화 조치 (2026-05-30)
- 문제:
  - ASGITransport 기반 인증 엔드포인트 측정 시 응답 미완료(hang) 발생 가능
- 조치:
  - `--include-authenticated` 기본값을 `false`로 변경(옵트인)
  - 요청 단위 타임아웃 가드 추가: `--request-timeout-sec` (기본 2초)
  - timeout 발생 시 `status=598`, `timeout_count` 기록 후 해당 엔드포인트 조기 FAIL 처리
  - GitHub Actions 입력 `api_include_authenticated` 추가(기본 false)
- 검증:
  - `PROPAI_STRICT_PERF_GATE=1 PROPAI_STRICT_API_GATE=1 pytest -q tests/unit/test_stage3_benchmark_pipeline_contract.py tests/unit/test_stage3_real_ifc_onboarding_contract.py tests/unit/test_stage3_refresh_real_ifc_pipeline_contract.py tests/unit/test_stage3_ifc_incoming_validation_contract.py tests/unit/test_stage4_api_latency_pipeline_contract.py tests/benchmarks/bench_stage3_pipeline.py tests/benchmarks/bench_stage4_api_latency.py`
  - 결과: `25 passed, 1 warning`
