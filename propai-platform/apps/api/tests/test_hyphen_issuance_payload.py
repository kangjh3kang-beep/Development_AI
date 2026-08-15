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
"안 된다" 로 보였다.

★과금에 대해 정직하게 — `issued_count({"status":"ok","origin":"hyphen"}) == 1` 은
`tests/test_registry_issue_charging.py` 가 **의도된 동작으로 잠가 둔 계약**이다
(하이픈 민원캐시는 호출 시점에 차감되므로 문서를 못 읽었어도 비용은 이미 나갔다).
따라서 이건 "과금 버그" 가 아니라 **우리가 산 문서를 못 꺼내 쓴 것**이다.
그 3주치 청구에 대한 소급 보정은 이 PR 의 범위가 아니다.

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
    # ★두 모집단을 **옛 파서와 대조**해 가른다(단순 != "" 는 위 == 단언에 함의돼 공허하다).
    live = {"pdfHexString": "255044"}          # 실측 응답 형태
    legacy_parser = lambda d: d.get("pdfHex") or ""   # noqa: E731 — 종전 코드 그대로
    assert legacy_parser(live) == "", "옛 파서가 실측 형태를 읽었다면 이 PR 의 전제가 틀렸다"
    assert hc.extract_pdf_hex(live) == "255044", "새 파서가 실측 형태를 못 읽는다"

    assert hc.extract_pdf_hex({}) == ""
    assert hc.extract_pdf_hex({"pdfHexString": "   "}) == "", "공백만 있는 값을 문서로 치면 안 된다"
    # 앞뒤 공백은 다듬어야 한다 — 그대로 두면 `bytes.fromhex` 가 깨진다.
    assert hc.extract_pdf_hex({"pdfHexString": " 255044 "}) == "255044"
    # 근거 없는 표기는 표에 없다(추측을 넣으면 다음 사람이 실측으로 읽는다).
    assert hc.extract_pdf_hex({"pdf_hex": "255044"}) == ""


@pytest.mark.parametrize("rows", [_OWNER_ROWS, json.dumps(_OWNER_ROWS, ensure_ascii=False)])
def test_소유자를_갑구_표에서_뽑는다(rows: Any) -> None:
    """`outList` 는 dict 이고 갑구 표는 **리스트 또는 JSON 문자열**로 온다(둘 다 실측 가능)."""
    owner = hc.extract_owner({"고유번호": "11012012009048", "소유지분현황_갑구": rows})
    # ★줄바꿈은 **공백이 아니라 제거**다. 벤더가 지면 너비에 맞춰 **단어 중간에서** 접기
    #   때문에, 공백으로 치환하면 "○○금융센터주 식회사" 라는 존재하지 않는 상호가 된다.
    assert owner == "○○금융센터주식회사 (소유자)", owner
    assert "\r" not in owner and "\n" not in owner


def test_공백_뒤에서_접힌_경우는_표기가_보존된다() -> None:
    """두 모집단을 가른다 — 단어 중간 접힘(붙여야 함) vs 공백 뒤 접힘(이미 공백 있음)."""
    assert hc.extract_owner({"소유지분현황_갑구": [{"등기명의인": "홍길동 \r\n(소유자)"}]}) == "홍길동 (소유자)"
    assert hc.extract_owner({"소유지분현황_갑구": [{"등기명의인": "주식회\r\n사가나"}]}) == "주식회사가나"


def test_공유_필지의_소유자를_한_명으로_줄이지_않는다() -> None:
    """★벤더는 행마다 지분을 준다 — 첫 행만 쓰면 나머지 소유자가 통째로 사라진다.

    그 값이 화면·DB 캐시·외부 LLM 프롬프트 **세 표면**에 "이 필지의 소유자" 로 흐른다.
    """
    ol = {"소유지분현황_갑구": [
        {"등기명의인": "김철수 (공유자)", "최종지분": "2분의 1"},
        {"등기명의인": "박영희 (공유자)", "최종지분": "2분의 1"},
    ]}
    owners = hc.extract_owners(ol)
    assert [o["name"] for o in owners] == ["김철수 (공유자)", "박영희 (공유자)"], owners
    assert [o["share"] for o in owners] == ["2분의 1", "2분의 1"], owners
    # 표시용 한 줄은 **축약했다는 사실이 보여야** 한다 — "김철수" 만 내면 단독으로 읽힌다.
    # 벤더가 붙여 주는 "(공유자)" 표기는 지우지 않는다 — 그 자체가 정보다.
    assert hc.extract_owner(ol) == "김철수 (공유자) 외 1인"
    # ★두 모집단을 가른다: 단독은 그대로, 공유는 "외 N인".
    single = {"소유지분현황_갑구": [{"등기명의인": "김철수 (소유자)", "최종지분": "단독소유"}]}
    assert hc.extract_owner(single) == "김철수 (소유자)"
    assert hc.extract_owner(single) != hc.extract_owner(ol), "차가 0이면 잠금이 아니다"


def test_소유자_자리에_채권자나_등록번호를_넣지_않는다() -> None:
    """★첫 판에 넣었던 폴백(`소유권에_관한_사항_갑구`·`권리자_및_기타사항`)의 재발 방지.

    갑구에는 가압류·압류도 살고, 그 칸은 이름·주민등록번호·주소가 붙은 블롭이다.
    측정한 적 없는 표를 추측으로 읽으면 **채권자가 소유자로** 나온다.
    """
    가압류 = {"소유권에_관한_사항_갑구": [
        {"등기목적": "가압류", "권리자_및_기타사항": "채권자 국민은행 110111-0000000"},
    ]}
    assert hc.extract_owners(가압류) == [], hc.extract_owners(가압류)
    assert hc.extract_owner(가압류) is None


def test_outList가_리스트로_와도_읽는다() -> None:
    """벤더 응답은 dict 로 실측됐지만 형제 파서에서는 리스트로도 온다 — 두 형태를 가른다."""
    rows = [{"등기명의인": "김철수 (소유자)", "최종지분": "단독소유"}]
    as_dict = {"소유지분현황_갑구": rows}
    as_list = [as_dict]
    assert hc.extract_owner(as_dict) == "김철수 (소유자)"
    assert hc.extract_owner(as_list) == "김철수 (소유자)", "리스트 형태를 못 읽는다"
    assert hc.extract_owners([]) == []


def test_표에_이상한_행이_섞여도_건너뛴다() -> None:
    """★벤더 표에 문자열·None 이 섞여 오면 종전엔 그 행에서 터졌다(전체 조회 실패)."""
    ol = {"소유지분현황_갑구": [
        "머리말 문자열",
        None,
        {"등기명의인": "박영희 (소유자)", "최종지분": "단독소유"},
    ]}
    owners = hc.extract_owners(ol)
    assert [o["name"] for o in owners] == ["박영희 (소유자)"], owners


def test_리스트로_온_값에_파이썬_repr을_내지_않는다() -> None:
    """벤더가 공유 소유자를 리스트로 주면 화면에 `['김철수', '박영희']` 가 떴다."""
    out = hc.extract_owner({"소유자": ["김철수", "박영희"]})
    assert out == "김철수, 박영희", out
    assert "[" not in out and "'" not in out


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

    captured: dict[str, Any] = {}

    async def post(self, url: str, headers: Any = None, json: Any = None) -> Any:  # noqa: A002
        type(self).captured = {"url": url, "body": json}

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
    assert res["owner"] == "○○금융센터주식회사 (소유자)", res.get("owner")
    assert res["owner_count"] == 1 and res["owners"][0]["share"] == "단독소유", res

    # ★배선 락 — 우리가 **PDF 를 달라고 요청**하는지. 이 플래그를 "N" 으로 뒤집으면
    #   벤더가 문서를 안 보내고 3주 장애가 그대로 재현되는데, 종전 스텁은 요청 본문을
    #   받기만 하고 아무 것도 단언하지 않아 그 변이가 초록으로 생존했다.
    body = _IssuanceClient.captured["body"]
    assert body["pdfHex"] == "Y", f"PDF 를 달라고 요청하지 않는다: {body.get('pdfHex')!r}"
    assert body["uniqNo"] == "11012012009048", body
    assert body["searchDiv"] == "uniqNo", body

    # ★MED-2 — 같은 문서를 두 번 싣지 않는다(base64 + 원본 hex = 건당 ~430KB).
    assert "pdfHexString" not in (res["raw"].get("data") or {}), "raw 에 PDF 원본이 남아 있다"
