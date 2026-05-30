# Stage 3 Benchmark Report

- 생성 시각(UTC): 2026-05-29T20:55:57.527127+00:00
- 전체 판정: PASS

## IFC 정확도
- MAE: 0.9032% (목표 <= 2.0%)
- 케이스 수: 8
- 판정: PASS

## Monte Carlo 성능
- 시뮬레이션: 10000회 x 3회
- p95 시간: 0.0617초 (목표 <= 30.0초)
- 평균 시간: 0.0376초
- 판정: PASS

## Real IFC Fixture 준비도
- manifest 상태: parsed
- 등록 fixture: 3개
- 로컬 사용가능: 3개
- 파싱 성공: 3개
- 최소 요구 파싱 수: 3개 (충족: True)
- 실 IFC MAE: 0.0% (목표 <= 2.0%)
- 실 IFC 판정: PASS

## 참고
- 골든셋: `/home/kangjh3kang/My_Projects/Development_AI/propai-platform/tests/fixtures/ifc/golden_quantity_reference.v1.json`
- 실 IFC manifest: `/home/kangjh3kang/My_Projects/Development_AI/propai-platform/tests/fixtures/ifc/real_ifc_manifest.v1.json`
