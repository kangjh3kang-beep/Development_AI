"""[B] 직원 모델 (5)."""

import uuid
from datetime import date, datetime

from geoalchemy2 import Geography
from sqlalchemy import Boolean, ForeignKey, Integer, String, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base
from apps.api.database.models.sales._mixins import PKMixin, SiteMixin, SoftDeleteMixin


class SalesStaff(Base, PKMixin, SiteMixin, SoftDeleteMixin):
    __tablename__ = "sales_staff"
    org_node_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_org_nodes.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), server_default="ACTIVE")
    license_no: Mapped[str | None] = mapped_column(String(60))
    register_meta: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class SalesStaffPhoneIndex(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_staff_phone_index"
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_staff.id"))
    phone_e164: Mapped[str] = mapped_column(String(20))
    label: Mapped[str | None] = mapped_column(String(40))


class SalesStaffAttendance(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_staff_attendance"
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_staff.id"))
    check_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    method: Mapped[str | None] = mapped_column(String(20))
    geo: Mapped[str | None] = mapped_column(Geography("POINT", 4326))
    work_minutes: Mapped[int | None] = mapped_column(Integer)


class SalesStaffSchedule(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_staff_schedule"
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_staff.id"))
    work_date: Mapped[date | None] = mapped_column()
    shift: Mapped[str | None] = mapped_column(String(20))
    planned: Mapped[bool | None] = mapped_column(Boolean)


class SalesStaffDocument(Base, PKMixin):
    __tablename__ = "sales_staff_documents"
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_staff.id"))
    doc_type: Mapped[str | None] = mapped_column(String(40))
    file_uri: Mapped[str | None] = mapped_column(String)
    verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
