"""v62 sales — Pydantic 스키마 자동 생성.

66개 모델 각각에 대해 {Model}Create / {Model}Update / {Model}Read 를 SQLAlchemy
컬럼 메타데이터에서 동적 생성해 모듈 속성으로 노출한다(getattr(S, f"{name}Create")).
- Create: 서버관리 컬럼(id/created_at/updated_at/deleted_at) 제외. site_id 는 컨텍스트 주입이라 optional.
- Update: 전 컬럼 optional.
- Read: 전 컬럼 + from_attributes. 민감 컬럼(va_number_enc 등)은 Read 제외.
"""

import sys
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, create_model

import apps.api.database.models.sales as _sales_pkg
from apps.api.database.models.base import Base


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


_AUTO = {"id", "created_at", "updated_at", "deleted_at"}
_SENSITIVE = {"va_number_enc", "hashed_password"}  # Read 제외


def _pytype(col) -> Any:
    try:
        t = col.type.python_type
    except Exception:  # noqa: BLE001  (geoalchemy2 Geography 등 python_type 미지원)
        return Any
    if t in (datetime, date, bool, int, str, float, uuid.UUID, dict, list, Decimal):
        return t
    return Any


def _build(model):
    name = model.__name__
    create_fields: dict[str, tuple] = {}
    update_fields: dict[str, tuple] = {}
    read_fields: dict[str, tuple] = {}

    for col in model.__table__.columns:
        cname = col.name
        pt = _pytype(col)
        if cname not in _SENSITIVE:
            read_fields[cname] = (Optional[pt], None)
        if cname in _AUTO:
            continue
        update_fields[cname] = (Optional[pt], None)
        has_default = col.default is not None or col.server_default is not None
        required = (not col.nullable) and (not has_default) and cname != "site_id" and not col.primary_key
        create_fields[cname] = (pt, ...) if required else (Optional[pt], None)

    create_m = create_model(f"{name}Create", __base__=BaseModel, **create_fields)
    update_m = create_model(f"{name}Update", __base__=BaseModel, **update_fields)
    read_m = create_model(f"{name}Read", __base__=ORMBase, **read_fields)
    return create_m, update_m, read_m


_mod = sys.modules[__name__]
__all__ = ["ORMBase"]

for _attr in _sales_pkg.__all__:
    _model = getattr(_sales_pkg, _attr)
    if not (isinstance(_model, type) and issubclass(_model, Base)):
        continue
    _c, _u, _r = _build(_model)
    setattr(_mod, _c.__name__, _c)
    setattr(_mod, _u.__name__, _u)
    setattr(_mod, _r.__name__, _r)
    __all__ += [_c.__name__, _u.__name__, _r.__name__]
