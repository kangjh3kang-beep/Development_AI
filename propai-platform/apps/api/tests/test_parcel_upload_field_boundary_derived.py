"""파생형 락 — **백엔드가 낸 필드가 프론트 타입 경계에서 조용히 버려지는가.**

## 무엇이 뚫려 있었나 (2026-08-16 실측)

엑셀 업로드 사슬:

    ① 양식 다운로드  GET  /zoning/land-schedule-template → `build_template_xlsx()`
       시트에 *"[토지사용동의]·[지구단위계획동의]·[시행자지정동의] … 활용됩니다"* 라고 **약속**한다.
    ② 업로드         POST /zoning/parse-parcels → `ParcelExcelService().parse()`
       동의 3종을 **실제로 파싱해 응답에 싣는다**.
    ③ 프론트         `GlobalAddressSearch.tsx` 의 응답 타입에 그 키가 **선언돼 있지 않다**
       → `.map()` 이 안 옮긴다 → **타입 경계에서 소실**.
    ④ 소비처         `consent_*` 는 `parcel_excel_service.py` 밖에 **0건**.

실측 결과 소실은 동의 3종만이 아니었다 — **한 경계에서 7개**가 버려지고 있었다:
`consent_land` · `consent_district` · `consent_operator` · `label` · `owner_type` ·
`registry_needed` · `status`.

★이 결함은 **아무 신호도 내지 않는다.** 타입이 좁을 뿐이라 빌드도 타입체크도 통과하고,
  사용자는 자기가 채운 칸이 어디로 갔는지 알 수 없다. 그래서 자동 락이 필요하다.

## 왜 목록형이 아니라 파생형인가

파서에 필드를 추가하는 사람은 **프론트 타입을 같이 고쳐야 한다는 걸 모른다**(다른 언어·다른 파일).
목록형이면 그 목록도 같이 안 고친다. 그래서 **양쪽을 소스에서 파생해 대조**한다 —
파서에 새 필드가 생기면 자동으로 여기서 걸린다.

## 면제는 사유를 적은 것만

의도적으로 안 넘기는 필드가 있을 수 있다(서버 전용 판정 등). 그건 **여기 사유와 함께** 적는다.
무증빙 면제를 금지해야 "그냥 추가해서 초록 만들기"가 리뷰에서 보인다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parents[1]
_WEB = _API.parents[0] / "web"
_PARSER = _API / "app" / "services" / "land_intelligence" / "parcel_excel_service.py"
_CLIENT = _WEB / "components" / "common" / "GlobalAddressSearch.tsx"
_UPLOAD_PATH = "/zoning/parse-parcels"

# ★면제 — **사유를 적은 것만** 인정한다. 늘어나면 리뷰에서 보인다.
_EXEMPT = {
    "status": "행 단위 파싱 상태(ok/need_geocode/failed) — 프론트는 injectable 로 이미 거른다",
    "registry_needed": "소유자 미기재 파생 플래그 — 등기 발급 안내는 별도 경로가 담당한다",
    "label": "원문 비고칸 — 집계행 판정용 내부 신호이고 화면 표기 계약이 없다",
    "owner_type": "소유'구분'(사유/국유/공유)이지 소유자 식별자가 아니다 — 소유자 단위 계산에 못 쓴다",
}


def _backend_fields() -> set[str]:
    """파서가 **응답 행에 싣는** 키를 AST 로 뽑는다(정규식은 주석·문자열에 뚫린다)."""
    tree = ast.parse(_PARSER.read_text(encoding="utf-8"))
    best: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.value, ast.Dict):
            continue
        target = getattr(node.target, "id", "")
        if target != "p":
            continue
        keys = {k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if len(keys) > len(best):
            best = keys
    return best


def _frontend_declared_fields() -> set[str]:
    """업로드 호출부의 **인라인 제네릭**에서 선언된 parcels 키를 뽑는다."""
    src = _CLIENT.read_text(encoding="utf-8")
    idx = src.find(_UPLOAD_PATH)
    if idx < 0:
        return set()
    # 호출부 앞쪽에서 `apiClient.post<` 를 찾아 그 사이(제네릭 블록)를 본다.
    start = src.rfind("apiClient.post<", 0, idx)
    if start < 0:
        return set()
    block = src[start:idx]
    m = re.search(r"parcels\?\s*:\s*Array<\{(.*?)\}>", block, re.S)
    if not m:
        return set()
    return set(re.findall(r"([a-z_]+)\??\s*:", m.group(1)))


def test_추출기가_살아_있다():
    """★공허 진리 가드 — 한쪽이 0이면 '차집합 0'이 조용히 참이 된다."""
    be, fe = _backend_fields(), _frontend_declared_fields()
    assert len(be) >= 10, f"백엔드 필드 추출 실패({len(be)}개) — 파서 구조가 바뀌었다: {sorted(be)}"
    assert len(fe) >= 5, f"프론트 타입 추출 실패({len(fe)}개) — 호출부 형태가 바뀌었다: {sorted(fe)}"
    # 양성 대조: 둘 다에 확실히 있는 필드가 실제로 잡히는지.
    for anchor in ("address", "pnu"):
        assert anchor in be and anchor in fe, f"'{anchor}' 가 한쪽에서 안 잡힌다 — 추출기가 틀렸다"


def test_면제는_사유가_있고_죽어_있지_않다():
    be = _backend_fields()
    for name, reason in _EXEMPT.items():
        assert reason.strip(), f"{name} 면제 사유가 비어 있다"
    dead = set(_EXEMPT) - be
    assert not dead, f"파서가 더 이상 내지 않는 필드가 면제 목록에 남아 있다(죽은 면제): {sorted(dead)}"


@pytest.mark.parametrize("field", sorted(_backend_fields() - set(_EXEMPT)))
def test_파서가_내는_필드는_프론트_타입에_선언돼야_한다(field: str):
    """필드별로 갈라 **어느 것이 버려지는지** 실패 메시지에서 바로 보이게 한다.

    ★특히 `consent_*` 는 우리가 사용자에게 *"활용됩니다"* 라고 **약속한** 칸이다.
      타입에서 빠지면 그 약속이 조용히 거짓이 된다.
    """
    assert field in _frontend_declared_fields(), (
        f"백엔드가 '{field}' 를 내는데 프론트 응답 타입에 없다 — 타입 경계에서 버려진다. "
        f"선언하거나, 의도적이면 _EXEMPT 에 **사유와 함께** 넣어라."
    )
