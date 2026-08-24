"""감쇠 사슬 — **원본 몇 곳이 어디서 깎여 화면의 N 이 됐는지** 한 줄로 말한다.

★픽스처는 **실제 프로덕션 응답**이다(합성 아님) — 라이브 실측 2026-08-25,
  역삼동 736 · 1000m. 그 응답에서 원본 **2,350곳 → 표시 209곳(91% 제외)** 이었는데
  화면은 209 만 말하고 2,350 은 어디에도 없었다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.land_intelligence.sample_attenuation import build_sample_attenuation

_FIX = Path(__file__).parent / "fixtures" / "nearby_map_yeoksam_live.json"


@pytest.fixture
def live() -> dict:
    return json.loads(_FIX.read_text(encoding="utf-8"))


def test_chain_reconciles_on_real_production_payload(live: dict) -> None:
    """실제 응답에서 사슬이 **정확히 맞아떨어진다**."""
    a = build_sample_attenuation(live)
    assert a is not None, "실제 응답인데 사슬을 못 만들었다"
    # ── 공허진리 가드: 잴 대상이 실제로 있는가 ──
    assert a["source_group_count"] > 0 and a["shown_group_count"] > 0
    assert a["dropped_total"] > 0, "감쇠가 0이면 이 테스트는 아무것도 잠그지 않는다"

    assert a["source_group_count"] == 2350, a["source_group_count"]
    assert a["shown_group_count"] == 209, a["shown_group_count"]
    assert a["reconciles"] is True, a.get("reconcile_mismatch")
    # 원본 − 각 단계 = 표시
    assert a["source_group_count"] - sum(s["dropped"] for s in a["stages"]) == a["shown_group_count"]


def test_headline_states_the_source_not_just_the_shown(live: dict) -> None:
    """★핵심 — 화면 문구가 **원본 수**를 말해야 한다(종전엔 표시 수만 있었다)."""
    h = build_sample_attenuation(live)["headline"]
    assert "2,350" in h, f"원본 수가 문구에 없다: {h}"
    assert "209" in h, f"표시 수가 문구에 없다: {h}"
    for label in ("지오코딩 사전컷", "좌표 미확보", "반경 밖", "표시 상한 절단"):
        assert label in h, f"감쇠 사유 '{label}' 가 문구에 없다: {h}"


def test_every_stage_says_why(live: dict) -> None:
    """단계마다 **사유**가 있어야 한다 — 숫자만 있으면 무엇을 고칠지 모른다."""
    for s in build_sample_attenuation(live)["stages"]:
        assert s.get("reason"), f"사유 없는 단계: {s['key']}"
        assert isinstance(s["dropped"], int) and s["dropped"] >= 0


def test_mismatch_is_reported_not_silently_corrected(live: dict) -> None:
    """★계기가 어긋나면 **신고**한다 — 조용히 맞추면 고장을 '깨끗함'으로 읽는다."""
    broken = json.loads(json.dumps(live))
    broken["radius_filtered_out_count"] += 100          # 사슬을 일부러 깬다
    a = build_sample_attenuation(broken)
    assert a["reconciles"] is False, "사슬이 깨졌는데 맞다고 한다"
    assert a["reconcile_mismatch"]["delta"] != 0
    # ★표시 수는 **건드리지 않는다**(신고하되 값을 바꾸지 않는다)
    assert a["shown_group_count"] == build_sample_attenuation(live)["shown_group_count"]


def test_two_populations_differ(live: dict) -> None:
    """★감쇠 있는 응답과 없는 응답이 **다른 문구**를 내야 한다."""
    clean = json.loads(json.dumps(live))
    for k in ("geocode_precut_count", "coords_unresolved_count", "radius_filtered_out_count"):
        clean[k] = 0
    for c in clean["categories"].values():
        c["precut"]["groups_before"] = len(c["groups"])
        c["precut"]["groups_cut"] = 0
    clean["groups_evaluated_count"] = sum(len(c["groups"]) for c in clean["categories"].values())
    a_clean, a_live = build_sample_attenuation(clean), build_sample_attenuation(live)
    assert a_clean["dropped_total"] == 0 and a_live["dropped_total"] > 0
    assert a_clean["headline"] != a_live["headline"], "감쇠 유무가 같은 문구를 낸다"
    assert "모두 표시" in a_clean["headline"], a_clean["headline"]


def test_returns_none_without_basis() -> None:
    """근거가 없으면 **만들지 않는다**(무목업)."""
    assert build_sample_attenuation({}) is None
    assert build_sample_attenuation({"categories": {}}) is None
    assert build_sample_attenuation("nope") is None  # type: ignore[arg-type]


def test_service_actually_attaches_the_chain_to_its_response() -> None:
    """배선 락 — 순수 함수만 잠그면 **서비스가 안 실어도 초록**이다.

    ★변이 실증: `result["sample_attenuation"] = None` 로 바꿔도 위 6건과 프론트 5건이
      **전부 통과**했다(층이 다르다). 그래서 배선을 따로 잠근다.
    ★소스 검사는 **주석·문자열을 걷어내고** 실행되는 줄만 본다(#586 계보 — 주석처리
      변이에 뚫린 전례가 있다).
    """
    import sys
    from pathlib import Path as _P

    sys.path.insert(0, str(_P(__file__).resolve().parents[3] / "tests"))
    from _scan_guard import code_lines, read, scan  # noqa: PLC0415

    svc = (_P(__file__).resolve().parents[1]
           / "app" / "services" / "land_intelligence" / "nearby_map_service.py")
    src = code_lines(read(svc, must_exist_reason="nearby_map 서비스가 사라졌다"))

    r = scan(
        src,
        pattern=r'result\["sample_attenuation"\]\s*=\s*build_sample_attenuation\(',
        # 대조군: 이 파일에 반드시 있는 것 — 0건이면 경로·정규식이 틀린 것이다
        positive_control=r'"display_cap_impact":',
        where=str(svc),
    )
    assert r.hits, (
        "서비스가 감쇠 사슬을 응답에 싣지 않는다 — 순수 함수는 있는데 **소비처가 0**이다.\n"
        f"  (양성대조 {r.positive_hits}건 — 검사기는 살아 있다)"
    )
    # 임포트도 실행 줄에 있어야 한다(주석만 남기고 배선을 지우는 변이 차단)
    assert "from app.services.land_intelligence.sample_attenuation import" in src, (
        "헬퍼 임포트가 실행 줄에 없다"
    )
