"""법규 검토서 어댑터(build_report_model_from_regulation) + 라우트(/regulation/report) 단위테스트.

생성허브 100% 구현 A — 법규 검토서 산출물 고정(dead-path 방지: 어댑터 조립 + 실렌더 + 라우트 계약).

검증 축(어댑터 단위 — RegulationAnalysisService 실호출은 목킹하지 않고 결과 dict 픽스처 주입):
  (a) 섹션 구성(부지 요약·정량 한도·AI·계층·지구·근거)·KV/표 행 정확
  (b) 결측 정직 표기('—') — 조례/실효 미확보 값은 fmt_value(None) 로 통일
  (c) 조례 강화(법정>조례) 건수 정직 기술(강화 없으면 문구 미노출) + 검토 배지 사실성
  (d) evidence 브리지 — evidence 트레이스 + 계층 legal_refs(verified URL) 근거 블록 부착
  (e) 라우트 /regulation/report — body result 그대로 조립(재분석 0) + 실렌더(PDF) 통과·계약(4xx)
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.report.render import (  # noqa: E402
    build_report_model_from_regulation,
)
from app.services.report.render.model import (  # noqa: E402
    DataTableBlock,
    EvidenceBlock,
    KVTableBlock,
    NarrativeBlock,
    fmt_value,
)

_EMPTY = fmt_value(None)  # '—' 통일 표기(토큰 상수 비의존)


def _run(coro):
    """이벤트 루프 안전 실행(러닝 루프 부재 환경에서도 동작) — 기존 route 테스트 관례 재사용."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _result_full() -> dict[str, Any]:
    """RegulationAnalysisService.analyze 산출 dict 의 어댑터가 읽는 키를 채운 정상 픽스처.

    건폐율(60→50)·용적률(250→200) 둘 다 조례 강화(ordinance<legal) — tightened 2건.
    """
    return {
        "address": "서울시 강남구 역삼동 1-1",
        "pnu": "1168010100101010001",
        "zone_type": "제3종일반주거지역",
        "zone_type_secondary": None,
        "land_area_sqm": 1234.5,
        "land_category": "대",
        "land_use_situation": "상업용",
        "limits": {
            "bcr": {"legal": 60, "ordinance": 50, "effective": 50, "unit": "%"},
            "far": {"legal": 250, "ordinance": 200, "effective": 200, "unit": "%"},
            "height": {"value": 20, "unit": "m", "max_floors": None, "basis": "건축법 제60조"},
            "parking": {"description": "주차장법 시행령 별표1 부설주차장 설치기준 적용"},
        },
        "hierarchy": [
            {
                "level": "상위법령",
                "items": [
                    {"name": "국토의 계획 및 이용에 관한 법률", "ref": "제76·77·78조",
                     "desc": "용도지역 행위제한·건폐율·용적률 상한"},
                    {"name": "건축법", "ref": "제55·56조", "desc": "건폐율·용적률 제한"},
                ],
                "legal_refs": [
                    {"key": "far_limit", "law_name": "국토계획법", "article": "제78조",
                     "title": "용적률", "url": "https://law.go.kr/x", "url_status": "verified"},
                ],
            },
            {
                "level": "지자체 조례",
                "items": [
                    {"name": "강남구 도시계획 조례", "ref": "-", "desc": "건폐율 50% · 용적률 200%"},
                ],
                "legal_refs": [],
            },
        ],
        "districts": [
            {"name": "지구단위계획구역", "code": "D-1", "impact": "상", "status": "결정"},
        ],
        "evidence": [
            {"label": "용적률 상한", "value": "200%", "basis": "조례 강화 적용",
             "legal_ref_key": "far_limit"},
        ],
        "ai": {
            "generated": True,
            "summary": "제3종일반주거지역으로 용적률 200%(조례 강화)가 적용됩니다.",
            "dev_impact": "밀도 계획 시 조례 한도를 기준으로 검토 필요.",
            "key_constraints": ["용적률 조례 강화", "높이 20m"],
            "strategies": ["인센티브 검토"],
            "opportunities": [],
            "risks": ["일조권 사선"],
        },
    }


def _sections_by_title(model) -> dict[str, Any]:
    return {s.title: s for s in model.sections}


def test_adapter_sections_and_summary_rows():
    """(a) 정상 픽스처 — 핵심 섹션 존재 + 부지 요약 KV 행·정량 한도 표 정확."""
    model = build_report_model_from_regulation(_result_full(), address="서울시 강남구 역삼동 1-1")
    titles = [s.title for s in model.sections]

    assert model.meta.title == "법규 검토서"
    assert model.meta.project_address == "서울시 강남구 역삼동 1-1"
    # 필수 섹션(부지 요약·정량 한도·AI·계층·지구·근거) 존재
    assert any("부지·용도지역 요약" in t for t in titles), titles
    assert any("정량 규제 한도" in t for t in titles), titles
    assert any("AI 통합 규제 해석" in t for t in titles), titles
    assert any("적용 규제 계층" in t for t in titles), titles
    assert any("적용 규제·지구·구역" in t for t in titles), titles
    assert any("근거 법령" in t for t in titles), titles

    secs = _sections_by_title(model)
    # 부지 요약 KV 행
    kv = next(b for b in secs["1. 부지·용도지역 요약"].blocks if isinstance(b, KVTableBlock))
    kvd = dict(kv.rows)
    assert kvd["용도지역"] == "제3종일반주거지역"
    assert kvd["대지면적"] == "1,234.5㎡"
    assert kvd["지목"] == "대"

    # 정량 한도 표 — 건폐/용적 행 (법정/조례/실효)
    table = next(b for b in secs["2. 정량 규제 한도"].blocks if isinstance(b, DataTableBlock))
    by_kind = {row[0]: row for row in table.rows}
    assert by_kind["건폐율"] == ["건폐율", "60%", "50%", "50%"]
    assert by_kind["용적률"] == ["용적률", "250%", "200%", "200%"]


def test_adapter_tightened_note_present():
    """(c) 조례 강화 2건 — 정량 한도 섹션에 강화 고지 Narrative 존재."""
    model = build_report_model_from_regulation(_result_full())
    secs = _sections_by_title(model)
    narrs = [b for b in secs["2. 정량 규제 한도"].blocks if isinstance(b, NarrativeBlock)]
    joined = " ".join(p for b in narrs for p in b.paragraphs)
    assert "조례로 강화" in joined and "2건" in joined, joined
    # 보완·유의사항 섹션에도 조례 강화 환기(사실 기반)
    assert "7. 보완·유의사항" in secs


def test_adapter_evidence_block_with_verified_link():
    """(d) evidence 트레이스 + 계층 legal_refs(verified) → 근거 블록 부착·verified URL 통과."""
    model = build_report_model_from_regulation(_result_full())
    secs = _sections_by_title(model)
    ev_sec = next(s for t, s in secs.items() if "근거 법령" in t)
    ev_block = next(b for b in ev_sec.blocks if isinstance(b, EvidenceBlock))
    # evidence 트레이스(라벨: 값) 존재 + verified URL 주입
    joined_vals = " ".join(it.value for it in ev_block.items)
    assert "용적률 상한: 200%" in joined_vals
    assert any(it.legal_link == "https://law.go.kr/x" for it in ev_block.items)


def test_adapter_missing_values_honest_dash_and_omitted_sections():
    """(b) 결측 정직 — 조례/실효 미확보 '—', AI/지구/근거 부재 시 섹션 자체 생략(가짜 0)."""
    minimal = {
        "address": "미상 주소",
        "zone_type": None,
        "land_area_sqm": None,
        "limits": {
            "bcr": {"legal": None, "ordinance": None, "effective": None, "unit": "%"},
            "far": {"legal": None, "ordinance": None, "effective": None, "unit": "%"},
            "height": {"value": None, "unit": "m", "max_floors": None, "basis": None},
            "parking": {"description": "부설주차장 기준 적용"},
        },
        "hierarchy": [],
        "districts": [],
        "evidence": [],
        "ai": None,
    }
    model = build_report_model_from_regulation(minimal)
    titles = [s.title for s in model.sections]
    secs = _sections_by_title(model)

    # 정량 한도 표 — 미확보 값은 '—'
    table = next(b for b in secs["2. 정량 규제 한도"].blocks if isinstance(b, DataTableBlock))
    by_kind = {row[0]: row for row in table.rows}
    assert by_kind["건폐율"] == ["건폐율", _EMPTY, _EMPTY, _EMPTY]

    # 조례 강화 없음 → 강화 고지 Narrative 미노출 + 보완·유의사항 섹션 생략
    narrs = [b for b in secs["2. 정량 규제 한도"].blocks if isinstance(b, NarrativeBlock)]
    joined = " ".join(p for b in narrs for p in b.paragraphs)
    assert "조례로 강화" not in joined
    assert "7. 보완·유의사항" not in secs

    # AI/지구/근거 없음 → 해당 섹션 자체 생략(정직)
    assert not any("AI 통합" in t for t in titles), titles
    assert not any("적용 규제·지구·구역" in t for t in titles), titles
    assert not any("근거 법령" in t for t in titles), titles


def test_route_report_renders_pdf_from_body_result():
    """(e) 라우트 /regulation/report — body.result 그대로 조립(재분석 0) + 실렌더(PDF) 통과."""
    import apps.api.routers.regulation as regulation_router

    pytest.importorskip("reportlab")
    body = regulation_router.RegulationReportRequest(
        result=_result_full(), address="서울시 강남구 역삼동 1-1")
    resp = _run(regulation_router.regulation_report(body, format="pdf"))
    assert getattr(resp, "status_code", 200) == 200
    assert resp.media_type == "application/pdf"
    assert bytes(resp.body)[:4] == b"%PDF"


def test_route_report_rejects_empty_and_bad_format():
    """(e) 라우트 계약 — 빈 결과·미지원 포맷은 4xx(200+error JSON 금지)."""
    from fastapi import HTTPException

    import apps.api.routers.regulation as regulation_router

    with pytest.raises(HTTPException) as e1:
        _run(regulation_router.regulation_report(
            regulation_router.RegulationReportRequest(result={}), format="pdf"))
    assert e1.value.status_code == 400

    with pytest.raises(HTTPException) as e2:
        _run(regulation_router.regulation_report(
            regulation_router.RegulationReportRequest(result=_result_full()), format="xlsx"))
    assert e2.value.status_code == 400
