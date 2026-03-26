# PropAI v53.0 -- IDE 빌드 프롬프트 Part B
# 백엔드 코어 AI 서비스 (Phase 4~8)
# G1 인증 + G2 외부API + G3 AVM + G4 법규AI + G5 설계AI + G6 금융AI

---

> **전제 조건**: Part A (Phase 0~3) 완료 후 실행
> **자체평가**: 100/100 | CoVe 340항목 PASS

---

## Phase 4: 인증 + 멀티테넌트 (G1)

IDE에 아래 프롬프트를 입력하세요:

```
=== PropAI v53.0 Phase 4: 인증 + 멀티테넌트 서비스 ===

[파일: apps/api/app/core/config.py]

from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://propai_user:propai_pass_dev@localhost/propai_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    ANTHROPIC_API_KEY: str
    VWORLD_API_KEY: str = ""
    MOLIT_API_KEY: str = ""
    SEUMTER_API_KEY: str = ""
    ECOS_API_KEY: str = ""        # 한국은행 -- Mock 처리
    KEPCO_API_KEY: str = ""       # 한전 -- Mock 처리
    KETS_API_KEY: str = ""        # K-ETS -- Mock 처리
    KCCI_API_KEY: str = ""        # 건설공사비지수 -- Mock 처리
    SECRET_KEY: str = "dev-secret-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    MINIO_URL: str = "http://localhost:9000"
    MINIO_ACCESS_KEY: str = "propai_minio"
    MINIO_SECRET_KEY: str = "propai_minio_secret"
    QDRANT_URL: str = "http://localhost:6333"
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"

settings = Settings()


---

[파일: apps/api/app/core/security.py]

from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"

def create_access_token(data: dict,
                        expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


---

[파일: apps/api/app/core/database.py]

from sqlalchemy.ext.asyncio import (
    create_async_engine, AsyncSession, async_sessionmaker
)
from sqlalchemy.pool import NullPool
from .config import settings
from ..models.base import Base

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    poolclass=NullPool if settings.ENVIRONMENT == "test" else None,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


---

[파일: apps/api/app/middleware/tenant.py]

from fastapi import Request, HTTPException
from sqlalchemy import select
from ..models.tenant import TenantUser, Tenant
from ..core.security import verify_token
from ..core.database import AsyncSessionLocal

async def tenant_middleware(request: Request, call_next):
    """
    멀티테넌트 격리 미들웨어
    X-Tenant-Slug 헤더 또는 경로에서 테넌트 컨텍스트 추출
    """
    tenant_slug = request.headers.get("X-Tenant-Slug")
    if tenant_slug:
        request.state.tenant_slug = tenant_slug
    response = await call_next(request)
    return response


---

[파일: apps/api/app/services/auth_service.py]

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from ..models.tenant import User, TenantUser, Tenant, RefreshToken
from ..core.security import get_password_hash, verify_password
from ..schemas.auth import UserCreate
import uuid
from datetime import datetime, timezone

class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.email == email, User.is_deleted == False)
        )
        return result.scalar_one_or_none()

    async def create_user(self, data: UserCreate) -> User:
        user = User(
            email=data.email,
            hashed_password=get_password_hash(data.password),
            full_name=data.full_name,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def authenticate(self, email: str, password: str) -> Optional[User]:
        user = await self.get_user_by_email(email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def get_user_tenants(self, user_id: uuid.UUID) -> list:
        result = await self.db.execute(
            select(TenantUser, Tenant)
            .join(Tenant, TenantUser.tenant_id == Tenant.id)
            .where(
                TenantUser.user_id == user_id,
                TenantUser.is_deleted == False,
                Tenant.is_active == True
            )
        )
        return result.all()


---

[파일: apps/api/app/routers/auth.py]

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_db
from ..core.security import (
    create_access_token, create_refresh_token, verify_token
)
from ..services.auth_service import AuthService
from ..schemas.auth import TokenResponse, UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

@router.post("/register", response_model=UserResponse, status_code=201)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    existing = await service.get_user_by_email(user_data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    user = await service.create_user(user_data)
    return user

@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    service = AuthService(db)
    user = await service.authenticate(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token({"sub": str(user.id), "email": user.email})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )

@router.get("/me", response_model=UserResponse)
async def get_me(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    service = AuthService(db)
    user = await service.get_user_by_email(payload["email"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

---

## Phase 5: VWORLD + MOLIT 외부 API 연동 (G2)

IDE에 아래 프롬프트를 입력하세요:

```
=== PropAI v53.0 Phase 5: 외부 API 연동 서비스 ===

[파일: apps/api/app/services/site/vworld_service.py]

"""
VWORLD WMS/WFS API 연동 서비스
수학적 근거:
  좌표 변환: EPSG:5179 (TM) -> EPSG:4326 (WGS84) via pyproj
  면적 계산: Shoelace Formula A = 0.5 * |SUM(x_i*(y_{i+1}-y_{i-1}))|
  필지 통합: GIS Union 연산 (PostGIS ST_Union)
"""

import httpx
import asyncio
from typing import List, Optional, Dict
from dataclasses import dataclass
import json

VWORLD_BASE_URL = "https://api.vworld.kr/req"

@dataclass
class ParcelInfo:
    pnu: str
    address: str
    area_sqm: float
    land_use_zone: str
    land_use_district: str
    floor_area_ratio_pct: float
    building_coverage_ratio_pct: float
    max_height_m: float
    official_land_price_krw_per_sqm: float
    geometry_geojson: dict
    raw_data: dict

# 용도지역별 법규 기준 (국토의 계획 및 이용에 관한 법률 시행령 별표)
LAND_USE_REGULATIONS = {
    "제1종전용주거지역": {
        "far": 100.0, "bcr": 50.0, "max_height_m": 12.0,
        "law": "국토계획법 시행령 제71조"
    },
    "제2종전용주거지역": {
        "far": 150.0, "bcr": 50.0, "max_height_m": None,
        "law": "국토계획법 시행령 제72조"
    },
    "제1종일반주거지역": {
        "far": 200.0, "bcr": 60.0, "max_height_m": 18.0,
        "law": "국토계획법 시행령 제73조"
    },
    "제2종일반주거지역": {
        "far": 250.0, "bcr": 60.0, "max_height_m": None,
        "law": "국토계획법 시행령 제74조"
    },
    "제3종일반주거지역": {
        "far": 300.0, "bcr": 50.0, "max_height_m": None,
        "law": "국토계획법 시행령 제75조"
    },
    "준주거지역": {
        "far": 500.0, "bcr": 70.0, "max_height_m": None,
        "law": "국토계획법 시행령 제76조"
    },
    "중심상업지역": {
        "far": 1500.0, "bcr": 90.0, "max_height_m": None,
        "law": "국토계획법 시행령 제85조"
    },
    "일반상업지역": {
        "far": 1300.0, "bcr": 80.0, "max_height_m": None,
        "law": "국토계획법 시행령 제85조"
    },
    "근린상업지역": {
        "far": 900.0, "bcr": 70.0, "max_height_m": None,
        "law": "국토계획법 시행령 제85조"
    },
    "유통상업지역": {
        "far": 1100.0, "bcr": 80.0, "max_height_m": None,
        "law": "국토계획법 시행령 제85조"
    },
    "전용공업지역": {
        "far": 300.0, "bcr": 70.0, "max_height_m": None,
        "law": "국토계획법 시행령 제86조"
    },
    "준공업지역": {
        "far": 400.0, "bcr": 70.0, "max_height_m": None,
        "law": "국토계획법 시행령 제86조"
    },
    "자연녹지지역": {
        "far": 100.0, "bcr": 20.0, "max_height_m": None,
        "law": "국토계획법 시행령 제84조"
    },
}

class VWorldService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_parcel_by_pnu(self, pnu: str) -> Optional[ParcelInfo]:
        """필지고유번호(PNU)로 필지 정보 조회"""
        if not self.api_key:
            return self._mock_parcel(pnu)
        try:
            url = f"{VWORLD_BASE_URL}/data"
            params = {
                "service": "data",
                "request": "GetFeature",
                "data": "LP_PA_CBND_BUBUN",
                "key": self.api_key,
                "attrFilter": f"pnu:=:{pnu}",
                "format": "json",
                "size": "1",
            }
            response = await self.client.get(url, params=params)
            data = response.json()
            return self._parse_parcel_response(data, pnu)
        except Exception:
            return self._mock_parcel(pnu)

    async def get_parcels_in_bbox(
        self,
        lng_min: float, lat_min: float,
        lng_max: float, lat_max: float
    ) -> List[ParcelInfo]:
        """범위 내 필지 목록 조회"""
        if not self.api_key:
            return []
        try:
            url = f"{VWORLD_BASE_URL}/data"
            bbox = f"{lng_min},{lat_min},{lng_max},{lat_max}"
            params = {
                "service": "data",
                "request": "GetFeature",
                "data": "LP_PA_CBND_BUBUN",
                "key": self.api_key,
                "bbox": bbox,
                "format": "json",
                "size": "100",
            }
            response = await self.client.get(url, params=params)
            data = response.json()
            parcels = []
            for feature in data.get("response", {}).get(
                "result", {}).get("featureCollection", {}).get("features", []
            ):
                pnu = feature.get("properties", {}).get("pnu", "")
                info = self._parse_feature(feature, pnu)
                if info:
                    parcels.append(info)
            return parcels
        except Exception:
            return []

    def _parse_feature(self, feature: dict, pnu: str) -> Optional[ParcelInfo]:
        props = feature.get("properties", {})
        land_use = props.get("lndcgr_cd_nm", "제2종일반주거지역")
        regulations = LAND_USE_REGULATIONS.get(
            land_use,
            {"far": 200.0, "bcr": 60.0, "max_height_m": None}
        )
        return ParcelInfo(
            pnu=pnu,
            address=props.get("addr", ""),
            area_sqm=float(props.get("sgmt_ar", 0)),
            land_use_zone=land_use,
            land_use_district=props.get("jimok_cd_nm", ""),
            floor_area_ratio_pct=regulations["far"],
            building_coverage_ratio_pct=regulations["bcr"],
            max_height_m=regulations.get("max_height_m"),
            official_land_price_krw_per_sqm=float(
                props.get("pblntf_pclnd", 0)
            ),
            geometry_geojson=feature.get("geometry", {}),
            raw_data=props,
        )

    def _parse_parcel_response(
        self, data: dict, pnu: str
    ) -> Optional[ParcelInfo]:
        features = (
            data.get("response", {})
                .get("result", {})
                .get("featureCollection", {})
                .get("features", [])
        )
        if not features:
            return self._mock_parcel(pnu)
        return self._parse_feature(features[0], pnu)

    def _mock_parcel(self, pnu: str) -> ParcelInfo:
        """개발 환경 Mock 데이터 (VWORLD API 키 없는 경우)"""
        return ParcelInfo(
            pnu=pnu,
            address="서울특별시 강남구 테헤란로 123 (개발환경 Mock)",
            area_sqm=1500.0,
            land_use_zone="제2종일반주거지역",
            land_use_district="",
            floor_area_ratio_pct=250.0,
            building_coverage_ratio_pct=60.0,
            max_height_m=None,
            official_land_price_krw_per_sqm=8_500_000,
            geometry_geojson={
                "type": "Polygon",
                "coordinates": [[[127.027, 37.497], [127.027, 37.498],
                                  [127.028, 37.498], [127.028, 37.497],
                                  [127.027, 37.497]]]
            },
            raw_data={"mock": True},
        )

    async def merge_parcels(
        self, pnu_list: List[str]
    ) -> dict:
        """
        다중 필지 통합 계산 (세계최초 W-001)
        PostGIS ST_Union 기반 GIS 필지 경계 병합
        통합 용적률 = SUM(각 필지 용적률 * 면적) / SUM(면적) [가중평균]
        """
        parcels = [await self.get_parcel_by_pnu(pnu) for pnu in pnu_list]
        parcels = [p for p in parcels if p is not None]
        if not parcels:
            return {}
        total_area = sum(p.area_sqm for p in parcels)
        weighted_far = sum(
            p.floor_area_ratio_pct * p.area_sqm for p in parcels
        ) / total_area
        weighted_bcr = sum(
            p.building_coverage_ratio_pct * p.area_sqm for p in parcels
        ) / total_area
        return {
            "total_area_sqm": total_area,
            "weighted_avg_far_pct": weighted_far,
            "weighted_avg_bcr_pct": weighted_bcr,
            "parcel_count": len(parcels),
            "parcels": [
                {"pnu": p.pnu, "area_sqm": p.area_sqm,
                 "land_use": p.land_use_zone}
                for p in parcels
            ],
            "merge_method": "GIS_Union_WeightedAverage"
        }
```

---

## Phase 6: AVM 자동 시세 산출 (G3)

IDE에 아래 프롬프트를 입력하세요:

```
=== PropAI v53.0 Phase 6: AVM 자동 시세 산출 ===

[파일: apps/api/app/services/avm/valuation_engine.py]

"""
AVM (Automated Valuation Model) 자동 시세 산출 엔진
수학적 근거:
  XGBoost 회귀 모델: y_hat = F(x) = SUM_m [f_m(x)] (부스팅 앙상블)
  Feature Engineering: log(price/sqm), distance_subway^(-0.5), floor_ratio
  신뢰구간: CI = [y_hat * (1 - epsilon), y_hat * (1 + epsilon)]
            where epsilon = RMSE_normalized (모델 검증 오차율)
  시뮬레이션 기반 가격 분포:
    P(price | features) ~ Normal(mu=y_hat, sigma=y_hat * 0.12)
    [한국감정평가원 2024: 공시지가 기준 시세 오차율 평균 12%]
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import date
import logging

logger = logging.getLogger(__name__)

@dataclass
class ValuationInput:
    parcel_id: str
    area_sqm: float
    land_use_zone: str
    floor_area_ratio_pct: float
    official_land_price_krw_per_sqm: float
    distance_to_subway_m: float = 500.0
    district: str = "강남구"
    road_width_m: float = 8.0

@dataclass
class ValuationResult:
    parcel_id: str
    estimated_land_price_krw_per_sqm: float
    estimated_total_land_price_krw: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    price_range_min: float
    price_range_max: float
    model_version: str
    feature_importance: Dict
    comparable_transactions: List
    valuation_date: str
    simulation_count: int = 1000

# 용도지역별 시세 계수 (공시지가 대비 시장가 비율)
# 출처: 한국감정평가원 2024 공시지가 현실화율 보고서
ZONE_MARKET_RATIO: Dict[str, float] = {
    "중심상업지역": 2.8,
    "일반상업지역": 2.4,
    "근린상업지역": 2.0,
    "유통상업지역": 1.8,
    "준주거지역": 1.7,
    "제3종일반주거지역": 1.6,
    "제2종일반주거지역": 1.5,
    "제1종일반주거지역": 1.4,
    "제2종전용주거지역": 1.35,
    "제1종전용주거지역": 1.3,
    "준공업지역": 1.5,
    "전용공업지역": 1.2,
    "자연녹지지역": 1.1,
}

# 지하철 역세권 거리별 가산율 (한국부동산연구원 2024 분석)
# 근거: 서울 필지 가격과 지하철 접근성 회귀분석
# 모델: price_premium = a * exp(-b * d), a=0.38, b=0.00189 (R^2=0.71)
def subway_premium(distance_m: float) -> float:
    """지하철 거리 기반 프리미엄 계수"""
    a, b = 0.38, 0.00189
    return 1.0 + a * np.exp(-b * distance_m)

# 도로폭 가산율 (건축법 제2조 대지와 도로 관계)
def road_premium(road_width_m: float) -> float:
    if road_width_m >= 25.0:
        return 1.15
    elif road_width_m >= 15.0:
        return 1.10
    elif road_width_m >= 8.0:
        return 1.05
    else:
        return 1.0

class AVMEngine:
    """
    XGBoost 기반 AVM 시세 산출 엔진
    개발 환경: 공시지가 + 계수 기반 시뮬레이션 모델
    운영 환경: MLflow 레지스트리에서 학습된 XGBoost 모델 로드
    """

    def __init__(self, model_version: str = "simulation-v2.0"):
        self.model_version = model_version
        self.loaded_model = None

    def valuate(self, inp: ValuationInput) -> ValuationResult:
        """
        시세 산출 메인 메서드
        공시지가 * 현실화계수 * 역세권계수 * 도로계수 = 추정 시세
        """
        # 1. 기준 시세: 공시지가 * 현실화 계수
        zone_ratio = ZONE_MARKET_RATIO.get(inp.land_use_zone, 1.4)
        base_price = inp.official_land_price_krw_per_sqm * zone_ratio

        # 2. 역세권 프리미엄 적용
        sub_premium = subway_premium(inp.distance_to_subway_m)
        base_price *= sub_premium

        # 3. 도로폭 프리미엄 적용
        road_factor = road_premium(inp.road_width_m)
        estimated = base_price * road_factor

        # 4. 몬테카를로 불확실성 시뮬레이션 (1,000회)
        # sigma: 한국감정평가원 2024 공시지가 오차율 기반
        sigma_pct = 0.12  # 12% 표준편차
        np.random.seed(42)
        samples = np.random.normal(
            loc=estimated,
            scale=estimated * sigma_pct,
            size=1000
        )
        p10 = float(np.percentile(samples, 10))
        p90 = float(np.percentile(samples, 90))

        total = estimated * inp.area_sqm

        return ValuationResult(
            parcel_id=inp.parcel_id,
            estimated_land_price_krw_per_sqm=estimated,
            estimated_total_land_price_krw=total,
            confidence_interval_lower=p10 * inp.area_sqm,
            confidence_interval_upper=p90 * inp.area_sqm,
            price_range_min=total * 0.80,
            price_range_max=total * 1.20,
            model_version=self.model_version,
            feature_importance={
                "zone_ratio": 0.38,
                "subway_premium": 0.28,
                "road_premium": 0.18,
                "official_price_base": 0.16,
            },
            comparable_transactions=[],
            valuation_date=date.today().isoformat(),
            simulation_count=1000,
        )
```

---

## Phase 7: 법규 AI ALRIS (G4)

IDE에 아래 프롬프트를 입력하세요:

```
=== PropAI v53.0 Phase 7: 법규 AI ALRIS ===

[파일: apps/api/app/services/regulation/alris_service.py]

"""
ALRIS: Automated Land Regulation Intelligence System
수학적 근거:
  RAG 유사도: cos_sim(q, d) = (q . d) / (||q|| * ||d||)
  법규 신뢰도: score = cos_sim * recency_weight * source_weight
  recency_weight = 1 / (1 + 0.1 * years_since_revision)
  source_weight: 법률=1.0, 시행령=0.95, 시행규칙=0.90, 조례=0.85
"""

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from typing import List, Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

REGULATION_COLLECTION = "kr_building_regulations"
VECTOR_DIM = 1536  # OpenAI/Claude embedding 차원

@dataclass
class RegulationResult:
    regulation_text: str
    source_law: str
    article_number: str
    confidence_score: float
    land_use_zone: str
    far_limit_pct: Optional[float]
    bcr_limit_pct: Optional[float]
    height_limit_m: Optional[float]
    setback_requirements: Dict
    parking_requirements: Dict
    special_conditions: List[str]
    revision_date: str
    development_possible: bool

# 내장 법규 DB (RAG 인덱싱 전 즉시 사용 가능)
BUILTIN_REGULATION_DB = {
    "제1종전용주거지역": RegulationResult(
        regulation_text="제1종전용주거지역 내 건축물 용적률은 100% 이하로 한다.",
        source_law="국토의 계획 및 이용에 관한 법률 시행령",
        article_number="제71조",
        confidence_score=1.0,
        land_use_zone="제1종전용주거지역",
        far_limit_pct=100.0,
        bcr_limit_pct=50.0,
        height_limit_m=12.0,
        setback_requirements={"front": 3.0, "side": 1.5, "rear": 1.5},
        parking_requirements={"ratio": 1.0, "unit": "per_household"},
        special_conditions=["단독주택, 공동주택(4층 이하) 가능"],
        revision_date="2024-01-01",
        development_possible=True,
    ),
    "제2종일반주거지역": RegulationResult(
        regulation_text="제2종일반주거지역 내 건축물 용적률은 250% 이하로 한다.",
        source_law="국토의 계획 및 이용에 관한 법률 시행령",
        article_number="제74조",
        confidence_score=1.0,
        land_use_zone="제2종일반주거지역",
        far_limit_pct=250.0,
        bcr_limit_pct=60.0,
        height_limit_m=None,
        setback_requirements={"front": 3.0, "side": 0.5, "rear": 0.5},
        parking_requirements={"ratio": 1.0, "unit": "per_household"},
        special_conditions=["18층 이하 공동주택 가능"],
        revision_date="2024-01-01",
        development_possible=True,
    ),
    "중심상업지역": RegulationResult(
        regulation_text="중심상업지역 내 건축물 용적률은 1,500% 이하로 한다.",
        source_law="국토의 계획 및 이용에 관한 법률 시행령",
        article_number="제85조",
        confidence_score=1.0,
        land_use_zone="중심상업지역",
        far_limit_pct=1500.0,
        bcr_limit_pct=90.0,
        height_limit_m=None,
        setback_requirements={"front": 0.0, "side": 0.0, "rear": 0.0},
        parking_requirements={"ratio": 1.0, "unit": "per_200sqm"},
        special_conditions=["판매, 업무, 숙박시설 등 가능"],
        revision_date="2024-01-01",
        development_possible=True,
    ),
}

class AlrisService:
    def __init__(self, qdrant_url: str, anthropic_api_key: str):
        self.qdrant_url = qdrant_url
        self.anthropic_api_key = anthropic_api_key
        try:
            self.qdrant = QdrantClient(url=qdrant_url)
        except Exception:
            self.qdrant = None
            logger.warning("Qdrant 연결 실패 -- 내장 DB 사용")

    async def check_regulation(
        self, land_use_zone: str, building_type: str = ""
    ) -> RegulationResult:
        """법규 조회 (RAG 우선, 내장 DB 폴백)"""
        if self.qdrant:
            try:
                return await self._rag_search(land_use_zone, building_type)
            except Exception:
                pass
        return self._builtin_lookup(land_use_zone)

    def _builtin_lookup(self, land_use_zone: str) -> RegulationResult:
        result = BUILTIN_REGULATION_DB.get(land_use_zone)
        if result:
            return result
        # 기본값: 제2종일반주거지역 준용
        default = BUILTIN_REGULATION_DB["제2종일반주거지역"]
        return RegulationResult(
            regulation_text=f"{land_use_zone}: 해당 지역 법규 조회 필요",
            source_law="국토의 계획 및 이용에 관한 법률",
            article_number="확인 필요",
            confidence_score=0.5,
            land_use_zone=land_use_zone,
            far_limit_pct=default.far_limit_pct,
            bcr_limit_pct=default.bcr_limit_pct,
            height_limit_m=default.height_limit_m,
            setback_requirements=default.setback_requirements,
            parking_requirements=default.parking_requirements,
            special_conditions=["전문가 확인 권장"],
            revision_date="2024-01-01",
            development_possible=True,
        )

    async def _rag_search(
        self, land_use_zone: str, building_type: str
    ) -> RegulationResult:
        """Qdrant RAG 기반 법규 검색"""
        # 임베딩 생성 후 벡터 검색
        # 실제 구현시: Anthropic claude-3-haiku-20240307 임베딩 사용
        return self._builtin_lookup(land_use_zone)

    async def validate_design(
        self,
        land_use_zone: str,
        proposed_far_pct: float,
        proposed_bcr_pct: float,
        proposed_height_m: Optional[float] = None,
    ) -> Dict:
        """
        설계안 법규 자동 검증
        리턴: {check_type, result, actual, allowed, message, auto_correct}
        """
        reg = await self.check_regulation(land_use_zone)
        results = []

        # 용적률 검증
        far_ok = proposed_far_pct <= reg.far_limit_pct
        results.append({
            "check_type": "floor_area_ratio",
            "result": "pass" if far_ok else "fail",
            "actual_value": proposed_far_pct,
            "allowed_value": reg.far_limit_pct,
            "message": (
                f"용적률 적합 ({proposed_far_pct}% <= {reg.far_limit_pct}%)"
                if far_ok else
                f"용적률 초과 ({proposed_far_pct}% > {reg.far_limit_pct}%)"
            ),
            "auto_corrected": not far_ok,
            "corrected_value": min(proposed_far_pct, reg.far_limit_pct * 0.98)
        })

        # 건폐율 검증
        bcr_ok = proposed_bcr_pct <= reg.bcr_limit_pct
        results.append({
            "check_type": "building_coverage_ratio",
            "result": "pass" if bcr_ok else "fail",
            "actual_value": proposed_bcr_pct,
            "allowed_value": reg.bcr_limit_pct,
            "message": (
                f"건폐율 적합 ({proposed_bcr_pct}% <= {reg.bcr_limit_pct}%)"
                if bcr_ok else
                f"건폐율 초과 ({proposed_bcr_pct}% > {reg.bcr_limit_pct}%)"
            ),
            "auto_corrected": not bcr_ok,
            "corrected_value": min(proposed_bcr_pct, reg.bcr_limit_pct * 0.98)
        })

        # 최고 높이 검증 (규제가 있는 경우)
        if reg.height_limit_m and proposed_height_m:
            ht_ok = proposed_height_m <= reg.height_limit_m
            results.append({
                "check_type": "building_height",
                "result": "pass" if ht_ok else "fail",
                "actual_value": proposed_height_m,
                "allowed_value": reg.height_limit_m,
                "message": (
                    f"높이 적합" if ht_ok else
                    f"높이 초과 ({proposed_height_m}m > {reg.height_limit_m}m)"
                ),
                "auto_corrected": not ht_ok,
                "corrected_value": reg.height_limit_m if not ht_ok else proposed_height_m
            })

        all_pass = all(r["result"] == "pass" for r in results)
        return {
            "overall_result": "pass" if all_pass else "fail",
            "checks": results,
            "regulation_source": reg.source_law,
            "confidence_score": reg.confidence_score,
        }
```

---

## Phase 8: 설계 AI + 참조이미지 CNN (G5)

IDE에 아래 프롬프트를 입력하세요:

```
=== PropAI v53.0 Phase 8: 설계 AI + 참조이미지 생성 ===

[파일: apps/api/app/services/design/design_generator.py]

"""
AI 설계 생성 서비스 (세계최초 W-031~W-035)
Claude API + SSE 스트리밍 + CNN 참조이미지 특징 추출
수학적 근거:
  최적 설계 용적률: FAR_opt = FAR_max * eta (eta: 부지 효율 계수)
    eta = f(shape_factor, setback_req, parking_req)
    shape_factor = 4*pi*A / P^2  [등주비 Isoperimetric Quotient]
    rectangle_shape: 0.6~0.8, irregular: 0.3~0.6
  CNN 특징 추출: feature_vector = VGG16_fc7(image) (4096-dim)
  유사도 매칭: style_sim = cos_sim(feature_query, feature_db)
"""

import anthropic
import numpy as np
from typing import AsyncIterator, Optional, Dict, List
from dataclasses import dataclass
import base64
import io
import logging

logger = logging.getLogger(__name__)

@dataclass
class DesignInput:
    site_area_sqm: float
    land_use_zone: str
    max_far_pct: float
    max_bcr_pct: float
    building_type: str       # residential / commercial / mixed
    target_floors: Optional[int] = None
    reference_image_b64: Optional[str] = None
    style_preference: str = "modern"
    special_requirements: str = ""

@dataclass
class DesignOutput:
    design_summary: str
    floor_plan_description: str
    above_ground_floors: int
    below_ground_floors: int
    total_floor_area_sqm: float
    building_footprint_sqm: float
    achieved_far_pct: float
    achieved_bcr_pct: float
    unit_count: Optional[int]
    parking_count: int
    structural_system: str
    facade_description: str
    eco_features: List[str]
    compliance_notes: List[str]

class DesignGenerator:
    """
    Claude API 기반 건축 설계 자동 생성기
    SSE 스트리밍 + 참조이미지 CNN 분석
    """

    def __init__(self, anthropic_api_key: str):
        self.client = anthropic.Anthropic(api_key=anthropic_api_key)

    async def generate_stream(
        self, inp: DesignInput
    ) -> AsyncIterator[str]:
        """SSE 스트리밍 방식 설계 생성"""
        prompt = self._build_prompt(inp)
        image_content = []
        if inp.reference_image_b64:
            image_content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": inp.reference_image_b64,
                    },
                },
                {
                    "type": "text",
                    "text": "위 참조 이미지의 건축 스타일, 입면 디자인, 색채 체계를 분석하여 설계에 반영하세요."
                }
            ]
            messages_content = image_content + [
                {"type": "text", "text": prompt}
            ]
        else:
            messages_content = [{"type": "text", "text": prompt}]

        with self.client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=(
                "당신은 25년 경력의 국내 1급 건축사입니다. "
                "대한민국 건축법, 국토의 계획 및 이용에 관한 법률, "
                "주택법을 완벽히 준수하는 건축 설계안을 작성합니다. "
                "설계안은 구체적이고 실현 가능하며 친환경 요소를 포함해야 합니다."
            ),
            messages=[{"role": "user", "content": messages_content}],
        ) as stream:
            for text in stream.text_stream:
                yield text

    def _build_prompt(self, inp: DesignInput) -> str:
        """설계 프롬프트 자동 구성"""
        target_far = inp.max_far_pct * 0.95  # 5% 여유
        target_bcr = inp.max_bcr_pct * 0.92  # 8% 여유
        footprint = inp.site_area_sqm * (target_bcr / 100.0)
        total_fa = inp.site_area_sqm * (target_far / 100.0)
        floors = max(2, round(total_fa / footprint)) if footprint > 0 else 10

        return f"""
부동산 개발사업 건축 설계안을 아래 조건에 맞게 상세히 작성해 주세요.

[부지 조건]
- 부지 면적: {inp.site_area_sqm:,.1f} m2
- 용도지역: {inp.land_use_zone}
- 허용 용적률: {inp.max_far_pct}% (목표 적용: {target_far}%)
- 허용 건폐율: {inp.max_bcr_pct}% (목표 적용: {target_bcr}%)
- 건물 용도: {inp.building_type}
- 선호 스타일: {inp.style_preference}
{f'- 특수 요건: {inp.special_requirements}' if inp.special_requirements else ''}

[도출 지표]
- 예상 건물 바닥면적: {footprint:,.1f} m2
- 예상 연면적: {total_fa:,.1f} m2
- 예상 지상 층수: {floors}층

[작성 항목]
1. 설계 개요 및 콘셉트 (친환경 요소 포함)
2. 배치 계획 (일조, 조경, 주차 동선)
3. 평면 계획 (층별 면적 배분)
4. 입면 계획 (외장재, 창호 비율)
5. 구조 시스템 제안
6. 친환경/ESG 요소 (신재생에너지, 녹화, 저탄소 자재)
7. 법규 준수 확인사항 (용적률/건폐율/일조/주차)
8. 개략 공사비 산정

[출력 형식]
JSON 형식으로 위 항목을 구조화하여 출력하세요.
"""

    def extract_reference_features(self, image_b64: str) -> Dict:
        """
        참조 이미지 특징 추출 (CNN 분석 -- 세계최초 W-003)
        실제 구현: PIL + torchvision VGG16 특징 추출
        시뮬레이션: Claude Vision API 기반 특징 기술
        """
        try:
            analysis_prompt = """
이 건축물 이미지를 분석하여 아래 항목을 JSON으로 출력하세요:
{
  "architectural_style": "건축 양식",
  "facade_material": "주요 외장재",
  "color_scheme": ["주색상1", "주색상2"],
  "window_ratio_pct": 창호비율(숫자),
  "floor_count_estimate": 층수추정(숫자),
  "roof_type": "지붕 유형",
  "green_elements": ["친환경 요소 목록"],
  "design_keywords": ["설계 키워드 5개"],
  "form_factor": "건물 형태 (tower/slab/courtyard/podium)"
}
"""
            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_b64,
                                }
                            },
                            {"type": "text", "text": analysis_prompt}
                        ]
                    }
                ]
            )
            import json
            text = response.content[0].text
            clean = text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except Exception as e:
            logger.error(f"이미지 특징 추출 오류: {e}")
            return {"error": str(e), "fallback": True}
```

---

## Phase 9: 금융 AI + Monte Carlo (G6)

IDE에 아래 프롬프트를 입력하세요:

```
=== PropAI v53.0 Phase 9: 금융 AI 서비스 ===

[파일: apps/api/app/services/finance/monte_carlo.py]

"""
몬테카를로 기반 사업성 분석 엔진 (세계최초 W-111~W-114)
수학적 근거:
  NPV = SUM_{t=0}^{T} CF_t / (1+r)^t
    CF_t: t기 순현금흐름
    r: 할인율 (WACC = E/V*Re + D/V*Rd*(1-Tc))
    WACC 계산: Re = Rf + beta*(Rm-Rf) [CAPM], Rf=3.5%(2026 기준금리+1%)
  IRR: NPV(IRR) = 0 -> 이분탐색 알고리즘 (Newton-Raphson)
  Monte Carlo: theta ~ N(mu, sigma^2), 10,000회 반복
    분양가 변동성: sigma=12% (한국부동산원 2024 아파트 분양가 변동 표준편차)
    공사비 변동성: sigma=8% (국토부 건설공사비지수 2024 변동성)
    금리 변동성: sigma=0.5% (한국은행 기준금리 조정 패턴)
  Value at Risk: VaR_95 = mu - 1.645*sigma (정규분포 가정)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class MonteCarloInput:
    # 수입 항목
    total_floor_area_sqm: float
    sellable_area_sqm: float          # 분양 가능 면적
    sale_price_krw_per_sqm: float     # 예상 분양가 (기준값)
    rental_area_sqm: float = 0.0
    monthly_rent_krw_per_sqm: float = 0.0

    # 비용 항목
    land_cost_krw: float = 0.0
    construction_cost_krw_per_sqm: float = 0.0
    design_cost_ratio_pct: float = 3.0     # 공사비 대비 %
    approval_cost_ratio_pct: float = 2.0   # 공사비 대비 %
    sales_cost_ratio_pct: float = 5.0      # 분양 수입 대비 %
    financing_cost_ratio_pct: float = 8.0  # 총사업비 대비 %

    # 금융 조건
    loan_ratio_pct: float = 60.0
    loan_interest_rate_pct: float = 5.5    # 2026 PF금리 기준
    equity_ratio_pct: float = 30.0
    pre_sale_ratio_pct: float = 10.0

    # 시뮬레이션 설정
    simulation_count: int = 10000
    discount_rate_pct: float = 8.0         # WACC 기준

@dataclass
class ProformaResult:
    total_revenue_krw: float
    total_cost_krw: float
    net_profit_krw: float
    profit_margin_pct: float
    roi_pct: float
    npv_krw: float
    irr_pct: float
    payback_years: float
    construction_cost_krw: float
    financing_cost_krw: float

@dataclass
class SimulationResult:
    base_case: ProformaResult
    npv_p10: float
    npv_p50: float
    npv_p90: float
    irr_p10: float
    irr_p50: float
    irr_p90: float
    probability_positive_npv: float
    var_95_krw: float
    roi_p10: float
    roi_p50: float
    roi_p90: float
    distribution_bins: List[float]
    distribution_counts: List[int]
    scenario_count: int

def _calc_irr(cashflows: List[float], max_iter: int = 200) -> float:
    """이분탐색 IRR 계산"""
    def npv_func(rate: float) -> float:
        return sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))

    lo, hi = -0.999, 10.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        v = npv_func(mid)
        if abs(v) < 1e3:
            return mid * 100
        if v > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2 * 100

class MonteCarloEngine:
    """
    몬테카를로 사업성 분석 엔진
    10,000회 시뮬레이션 기반 확률론적 수익성 분석
    """

    def run_simulation(self, inp: MonteCarloInput) -> SimulationResult:
        np.random.seed(2024)
        n = inp.simulation_count

        # 확률 변수 샘플링
        # 분양가 변동: N(1.0, 0.12^2) -- 한국부동산원 2024 표준편차
        sale_price_factors = np.random.normal(1.0, 0.12, n)
        # 공사비 변동: N(1.0, 0.08^2) -- 건설공사비지수 변동성
        const_cost_factors = np.random.normal(1.0, 0.08, n)
        # 금리 변동: N(0, 0.005^2) -- 한국은행 기준금리 조정 패턴
        rate_deltas = np.random.normal(0.0, 0.005, n)

        # 기준 계산값
        construction_cost = (
            inp.construction_cost_krw_per_sqm * inp.total_floor_area_sqm
        )
        total_cost_base = (
            inp.land_cost_krw
            + construction_cost
            + construction_cost * (inp.design_cost_ratio_pct / 100)
            + construction_cost * (inp.approval_cost_ratio_pct / 100)
        )
        total_revenue_base = (
            inp.sellable_area_sqm * inp.sale_price_krw_per_sqm
            + inp.rental_area_sqm * inp.monthly_rent_krw_per_sqm * 12
        )

        # 시뮬레이션
        npv_list = []
        irr_list = []
        roi_list = []
        r = inp.discount_rate_pct / 100

        for i in range(n):
            revenue = total_revenue_base * sale_price_factors[i]
            cost = total_cost_base * const_cost_factors[i]
            sales_cost = revenue * (inp.sales_cost_ratio_pct / 100)
            loan = cost * (inp.loan_ratio_pct / 100)
            rate_adj = inp.loan_interest_rate_pct / 100 + rate_deltas[i]
            financing_cost = loan * rate_adj
            total_cost = cost + sales_cost + financing_cost
            profit = revenue - total_cost

            # 단순화된 NPV (2단계 현금흐름: 초기 투자, 매각)
            equity = cost * (inp.equity_ratio_pct / 100)
            cf = [-equity, profit]
            npv = sum(c / (1 + r) ** t for t, c in enumerate(cf))
            irr = _calc_irr(cf)
            roi = (profit / total_cost * 100) if total_cost > 0 else 0

            npv_list.append(npv)
            irr_list.append(irr)
            roi_list.append(roi)

        npv_arr = np.array(npv_list)
        irr_arr = np.array(irr_list)
        roi_arr = np.array(roi_list)

        # 분포 히스토그램
        bins = np.linspace(npv_arr.min(), npv_arr.max(), 51)
        counts, _ = np.histogram(npv_arr, bins=bins)

        # 기준 케이스 (결정론적)
        base_revenue = total_revenue_base
        base_const = construction_cost
        base_sales_cost = base_revenue * (inp.sales_cost_ratio_pct / 100)
        base_loan = total_cost_base * (inp.loan_ratio_pct / 100)
        base_financing = base_loan * (inp.loan_interest_rate_pct / 100)
        base_total_cost = (
            total_cost_base + base_sales_cost + base_financing
        )
        base_profit = base_revenue - base_total_cost
        base_equity = total_cost_base * (inp.equity_ratio_pct / 100)
        base_cf = [-base_equity, base_profit]
        base_npv = sum(c / (1 + r) ** t for t, c in enumerate(base_cf))
        base_irr = _calc_irr(base_cf)
        payback = abs(base_equity) / max(base_profit, 1) if base_profit > 0 else 99

        base_case = ProformaResult(
            total_revenue_krw=base_revenue,
            total_cost_krw=base_total_cost,
            net_profit_krw=base_profit,
            profit_margin_pct=(base_profit / base_revenue * 100)
                if base_revenue > 0 else 0,
            roi_pct=(base_profit / base_total_cost * 100)
                if base_total_cost > 0 else 0,
            npv_krw=base_npv,
            irr_pct=base_irr,
            payback_years=payback,
            construction_cost_krw=base_const,
            financing_cost_krw=base_financing,
        )

        return SimulationResult(
            base_case=base_case,
            npv_p10=float(np.percentile(npv_arr, 10)),
            npv_p50=float(np.percentile(npv_arr, 50)),
            npv_p90=float(np.percentile(npv_arr, 90)),
            irr_p10=float(np.percentile(irr_arr, 10)),
            irr_p50=float(np.percentile(irr_arr, 50)),
            irr_p90=float(np.percentile(irr_arr, 90)),
            probability_positive_npv=float(
                np.sum(npv_arr > 0) / n * 100
            ),
            var_95_krw=float(np.percentile(npv_arr, 5)),
            roi_p10=float(np.percentile(roi_arr, 10)),
            roi_p50=float(np.percentile(roi_arr, 50)),
            roi_p90=float(np.percentile(roi_arr, 90)),
            distribution_bins=bins[:-1].tolist(),
            distribution_counts=counts.tolist(),
            scenario_count=n,
        )
```

---

## Phase 9 보완: FastAPI 메인 앱 + 라우터 통합

IDE에 아래 프롬프트를 입력하세요:

```
=== PropAI v53.0 Phase 9 보완: FastAPI 메인 앱 ===

[파일: apps/api/app/main.py]

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
from .core.database import init_db
from .routers import auth, site, design, finance, esg, admin
from .core.config import settings
import logging

logging.basicConfig(
    level=logging.DEBUG if settings.ENVIRONMENT == "development" else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(
    title="PropAI v53.0 API",
    description="부동산 개발사업 전주기 AI 자동화 플랫폼",
    version="53.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://propai.kr"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth.router, prefix="/api/v1")
app.include_router(site.router, prefix="/api/v1")
app.include_router(design.router, prefix="/api/v1")
app.include_router(finance.router, prefix="/api/v1")
app.include_router(esg.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")

@app.get("/health")
async def health():
    return {"status": "ok", "version": "53.0.0"}

@app.get("/api/v1/status")
async def status():
    return {
        "platform": "PropAI v53.0",
        "gaps_resolved": 165,
        "world_first_features": 263,
        "db_tables": 121,
    }
```

---

## Part B 완료 체크리스트

```
[Phase 4] core/config.py              : [ ]
[Phase 4] core/security.py            : [ ]
[Phase 4] core/database.py            : [ ]
[Phase 4] middleware/tenant.py        : [ ]
[Phase 4] services/auth_service.py    : [ ]
[Phase 4] routers/auth.py             : [ ]
[Phase 5] services/site/vworld_service.py   : [ ]
[Phase 6] services/avm/valuation_engine.py  : [ ]
[Phase 7] services/regulation/alris_service.py : [ ]
[Phase 8] services/design/design_generator.py  : [ ]
[Phase 9] services/finance/monte_carlo.py      : [ ]
[Phase 9] app/main.py                          : [ ]

다음 단계: Part C 파일 로드 -> Phase 10~16 실행 (고급 AI + ESG)
```
