"""근거 게이트(grounding) — P3. LLM 설명문의 수치를 커널 산출값과 대조해 가짜수치 적발.

원칙: 화면에 표시되는 숫자는 전부 커널(AutoDesignEngine) 산출값이어야 한다.
LLM이 설명문(6섹션 해석 등)에서 산출값과 다른 건폐율·용적률·세대수·층수를 말하면
flagged(할루시네이션)로 표시해 결론에서 배제한다. 순수 결정론(정규식), LLM·외부호출 없음.
"""

from __future__ import annotations

import re
from typing import Any


def _nums(pattern: str, text: str) -> list[float]:
    out: list[float] = []
    for m in re.findall(pattern, text):
        try:
            out.append(float(m))
        except Exception:  # noqa: BLE001
            continue
    return out


def ground_check(summary: dict[str, Any], text: str) -> dict[str, Any]:
    """커널 summary 대비 설명문 수치 일관성 검증.

    반환: {grounded:[...], flagged:[{metric,kernel,claimed,reason}], confidence:int|None}
    flagged가 있으면 해당 수치는 신뢰 불가(표시 배제 권고).
    """
    text = text or ""
    grounded: list[str] = []
    flagged: list[dict[str, Any]] = []

    def check(label: str, kernel_val: Any, nums: list[float], tol: float) -> None:
        if kernel_val is None or not nums:
            return
        try:
            kv = float(kernel_val)
        except Exception:  # noqa: BLE001
            return
        if any(abs(n - kv) <= tol for n in nums):
            grounded.append(f"{label} {kernel_val}")
        else:
            flagged.append({
                "metric": label, "kernel": kernel_val, "claimed": nums,
                "reason": f"{label} 본문값 {nums} ≠ 산출값 {kernel_val}",
            })

    # 라벨 앵커 기반(노이즈 최소화): 건폐율·용적률은 라벨 직후 숫자%만.
    check("건폐율", summary.get("bcr_percent"), _nums(r"건폐율[^0-9]{0,8}(\d+\.?\d*)\s*%", text), 0.6)
    check("용적률", summary.get("far_percent"), _nums(r"용적률[^0-9]{0,8}(\d+\.?\d*)\s*%", text), 0.6)
    check("세대수", summary.get("total_units"), _nums(r"(\d+)\s*세대", text), 0.5)
    check("층수", summary.get("num_floors"), _nums(r"(?:지상\s*)?(\d+)\s*개?\s*층", text), 0.5)
    check("주차", summary.get("parking_count"), _nums(r"주차[^0-9]{0,8}(\d+)\s*대", text), 0.5)

    total = len(grounded) + len(flagged)
    conf = round(100 * len(grounded) / total) if total else None
    return {"grounded": grounded, "flagged": flagged, "confidence": conf}
