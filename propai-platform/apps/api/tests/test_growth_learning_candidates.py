"""few-shot 후보 승인 게이트 — 후보 **목록** 경로 잠금(2026-08-19).

【무엇이 결함이었나 — 실측】
자가학습 few-shot 은 `curate_few_shot` 이 status='candidate' 로만 적재하고
(`learning_loop.py` — 자동 active 금지), 프롬프트 주입은 status='active' 만 읽는다
(`base_interpreter._load_fewshot`). candidate→active 는 `POST /growth/learning/promote`
하나뿐인데 그 API 는 `example_id` 를 요구한다. 그런데 learning_examples 를 읽는 유일한
경로였던 `build_dataset_jsonl` 은 `SELECT input_summary, good_output, content_hash, tenant_id`
로 **id 를 안 돌려줬다**. → 화면을 만들어도 무엇을 승인할지 지목할 수 없었다.
즉 "사람이 승인해야만 도는 게이트인데 사람에게 문이 없다".

【이 파일이 잠그는 것】
  · `list_examples` 가 **id 를 준다**(promote 의 example_id 로 그대로 쓸 수 있다).
  · **두 모집단이 갈린다** — candidate 와 active 가 서로 **다른 id·다른 본문**을 내므로
    status 배선을 끊으면 결과가 실제로 달라진다(픽스처가 차를 만든다).
  · `build_dataset_jsonl` 계약 **불변**(id 없음·(input,output) 페어만) — 목록을 위해
    학습셋 계약을 건드리지 않았음을 증명한다.
  · 권리 미확인 후보를 **숨기지 않고 표시**한다(숨기면 관리자가 "후보 없음"으로 오독한다).
  · 엔드포인트가 super_admin 문지기를 실제로 태운다(무인증 → 401).

【가짜 DB 가 SQL 을 읽는 이유】
파라미터만 보고 거르면 SQL 의 WHERE 절을 지워도 통과한다(배선 무잠금). 그래서 아래
`_FakeDB` 는 **질의문에 그 절이 들어 있을 때만** 해당 필터를 적용한다 — WHERE 절을
지우는 변이가 곧 결과 변화로 드러난다.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import UTC, datetime

import pytest

_API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)
_ROOT = os.path.dirname(os.path.dirname(_API_DIR))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.services.growth import learning_loop as ll  # noqa: E402
from app.services.security import asset_rights as ar  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# 인메모리 가짜 DB (learning_examples + asset_rights)
# ════════════════════════════════════════════════════════════════════════════
class _Result:
    def __init__(self, rows=None, one=None, scalar=None):
        self._rows = rows or []
        self._one = one
        self._scalar = scalar

    def all(self):
        return self._rows

    def fetchall(self):
        return self._rows

    def first(self):
        # ★rows 만 준 경우에도 실제 DB 처럼 첫 행을 돌려준다(안 그러면 fetchone 경로가
        #   항상 None 이 되어 '없는 행'으로 오인되고, 그 오인이 테스트를 거짓 빨강/초록으로 만든다).
        return self._one if self._one is not None else (self._rows[0] if self._rows else None)

    def fetchone(self):
        return self.first()

    def scalar(self):
        return self._scalar


def _select_cols(sql: str) -> list[str]:
    """`SELECT a, b, c FROM learning_examples` 의 컬럼 목록을 읽는다(별칭 없음 전제)."""
    m = re.search(r"SELECT\s+(.+?)\s+FROM learning_examples", sql, re.S)
    assert m, f"learning_examples SELECT 를 파싱하지 못했다: {sql[:80]}"
    return [c.strip() for c in m.group(1).split(",") if c.strip()]


_KNOWN_COLUMNS = {
    "id", "service", "analysis_type", "status", "tenant_id", "content_hash",
    "input_summary", "good_output", "created_at", "source_feedback_id",
}


def _col(row: dict, name: str):
    """없는 컬럼을 고르면 실제 DB 처럼 터진다(오타·잘못된 컬럼 변이를 살려두지 않는다)."""
    if name not in _KNOWN_COLUMNS:
        raise RuntimeError(f'column "{name}" does not exist')
    return row.get(name)


class _FakeDB:
    """learning_examples SELECT(+COUNT) 와 asset_rights upsert/배치조회를 모사한다.

    ★필터는 **질의문에 그 절이 있을 때만** 적용한다(파라미터만 보면 WHERE 를 지워도 통과).
    """

    def __init__(self, examples=None):
        # examples: dict 리스트 — 키는 learning_examples 컬럼명.
        self.examples = examples or []
        self.rights: dict[tuple, dict] = {}
        self.commits = 0
        self.rollbacks = 0
        self.rights_selects = 0

    # ── 내부: SQL·파라미터로 learning_examples 행 거르기 ──────────────────
    def _filter(self, sql: str, p: dict) -> list[dict]:
        rows = list(self.examples)
        if "status IN (" in sql:
            wanted = {v for k, v in p.items() if re.fullmatch(r"st\d+", k)}
            rows = [r for r in rows if r.get("status") in wanted]
        if "service = :svc" in sql and p.get("svc"):
            rows = [r for r in rows if r.get("service") == p["svc"]]
        if "tenant_id = :tid" in sql and p.get("tid"):
            rows = [r for r in rows if r.get("tenant_id") == p["tid"]]
        if "WHERE id = :id" in sql and p.get("id"):
            rows = [r for r in rows if r.get("id") == p["id"]]
        # created_at DESC 정렬(문자열 비교 — 픽스처가 정렬 가능한 값을 쓴다).
        if "ORDER BY created_at DESC" in sql:
            rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(getattr(statement, "text", statement))
        p = params or {}

        if "CREATE TABLE" in sql or "CREATE INDEX" in sql:
            return _Result()
        if sql.strip().startswith("INSERT INTO asset_rights"):
            self.rights[(p["k"], p["t"])] = {
                "scope": p["sc"], "train": p["tr"], "export": p["ex"],
                "source": p["src"], "note": p["note"], "meta": p["meta"],
            }
            return _Result()
        if "FROM asset_rights" in sql and "IN (" in sql:
            self.rights_selects += 1
            n = sum(1 for kk in p if kk.startswith("k") and kk[1:].isdigit())
            out = []
            for i in range(n):
                key = (p[f"k{i}"], p[f"t{i}"])
                r = self.rights.get(key)
                if r is not None:
                    out.append((key[0], key[1], r["scope"], r["train"],
                                r["export"], r["source"], r["note"], {}))
            return _Result(rows=out)
        if "FROM asset_rights" in sql:  # 단건 조회(get_asset_right — 승인 지점 권리 게이트)
            self.rights_selects += 1
            r = self.rights.get((p["k"], p["t"]))
            if r is None:
                return _Result(one=None)
            return _Result(one=(r["scope"], r["train"], r["export"],
                                r["source"], r["note"], {}))
        if sql.strip().startswith("UPDATE learning_examples"):
            # `WHERE id = :id AND status = 'candidate'` — candidate 만 전이(재전이 금지).
            for r in self.examples:
                if r.get("id") == p.get("id") and r.get("status") == "candidate":
                    r["status"] = p["st"]
                    return _Result(one=(r["id"], r["status"]))
            return _Result(one=None)
        if "COUNT(*) FROM learning_examples" in sql:
            return _Result(scalar=len(self._filter(sql, p)))
        if "FROM learning_examples" in sql:
            rows = self._filter(sql, p)
            if "LIMIT :lim OFFSET :off" in sql:
                off = int(p.get("off", 0))
                lim = int(p.get("lim", 50))
                rows = rows[off:off + lim]
            elif "LIMIT :lim" in sql:
                rows = rows[: int(p.get("lim", 50))]
            # ★SELECT 컬럼 목록을 **질의문에서 읽어** 그 순서대로 값을 돌려준다.
            #   고정 튜플을 돌려주면 SELECT 에서 `id` 를 빼는 변이가 살아남는다 —
            #   그건 이 커밋이 고치는 결함(=조회가 id 를 안 준다) 그 자체다.
            return _Result(rows=[tuple(_col(r, c) for c in _select_cols(sql)) for r in rows])
        return _Result()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.fixture(autouse=True)
def _schema_ready():
    """asset_rights ensure_schema 를 준비됨으로 고정(가짜 DB 에 DDL 왕복 불필요)."""
    saved = ar._SCHEMA_READY
    ar._SCHEMA_READY = True
    yield
    ar._SCHEMA_READY = saved


# ════════════════════════════════════════════════════════════════════════════
# 픽스처 — ★두 모집단(candidate vs active)이 **다른 값**을 내야 배선 변이가 죽는다
# ════════════════════════════════════════════════════════════════════════════
CAND = {
    "id": "ex-cand-1", "service": "avm", "analysis_type": "avm_valuation",
    "status": "candidate", "tenant_id": "tenant-A", "content_hash": "hash-cand",
    "input_summary": "후보 입력요약", "good_output": "후보-미승인-본문",
    "created_at": "2026-08-18T10:00:00+00:00",
}
ACTIVE = {
    "id": "ex-active-1", "service": "avm", "analysis_type": "avm_valuation",
    "status": "active", "tenant_id": "tenant-A", "content_hash": "hash-active",
    "input_summary": "이미승인 입력요약", "good_output": "활성-승인완료-본문",
    "created_at": "2026-08-17T10:00:00+00:00",
}
REJECTED = {
    "id": "ex-rejected-1", "service": "avm", "analysis_type": "avm_valuation",
    "status": "rejected", "tenant_id": "tenant-A", "content_hash": "hash-rejected",
    "input_summary": "거부 입력요약", "good_output": "거부-본문",
    "created_at": "2026-08-16T10:00:00+00:00",
}
CAND_OTHER = {
    "id": "ex-cand-2", "service": "permit", "analysis_type": "permit_ai",
    "status": "candidate", "tenant_id": "tenant-B", "content_hash": "hash-cand-2",
    "input_summary": "다른 테넌트 후보", "good_output": "다른-서비스-본문",
    "created_at": "2026-08-19T10:00:00+00:00",
}

ALL_ROWS = [CAND, ACTIVE, REJECTED, CAND_OTHER]

# ★created_at 이 문자열인 픽스처만 쓰면 `isoformat()` 분기와 `str()` 분기가 **같은 값**을 내
#   그 배선을 끊어도 결과가 안 변한다(모집단이 안 갈린 상태). 진짜 datetime 행을 따로 둔다.
CAND_DT = dict(CAND, id="ex-cand-dt", content_hash="hash-cand-dt",
               created_at=datetime(2026, 8, 15, 9, 30, tzinfo=UTC))


def _db() -> _FakeDB:
    return _FakeDB(examples=[dict(r) for r in ALL_ROWS])


# ════════════════════════════════════════════════════════════════════════════
# 1) 결함 잠금 — 목록이 id 를 준다(= promote 대상을 지목할 수 있다)
# ════════════════════════════════════════════════════════════════════════════
async def test_후보목록이_승인에_필요한_id를_돌려준다():
    """★이 결함의 핵심. id 가 없으면 화면이 있어도 승인이 불가능하다."""
    res = await ll.list_examples(_db())
    assert res["items"], "전제 불성립 — 후보가 0건이면 아래 단언이 공허하다"
    for it in res["items"]:
        assert it["id"], "id 가 비었다 — promote(example_id) 를 부를 수 없다"
    assert {it["id"] for it in res["items"]} == {"ex-cand-1", "ex-cand-2"}


async def test_목록의_id가_promote_요청_계약에_그대로_들어간다():
    """목록 → 승인 배선: 목록이 준 id 가 PromoteRequest.example_id 로 검증을 통과해야 한다."""
    from app.routers.growth import PromoteRequest

    res = await ll.list_examples(_db())
    assert len(res["items"]) >= 1
    req = PromoteRequest(example_id=res["items"][0]["id"], status="active")
    assert req.example_id == res["items"][0]["id"]
    assert req.status == "active"


async def test_build_dataset_jsonl_계약은_그대로다():
    """★학습셋 계약 불변 증명 — 목록을 만들려고 이 함수를 건드리지 않았다.

    여전히 (input, output) 페어만 내고 **id 는 없다**(그래서 별도 목록 함수가 필요했다).
    """
    import json

    ds = await ll.build_dataset_jsonl(_db(), statuses=("candidate",))
    assert ds["count"] == 2, "전제 불성립 — 대상이 0이면 아래 단언이 공허하다"
    for line in ds["jsonl"].split("\n"):
        obj = json.loads(line)
        assert set(obj) == {"messages"}
        assert "id" not in obj
        assert [m["role"] for m in obj["messages"]] == ["user", "assistant"]


# ════════════════════════════════════════════════════════════════════════════
# 2) 배선 — status/service/tenant 필터가 실제로 결과를 가른다
# ════════════════════════════════════════════════════════════════════════════
async def test_기본은_candidate만_보이고_active와_다른_값이다():
    """두 모집단이 갈린다 — 후보 본문과 활성 본문이 실제로 다르다."""
    res = await ll.list_examples(_db())
    bodies = {it["good_output"] for it in res["items"]}
    assert "후보-미승인-본문" in bodies
    assert "활성-승인완료-본문" not in bodies, "active 가 섞였다 — status 배선이 끊겼다"
    assert "거부-본문" not in bodies
    assert res["statuses"] == ["candidate"]


async def test_status_active_로_바꾸면_다른_모집단이_나온다():
    res = await ll.list_examples(_db(), statuses=("active",))
    assert [it["id"] for it in res["items"]] == ["ex-active-1"]
    assert res["items"][0]["good_output"] == "활성-승인완료-본문"


async def test_알_수_없는_status는_candidate로_수렴한다():
    res = await ll.list_examples(_db(), statuses=("banana",))
    assert res["statuses"] == ["candidate"]
    assert {it["id"] for it in res["items"]} == {"ex-cand-1", "ex-cand-2"}


async def test_service_필터가_실제로_좁힌다():
    res = await ll.list_examples(_db(), service="permit")
    assert [it["id"] for it in res["items"]] == ["ex-cand-2"]
    assert res["total"] == 1


async def test_tenant_필터가_실제로_좁힌다():
    res = await ll.list_examples(_db(), tenant_id="tenant-B")
    assert [it["id"] for it in res["items"]] == ["ex-cand-2"]


async def test_테넌트를_지정하지_않으면_전체가_보인다():
    """★조용히 숨기지 않는다 — 다른 테넌트 후보도 보여야 그 테넌트의 게이트가 열린다."""
    res = await ll.list_examples(_db())
    assert {it["tenant_id"] for it in res["items"]} == {"tenant-A", "tenant-B"}


async def test_각_행이_어느_테넌트에_주입될지_알려준다():
    """승인하면 base_interpreter._load_fewshot 이 그 tenant_id 로만 주입한다 — 화면이 봐야 한다."""
    res = await ll.list_examples(_db(), service="permit")
    assert res["items"][0]["tenant_id"] == "tenant-B"


async def test_최신순_정렬과_페이지네이션():
    res = await ll.list_examples(_db(), limit=1, offset=0)
    assert [it["id"] for it in res["items"]] == ["ex-cand-2"]  # created_at 이 더 최신
    assert res["total"] == 2 and res["limit"] == 1 and res["offset"] == 0

    res2 = await ll.list_examples(_db(), limit=1, offset=1)
    assert [it["id"] for it in res2["items"]] == ["ex-cand-1"]
    assert res2["total"] == 2


async def test_limit_상한이_걸린다():
    res = await ll.list_examples(_db(), limit=99999)
    assert res["limit"] == ll.LIST_MAX_LIMIT


# ════════════════════════════════════════════════════════════════════════════
# 3) 미리보기 — 자르되 잘랐다고 말한다
# ════════════════════════════════════════════════════════════════════════════
def test_preview_는_자른_사실을_함께_돌려준다():
    short, cut = ll._preview("가나다", max_chars=10)
    assert (short, cut) == ("가나다", False)
    long_text = "가" * 50
    cut_text, was_cut = ll._preview(long_text, max_chars=10)
    assert was_cut is True and len(cut_text) == 10
    assert ll._preview(None, max_chars=10) == ("", False)
    # 상한 0 이하면 자르지 않는다(원문 그대로).
    assert ll._preview(long_text, max_chars=0) == (long_text, False)


async def test_긴_본문은_미리보기로_잘리고_잘렸다고_표시된다():
    rows = [dict(CAND, good_output="가" * 1500, input_summary="나" * 1500)]
    res = await ll.list_examples(_FakeDB(examples=rows), preview_chars=100)
    it = res["items"][0]
    assert len(it["good_output"]) == 100 and it["good_output_truncated"] is True
    assert len(it["input_summary"]) == 100 and it["input_summary_truncated"] is True


# ════════════════════════════════════════════════════════════════════════════
# 4) 자산권리 — 거르지 않고 **표시**한다(숨기면 "후보 없음"으로 오독된다)
# ════════════════════════════════════════════════════════════════════════════
async def test_권리_미확인_후보도_목록에서_사라지지_않는다():
    db = _db()
    # hash-cand 만 학습허용으로 등록. hash-cand-2 는 미등록(=권리 불명).
    await ar.upsert_asset_rights_batch(db, [
        ar.AssetRight(asset_key="hash-cand", tenant_id="tenant-A",
                      scope="train_ok", train_allowed=True, source="test"),
    ])
    res = await ll.list_examples(db)

    # ★핵심: 권리 없는 것을 숨기지 않는다 — 건수가 줄지 않아야 한다.
    assert {it["id"] for it in res["items"]} == {"ex-cand-1", "ex-cand-2"}
    by_id = {it["id"]: it for it in res["items"]}
    assert by_id["ex-cand-1"]["train_allowed"] is True
    assert by_id["ex-cand-1"]["rights_scope"] == "train_ok"
    # 미등록 = 권리 불명 = 학습 금지(default-deny) — 그러나 목록에는 남아 관리자가 본다.
    assert by_id["ex-cand-2"]["train_allowed"] is False


async def test_권리조회가_실패해도_목록은_돌아온다():
    """권리 조회는 표시용이다 — 실패는 '권리 미확인'으로 정직하게 수렴하고 화면을 죽이지 않는다."""
    db = _db()

    async def _boom(*_a, **_k):
        raise RuntimeError("registry down")

    import app.services.security.asset_rights as ar_mod
    saved = ar_mod.get_asset_rights_batch
    ar_mod.get_asset_rights_batch = _boom
    try:
        res = await ll.list_examples(db)
    finally:
        ar_mod.get_asset_rights_batch = saved

    assert {it["id"] for it in res["items"]} == {"ex-cand-1", "ex-cand-2"}
    assert all(it["train_allowed"] is False for it in res["items"])


async def test_조회_실패는_빈_목록으로_수렴한다():
    class _BrokenDB(_FakeDB):
        async def execute(self, statement, params=None):  # noqa: ANN001
            raise RuntimeError("db down")

    res = await ll.list_examples(_BrokenDB())
    assert res["items"] == [] and res["total"] == 0


# ════════════════════════════════════════════════════════════════════════════
# 5) 엔드포인트 — super_admin 문지기·status 어휘·경로 등록
# ════════════════════════════════════════════════════════════════════════════
class _FakeHeaders(dict):
    def get(self, k, default=None):  # noqa: A003
        return dict.get(self, k, default)


class _FakeRequest:
    def __init__(self, headers=None):
        self.headers = _FakeHeaders(headers or {})


async def test_후보목록_엔드포인트가_등록돼_있다():
    from app.routers import growth as g

    paths = {(r.path, tuple(sorted(r.methods))) for r in g.router.routes
             if hasattr(r, "methods")}
    assert ("/growth/learning/candidates", ("GET",)) in paths
    # 대조군 — 조회기가 죽으면 위 단언도 함께 죽어야 한다(공허한 초록 방지).
    assert ("/growth/learning/promote", ("POST",)) in paths


async def test_인증없이_부르면_401():
    """★super_admin 문지기를 실제로 태운다(선언만 하고 안 부르는 형태 차단)."""
    from fastapi import HTTPException

    from app.routers import growth as g

    with pytest.raises(HTTPException) as ei:
        await g.list_learning_candidates(request=_FakeRequest(), db=_db())
    assert ei.value.status_code == 401


async def test_status_어휘가_learning_loop와_어긋나지_않는다():
    from app.routers import growth as g

    assert g._LEARNING_LIST_STATUSES == ll._VALID_STATUSES


# ════════════════════════════════════════════════════════════════════════════
# 6) 행 모양 · 날짜 직렬화 — 화면이 읽는 필드가 실제로 실려 온다
# ════════════════════════════════════════════════════════════════════════════
async def test_행에_화면이_쓰는_필드가_전부_실린다():
    res = await ll.list_examples(_FakeDB(examples=[dict(CAND)]))
    it = res["items"][0]
    assert it["id"] == "ex-cand-1"
    assert it["service"] == "avm"
    assert it["analysis_type"] == "avm_valuation"
    assert it["status"] == "candidate"
    assert it["tenant_id"] == "tenant-A"
    assert it["content_hash"] == "hash-cand"
    assert it["input_summary"] == "후보 입력요약"
    assert it["good_output"] == "후보-미승인-본문"
    assert it["created_at"] == "2026-08-18T10:00:00+00:00"


async def test_datetime_created_at은_ISO_문자열로_직렬화된다():
    """JSON 응답에 그대로 실리려면 문자열이어야 한다(datetime 그대로면 직렬화가 깨진다)."""
    res = await ll.list_examples(_FakeDB(examples=[dict(CAND_DT)]))
    created = res["items"][0]["created_at"]
    assert isinstance(created, str)
    assert created == datetime(2026, 8, 15, 9, 30, tzinfo=UTC).isoformat()
    assert created.startswith("2026-08-15T09:30")


async def test_created_at이_없어도_터지지_않는다():
    res = await ll.list_examples(_FakeDB(examples=[dict(CAND, created_at=None)]))
    assert res["items"][0]["created_at"] is None


def test_공개목록_all_에_적힌_이름이_전부_실재한다():
    """`__all__` 오타는 `from ... import *` 를 조용히 깨뜨린다 — 이름을 실물과 결속한다."""
    assert ll.__all__, "공개목록이 비었다 — 아래 단언이 공허해진다"
    missing = [n for n in ll.__all__ if not hasattr(ll, n)]
    assert missing == [], f"__all__ 에만 있고 실물이 없는 이름: {missing}"
    for name in ("list_examples", "_preview", "CANDIDATE_PREVIEW_MAX_CHARS", "LIST_MAX_LIMIT"):
        assert name in ll.__all__


# ════════════════════════════════════════════════════════════════════════════
# 7) 엔드포인트 — 응답 계약·필터 전달·감사기록·status 검증
# ════════════════════════════════════════════════════════════════════════════
async def _call_endpoint(monkeypatch, db, **kw):
    """총괄관리자 통과 상태로 후보목록 엔드포인트를 직접 호출한다."""
    import app.core.audit as audit_mod
    from app.routers import growth as g

    async def _admin(_request, _db):
        return "admin-1"

    audits: list[dict] = []

    async def _audit(**payload):
        audits.append(payload)

    monkeypatch.setattr(g, "_require_admin", _admin)
    monkeypatch.setattr(audit_mod, "audit_admin_action", _audit)

    params = {"service": None, "status": "candidate", "tenant_id": None,
              "limit": 50, "offset": 0}
    params.update(kw)
    res = await g.list_learning_candidates(request=_FakeRequest(), db=db, **params)
    return res, audits


async def test_엔드포인트가_후보를_응답계약대로_돌려준다(monkeypatch):
    res, _ = await _call_endpoint(monkeypatch, _db())

    assert [it.id for it in res.items] == ["ex-cand-2", "ex-cand-1"]  # 최신순
    assert res.total == 2
    assert res.statuses == ["candidate"]
    assert res.limit == 50 and res.offset == 0
    first = res.items[0]
    assert first.service == "permit"
    assert first.analysis_type == "permit_ai"
    assert first.status == "candidate"
    assert first.tenant_id == "tenant-B"
    assert first.content_hash == "hash-cand-2"
    assert first.input_summary == "다른 테넌트 후보"
    assert first.good_output == "다른-서비스-본문"
    assert first.input_summary_truncated is False
    assert first.good_output_truncated is False
    assert first.created_at == "2026-08-19T10:00:00+00:00"
    assert first.train_allowed is False  # 권리 미등록 = 불명 = 학습 금지(표시만)
    assert first.rights_scope == "unknown"


async def test_엔드포인트가_필터를_서비스층에_그대로_넘긴다(monkeypatch):
    res, _ = await _call_endpoint(monkeypatch, _db(), service="permit", limit=1)
    assert [it.id for it in res.items] == ["ex-cand-2"]
    assert res.service == "permit" and res.limit == 1

    res2, _ = await _call_endpoint(monkeypatch, _db(), tenant_id="tenant-A")
    assert [it.id for it in res2.items] == ["ex-cand-1"]
    assert res2.tenant_id == "tenant-A"

    res3, _ = await _call_endpoint(monkeypatch, _db(), status="active")
    assert [it.id for it in res3.items] == ["ex-active-1"]
    assert res3.statuses == ["active"]


async def test_엔드포인트가_페이지_이동을_전달한다(monkeypatch):
    res, _ = await _call_endpoint(monkeypatch, _db(), limit=1, offset=1)
    assert [it.id for it in res.items] == ["ex-cand-1"]
    assert res.offset == 1 and res.total == 2


async def test_열람은_감사에_남는다(monkeypatch):
    """promote 가 감사를 남기는 것과 짝을 맞춘다 — 누가 어떤 묶음을 봤는지 추적된다."""
    _, audits = await _call_endpoint(monkeypatch, _db(), service="permit")
    assert len(audits) == 1, "감사 기록이 남지 않았다"
    a = audits[0]
    assert a["action"] == "growth.learn.candidates_list"
    assert a["actor_id"] == "admin-1"
    assert a["actor_role"] == "super_admin"
    assert a["target"] == "permit@candidate"
    assert a["detail"]["count"] == 1
    assert a["detail"]["total"] == 1
    assert a["detail"]["tenant_id"] is None  # 테넌트를 안 좁혔다는 사실도 감사에 남는다


async def test_어휘에_없는_status는_400(monkeypatch):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        await _call_endpoint(monkeypatch, _db(), status="banana")
    assert ei.value.status_code == 400
    # 안내문이 "무엇을 써야 하는지"를 실제로 알려야 한다(빈 400 은 관리자를 막다른 길에 둔다).
    assert "candidate" in str(ei.value.detail)


async def test_잘린_본문_표시가_엔드포인트까지_전달된다(monkeypatch):
    long_row = dict(CAND, good_output="가" * 5000, input_summary="나" * 5000)
    res, _ = await _call_endpoint(monkeypatch, _FakeDB(examples=[long_row]))
    it = res.items[0]
    assert it.good_output_truncated is True
    assert it.input_summary_truncated is True
    assert len(it.good_output) == ll.CANDIDATE_PREVIEW_MAX_CHARS


def test_엔드포인트_기본값이_승인대기_목록이다():
    """★기본이 candidate 여야 관리자가 화면을 열자마자 '승인할 것'을 본다.

    직접 호출 테스트는 인자를 명시하므로 기본값을 태우지 않는다 — 선언을 직접 잠근다.
    """
    import inspect

    from app.routers import growth as g

    params = inspect.signature(g.list_learning_candidates).parameters
    assert params["status"].default.default == "candidate"
    assert params["service"].default.default is None
    assert params["tenant_id"].default.default is None
    assert params["limit"].default.default == 50
    assert params["offset"].default.default == 0


# ════════════════════════════════════════════════════════════════════════════
# 8) 승인 지점 학습권리 게이트 (2026-08-19 적대리뷰 HIGH)
# ════════════════════════════════════════════════════════════════════════════
# 【왜 여기서 막는가 — 실측】
#   · base_interpreter._load_fewshot 은 status='active' 만 보고 권리를 전혀 보지 않는다.
#   · build_dataset_jsonl 의 enforce_asset_rights 는 **학습셋 다운로드** 경로이고 기본 OFF 다.
#   → 주입 경로에 권리 게이트가 없다. 그래서 active 로 가는 **유일한 문**에서 막는다.
# 【픽스처가 두 모집단을 가른다】
#   hash-cand(train_ok 등록) 와 hash-cand-2(미등록) 가 **다른 HTTP 결과**를 낸다 —
#   200 vs 409. 같은 결과를 내면 게이트 배선을 끊어도 통과한다.


async def _call_promote(monkeypatch, db, **body_kw):
    """총괄관리자 통과 상태로 promote 를 직접 호출한다. (결과, 감사기록) 반환."""
    import app.core.audit as audit_mod
    from app.routers import growth as g

    async def _admin(_request, _db):
        return "admin-1"

    audits: list[dict] = []

    async def _audit(**payload):
        audits.append(payload)

    monkeypatch.setattr(g, "_require_admin", _admin)
    monkeypatch.setattr(audit_mod, "audit_admin_action", _audit)

    body = g.PromoteRequest(**body_kw)
    res = await g.promote_learning_example(body=body, request=_FakeRequest(), db=db)
    return res, audits


async def _seed_rights(db, *, asset_key, tenant_id, train_allowed):
    await ar.upsert_asset_rights_batch(db, [
        ar.AssetRight(asset_key=asset_key, tenant_id=tenant_id,
                      scope="train_ok" if train_allowed else "internal_only",
                      train_allowed=train_allowed, source="test"),
    ])


async def test_권리_확인된_후보는_그냥_승인된다(monkeypatch):
    db = _db()
    await _seed_rights(db, asset_key="hash-cand", tenant_id="tenant-A", train_allowed=True)

    res, audits = await _call_promote(monkeypatch, db, example_id="ex-cand-1", status="active")

    assert res.status == "active"
    assert res.rights_acknowledged is False  # 인수 없이 통과 = 권리가 실제로 확인됐다
    assert audits[0]["detail"] == {"status": "active", "rights_acknowledged": False}


async def test_권리_미확인_후보는_승인이_거부된다(monkeypatch):
    """★핵심 — '승인만으로 권리 없는 예시가 프롬프트에 들어가는' 경로를 닫는다."""
    from fastapi import HTTPException

    db = _db()  # hash-cand-2 는 레지스트리 미등록 = 권리 불명

    with pytest.raises(HTTPException) as ei:
        await _call_promote(monkeypatch, db, example_id="ex-cand-2", status="active")

    assert ei.value.status_code == 409
    assert "학습 사용 권리가 확인되지 않은" in str(ei.value.detail)
    # ★상태가 바뀌지 않았다 — 거부가 실제로 쓰기를 막았는지까지 본다(문구만 보면 공허하다).
    still = await ll.list_examples(db, statuses=("candidate",), service="permit")
    assert [it["id"] for it in still["items"]] == ["ex-cand-2"]


async def test_명시_거부된_권리도_승인이_거부된다(monkeypatch):
    """미등록(불명)뿐 아니라 train_allowed=False 로 **명시 거부**된 것도 막힌다."""
    from fastapi import HTTPException

    db = _db()
    await _seed_rights(db, asset_key="hash-cand", tenant_id="tenant-A", train_allowed=False)

    with pytest.raises(HTTPException) as ei:
        await _call_promote(monkeypatch, db, example_id="ex-cand-1", status="active")
    assert ei.value.status_code == 409


async def test_사람이_책임을_인수하면_승인되고_감사에_남는다(monkeypatch):
    """문을 완전히 닫지는 않는다 — 다만 '몰랐다'로는 못 켠다(인수 사실이 감사에 남는다)."""
    db = _db()

    res, audits = await _call_promote(
        monkeypatch, db, example_id="ex-cand-2", status="active",
        acknowledge_unverified_rights=True,
    )

    assert res.status == "active"
    assert res.rights_acknowledged is True
    assert audits[0]["action"] == "growth.learn.promote.active"
    assert audits[0]["detail"]["rights_acknowledged"] is True


async def test_거부는_권리와_무관하게_항상_가능하다(monkeypatch):
    """거부는 안전한 방향이다 — 권리 게이트가 '치우기'를 막으면 후보가 쌓이기만 한다."""
    db = _db()
    res, audits = await _call_promote(
        monkeypatch, db, example_id="ex-cand-2", status="rejected",
    )
    assert res.status == "rejected"
    assert res.rights_acknowledged is False
    assert audits[0]["detail"]["rights_acknowledged"] is False


async def test_인수해도_이미_처리된_건은_재전이되지_않는다(monkeypatch):
    """권리 게이트를 통과해도 candidate 만 전이한다(기존 계약 무회귀)."""
    from fastapi import HTTPException

    db = _db()
    with pytest.raises(HTTPException) as ei:
        await _call_promote(monkeypatch, db, example_id="ex-active-1", status="active",
                            acknowledge_unverified_rights=True)
    assert ei.value.status_code == 409
    assert "이미 처리된" in str(ei.value.detail)


async def test_없는_예시는_404(monkeypatch):
    from fastapi import HTTPException

    db = _db()
    with pytest.raises(HTTPException) as ei:
        await _call_promote(monkeypatch, db, example_id="없는id", status="active")
    assert ei.value.status_code == 404


def test_권리_인수_기본값은_거짓이다():
    """★기본이 True 면 게이트가 장식이 된다 — 기본값을 직접 잠근다."""
    from app.routers.growth import PromoteRequest

    assert PromoteRequest(example_id="x").acknowledge_unverified_rights is False
    assert PromoteRequest(example_id="x").status == "active"
