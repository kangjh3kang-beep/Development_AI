"""F-Parcel 배치 테스트 픽스처.

apps/api 루트를 sys.path 에 넣어 `app.*` 임포트가 되도록 한다.
FakeVWorld(라이브콜 0)는 _fakes 모듈에서 재사용한다.
"""

from __future__ import annotations

import os
import sys

import pytest

# apps/api 루트(= 이 파일에서 3단계 상위: parcel→foundation→tests→apps/api)를 path 최상단에 둔다.
_API_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _API_ROOT not in sys.path:
    sys.path.insert(0, _API_ROOT)

# 같은 디렉터리의 _fakes 를 import 하기 위해 디렉터리도 path 에 둔다.
_HERE = os.path.dirname(__file__)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _fakes import FakeVWorld  # noqa: E402


@pytest.fixture
def fake_vworld():
    """기본 FakeVWorld(확정 3 + 애매 1)."""
    return FakeVWorld()