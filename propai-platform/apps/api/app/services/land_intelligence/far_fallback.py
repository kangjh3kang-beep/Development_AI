"""용적률 가정치 폴백 정직 표기 — 표준 문구 SSOT.

★P3(PR#292) 후속 스윕(2026-07-15 감사): 용적률 상한 미확보 시 가정치(250%/200% 등)가
조용히 들어가는 경로가 auto_recommend(수지 추천) 외에 solar_envelope(매스/층수 추정)에도
있었다. 고지 문구가 경로마다 따로 조립되면 표현이 발산하므로 이 모듈을 문구의 단일
출처로 둔다 — 한 곳을 고치면 전 표면(추천 far_disclosure·rough degraded_notes·
매스 assumptions)이 따라온다.

값 정책: 폴백 수치 자체는 각 경로의 기존 값을 유지한다(무회귀 — 랭킹·상대비교 유효).
이 모듈은 '표기'만 담당한다.
"""

from __future__ import annotations


def far_fallback_disclosure(assumed_pct: float) -> str:
    """용적률 가정치 사용 시의 표준 정직 고지 문구.

    auto_recommend_top3(PR#292)가 쓰던 문구와 동일 형식 — 소비처(프론트 배너·
    degraded_notes·assumptions)가 같은 문장을 보게 한다.
    """
    pct_label = f"{assumed_pct:g}%"
    return (
        f"용도지역 용적률 상한 미확보 — {pct_label} 가정치 기준 산정(참고용). "
        "GFA·세대수·매출·ROI 전 수치가 가정치 기반이므로 용도지역 확정 후 재산정이 필요합니다."
    )
