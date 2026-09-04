"""전문가 패널 실효 한도 근거 블록 — 구조상한 오귀속(조례 실효치로 단정) 재발 방지.

실측 결함(2026-07-17): /regulation/analyze 결과의 effective_far 통과키(far_basis·구조상한)가
ctx 절단([:4000]) 뒤쪽이라 전문가 LLM에 도달하지 못했고, 패널이 자연녹지 실효 80%를
"조례 실효치"로 오귀속(+가짜 쟁점 "조례 원문 확인 필요" 생성). 근거 블록을 선두 삽입해
절단과 무관하게 생존시키고, 시스템 프롬프트에 단정 금지 지시를 고정한다.
"""

from app.services.expert_panel.expert_panel_service import (
    _PANEL_SYSTEM,
    _effective_limit_note,
)

# 자연녹지 대표 케이스 — 규제 분석 응답의 실제 통과키 계약(regulation_analysis_service WP-R1).
_NATURAL_GREEN_CTX = {
    "zone_type": "자연녹지지역",
    "limits": {
        "far": {"legal": 100, "ordinance": None, "effective": 80},
        "bcr": {"legal": 20, "ordinance": None, "effective": 20},
    },
    "effective_far": {
        "effective_far_pct": 80.0,
        "effective_bcr_pct": 20.0,
        "structural_cap_pct": 80.0,
        "floor_cap": 4,
        "floor_cap_basis": "국토계획법 시행령 별표17(4층 이하)",
        "far_basis": "구조상한(건폐율×층수)",
    },
}


def test_structural_cap_note_explains_formula_not_ordinance():
    """구조상한 케이스: 공식(20%×4층=80%)과 '조례 인하 아님'을 명시해야 한다."""
    note = _effective_limit_note(_NATURAL_GREEN_CTX)
    assert "[실효 한도 근거 — SSOT]" in note
    assert "실효 용적률 80%" in note
    assert "법정 상한 100%" in note
    assert "구조상한(건폐율×층수)" in note
    assert "건폐율 20% × 최고 4층 = 80%" in note
    assert "조례가 낮춘 것이 아니라" in note
    assert "별표17" in note  # 층수 제한 근거 원문 전달


def test_note_survives_truncation_when_prepended():
    """대형 컨텍스트여도 선두 삽입이라 절단([:6000]) 후에도 근거 블록이 생존해야 한다."""
    import json

    big = dict(_NATURAL_GREEN_CTX)
    big["padding"] = "x" * 20000  # 절단을 강제하는 대형 필드
    note = _effective_limit_note(big)
    ctx_str = (note + json.dumps(big, ensure_ascii=False))[:6000]
    assert "구조상한(건폐율×층수)" in ctx_str
    assert "조례가 낮춘 것이 아니라" in ctx_str


def test_ordinance_basis_passthrough():
    """조례가 진짜 원인인 케이스는 그 basis를 그대로 전달한다(구조상한 문구 미부착)."""
    ctx = {
        "limits": {"far": {"legal": 900, "effective": 700}},
        "effective_far": {
            "effective_far_pct": 700.0,
            "effective_bcr_pct": None,
            "structural_cap_pct": None,
            "floor_cap": None,
            "floor_cap_basis": None,
            "far_basis": "지자체 도시계획조례",
        },
    }
    note = _effective_limit_note(ctx)
    assert "지자체 도시계획조례" in note
    assert "조례가 낮춘 것이 아니라" not in note


def test_missing_basis_forbids_attribution():
    """근거 필드 부재 시 '단정하지 말 것' 지시가 실려야 한다(무날조)."""
    ctx = {"effective_far": {"effective_far_pct": 80.0, "far_basis": None}}
    note = _effective_limit_note(ctx)
    assert "단정하지 말 것" in note


def test_no_effective_fields_returns_empty():
    """통과키 자체가 없으면(시장·세무 등 타 유형) 빈 문자열 — 타 패널 무영향."""
    assert _effective_limit_note({"zone_type": "일반상업지역"}) == ""
    assert _effective_limit_note("문자열 컨텍스트") == ""


def test_panel_system_forbids_ordinance_default_attribution():
    """시스템 프롬프트에 '조례 실효치 단정 금지' 지시가 고정돼야 한다(회귀 앵커)."""
    assert "far_basis" in _PANEL_SYSTEM
    assert "단정" in _PANEL_SYSTEM
