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

import re
from typing import Any

# 구분코드 → 사람이 읽는 표기(로그·안내문구용)
REALTY_KIND_LABELS: dict[str, str] = {
    "1": "집합건물",
    "2": "토지",
    "3": "건물",
}

# 집합건물의 동의어(프로바이더마다 표기가 다르다).
#   "구분건물"은 등기 실무에서 집합건물을 가리키는 표기 — '건물'(3)로 오분류되면 안 된다.
_COLLECTIVE_TOKENS = ("집합", "구분건물", "구분소유")

# 동·호 토큰 추출: "제1101동" · "101동" · "가동" · "제1502호" 모두에서 번호부만 뽑는다.
_UNIT_TOKEN_RE = {
    "동": re.compile(r"제?\s*([0-9A-Za-z가-힣\-]+?)\s*동"),
    "호": re.compile(r"제?\s*([0-9A-Za-z가-힣\-]+?)\s*호"),
}


def realty_kind_label(realty_type: str | None) -> str | None:
    """구분코드 → 한글 표기. 전체(0/None)·미지코드면 None."""
    if not realty_type or realty_type == "0":
        return None
    return REALTY_KIND_LABELS.get(realty_type.strip())


def is_known_realty_kind(realty_type: str | None) -> bool:
    """아는 구분코드인가. 전체(0/None)도 '안다'로 본다(필터 없음이 정의된 상태)."""
    if not realty_type or realty_type == "0":
        return True
    return realty_type.strip() in REALTY_KIND_LABELS


def matches_realty_kind(gubun: str | None, realty_type: str | None) -> bool:
    """검색결과의 구분표기가 사용자가 고른 구분과 같은 물건인지 판정.

    구분을 지정하지 않았으면(전체) 항상 참. 결과에 구분표기가 없으면 판정 불가로 보아
    거짓을 돌려주고, 선택 단계에서 '대조 못함'으로 정직하게 처리한다.

    ★함정: "집합건물"·"구분건물"에는 "건물"이 부분문자열로 들어있다. '건물'(3)을 고른
    경우 이들이 걸리지 않도록 집합 계열을 먼저 배제한다.

    프로바이더가 표기 대신 코드("1"/"2"/"3")를 주는 경우도 그대로 대조한다.
    """
    if not realty_type or realty_type == "0":
        return True
    rt = realty_type.strip()
    g = re.sub(r"\s+", "", gubun or "")
    if not g:
        return False
    # 코드로 오는 프로바이더 대응
    if g in REALTY_KIND_LABELS:
        return g == rt
    is_collective = any(t in g for t in _COLLECTIVE_TOKENS)
    if rt == "1":
        return is_collective
    if rt == "2":
        return "토지" in g
    if rt == "3":
        # "토지및건물"처럼 건물을 포함하는 복합 표기는 건물로도 인정(실제 그 물건이 맞다).
        return "건물" in g and not is_collective
    return True


def _norm_unit(value: str) -> str:
    """동·호 번호 정규화: 앞의 '제', 단위 접미사, 선행 0, 공백·대소문자 차이를 흡수."""
    v = re.sub(r"\s+", "", value).upper()
    v = re.sub(r"^제", "", v)
    v = re.sub(r"[동호]$", "", v)
    if v.isdigit():
        v = v.lstrip("0") or "0"
    return v


def _unit_verdict(jibun: str, wanted: str, unit: str) -> bool | None:
    """소재지번 표기에서 해당 단위 토큰을 뽑아 요청값과 대조.

    True=일치 · False=불일치 · None=판정불가(표기에 그 단위가 아예 없음)

    ★부분문자열 매칭 금지: "101"이 "제1101동"에 들어있다는 이유로 일치시키면
    남의 세대 등기를 열람하고도 '정확히 일치'라고 보고하게 된다(실제 발생 결함).
    반드시 단위 토큰 단위로 뽑아 정규화 후 동등 비교한다.
    """
    tokens = [_norm_unit(t) for t in _UNIT_TOKEN_RE[unit].findall(jibun)]
    if not tokens:
        return None
    return _norm_unit(wanted) in tokens


def dong_ho_verdict(jibun: str | None, dong: str | None, ho: str | None) -> str:
    """동·호 대조 결과: "match" · "mismatch" · "unknown"(표기로 판정 불가).

    요청에 동·호가 없으면 대조할 것이 없으므로 "match".
    """
    if not (dong and dong.strip()) and not (ho and ho.strip()):
        return "match"
    j = (jibun or "").strip()
    if not j:
        return "unknown"
    verdicts = [
        _unit_verdict(j, v.strip(), unit)
        for v, unit in ((dong, "동"), (ho, "호"))
        if v and v.strip()
    ]
    if any(v is False for v in verdicts):
        return "mismatch"
    if any(v is None for v in verdicts):
        return "unknown"
    return "match"


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

    # 0단계: 아는 구분코드인지. 모르는 코드는 필터가 조용히 무력화되므로 반드시 고지한다.
    if not is_known_realty_kind(realty_type):
        return rows[0], (
            f"알 수 없는 부동산 구분값('{realty_type}')이라 구분을 적용하지 못하고 "
            "첫 번째 물건으로 조회했습니다. 결과의 부동산 구분을 확인하세요."
        )

    # 1단계: 부동산 구분으로 후보 좁히기
    kind_matched = [it for it in rows if matches_realty_kind(it.get("gubun"), realty_type)]
    if realty_type and realty_type != "0" and not kind_matched:
        return rows[0], (
            f"검색 결과에 '{label or realty_type}' 구분의 물건이 없어 첫 번째 물건으로 조회했습니다. "
            "결과의 부동산 구분을 확인하세요."
        )
    candidates = kind_matched or rows

    # 2단계: 집합건물이면 동·호로 특정 호 좁히기
    want = " ".join(v.strip() for v in (dong, ho) if v and v.strip())
    if want:
        verdicts = [(it, dong_ho_verdict(it.get("jibun"), dong, ho)) for it in candidates]
        exact = [it for it, v in verdicts if v == "match"]
        if len(exact) == 1:
            return exact[0], None
        if len(exact) > 1:
            # 여러 건이 똑같이 일치 = 모호. 침묵하면 "정확히 골랐다"는 거짓 보고가 된다.
            return exact[0], (
                f"'{want}'에 해당하는 물건이 {len(exact)}건이라 첫 번째 물건으로 조회했습니다. "
                "동·호 표기를 확인하세요."
            )
        unknown = [it for it, v in verdicts if v == "unknown"]
        if unknown:
            return unknown[0], (
                f"검색 결과 표기에서 동·호를 확인할 수 없어 '{want}' 여부를 대조하지 못한 채 "
                "조회했습니다. 결과의 소재지번을 확인하세요."
            )
        return candidates[0], (
            f"검색 결과에서 '{want}'에 해당하는 호를 특정하지 못해 같은 구분의 첫 물건으로 조회했습니다. "
            "동·호 표기를 확인하세요."
        )

    if len(candidates) > 1 and realty_type and realty_type != "0":
        return candidates[0], (
            f"'{label}' 구분의 물건이 {len(candidates)}건이라 첫 번째 물건으로 조회했습니다. "
            "결과의 소재지번을 확인하세요."
        )
    return candidates[0], None
