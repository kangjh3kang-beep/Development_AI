"""양식 락 — ★**주소와 지번 두 칸만 채우면 올라간다.**

## 왜 이 파일이 있나

종전 양식은 **12열**이었고 그중 **10열이 「비워도 되는」 칸**이었다. 안내문 자신이
*"[소재지(주소)] 는 필수입니다. 나머지는 비워도 됩니다"* 라고 적고 있었다 —
***양식이 스스로 「대부분 안 채워도 된다」고 말하면서 그 칸들을 사용자 앞에 늘어놓고 있었다.***

## 더 중요한 것 — 예시행이 **실제 필지로 등록**됐다

종전 양식은 2·3행에 예시를 깔고 *"삭제 후 작성"* 이라고 안내했다. 이 저장소에는 그 예시값이
지워지지 않은 채 올라와 **면적이 오적재된 전례**가 있다(그래서 면적·지목 칸을 비워 두는
완화까지 들어가 있었다). 열이 둘로 줄면 예시행이 남을 때 **존재하지 않는 필지 2건이 그대로
등록**된다. ⇒ 완화가 아니라 **원인을 없앴다**: 데이터 시트는 **머리글만** 둔다.

## 이 파일이 잠그는 것

1. 양식은 **정확히 두 열**이고, 그 두 열을 **파서가 주소·지번으로 인식**한다
   (헤더 문자열을 손으로 대조하지 않고 **파서의 판정 함수**에 태운다 — 별칭이 바뀌면 여기서 걸린다)
2. **빈 양식을 그대로 올리면 필지 0건** ↔ **채우면 그 수만큼** (두 모집단 — 하나만 보면
   "파서가 아무것도 못 읽는" 구현도 통과한다)
3. 데이터 시트에 **예시행이 없다**
4. 안내 시트가 *"이미 쓰던 양식도 그대로 읽는다"* 고 **약속**한다 — 그 약속을 **실제로 태워** 확인한다
   (약속만 적고 동작을 안 재면 그게 이 저장소가 반복해 데인 자리다)
"""

from __future__ import annotations

import asyncio
import io

from openpyxl import load_workbook

from app.services.land_intelligence import parcel_excel_service as pes


def _sheet(raw: bytes, name: str):
    return load_workbook(io.BytesIO(raw))[name]


def _parse(raw: bytes, fn: str = "t.xlsx"):
    return asyncio.run(pes.ParcelExcelService().parse(raw, fn, use_llm=False))


def test_template_has_exactly_address_and_jibun():
    """★두 열뿐이고, **파서가 그 둘을 주소·지번으로 인식**한다."""
    assert len(pes.TEMPLATE_COLUMNS) == 2, pes.TEMPLATE_COLUMNS
    headers = [n for n, _ex in pes.TEMPLATE_COLUMNS]

    # ★손으로 문자열을 대조하지 않는다 — **파서의 판정 함수**에 태운다.
    roles = pes._detect_columns(headers)
    assert roles["address"] == headers[0], f"파서가 1열을 주소로 못 읽는다: {roles}"
    assert roles["jibun"] == headers[1], f"파서가 2열을 지번으로 못 읽는다: {roles}"
    # 공허 방지 — 나머지 역할은 실제로 비어 있어야 한다(열이 둘뿐이므로)
    assert {k for k, v in roles.items() if v} == {"address", "jibun"}, roles


def test_downloaded_sheet_matches_the_declared_columns():
    """선언(`TEMPLATE_COLUMNS`)과 **산출물**(실제 시트)이 같은가 — 선언만 고치는 변경을 막는다."""
    ws = _sheet(pes.build_template_xlsx(), "토지조서")
    assert [c.value for c in ws[1]] == [n for n, _ in pes.TEMPLATE_COLUMNS]


def test_blank_template_yields_zero_parcels_but_filled_yields_rows():
    """★**두 모집단** — 빈 양식은 0건, 채운 양식은 그 수만큼.

    하나만 보면 "파서가 아무것도 못 읽는" 구현도 통과한다.
    """
    raw = pes.build_template_xlsx()

    blank = _parse(raw, "template.xlsx")
    assert not blank.get("error"), blank.get("error")
    assert (blank.get("parcels") or []) == [], (
        "빈 양식을 올렸는데 필지가 생겼다 — 예시행이 실제 필지로 등록되는 그 결함이다"
    )

    wb = load_workbook(io.BytesIO(raw))
    ws = wb["토지조서"]
    ws.append(["경기도 안양시 동안구 비산동 511-168", "511-168"])
    ws.append(["경기도 의정부시 의정부동 224", "224"])
    buf = io.BytesIO()
    wb.save(buf)

    filled = _parse(buf.getvalue(), "filled.xlsx")
    assert not filled.get("error"), filled.get("error")
    got = filled.get("parcels") or []
    assert len(got) == 2, f"채운 2행이 안 읽혔다: {got}"
    assert [p.get("address") for p in got] == [
        "경기도 안양시 동안구 비산동 511-168",
        "경기도 의정부시 의정부동 224",
    ], got
    assert [p.get("jibun") for p in got] == ["511-168", "224"], got


def test_data_sheet_has_no_example_rows():
    """예시행을 데이터 시트에 두지 않는다 — 안 지우고 올리면 없는 필지가 등록된다."""
    ws = _sheet(pes.build_template_xlsx(), "토지조서")
    assert ws.max_row == 1, f"머리글 말고 {ws.max_row - 1}행이 더 있다"
    # ★틀 고정 — 산문이 아니라 **산출물의 동작**이다(수백 행을 채울 때 머리글이 사라지면
    #   어느 칸이 주소인지 모른다). 손 변이 F 에서 **SURVIVED** 였다(도구가 이 줄을 안 골랐다).
    assert ws.freeze_panes == "A2", f"머리글 틀 고정이 없다: {ws.freeze_panes!r}"


def test_guide_sheet_shows_the_example_instead():
    """예시를 없앤 게 아니라 **옮긴** 것이다 — 안내 시트가 실제 예시를 보여 준다."""
    g = _sheet(pes.build_template_xlsx(), "작성안내")
    text = "\n".join(str(r[0].value or "") for r in g.iter_rows(max_col=1))
    assert "의정부동 224" in text, "안내에 예시 주소가 없다"
    assert "511-168" in text, "안내에 예시 지번이 없다"
    assert "산12-3" in text, "'산' 지번 표기 안내가 없다"


def test_guide_promise_that_legacy_files_still_work_is_true():
    """★안내문이 *"이미 쓰던 양식도 그대로 읽는다"* 고 **약속**한다 — 그 약속을 **태운다.**

    약속만 적고 동작을 안 재면 그게 이 저장소가 반복해 데인 자리다.
    """
    g = _sheet(pes.build_template_xlsx(), "작성안내")
    text = "\n".join(str(r[0].value or "") for r in g.iter_rows(max_col=1))
    assert "그대로 올리셔도" in text or "그대로 읽습니다" in text, text[:300]

    # 종전 12열 양식을 **그대로** 태운다(사용자가 이미 갖고 있을 파일).
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append([
        "연번", "소재지(주소)", "지번", "법정동코드(bcode·10자리)",
        "PNU(필지고유번호·19자리)", "지목", "면적(㎡)", "소유구분",
        "토지사용동의(O/X)", "지구단위계획동의(O/X)", "시행자지정동의(O/X)", "비고",
    ])
    ws.append([1, "경기도 의정부시 의정부동 224", "224", "4115010100",
               "", "대", "1000", "사유", "O", "X", "X", ""])
    buf = io.BytesIO()
    wb.save(buf)

    out = _parse(buf.getvalue(), "legacy.xlsx")
    assert not out.get("error"), out.get("error")
    got = out.get("parcels") or []
    assert len(got) == 1, f"종전 양식이 안 읽힌다 — 안내문이 거짓이 된다: {out}"
    p = got[0]
    assert p.get("address") == "경기도 의정부시 의정부동 224", p
    assert p.get("jibun") == "224", p
    # ★동의 칸도 **여전히** 읽는다(양식에서 뺐을 뿐 능력은 그대로다)
    assert p.get("consent_land") is True, f"토지사용동의 O 가 안 읽혔다: {p}"
    assert p.get("consent_district") is False, p
