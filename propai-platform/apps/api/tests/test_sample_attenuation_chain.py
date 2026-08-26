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

    assert a["source_group_count"] == 2357, a["source_group_count"]
    assert a["shown_group_count"] == 210, a["shown_group_count"]
    assert a["reconciles"] is True, a.get("reconcile_mismatch")
    # 원본 − 각 단계 = 표시
    assert a["source_group_count"] - sum(s["dropped"] for s in a["stages"]) == a["shown_group_count"]


def test_headline_states_the_source_not_just_the_shown(live: dict) -> None:
    """★핵심 — 화면 문구가 **원본 수**를 말해야 한다(종전엔 표시 수만 있었다)."""
    h = build_sample_attenuation(live)["headline"]
    assert "2,357" in h, f"원본 수가 문구에 없다: {h}"
    assert "210" in h, f"표시 수가 문구에 없다: {h}"
    # ★"좌표 미확보"는 뺐다 — 차감이 아니라 참고다(2026-08-25 교정).
    for label in ("지오코딩 사전컷", "반경 밖", "표시 상한 절단"):
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
        c["capped_group_count"] = 0   # ★표시 상한도 0 이어야 "감쇠 없음" 이 성립한다
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


# ── 2026-08-25 교정 — 라이브 검증이 내 검산이 **공허했음**을 드러냈다 ──────────────
_FIX2 = Path(__file__).parent / "fixtures" / "nearby_map_jecheon_live.json"


@pytest.fixture
def live_jecheon() -> dict:
    """★현행 검산을 **깨뜨린** 실제 프로덕션 응답(제천 모산동 123-1).

    반경 안 = evaluated 182 − filtered 180 = **2** 인데 표시는 **58** 이다
    (좌표 미확보 그룹이 버려지지 않고 표시 경로에 들어간다 —
     카테고리 실측: house_trade `located=0` 인데 `shown=19`).
    """
    return json.loads(_FIX2.read_text(encoding="utf-8"))


def test_두_모집단에서_모두_검산이_성립한다(live: dict, live_jecheon: dict) -> None:
    """★한쪽에서만 맞는 모델은 모델이 아니다.

    종전 모델은 `display_cap` 을 **잔차**로 정의해 `reconciles` 가 **구성상 항상 참**이었다
    (잔차가 음수가 될 때만 깨진다). 즉 자기검산이 모델 오류를 **흡수**했다.
    """
    a1, a2 = build_sample_attenuation(live), build_sample_attenuation(live_jecheon)
    # 공허 방지 — 두 표본이 실제로 다른 모집단인가
    assert a1["source_group_count"] != a2["source_group_count"], "두 픽스처가 같은 모집단이다"
    assert a2["shown_group_count"] > a2["in_radius_group_count"], (
        "이 픽스처의 핵심 성질(표시 > 반경안)이 사라졌다 — 회귀 대상이 바뀌었다"
    )
    for label, a in (("역삼동", a1), ("제천", a2)):
        assert a["reconciles"] is True, f"[{label}] 검산 불일치: {a.get('reconcile_mismatch')}"
        assert (a["source_group_count"] - sum(s["dropped"] for s in a["stages"])
                == a["shown_group_count"]), f"[{label}] 사슬이 표시 수와 안 맞는다"


def test_좌표_미확보는_차감이_아니라_참고다(live_jecheon: dict) -> None:
    """★"제외됐다"는 거짓이다 — 반경 판정을 못 했을 뿐 표시에는 남는다."""
    a = build_sample_attenuation(live_jecheon)
    assert a["unlocated_group_count"] > 0, "이 픽스처는 미확보가 있어야 의미가 있다"
    assert all(s["key"] != "unlocated" for s in a["stages"]), (
        "좌표 미확보가 아직 **차감 단계**에 있다 — 표시에 남는 것을 제외됐다고 말한다"
    )
    assert a["unlocated_note"], "미확보를 세었으면 **무엇인지** 말해야 한다"
    assert "제외된 것이 아니라" in a["unlocated_note"]
    assert "좌표 미확보" not in a["headline"], (
        f"헤드라인이 아직 미확보를 제외 사유로 말한다: {a['headline']}"
    )


def test_표시상한은_실제_카운터를_쓴다_잔차가_아니라(live: dict) -> None:
    """★잔차는 모델 오류를 흡수해 검산을 공허하게 만든다.

    역삼동에서 **총합은 우연히 같았지만 귀속이 틀렸다** — 잔차cap 37 = 실제cap 73 − 미확보 36.
    표시 상한으로 깎인 36곳을 "좌표 미확보"라고 말하고 있었다.
    """
    a = build_sample_attenuation(live)
    cap = next(s for s in a["stages"] if s["key"] == "display_cap")
    real = sum((c.get("capped_group_count") or 0) for c in live["categories"].values())
    assert real > 0, "이 픽스처는 절단이 있어야 이 테스트가 의미를 갖는다"
    assert cap["dropped"] == real, (
        f"표시 상한이 실제 카운터와 다르다 — 잔차로 되돌아갔다: {cap['dropped']} vs {real}"
    )
