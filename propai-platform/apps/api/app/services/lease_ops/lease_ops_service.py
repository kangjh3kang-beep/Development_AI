"""임대·임차인 운영(LeaseOps) 서비스 — 임차인/임대계약 CRUD + 공실률·임대수익 집계.

DB 전략(CM·원장과 동일): Alembic 불사용. 프로덕션 DB는 런타임 생성 패턴(alembic_version 없음)이라
analysis_ledger_service._ensure / cost_tables_bootstrap 패턴을 그대로 따른다:
 - CREATE TABLE IF NOT EXISTS 로 tenants / lease_contracts 를 멱등 생성(기존 데이터 무영향).
 - 라우터 첫 사용 시 lazy 호출(_ensure) → 배포되면 자동 생성, 수동 마이그레이션 불필요.

멀티테넌트 격리: 모든 조회/집계/변경은 tenant_id(JWT) 스코프로 강제한다(교차 테넌트 차단).
정직성: 데이터 없으면 0/빈배열을 그대로 반환(추정·하드코딩 금지). 멱등·안전(IF NOT EXISTS).
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# 활성(임대중) 상태 — 점유/수익 집계 대상.
ACTIVE_STATUSES = ("active", "occupied", "leased")
# 허용 계약 상태(입력검증·상태변경 화이트리스트).
VALID_STATUSES = ("draft", "active", "occupied", "leased", "vacant", "expired", "terminated")

# ── DDL: 임차인 ──
_DDL_TENANTS = (
    "CREATE TABLE IF NOT EXISTS tenants ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  tenant_id text NOT NULL,"
    "  project_id text,"
    "  name varchar(300) NOT NULL,"
    "  contact varchar(200),"
    "  business_type varchar(150),"
    "  notes text,"
    "  created_at timestamptz DEFAULT now(),"
    "  updated_at timestamptz DEFAULT now()"
    ")"
)
# ── DDL: 임대계약 ──
_DDL_CONTRACTS = (
    "CREATE TABLE IF NOT EXISTS lease_contracts ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  tenant_id text NOT NULL,"
    "  project_id text,"
    "  unit_label varchar(150) NOT NULL,"
    "  lessee uuid,"
    "  deposit numeric(20,2) DEFAULT 0,"
    "  monthly_rent numeric(20,2) DEFAULT 0,"
    "  start_date date,"
    "  end_date date,"
    "  status varchar(30) NOT NULL DEFAULT 'active',"
    "  area_sqm numeric(18,2) DEFAULT 0,"
    "  notes text,"
    "  created_at timestamptz DEFAULT now(),"
    "  updated_at timestamptz DEFAULT now()"
    ")"
)
_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_tenants_scope "
    "ON tenants(tenant_id, project_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_lease_contracts_scope "
    "ON lease_contracts(tenant_id, project_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_lease_contracts_lessee "
    "ON lease_contracts(lessee)",
)


class LeaseOpsService:
    """임차인·임대계약 CRUD 및 공실률/임대수익 집계."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure(self) -> None:
        await self.db.execute(text(_DDL_TENANTS))
        await self.db.execute(text(_DDL_CONTRACTS))
        for ix in _IDX:
            await self.db.execute(text(ix))

    # ── 임차인 ──
    async def create_tenant(
        self,
        *,
        tenant_id: str,
        name: str,
        contact: str | None = None,
        business_type: str | None = None,
        project_id: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        await self._ensure()
        row = (await self.db.execute(text(
            "INSERT INTO tenants(tenant_id, project_id, name, contact, business_type, notes) "
            "VALUES (:tid, :pid, :name, :contact, :btype, :notes) RETURNING id"),
            {"tid": tenant_id, "pid": project_id, "name": name,
             "contact": contact, "btype": business_type, "notes": notes})).first()
        await self.db.commit()
        return {"ok": True, "id": str(row[0])}

    async def list_tenants(
        self, *, tenant_id: str, project_id: str | None = None
    ) -> dict[str, Any]:
        await self._ensure()
        sql = ("SELECT id, name, contact, business_type FROM tenants "
               "WHERE tenant_id = :tid")
        params: dict[str, Any] = {"tid": tenant_id}
        if project_id:
            sql += " AND project_id = :pid"
            params["pid"] = project_id
        sql += " ORDER BY created_at DESC"
        rows = (await self.db.execute(text(sql), params)).fetchall()
        tenants = [
            {"id": str(r[0]), "name": r[1], "contact": r[2], "business_type": r[3]}
            for r in rows
        ]
        return {"ok": True, "tenants": tenants}

    # ── 임대계약 ──
    async def create_contract(
        self,
        *,
        tenant_id: str,
        unit_label: str,
        lessee: str | None = None,
        deposit: float = 0.0,
        monthly_rent: float = 0.0,
        start_date: str | None = None,
        end_date: str | None = None,
        status: str = "active",
        area_sqm: float = 0.0,
        project_id: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        await self._ensure()
        status = status if status in VALID_STATUSES else "active"
        row = (await self.db.execute(text(
            "INSERT INTO lease_contracts"
            "(tenant_id, project_id, unit_label, lessee, deposit, monthly_rent,"
            " start_date, end_date, status, area_sqm, notes) "
            "VALUES (:tid, :pid, :unit, :lessee, :deposit, :rent,"
            " :sdate, :edate, :status, :area, :notes) RETURNING id"),
            {"tid": tenant_id, "pid": project_id, "unit": unit_label,
             "lessee": lessee, "deposit": deposit, "rent": monthly_rent,
             "sdate": start_date or None, "edate": end_date or None,
             "status": status, "area": area_sqm, "notes": notes})).first()
        await self.db.commit()
        return {"ok": True, "id": str(row[0])}

    async def list_contracts(
        self,
        *,
        tenant_id: str,
        project_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        await self._ensure()
        sql = (
            "SELECT c.id, c.unit_label, t.name, c.deposit, c.monthly_rent,"
            " c.start_date, c.end_date, c.status, c.area_sqm "
            "FROM lease_contracts c LEFT JOIN tenants t ON t.id = c.lessee "
            "WHERE c.tenant_id = :tid"
        )
        params: dict[str, Any] = {"tid": tenant_id}
        if project_id:
            sql += " AND c.project_id = :pid"
            params["pid"] = project_id
        if status:
            sql += " AND c.status = :status"
            params["status"] = status
        sql += " ORDER BY c.created_at DESC"
        rows = (await self.db.execute(text(sql), params)).fetchall()
        contracts = [
            {
                "id": str(r[0]),
                "unit_label": r[1],
                "lessee_name": r[2],
                "deposit": float(r[3] or 0),
                "monthly_rent": float(r[4] or 0),
                "start_date": r[5].isoformat() if r[5] else None,
                "end_date": r[6].isoformat() if r[6] else None,
                "status": r[7],
                "area_sqm": float(r[8] or 0),
            }
            for r in rows
        ]
        return {"ok": True, "contracts": contracts}

    async def update_status(
        self, *, tenant_id: str, contract_id: str, status: str
    ) -> dict[str, Any]:
        await self._ensure()
        if status not in VALID_STATUSES:
            return {"ok": False, "message": f"허용되지 않은 상태: {status}"}
        res = await self.db.execute(text(
            "UPDATE lease_contracts SET status = :status, updated_at = now() "
            "WHERE id = :cid AND tenant_id = :tid"),
            {"status": status, "cid": contract_id, "tid": tenant_id})
        await self.db.commit()
        if (res.rowcount or 0) == 0:
            return {"ok": False, "message": "대상 계약 없음(또는 권한 없음)"}
        return {"ok": True, "id": contract_id, "status": status}

    # ── 집계(대시보드) ──
    async def summary(
        self, *, tenant_id: str, project_id: str | None = None
    ) -> dict[str, Any]:
        """공실률·임대수익 집계. total=계약(세대)수, leased=활성상태, vacant=나머지."""
        await self._ensure()
        active_in = ", ".join(f"'{s}'" for s in ACTIVE_STATUSES)
        scope = "tenant_id = :tid"
        params: dict[str, Any] = {"tid": tenant_id}
        if project_id:
            scope += " AND project_id = :pid"
            params["pid"] = project_id
        row = (await self.db.execute(text(
            f"SELECT count(*) AS total,"
            f" count(*) FILTER (WHERE status IN ({active_in})) AS leased,"
            f" COALESCE(sum(monthly_rent) FILTER (WHERE status IN ({active_in})), 0) AS rent_total "
            f"FROM lease_contracts WHERE {scope}"), params)).first()
        # 상태별 분포(by_status)
        by_rows = (await self.db.execute(text(
            f"SELECT status, count(*) FROM lease_contracts WHERE {scope} GROUP BY status"),
            params)).fetchall()

        total = int(row[0] or 0)
        leased = int(row[1] or 0)
        monthly_rent_total = float(row[2] or 0)
        vacant = max(0, total - leased)
        vacancy_rate_pct = round(vacant / total * 100, 1) if total else 0.0
        annual_income_est = round(monthly_rent_total * 12, 2)
        by_status = {r[0]: int(r[1]) for r in by_rows}
        return {
            "ok": True,
            "total_units": total,
            "leased": leased,
            "vacant": vacant,
            "vacancy_rate_pct": vacancy_rate_pct,
            "monthly_rent_total": monthly_rent_total,
            "annual_income_est": annual_income_est,
            "by_status": by_status,
        }
