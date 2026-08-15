"""등기부 **열람 응답**을 실제로 읽어내는지 잠근다 — 3주 장애의 마지막 구간.

2026-08-15 프로덕션 실측(역삼동 737 토지 `11012012009048`):

    common.errYn = "N"          ← 열람은 **성공하고 있었다**
    data.pdfHexString  253,950자 ← 약 127KB PDF 를 매번 받고 있었다
    data.outList        26,417자 ← 갑구·을구·표제부까지 구조화돼 왔다
    → 그런데 우리 응답은  ok=True · has_pdf=False · owner=None

원인은 **키 이름 두 개**다:

    PDF   : 우리가 읽은 `pdfHex`  ↔ 실제 `pdfHexString`
    소유자: 우리가 읽은 `소유자`   ↔ 실제 `소유지분현황_갑구[].등기명의인`

★RC-1(주소검색 요청·응답 키)과 **같은 결함 클래스**다: 벤더가 준 것을 우리가 못 읽어
"안 된다" 로 보였다. 사용자에게는 3주 내내 '열람 실패' 였고, 그 사이 **문서 없는 성공**은
과금 대상으로 읽혔다(`origin=hyphen` 이므로).

★이 파일은 **실측한 응답 형태 그대로** 픽스처를 만든다 — 명세 화면이 아니라.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.registry import hyphen_client as hc

# 실측 응답의 형태(값은 축약·가명). 실제로는 `소유지분현황_갑구` 가 JSON 문자열로 올 수도
# 있어 두 표기를 모두 태운다.
_OWNER_ROWS = [{"등기명의인": "○○금융센터주\r\n식회사 (소유자)", "최종지분": "단독소유"}]


def test_PDF_키_표기를_전부_본다() -> None:
    """`pdfHex` 만 읽던 파서가 127KB 문서를 버렸다."""
    assert hc.extract_pdf_hex({"pdfHexString": "255044"}) == "255044"
    # 종전 표기도 계속 지원한다(벤더가 되돌려도 깨지지 않게).
    assert hc.extract_pdf_hex({"pdfHex": "255044"}) == "255044"
    # 두 모집단이 실제로 다르다 — 옛 키만 보던 파서는 새 키에서 빈 문자열을 냈다.
    assert hc.extract_pdf_hex({"pdfHexString": "255044"}) != ""
    assert hc.extract_pdf_hex({}) == ""
    assert hc.extract_pdf_hex({"pdfHexString": "   "}) == "", "공백만 있는 값을 문서로 치면 안 된다"


@pytest.mark.parametrize("rows", [_OWNER_ROWS, json.dumps(_OWNER_ROWS, ensure_ascii=False)])
def test_소유자를_갑구_표에서_뽑는다(rows: Any) -> None:
    """`outList` 는 dict 이고 갑구 표는 **리스트 또는 JSON 문자열**로 온다(둘 다 실측 가능)."""
    owner = hc.extract_owner({"고유번호": "11012012009048", "소유지분현황_갑구": rows})
    assert owner == "○○금융센터주 식회사 (소유자)", owner
    # ★줄바꿈(\r\n)이 값 안에 섞여 온다 — 그대로 두면 화면이 깨진다.
    assert "\r" not in owner and "\n" not in owner


def test_종전_평평한_표기도_계속_읽는다() -> None:
    assert hc.extract_owner({"소유자": "홍길동"}) == "홍길동"
    assert hc.extract_owner({"get소유자": "홍길동"}) == "홍길동"


def test_소유자가_없으면_지어내지_않는다() -> None:
    assert hc.extract_owner({}) is None
    assert hc.extract_owner({"소유지분현황_갑구": []}) is None
    assert hc.extract_owner("문자열") is None
    # 표는 있는데 이름 칸이 비면 None — 빈 문자열을 소유자로 내보내면 화면이 거짓말한다.
    assert hc.extract_owner({"소유지분현황_갑구": [{"등기명의인": ""}]}) is None


class _IssuanceClient:
    """실측 응답 형태를 그대로 돌려주는 스텁."""

    async def __aenter__(self) -> _IssuanceClient:
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    async def post(self, url: str, headers: Any = None, json: Any = None) -> Any:  # noqa: A002
        class _R:
            status_code = 200

            @staticmethod
            def json() -> dict[str, Any]:
                return {
                    "common": {"errYn": "N", "errCd": "", "errMsg": ""},
                    "data": {
                        "kindcls": "토지",
                        # "%PDF-1.4" 의 16진 표기 — 실제 응답과 같은 시작이다.
                        "pdfHexString": "255044462D312E34",
                        "outList": {
                            "고유번호": "11012012009048",
                            "지번_및_번호": "[토지] 서울특별시 강남구 역삼동 737",
                            "소유지분현황_갑구": _OWNER_ROWS,
                        },
                    },
                }

        return _R()


@pytest.mark.asyncio
async def test_열람이_문서와_소유자를_실제로_싣는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★결함이 살던 자리를 끝까지 태운다 — 응답 → 파싱 → 반환 필드까지.

    종전에는 여기서 `ok=True` 인데 `has_pdf=False` 였다. '문서 없는 성공' 은
    사용자에게 실패로 보이고, 과금 판정에는 성공으로 읽힌다 — 최악의 조합이다.
    """
    import base64

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _IssuanceClient)
    monkeypatch.setattr(hc, "hyphen_ready", lambda: True)
    monkeypatch.setattr(hc, "_headers", lambda: {})
    monkeypatch.setattr(hc, "_host", lambda: "https://example.invalid")

    res = await hc.fetch_realty_registry(unique_no="1101-2012-009048")

    assert res["ok"] is True and res["status"] == "ok", res
    assert res["has_pdf"] is True, f"문서를 받았는데 has_pdf 가 False 다: {res.get('has_pdf')}"
    assert base64.b64decode(res["pdf_base64"]).startswith(b"%PDF-"), "PDF 로 복원되지 않는다"
    assert res["owner"] == "○○금융센터주 식회사 (소유자)", res.get("owner")
