"""워커 테스트 공유 픽스처.

워커 태스크가 의존하는 외부 패키지(miniopy_async, paho, web3, ifcopenshell 등)가
테스트 환경에 설치되어 있지 않을 수 있으므로, sys.modules에 mock을 주입한다.
세션 종료 시 주입한 mock을 제거하여 다른 테스트에 영향을 주지 않는다.
"""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── 외부 패키지 mock 정의 (테스트 환경에 미설치된 패키지만) ──
# 계층 구조 모듈은 부모.자식 경로가 일관되도록 단일 MagicMock 트리로 생성한다.
# (patch()가 sys.modules["paho"].mqtt.client 경로로 탐색하기 때문)
# NOTE: 설치된 패키지(qdrant_client, httpx 등)는 mock하지 않는다.
_HIERARCHICAL: dict[str, list[str]] = {
    "paho": ["paho.mqtt", "paho.mqtt.client"],
    "web3": ["web3.providers"],
    "mlflow": ["mlflow.xgboost"],
    "evidently": ["evidently.report", "evidently.metric_preset"],
    "sklearn": ["sklearn.model_selection"],
    "reportlab": [
        "reportlab.lib", "reportlab.lib.colors",
        "reportlab.lib.pagesizes", "reportlab.lib.styles",
        "reportlab.lib.units", "reportlab.pdfbase",
        "reportlab.pdfbase.pdfmetrics", "reportlab.pdfbase.ttfonts",
        "reportlab.platypus",
    ],
}

_FLAT_MODULES = [
    "miniopy_async", "ifcopenshell", "replicate",
    "xgboost", "pandas", "openai",
]


@pytest.fixture(autouse=True, scope="session")
def _worker_mock_modules():
    """세션 픽스처: 워커 테스트 실행 전 mock 주입 → 종료 후 제거."""
    injected: list[str] = []

    for root, children in _HIERARCHICAL.items():
        if root in sys.modules:
            continue
        root_mock = MagicMock()
        sys.modules[root] = root_mock
        injected.append(root)
        for child in children:
            parts = child.split(".")
            obj = root_mock
            for part in parts[1:]:
                obj = getattr(obj, part)
            sys.modules[child] = obj
            injected.append(child)

    for mod_name in _FLAT_MODULES:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = MagicMock()
            injected.append(mod_name)

    yield

    # 워커 테스트 종료 후 주입한 mock 제거
    for key in injected:
        sys.modules.pop(key, None)


@pytest.fixture
def worker_settings() -> MagicMock:
    """워커 테스트용 설정 (MagicMock — 워커 코드가 참조하는 임의 속성 지원)."""
    s = MagicMock()
    s.minio_endpoint = "localhost:9000"
    s.minio_access_key = "minioadmin"
    s.minio_secret_key = "minioadmin"
    s.polygon_node_url = "https://rpc-amoy.polygon.technology/"
    s.escrow_contract_address = "0x961cba4A27D3080d8450789c91D4f30ff72E82E6"
    s.mlflow_tracking_uri = "http://localhost:5000"
    s.openai_api_key = "test-key"
    s.qdrant_url = "http://localhost:6333"
    return s


@pytest.fixture
def worker_ctx(worker_settings: MagicMock) -> dict:
    """arq 워커 컨텍스트 mock."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    return {
        "settings": worker_settings,
        "db": mock_db,
    }


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """AsyncSessionLocal mock (컨텍스트 매니저 지원)."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session
