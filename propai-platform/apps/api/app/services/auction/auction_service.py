"""경·공매(온비드 공매 + 법원경매 스크래핑) 전국 연동 서비스 — 무목업.

멱등 _ensure 테이블(auction_items / auction_saved_filters / auction_watch)을 lazy 생성하고,
온비드(공매)·법원경매(스크래핑) 동기화·조건검색·순위·저장조건 CRUD·내토지매칭을 처리한다.
analysis_ledger / cost_estimate 와 동일한 raw SQL + text() + _ensure 패턴을 따른다.

★정직성(무목업): 응답에 data_source(onbid_live|court_scrape|unavailable) 표기. 키 미설정/
호출실패/무자료/스크래핑 불가 시 ★가짜데이터를 만들지 않고 빈 결과 + reason 을 반환한다.
est_win은 추정·가정 명시. 저장조건/watch는 user_id 격리. public_data_registry로 신선도 기록.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auction.court_scraper import CourtAuctionScraper
from app.services.auction.onbid_client import OnbidClient
from app.services.auction.win_estimator import estimate_win_price

logger = logging.getLogger(__name__)


_DDL = [
    # 전국 공매(+확장: 경매) 물건 캐시.
    """
    CREATE TABLE IF NOT EXISTS auction_items (
        id              BIGSERIAL PRIMARY KEY,
        source          TEXT NOT NULL DEFAULT 'onbid',
        item_no         TEXT NOT NULL,
        kind            TEXT,
        region_sido     TEXT,
        region_sigungu  TEXT,
        bjd_code        TEXT,
        pnu             TEXT,
        address         TEXT,
        appraisal_price BIGINT,
        min_bid_price   BIGINT,
        fail_count      INTEGER DEFAULT 0,
        status          TEXT,
        bid_start       TIMESTAMP,
        bid_end         TIMESTAMP,
        data_source     TEXT,
        raw             JSONB,
        fetched_at      TIMESTAMP DEFAULT now(),
        UNIQUE (source, item_no)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_auction_items_region ON auction_items(region_sido)",
    "CREATE INDEX IF NOT EXISTS ix_auction_items_kind ON auction_items(kind)",
    "CREATE INDEX IF NOT EXISTS ix_auction_items_pnu ON auction_items(pnu)",
    "CREATE INDEX IF NOT EXISTS ix_auction_items_minbid ON auction_items(min_bid_price)",
    # 사용자별 저장 조건(알림 대상).
    """
    CREATE TABLE IF NOT EXISTS auction_saved_filters (
        id          BIGSERIAL PRIMARY KEY,
        user_id     TEXT NOT NULL,
        name        TEXT,
        conditions  JSONB NOT NULL DEFAULT '{}'::jsonb,
        notify      BOOLEAN DEFAULT false,
        created_at  TIMESTAMP DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_auction_filters_user ON auction_saved_filters(user_id)",
    # 내토지 ↔ 물건 연결(관심/매칭).
    """
    CREATE TABLE IF NOT EXISTS auction_watch (
        id              BIGSERIAL PRIMARY KEY,
        user_id         TEXT NOT NULL,
        project_id      TEXT,
        pnu             TEXT,
        auction_item_id BIGINT,
        source          TEXT DEFAULT 'onbid',
        created_at      TIMESTAMP DEFAULT now(),
        UNIQUE (user_id, auction_item_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_auction_watch_user ON auction_watch(user_id)",
    "CREATE INDEX IF NOT EXISTS ix_auction_watch_project ON auction_watch(project_id)",
]


class AuctionStep1Service:
    """경·공매 1단계(온비드 공매 전국연동) 비즈니스 로직."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_tables(self) -> None:
        """멱등 테이블·인덱스 생성(lazy)."""
        for stmt in _DDL:
            await self.db.execute(text(stmt))
        await self.db.commit()

    # ──────────────────────────────────────────
    # 동기화(온비드 → auction_items upsert)
    # ──────────────────────────────────────────

    async def sync_region(
        self, *, service_key: Optional[str], region: Optional[str] = None,
        kind: Optional[str] = None, rows: int = 50, source: str = "onbid",
    ) -> dict[str, Any]:
        """공매(온비드) 또는 경매(법원 스크래핑)를 조회해 auction_items에 멱등 upsert.

        source="onbid" → 온비드 실 API(무목업). source="court" → 법원경매 스크래핑
        (지연·예의 적용, 무목업). 무자료/실패 시 가짜 없이 빈 결과 + reason 반환.
        """
        await self.ensure_tables()
        if source == "court":
            result = await self._fetch_court(region=region, kind=kind)
        else:
            client = OnbidClient(service_key)
            try:
                result = await client.fetch_items(region=region, kind=kind, rows=rows)
            finally:
                await client.close()

        items = result.get("items", [])
        data_source = result.get("data_source", "unavailable")
        healthy_sources = {"onbid_live", "court_scrape"}
        saved = await self._upsert_items(items, data_source) if items else 0

        self._mark_registry(
            source=source, record_count=saved,
            healthy=(data_source in healthy_sources),
            reason=result.get("reason"),
        )
        return {
            "source": source,
            "data_source": data_source,
            "fetched": len(items),
            "saved": saved,
            "note": result.get("note"),
            "reason": result.get("reason"),
        }

    async def _fetch_court(
        self, *, region: Optional[str], kind: Optional[str],
    ) -> dict[str, Any]:
        """법원경매 스크래핑(동기 requests)을 스레드 오프로드해 호출한다(무목업)."""
        import asyncio

        scraper = CourtAuctionScraper()
        return await asyncio.to_thread(
            scraper.fetch_items, region=region, kind=kind,
        )

    async def _upsert_items(self, items: list[dict[str, Any]], data_source: str) -> int:
        """정규화 물건 리스트를 UNIQUE(source,item_no) 기준 멱등 upsert."""
        sql = text(
            "INSERT INTO auction_items"
            " (source,item_no,kind,region_sido,region_sigungu,bjd_code,pnu,address,"
            "  appraisal_price,min_bid_price,fail_count,status,bid_start,bid_end,"
            "  data_source,raw,fetched_at)"
            " VALUES (:source,:item_no,:kind,:sido,:sgg,:bjd,:pnu,:address,"
            "  :appraisal,:minbid,:fail,:status,"
            "  CAST(:bid_start AS TIMESTAMP),CAST(:bid_end AS TIMESTAMP),"
            "  :data_source,CAST(:raw AS JSONB),now())"
            " ON CONFLICT (source,item_no) DO UPDATE SET"
            "  kind=EXCLUDED.kind,region_sido=EXCLUDED.region_sido,"
            "  region_sigungu=EXCLUDED.region_sigungu,bjd_code=EXCLUDED.bjd_code,"
            "  pnu=EXCLUDED.pnu,address=EXCLUDED.address,"
            "  appraisal_price=EXCLUDED.appraisal_price,min_bid_price=EXCLUDED.min_bid_price,"
            "  fail_count=EXCLUDED.fail_count,status=EXCLUDED.status,"
            "  bid_start=EXCLUDED.bid_start,bid_end=EXCLUDED.bid_end,"
            "  data_source=EXCLUDED.data_source,raw=EXCLUDED.raw,fetched_at=now()"
        )
        saved = 0
        for it in items:
            item_no = str(it.get("item_no") or "")
            if not item_no:
                continue
            await self.db.execute(sql, {
                "source": it.get("source", "onbid"),
                "item_no": item_no,
                "kind": it.get("kind"),
                "sido": it.get("region_sido"),
                "sgg": it.get("region_sigungu"),
                "bjd": it.get("bjd_code"),
                "pnu": it.get("pnu") or None,
                "address": it.get("address"),
                "appraisal": it.get("appraisal_price"),
                "minbid": it.get("min_bid_price"),
                # ★물건목록 미연동 시 유찰횟수는 None(가짜 0 금지). court는 실값.
                "fail": it.get("fail_count"),
                "status": it.get("status"),
                "bid_start": it.get("bid_start"),
                "bid_end": it.get("bid_end"),
                "data_source": data_source,
                "raw": json.dumps(it.get("raw", {}), ensure_ascii=False, default=str),
            })
            saved += 1
        await self.db.commit()
        return saved

    # ──────────────────────────────────────────
    # 조건검색 / 순위
    # ──────────────────────────────────────────

    async def search(
        self, *, region: Optional[str] = None, kind: Optional[str] = None,
        min_fail: Optional[int] = None, max_price: Optional[int] = None,
        est_win_max: Optional[int] = None, page: int = 1, page_size: int = 20,
        service_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """캐시 기반 조건검색. 결과가 비면 온비드 동기화 후 재조회한다."""
        await self.ensure_tables()
        rows, total, data_source = await self._query_items(
            region=region, kind=kind, min_fail=min_fail, max_price=max_price,
            page=page, page_size=page_size,
        )
        if total == 0:
            sync = await self.sync_region(service_key=service_key, region=region, kind=kind)
            data_source = sync.get("data_source", "unavailable")
            rows, total, _ = await self._query_items(
                region=region, kind=kind, min_fail=min_fail, max_price=max_price,
                page=page, page_size=page_size,
            )

        enriched = [self._attach_est_win(r) for r in rows]
        if est_win_max is not None:
            # ★감정가 미연동 물건은 est_win_mid=None → 필터 통과시키지 않음(정직).
            enriched = [
                e for e in enriched
                if e["est_win"].get("est_win_mid") is not None
                and e["est_win"]["est_win_mid"] <= est_win_max
            ]
        result: dict[str, Any] = {
            "items": enriched,
            "total": total,
            "page": page,
            "page_size": page_size,
            "data_source": data_source,
        }
        # ★온비드 공고목록은 현재 감정가/최저입찰가/유찰횟수 미연동(가짜 금지) — 정직 안내.
        if enriched and any(
            e.get("source") == "onbid" and e.get("appraisal_price") is None
            for e in enriched
        ):
            result["price_note"] = (
                "온비드 공고목록 기반(감정가·최저입찰가·유찰횟수는 물건목록 엔드포인트"
                " 연동 후 제공). 현재는 공고·주소·입찰기간·개찰일시만 실연동."
            )
        return result

    async def ranking(
        self, *, region: Optional[str] = None, kind: Optional[str] = None,
        by: str = "min_bid", limit: int = 20,
    ) -> dict[str, Any]:
        """전국 최저입찰가/할인율 순위."""
        await self.ensure_tables()
        conditions = ["min_bid_price IS NOT NULL", "min_bid_price > 0"]
        params: dict[str, Any] = {"limit": limit}
        if region:
            conditions.append("region_sido = :region")
            params["region"] = region
        if kind:
            conditions.append("kind = :kind")
            params["kind"] = kind
        where = " AND ".join(conditions)

        if by == "discount_rate":
            # 할인율 = 1 - 최저입찰가/감정가 (감정가>0). 큰 순.
            order = "(1.0 - min_bid_price::float / NULLIF(appraisal_price,0)) DESC NULLS LAST"
            conditions.append("appraisal_price IS NOT NULL AND appraisal_price > 0")
            where = " AND ".join(conditions)
        else:
            order = "min_bid_price ASC"

        sql = text(
            "SELECT id,source,item_no,kind,region_sido,region_sigungu,pnu,address,"
            " appraisal_price,min_bid_price,fail_count,status,bid_start,bid_end,data_source"
            f" FROM auction_items WHERE {where} ORDER BY {order} LIMIT :limit"
        )
        result = await self.db.execute(sql, params)
        rows = [self._row_to_dict(r) for r in result.mappings().all()]
        enriched = [self._attach_est_win(r) for r in rows]
        for e in enriched:
            ap = e.get("appraisal_price")
            mb = e.get("min_bid_price")
            e["discount_rate"] = (
                round((1.0 - mb / ap) * 100, 1) if ap and mb else None
            )
        out: dict[str, Any] = {"items": enriched, "by": by, "total": len(enriched)}
        if not enriched:
            # ★온비드 공고목록엔 최저입찰가/감정가 미연동 → 순위 데이터 없을 수 있음(정직).
            out["note"] = (
                "최저입찰가/감정가 데이터가 있는 물건이 없습니다. 온비드 부동산"
                " 물건목록 엔드포인트 연동 후 순위가 채워집니다(현재 공고목록만 실연동)."
            )
        return out

    async def get_item(self, item_id: int) -> Optional[dict[str, Any]]:
        """물건 상세(+raw +est_win)."""
        await self.ensure_tables()
        sql = text(
            "SELECT id,source,item_no,kind,region_sido,region_sigungu,bjd_code,pnu,address,"
            " appraisal_price,min_bid_price,fail_count,status,bid_start,bid_end,data_source,raw"
            " FROM auction_items WHERE id = :id"
        )
        row = (await self.db.execute(sql, {"id": item_id})).mappings().first()
        if not row:
            return None
        d = self._row_to_dict(row)
        d["raw"] = row.get("raw")
        return self._attach_est_win(d)

    async def _query_items(
        self, *, region, kind, min_fail, max_price, page, page_size,
    ) -> tuple[list[dict[str, Any]], int, str]:
        conditions: list[str] = []
        params: dict[str, Any] = {}
        if region:
            conditions.append("region_sido = :region")
            params["region"] = region
        if kind:
            conditions.append("kind = :kind")
            params["kind"] = kind
        if min_fail is not None:
            conditions.append("fail_count >= :min_fail")
            params["min_fail"] = min_fail
        if max_price is not None:
            conditions.append("min_bid_price <= :max_price")
            params["max_price"] = max_price
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        total = (await self.db.execute(
            text(f"SELECT count(*) FROM auction_items{where}"), params
        )).scalar() or 0

        params["limit"] = page_size
        params["offset"] = (page - 1) * page_size
        sql = text(
            "SELECT id,source,item_no,kind,region_sido,region_sigungu,pnu,address,"
            " appraisal_price,min_bid_price,fail_count,status,bid_start,bid_end,data_source"
            f" FROM auction_items{where}"
            " ORDER BY fetched_at DESC, id DESC LIMIT :limit OFFSET :offset"
        )
        result = await self.db.execute(sql, params)
        rows = [self._row_to_dict(r) for r in result.mappings().all()]
        data_source = rows[0]["data_source"] if rows else "unavailable"
        return rows, total, data_source

    # ──────────────────────────────────────────
    # 저장 조건 CRUD (user_id 격리)
    # ──────────────────────────────────────────

    async def create_filter(
        self, *, user_id: str, name: str, conditions: dict[str, Any], notify: bool = False,
    ) -> dict[str, Any]:
        await self.ensure_tables()
        row = (await self.db.execute(text(
            "INSERT INTO auction_saved_filters(user_id,name,conditions,notify)"
            " VALUES (:uid,:name,CAST(:cond AS JSONB),:notify) RETURNING id,created_at"
        ), {
            "uid": user_id, "name": name,
            "cond": json.dumps(conditions or {}, ensure_ascii=False, default=str),
            "notify": notify,
        })).first()
        await self.db.commit()
        return {
            "id": row[0], "user_id": user_id, "name": name,
            "conditions": conditions or {}, "notify": notify,
            "created_at": self._iso(row[1]),
        }

    async def list_filters(self, *, user_id: str) -> list[dict[str, Any]]:
        await self.ensure_tables()
        result = await self.db.execute(text(
            "SELECT id,name,conditions,notify,created_at FROM auction_saved_filters"
            " WHERE user_id = :uid ORDER BY created_at DESC"
        ), {"uid": user_id})
        return [{
            "id": r["id"], "name": r["name"], "conditions": r["conditions"] or {},
            "notify": r["notify"],
            "created_at": self._iso(r["created_at"]),
        } for r in result.mappings().all()]

    async def delete_filter(self, *, user_id: str, filter_id: int) -> bool:
        await self.ensure_tables()
        result = await self.db.execute(text(
            "DELETE FROM auction_saved_filters WHERE id = :id AND user_id = :uid"
        ), {"id": filter_id, "uid": user_id})
        await self.db.commit()
        return (result.rowcount or 0) > 0

    # ──────────────────────────────────────────
    # 내 관리토지 매칭 (프로젝트/토지조서 PNU ∩ 물건 PNU)
    # ──────────────────────────────────────────

    async def match_my_land(self, *, user_id: str, tenant_id: Optional[str]) -> int:
        """내 프로젝트/토지조서 PNU와 일치하는 공매 물건을 auction_watch에 자동 등록.

        반환: 신규 매칭 건수. 알림훅은 notify_match로 기록(키 없으면 로깅).
        """
        await self.ensure_tables()
        pnus = await self._my_pnus(tenant_id)
        if not pnus:
            return 0
        # 일치 물건 조회.
        result = await self.db.execute(text(
            "SELECT id,pnu,source,address FROM auction_items"
            " WHERE pnu = ANY(:pnus)"
        ), {"pnus": list(pnus)})
        matched = result.mappings().all()
        created = 0
        for m in matched:
            ins = await self.db.execute(text(
                "INSERT INTO auction_watch(user_id,pnu,auction_item_id,source)"
                " VALUES (:uid,:pnu,:aid,:src)"
                " ON CONFLICT (user_id,auction_item_id) DO NOTHING RETURNING id"
            ), {"uid": user_id, "pnu": m["pnu"], "aid": m["id"], "src": m["source"]})
            if ins.first():
                created += 1
                self._notify_match(user_id, m["address"])
        await self.db.commit()
        return created

    async def my_listings(
        self, *, user_id: str, tenant_id: Optional[str], group_by: str = "project",
    ) -> dict[str, Any]:
        """내 관리토지 중 경공매 연동분. 자동매칭 후 프로젝트별 분류 + 통합 반환."""
        await self.ensure_tables()
        await self.match_my_land(user_id=user_id, tenant_id=tenant_id)

        # watch ⋈ items, 그리고 PNU→project 매핑.
        result = await self.db.execute(text(
            "SELECT w.id AS watch_id, w.project_id, i.id AS item_id, i.source, i.item_no,"
            " i.kind, i.region_sido, i.region_sigungu, i.pnu, i.address,"
            " i.appraisal_price, i.min_bid_price, i.fail_count, i.status,"
            " i.bid_start, i.bid_end, i.data_source"
            " FROM auction_watch w JOIN auction_items i ON i.id = w.auction_item_id"
            " WHERE w.user_id = :uid ORDER BY i.bid_end NULLS LAST"
        ), {"uid": user_id})
        rows = [self._row_to_dict(r, id_key="item_id") for r in result.mappings().all()]
        enriched = [self._attach_est_win(r) for r in rows]
        # PNU→project_id 보강.
        pnu_to_proj = await self._pnu_project_map(tenant_id)
        for e in enriched:
            if not e.get("project_id"):
                e["project_id"] = pnu_to_proj.get(e.get("pnu") or "")

        unified = enriched
        if group_by == "project":
            groups: dict[str, list[dict[str, Any]]] = {}
            for e in enriched:
                key = e.get("project_id") or "_unassigned"
                groups.setdefault(key, []).append(e)
            return {
                "group_by": "project",
                "projects": [
                    {"project_id": (None if k == "_unassigned" else k), "items": v}
                    for k, v in groups.items()
                ],
                "unified": unified,
                "total": len(unified),
            }
        return {"group_by": "none", "unified": unified, "total": len(unified)}

    async def _my_pnus(self, tenant_id: Optional[str]) -> set[str]:
        """내 테넌트의 프로젝트(pnu_codes JSON) + parcels.pnu 집합."""
        pnus: set[str] = set()
        if not tenant_id:
            return pnus
        try:
            proj = await self.db.execute(text(
                "SELECT pnu_codes FROM projects WHERE tenant_id = CAST(:tid AS uuid)"
                " AND (is_deleted = false OR is_deleted IS NULL)"
            ), {"tid": tenant_id})
            for r in proj.mappings().all():
                codes = r.get("pnu_codes")
                if isinstance(codes, dict):
                    codes = codes.get("codes") or list(codes.values())
                if isinstance(codes, list):
                    pnus.update(str(c) for c in codes if c)
        except Exception as e:  # noqa: BLE001
            logger.warning("projects PNU 조회 실패: %s", str(e)[:120])
        try:
            par = await self.db.execute(text(
                "SELECT pnu FROM parcels WHERE tenant_id = CAST(:tid AS uuid) AND pnu IS NOT NULL"
            ), {"tid": tenant_id})
            pnus.update(str(r[0]) for r in par.all() if r[0])
        except Exception as e:  # noqa: BLE001
            logger.warning("parcels PNU 조회 실패: %s", str(e)[:120])
        return pnus

    async def _pnu_project_map(self, tenant_id: Optional[str]) -> dict[str, str]:
        """PNU → project_id 매핑(parcels 기준)."""
        mapping: dict[str, str] = {}
        if not tenant_id:
            return mapping
        try:
            par = await self.db.execute(text(
                "SELECT pnu, project_id FROM parcels"
                " WHERE tenant_id = CAST(:tid AS uuid) AND pnu IS NOT NULL"
            ), {"tid": tenant_id})
            for r in par.mappings().all():
                if r.get("pnu"):
                    mapping[str(r["pnu"])] = str(r["project_id"])
        except Exception as e:  # noqa: BLE001
            logger.warning("PNU→project 매핑 조회 실패: %s", str(e)[:120])
        return mapping

    # ──────────────────────────────────────────
    # 헬퍼
    # ──────────────────────────────────────────

    @staticmethod
    def _iso(v: Any) -> Optional[str]:
        """datetime(Postgres) / str(드라이버 차이) 모두 ISO 문자열로 정규화."""
        if v is None:
            return None
        return v.isoformat() if hasattr(v, "isoformat") else str(v)

    @staticmethod
    def _row_to_dict(r, id_key: str = "id") -> dict[str, Any]:
        return {
            "id": r.get(id_key),
            "project_id": r.get("project_id"),
            "source": r.get("source"),
            "item_no": r.get("item_no"),
            "kind": r.get("kind"),
            "region_sido": r.get("region_sido"),
            "region_sigungu": r.get("region_sigungu"),
            "pnu": r.get("pnu"),
            "address": r.get("address"),
            "appraisal_price": r.get("appraisal_price"),
            "min_bid_price": r.get("min_bid_price"),
            "fail_count": r.get("fail_count"),
            "status": r.get("status"),
            "bid_start": AuctionStep1Service._iso(r.get("bid_start")),
            "bid_end": AuctionStep1Service._iso(r.get("bid_end")),
            "data_source": r.get("data_source"),
        }

    @staticmethod
    def _attach_est_win(d: dict[str, Any]) -> dict[str, Any]:
        d["est_win"] = estimate_win_price(
            appraisal_price=d.get("appraisal_price"),
            min_bid_price=d.get("min_bid_price"),
            kind=d.get("kind") or "etc",
            region_sido=d.get("region_sido"),
            fail_count=d.get("fail_count") or 0,
        )
        return d

    @staticmethod
    def _notify_match(user_id: str, address: Optional[str]) -> None:
        """내토지 매칭 알림훅. 푸시키 없으면 로그로 기록(정직)."""
        logger.info("[auction] 내토지 경공매 매칭 user=%s addr=%s (알림훅 기록)",
                    user_id, address or "")

    @staticmethod
    def _mark_registry(
        *, source: str = "onbid", record_count: int = 0, healthy: bool,
        reason: Optional[str] = None,
    ) -> None:
        try:
            from app.services.data_validation.public_data_registry import PublicDataRegistry
            reg = PublicDataRegistry.get_instance()
            key = "court_auction" if source == "court" else "onbid_auction"
            src = reg.sources.get(key)
            if src is None:
                from app.services.data_validation.public_data_registry import DataSourceStatus
                kind = "scrape" if source == "court" else "api"
                src = DataSourceStatus(key, kind, "daily")
                reg.sources[key] = src
            if healthy:
                src.mark_updated(record_count)
            else:
                src.mark_error(reason or "수집 불가(무목업, 빈 결과)")
        except Exception:  # noqa: BLE001
            pass
