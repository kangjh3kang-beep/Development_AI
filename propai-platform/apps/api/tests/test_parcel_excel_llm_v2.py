"""토지조서 엑셀 LLM 보조 반복검증 v2 — 다양식 픽스처 매트릭스(T6).

검증 범위:
  T1 use_llm 게이트 — False면 LLM 0호출(비용/신뢰 보장).
  T2 S1 구조인식 — 시트선택·전치판정·복합셀분해·컬럼역할을 '한 번의 질의'로 처리(중복 프롬프트
    금지), 실존 검증 실패(가짜 시트/컬럼명)는 거부.
  T3 S3 반복검증 — 결정론 게이트(지번형식·PNU19자리·미해소상태)+합계행 감지+선별 재질의(최대2회,
    원문 부분문자열만 채택).
  T4 S4 분류 — verified/corrected/needs_review + verification_report(additive, 기존 키 불변).

픽스처는 openpyxl로 테스트 내 동적 생성(바이너리 커밋 금지). LLM은 전부 mock(get_llm 패치,
실제 API 미호출). VWorld는 결정적 stub(네트워크 없는 환경에서도 안정적으로 검증).
"""
from __future__ import annotations

import asyncio
import io
import json

import pytest

from app.services.land_intelligence import parcel_excel_service as pes


# ── 공용 헬퍼 ────────────────────────────────────────────────────────────
def _xlsx(rows: list[list], sheet_title: str = "토지조서",
          extra_sheets: dict[str, list[list]] | None = None) -> bytes:
    """행 리스트 → xlsx 바이트(테스트 내 동적 생성)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title
    for r in rows:
        ws.append(r)
    for name, rs in (extra_sheets or {}).items():
        s = wb.create_sheet(name)
        for r in rs:
            s.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class _StubVWorld:
    """결정적 VWorld 대역 — PNU가 직접 주어진 필지는 조회 성공(happy path 안정),
    주소만으로 지오코딩해야 하는 필지는 실패(네트워크 없는 테스트 환경 — 정직 실패 검증용).
    """

    async def geocode_address(self, query):
        return None

    async def get_land_characteristics(self, pnu):
        return {"zone_type": "제2종일반주거지역", "land_category": "대",
                "official_price_per_sqm": 1_000_000}

    async def search_address(self, query, size=8):
        return []


@pytest.fixture(autouse=True)
def _patch_vworld(monkeypatch):
    import app.services.external_api.vworld_service as vmod
    monkeypatch.setattr(vmod, "VWorldService", _StubVWorld)


@pytest.fixture(autouse=True)
def _clear_llm_struct_cache():
    """구조질의 캐시(_STRUCT_CACHE)는 모듈 전역 — 테스트 간 시그니처 충돌(다른 테스트의 mock
    응답이 캐시로 새는 것) 방지를 위해 매 테스트 전후로 비운다."""
    pes._STRUCT_CACHE.clear()
    yield
    pes._STRUCT_CACHE.clear()


def _fake_llm(responder):
    """ainvoke가 human 프롬프트 텍스트를 responder(human)->json문자열 에 넘겨 응답을 만드는 가짜 LLM."""

    class _Resp:
        def __init__(self, content: str):
            self.content = content
            self.usage_metadata = {"input_tokens": 10, "output_tokens": 5}

    class _LLM:
        model = "fake-model"

        async def ainvoke(self, messages):
            human = messages[-1].content if messages else ""
            return _Resp(responder(human))

    def _factory(*_a, **_k):
        return _LLM()

    return _factory


def _patch_llm(monkeypatch, responder):
    monkeypatch.setattr("app.services.ai.llm_provider.get_llm", _fake_llm(responder))


def _no_llm_reply(_human: str) -> str:
    """구조질의엔 응답 없음(호출되면 실패해야 하는 use_llm=False 테스트용)."""
    raise AssertionError("use_llm=False인데 LLM이 호출됨")


# ── ① 표준양식 — 규칙기반만으로 완결, LLM 0호출 ──────────────────────────
def test_standard_form_rule_based_zero_llm_calls(monkeypatch):
    monkeypatch.setattr("app.services.ai.llm_provider.get_llm", _fake_llm(_no_llm_reply))
    raw = _xlsx([
        ["연번", "소재지(주소)", "지번", "법정동코드(bcode·10자리)", "PNU(필지고유번호·19자리)", "지목", "면적(㎡)", "소유구분"],
        [1, "서울특별시 동작구 상도동", "210-453", "1159010300", "1159010300102100453", "대", "200", "사유"],
        [2, "경기도 의정부시 의정부동", "224-1", "4115010100", "4115010100201100224", "대", "150", "사유"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "표준.xlsx", use_llm=False))
    assert not out.get("error")
    assert len(out["parcels"]) == 2
    assert out["column_engine"] == "rule"
    vr = out["verification_report"]
    assert vr["llm_used"] is False
    assert vr["passes"] == 0
    assert vr["counts"] == {"verified": 2, "corrected": 0, "needs_review": 0, "excluded": 0}
    assert all(p["injectable"] for p in out["parcels"])


def test_standard_form_use_llm_true_still_zero_calls_when_confident(monkeypatch):
    """use_llm=True라도 규칙기반이 이미 신뢰도 높으면 LLM을 호출하지 않는다(비용 보호)."""
    monkeypatch.setattr("app.services.ai.llm_provider.get_llm", _fake_llm(_no_llm_reply))
    raw = _xlsx([
        ["소재지(주소)", "지번", "PNU(필지고유번호·19자리)"],
        ["서울특별시 동작구 상도동", "210-453", "1159010300102100453"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "표준2.xlsx", use_llm=True))
    assert not out.get("error")
    assert out["verification_report"]["llm_used"] is False


# ── ② 비표준 헤더(동의어 밖) — LLM 컬럼 역할 분류 ────────────────────────
def test_nonstandard_headers_llm_column_mapping(monkeypatch):
    def responder(_human: str) -> str:
        return json.dumps({"columns": {"address": "A열", "jibun": "B열", "pnu": "C열"}}, ensure_ascii=False)

    _patch_llm(monkeypatch, responder)
    raw = _xlsx([
        ["A열", "B열", "C열"],
        ["서울특별시 동작구 상도동", "210-453", "1159010300102100453"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "비표준.xlsx", use_llm=True))
    assert not out.get("error")
    assert out["column_engine"] == "rule+llm"
    assert len(out["parcels"]) == 1
    assert out["parcels"][0]["address"] == "서울특별시 동작구 상도동"
    assert out["parcels"][0]["jibun"] == "210-453"


# ── ③ 세로형(전치) — LLM is_transposed 판정 → 결정론 전치 후 재파싱 ──────
def test_transposed_form_deterministic_transpose(monkeypatch):
    def responder(_human: str) -> str:
        return json.dumps({"is_transposed": True}, ensure_ascii=False)

    _patch_llm(monkeypatch, responder)
    raw = _xlsx([
        ["항목", "필지1", "필지2"],
        ["소재지", "서울특별시 동작구 상도동", "경기도 의정부시 의정부동 224"],
        ["지번", "210-453", "224"],
        ["PNU", "1159010300102100453", "4115010100201100224"],
        ["면적", "200", "300"],
        ["지목", "대", "대"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "전치.xlsx", use_llm=True))
    assert not out.get("error")
    assert out["column_engine"] == "rule+llm"
    assert len(out["parcels"]) == 2
    addrs = {p["address"] for p in out["parcels"]}
    assert addrs == {"서울특별시 동작구 상도동", "경기도 의정부시 의정부동 224"}
    jibuns = {p["jibun"] for p in out["parcels"]}
    assert jibuns == {"210-453", "224"}


# ── ④ 다중시트(2번째가 토지조서) — LLM sheet_name 재선택(실존 검증) ──────
def test_multi_sheet_llm_reselects_correct_sheet(monkeypatch):
    def responder(_human: str) -> str:
        return json.dumps({"sheet_name": "필지목록"}, ensure_ascii=False)

    _patch_llm(monkeypatch, responder)
    raw = _xlsx(
        rows=[["프로젝트 개요"], ["작성일자: 2026-01-01"], ["담당자: 홍길동"]],
        sheet_title="표지",
        extra_sheets={
            "필지목록": [
                ["소재지(주소)", "지번", "PNU(필지고유번호·19자리)"],
                ["서울특별시 동작구 상도동", "210-453", "1159010300102100453"],
                ["경기도 의정부시 의정부동 224", "224-1", "4115010100201100224"],
            ],
        },
    )
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "다중시트.xlsx", use_llm=True))
    assert not out.get("error")
    assert out["column_engine"] == "rule+llm"
    assert len(out["parcels"]) == 2


# ── ⑤ 복합셀("의정부동 224-1 대 500㎡") — LLM regex 제안 → 매치율≥60% 채택 ─
def test_compound_cell_decomposition_applied_when_match_rate_high(monkeypatch):
    def responder(human: str) -> str:
        if "compound_cell" in human:
            return json.dumps({
                "compound_cell": {
                    "column": "복합정보",
                    "regex": r"(?P<addr>[가-힣]+동)\s+(?P<jibun>\d+(-\d+)?)\s+(?P<jimok>[가-힣])\s+(?P<area>\d+)㎡",
                },
            }, ensure_ascii=False)
        return "{}"

    _patch_llm(monkeypatch, responder)
    raw = _xlsx([
        ["복합정보"],
        ["의정부동 224-1 대 500㎡"],
        ["상도동 210-453 대 200㎡"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "복합.xlsx", use_llm=True))
    assert not out.get("error")
    assert out["column_engine"] == "rule+llm"
    assert len(out["parcels"]) == 2
    addrs = {p["address"] for p in out["parcels"]}
    assert addrs == {"의정부동", "상도동"}
    jibuns = {p["jibun"] for p in out["parcels"]}
    assert jibuns == {"224-1", "210-453"}
    areas = {p["area_sqm"] for p in out["parcels"]}
    assert areas == {500.0, 200.0}


def test_compound_cell_discarded_when_match_rate_below_threshold(monkeypatch):
    """매치율<60%면 폐기 — 채택되지 않아 결국 필수컬럼(address/pnu/bcode) 미확보 에러."""
    def responder(human: str) -> str:
        if "compound_cell" in human:
            return json.dumps({
                "compound_cell": {"column": "복합정보", "regex": r"(?P<addr>동작구)"},
            }, ensure_ascii=False)
        return "{}"

    _patch_llm(monkeypatch, responder)
    raw = _xlsx([
        ["복합정보"],
        ["서울특별시 동작구 상도동 210-453"],
        ["경기도 의정부시 의정부동 224-1"],
        ["부산광역시 해운대구 우동 500"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "복합폐기.xlsx", use_llm=True))
    assert out.get("error"), "매치율 1/3(33%)<60% 이므로 복합셀 분해가 폐기되고 필수컬럼 에러여야 함"


# ── ⑥ 합계행 오염 — 키워드/누적합 두 경로 모두 제외 + 대조 경고 ─────────
def test_summary_row_excluded_by_keyword_and_mismatch_warning():
    raw = _xlsx([
        ["소재지(주소)", "지번", "PNU(필지고유번호·19자리)", "면적(㎡)"],
        ["서울특별시 동작구 상도동", "210-453", "1159010300102100453", "200"],
        ["경기도 의정부시 의정부동 224", "224-1", "4115010100201100224", "150"],
        ["합계", "", "", "999"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "합계.xlsx", use_llm=False))
    assert not out.get("error")
    assert len(out["parcels"]) == 2
    vr = out["verification_report"]
    assert vr["counts"]["excluded"] == 1
    assert any("합계" in w and "차이" in w for w in vr["warnings"])


def test_summary_row_excluded_by_cumulative_area_match():
    """키워드가 없어도(예: '집계') 면적이 상위행 누적합과 ±1% 이내면 집계행으로 감지·제외."""
    raw = _xlsx([
        ["소재지(주소)", "지번", "PNU(필지고유번호·19자리)", "면적(㎡)"],
        ["서울특별시 동작구 상도동", "210-453", "1159010300102100453", "200"],
        ["경기도 의정부시 의정부동 224", "224-1", "4115010100201100224", "150"],
        ["집계", "", "", "350"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "집계.xlsx", use_llm=False))
    assert not out.get("error")
    assert len(out["parcels"]) == 2
    assert out["verification_report"]["counts"]["excluded"] == 1


# ── ⑦ 병합셀 — forward-fill(공유지분) 회귀 확인(_rebuild 리팩토링 후에도 유지) ─
def test_merged_cells_forward_fill():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "토지조서"
    ws.append(["소재지(주소)", "지번", "PNU(필지고유번호·19자리)", "소유구분"])
    ws.append(["서울특별시 동작구 상도동", "210-453", "1159010300102100453", "김철수"])
    ws.append(["", "", "", "이영희"])
    ws.merge_cells("A2:A3")
    ws.merge_cells("B2:B3")
    ws.merge_cells("C2:C3")
    buf = io.BytesIO()
    wb.save(buf)
    raw = buf.getvalue()

    out = asyncio.run(pes.ParcelExcelService().parse(raw, "병합.xlsx", use_llm=False))
    assert not out.get("error")
    assert len(out["parcels"]) == 2
    assert out["parcels"][0]["jibun"] == out["parcels"][1]["jibun"] == "210-453"
    assert all(p.get("co_owner") for p in out["parcels"]), "같은 PNU 공유지분(병합 복원)으로 표시돼야 함"


# ── ⑧ CSV cp949 인코딩 폴백 ───────────────────────────────────────────
def test_csv_cp949_encoding_fallback():
    csv_text = ("소재지(주소),지번,PNU(필지고유번호·19자리)\n"
                "서울특별시 동작구 상도동,210-453,1159010300102100453\n")
    raw = csv_text.encode("cp949")
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "cp949.csv", use_llm=False))
    assert not out.get("error")
    assert len(out["parcels"]) == 1
    assert out["parcels"][0]["address"] == "서울특별시 동작구 상도동"


# ── ⑨ 예시행 잔존 — 예시값 미삭제 사고(하드코딩 면적) 재발 방지 확인 ──────
def test_template_example_rows_no_fake_area_injection():
    raw = pes.build_template_xlsx()
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "template.xlsx", use_llm=False))
    assert not out.get("error")
    for p in out["parcels"]:
        assert p.get("area_sqm") not in (14959, 8500), "예시행의 옛 하드코딩 면적값이 재발하면 안 됨"


# ── ⑩ 빈/깨진 파일 — 정직 실패(크래시 없이 error) ────────────────────────
def test_empty_and_corrupt_file_honest_failure():
    out1 = asyncio.run(pes.ParcelExcelService().parse(b"", "empty.xlsx", use_llm=False))
    assert out1.get("error")
    assert out1["parcels"] == []

    out2 = asyncio.run(pes.ParcelExcelService().parse(b"not a real xlsx content", "broken.xlsx", use_llm=False))
    assert out2.get("error")
    assert out2["parcels"] == []


# ── 반복검증(S3): 중복 필지·PNU 형식·합계 불일치 ─────────────────────────
def test_duplicate_pnu_marks_ambiguous_and_needs_review():
    raw = _xlsx([
        ["소재지(주소)", "지번", "PNU(필지고유번호·19자리)"],
        ["서울특별시 동작구 상도동", "210-453", "1159010300102100453"],
        ["경기도 성남시 분당구 정자동", "999-1", "1159010300102100453"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "중복.xlsx", use_llm=False))
    assert not out.get("error")
    assert out["duplicate_pnu_warning"]
    assert {p["status"] for p in out["parcels"]} == {"ambiguous"}
    vr = out["verification_report"]
    assert vr["counts"]["needs_review"] == 2
    assert all(not p["injectable"] for p in out["parcels"])


def test_jibun_format_gate_allows_san_and_rejects_garbage():
    assert pes._JIBUN_RE.match("210-453")
    assert pes._JIBUN_RE.match("산12-3")
    assert pes._JIBUN_RE.match("224")
    assert not pes._JIBUN_RE.match("확인필요")
    assert not pes._JIBUN_RE.match("N/A")


def test_jibun_format_issue_triggers_reverify_and_correction(monkeypatch):
    """지번 형식 불량 행 — 같은 행의 다른 원본 셀(비고)에 있는 값을 재질의로 부분문자열 채택."""
    def responder(human: str) -> str:
        if "검증 실패 사유" in human:
            return json.dumps({"jibun": "210-453"}, ensure_ascii=False)
        return "{}"

    _patch_llm(monkeypatch, responder)
    raw = _xlsx([
        ["소재지(주소)", "지번", "비고"],
        ["서울특별시 동작구 상도동", "확인필요", "실제 지번 210-453 로 추정"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "재질의.xlsx", use_llm=True))
    vr = out["verification_report"]
    assert vr["passes"] >= 1
    assert vr["llm_used"] is True
    corr = [c for c in vr["corrections"] if c["field"] == "jibun"]
    assert corr and corr[0]["after"] == "210-453"
    assert out["parcels"][0]["jibun"] == "210-453"


def test_reverify_capped_at_two_passes_when_unresolvable(monkeypatch):
    call_count = {"n": 0}

    def responder(_human: str) -> str:
        call_count["n"] += 1
        return "{}"  # 원문에 유효 후보가 없다고 가정(교정 불가) — 최대 2회로 멈춰야 함

    _patch_llm(monkeypatch, responder)
    raw = _xlsx([
        ["소재지(주소)", "지번"],
        ["서울특별시 동작구 상도동", "확인불가"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "미해결.xlsx", use_llm=True))
    vr = out["verification_report"]
    assert vr["passes"] == 2
    assert call_count["n"] == 2
    assert vr["counts"]["needs_review"] == 1


# ── use_llm=False 게이트 — 구조가 아무리 나빠도(전치+비표준) LLM 0호출 ────
def test_use_llm_false_zero_llm_calls_even_on_bad_form(monkeypatch):
    monkeypatch.setattr("app.services.ai.llm_provider.get_llm", _fake_llm(_no_llm_reply))
    raw = _xlsx([
        ["항목", "필지1"],
        ["소재지", "서울특별시 동작구 상도동"],
        ["지번", "210-453"],
        ["PNU", "1159010300102100453"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "bad.xlsx", use_llm=False))
    assert out["verification_report"]["llm_used"] is False
    assert out["verification_report"]["passes"] == 0


# ── 환각 차단 ─────────────────────────────────────────────────────────
def test_parse_rejects_hallucinated_sheet_and_column_names(monkeypatch):
    """LLM이 실존하지 않는 시트명·컬럼명을 답해도 채택되지 않는다(정직 실패로 귀결)."""
    calls: list[str] = []

    def responder(human: str) -> str:
        calls.append(human)
        return json.dumps({"sheet_name": "존재안함시트", "columns": {"address": "존재안함컬럼"}},
                           ensure_ascii=False)

    _patch_llm(monkeypatch, responder)
    raw = _xlsx([
        ["X1", "X2", "X3"],
        ["서울특별시 동작구 상도동", "210-453", "200"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "환각.xlsx", use_llm=True))
    assert calls, "LLM은 호출됐어야 함(구조질의 시도)"
    assert out.get("error"), "가짜 시트/컬럼명은 거부되어 필수컬럼 에러로 귀결해야 함"


def test_reverify_hallucination_guard_rejects_non_substring(monkeypatch):
    """LLM이 원본 셀에 없는 값을 답하면(새로 생성) 채택하지 않는다."""
    def responder(_human: str) -> str:
        return json.dumps({"jibun": "완전조작된값"}, ensure_ascii=False)

    _patch_llm(monkeypatch, responder)
    cand, hit = asyncio.run(
        pes._llm_reverify_row({"지번": "확인필요", "비고": "실제지번 아님"}, ["jibun_format"])
    )
    assert hit is True
    assert cand == {}, "원본 셀에 실존하지 않는 값은 채택되지 않아야 함(환각 차단)"


def test_reverify_hallucination_guard_accepts_valid_substring(monkeypatch):
    def responder(_human: str) -> str:
        return json.dumps({"jibun": "224-1"}, ensure_ascii=False)

    _patch_llm(monkeypatch, responder)
    cand, hit = asyncio.run(
        pes._llm_reverify_row({"지번": "확인필요", "비고": "실제 지번 224-1"}, ["jibun_format"])
    )
    assert hit is True
    assert cand == {"jibun": "224-1"}
