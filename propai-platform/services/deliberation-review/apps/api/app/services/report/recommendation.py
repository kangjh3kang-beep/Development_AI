"""L6 — 보완권고 생성(근거접지, INV-29). 부적합/조건부/미흡 항목별 권고. 임의 권고 금지.

권고는 어느 기준/조문 충족을 위한 것인지 basis_article로 접지. 근거 없으면 권고 보류.
"""
from __future__ import annotations

from pydantic import BaseModel


class RecommendationResult(BaseModel):
    target_variable: str | None = None
    text: str | None = None
    basis_article: str | None = None
    grounded: bool = False


class Recommendation:
    def make(self, finding: dict) -> RecommendationResult:
        basis = finding.get("basis_article")
        target = finding.get("target_variable")

        if not basis:
            # 근거 미접지 — 임의 권고 금지, 보류.
            return RecommendationResult(target_variable=target, text=None, basis_article=None, grounded=False)

        verdict = finding.get("verdict")
        text = f"{target} 항목이 {basis} 기준에 미달({verdict}). 해당 기준 충족을 위한 보완 필요."
        return RecommendationResult(
            target_variable=target, text=text, basis_article=basis, grounded=True
        )
