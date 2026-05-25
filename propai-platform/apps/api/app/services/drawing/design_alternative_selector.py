"""설계 대안 선정기 — MCDM 가중합 + 몬테카를로 승률 산출."""

from __future__ import annotations

import random
from typing import Any

# MCDM 가중치
WEIGHTS: dict[str, float] = {
    "profit": 0.40,
    "legal": 0.30,
    "design": 0.20,
    "esg": 0.10,
}


def _normalize_scores(alts: list[dict], key: str) -> list[float]:
    """Min-Max 정규화 (0~1)."""
    vals = [a.get(key, 0.0) for a in alts]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return [1.0] * len(vals)
    return [(v - lo) / (hi - lo) for v in vals]


class DesignAlternativeSelector:
    """MCDM + 몬테카를로 기반 설계 대안 선정.

    입력: alternatives — [{profit_score, legal_score, design_score, esg_score, ...}]
    출력: {ranked, mc_results, winner}
    """

    def simulate(
        self,
        alternatives: list[dict[str, Any]],
        iterations: int = 5000,
        noise_pct: float = 0.10,
        seed: int | None = 42,
    ) -> dict[str, Any]:
        """대안 비교: MCDM 점수 + MC 승률."""
        if not alternatives:
            return {"ranked": [], "mc_results": [], "winner": None}

        n = len(alternatives)

        # ── MCDM 정규화 + 가중합 ──
        norm = {}
        for key in WEIGHTS:
            score_key = f"{key}_score"
            norm[key] = _normalize_scores(alternatives, score_key)

        mcdm_scores: list[float] = []
        for i in range(n):
            s = sum(WEIGHTS[k] * norm[k][i] for k in WEIGHTS)
            mcdm_scores.append(round(s, 4))

        # ── 몬테카를로 ──
        rng = random.Random(seed)
        win_counts = [0] * n

        for _ in range(iterations):
            noisy = []
            for i in range(n):
                noise = rng.gauss(0, noise_pct)
                noisy.append(mcdm_scores[i] * (1.0 + noise))
            winner_idx = max(range(n), key=lambda j: noisy[j])
            win_counts[winner_idx] += 1

        win_rates = [round(c / iterations * 100, 1) for c in win_counts]

        # ── 결과 정리 ──
        ranked = []
        for i in range(n):
            alt = alternatives[i].copy()
            alt["mcdm_score"] = mcdm_scores[i]
            alt["mc_win_rate"] = win_rates[i]
            ranked.append(alt)

        ranked.sort(key=lambda a: a["mcdm_score"], reverse=True)

        winner = ranked[0] if ranked else None

        return {
            "ranked": ranked,
            "mc_results": {
                "iterations": iterations,
                "noise_pct": noise_pct,
                "win_rates": win_rates,
            },
            "winner": winner,
        }
