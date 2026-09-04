"""``/access/assess`` 가 **해결경로를 실제로 싣는지** 잠근다.

★왜 이 파일이 있나(2026-08-12 라이브 검증 중 발견):
  #538 이 해결경로 판정을 이름→코드(`resolution_key`)로 바꿨다. 그런데 그 코드가 심긴
  3요인(막다른 도로·자루형 통로부·소방 접근)은 `detect_special_parcel` 의 요인 체인에
  **들어가지 않고** `access_basis_service` 에서만 만들어지는데, 그 서비스는
  `_resolution_for` 를 부르지 않았다. 즉 **코드는 심겼는데 소비처가 없었다.**

  그 상태에서도 화면 문장(`implications`)은 맞는 말을 했다 — 그래서 눈으로는 멀쩡해
  보였다. 구조화 필드가 없다는 것만이 차이였고, 그건 소비처가 문장을 파싱하게 만든다.

★이 잠금이 보는 것: 이 서비스가 만드는 요인마다 `resolution_paths` 가 비어 있지 않고,
  #538 이 적발한 **오답 문구가 다시 나타나지 않는지**.
"""

from __future__ import annotations

import pytest

from app.services.access.access_basis_service import assess_access

# (입력, 기대 요인명 조각, 첫 해결경로 조각, 이 요인에 나오면 안 되는 오답 문구)
#
# ★오답 문구는 #538 이 실제로 적발한 것들이다:
#   맹지 → "폐지"(도로가 없어서 문제인데 없애라고 했다) · 막다른 도로 → 같은 폐도 경로
#   소방 접근 → "성능위주설계"(규모 임계 심의로 보냈다) · 자루형 → 기본값 "관계기관 협의"
CASES = [
    (
        {"address": "t", "road_contact": False},
        "맹지",
        "진입도로 확보",
        "폐지",
    ),
    (
        {"address": "t", "dead_end_road": True, "dead_end_length_m": 40, "road_width_m": 2.5},
        "막다른 도로",
        "막다른 도로 길이별 최소 너비 확보",
        "폐지",
    ),
    (
        {"address": "t", "flag_lot": True, "access_corridor_width_m": 1.5},
        "자루형",
        "통로부(자루목) 최소너비 확보",
        "관계기관 협의",
    ),
    (
        {"address": "t", "fire_truck_access_width_m": 2.0, "emergency_access_required": True},
        "소방·응급",
        "소방자동차 진입로 폭",
        "성능위주설계",
    ),
]


def _findings(payload: dict) -> list:
    """3상태(legal/physical/emergency) 전체에서 요인을 모은다."""
    res = assess_access(payload)
    out = []
    for state in ("legal", "physical", "emergency"):
        st = getattr(res, state, None)
        if st is not None:
            out.extend(st.findings)
    return out


@pytest.mark.parametrize(
    ("payload", "cat_frag", "path_frag", "wrong"), CASES, ids=[c[1] for c in CASES]
)
def test_해결경로가_실려_나온다(payload: dict, cat_frag: str, path_frag: str, wrong: str) -> None:
    findings = _findings(payload)

    # ★공허진리 방지 — 요인이 아예 안 잡히면 아래 단언들이 "대상 0개라 위반 0"으로 통과한다.
    target = [f for f in findings if cat_frag in f.category]
    assert target, (
        f"'{cat_frag}' 요인이 하나도 잡히지 않았다(전체 {len(findings)}건: "
        f"{[f.category for f in findings]}) — 입력이 규칙을 태우지 못한 것이다"
    )

    for f in target:
        assert f.resolution_paths, (
            f"'{f.category}' 에 resolution_paths 가 비어 있다 — "
            "_resolution_for 배선이 끊겼다(코드는 심겼는데 소비처가 없던 상태로 회귀)"
        )
        assert path_frag in f.resolution_paths[0], (
            f"'{f.category}' 첫 해결경로가 기대와 다르다: {f.resolution_paths[0]!r}"
        )
        assert wrong not in " ".join(f.resolution_paths), (
            f"'{f.category}' 에 #538 이 적발한 오답 문구 '{wrong}' 가 다시 나타났다: "
            f"{f.resolution_paths}"
        )


def test_이름을_바꿔도_코드가_이긴다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★변이 감사가 남긴 구멍을 메운다.

    배선에서 ``resolution_key`` 를 빼고 이름 분기만 태우는 변이를 넣었더니 **생존**했다.
    이유는 결함이 아니라 사실이다 — #538 이 이름 분기의 오답도 함께 고쳐서, 지금은
    두 경로가 **같은 값**을 낸다(4요인 전부 실측 확인). 값만 비교하는 테스트로는 원리적으로
    구분할 수 없다.

    그런데 코드 라우팅이 존재하는 이유는 값이 달라서가 아니라 **이름이 바뀌어도 해결경로가
    안 바뀌게** 하려는 것이다. 그러니 이름을 바꿔서 검사한다. 이름을 쉬운 말로 다듬는 흔한
    변경이 해결경로를 조용히 갈아치우면, 그게 #538 이 막으려던 사고다.
    """
    from app.services.zoning import special_parcel as sp

    renamed = {
        # 이름에 "도로"조차 없다 — 이름 분기라면 기본값("관계기관 협의")으로 떨어진다.
        "category": "접근 통로 폭 부족(표기 변경 테스트)",
        "developability": "CONDITIONAL",
        "resolution_key": "ROAD_DEAD_END",
        "implications": ["표기만 바꾼 요인"],
        "legal_ref_keys": ["road_relation"],
    }
    monkeypatch.setattr(sp, "_rule_by_cul_de_sac", lambda _result: dict(renamed))

    findings = _findings({"address": "t", "dead_end_road": True, "road_width_m": 2.5})
    target = [f for f in findings if "표기 변경 테스트" in f.category]
    assert target, f"위조한 요인이 안 잡혔다: {[f.category for f in findings]}"

    paths = target[0].resolution_paths
    assert paths, "이름을 바꾸자 해결경로가 사라졌다 — 코드 라우팅이 안 먹는다"
    assert "막다른 도로 길이별 최소 너비 확보" in paths[0], (
        f"이름이 바뀌자 해결경로가 갈아치워졌다: {paths[0]!r} — "
        "판정이 코드가 아니라 이름을 보고 있다(#538 이 막으려던 상태)"
    )


def test_요인_해결가능성과_상태_종합값은_별개다() -> None:
    """요인 단위 ``resolvable`` 을 실으면서 상태 종합값을 덮어쓰지 않는지 본다.

    둘은 의미가 다르다(요인 하나 vs 상태 전체). 같은 이름이라 섞이기 쉬워 명시로 잠근다.
    """
    res = assess_access({"address": "t", "road_contact": False})
    legal = res.legal
    assert legal.resolvable in {"YES", "CONDITIONAL", "NO"}
    fs = [f for f in legal.findings if "맹지" in f.category]
    assert fs, "맹지 요인이 legal 상태에 없다 — 이 테스트의 전제가 깨졌다"
    assert fs[0].resolvable, "요인 단위 resolvable 이 비어 있다"
