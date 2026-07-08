"""app.services.zoning.special_parcel_gate(B2 공용 게이트 헬퍼) 단위 테스트.

핵심 회귀잠금:
- 컨텍스트(land_category·special_districts) 모두 없으면 None(정직 생략 — 무날조).
- land_category만 있어도(학교용지 등) 판정 — detect_special_parcel과 동일 developability.
- 표준 shape({developability, warnings, legal_refs, ...}) 키 존재 + pnu echo.
- 특이 없는 일상 지목(예: '대')은 None(과탐 방지).
- 판정 실패(예외)도 graceful None(주 경로를 깨지 않음).
"""

from app.services.zoning.special_parcel_gate import build_special_parcel_gate


def test_no_context_returns_none():
    """land_category·special_districts 둘 다 없으면 판정 불가 → None(정직 생략)."""
    assert build_special_parcel_gate() is None
    assert build_special_parcel_gate(zone_type="자연녹지지역", area_sqm=1000.0) is None


def test_school_land_category_triggers_precondition_gate():
    """학교용지(지목) → PRECONDITION 게이트 + 경고·법령근거 동봉(표준 shape)."""
    out = build_special_parcel_gate(land_category="학교용지", zone_type="일반상업지역", pnu="1111011100100010000")
    assert out is not None
    assert out["is_special"] is True
    assert out["developability"] == "PRECONDITION"
    assert out["warnings"] and any("학교용지" in w for w in out["warnings"])
    assert out["pnu"] == "1111011100100010000"
    # 표준 shape 키 존재(요청 계약).
    for key in ("developability", "warnings", "legal_refs", "severity_label", "resolvable", "note"):
        assert key in out


def test_special_districts_only_also_triggers_gate():
    """지목 없이 special_districts(GB 등)만 있어도 판정된다."""
    out = build_special_parcel_gate(special_districts=["개발제한구역"])
    assert out is not None
    assert out["developability"] == "BLOCKED"
    assert out["resolvable"] == "NO"


def test_ordinary_land_category_no_special_factors_returns_none():
    """일상 지목(대지 등 매칭 규칙 없음) + 특이구역 없음 → 특이요인 0건 → None."""
    out = build_special_parcel_gate(land_category="대", zone_type="제2종일반주거지역")
    assert out is None


def test_detect_failure_is_graceful_none(monkeypatch):
    """detect_special_parcel이 예외를 던져도 게이트가 주 경로를 깨지 않고 None을 반환한다."""
    import app.services.zoning.special_parcel as sp_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(sp_mod, "detect_special_parcel", _boom)
    # special_parcel_gate는 함수 내부에서 지연 import하므로, 모듈 레벨 몽키패치가 반영된다.
    assert build_special_parcel_gate(land_category="학교용지") is None
