"""AVM (자동 시세 추정) 서비스.

XGBoost 기반 부동산 시세 추정.
목표: MAPE ≤ 5% (CoVe O1 기준).

흐름:
1. 공공 API(국토부, V-World)에서 실거래가/공시지가 수집
2. 16개 특성 벡터 생성 (면적, 층수, 건물연령, 접근성 등)
3. MLflow 3단계 폴백 모델 추론
4. 비교 사례 선정 및 신뢰도 산출
5. MLflow에 추론 결과 기록
"""

import math
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any
from uuid import UUID

import structlog
from packages.schemas.models import AVMRequest, AVMValuationResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.avm_valuation import AVMValuation

logger = structlog.get_logger(__name__)

# ── MLflow 모델 3단계 폴백 순서 ──
_MODEL_STAGES = [
    ("models:/PropAI-AVM/Production", "production"),
    ("models:/PropAI-AVM/Staging", "staging"),
]

# ── 모델 단계별 기본 신뢰도 ──
_BASE_CONFIDENCE: dict[str, float] = {
    "production": 0.87,
    "staging": 0.70,
    "fallback": 0.40,
}


class AVMService:
    """AVM 시세 추정 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._model: Any = None
        self._model_stage = "fallback"
        self.settings = get_settings()

    # ── MLflow 3단계 폴백 모델 로드 ──

    async def _load_model(self) -> None:
        """MLflow에서 모델을 3단계 폴백으로 로드한다.

        Production → Staging → 면적 기반 단순 추정 폴백.
        """
        if self._model is not None:
            return

        try:
            import mlflow

            mlflow.set_tracking_uri(self.settings.mlflow_tracking_uri)

            for model_uri, stage in _MODEL_STAGES:
                try:
                    self._model = mlflow.xgboost.load_model(model_uri)
                    self._model_stage = stage
                    logger.info("AVM 모델 로드 완료", stage=stage)
                    return
                except Exception:
                    logger.debug("MLflow 모델 없음", uri=model_uri)
                    continue

        except Exception:
            logger.debug("MLflow 연결 실패")

        # 최종 폴백: 미학습 XGBoost (predict 시 면적 기반 단순 추정 사용)
        logger.warning("모든 MLflow 모델 로드 실패 — 면적 기반 폴백")
        self._model_stage = "fallback"

    # ── 비교 사례 실제 조회 ──

    async def _fetch_comparables(
        self,
        address: str,
        area_sqm: float,
        lawd_cd: str = "",
    ) -> list[dict[str, Any]]:
        """국토부 실거래 API에서 유사 면적(±15㎡) 비교 사례를 조회한다."""
        from apps.api.integrations.molit_client import MolitClient

        if not lawd_cd:
            lawd_cd = "11680"  # 서울 강남구 기본값

        molit = MolitClient()
        now = datetime.now(tz=UTC)
        comparables: list[dict[str, Any]] = []

        try:
            # 최근 3개월 실거래 데이터 수집
            for month_offset in range(3):
                month = now.month - month_offset
                year = now.year
                if month <= 0:
                    month += 12
                    year -= 1
                deal_ymd = f"{year}{month:02d}"

                trades = await molit.get_transactions(lawd_cd, deal_ymd)
                for t in trades:
                    t_area = t.get("area_m2", 0.0)
                    if abs(t_area - area_sqm) <= 15.0 and t.get("price_10k_won", 0) > 0:
                        comparables.append(t)

            # 최근 거래 순으로 정렬, 최대 10건
            comparables = comparables[:10]
            logger.info("비교 사례 수집 완료", count=len(comparables))

        except Exception:
            logger.warning("비교 사례 수집 실패", address=address)

        await molit.close()
        return comparables

    def _build_comparable_evidence(
        self,
        comparables: list[dict[str, Any]],
    ) -> str | None:
        """P3: MOLIT 실거래 비교 사례를 LLM 근거 문자열로 변환.

        실거래 상위 5건을 평당가와 함께 요약한다. 합성(synthetic) 사례는 환각
        방지를 위해 제외하고 실거래만 인용한다. 실거래가 없으면 None.
        """
        if not comparables:
            return None
        rows: list[str] = []
        for c in comparables[:5]:
            if c.get("synthetic"):
                continue
            price = c.get("price_10k_won")
            area = c.get("area_m2")
            if not price or not area:
                continue
            try:
                per_pyeong = int(price / (area / 3.305785))
            except (ZeroDivisionError, TypeError):
                continue
            name = c.get("building_name", "")
            date = c.get("deal_date", "")
            rows.append(
                f"  · {name} {area}㎡ {price:,}만원"
                f"(평당 약 {per_pyeong:,}만원, {date})"
            )
        if not rows:
            return None
        body = "\n".join(rows)
        return (
            f"- MOLIT 실거래 비교 사례(실거래 {len(rows)}건):\n{body}\n"
            "  위 실거래가와 추정 시세를 비교해 적정성을 평가할 것."
        )

    # ── V-World 공간 데이터 조회 ──

    async def _fetch_spatial_data(
        self,
        pnu: str = "",
        address: str = "",
    ) -> dict[str, Any]:
        """V-World API에서 필지 공간 데이터를 조회한다.

        반환 키:
        - land_official_price: 공시지가 (원/㎡)
        - floor_area_ratio: 용적률 상한 (%)
        - building_coverage_ratio: 건폐율 상한 (%)
        - distance_to_subway_m: 최근접 지하철역 추정 거리 (m)
        - distance_to_school_m: 최근접 학교 추정 거리 (m)
        - school_score: 학군 점수 (0~100)
        - noise_db: 소음 추정치 (dB)
        - view_score: 조망 점수 (0~100)
        """
        import asyncio

        from apps.api.integrations.vworld_client import VWorldClient

        result: dict[str, Any] = {
            "land_official_price": 0,
            "floor_area_ratio": 0.0,
            "building_coverage_ratio": 0.0,
            "distance_to_subway_m": 500.0,
            "distance_to_school_m": 300.0,
            "school_score": 75.0,
            "noise_db": 55.0,
            "view_score": 60.0,
        }

        if not pnu and not address:
            return result

        vworld = VWorldClient()
        try:
            # 1) 용도지역 + 토지정보 병렬 조회
            tasks: list[Any] = []
            if pnu:
                tasks.append(vworld.get_land_use_zone(pnu))
                tasks.append(vworld.get_land_info(pnu))
            else:
                tasks.append(asyncio.sleep(0))
                tasks.append(asyncio.sleep(0))

            # 2) 좌표 조회 (지하시설물/POI 거리 추정용)
            if address:
                tasks.append(vworld.geocode(address))
            else:
                tasks.append(asyncio.sleep(0))

            gather_results = await asyncio.gather(*tasks, return_exceptions=True)

            land_use_raw = gather_results[0]
            land_info_raw = gather_results[1]
            geocode_raw = gather_results[2]

            # 용도지역 파싱
            if isinstance(land_use_raw, dict):
                result["floor_area_ratio"] = land_use_raw.get("far_limit", 0.0)
                result["building_coverage_ratio"] = land_use_raw.get("bcr_limit", 0.0)

            # 공시지가 파싱
            if isinstance(land_info_raw, dict):
                price_data = (
                    land_info_raw.get("response", {})
                    .get("body", {})
                    .get("items", {})
                    .get("item", {})
                )
                if isinstance(price_data, dict):
                    result["land_official_price"] = int(
                        price_data.get("pblntfPclnd", 0) or 0
                    )

            # 좌표 기반 POI 거리 및 환경 점수 추정
            if isinstance(geocode_raw, dict) and geocode_raw.get("lat", 0) != 0.0:
                lat = geocode_raw["lat"]
                lon = geocode_raw["lon"]
                poi_scores = self._estimate_poi_scores(lat, lon)
                result.update(poi_scores)

                # 지하시설물 조회로 인프라 밀도 기반 소음/조망 보정
                try:
                    facilities = await vworld.get_underground_facilities(lat, lon)
                    result.update(
                        self._adjust_env_scores_by_infra(facilities, result),
                    )
                except Exception:
                    pass  # 지하시설물 조회 실패 시 기본값 유지

        except Exception:
            logger.warning("V-World 공간 데이터 조회 실패", pnu=pnu)

        await vworld.close()
        return result

    @staticmethod
    def _estimate_poi_scores(lat: float, lon: float) -> dict[str, float]:
        """좌표 기반 POI 거리 및 학군/조망 점수를 추정한다.

        실제 POI DB 연동 전까지 위치 기반 경험적 추정을 사용한다:
        - 서울 도심(위도 37.5±0.05, 경도 127.0±0.05): 교통/학군 밀집 → 거리 짧음
        - 수도권 외곽: 거리 증가, 학군 점수 감소
        """
        # 서울 도심(시청) 기준 위경도 차이
        delta_lat = abs(lat - 37.5665)
        delta_lon = abs(lon - 126.9780)
        distance_from_center_km = (
            (delta_lat * 111.0) ** 2 + (delta_lon * 88.8) ** 2
        ) ** 0.5

        # 지하철역 거리: 도심 200m, 외곽으로 갈수록 증가 (최대 2,000m)
        subway_dist = min(2000.0, 200.0 + distance_from_center_km * 80.0)

        # 학교 거리: 도심 150m, 외곽 증가 (최대 1,500m)
        school_dist = min(1500.0, 150.0 + distance_from_center_km * 50.0)

        # 학군 점수: 도심 90점, 외곽으로 감소 (최저 40점)
        school_score = max(40.0, 90.0 - distance_from_center_km * 3.0)

        # 조망 점수: 도심 50(빌딩 밀집), 외곽 70+ (탁 트인 뷰)
        view_score = min(90.0, 50.0 + distance_from_center_km * 2.0)

        return {
            "distance_to_subway_m": round(subway_dist, 1),
            "distance_to_school_m": round(school_dist, 1),
            "school_score": round(school_score, 1),
            "view_score": round(view_score, 1),
        }

    @staticmethod
    def _adjust_env_scores_by_infra(
        facilities: list[dict[str, Any]],
        current: dict[str, Any],
    ) -> dict[str, float]:
        """지하시설물 밀도로 소음/조망 점수를 보정한다.

        인프라 밀집 지역 → 도시화 정도 높음 → 소음 ↑, 조망 ↓
        """
        infra_count = len(facilities)
        base_noise = float(current.get("noise_db", 55.0))
        base_view = float(current.get("view_score", 60.0))

        # 시설 10개 이상이면 밀집 도심 → 소음 증가
        noise_adjust = min(15.0, infra_count * 1.5)
        view_adjust = min(20.0, infra_count * 2.0)

        return {
            "noise_db": round(min(80.0, base_noise + noise_adjust), 1),
            "view_score": round(max(20.0, base_view - view_adjust), 1),
        }

    # ── CTGAN 콜드스타트 합성 데이터 ──

    @staticmethod
    def _generate_synthetic_comparables(
        area_sqm: float,
        n_samples: int = 30,
    ) -> list[dict[str, Any]]:
        """CTGAN으로 합성 비교 사례를 생성한다 (콜드스타트 대응).

        비교 사례 3건 미만일 때 호출된다.
        CTGAN 학습 실패 시 통계 분포 기반 폴백을 사용한다.
        """
        try:
            import pandas as pd
            from ctgan import CTGAN

            # 시드 데이터: 면적/가격 기본 분포
            seed_data = pd.DataFrame({
                "area_m2": [area_sqm * (0.85 + i * 0.03) for i in range(10)],
                "price_10k_won": [int(area_sqm * 500 * (0.9 + i * 0.02)) for i in range(10)],
                "floor": [i % 20 + 1 for i in range(10)],
                "building_age": [i * 2 + 1 for i in range(10)],
            })

            ctgan = CTGAN(epochs=100, verbose=False)
            ctgan.fit(seed_data, discrete_columns=["floor"])
            synthetic = ctgan.sample(n_samples)

            return [
                {
                    "area_m2": float(row["area_m2"]),
                    "price_10k_won": int(row["price_10k_won"]),
                    "floor": int(row["floor"]),
                    "building_age": int(row["building_age"]),
                    "synthetic": True,
                }
                for _, row in synthetic.iterrows()
            ]
        except Exception:
            logger.debug("CTGAN 합성 실패 — 통계 분포 폴백")
            import random

            rng = random.Random(42)  # noqa: S311
            return [
                {
                    "area_m2": area_sqm + rng.gauss(0, area_sqm * 0.1),
                    "price_10k_won": int(area_sqm * 500 * (1 + rng.gauss(0, 0.1))),
                    "floor": rng.randint(1, 20),
                    "building_age": rng.randint(1, 30),
                    "synthetic": True,
                }
                for _ in range(n_samples)
            ]

    # ── 16개 특징 벡터 생성 ──

    async def _build_features(
        self,
        request: AVMRequest,
        comparables: list[dict[str, Any]],
    ) -> dict[str, float]:
        """16개 특성 벡터를 생성한다.

        기존 4개:
          area_sqm, building_age_years, floor, comparable_count

        추가 12개:
          total_floors, distance_to_subway_m, distance_to_school_m,
          land_official_price, recent_trans_avg_10k, floor_area_ratio,
          building_coverage_ratio, school_score, noise_db, view_score,
          month_sin, month_cos
        """
        now = datetime.now(tz=UTC)

        # 기존 4개
        features: dict[str, float] = {
            "area_sqm": request.area_sqm,
            "building_age_years": float(request.building_age_years or 0),
            "floor": float(request.floor or 1),
            "comparable_count": float(len(comparables)),
        }

        # 추가: total_floors
        features["total_floors"] = float(request.total_floors or 15)

        # 추가: 공간 데이터 (V-World — 용도지역/공시지가/POI 거리/환경 점수)
        spatial = await self._fetch_spatial_data(
            pnu=request.pnu or "",
            address=request.address,
        )
        features["land_official_price"] = float(spatial["land_official_price"])
        features["floor_area_ratio"] = spatial["floor_area_ratio"]
        features["building_coverage_ratio"] = spatial["building_coverage_ratio"]

        # 추가: 최근 실거래 평균 (만원 단위)
        if comparables:
            prices = [c["price_10k_won"] for c in comparables if c.get("price_10k_won", 0) > 0]
            features["recent_trans_avg_10k"] = sum(prices) / len(prices) if prices else 0.0
        else:
            features["recent_trans_avg_10k"] = 0.0

        # 추가: VWorld 좌표 기반 POI 거리 및 환경 점수
        features["distance_to_subway_m"] = spatial["distance_to_subway_m"]
        features["distance_to_school_m"] = spatial["distance_to_school_m"]
        features["school_score"] = spatial["school_score"]
        features["noise_db"] = spatial["noise_db"]
        features["view_score"] = spatial["view_score"]

        # 추가: 월별 계절성 (sin/cos 인코딩)
        month = now.month
        features["month_sin"] = math.sin(2 * math.pi * month / 12)
        features["month_cos"] = math.cos(2 * math.pi * month / 12)

        return features

    # ── 신뢰도 계산 ──

    def _calculate_confidence(
        self,
        comparable_count: int,
        model_stage: str,
    ) -> float:
        """모델 단계 + 비교 사례 수 기반 신뢰도를 산출한다."""
        base = _BASE_CONFIDENCE.get(model_stage, 0.40)

        # 비교 사례 수 보정
        if comparable_count >= 50:
            base += 0.05
        elif comparable_count >= 10:
            base += 0.02
        elif comparable_count <= 3:
            base -= 0.10

        return max(0.10, min(0.98, base))

    # ── 단순 추정 폴백 ──

    @staticmethod
    def _simple_price_estimate(
        area_sqm: float,
        comparables: list[dict[str, Any]],
        features: dict[str, float],
    ) -> float:
        """비교 사례 기반 단순 추정 (모델 미가용 시 폴백).

        1순위: 비교 사례 평균 가격
        2순위: 공시지가 × 면적 × 보정계수
        3순위: 면적 × 500만원 (최종 폴백)
        """
        # 1순위: 비교 사례 평균
        if comparables:
            prices = [c["price_10k_won"] for c in comparables if c.get("price_10k_won", 0) > 0]
            if prices:
                avg_price_10k = sum(prices) / len(prices)
                return float(avg_price_10k * 10_000)  # 만원 → 원

        # 2순위: 공시지가 기반 (공시지가 × 면적 × 1.5 보정)
        official_price = features.get("land_official_price", 0)
        if official_price > 0:
            return official_price * area_sqm * 1.5

        # 3순위: 면적 기반 최종 폴백
        return area_sqm * 5_000_000

    # ── 메인 추정 ──

    async def estimate(self, request: AVMRequest, tenant_id: UUID) -> AVMValuationResponse:
        """시세를 추정한다."""
        logger.info("AVM 시세 추정 시작", project_id=str(request.project_id))

        await self._load_model()

        # 1. 비교 사례 수집
        comparables = await self._fetch_comparables(
            request.address,
            request.area_sqm,
            lawd_cd=request.lawd_cd or "",
        )

        # 1-1. 콜드스타트: 비교사례 3건 미만이면 CTGAN 합성 보강
        if len(comparables) < 3:
            logger.info("콜드스타트 감지 — CTGAN 합성 데이터 생성", count=len(comparables))
            synthetic = self._generate_synthetic_comparables(request.area_sqm)
            comparables.extend(synthetic)

        # 2. 16개 특성 벡터 생성
        features = await self._build_features(request, comparables)

        # 3. 모델 추론
        model_version = f"xgboost-v1-{self._model_stage}"

        if self._model is not None and self._model_stage != "fallback":
            try:
                import pandas as pd

                feature_df = pd.DataFrame([features])
                predicted_price = float(self._model.predict(feature_df)[0])
            except Exception:
                logger.warning("모델 추론 실패 — 단순 추정 폴백")
                predicted_price = self._simple_price_estimate(
                    request.area_sqm, comparables, features,
                )
                model_version = "simple-estimate-fallback"
        else:
            predicted_price = self._simple_price_estimate(
                request.area_sqm, comparables, features,
            )
            model_version = "simple-estimate-fallback"

        price_per_sqm = predicted_price / request.area_sqm if request.area_sqm > 0 else 0
        confidence = self._calculate_confidence(len(comparables), self._model_stage)

        # 4. 비교 사례 상위 3건 선택
        top_comparables = comparables[:3]

        # 5. DB 저장
        valuation = AVMValuation(
            tenant_id=tenant_id,
            project_id=request.project_id,
            estimated_price=predicted_price,
            price_per_sqm=price_per_sqm,
            confidence_score=confidence,
            comparable_count=len(comparables),
            model_version=model_version,
            feature_importance=features,
            comparables=top_comparables,
        )
        self.db.add(valuation)
        await self.db.commit()
        await self.db.refresh(valuation)

        logger.info(
            "AVM 시세 추정 완료",
            valuation_id=str(valuation.id),
            estimated_price=predicted_price,
            confidence=confidence,
            model=model_version,
            comparables=len(comparables),
        )

        # LLM(Claude) 자연어 해석 — 실패해도 기존 AVM 결과는 정상 반환(graceful fallback)
        narrative: dict[str, Any] = {}
        try:
            from app.services.ai.avm_interpreter import AvmInterpreter

            interp_input = {
                "estimated_value": {
                    "value_won": round(predicted_price, 2),
                    "value_per_sqm_won": round(price_per_sqm, 2),
                    "confidence_score": round(confidence, 4),
                    "valuation_date": str(valuation.created_at),
                },
                "comparables": top_comparables,
                "address": request.address,
                "area_sqm": request.area_sqm,
            }
            # P3: 이미 조회한 MOLIT 실거래 비교사례를 LLM 근거로 주입(키·async는
            # 이 서비스 책임). 합성 폴백 사례는 근거에서 제외(실거래만 인용).
            evidence_text = self._build_comparable_evidence(top_comparables)
            interp = await AvmInterpreter().generate_interpretation(
                interp_input, evidence_text=evidence_text
            )
            if isinstance(interp, dict):
                narrative = interp
        except Exception as e:  # noqa: BLE001
            logger.warning("AVM AI 해석 생성 스킵", error=str(e)[:120])

        return AVMValuationResponse(
            id=valuation.id,
            project_id=valuation.project_id,
            estimated_price=valuation.estimated_price,
            price_per_sqm=valuation.price_per_sqm,
            confidence_score=valuation.confidence_score,
            comparable_count=valuation.comparable_count,
            model_version=valuation.model_version,
            created_at=valuation.created_at,
            valuation_narrative=narrative.get("valuation_narrative"),
            comparable_explanation=narrative.get("comparable_explanation"),
            market_position=narrative.get("market_position"),
            appreciation_outlook=narrative.get("appreciation_outlook"),
            investment_recommendation=narrative.get("investment_recommendation"),
        )

    # ── MAPE 검증 ──

    @staticmethod
    def validate_mape(predictions: list[float], actuals: list[float]) -> dict:
        """MAPE(Mean Absolute Percentage Error)를 산출한다.

        예측값과 실제값의 평균 절대 백분율 오차를 계산하여
        모델 성능이 허용 범위(5%) 이내인지 판정한다.

        Args:
            predictions: 예측값 리스트
            actuals: 실제값 리스트

        Returns:
            {"mape_pct": float, "is_acceptable": bool, "threshold_pct": 5.0}

        Raises:
            ValueError: 리스트가 비어있거나 길이가 다를 때
            ZeroDivisionError: 실제값에 0이 포함될 때
        """
        if not predictions or not actuals:
            raise ValueError("predictions와 actuals는 비어있을 수 없습니다.")
        if len(predictions) != len(actuals):
            raise ValueError("predictions와 actuals의 길이가 같아야 합니다.")

        for i, actual in enumerate(actuals):
            if actual == 0:
                raise ZeroDivisionError(f"actuals[{i}]가 0이므로 MAPE를 계산할 수 없습니다.")

        n = len(predictions)
        mape = sum(abs(actual - pred) / abs(actual) for pred, actual in zip(predictions, actuals)) / n * 100
        threshold = 5.0

        return {
            "mape_pct": round(mape, 4),
            "is_acceptable": mape <= threshold,
            "threshold_pct": threshold,
        }

    # ── 지역별 시장 보정 계수 ──

    @staticmethod
    def _apply_regional_weight(base_value: float, region_code: str) -> float:
        """17개 지역별 시장 보정 계수를 적용한다.

        강남, 서초 등 프리미엄 지역은 가중치 > 1.0,
        외곽 지역은 < 1.0 으로 시세를 보정한다.

        Args:
            base_value: 보정 전 기본 시세
            region_code: 지역 코드 (예: "강남", "서초", "부산" 등)

        Returns:
            보정된 시세
        """
        weights: dict[str, float] = {
            "강남": 1.15,
            "서초": 1.12,
            "송파": 1.08,
            "마포": 1.05,
            "용산": 1.10,
            "성동": 1.03,
            "영등포": 1.02,
            "강서": 0.98,
            "노원": 0.95,
            "도봉": 0.93,
            "인천": 0.90,
            "수원": 0.92,
            "성남": 1.00,
            "고양": 0.88,
            "부산": 0.85,
            "대구": 0.83,
            "기타": 0.80,
        }
        weight = weights.get(region_code, weights["기타"])
        return base_value * weight

    # ── 외부 API 재시도 ──

    async def _fetch_with_retry(self, fetch_fn, *args, max_retries: int = 3) -> Any:
        """외부 API 호출을 재시도한다 (exponential backoff).

        1초, 2초, 4초 간격으로 재시도하며,
        최대 재시도 횟수 초과 시 마지막 예외를 다시 발생시킨다.

        Args:
            fetch_fn: 호출할 비동기 함수
            *args: 함수에 전달할 인자
            max_retries: 최대 재시도 횟수 (기본 3)

        Returns:
            fetch_fn의 반환값

        Raises:
            Exception: 최대 재시도 횟수 초과 시 마지막 예외
        """
        import asyncio

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return await fetch_fn(*args)
            except Exception as e:
                last_error = e
                logger.warning(
                    "외부 API 호출 실패",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e),
                )
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s

        raise last_error  # type: ignore[misc]
