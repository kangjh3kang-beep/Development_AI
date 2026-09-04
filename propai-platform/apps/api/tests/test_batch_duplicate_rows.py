"""배치 중복 행 — **읽는 순간 접고, `counts` 도 다시 센다**.

## 라이브 실측 (2026-09-03 · 동료 세션 `development-ai-62` 가 DB 에서 측정)

    잡 총 25건 · 중복 행을 가진 잡 **9건(36%)** · 음성 대조군(중복 없음) 16건
    최악: counts=2,800 인데 고유 PNU **1,000** (2.8배)

★그 `counts.confirmed` 는 `batch_service` 에서 **견적 금액에 곱해진다** — 부풀린 수가 **돈**이 된다.
★★그리고 8건은 **`counts` 도 함께 부풀어** 있어 «counts ≠ 행수» 조회로는 **원리적으로 안 보였다**.
   내 첫 쿼리가 1건만 낸 이유이고, 옳은 축은 **중복 (job,pnu)** 이었다.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.api.app.foundation.parcel.batch.job_store import dedupe_item_rows


class _Row:
    """`batch_item_result` 행 흉내 — ★순서 컬럼이 없다(id 는 랜덤 UUID)."""

    # ★스텁도 계약이다 — 실제 행이 갖는 필드를 다 갖춰야 «테스트에서만 터지는» 결함을 안 만든다.
    def __init__(self, pnu: str, status: str = "confirmed", ref: dict | None = None,
                 rid: str = "a", reason: str | None = None) -> None:
        self.pnu, self.status, self.record_ref, self.id = pnu, status, ref, rid
        self.reason = reason


class Test중복을PNU당한건으로접는다:
    def test_같은_PNU_세_행이_한_건이_된다(self):
        rows = [_Row("A", rid="x"), _Row("A", rid="y"), _Row("A", rid="z")]
        assert len(dedupe_item_rows(rows)) == 1

    def test_대조군_서로_다른_PNU_는_안_접힌다(self):
        """★「전부 하나로 접는」 구현과 구별한다."""
        rows = [_Row("A"), _Row("B"), _Row("C")]
        assert len({r.pnu for r in dedupe_item_rows(rows)}) == 3

    def test_중복이_없으면_그대로다(self):
        rows = [_Row("A"), _Row("B")]
        assert len(dedupe_item_rows(rows)) == 2


class Test어느행을남기는가결정적이다:
    """★순서 컬럼이 없으므로 **시간이 아니라 정보량**으로 고른다."""

    def test_상태가_높은_것을_남긴다(self):
        rows = [_Row("A", "not_found", rid="x"), _Row("A", "confirmed", rid="y")]
        kept = dedupe_item_rows(rows)[0]
        assert kept.status == "confirmed", "뒤에 성공한 실행이 앞선 실패를 대체해야 한다"

    def test_상태가_같으면_record_ref_가_풍부한_것(self):
        """★투영 확장 전 행은 3필드, 후는 11필드 — 풍부한 쪽이 나중 것이다."""
        # ★`rid` 를 **반대로** 준다 — `rich` 가 사전순으로 **지도록** 해야 규칙 ②(정보량)가
        #   **유일하게 답을 가른다.** 초판은 rich="b"/thin="a" 라 타이브레이크 ③ 단독으로도
        #   같은 답이 나와 **규칙 ② 가 완전 무잠금**이었다(적대 리뷰 변이 M6 SURVIVED).
        thin = _Row("A", ref={"source": "x", "zone_type": "y", "land_category": "z"}, rid="z")
        rich = _Row("A", ref={f"k{i}": i for i in range(11)}, rid="a")
        assert dedupe_item_rows([thin, rich])[0].record_ref == rich.record_ref
        # ★입력 순서를 뒤집어도 같은 답(순서 의존이면 재현 불가능하다)
        assert dedupe_item_rows([rich, thin])[0].record_ref == rich.record_ref

    def test_전부_같으면_id_사전순으로_결정적이다(self):
        a, b = _Row("A", ref={"k": 1}, rid="aaa"), _Row("A", ref={"k": 1}, rid="bbb")
        assert dedupe_item_rows([a, b])[0].id == "bbb"
        assert dedupe_item_rows([b, a])[0].id == "bbb", "입력 순서에 따라 답이 바뀌면 안 된다"


class Test레코드복원이counts를다시센다:
    """★배열만 접고 `counts` 를 그대로 두면 **소비처마다 다른 답**을 받는다 — 그게 이 결함의 본체다."""

    @staticmethod
    def _job_row(counts: dict):
        class _J:
            id = "j1"
            snapshot_id = "s1"
            state = "complete"
            region_input: dict = {}
            completeness = "complete"

        _J.counts = counts
        return _J()

    def test_저장된_counts_가_부풀어_있어도_실제로_다시_센다(self):
        from apps.api.app.foundation.parcel.batch.job_store import DbJobStore

        rows = [_Row("A", rid="x"), _Row("A", rid="y"), _Row("B", rid="z")]
        rec = DbJobStore.__new__(DbJobStore)._to_record(
            self._job_row({"total": 3, "confirmed": 3}), rows, None,
        )
        assert len(rec.items) == 2, "items 가 안 접혔다"
        # ★저장값 3 을 그대로 쓰면 견적이 1.5배가 된다.
        assert rec.job.counts.total == 2
        assert rec.job.counts.confirmed == 2

    def test_대조군_오염이_없으면_저장값과_같다(self):
        """★「항상 다시 세서 값이 달라지는」 것이 아니라 **오염일 때만** 달라진다."""
        from apps.api.app.foundation.parcel.batch.job_store import DbJobStore

        rows = [_Row("A", rid="x"), _Row("B", rid="y")]
        rec = DbJobStore.__new__(DbJobStore)._to_record(
            self._job_row({"total": 2, "confirmed": 2}), rows, None,
        )
        assert rec.job.counts.total == 2 and rec.job.counts.confirmed == 2

    def test_라이브_최악_사례_비율을_재현한다(self):
        """★실측: counts 2,800 · 고유 1,000 → **2.8배**. 그 배수가 견적에 곱해졌다."""
        from apps.api.app.foundation.parcel.batch.job_store import DbJobStore

        rows = [_Row(f"P{i}", rid=f"r{i}-{k}") for i in range(1000) for k in range(3)]
        rec = DbJobStore.__new__(DbJobStore)._to_record(
            self._job_row({"total": 3000, "confirmed": 3000}), rows, None,
        )
        assert rec.job.counts.total == 1000
        assert len(rec.items) == 1000


@pytest.mark.parametrize("empty", [[], ()])
def test_빈_입력은_빈_결과다_지어내지_않는다(empty):
    # ★초판은 `dedupe_item_rows(bad or [])` 라 세 파라미터가 **전부 `[]`** 로 들어가
    #   같은 단언을 3번 했다(공허). 이제 인자를 **그대로** 넘긴다.
    assert dedupe_item_rows(empty) == []


def test_None_은_조용히_빈결과가_아니라_터진다():
    """★「모름」을 「없음」으로 바꾸지 않는다 — 호출부의 버그를 삼키면 안 된다."""
    with pytest.raises(TypeError):
        dedupe_item_rows(None)


class Test부풀린수가견적에곱해지지않는다:
    """★`batch_service:265` — `estimated_fee = per_unit * counts.confirmed`.

    **부풀린 수가 곧 돈이다.** 라이브 최악 사례(2.8배)면 견적도 2.8배가 된다.
    그래서 「접었다」로 끝내지 않고 **금액까지** 태운다.
    """

    @pytest.mark.asyncio
    async def test_중복이_견적을_부풀리지_않는다(self, monkeypatch):
        from apps.api.app.foundation.parcel.batch.batch_service import BatchService
        from apps.api.app.foundation.parcel.batch.job_store import DbJobStore, InMemoryJobStore

        # 같은 PNU 3행 + 다른 PNU 1행 → 고유 2건
        rows = [_Row("A", rid="x"), _Row("A", rid="y"), _Row("A", rid="z"), _Row("B", rid="w")]

        class _J:
            id = "j1"; snapshot_id = "s1"; state = "complete"
            region_input: dict = {}; completeness = "complete"
            counts = {"total": 4, "confirmed": 4}

        rec = DbJobStore.__new__(DbJobStore)._to_record(_J(), rows, None)

        store = InMemoryJobStore()
        await store.save(rec)
        svc = BatchService(store=store)

        import app.core.billing as billing

        monkeypatch.setattr(billing, "service_fee_bulk_parcel_per_unit", lambda: 1000.0)
        res = await svc.result(rec.job.id)

        # ★고유 2건 × 1,000원 = 2,000원. 접기 전이면 4,000원(2배)이 됐다.
        assert res.counts.confirmed == 2
        assert res.estimated_fee_krw == 2000.0, f"부풀린 수가 금액에 곱해졌다: {res.estimated_fee_krw}"

    @pytest.mark.asyncio
    async def test_대조군_중복이_없으면_금액이_그대로다(self, monkeypatch):
        """★「항상 절반으로 깎는」 구현과 구별한다."""
        from apps.api.app.foundation.parcel.batch.batch_service import BatchService
        from apps.api.app.foundation.parcel.batch.job_store import DbJobStore, InMemoryJobStore

        rows = [_Row("A", rid="x"), _Row("B", rid="y")]

        class _J:
            id = "j2"; snapshot_id = "s1"; state = "complete"
            region_input: dict = {}; completeness = "complete"
            counts = {"total": 2, "confirmed": 2}

        rec = DbJobStore.__new__(DbJobStore)._to_record(_J(), rows, None)
        store = InMemoryJobStore()
        await store.save(rec)

        import app.core.billing as billing

        monkeypatch.setattr(billing, "service_fee_bulk_parcel_per_unit", lambda: 1000.0)
        res = await BatchService(store=store).result(rec.job.id)
        assert res.estimated_fee_krw == 2000.0


class Test판정할수없는행을뭉개지않는다:
    """★**결함을 고치려다 데이터를 지우는 것**을 막는다.

    PNU 가 비면 두 행이 **같은 필지인지 알 수 없다**. 「모른다」를 「같다」로 뭉개면
    서로 다른 미해석 입력이 **한 건으로 사라진다** — 원래 결함보다 나쁘다.
    `job_runner` 는 PNU 형식 오류 입력에 `pnu=str(pnu)` 로 **빈 값을 실을 수 있다.**
    """

    def test_빈_PNU_행은_전부_남는다(self):
        rows = [_Row("", rid="x"), _Row("", rid="y"), _Row("  ", rid="z")]
        assert len(dedupe_item_rows(rows)) == 3

    def test_두_모집단이_같은_실행에서_갈린다(self):
        """★남아야 할 것이 남고, 접혀야 할 것이 접히는지 **한 번에** 본다."""
        rows = [
            _Row("A", rid="1"), _Row("A", rid="2"),   # 접힌다 → 1
            _Row("", rid="3"), _Row("", rid="4"),      # 남는다 → 2
        ]
        out = dedupe_item_rows(rows)
        assert len(out) == 3, [(r.pnu, r.id) for r in out]
        assert sum(1 for r in out if not r.pnu.strip()) == 2
        assert sum(1 for r in out if r.pnu == "A") == 1


class Test상태우선순위가전수로잠긴다:
    """★초판은 `not_found` vs `confirmed` **한 쌍만** 태워서, 인접 순위를 뒤집는 변이가
    **생존**했다(적대 리뷰 M1). 목록형 상태표는 값이 늘면 조용히 최하위가 된다(M2).
    """

    def test_상태표가_ItemStatus_전수를_덮는다(self):
        """★**파생형 정합** — 상태가 하나 늘면 여기서 빨개진다(조용히 지지 않는다)."""
        from apps.api.app.foundation.parcel.batch.job_store import _STATUS_RANK
        from apps.api.app.foundation.parcel.contracts.batch import ItemStatus

        assert set(_STATUS_RANK) == {s.value for s in ItemStatus}
        assert len(set(_STATUS_RANK.values())) == len(_STATUS_RANK), "순위가 겹치면 결정성이 깨진다"

    @pytest.mark.parametrize(
        ("higher", "lower"),
        [("confirmed", "ambiguous"), ("ambiguous", "not_found"), ("not_found", "error")],
    )
    def test_인접한_두_상태가_각각_갈린다(self, higher, lower):
        """★**인접 쌍 전부**를 태운다 — 한 쌍만 태우면 나머지 순위는 무잠금이다."""
        rows = [_Row("A", lower, rid="z"), _Row("A", higher, rid="a")]
        # ★`rid` 를 반대로 줘서 **상태만이 유일하게 답을 가르게** 한다.
        assert dedupe_item_rows(rows)[0].status == higher
        assert dedupe_item_rows(list(reversed(rows)))[0].status == higher

    def test_모르는_상태는_알려진_어떤_상태에도_진다(self):
        """★목록 밖 상태가 **최상위로 올라가면** 알 수 없는 값이 필지를 대표하게 된다."""
        rows = [_Row("A", "zzz_알수없는상태", rid="z"), _Row("A", "error", rid="a")]
        assert dedupe_item_rows(rows)[0].status == "error"


class Test공백만있는PNU도판정불가다:
    """★초판 픽스처는 `"  "` 하나뿐이라 `.strip()` 을 지워도 결과가 같았다(리뷰 M4 SURVIVED)
    — **두 모집단을 안 가르는 픽스처**의 교과서적 형태다.
    """

    def test_같은_공백문자열_두_행이_접히지_않는다(self):
        """★**이 입력만이 `.strip()` 축을 가른다.**

        표기가 *다른* 공백(`"  "` vs `" "`)은 strip 이 없어도 **서로 다른 키**가 되어
        우연히 3건이 나온다 — 개수로도 id 로도 못 가른다(리뷰 M4 가 생존한 이유).
        **같은** 공백 문자열 둘이어야 strip 없는 구현이 **한 건으로 접는다.**
        """
        rows = [_Row("  ", rid="x"), _Row("  ", rid="y")]
        out = dedupe_item_rows(rows)
        assert {r.id for r in out} == {"x", "y"}, (
            "공백만 있는 PNU 는 **판정 불가**다 — 같은 공백이라도 같은 필지라는 근거가 없다"
        )

    def test_공백_표기가_다른_두_행도_각각_남는다(self):
        rows = [_Row("  ", rid="x"), _Row(" ", rid="y"), _Row("\t", rid="z")]
        assert {r.id for r in dedupe_item_rows(rows)} == {"x", "y", "z"}

    def test_공백_PNU_는_유효_PNU_와_섞이지_않는다(self):
        rows = [_Row(" ", rid="x"), _Row("A", rid="y"), _Row("A", rid="z")]
        out = dedupe_item_rows(rows)
        assert len(out) == 2 and {r.pnu for r in out} == {" ", "A"}


class Test출력순서가고정된다:
    """★리뷰 M3: `list(best.values()) + passthrough` 를 뒤집어도 초록이었다.
    `result()` 가 `record.items[start:end]` 로 페이지를 자르므로 **순서는 사용자에게 닿는다.**
    """

    def test_판정된_행이_먼저_판정불가가_뒤에_온다(self):
        rows = [_Row("", rid="1"), _Row("A", rid="2"), _Row("", rid="3"), _Row("B", rid="4")]
        out = dedupe_item_rows(rows)
        assert [r.pnu for r in out] == ["A", "B", "", ""], "PNU 있는 행이 앞, 판정불가가 뒤"

    def test_같은_입력이면_항상_같은_순서다(self):
        rows = [_Row("B", rid="1"), _Row("A", rid="2"), _Row("B", rid="3")]
        assert [r.id for r in dedupe_item_rows(rows)] == [r.id for r in dedupe_item_rows(rows)]


class Test쓰기왕복은의도적으로정리한다:
    """★★초판이 *"데이터를 지우지 않는다"* 라고 **거짓 선언**한 자리다(적대 리뷰 MAJOR-1).

    `save()` 는 `job_id` 의 행을 **전부 DELETE 한 뒤 `record.items` 를 재삽입**한다.
    따라서 접힌 뒤 저장이 일어나면 중복 행은 **영구히 사라진다** — 그것을 **의도로 승격**하고
    여기서 잠근다. 선언만 고치고 락이 없으면 다음 사람이 또 「지우지 않는다」로 되돌린다.
    """

    def test_save_는_record_items_만_다시_넣는다_계약을_읽는다(self):
        """★소스가 아니라 **행위**로 확인한다 — 가짜 세션에 실제 `save()` 를 태운다."""
        import asyncio

        from apps.api.app.foundation.parcel.batch.job_store import DbJobStore

        inserted: list[Any] = []
        deleted: list[Any] = []

        class _Res:
            @staticmethod
            def scalar_one_or_none(): return None

        class _Sess:
            async def flush(self): return None
            async def execute(self, stmt):
                deleted.append(stmt)
                return _Res()
            def add(self, o): inserted.append(o)
            async def commit(self): return None
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False

        rows = [_Row("A", rid="x"), _Row("A", rid="y"), _Row("B", rid="z")]

        class _J:
            id = "j9"; snapshot_id = "s"; state = "complete"
            region_input: dict = {}; completeness = "complete"
            counts = {"total": 3, "confirmed": 3}

        store = DbJobStore.__new__(DbJobStore)
        rec = store._to_record(_J(), rows, None)
        assert len(rec.items) == 2, "전제: 읽으면서 접힌다"

        # ★`_sf()()` 로 세션을 얻는다 — 팩토리를 반환하는 팩토리다.
        store._session_factory = lambda: _Sess()   # type: ignore[attr-defined]
        # ★예외를 **삼키지 않는다** — 초판은 `except Exception: pass` 로 감싸서
        #   스텁이 `save()` 를 중간에 터뜨린 것을 「재삽입 0건」으로 보이게 했다.
        #   무성 실패를 만드는 락은 락이 아니다.
        asyncio.run(store.save(rec))

        # ★핵심: 삭제는 **일어난다**(중복행 정리) — 그리고 다시 들어가는 것은 **접힌 2건**이다.
        assert deleted, "save() 가 기존 행을 지우지 않는다면 이 설계 설명이 틀린 것이다"
        pnus = [getattr(o, "pnu", None) for o in inserted if hasattr(o, "pnu")]
        assert sorted(x for x in pnus if x) == ["A", "B"], f"재삽입된 행: {pnus}"


class Test조용히지우지않는다:
    """★`save()` 가 원본 행을 **영구 삭제**하므로, 접힘은 **로그로 남아야** 한다.

    계획서가 *"9건 전부가 같은 기전인지는 미측정"* 이라고 적어 둔 조사의 **유일한 증거**다.
    ★이 락이 없으면 「조용히 지우지 않는다」는 **주석에만 있는 주장**이 된다
    (선언 자체가 검증 대상이다 — 적대 리뷰가 그 자리를 짚었다).
    """

    def test_접히면_경고를_남긴다_수치와_함께(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="app.foundation.parcel.batch.job_store"):
            dedupe_item_rows([_Row("A", rid="x"), _Row("A", rid="y"), _Row("B", rid="z")])
        recs = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert recs, "접었는데 아무 흔적도 안 남기면 근본원인 조사가 불가능해진다"
        # ★문구가 아니라 **수치**를 단언한다(산문은 다듬을 때마다 깨지는 취약한 락이다).
        msg = recs[0].getMessage()
        assert "3" in msg and "2" in msg, f"원본/잔존 행수가 안 실렸다: {msg}"

    def test_대조군_접힐_것이_없으면_경고하지_않는다(self, caplog):
        """★「항상 경고하는」 구현과 구별한다 — 상시 경고는 곧 무시된다."""
        import logging

        with caplog.at_level(logging.WARNING, logger="app.foundation.parcel.batch.job_store"):
            dedupe_item_rows([_Row("A", rid="x"), _Row("B", rid="y")])
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
