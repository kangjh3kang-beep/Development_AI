"""PropAI AVM 학습 파이프라인 패키지 (R5).

학습/등록 전용 패키지 — 서빙 코드는 두지 않는다.
레거시 서빙(`apps/api/services/avm_service.py`)의 MLflow 3단계 폴백 로드 경로
(Production → Staging → 면적 기반 폴백)가 이 파이프라인이 Production에 등록한
모델을 자동 승격하므로, 별도의 서빙 배선이 필요 없다.

실행:
    python -m apps.api.ml.avm.train --lawd-cd 11680 --months 12
"""
