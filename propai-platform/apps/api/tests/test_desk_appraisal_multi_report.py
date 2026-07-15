"""다필지 탁상감정 통합 보고서 어댑터(build_report_model_from_appraisal_multi) 단위테스트.

후속 캠페인 WS② — DeskAppraisal 산출물 다필지(A안 additive) 고정.

검증 축(어댑터 단위만 — desk_appraisal 실호출은 목킹하지 않고 결과 dict 픽스처 주입):
  (a) 필지별 행 수·통합 합계(면적 합·추정총액 합·평균단가=합계/면적합) 정확
  (b) 실패 필지는 상태 '보완필요'·값 '—'(fmt_value(None)) 표기
  (c) 대표(첫 성공) 필지 단건 상세 섹션 보존 + 실렌더(PDF) 통과(dead-path 방지)
  (d) 30필지 상한 초과분(omitted_count) caption 정직 고지
"""
from __future__ import annotations

import pytest

from typing import Any

from app.services.report.render import (
    build_report_model_from_appraisal_multi,
    render_report,
)
from app.services.report.render.model import (
    DataTableBlock,
    KVTableBlock,
    fmt_value,
)

_EMPTY = fmt_value(None)  # '—' 통일 표기(토큰 상수에 비의존)


def _ok(unit: int, total: int, area: float, methods: tuple[str, ...] = ("공시지가 기준 추정",)) -> dict[str, Any]:
    """성공 필지 픽스처 — desk_appraisal 산출 dict 의 단건 어댑터가 읽는 키만 채운다."""
    return {
        "ok": True,
        "appraised_price_per_sqm": unit,
        "appraised_total_won": total,
        "area_sqm": area,
        "confidence": 0.8,
        "range_per_sqm": {"low": unit - 100_000, "high": unit + 100_000},
        "methods": [{"method": mm, "unit_price": unit, "rationale": "산식"} for mm in methods],
        "disclaimer": "참고용 추정(감정평가 아님)",
    }


def _fail(msg: str = "공시지가 미확인") -> dict[str, Any]:
    return {"ok": False, "message": msg}


def _overview_blocks(model):
    """맨 앞 '0. 다필지 추정 총괄' 섹션의 (DataTableBlock, KVTableBlock) 반환."""
    sec = model.sections[0]
    assert sec.title == "0. 다필지 추정 총괄", model.sections[0].title
    table = next(b for b in sec.blocks if isinstance(b, DataTableBlock))
    kv = next(b for b in sec.blocks if isinstance(b, KVTableBlock))
    return table, kv


def test_multi_row_count_and_totals_exact():
    """(a) 3필지 전부 성공 — 행 3개 + 통합 합계(면적/총액/평균단가) 정확."""
    results = [
        _ok(1_000_000, 500_000_000, 500),
        _ok(2_000_000, 1_000_000_000, 500),
        _ok(1_500_000, 600_000_000, 400),
    ]
    addresses = ["A-1", "A-2", "A-3"]
    model = build_report_model_from_appraisal_multi(results, addresses=addresses)

    table, kv = _overview_blocks(model)
    # 필지별 행 = 3(합계 행은 별도 KVTable 로 분리)
    assert len(table.rows) == 3
    # 소재지·상태 열 확인
    assert [row[1] for row in table.rows] == ["A-1", "A-2", "A-3"]
    assert all(row[-1] == "확정" for row in table.rows)

    kvd = dict(kv.rows)
    assert kvd["성공 필지 수"] == "3 / 3필지"
    # 면적 합 = 1400.0㎡
    assert kvd["합산 대지면적"] == "1,400.0㎡"
    # 총액 합 = 2,100,000,000원
    assert kvd["합산 추정 총액"] == "2,100,000,000원"
    # 통합 평균단가 = 2,100,000,000 / 1400 = 1,500,000원/㎡
    assert kvd["통합 평균단가(/㎡)"] == "1,500,000원/㎡"


def test_multi_failed_parcel_marked_needs_fix():
    """(b) 실패 필지는 상태 '보완필요'·값 셀 '—'(성공 필지만 합산에 반영)."""
    results = [
        _ok(1_000_000, 500_000_000, 500),
        _fail(),
        _ok(2_000_000, 1_000_000_000, 500),
    ]
    addresses = ["OK-1", "FAIL-2", "OK-3"]
    model = build_report_model_from_appraisal_multi(results, addresses=addresses)

    table, kv = _overview_blocks(model)
    assert len(table.rows) == 3
    fail_row = table.rows[1]
    assert fail_row[1] == "FAIL-2"
    assert fail_row[-1] == "보완필요"
    # 면적·채택단가·총액·산정방법 셀 전부 '—'(미확보 정직 표기)
    assert fail_row[2] == _EMPTY  # 면적
    assert fail_row[3] == _EMPTY  # 채택 추정단가
    assert fail_row[4] == _EMPTY  # 추정 총액
    assert fail_row[5] == _EMPTY  # 산정방법

    kvd = dict(kv.rows)
    assert kvd["성공 필지 수"] == "2 / 3필지"
    # 합계는 성공 2필지만 — 면적 1000.0㎡, 총액 1,500,000,000원
    assert kvd["합산 대지면적"] == "1,000.0㎡"
    assert kvd["합산 추정 총액"] == "1,500,000,000원"
    # caption 정직 고지
    assert "성공 2/3필지" in table.caption


def test_multi_preserves_representative_detail_and_renders():
    """(c) 대표(첫 성공) 필지 단건 상세 섹션 보존 + 실제 PDF 렌더 통과(dead-path 방지)."""
    results = [_fail(), _ok(1_200_000, 600_000_000, 500), _ok(900_000, 450_000_000, 500)]
    addresses = ["FAIL", "REP", "P3"]
    model = build_report_model_from_appraisal_multi(results, addresses=addresses)

    # 0번 총괄 뒤에 단건 어댑터의 상세 섹션(예: '1. 추정 요약 (결론)')이 그대로 존재
    titles = [s.title for s in model.sections]
    assert titles[0] == "0. 다필지 추정 총괄"
    assert any("추정 요약" in t for t in titles[1:]), titles
    # 대표는 첫 성공(REP) — 표지 메타는 다필지로 보강
    assert "다필지" in model.meta.title
    assert "3필지 통합" in (model.meta.subtitle or "")

    # 모델→PDF 실렌더까지 통과(모델에만 있고 렌더에서 깨지면 무의미)
    # 라이브러리 미설치 환경(로컬 venv 등)은 skip — CI 는 reportlab 설치돼 실렌더 검증
    # (기존 test_report_render_engine.py:206 관례 미러).
    pytest.importorskip("reportlab")
    data, _mime, ext = render_report(model, "pdf")
    assert ext == "pdf" and data[:4] == b"%PDF"


def test_multi_truncation_disclosed_in_caption():
    """(d) 30필지 상한 초과분(omitted_count)이 caption 에 정직 고지."""
    results = [_ok(1_000_000, 500_000_000, 500) for _ in range(30)]
    addresses = [f"P-{i}" for i in range(30)]

    model = build_report_model_from_appraisal_multi(
        results, addresses=addresses, omitted_count=2)
    table, _kv = _overview_blocks(model)
    assert len(table.rows) == 30
    assert "미포함" in table.caption
    assert "2필지" in table.caption

    # 절단 없으면(omitted_count=0) '미포함' 문구 미노출(조건부 고지)
    model0 = build_report_model_from_appraisal_multi(
        results, addresses=addresses, omitted_count=0)
    table0, _ = _overview_blocks(model0)
    assert "미포함" not in table0.caption
