"""종상향 시나리오 — 위계별 용적률·추가용량·가능성 신호(촉진/제약)·대지카드 통합."""
from app.services.land.upzoning import upzoning_scenarios, upzoning_signals


def test_scenarios_residential_ladder():
    # 제1종일반(200) → 1단계 2종일반(250) → 2단계 3종일반(300). 대지 1000㎡.
    out = upzoning_scenarios("제1종일반주거지역", 1000.0, 0.0, max_steps=2)
    s = out["scenarios"]
    assert s[0]["target_zone"] == "제1종일반주거지역" and s[0]["far_limit_pct"] == 200
    assert s[1]["target_zone"] == "제2종일반주거지역" and s[1]["far_limit_pct"] == 250
    assert s[2]["target_zone"] == "제3종일반주거지역" and s[2]["far_limit_pct"] == 300
    # 2단계 상향 시 현행 대비 추가 (300-200)%*1000 = 1000㎡.
    assert s[2]["additional_vs_current_zoning"] == 1000.0


def test_scenarios_additional_vs_existing():
    # 제1종일반(200), 대지 15622㎡, 기존 50551㎡(초과). 2단계 3종일반(300%)→max 46866㎡.
    out = upzoning_scenarios("제1종일반주거지역", 15622.1, 50551.9, max_steps=2)
    s2 = out["scenarios"][2]
    assert s2["target_zone"] == "제3종일반주거지역"
    # 3종일반 상향해도 max 46866 < 기존 50551 → 여전히 음수(고밀 기존).
    assert s2["additional_vs_existing"] < 0


def test_ladder_out_of_scope_none():
    # 녹지/공업/관리는 주거 위계 밖 → None.
    assert upzoning_scenarios("자연녹지지역", 1000.0, 0.0) is None
    assert upzoning_scenarios("준공업지역", 1000.0, 0.0) is None


def test_signals_high():
    sig = upzoning_signals(["제2종일반주거지역", "지구단위계획구역", "역세권"])
    assert sig["likelihood"] == "HIGH"
    assert "지구단위계획구역" in sig["promote_signals"]
    assert sig["height_sealed"] is False


def test_signals_height_sealed_low():
    # 고도지구 있으면 종상향해도 높이 봉인 → LOW + height_sealed.
    sig = upzoning_signals(["제1종일반주거지역", "최고고도지구", "자연경관지구"])
    assert sig["likelihood"] == "LOW"
    assert sig["height_sealed"] is True
    assert any("고도" in r for r in sig["height_seal_reason"])
    assert any("높이규제" in n for n in sig["notes"])


def test_signals_blocked_by_cultural():
    # 문화재/그린벨트 → 개발 봉쇄 BLOCKED(촉진신호 있어도).
    sig = upzoning_signals(["지구단위계획구역", "문화재보호구역"])
    assert sig["likelihood"] == "BLOCKED"
    assert sig["development_blocked"] is True


def test_signals_mixed():
    # 촉진+제약(높이봉인/봉쇄 아닌) → MIXED. 역사문화환경보존=제약이나 높이봉인 키워드 아님.
    sig = upzoning_signals(["지구단위계획구역", "역사문화환경보존지역"])
    assert sig["likelihood"] == "MIXED"
    assert sig["height_sealed"] is False


def test_signals_unknown():
    sig = upzoning_signals(["제1종일반주거지역"])
    assert sig["likelihood"] == "UNKNOWN"
    assert sig["height_sealed"] is False


def test_promote_signals_expanded():
    # 워크플로우 확장 신호 인식.
    for z in ("재정비촉진지구", "개발진흥지구", "입지규제최소구역", "정비예정구역"):
        assert upzoning_signals([z])["promote_signals"] == [z]


def test_scenarios_carry_rationale():
    # 각 시나리오에 도출이유·도출식·법령근거·한계 동반(설명가능성 — land_card free dict 노출 보강).
    out = upzoning_scenarios("제1종일반주거지역", 1000.0, 0.0, max_steps=2)
    rat = out["scenarios"][1]["rationale"]
    assert rat["formula"] and rat["caveats"]
    assert any(lb["ref_id"] == "국토계획법시행령§85" for lb in rat["legal_basis"])
    assert any("이론상 최대" in c for c in rat["caveats"])


def test_signals_carry_legal_basis():
    # likelihood/신호 분류에 법령근거 동반(국토계획법§78·도시정비법 기본 + 매칭 신호 §52).
    sig = upzoning_signals(["제2종일반주거지역", "지구단위계획구역", "재개발구역"])
    ids = [lb["ref_id"] for lb in sig["legal_basis"]]
    assert "국토계획법§78" in ids and "도시정비법" in ids
    assert "국토계획법§52" in ids  # 지구단위계획 → §52
    # 미등록 법령은 placeholder로 표면화(무음 금지) — 등록본은 (미등록) 아님.
    assert all(lb["law"] != "(미등록)" for lb in sig["legal_basis"])
