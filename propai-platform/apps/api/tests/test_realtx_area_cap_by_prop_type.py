"""실거래 검증기의 면적 상한이 **유형별**인지 잠근다 — 아파트 기준이 토지를 죽이고 있었다.

★라이브 실측(2026-08-26 · MOLIT 토지 원본 `LAWD_CD=41370`·`DEAL_YMD=202607` **114행**):
    면적 > 1000㎡ = **68/114 = 60%** (범위 1,031~10,763㎡ · 중앙 1,795㎡)
  종전 `TransactionRecord.validate_area` 는 유형과 무관하게 `v > 1000` 을 이상치로 드롭했다.
  즉 **정상 토지거래의 60%가 조용히 사라졌다** — 파서 로그에만 남고 소비처는 알 수 없다.

★왜 아파트는 1000㎡ 가 옳은가: 집합주택 값은 **전용면적**이라 1000㎡ 를 넘을 수 없다.
  토지는 **필지 면적**이라 수만 ㎡ 가 정상이다(같은 날 실측한 프로젝트 필지 147,074㎡).

★파장: 이 게이트는 `MolitClient._parse_trade_items` 의 **단일 통로**라, 토지를 쓰는 모든 소비처
  (AVM 학습·시장보고서·탁상감정 비교표본·주변지도)가 같은 손실을 공유했다.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from app.services.data_validation.validator import (
    _ABSOLUTE_MAX_AREA_SQM,
    max_area_sqm_for,
    validate_transactions,
)


def _row(area: float, price: int = 1041) -> dict:
    return {"deal_date": "2026년 7월 1일", "price_10k_won": price, "area_m2": area, "floor": 0}


class Test유형별면적상한:
    def test_집합주택은_1000_상한을_유지한다(self) -> None:
        """★회귀 — 아파트 동작은 바뀌지 않아야 한다(이 PR 이 넓힌 것은 토지뿐)."""
        for pt in ("apt", "villa", "officetel"):
            assert max_area_sqm_for(pt) == 1000.0
            acc, rep = validate_transactions([_row(1795.0)], prop_type=pt)
            assert not acc and rep["dropped"] == 1, f"{pt}: 전용면적 1795㎡ 는 드롭돼야 한다"

    def test_토지는_1000을_넘어도_채택된다(self) -> None:
        """★탐지 — 이 PR 이 고친 결함 그 자체."""
        acc, rep = validate_transactions([_row(1795.0)], prop_type="land")
        assert len(acc) == 1 and rep["dropped"] == 0

    def test_라이브_분포를_그대로_태운다(self) -> None:
        """★실측 형상 — 1,031~10,763㎡ 가 토지에서 전부 살아야 한다.

        이 값들은 지어낸 것이 아니라 **2026-08-26 원본 114행의 실제 범위**다.
        """
        areas = [1031.0, 1795.0, 4200.0, 10763.0]
        acc, rep = validate_transactions([_row(a) for a in areas], prop_type="land")
        assert len(acc) == len(areas), f"토지에서 드롭됐다: {rep.get('dropped_detail')}"
        # 대조군 — 같은 행이 아파트에서는 **전부** 드롭돼야 한다(상한이 실제로 작동함을 증명)
        acc_apt, _ = validate_transactions([_row(a) for a in areas], prop_type="apt")
        assert not acc_apt, "아파트 상한이 무력화됐다 — 이 테스트가 공허해진다"

    def test_모르는_유형은_좁은_쪽으로_접는다(self) -> None:
        """fail-safe 방향 — 오타 하나가 검증을 통째로 열면 안 된다."""
        assert max_area_sqm_for("zzz") == 1000.0
        assert max_area_sqm_for("") == 1000.0
        assert max_area_sqm_for(None) == 1000.0  # type: ignore[arg-type]

    def test_절대상한은_어떤_유형에도_적용된다(self) -> None:
        """유형이 넓어도 원본 오류(5㎢ 초과)는 막는다."""
        acc, rep = validate_transactions([_row(_ABSOLUTE_MAX_AREA_SQM + 1)], prop_type="land")
        assert not acc and rep["dropped"] == 1

    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_비양수_면적은_유형과_무관하게_드롭(self, bad: float) -> None:
        acc, _ = validate_transactions([_row(bad)], prop_type="land")
        assert not acc


class Test배선:
    def test_파서가_prop_type을_실제로_넘긴다(self) -> None:
        """★배선 — **`_parse_trade_items` 안에서** 넘기는지 본다(모듈 전체가 아니라).

        ★오늘(2026-08-26) 같은 형태의 락이 **모듈 전체 스코프**라 뚫린 전례가 있다:
          조립을 결함 상태로 되돌리고 호출을 **다른 함수에 심으면** 통과했다.
          그래서 여기서는 **대상 함수 노드 안에서만** 찾는다.

        ★대조군도 **문법 구조**에 결속한다 — 함수가 사라지면 `StopIteration` 으로 시끄럽게 죽는다
          (문자열 `in src` 대조군은 내가 쓴 독스트링에 걸려 공허해진 전례가 있다).
        """
        from integrations import molit_client

        tree = ast.parse(inspect.getsource(molit_client))
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_parse_trade_items"
        )  # ← 살아 있는 대조군
        ok = False
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "validate_transactions":
                if any(kw.arg == "prop_type" for kw in node.keywords):
                    ok = True
        assert ok, (
            "_parse_trade_items 가 validate_transactions 에 prop_type 을 넘기지 않는다 — "
            "유형별 상한이 배선되지 않아 토지가 아파트 기준으로 다시 드롭된다"
        )
