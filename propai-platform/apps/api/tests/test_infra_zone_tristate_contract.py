"""기반시설부담구역 게이트가 **전 경로에서 3상태를 유지하는가**.

## 왜 (2026-08-26)

`in_infra_charge_zone` 의 기본값은 `False` 였고, 사유를 **`"기반시설부담구역 미지정"`** 이라고
썼다. 그런데 그 값을 실제로 넘기는 곳이 **한 군데도 없었다**(프론트 출현 0건 · camelCase 도 0 ·
대조군 `total_gfa_sqm` 33건 = 조회기 생존). 즉 **전 사업이 「미조회」인데 화면에는 「미지정」이라는
관측 주장**이 나갔다. ★증거 규율 §1 — **미측정을 관측처럼 쓰지 않는다.**

금액은 셋 다 0(안전측 유지 — 이 변경은 **표기**만 바로잡는다). 바뀌는 것은
**우리가 무엇을 아는지에 대한 주장**이다.

## 이 테스트가 잠그는 것

★한 층만 고치면 **위층이 다시 뭉갠다**(실제로 그랬다 — 함수를 3상태로 바꿨는데
`calculate_all_sale_stage` · `project_charges` · `cost_blocks` 세 곳이 `bool = False` 로 강제해
**세 상태가 C07 에 닿지 못했다**). 그래서 **경로를 파생형으로 수집**해 전수 검사한다.
"""

from __future__ import annotations

import inspect

from app.services.tax import project_charges as pc
from app.services.tax import sale_stage_engine as sse
from app.services.tax.project_charges import parse_tristate_flag


def _gate_params():
    """`in_infra_charge_zone` 을 받는 함수를 **파생형으로** 모은다(손 목록 금지)."""
    found = []
    for mod in (pc, sse):
        for name, fn in vars(mod).items():
            if not callable(fn) or not hasattr(fn, "__module__"):
                continue
            if getattr(fn, "__module__", None) != mod.__name__:
                continue
            try:
                sig = inspect.signature(fn)
            except (TypeError, ValueError):
                continue
            p = sig.parameters.get("in_infra_charge_zone")
            if p is not None:
                found.append((f"{mod.__name__}.{name}", p))
    return found


def test_probe_is_alive():
    """★전제 — 게이트를 받는 함수를 실제로 찾았다(0건이 초록이 되지 않게)."""
    found = _gate_params()
    assert len(found) >= 3, f"게이트 경로를 못 찾았다 — 조회기가 죽었다: {found}"


def test_every_path_keeps_the_tristate():
    """★★어느 층도 3상태를 **`bool` 로 뭉개지 않는다** — 뭉개면 아래층 분기가 죽는다."""
    bad = [
        f"{n}: default={p.default!r} annotation={p.annotation!r}"
        for n, p in _gate_params()
        if p.default is not None
    ]
    assert not bad, (
        "게이트 기본값이 `None`(미조회)이 아니다 — 미조회를 미지정으로 뭉갠다:\n"
        + "\n".join(bad)
    )


def test_tristate_parser_distinguishes_absent_from_false():
    """★파서가 **미조회**와 **조회했고 아님**을 가른다(두 모집단)."""
    assert parse_tristate_flag(None) is None
    assert parse_tristate_flag("") is None          # 입력했다 지운 것도 「모른다」쪽
    assert parse_tristate_flag(False) is False
    assert parse_tristate_flag("false") is False    # 문자열 오부과 방지(기존 규율 계승)
    assert parse_tristate_flag("0") is False
    assert parse_tristate_flag(True) is True
    assert parse_tristate_flag("true") is True
    # ★대조군 — 전부 None 을 돌려주는 구현이 통과하지 않게.
    assert len({parse_tristate_flag(v) for v in (None, False, True)}) == 3


def test_three_states_produce_three_different_claims():
    """★★세 상태가 **서로 다른 말**을 한다 — 둘이 같으면 분기를 지워도 통과한다."""
    reasons = {}
    for label, val in (("unknown", None), ("surveyed_no", False), ("in_zone", True)):
        r = sse.calculate_c07_infrastructure_charge(total_gfa_sqm=50_000, in_infra_charge_zone=val)
        reasons[label] = (r["amount_won"], (r.get("detail") or {}).get("reason"))
    assert reasons["unknown"][0] == reasons["surveyed_no"][0] == 0, "안전측 0 이 깨졌다"
    assert reasons["in_zone"][0] > 0, "지정 구역인데 미부과다"
    assert reasons["unknown"][1] != reasons["surveyed_no"][1], (
        "미조회와 미지정이 **같은 문장**을 쓴다 — 구별이 화면에 닿지 않는다"
    )
    assert "미조회" in reasons["unknown"][1]
    assert "미지정" in reasons["surveyed_no"][1]


def test_unknown_is_flagged_unavailable_but_surveyed_is_not():
    """★미조회만 강등 표기 — 확정에 강등이 붙으면 그것도 거짓이다(양방향)."""
    unk = sse.calculate_c07_infrastructure_charge(total_gfa_sqm=1, in_infra_charge_zone=None)
    sur = sse.calculate_c07_infrastructure_charge(total_gfa_sqm=1, in_infra_charge_zone=False)
    assert unk.get("confidence") == "unavailable"
    assert "confidence" not in sur


def test_end_to_end_through_project_charges():
    """★상위 통합 경유에서도 3상태가 산다(한 층만 고치면 위층이 뭉갠다 — 실제로 그랬다)."""
    def reason(val):
        r = pc.compute_developer_stage_charges(
            sido_name="서울특별시", sigungu_name="강남구",
            total_sale_amount_won=100_000_000_000, total_households=300,
            total_gfa_sqm=45_000, in_infra_charge_zone=val,
        )
        c07 = next(i for i in r["sale"]["items"] if i["code"] == "C07")
        return c07["amount_won"], (c07.get("detail") or {}).get("reason")

    unk, sur, yes = reason(None), reason(False), reason(True)
    assert unk[0] == sur[0] == 0 and yes[0] > 0
    assert unk[1] != sur[1], "상위 경유에서 3상태가 다시 뭉개졌다"
    assert "미조회" in unk[1]


# ── 축 ③ **호출부** — 정의부만 훑는 락은 뚫린다(2026-08-26 라이브 실증) ────────────
#   ★#865 는 엔진·통합·모듈 **세 층의 정의**를 3상태로 고쳤고, 위의 `_gate_params()` 락이
#     그것을 지켰다. 그런데 **네 번째 층은 호출부**였다 —
#     `rough_feasibility_orchestrator.py` 가 `parse_bool_flag(...)` 로 넘겨
#     **미조회를 미지정으로 뭉갠 채** 라이브에 나갔다.
#   ★락이 초록이었고 **라이브 프로브만이** 잡았다. 정의부 스캔은 **넘기는 값**을 안 본다.
def _call_sites() -> list[tuple[str, str]]:
    """`in_infra_charge_zone=` 로 **넘기는** 줄을 저장소에서 **파생형으로** 모은다.

    손 목록이면 다음에 생기는 다섯 번째 호출부가 조용히 빠진다.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    out: list[tuple[str, str]] = []
    for f in root.rglob("*.py"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if re.search(r"in_infra_charge_zone\s*=", line) and "def " not in line:
                out.append((str(f.relative_to(root)), line.strip()))
    return out


def test_call_sites_probe_is_alive():
    """★전제 — 호출부를 실제로 찾았다(0건이 초록이 되지 않게)."""
    sites = _call_sites()
    assert len(sites) >= 2, f"호출부를 못 찾았다 — 조회기가 죽었다: {sites}"


def test_no_call_site_collapses_the_tristate_with_bool_parser():
    """★★어느 호출부도 **`parse_bool_flag` 로 뭉개지 않는다**.

    `parse_bool_flag` 는 `None`(미조회)을 `False`(조회했고 미지정)로 바꾼다. 그러면
    화면에 *"기반시설부담구역 미지정"* 이라는 **없는 관측 주장**이 나간다(증거 규율 §1).
    """
    bad = [f"{f}: {line}" for f, line in _call_sites() if "parse_bool_flag" in line]
    assert not bad, (
        "미조회를 미지정으로 뭉개는 호출부:\n" + "\n".join(bad)
        + "\n→ parse_tristate_flag 를 쓰십시오."
    )


def test_at_least_one_call_site_uses_the_tristate_parser():
    """★대조군 — *"아무도 안 쓴다"* 가 위 검사를 공허하게 만들지 않게."""
    good = [f for f, line in _call_sites() if "parse_tristate_flag" in line]
    assert good, "3상태 파서를 쓰는 호출부가 하나도 없다 — 위 검사가 공허하다"
