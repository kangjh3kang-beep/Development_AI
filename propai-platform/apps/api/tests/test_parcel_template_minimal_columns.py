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
import re

from openpyxl import load_workbook

from app.services.land_intelligence import parcel_excel_service as pes


def _sheet(raw: bytes, name: str):
    return load_workbook(io.BytesIO(raw))[name]


def _parse(raw: bytes, fn: str = "t.xlsx"):
    return asyncio.run(pes.ParcelExcelService().parse(raw, fn, use_llm=False))


def test_template_has_exactly_address_and_jibun():
    """★두 열뿐이고, **파서가 그 둘을 주소·지번으로 인식**한다."""
    assert len(pes.TEMPLATE_COLUMNS) == 2, pes.TEMPLATE_COLUMNS
    headers = list(pes.TEMPLATE_COLUMNS)

    # ★손으로 문자열을 대조하지 않는다 — **파서의 판정 함수**에 태운다.
    roles = pes._detect_columns(headers)
    assert roles["address"] == headers[0], f"파서가 1열을 주소로 못 읽는다: {roles}"
    assert roles["jibun"] == headers[1], f"파서가 2열을 지번으로 못 읽는다: {roles}"
    # 공허 방지 — 나머지 역할은 실제로 비어 있어야 한다(열이 둘뿐이므로)
    assert {k for k, v in roles.items() if v} == {"address", "jibun"}, roles


def test_downloaded_sheet_matches_the_declared_columns():
    """선언(`TEMPLATE_COLUMNS`)과 **산출물**(실제 시트)이 같은가 — 선언만 고치는 변경을 막는다."""
    ws = _sheet(pes.build_template_xlsx(), "토지조서")
    assert [c.value for c in ws[1]] == list(pes.TEMPLATE_COLUMNS)
    # ★그리고 **적는 칸의 너비**도 산출물이다(머리글 길이가 아니라 값 길이로 정한다).
    assert ws.column_dimensions["A"].width >= 30, (
        f"주소 칸이 {ws.column_dimensions['A'].width} — 20자 넘는 주소가 안 보인다"
    )


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


# ─────────────────────────────────────────────────────────────────────────────
# ★독립 적대 리뷰(2026-09-12)가 찾은 자리 — 전부 **내가 새로 만든 사용자 대면 거짓**이었다.
#   내 분모는 「데이터 시트」였고 결함은 「워크북」과 「안내문의 약속」에 있었다.
# ─────────────────────────────────────────────────────────────────────────────


def _guide_text() -> str:
    g = _sheet(pes.build_template_xlsx(), "작성안내")
    return "\n".join(str(r[0].value or "") for r in g.iter_rows(max_col=1))


def test_guide_sheet_has_no_literal_markdown():
    """★엑셀 셀은 마크다운을 렌더하지 않는다 — `**` 가 **별표째** 사용자에게 찍힌다.

    실측(이전 판): `**` 리터럴이 **6셀**. `origin/main` 은 0셀이었으니 **내가 새로 만든** 결함이다.
    저장소에 같은 형태의 선례가 있다(`**같아야**` 가 별표째 화면에 찍힘).
    """
    text = _guide_text()
    assert "★" in text or "[토지조서]" in text, "대조군 실패 — 안내문을 못 읽었다"
    assert "**" not in text, (
        "안내 시트에 마크다운 별표가 리터럴로 남았다 — 강조는 Font(bold=True) 로 하라:\n"
        + "\n".join(l for l in text.splitlines() if "**" in l)
    )


def test_guide_sheet_has_no_bare_geocodable_address():
    """★안내 시트에 **그대로 지오코딩되는 맨주소 줄**이 없어야 한다.

    ## 왜 「필지 0건」이 아니라 이 축인가 (기준을 재서 정했다)

    엑셀의 «다른 이름으로 저장 → CSV» 는 **활성 시트만** 내보낸다. 사용자가 안내 시트를
    활성화한 채 저장해 올리면 이 시트가 데이터로 파싱된다. 그때 **필지 0건은 원리적으로
    달성 불가**다 — 파서는 비지 않은 셀을 주소로 보므로 안내문 산문도 행이 된다.
    실측: 현재 판 18행 · `origin/main` 9행. **둘 다 그렇다(회귀가 아니다).**

    ★갈라 주는 것은 **맨주소가 섞였는가**다. 산문 행은 사용자 눈에 즉시 쓰레기로 보이고
    지오코딩도 실패한다. 그러나 `경기도 안양시 동안구 비산동 511-168` 같은 **맨주소**는
    조회에 성공해 **없는 필지가 그럴듯하게 등록**된다.
    독립 리뷰 실측(이전 판): 맨주소 **2건** ↔ `origin/main` **0건** — 내가 새로 심었던 위험이다.
    ⇒ 예시를 `(보기: …)` 로 감싸고 머리글처럼 보이던 표 줄(`소재지(주소) | 지번`)을 없앴다.
    """
    BARE = re.compile(
        r"^\s*(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청|충북|충남|"
        r"전라|전북|전남|경상|경북|경남|제주)\S*\s+\S+.*\s산?\d+(-\d+)?\s*$"
    )
    # ★대조군 먼저 — 검사기가 살아 있는가(순서를 바꾸면 사람이 먼저 결론을 낸다)
    assert BARE.match("경기도 안양시 동안구 비산동 511-168"), "검사기 사망 — 맨주소를 못 잡는다"
    assert not BARE.match("     (보기: 경기도 의정부시 의정부동 224)"), "검사기 과탐 — 보기를 맨주소로 본다"

    g = _sheet(pes.build_template_xlsx(), "작성안내")
    lines = [str(r[0].value or "") for r in g.iter_rows(max_col=1)]
    assert len(lines) >= 10, f"안내문을 못 읽었다(공허 방지): {len(lines)}줄"
    offenders = [l for l in lines if BARE.match(l)]
    assert offenders == [], (
        "안내 시트에 그대로 지오코딩되는 맨주소가 있다 — 이 시트를 CSV 로 올리면 "
        "없는 필지가 «성공적으로» 등록된다:\n" + "\n".join(offenders)
    )



def test_guide_makes_no_promise_the_code_does_not_keep():
    """★안내문의 **약속**을 코드와 대조한다 — 거짓 약속은 사용자 대면 산출물에 인쇄된다.

    ① 소유구분 「자동 조회」는 **거짓**이었다: `owner_type` 이 값을 얻는 자리는 엑셀 셀뿐이고
       (`:981`), 공부의 `posesnSeCodeNm` 은 프론트 도달 **0건**(대조군 `official_price_per_sqm` 82건).
    ② 지번 「따로 적으면 더 정확」도 **거짓**이었다: `_geocode_fill` 은
       `jibun not in addr` 일 때만 결합하므로, 안내문 예시처럼 주소에 번지가 있으면
       질의가 **문자 단위로 동일**하다.
    """
    text = _guide_text()
    from pathlib import Path as _P
    src = (_P(pes.__file__)).read_text(encoding="utf-8")

    # ① 자동 조회 목록에 소유구분이 없어야 한다
    auto_lines = [l for l in text.splitlines() if "자동으로 조회합니다" in l]
    assert auto_lines, "대조군 실패 — 「자동으로 조회」 문장을 못 찾았다"
    for l in auto_lines:
        assert "소유구분" not in l, f"소유구분을 자동 조회한다고 약속한다(거짓): {l}"
    # 그리고 **안 한다고** 명시했는가
    assert "소유구분은 자동으로 조회하지 않습니다" in text, (
        "소유구분을 빼기만 하고 «안 한다»를 말하지 않으면 사용자는 여전히 기대한다"
    )

    # ② 지번 약속이 코드와 맞는가 — 코드는 「주소에 없을 때만」 결합한다
    assert "jibun not in addr" in src, "지오코딩 결합 조건이 바뀌었다 — 이 락을 다시 맞춰라"
    assert "비워 두셔도 결과가 같습니다" in text, (
        "지번이 조회에 기여하지 않는 경우를 안내문이 말하지 않는다"
    )
    assert "더 정확합니다" not in text, "코드가 지키지 않는 «더 정확» 약속이 남아 있다"
