# Stage 4 API Latency Report

- 생성 시각(UTC): 2026-05-30T06:27:09.577211+00:00
- 전체 판정: PASS

## 목표
- API p95 <= 0.200초
- 요청 타임아웃 <= 2.000초
- 인증 엔드포인트 측정 포함: YES

## 엔드포인트 결과
- `/api/v1/system/integration/status` (public): p95 0.0019초, 평균 0.0015초, timeout 0회, 상태검증 PASS, 판정 PASS
- `/api/latest` (public): p95 0.0018초, 평균 0.0015초, timeout 0회, 상태검증 PASS, 판정 PASS
- `/api/v1/system/version` (authenticated): p95 0.0034초, 평균 0.0028초, timeout 0회, 상태검증 PASS, 판정 PASS
