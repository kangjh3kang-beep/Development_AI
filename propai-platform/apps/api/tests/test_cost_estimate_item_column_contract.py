"""저장된 적산에서 **그 값이 무엇인지가 사라졌다** — 열 계약을 SQL 에서 파생해 잠근다.

## 무엇이 있었나(실측)

`boq_builder` 는 `market_unit_price` 와 함께 **`market_unit_price_source`**(= `"simulation"`,
KCCI 결정론 시뮬레이션 · 실시세 API 아님)를 정직하게 만들어 내보낸다.
그런데 `cost_estimate_repository` 는 **값만 저장하고 출처는 버렸다** — 테이블에 컬럼조차 없었다.

    INSERT … market_unit_price, actual_unit_price …      ← 출처 없음
    SELECT … market_unit_price, actual_unit_price …      ← 출처 없음

즉 저장된 적산을 복원하면 그 시장단가가 **시뮬레이션이라는 사실이 소실**된다.
*"값은 나가는데 그 값이 무엇인지가 안 나간다"* — 이 저장소의 반복 결함이다.

## 이 파일이 잠그는 것 — **목록이 아니라 파생**

열을 손으로 세면 그 목록이 곧 상한이 된다. 그래서 **SQL 문자열에서 열 순서를 파싱**해
코드의 `r[N]` 인덱스와 대조한다. 열을 하나 끼워 넣어 인덱스가 밀리면 **조용히** 값이
뒤바뀌는데(이번 변경이 정확히 그 위험이었다: `r[11]` → `r[12]`), 그것을 여기서 잡는다.
"""
from __future__ import annotations

import re
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[1]
_REPO_SRC = (_API_ROOT / "app/services/cost/cost_estimate_repository.py").read_text(encoding="utf-8")
_BOOT_SRC = (_API_ROOT / "app/services/cost/cost_tables_bootstrap.py").read_text(encoding="utf-8")


def _joined(fragment_start: str, fragment_end: str, src: str) -> str:
    """여러 줄로 쪼개진 SQL 문자열 조각을 이어 붙인다(따옴표·개행 제거)."""
    i = src.index(fragment_start)
    j = src.index(fragment_end, i)
    chunk = src[i : j + len(fragment_end)]
    # "…" 리터럴 안의 내용만 모아 붙인다.
    return " ".join(re.findall(r'"([^"]*)"', chunk))


def _select_columns() -> list[str]:
    sql = _joined('"SELECT code, name, work_type', 'ORDER BY sort_order"', _REPO_SRC)
    body = sql[sql.index("SELECT ") + 7 : sql.index(" FROM ")]
    return [c.strip() for c in body.split(",") if c.strip()]


def _insert_columns() -> list[str]:
    sql = _joined('"INSERT INTO cost_estimate_item"', ':so)")', _REPO_SRC)
    body = sql[sql.index("(") + 1 : sql.index(")")]
    return [c.strip() for c in body.split(",") if c.strip()]


def _insert_placeholders() -> list[str]:
    sql = _joined('"INSERT INTO cost_estimate_item"', ':so)")', _REPO_SRC)
    body = sql[sql.rindex("VALUES (") + 8 : sql.rindex(")")]
    return [c.strip() for c in body.split(",") if c.strip()]


# ── 파서 자신이 살아 있는가(공허한 초록 방지) ───────────────────────────────
def test_파서가_살아있다_열을_실제로_뽑는다():
    sel, ins, ph = _select_columns(), _insert_columns(), _insert_placeholders()
    assert len(sel) >= 12, f"SELECT 열을 못 뽑았다: {sel}"
    assert len(ins) >= 14, f"INSERT 열을 못 뽑았다: {ins}"
    assert len(ph) >= 14, f"플레이스홀더를 못 뽑았다: {ph}"
    assert "code" in sel and "estimate_id" in ins
    assert all(x.startswith(":") for x in ph), f"플레이스홀더 형태가 아니다: {ph}"


# ── 계약: 값과 기준이 **함께** 오간다 ───────────────────────────────────────
def test_시장단가와_그_출처가_함께_저장된다():
    ins = _insert_columns()
    assert "market_unit_price" in ins
    assert "market_unit_price_source" in ins, (
        "값만 저장하고 그 값이 무엇인지는 버린다 — 복원하면 시뮬레이션이라는 사실이 사라진다"
    )


def test_시장단가와_그_출처가_함께_복원된다():
    sel = _select_columns()
    assert "market_unit_price" in sel
    assert "market_unit_price_source" in sel


def test_읽기_인덱스가_SELECT_열_순서와_일치한다():
    """★열을 끼워 넣으면 `r[N]` 이 조용히 밀린다 — 목록이 아니라 **파생**으로 대조한다."""
    sel = _select_columns()
    for col, expr in (
        ("market_unit_price", "r[{}]"),
        ("market_unit_price_source", "r[{}]"),
        ("actual_unit_price", "r[{}]"),
    ):
        idx = sel.index(col)
        needle = f'"{col}": ' + expr.format(idx)
        assert needle in _REPO_SRC.replace("float(", "").replace(") if", " if"), (
            f"{col} 은 SELECT {idx}번째인데 코드가 그 인덱스를 읽지 않는다 — 값이 뒤바뀐다"
        )


def test_INSERT_열수와_플레이스홀더수가_같다():
    """열/플레이스홀더 드리프트는 **조용히** 값을 어긋나게 한다."""
    assert len(_insert_columns()) == len(_insert_placeholders())


def test_INSERT_플레이스홀더가_모두_파라미터로_공급된다():
    """`:mups` 를 SQL 에만 넣고 dict 에 안 넣으면 런타임에야 터진다."""
    for ph in _insert_placeholders():
        key = ph.lstrip(":")
        assert f'"{key}":' in _REPO_SRC, f"플레이스홀더 {ph} 에 대응하는 파라미터가 없다"


# ── 스키마: 기존 배포 테이블에도 멱등 보강되는가 ────────────────────────────
def test_출처_컬럼이_additive_DDL_로_보강되고_실행목록에_등록됐다():
    """★배선만 하고 `_ALL_DDL` 에 안 넣으면 컬럼이 안 생겨 INSERT 가 터진다."""
    assert "ADD COLUMN IF NOT EXISTS market_unit_price_source" in _BOOT_SRC
    assert "_DDL_COST_ESTIMATE_ITEM_MARKET_SRC" in _BOOT_SRC
    all_ddl = _BOOT_SRC[_BOOT_SRC.index("_ALL_DDL = (") :]
    assert "_DDL_COST_ESTIMATE_ITEM_MARKET_SRC" in all_ddl, (
        "DDL 을 정의만 하고 실행 목록에 등록하지 않았다 — 컬럼이 생기지 않는다"
    )


def test_기존_행을_깨지_않는다_nullable_추가():
    """[양성 대조군] NOT NULL 백필은 운영 리스크 — 선례(`_DDL_MATERIAL_SOURCE_URL`)와 같은 형태."""
    line = [ln for ln in _BOOT_SRC.splitlines() if "market_unit_price_source varchar" in ln][0]
    assert "NOT NULL" not in line
