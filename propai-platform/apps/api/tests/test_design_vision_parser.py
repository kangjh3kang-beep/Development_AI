"""비전 LLM 도면 파서(vision_parser) 단위테스트.

원칙: best-effort·정직. 키 없음/LLM실패/JSON불량 → 숫자 날조 없는 정직 스텁.
비상식 값(음수·과대)은 거부(할루시네이션 가드). LLM 호출은 get_llm 모킹으로 결정적 검증.
"""

import json

import pytest

from app.services.design_ingest import vision_parser as vp
from app.services.design_ingest.parsers import parse_design_file_async


class _FakeResp:
    def __init__(self, content):
        self.content = content


def _fake_llm_returning(content):
    """ainvoke가 주어진 content를 담은 응답을 반환하는 가짜 LLM 팩토리."""
    class _LLM:
        async def ainvoke(self, _messages):
            return _FakeResp(content)

    def _factory(*_a, **_k):
        return _LLM()

    return _factory


def _patch_llm(monkeypatch, factory):
    monkeypatch.setattr("app.services.ai.llm_provider.get_llm", factory)


# ── 미디어 타입 판별 ──
def test_media_type_for():
    assert vp.media_type_for("a.PNG") == "image/png"
    assert vp.media_type_for("b.jpg") == "image/jpeg"
    assert vp.media_type_for("c.jpeg") == "image/jpeg"
    assert vp.media_type_for("d.webp") == "image/webp"
    assert vp.media_type_for("e.gif") is None


# ── 정상 추출 ──
async def test_vision_extracts_fields(monkeypatch):
    payload = {
        "drawing_type": "floor_plan",
        "total_area_sqm": 1850.5,
        "floor_count": 5,
        "unit_count": 24,
        "parking_count": 30,
        "rooms": ["거실", "주방", "침실1"],
        "confidence": 0.82,
        "summary": "5층 공동주택 평면도",
    }
    _patch_llm(monkeypatch, _fake_llm_returning(json.dumps(payload, ensure_ascii=False)))
    spec = await vp.parse_drawing_with_vision(b"\x89PNG...", "평면도.png", "image")

    assert spec.source_format == "image"
    assert spec.drawing_type == "floor_plan"
    assert spec.total_area_sqm == 1850.5
    assert spec.floor_count == 5 and spec.unit_count == 24 and spec.parking_count == 30
    assert [r.name for r in spec.rooms] == ["거실", "주방", "침실1"]
    assert spec.meta["vision"] == "ok"
    assert spec.meta["vision_confidence"] == 0.82
    assert "5층" in spec.raw_summary


# ── JSON이 코드펜스로 감싸져 와도 파싱 ──
async def test_vision_handles_code_fenced_json(monkeypatch):
    body = "여기 결과입니다:\n```json\n{\"drawing_type\": \"site_plan\", \"floor_count\": 3}\n```\n끝"
    _patch_llm(monkeypatch, _fake_llm_returning(body))
    spec = await vp.parse_drawing_with_vision(b"x", "배치.png", "image")
    assert spec.drawing_type == "site_plan" and spec.floor_count == 3


# ── 응답 content가 블록 리스트(멀티모달) 형태여도 텍스트 추출 ──
async def test_vision_handles_block_list_content(monkeypatch):
    blocks = [{"type": "text", "text": json.dumps({"drawing_type": "section", "unit_count": 10})}]
    _patch_llm(monkeypatch, _fake_llm_returning(blocks))
    spec = await vp.parse_drawing_with_vision(b"x", "단면.png", "image")
    assert spec.drawing_type == "section" and spec.unit_count == 10


# ── 키 미설정(get_llm가 ValueError) → 정직 스텁, 숫자 날조 없음 ──
async def test_vision_no_key_is_honest_stub(monkeypatch):
    def _raise(*_a, **_k):
        raise ValueError("anthropic API key not configured")

    _patch_llm(monkeypatch, _raise)
    spec = await vp.parse_drawing_with_vision(b"x", "평면도.png", "image")
    assert spec.meta["vision"] == "failed"
    assert spec.meta.get("warnings")
    # 어떤 정량값도 지어내지 않음
    assert spec.total_area_sqm is None and spec.floor_count is None
    assert spec.unit_count is None and spec.parking_count is None
    # 파일명 휴리스틱으로 도면종류는 채움(정직 범위)
    assert spec.drawing_type == "floor_plan"


# ── LLM이 JSON 아닌 잡텍스트 → 정직 스텁 ──
async def test_vision_malformed_json_is_honest_stub(monkeypatch):
    _patch_llm(monkeypatch, _fake_llm_returning("도면을 분석할 수 없습니다."))
    spec = await vp.parse_drawing_with_vision(b"x", "img.png", "image")
    assert spec.meta["vision"] == "failed"
    assert spec.total_area_sqm is None


# ── 비상식 값 거부(할루시네이션 가드): 음수 면적·과대 층수는 None, 정상 세대수는 유지 ──
async def test_vision_rejects_implausible_numbers(monkeypatch):
    payload = {
        "drawing_type": "floor_plan",
        "total_area_sqm": -100,        # 음수 → 거부
        "floor_count": 9999,           # 과대(>200) → 거부
        "unit_count": 12,              # 정상 → 유지
        "parking_count": 0,            # 0 → 거부(>0 조건)
    }
    _patch_llm(monkeypatch, _fake_llm_returning(json.dumps(payload)))
    spec = await vp.parse_drawing_with_vision(b"x", "p.png", "image")
    assert spec.total_area_sqm is None
    assert spec.floor_count is None
    assert spec.unit_count == 12
    assert spec.parking_count is None


# ── NaN/Infinity 거부(할루시네이션 가드 + never-raises 불변식): 예외 없이 None ──
async def test_vision_rejects_nan_and_infinity(monkeypatch):
    # json은 기본적으로 NaN/Infinity 리터럴을 허용 → 가드 우회·int(nan) 예외 위험.
    body = ('{"drawing_type":"floor_plan","total_area_sqm": NaN, '
            '"floor_count": Infinity, "parking_count": -Infinity, "unit_count": 7}')
    _patch_llm(monkeypatch, _fake_llm_returning(body))
    spec = await vp.parse_drawing_with_vision(b"x", "p.png", "image")  # 예외 없이 반환되어야 함
    assert spec.total_area_sqm is None
    assert spec.floor_count is None and spec.parking_count is None
    assert spec.unit_count == 7  # 정상값은 유지


# ── 입력 크기 초과 → LLM 호출 없이 unavailable(선제 방어) ──
async def test_vision_oversized_input_unavailable(monkeypatch):
    called = {"n": 0}

    def _factory(*_a, **_k):
        called["n"] += 1
        raise AssertionError("LLM should not be called on oversized input")

    _patch_llm(monkeypatch, _factory)
    big = b"x" * (20 * 1024 * 1024 + 1)
    spec = await vp.parse_drawing_with_vision(big, "huge.png", "image")
    assert spec.meta["vision"] == "unavailable" and called["n"] == 0


# ── _pos_number 직접 단위검증(NaN/inf/bool/경계) ──
def test_pos_number_guards():
    assert vp._pos_number(float("nan"), 100.0) is None
    assert vp._pos_number(float("inf"), 100.0) is None
    assert vp._pos_number(True, 100.0) is None   # bool 거부
    assert vp._pos_number(0, 100.0) is None
    assert vp._pos_number(-1, 100.0) is None
    assert vp._pos_number(101, 100.0) is None    # 상한 초과
    assert vp._pos_number(50, 100.0) == 50.0


# ── 허용되지 않은 도면종류 → 파일명 휴리스틱으로 폴백 ──
async def test_vision_invalid_drawing_type_falls_back(monkeypatch):
    _patch_llm(monkeypatch, _fake_llm_returning(json.dumps({"drawing_type": "garbage"})))
    spec = await vp.parse_drawing_with_vision(b"x", "주차도.png", "image")
    assert spec.drawing_type == "parking"  # 파일명('주차') 휴리스틱


# ── 지원하지 않는 이미지 확장자 → LLM 호출 없이 unavailable ──
async def test_vision_unsupported_image_ext(monkeypatch):
    called = {"n": 0}

    def _factory(*_a, **_k):
        called["n"] += 1
        raise AssertionError("LLM should not be called")

    _patch_llm(monkeypatch, _factory)
    spec = await vp.parse_drawing_with_vision(b"x", "a.gif", "image")
    assert spec.meta["vision"] == "unavailable" and called["n"] == 0


# ── PDF 경로: document 블록 구성(성공 모킹) ──
async def test_vision_pdf_path(monkeypatch):
    _patch_llm(monkeypatch, _fake_llm_returning(json.dumps({"drawing_type": "section"})))
    spec = await vp.parse_drawing_with_vision(b"%PDF-1.4", "도면.pdf", "pdf")
    assert spec.source_format == "pdf" and spec.drawing_type == "section"


# ── 비동기 진입점 라우팅: 이미지→비전, 엑셀→동기 파서 ──
async def test_async_entry_routes_image_to_vision(monkeypatch):
    _patch_llm(monkeypatch, _fake_llm_returning(json.dumps({"drawing_type": "elevation"})))
    spec = await parse_design_file_async(b"x", "입면도.png")
    assert spec.source_format == "image" and spec.drawing_type == "elevation"


async def test_async_entry_excel_uses_sync_parser():
    # 엑셀은 비전 경로를 타지 않음(LLM 모킹 없이도 동작) — source_format=excel
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    wb.active["A1"] = "연면적 1234"
    buf = io.BytesIO()
    wb.save(buf)
    spec = await parse_design_file_async(buf.getvalue(), "스펙.xlsx")
    assert spec.source_format == "excel" and spec.total_area_sqm == 1234.0


# ── 응답 텍스트 추출 유틸 ──
def test_message_text_variants():
    assert vp._message_text(_FakeResp("hello")) == "hello"
    assert vp._message_text(_FakeResp([{"type": "text", "text": "a"}, {"type": "image"}])) == "a"
    assert vp._message_text("plain") == "plain"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
