"""부동산 구분(realty_type) SSOT — 구분코드 대조·검색결과 선택 공용 헬퍼.

왜 필요한가:
    등기부 주소검색은 한 주소에 여러 물건(토지·건물·집합건물의 각 호)을 돌려준다.
    지금까지 프로바이더 경로들이 결과 목록에서 무조건 첫 번째(items[0])를 집어
    사용자가 고른 "부동산 구분"과 다른 물건의 등기를 열람할 수 있었다.
    구분 대조·선택 로직을 이 한 곳에 모아 하이픈·틸코 등 모든 경로가 함께 따르게 한다.

구분코드 체계(인터넷등기소 관례 — 프론트 RegistryAnalysisWorkspaceClient와 동일):
    "1" = 집합건물(아파트·오피스텔) · "2" = 토지 · "3" = 건물 · "0"/None = 전체(구분 없음)

주의(검증되지 않은 가정을 두지 않는다):
    하이픈 주소검색 요청 파라미터 `kindcls`의 코드 규약은 벤더 문서로 확증하지 못했다.
    따라서 요청측 코드로 서버 필터를 걸지 않고, **응답에 담긴 한글 구분표기(gubun)**로
    결과측에서 대조한다. 표기는 자기설명적이라 코드 규약을 추측할 필요가 없다.
"""

from __future__ import annotations

from typing import Any

# 구분코드 → 사람이 읽는 표기(로그·안내문구용)
REALTY_KIND_LABELS: dict[str, str] = {
    "1": "집합건물",
    "2": "토지",
    "3": "건물",
}


def realty_kind_label(realty_type: str | None) -> str | None:
    """구분코드 → 한글 표기. 전체(0/None)면 None."""
    if not realty_type or realty_type == "0":
        return None
    return REALTY_KIND_LABELS.get(realty_type.strip())


def matches_realty_kind(gubun: str | None, realty_type: str | None) -> bool:
    """검색결과의 구분표기가 사용자가 고른 구분과 같은 물건인지 판정.

    구분을 지정하지 않았으면(전체) 항상 참. 결과에 구분표기가 없으면 판정 불가로 보아
    거짓을 돌려주고, 선택 단계에서 '대조 못함'으로 정직하게 처리한다.

    ★함정: "집합건물"에는 "건물"이 부분문자열로 들어있다. 그래서 '건물'(3)을 고른 경우
    집합건물이 걸리지 않도록 집합 여부를 먼저 배제한다.
    """
    if not realty_type or realty_type == "0":
        return True
    g = (gubun or "").strip()
    if not g:
        return False
    rt = realty_type.strip()
    if rt == "1":
        return "집합" in g
    if rt == "2":
        return "토지" in g
    if rt == "3":
        return "건물" in g and "집합" not in g
    return True


def _matches_dong_ho(jibun: str | None, dong: str | None, ho: str | None) -> bool:
    """집합건물 소재지번 표기에 동·호가 모두 들어있는지(둘 다 없으면 참)."""
    if not dong and not ho:
        return True
    j = (jibun or "").strip()
    if not j:
        return False
    wanted = [v.strip() for v in (dong, ho) if v and v.strip()]
    return all(w in j for w in wanted)


def select_registry_item(
    items: list[dict[str, Any]],
    realty_type: str | None = None,
    dong: str | None = None,
    ho: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """검색결과 목록에서 요청한 구분·동·호에 맞는 물건 1건을 고른다.

    반환: (고른 물건 | None, 사용자 안내문구 | None)
        안내문구는 "요청대로 못 골랐다"는 사실을 숨기지 않기 위한 것이다.
        요청과 정확히 일치하는 물건을 골랐으면 None.

    정책: 좁히지 못했다고 조회를 실패시키지 않는다(기존 동작 유지). 대신 첫 물건으로
    진행하되 무엇을 적용하지 못했는지 반드시 알린다 — 조용한 오답을 만들지 않는다.
    """
    rows = [it for it in (items or []) if isinstance(it, dict)]
    if not rows:
        return None, None

    label = realty_kind_label(realty_type)

    # 1단계: 부동산 구분으로 후보 좁히기
    kind_matched = [it for it in rows if matches_realty_kind(it.get("gubun"), realty_type)]
    if realty_type and realty_type != "0" and not kind_matched:
        return rows[0], (
            f"검색 결과에 '{label or realty_type}' 구분의 물건이 없어 첫 번째 물건으로 조회했습니다. "
            "결과의 부동산 구분을 확인하세요."
        )
    candidates = kind_matched or rows

    # 2단계: 집합건물이면 동·호로 특정 호 좁히기
    if dong or ho:
        exact = [it for it in candidates if _matches_dong_ho(it.get("jibun"), dong, ho)]
        if exact:
            return exact[0], None
        want = " ".join(v for v in (dong, ho) if v)
        return candidates[0], (
            f"검색 결과에서 '{want}'에 해당하는 호를 특정하지 못해 같은 구분의 첫 물건으로 조회했습니다. "
            "동·호 표기를 확인하세요."
        )

    return candidates[0], None
