"""학습 데이터셋이 **자기 모집단을 말하는가** — `LIMIT` 로 자른 반환수를 모집단으로 읽지 않게.

★왜(2026-09-13 실측): 같은 저장소에서 **두 세션이 각각** `GET /growth/insights?limit=500` 의
  `items`(500) 를 전수로 읽고 **분포·개수·「없다」를 전부 틀렸다**(전수는 `total=4133`).
  그 응답에는 `total` 이 **있었는데 안 읽었다.**
  `build_dataset_jsonl` 은 더 나빴다 — **`total` 자체가 없어서** 소비처가 읽을 수도 없었고,
  `learning_loop` 요약은 `count` 를 **「활성 페어 수」**라고 불렀다.

★형제 `/growth/learning/candidates` 는 `total` 을 **이미 준다**(라이브 실측) —
  **없던 것을 만드는 게 아니라 안 쓰던 것을 맞추는 것**이다.
"""
from __future__ import annotations

import sys

import pytest

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        sys.version_info < (3, 11),
        reason="app.crud.base 가 PEP 695 를 쓴다 — 개발 기본 python3(3.10)에서는 임포트 불가. "
               "★로컬에서 돌리려면 3.12 venv 를 쓴다: "
               "/home/kangjh3kang/.venvs/propai312/bin/python -m pytest <이 파일> (propai312 · GDAL 불필요).",
    ),
]


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _DB:
    """행 조회와 **모집단 계수**를 **따로** 라우팅하는 스텁.

    ★조회별 라우팅이 없으면 두 값이 **같은 모집단**이 되어 「차가 0인 픽스처」가 된다 —
      그러면 이 파일의 단언은 전부 공허하다.
    ★`count_fails=True` 면 계수만 실패시킨다(데이터셋은 살아야 한다).
    """

    def __init__(self, *, rows, total, count_fails: bool = False):
        self.rows = rows
        self.total = total
        self.count_fails = count_fails
        self.count_queries = 0
        self.row_queries = 0

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(getattr(statement, "text", statement))
        if "count(*)" in sql and "learning_examples" in sql:
            self.count_queries += 1
            if self.count_fails:
                raise RuntimeError("simulated count failure")
            return _Result(scalar=self.total)
        if "FROM learning_examples" in sql:
            self.row_queries += 1
            return _Result(rows=self.rows)
        return _Result()

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _rows(n: int):
    return [(f"in{i}", f"out{i}", None, None) for i in range(n)]


async def test_dataset_reports_its_population_when_truncated():
    """★모집단 > limit → `count < total` 이고 `truncated is True`."""
    from app.services.growth import learning_loop as ll

    db = _DB(rows=_rows(3), total=4133)          # 반환 3 · 모집단 4133
    ds = await ll.build_dataset_jsonl(db, limit=3)

    # ★공허 방지 — 스텁이 실제로 두 값을 **다르게** 냈는가(차가 0이면 아래가 공허하다)
    assert db.row_queries == 1 and db.count_queries == 1, (
        f"두 조회가 각각 한 번씩 돌아야 한다: rows={db.row_queries} count={db.count_queries}")
    assert ds["count"] != ds["total"], "픽스처가 두 모집단을 안 갈랐다 — 이 락은 공허하다"

    assert ds["count"] == 3
    assert ds["total"] == 4133
    assert ds["truncated"] is True


async def test_not_truncated_when_the_population_fits():
    """★반대 모집단 — 모집단 ≤ limit 면 `count == total` 이고 `truncated is False`.

    ★한쪽만 단언하면 반대쪽이 무제한이다(`truncated` 를 상수 True 로 바꿔도 위 락은 초록).
    """
    from app.services.growth import learning_loop as ll

    db = _DB(rows=_rows(2), total=2)
    ds = await ll.build_dataset_jsonl(db, limit=5000)

    assert ds["count"] == 2
    assert ds["total"] == 2
    assert ds["truncated"] is False


async def test_count_never_exceeds_total():
    """★**자기모순 검사** — 어떤 입력에서도 `count <= total`.

    이 부등식은 **대조군 없이도** 성립해야 한다. 깨지면 둘 중 하나가 다른 모집단을 센 것이다.
    """
    from app.services.growth import learning_loop as ll

    for n, total in ((0, 0), (1, 1), (3, 4133), (2, 2)):
        db = _DB(rows=_rows(n), total=total)
        ds = await ll.build_dataset_jsonl(db, limit=max(n, 1))
        assert ds["count"] <= ds["total"], f"count {ds['count']} > total {ds['total']} (n={n})"


async def test_unmeasured_total_is_none_not_zero():
    """★「못 쟀다」와 「0건」을 **구별**한다 — 계수가 실패해도 데이터셋은 살아야 한다.

    ★이 자리에서 실제로 데였다: 계수 쿼리를 행 조회와 **같은 try** 에 뒀더니, 계수가 실패하자
      **데이터셋 자체가 날아갔다**(기존 테스트 3건이 잡았다). ***보조 측정이 주 산출물을 죽이면 안 된다.***
    """
    from app.services.growth import learning_loop as ll

    db = _DB(rows=_rows(2), total=99, count_fails=True)
    ds = await ll.build_dataset_jsonl(db, limit=5000)

    assert ds["count"] == 2, "★모집단 계수가 실패했다고 데이터셋이 비면 안 된다"
    assert ds["total"] is None, "못 쟀으면 None 이어야 한다 — 0 으로 내리면 「0건」과 뭉개진다"
    assert ds["truncated"] is None, "모집단을 모르면 절단 여부도 모른다"


def _dataset_summary_keys() -> set[str]:
    """`run_learning_cycle` 이 `summary["dataset"]` 에 넣는 **딕셔너리 리터럴 키**를 AST 로 뽑는다.

    ★**문자열 포함 검사를 쓰지 않는 이유(실측 2026-09-13)**: 처음엔 `"active_pairs_total" in src`
      로 짰는데, 그 줄을 지우는 변이가 **SURVIVED** 했다 — **바로 위에 내가 쓴 주석**에 같은 낱말이
      있었기 때문이다. 저장소 지침이 *「소스 검사는 주석·문자열에 뚫린다」* 를 명문으로 적어 뒀고
      **내 락이 그것을 어겼다.** ⇒ ***AST 는 주석을 애초에 담지 않는다.***
    """
    import ast
    import inspect
    import textwrap

    from app.services.growth import learning_loop as ll

    tree = ast.parse(textwrap.dedent(inspect.getsource(ll.run_learning_cycle)))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if (isinstance(tgt, ast.Subscript)
                    and isinstance(tgt.slice, ast.Constant) and tgt.slice.value == "dataset"
                    and isinstance(node.value, ast.Dict)):
                keys |= {k.value for k in node.value.keys
                         if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return keys


async def test_summary_carries_the_total_not_just_the_count():
    """★**소비처까지** — 요약이 반환수만 싣고 모집단을 버리면 이 변경은 장식이다."""
    keys = _dataset_summary_keys()

    # ★대조군 먼저 — AST 가 실제로 그 대입을 찾았는가(못 찾으면 아래 셋이 공허하다)
    assert "active_pairs" in keys, (
        f"조회기 사망 — summary['dataset'] 의 키를 못 찾았다: {sorted(keys)}")
    # ★역대조군 — 없는 키가 잡히면 파서가 아무거나 집고 있다
    assert "zzz_nope_sentinel" not in keys

    assert "active_pairs_total" in keys, (
        f"요약이 **모집단**을 안 싣는다 — 소비처가 count 를 모집단으로 읽게 된다: {sorted(keys)}")
    assert "truncated" in keys, f"요약이 절단 여부를 안 싣는다: {sorted(keys)}"


def _audit_detail_keys() -> set[str]:
    """데이터셋 다운로드 라우트의 `audit_admin_action(detail={...})` **키**를 AST 로 뽑는다.

    ★기계 변이가 이 자리를 **생존**으로 짚었다(2026-09-13): 감사기록에 `total`·`truncated` 를
      실어 놓고 **아무도 그것을 단언하지 않았다.** 반출 추적은 «얼마나 나갔나」뿐 아니라
      «전체 중 얼마인가」까지 남아야 하는데, 락이 없으면 그 줄은 **조용히 사라질 수 있다.**
    """
    import ast
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "routers" / "growth.py").read_text(encoding="utf-8")
    keys: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "audit_admin_action"):
            continue
        for kw in node.keywords:
            if kw.arg == "detail" and isinstance(kw.value, ast.Dict):
                keys |= {k.value for k in kw.value.keys
                         if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return keys


def test_audit_record_says_how_much_of_the_whole_went_out():
    """★감사기록이 **반출량과 모집단**을 함께 남기는가 — 기계 변이 생존을 닫는다."""
    keys = _audit_detail_keys()

    # ★대조군 먼저 — AST 가 실제로 감사 호출을 찾았는가
    assert "count" in keys, f"조회기 사망 — audit_admin_action(detail=...) 을 못 찾았다: {sorted(keys)}"
    # ★역대조군 — 없는 키가 잡히면 파서가 아무거나 집고 있다
    assert "zzz_nope_sentinel" not in keys

    assert "total" in keys, (
        f"감사기록이 **모집단**을 안 남긴다 — 「전체 중 얼마가 나갔나」를 못 되짚는다: {sorted(keys)}")
    assert "truncated" in keys, f"감사기록이 절단 여부를 안 남긴다: {sorted(keys)}"
