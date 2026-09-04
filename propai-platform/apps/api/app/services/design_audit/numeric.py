"""설계심사(Design Audit) 숫자 정규화 공용 가드 — R1 HIGH-2 공용화.

오케스트레이터(design_audit_orchestrator._num)와 라우터(routers/design_audit._coerce_numeric)가
각자 따로 'bool·NaN·inf·비수치 거부' 가드를 들고 있었는데, 라우터 쪽이 이 가드 없이 문자열을
그대로 float() 변환해 "units":"inf" 같은 입력이 통과 → 8~9엔진 오케스트레이션을 전부 끝낸 뒤
JSON 직렬화 단계에서 `ValueError: Out of range float values are not JSON compliant`로 500을
내는 결함(라이브 재현)을 만들었다. 이 모듈이 두 소비처의 공용 코어다 — 여기 하나만 고치면
전역이 따라온다(버그수정 정책: 공용화 수정).

의존성 0(표준 라이브러리만) — 라우터 모듈 레벨에서 안전하게 임포트할 수 있다
(오케스트레이터 전체를 임포트하면 U5 미배포 환경에서 라우터 등록 자체가 깨질 위험이 있어
지연 임포트하는 기존 정책과 무관하게, 이 파일은 항상 가볍다).
"""

from __future__ import annotations

import math
from typing import Any


def finite_float(value: Any) -> float | None:
    """유한 실수만 통과(bool·NaN·inf·비수치 → None) — 가짜 수치 금지.

    bool은 산술적으로 int의 서브클래스라 float(True)==1.0이 통과해버리는 오염을 막고,
    NaN/Inf는 math.isfinite로 걸러 JSON 비적합 값이 하류(직렬화·비교연산)로 새지 않게 한다.
    """
    if isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None
