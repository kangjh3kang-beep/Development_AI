"""계약 공용 타입 별칭 — 값역 제약으로 무음 범위이탈 방지.

Probability: 신뢰도·유사도·합성신뢰도 등 [0,1] 강제. 게이트가 임계와 비교하므로 범위이탈
(<0 또는 >1)은 오통과/오차단을 유발 → pydantic 검증에서 거부(무음 오판 0).
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
