"""R2 — 라이브 외부 호출 단일 choke point. 분석(소비)경로에서 사용 금지(INV-13).

공급측 harvester/주기 정합잡만 LiveNetwork를 사용. dev/mock 환경에서는 실제 호출 비활성(NetworkError).
소비 경로가 이 모듈을 import/사용하지 않음을 정적검사로 강제(test_consume_static).
"""
from __future__ import annotations


class NetworkError(Exception):
    """라이브 외부 호출 실패/비활성. 호출자는 fallback으로 흡수."""


class LiveNetwork:
    def get(self, url: str) -> bytes:
        # dev/mock: 실제 라이브 호출 비활성. 공급측은 실패를 fallback으로 흡수한다.
        raise NetworkError(f"live network disabled (mock env): {url}")
