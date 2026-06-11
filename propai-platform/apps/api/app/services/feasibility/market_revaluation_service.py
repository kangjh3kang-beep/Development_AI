"""시장 재평가 엔진(F1) — 다중 시장가 출처를 신뢰도 가중으로 블렌딩.

단일 출처(regional_market_table)에 의존하던 분양가를, 여러 시장 신호를 신뢰도점수(0~100)로
가중 블렌딩해 "그때그때 현실을 반영한" 평당 분양가로 산출한다. 각 출처는 best-effort —
실패/희소하면 자동 제외되고 전체 신뢰도가 낮아진다(정직). 산출에는 timestamp가 붙어
분석원장(해시체인)에 가정버전으로 기록된다.

출처(현재):
  - regional   : 지역 시장표준 단가표(항상)
  - molit_real : MOLIT 실거래 최근 평균 평당가(있으면 — 가장 강한 시장신호)
  - avm        : 레거시 AVM(MLflow Production/Staging 등록 모델) 평당가 추정
                 (R5 — 등록 모델이 있을 때만 합류, 없으면/실패 시 기존 동작 완전 동일)
확장 예정: 청약홈 분양가, 시세지수 추세.

결과 dict의 `sale_price_source`: AVM이 실제 블렌딩에 기여하면 "avm_blended",
그 외 블렌딩 성공 시 "market_blended", 산출 불가 시 None (정직 표기).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_PYEONG = 3.3058

# ── AVM 블렌딩 상수 (R5) ──
_AVM_REF_AREA_SQM = 84.0  # 국민평형 전용면적 — 평당가 환산 기준
_AVM_WEIGHT = 0.5  # regional(0.35) < avm(0.5) < molit_real(0.65)

# AVM 모델 로드 캐시: 성공 시 서비스 인스턴스 재사용, 실패 시 쿨다운 동안 재시도 생략
# (MLflow 다운 시 매 수지분석마다 재시도 지연이 파이프라인에 전파되는 것 방지).
_avm_cache: dict[str, Any] = {"svc": None, "failed_at": 0.0}
_AVM_FAIL_COOLDOWN_S = 600.0


def _blend(sources: list[dict[str, Any]]) -> tuple[float, int]:
    """신뢰도×가중 평균으로 평당가·종합신뢰도 산출."""
    usable = [s for s in sources if s.get("price_per_pyeong") and s["price_per_pyeong"] > 0]
    if not usable:
        return 0.0, 0
    wsum = sum((s["confidence"] / 100.0) * s["weight"] for s in usable)
    if wsum <= 0:
        return 0.0, 0
    price = sum(s["price_per_pyeong"] * (s["confidence"] / 100.0) * s["weight"] for s in usable) / wsum
    # 종합신뢰도: 출처별 신뢰도의 가중평균 + 출처 다양성 보너스(최대 +10).
    base_conf = sum(s["confidence"] * s["weight"] for s in usable) / sum(s["weight"] for s in usable)
    diversity = min(10, (len(usable) - 1) * 6)
    return round(price), int(min(100, base_conf + diversity))


class MarketRevaluationService:
    """다중 출처 신뢰도 가중 시장 재평가."""

    async def revalue(self, *, address: str, building_type: str | None = None,
                      lawd_cd: str | None = None, land_area_sqm: float | None = None,
                      include_avm: bool = True) -> dict[str, Any]:
        sources: list[dict[str, Any]] = []

        # 1) 지역 시장표준 단가표(항상 시도)
        try:
            from app.services.feasibility.regional_pricing import get_regional_sale_price_per_pyeong
            rp = get_regional_sale_price_per_pyeong(address=address)
            if rp and rp > 0:
                sources.append({
                    "source": "regional", "label": "지역 시장표준",
                    "price_per_pyeong": float(rp), "confidence": 55, "weight": 0.35,
                    "count": None, "note": "지역·용도 표준단가",
                })
        except Exception as e:  # noqa: BLE001
            logger.warning("revalue.regional_failed", error=str(e)[:120])

        # 2) MOLIT 실거래 최근 평균 평당가(있으면)
        try:
            molit = await self._molit_avg_per_pyeong(lawd_cd)
            if molit and molit["price_per_pyeong"] > 0:
                sources.append(molit)
        except Exception as e:  # noqa: BLE001
            logger.warning("revalue.molit_failed", error=str(e)[:120])

        # 3) AVM 모델 추정 (R5) — MLflow Production/Staging 등록 모델이 있을 때만 합류.
        #    모델 미등록·로드 실패·예측 실패 등 어떤 실패에도 기존 동작 완전 동일(graceful).
        if include_avm:
            try:
                avm = await self._avm_source(address=address, lawd_cd=lawd_cd)
                if avm and avm["price_per_pyeong"] > 0:
                    sources.append(avm)
            except Exception as e:  # noqa: BLE001
                logger.warning("revalue.avm_failed", error=str(e)[:120])

        price, confidence = _blend(sources)
        has_avm = any(s.get("source") == "avm" for s in sources)
        return {
            "price_per_pyeong": price,
            "confidence": confidence,
            "sources": sources,
            "blended_at": datetime.now().isoformat(timespec="seconds"),
            "available": price > 0,
            # R5 정직 표기: AVM이 실제 블렌딩에 기여했을 때만 avm_blended
            "sale_price_source": (
                ("avm_blended" if has_avm else "market_blended") if price > 0 else None
            ),
        }

    async def _avm_source(self, *, address: str, lawd_cd: str | None) -> dict[str, Any] | None:
        """레거시 AVM(MLflow 등록 모델)으로 평당가를 추정해 블렌딩 소스로 반환한다.

        새 서빙 코드가 아니라 레거시 `AVMService`의 모델 로드(Production→Staging)·
        16피처·예측 경로를 그대로 재사용한다(DB 미접근 — 저장 없는 추정 전용).
        등록 모델이 없으면(stage='fallback') None을 반환해 기존 동작을 보존한다.
        예측값은 전용 84㎡(국민평형) 기준 총액(원) → 평당가(원/평)로 환산한다.
        """
        import os
        import time
        from types import SimpleNamespace

        from apps.api.services.avm_service import AVMService

        svc = _avm_cache.get("svc")
        if svc is None:
            failed_at = float(_avm_cache.get("failed_at") or 0.0)
            if failed_at > 0 and (time.monotonic() - failed_at) < _AVM_FAIL_COOLDOWN_S:
                return None  # 최근 로드 실패 — 쿨다운 동안 재시도 생략(지연 전파 방지)

            # MLflow 서버 다운 시 HTTP 재시도 지연이 수지 파이프라인에 전파되지 않게
            # 재시도/타임아웃 상한(미설정 시에만 — 사용자 설정 우선, additive).
            os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "1")
            os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "10")

            candidate = AVMService(db=None)  # type: ignore[arg-type]  # 모델로드·피처·예측만 사용
            await candidate._load_model()
            if candidate._model is None or candidate._model_stage not in ("production", "staging"):
                _avm_cache["failed_at"] = time.monotonic()
                return None
            _avm_cache["svc"] = candidate
            _avm_cache["failed_at"] = 0.0
            svc = candidate

        lawd = (lawd_cd or "").strip()[:5]
        comparables = await svc._fetch_comparables(
            address, _AVM_REF_AREA_SQM,
            lawd_cd=lawd if len(lawd) == 5 and lawd.isdigit() else "",
        )
        # 합성(synthetic) 사례 없이 실거래만 피처에 사용(가짜값 금지)
        real_comps = [c for c in comparables if not c.get("synthetic")]

        request_like = SimpleNamespace(
            area_sqm=_AVM_REF_AREA_SQM, building_age_years=None, floor=None,
            total_floors=None, pnu=None, address=address,
        )
        features = await svc._build_features(request_like, real_comps)  # type: ignore[arg-type]

        import pandas as pd

        predicted_won = float(svc._model.predict(pd.DataFrame([features]))[0])
        if predicted_won <= 0:
            return None

        price_per_pyeong = predicted_won / (_AVM_REF_AREA_SQM / _PYEONG)
        confidence = int(round(
            svc._calculate_confidence(len(real_comps), svc._model_stage) * 100,
        ))
        return {
            "source": "avm", "label": f"AVM 모델 추정({svc._model_stage})",
            "price_per_pyeong": round(price_per_pyeong),
            "confidence": confidence, "weight": _AVM_WEIGHT,
            "count": len(real_comps),
            "note": f"XGBoost {svc._model_stage} 모델, 전용 {_AVM_REF_AREA_SQM:.0f}㎡ 환산 평당가",
        }

    async def _molit_avg_per_pyeong(self, lawd_cd: str | None) -> dict[str, Any] | None:
        """MOLIT 아파트 실거래 최근 평균 평당가(만원). lawd_cd 없으면 None."""
        lawd = (lawd_cd or "")[:5]
        if len(lawd) < 5:
            return None
        from apps.api.integrations.molit_client import MolitClient
        client = MolitClient()
        # 최근 3개월 수집
        now = datetime.now()
        yms = []
        y, m = now.year, now.month
        for _ in range(3):
            m -= 1
            if m == 0:
                m, y = 12, y - 1
            yms.append(f"{y}{m:02d}")
        per_pyeong: list[float] = []
        for ym in yms:
            try:
                rows = await client.get_transactions(lawd, ym, prop_type="apt", num_rows=1000)
            except Exception:  # noqa: BLE001
                rows = []
            for r in rows:
                try:
                    price_10k = float(r.get("price_10k_won") or r.get("deal_amount") or 0)
                    area_m2 = float(r.get("area_m2") or r.get("exclusive_area") or 0)
                    if price_10k > 0 and area_m2 > 0:
                        # ★단위 통일: 만원/평 × 10,000 = 원/평 (지역표준이 원/평이라 일치시킴)
                        per_pyeong.append((price_10k / (area_m2 / _PYEONG)) * 10000)
                except Exception:  # noqa: BLE001
                    continue
        if not per_pyeong:
            return None
        # 이상치 절사(상하위 10%) 후 평균
        per_pyeong.sort()
        n = len(per_pyeong)
        trim = per_pyeong[int(n * 0.1): max(int(n * 0.1) + 1, int(n * 0.9))] or per_pyeong
        avg = sum(trim) / len(trim)
        cnt = len(per_pyeong)
        # 신뢰도: 거래건수·최근성 기반(많을수록↑, 최대 92)
        confidence = min(92, 50 + cnt)
        return {
            "source": "molit_real", "label": "MOLIT 실거래(최근3개월)",
            "price_per_pyeong": round(avg), "confidence": confidence, "weight": 0.65,
            "count": cnt, "note": f"아파트 실거래 {cnt}건 평균(상하위10% 절사)",
        }
