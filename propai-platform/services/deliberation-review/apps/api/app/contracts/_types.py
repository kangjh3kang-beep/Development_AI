"""계약 공용 타입 별칭 — 값역 제약으로 무음 범위이탈 방지.

Probability: 신뢰도·유사도·합성신뢰도 등 [0,1] 강제. 게이트가 임계와 비교하므로 범위이탈
(<0 또는 >1)은 오통과/오차단을 유발 → pydantic 검증에서 거부(무음 오판 0).
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
# 유사도(코사인 등) — 음수 허용([-1,1]). 1 초과/-1 미만은 무음 범위이탈로 거부.
Similarity = Annotated[float, Field(ge=-1.0, le=1.0)]
# 측정치/한계치/시뮬값 — nan/inf 거부. nan<=limit이 False로 평가돼 무음 COMPLIANT 오판정되던 것 차단.
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
