"""설계제안 PDF 빌더 단위테스트 — 실 reportlab으로 유효 PDF 생성(라이브검증 겸)."""

from app.services.design_ingest.design_proposal_pdf import build_design_proposal_pdf


def _result(with_proposal: bool = True) -> dict:
    site = {
        "zone_code": "2R", "area_sqm": 5000.0, "buildable_footprint_sqm": 3000.0,
        "max_gfa_sqm": 15000.0, "max_floors_est": 5, "far_source": "ordinance",
        "warnings": ["미지정 용도지역 폴백 없음"],
        "evidence": [{"claim": "용적률 한도", "value": "300%", "link": "https://law.go.kr/x"}],
    }
    if not with_proposal:
        return {"ok": True, "site": site, "permit": None, "proposals": [], "recommendation": None}
    cand = {
        "estimated_gfa_sqm": 9000.0, "estimated_floors": 5, "estimated_units": 70,
        "disciplines_covered": ["건축", "구조"], "missing_disciplines": ["전기"],
        "parking_required": 70,
        "placement": {
            "site": {"w": 100.0, "d": 50.0}, "setback_m": 1.0,
            "building": {"x": 1.0, "y": 1.5, "w": 46.0, "d": 20.0, "area_sqm": 920.0},
            "blocks": [{"x": 1.0, "y": 1.5, "w": 46.0, "d": 20.0}],
            "dong_count": 3, "gap_m": 6.0, "buildable_region_sqm": 4704.0,
            "setback_binds": False, "note": "스키매틱 배치", "notes": ["단지 배치 개략 추정"],
        },
        "warnings": ["세대수는 추정치"],
    }
    return {
        "ok": True, "site": site,
        "permit": {"is_permitted": True, "permit_complexity": 3, "reason": "일반분양 허용"},
        "proposals": [{"candidate": cand, "verdict": {"verdict": "pass", "notes": ["적합"]},
                       "evidence": [{"claim": "주차장법", "link": "https://law.go.kr/p"}]}],
        "recommendation": {"index": 0, "verdict": "pass"},
    }


def _is_pdf(b: bytes) -> bool:
    return isinstance(b, bytes) and b.startswith(b"%PDF") and len(b) > 1500


def test_build_pdf_with_proposal():
    pdf = build_design_proposal_pdf(_result(with_proposal=True))
    assert _is_pdf(pdf)


def test_build_pdf_no_proposal_honest():
    # 추천안 없어도(도면 없음) 부지·인허가 평가만으로 유효 PDF 생성(무목업·정직)
    pdf = build_design_proposal_pdf(_result(with_proposal=False))
    assert _is_pdf(pdf)


def test_build_pdf_empty_result_safe():
    # 빈 결과(엣지)도 크래시 없이 유효 PDF(데이터 없음 표기)
    pdf = build_design_proposal_pdf({"ok": True})
    assert _is_pdf(pdf)


def test_build_pdf_placement_unbuildable_no_keyerror():
    # ★회귀: 배치불가 placement(dong_count 키 부재·building None — 극소부지 실엔진 출력)에서
    #   KeyError 없이 유효 PDF. 과거 pl["dong_count"] 직접인덱싱 크래시 방지.
    r = _result(with_proposal=True)
    r["proposals"][0]["candidate"]["placement"] = {
        "site": {"w": 10.0, "d": 10.0}, "setback_m": 6.0, "building": None,
        "setback_binds": True, "note": "이격 적용 시 가용영역 없음(배치 불가)", "notes": [],
    }
    pdf = build_design_proposal_pdf(r)
    assert _is_pdf(pdf)
