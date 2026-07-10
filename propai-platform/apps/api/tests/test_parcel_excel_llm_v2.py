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
    # ★H3: injectable=False는 표에서 완전히 제외된 행(합계/집계)에만 쓴다 — ambiguous(needs_review)
    #   도 일단 주입해 주입 후 2차 enrich의 재지오코딩·재검증으로 자기치유되게 한다(과거엔
    #   이 자기치유 경로가 자동반영 제외로 조용히 끊겼었음). 분류·사유는 verification_status/
    #   verification_reasons로 계속 노출된다.
    assert all(p["injectable"] for p in out["parcels"])
    assert all(p["verification_status"] == "needs_review" for p in out["parcels"])


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


def test_reverify_stops_after_pass1_when_zero_corrections(monkeypatch):
    """H4-①: pass1이 한 건도 교정하지 못하면 pass2를 생략한다(동일 셀 재질의 과금 폭주 방지).
    (구 테스트명 test_reverify_capped_at_two_passes_when_unresolvable — 2회 고정 재시도였던
    구동작을 대체: 이제 무교정이면 1회로 멈춘다.)"""
    call_count = {"n": 0}

    def responder(_human: str) -> str:
        call_count["n"] += 1
        return "{}"  # 원문에 유효 후보가 없다고 가정(교정 불가) — pass1에서 즉시 멈춰야 함

    _patch_llm(monkeypatch, responder)
    raw = _xlsx([
        ["소재지(주소)", "지번"],
        ["서울특별시 동작구 상도동", "확인불가"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "미해결.xlsx", use_llm=True))
    vr = out["verification_report"]
    assert vr["passes"] == 1
    assert call_count["n"] == 1, "pass1 무교정 → LLM 재질의 호출은 pass1의 1건뿐이어야 함(pass2 생략)"
    assert vr["counts"]["needs_review"] == 1


def test_reverify_continues_to_pass2_when_pass1_has_correction(monkeypatch):
    """H4-①의 반대 경계: pass1에서 '어떤 행이든' 교정이 있었으면 아직 미해결 행에 대해
    pass2까지 시도한다(무교정일 때만 조기종료 — 교정 성공 시 조기종료로 다른 행 기회를
    빼앗으면 안 됨)."""
    class _Geo:
        async def geocode_address(self, query):
            if "210-453" in query:
                return {"lat": 37.5, "lon": 127.0, "pnu": "1159010300102100453"}
            return None
        async def get_land_characteristics(self, pnu):
            return {"zone_type": "제2종일반주거지역", "land_category": "대", "official_price_per_sqm": 1_000_000}
        async def search_address(self, query, size=8):
            return []

    import app.services.external_api.vworld_service as vmod
    monkeypatch.setattr(vmod, "VWorldService", _Geo)

    def responder(human: str) -> str:
        if "행1" in human:
            return json.dumps({"jibun": "210-453"}, ensure_ascii=False)
        return "{}"  # 행2는 끝까지 교정 불가

    _patch_llm(monkeypatch, responder)
    raw = _xlsx([
        ["소재지(주소)", "지번", "비고"],
        ["서울특별시 동작구 상도동", "확인필요", "행1 실제 지번 210-453 로 추정"],
        ["경기도 의정부시 의정부동", "확인불가", "행2 단서 없음"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "부분교정.xlsx", use_llm=True))
    vr = out["verification_report"]
    assert vr["passes"] == 2, "행1이 교정·재지오코딩으로 해소됐으므로 행2를 위해 pass2까지 시도해야 함"
    assert out["parcels"][0]["status"] == "ok"
    assert out["parcels"][0]["verification_status"] == "corrected"
    assert out["parcels"][1]["verification_status"] == "needs_review"
    assert vr["counts"] == {"verified": 0, "corrected": 1, "needs_review": 1, "excluded": 0}


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


# ── M1: 재질의 환각가드 강화(셀단위 검사 + 역할별 형식 게이트) ────────────
def test_reverify_area_rejects_pnu_fragment_via_haystack(monkeypatch):
    """M1 재현: 전 셀을 이어붙인 haystack 검사면 PNU 숫자파편("10300")이 area로 오채택될 수
    있다 — 셀 단위 검사(그 파편이 속한 셀 전체가 PNU이지 면적이 아님)로 거부해야 한다."""
    def responder(_human: str) -> str:
        return json.dumps({"area": "10300"}, ensure_ascii=False)

    _patch_llm(monkeypatch, responder)
    cand, hit = asyncio.run(
        pes._llm_reverify_row({"PNU": "9910300000", "비고": "확인 필요"}, ["area_format"])
    )
    assert hit is True
    assert cand == {}, "PNU 숫자파편이 area로 채택되면 안 됨(출처 셀 전체가 PNU이지 면적이 아님)"


def test_reverify_area_accepts_pure_numeric_or_unit_cell(monkeypatch):
    """M1: 정상 면적 후보 셀(순수 숫자, 또는 ㎡ 단위 표기 셀)의 값은 area로 채택된다."""
    def responder(_human: str) -> str:
        return json.dumps({"area": "200"}, ensure_ascii=False)

    _patch_llm(monkeypatch, responder)
    cand, hit = asyncio.run(
        pes._llm_reverify_row({"면적": "200㎡", "비고": "확인 필요"}, ["area_format"])
    )
    assert hit is True
    assert cand == {"area": "200"}


# ── M2: 교정 후 재지오코딩 조건(need_geocode 상태 누락 수정) ─────────────
def test_reverify_correction_retriggers_geocode_from_need_geocode_status(monkeypatch):
    """M2 재현: 기존엔 status in (failed, ambiguous)만 재지오코딩 트리거로 체크해 need_geocode
    상태(주소는 있으나 PNU 미확보)인 행의 지번 교정이 재지오코딩으로 이어지지 못하고 사장됐다.
    _UNRESOLVED_STATUSES(need_geocode 포함)로 통일해 교정 후 자기치유(PNU 확보)까지 이어진다."""
    class _Geo:
        async def geocode_address(self, query):
            if "210-453" in query:
                return {"lat": 37.5, "lon": 127.0, "pnu": "1159010300102100453"}
            return None
        async def get_land_characteristics(self, pnu):
            return {"zone_type": "제2종일반주거지역", "land_category": "대", "official_price_per_sqm": 1_000_000}
        async def search_address(self, query, size=8):
            return []

    import app.services.external_api.vworld_service as vmod
    monkeypatch.setattr(vmod, "VWorldService", _Geo)

    def responder(human: str) -> str:
        if "검증 실패 사유" in human:
            return json.dumps({"jibun": "210-453"}, ensure_ascii=False)
        return "{}"

    _patch_llm(monkeypatch, responder)
    raw = _xlsx([
        ["소재지(주소)", "지번", "비고"],
        ["서울특별시 동작구 상도동", "확인필요", "실제 지번 210-453 로 추정"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "재지오코딩.xlsx", use_llm=True))
    assert out["parcels"][0]["jibun"] == "210-453"
    assert out["parcels"][0]["status"] == "ok", "교정 후 재지오코딩으로 PNU 확보(자기치유)돼야 함"
    assert out["parcels"][0]["pnu"] == "1159010300102100453"


# ── M4: 누적합 합계행 오제외 경계(bcode 있는 정상 행 보호) ────────────────
def test_cumulative_area_summary_gate_respects_bcode_presence():
    """M4 재현: 누적합 분기는 키워드 분기와 달리 not bcode 조건이 없어, bcode가 있는 정상
    행(면적이 우연히 이전 누적합과 일치)이 집계행으로 오제외될 수 있었다."""
    raw = _xlsx([
        ["소재지(주소)", "지번", "법정동코드(bcode·10자리)", "면적(㎡)"],
        ["서울특별시 동작구 상도동", "210-453", "1159010300", "100"],
        ["경기도 의정부시 의정부동", "224-1", "4115010100", "50"],
        # 지번은 비어있지만 bcode가 있는 정상 필지 — 면적이 우연히 위 두 행의 합(150)과 일치.
        ["부산광역시 해운대구 우동", "", "2635010100", "150"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "경계.xlsx", use_llm=False))
    assert not out.get("error")
    assert len(out["parcels"]) == 3, "bcode 있는 정상 행이 누적합 오탐으로 제외되면 안 됨"
    assert out["verification_report"]["counts"]["excluded"] == 0


def test_summary_row_exclusion_is_not_silent():
    """M4: 제외된 행의 원문 요약이 warnings에 남아야 한다(무음 제외 금지)."""
    raw = _xlsx([
        ["소재지(주소)", "지번", "PNU(필지고유번호·19자리)", "면적(㎡)"],
        ["서울특별시 동작구 상도동", "210-453", "1159010300102100453", "200"],
        ["합계", "", "", "200"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "무음제외.xlsx", use_llm=False))
    assert not out.get("error")
    warnings = out["verification_report"]["warnings"]
    assert any("집계/합계 추정 행 제외" in w and "합계" in w for w in warnings), (
        "제외된 행의 원문이 warnings에 표면화돼야 함(무음 금지)"
    )


# ── L5: co_owner(공유지분 연속행)는 'corrected'가 아니라 'verified' ───────
def test_co_owner_rows_classified_verified_not_corrected():
    """L5: 병합복원 등으로 co_owner=True 표시된 공유지분 연속행은 실제 값 보정이 아니므로
    'corrected'가 아니라 'verified'로 분류하고, 사유에 '공유지분 연속행'을 명시한다."""
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

    out = asyncio.run(pes.ParcelExcelService().parse(raw, "공유지분.xlsx", use_llm=False))
    assert not out.get("error")
    assert len(out["parcels"]) == 2
    for p in out["parcels"]:
        assert p["verification_status"] == "verified"
        assert "공유지분 연속행" in p["verification_reasons"]
        assert p["injectable"] is True


# ── L6: _reverify_loop gather 예외 로그(무음 금지) ────────────────────────
def test_reverify_loop_logs_gather_exceptions_not_silent(monkeypatch):
    """L6: asyncio.gather(return_exceptions=True)로 삼켜지던 개별 행 처리 예외가 로그로
    남아야 한다(무음 금지). 예외가 나도 parse()는 크래시 없이 정상 반환해야 한다."""
    logged: list[tuple] = []

    class _FakeLogger:
        def warning(self, *a, **k):
            logged.append((a, k))

        def info(self, *a, **k):
            pass

    monkeypatch.setattr(pes, "logger", _FakeLogger())

    async def _boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(pes, "_llm_reverify_row", _boom)
    raw = _xlsx([
        ["소재지(주소)", "지번"],
        ["서울특별시 동작구 상도동", "확인불가"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "예외.xlsx", use_llm=True))
    assert not out.get("error")
    assert logged, "gather에서 삼켜지던 개별 행 처리 예외가 로그로 남아야 함(무음 금지)"


# ── C1: _STRUCT_CACHE에 행범위가 남아 재업로드 절단 ───────────────────────
def test_struct_cache_excludes_data_range_no_truncation_on_reupload(monkeypatch):
    """C1 재현: 캐시 키(시트목록+현재시트+헤더)에는 행수가 없는데 캐시값에 data_start/end_row가
    남아 있으면, 같은 양식을 행 늘려 재업로드할 때 이전 행범위로 절단된다(1행 업로드 후 4행
    재업로드 → 1필지로 절단·LLM 0호출). 캐시엔 구조속성만 남아야 재업로드 시 전체 행이 산다."""
    call_count = {"n": 0}

    def responder(_human: str) -> str:
        call_count["n"] += 1
        # 1행짜리 업로드 시점 기준 데이터범위(0-based, 헤더행 다음 1개행=인덱스1)를 그대로 답한다.
        return json.dumps({
            "columns": {"address": "A열", "jibun": "B열", "pnu": "C열"},
            "data_start_row": 1, "data_end_row": 1,
        }, ensure_ascii=False)

    _patch_llm(monkeypatch, responder)
    svc = pes.ParcelExcelService()

    raw1 = _xlsx([
        ["A열", "B열", "C열"],
        ["서울특별시 동작구 상도동", "210-453", "1159010300102100453"],
    ])
    out1 = asyncio.run(svc.parse(raw1, "비표준1.xlsx", use_llm=True))
    assert not out1.get("error")
    assert len(out1["parcels"]) == 1
    assert call_count["n"] == 1

    raw4 = _xlsx([
        ["A열", "B열", "C열"],
        ["서울특별시 동작구 상도동", "210-453", "1159010300102100453"],
        ["경기도 의정부시 의정부동 224", "224-1", "4115010100201100224"],
        ["부산광역시 해운대구 우동 500", "500", "2635010100105000000"],
        ["대구광역시 수성구 범어동", "1-1", "2726010600100010000"],
    ])
    out2 = asyncio.run(svc.parse(raw4, "비표준4.xlsx", use_llm=True))
    assert not out2.get("error")
    assert len(out2["parcels"]) == 4, "캐시 히트로 이전 1행 범위에 절단되면 안 됨"
    assert call_count["n"] == 1, "구조질의 캐시 히트 — LLM 재호출 없이도 전체 행이 반영돼야 함"
    assert out2["verification_report"]["llm_used"] is True, "캐시 히트라도 LLM 유래 구조 적용은 llm_used=True(M3)"


# ── H1: data_start/end_row off-by-one(마지막 행 상시 절단) ───────────────
def test_data_range_slice_is_0_based_not_off_by_one(monkeypatch):
    """H1 재현: 프롬프트는 0-based 미리보기 행을 지시하는데 적용부가 base=hdr+2(1-based)로
    매핑해 마지막 데이터 행이 상시 절단됐다(3행+end=3행(0-based 마지막)→2필지로 절단).
    base=hdr+1(0-based)로 통일하면 3행 모두 온전히 남아야 한다."""
    def responder(_human: str) -> str:
        return json.dumps({
            "columns": {"address": "A열", "jibun": "B열", "pnu": "C열"},
            # 헤더가 0행, 데이터는 1~3행(0-based, 미리보기 grid 좌표) — 3행 전부 포함하려는 의도.
            "data_start_row": 1, "data_end_row": 3,
        }, ensure_ascii=False)

    _patch_llm(monkeypatch, responder)
    raw = _xlsx([
        ["A열", "B열", "C열"],
        ["서울특별시 동작구 상도동", "210-453", "1159010300102100453"],
        ["경기도 의정부시 의정부동 224", "224-1", "4115010100201100224"],
        ["부산광역시 해운대구 우동", "500", "2635010100105000000"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "off-by-one.xlsx", use_llm=True))
    assert not out.get("error")
    assert len(out["parcels"]) == 3, "0-based 데이터범위 3행이 모두 온전히 남아야 함(off-by-one 회귀)"


def test_data_range_slice_truncation_is_reported_in_warnings(monkeypatch):
    """H1: 슬라이스로 실제 행이 줄면 warnings에 '구조인식으로 N행 제외'가 표면화돼야 한다."""
    def responder(_human: str) -> str:
        return json.dumps({
            "columns": {"address": "A열", "jibun": "B열", "pnu": "C열"},
            "data_start_row": 1, "data_end_row": 2,  # 3번째 데이터 행(인덱스3)은 범위 밖 — 실제 제외.
        }, ensure_ascii=False)

    _patch_llm(monkeypatch, responder)
    raw = _xlsx([
        ["A열", "B열", "C열"],
        ["서울특별시 동작구 상도동", "210-453", "1159010300102100453"],
        ["경기도 의정부시 의정부동 224", "224-1", "4115010100201100224"],
        ["부산광역시 해운대구 우동", "500", "2635010100105000000"],
    ])
    out = asyncio.run(pes.ParcelExcelService().parse(raw, "슬라이스경고.xlsx", use_llm=True))
    assert not out.get("error")
    assert len(out["parcels"]) == 2
    warnings = out["verification_report"]["warnings"]
    assert any("구조인식으로" in w and "제외" in w for w in warnings), "무음 절단 금지 — 제외 사유가 표면화돼야 함"


# ── H2: LLM 컬럼매핑 경로에서도 병합셀 forward-fill이 유지돼야 함(main 회귀) ─
def test_llm_column_mapping_preserves_merged_cell_expansion(monkeypatch):
    """H2 재현: struct가 truthy(컬럼역할만 응답)면 시트/전치 불변이어도 무조건 rebuild해
    병합셀 forward-fill이 적용된 df를 버리고 원본(미병합) df0에서 다시 만들었다 — 공유지분
    병합이 1필지로 소실(main은 2필지). 시트/전치 변경이 없으면 rebuild를 생략해야 한다.

    ★pd.read_excel(header=None)은 전 셀이 빈 '완전 공백 행'은 통째로 드롭한다(병합 자식
    셀은 None) — 그래서 기존 test_merged_cells_forward_fill처럼 병합 안 되는 컬럼(소유구분)에
    행마다 다른 값을 둬서 pandas가 그 행을 드롭하지 못하게 한다.
    """
    def responder(_human: str) -> str:
        return json.dumps({"columns": {"address": "A열", "jibun": "B열", "pnu": "C열"}},
                           ensure_ascii=False)

    _patch_llm(monkeypatch, responder)
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "토지조서"
    ws.append(["A열", "B열", "C열", "소유구분"])
    ws.append(["서울특별시 동작구 상도동", "210-453", "1159010300102100453", "김철수"])
    ws.append(["", "", "", "이영희"])
    ws.merge_cells("A2:A3")
    ws.merge_cells("B2:B3")
    ws.merge_cells("C2:C3")
    buf = io.BytesIO()
    wb.save(buf)
    raw = buf.getvalue()

    out = asyncio.run(pes.ParcelExcelService().parse(raw, "비표준병합.xlsx", use_llm=True))
    assert not out.get("error")
    assert out["column_engine"] == "rule+llm"
    assert len(out["parcels"]) == 2, "LLM 컬럼매핑 경유에도(시트/전치 불변) 병합 복원 2행이 유지돼야 함"
    assert all(p["jibun"] == "210-453" for p in out["parcels"])
