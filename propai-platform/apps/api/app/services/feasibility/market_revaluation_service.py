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


#: `sale_price_source` 가 가질 수 있는 **전체 어휘**(선언).
#:
#: ★왜 선언을 두나: 프론트가 이 값을 한글로 바꾸는데, 그 매핑이 **손 목록**이라
#:   백엔드가 값을 추가하면 화면에 **raw 토큰**이 나온다(실측: `avm_blended`·
#:   `national_default_fallback` 이 이미 빠져 있었다). 정규식으로 소스를 긁는 방식은
#:   **위양성 투성이**였다(키 이름 자체·다른 필드의 값까지 집었다) — 그래서 **선언**한다.
#:
#: ★★선언은 자기를 검증하지 않는다 — `tests/test_sale_price_source_vocab.py` 가
#:   **생산자(ast)와 이 선언의 정합**을 잠근다. 선언만 두면 그것이 다음 거짓말이 된다.
#:
#: `single_source:` 는 **접두 계열**이다(하위 출처가 늘어난다) — 소비처는 접두로 처리한다.
SALE_PRICE_SOURCE_VOCAB: tuple[str, ...] = (
    "market_blended",
    "avm_blended",
    "single_source:",          # ★접두 — `single_source:<source key>`
    "regional_market_table",
    "national_default_fallback",
    "cost_based_fallback",
    "user",
    # ★"unavailable" 은 뺐다 — **아무도 안 낸다**(락이 「죽은 어휘」로 잡았다).
    #   선언에만 있는 값은 다음 사람에게 «있는 것» 으로 읽힌다.
)


def _blend_label(sources: list[dict[str, Any]], has_avm: bool, price: float) -> str | None:
    """`sale_price_source` — **실제로 무엇이 섞였는지**를 말한다.

    | 상황 | 라벨 |
    |---|---|
    | 산출 불가 | `None` |
    | 출처 **2개 이상** + AVM 기여 | `avm_blended` |
    | 출처 **2개 이상** | `market_blended` |
    | ★출처 **1개뿐** | `single_source:<key>` — «블렌딩» 이 아니다 |

    ★마지막 줄이 이 함수의 존재 이유다. 실거래가 빠지고 지역 테이블만 남은 상태를
      `market_blended` 라 부르면 **없는 근거를 주장하는 것**이고, 그 차이가 −39% 였다.
    """
    if price <= 0:
        return None
    if len(sources) >= 2:
        return "avm_blended" if has_avm else "market_blended"
    only = (sources[0].get("source") if sources else None) or "unknown"
    return f"single_source:{only}"


class MarketRevaluationService:
    """다중 출처 신뢰도 가중 시장 재평가."""

    async def revalue(self, *, address: str, building_type: str | None = None,
                      lawd_cd: str | None = None, land_area_sqm: float | None = None,
                      include_avm: bool = True, dev_type: str = "M01") -> dict[str, Any]:
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

        # 2) MOLIT 실거래 — ★**공용 SSOT 리졸버**를 경유한다(`sale_price_resolver`).
        #
        # ★★종전엔 `_molit_avg_per_pyeong` 이 **전용면적 기준 기존아파트 매매가**를
        #   그대로 돌려줬고, 위 `regional` 은 **공급면적 기준 신축 분양가**다
        #   (`regional_pricing` 첫 줄: *"지역 × 개발유형별 평균 **분양가**(원/평)"*).
        #   **단위도 상품도 다른 두 수를 가중 블렌딩**하고 있었고, 그 결과가
        #   `project_pipeline` 에서 **지역 테이블보다 우선해** 분양가로 쓰였다.
        #
        #   라이브 실측(2026-09-04 · 같은 주소 5곳 · 컨테이너 내부):
        #     강남 역삼 100.8M vs 공용 리졸버 64.8M  → **+56%**
        #     부산 해운대 22.4M vs 28.5M            → **−21%**
        #   ★부호가 일정하지 않은 이유는 **두 오류가 부분 상쇄**되기 때문이다
        #     (전용→공급 미변환은 상방 · 시군구 평균 ↔ 동 중앙값은 지역마다 부호가 다름).
        #     **그래서 조용했다.**
        #
        # 공용 리졸버는 ①**동** 우선(시군구 폴백) ②**중앙값**(평균은 강남에서 1.56배로 튄다)
        # ③최근 **8개월** ④`_MIN_TRADE_SAMPLES` **표본 하한** ⑤**전용→공급 환산 + 신축
        # 프리미엄** 을 갖는다 — 즉 `regional` 과 **같은 단위**가 된다.
        try:
            # ★`building_type` 은 `revalue()` 가 **이미 받고 있었는데 이 출처에 안 쓰였다.**
            # ★★**정정(2026-09-05)**: 앞 커밋의 주석은 이것을 넘기면 *"실제로 쓰인다"* 고
            #   **단정했는데 거짓이었다.** 파이프라인이 넘기는 값은 **한국어 표시 문자열**
            #   ("아파트"·"공동주택"…)이고 매핑 키는 **영어 정규 키**라 전부 미스했다.
            #   더 나쁜 것은 그 문자열이 truthy 라 `dev_type` 폴백까지 **억제**해
            #   **넘기는 것이 안 넘기는 것보다 나빴다**는 점이다.
            #   → 리졸버가 `_canonical_building()` 으로 **경계에서 정규화**한다.
            molit = await self._molit_sale_price_source(
                address=address, dev_type=dev_type, lawd_cd=lawd_cd,
                building_type=building_type)
            if molit and molit["price_per_pyeong"] > 0:
                sources.append(molit)
        except Exception as e:  # noqa: BLE001
            logger.warning("revalue.molit_failed", error=str(e)[:120])

        # 3) AVM 모델 추정 (R5) — MLflow Production/Staging 등록 모델이 있을 때만 합류.
        #    모델 미등록·로드 실패·예측 실패 등 어떤 실패에도 기존 동작 완전 동일(graceful).
        if include_avm:
            try:
                avm = await self._avm_source(
                    address=address, lawd_cd=lawd_cd,
                    dev_type=dev_type, building_type=building_type)
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
            # ★★그리고 **블렌딩이 안 됐으면 「블렌딩」이라 말하지 않는다.**
            #   종전엔 출처가 `regional` **하나**만 남아도 `market_blended` 였다 —
            #   적대 리뷰 실측: VWorld 장애 시 실거래가 통째로 빠져 **−39%**(36.05M → 22.00M)
            #   로 하드코딩 테이블에 떨어지는데 라벨은 그대로였다. **실패가 자기를 구별하지
            #   못하면 조사자도 사용자도 원인을 못 본다**(§유료 산출물 규율 4).
            "sale_price_source": _blend_label(sources, has_avm, price),
        }

    async def _avm_source(
        self, *, address: str, lawd_cd: str | None,
        dev_type: str = "M01", building_type: str | None = None,
    ) -> dict[str, Any] | None:
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

        # ★★AVM 도 **전용면적 기준 기존아파트 매매가**다 — MOLIT `area_m2`(전용) +
        #   `price_10k_won`(매매)로 학습·비교한다. 그런데 이 블렌딩의 다른 출처는
        #   **공급면적 기준 신축 분양가**다(`regional`·`molit_real`).
        #   즉 `molit_real` 에서 고친 **바로 그 단위 불일치**가 여기 그대로 남아 있었다 —
        #   **모집단이 3인데 2로 세고 고쳤다**(적대 리뷰 M-3).
        #
        # ★라이브 실측(2026-09-05): 이 출처는 지금 **휴면**이다 —
        #   `_avm_source` 반환 `None` · 모델 미등록(`stage=fallback`).
        #   그래도 고치는 이유: **누가 모델을 등록하는 순간 발화하는 지뢰**이고,
        #   그때는 «왜 분양가가 튀었나» 를 이 자리에서 찾기 어렵다.
        #
        # ★환산은 **공용 헬퍼를 경유**한다 — 여기서 다시 쓰면 그것이 **세 번째 산식**이 되고,
        #   세 산식은 반드시 갈린다(이 PR 이 고치는 결함의 정확한 형태).
        from app.services.feasibility.sale_price_resolver import (
            _exclusive_ratio_for,
            _new_build_premium,
        )

        exclusive_pp = predicted_won / (_AVM_REF_AREA_SQM / _PYEONG)
        ratio, ratio_note = _exclusive_ratio_for(dev_type, building_type)
        premium = _new_build_premium()
        price_per_pyeong = exclusive_pp * ratio * premium
        confidence = int(round(
            svc._calculate_confidence(len(real_comps), svc._model_stage) * 100,
        ))
        return {
            "source": "avm", "label": f"AVM 모델 추정({svc._model_stage})",
            "price_per_pyeong": round(price_per_pyeong),
            "confidence": confidence, "weight": _AVM_WEIGHT,
            "count": len(real_comps),
            "note": (f"XGBoost {svc._model_stage} 모델, 전용 {_AVM_REF_AREA_SQM:.0f}㎡ 기준 "
                     f"{round(exclusive_pp):,}원/평 × {ratio_note} × 신축 프리미엄 {premium} "
                     f"→ 공급 평당가"),
        }

    async def _molit_sale_price_source(
        self, *, address: str, dev_type: str = "M01", lawd_cd: str | None = None,
        building_type: str | None = None,
    ) -> dict[str, Any] | None:
        """MOLIT 실거래 → **공급면적 기준 신축 분양가**(원/평). 공용 SSOT 경유.

        ★산식을 여기서 다시 쓰지 않는다 — `sale_price_resolver` 가 정본이다.
          여기서 재구현하면 **또 갈린다**(그것이 이 함수가 대체하는 결함이었다).

        표본 하한 미달·조회 실패면 `None` → 이 출처는 블렌딩에서 **자동 제외**되고
        전체 신뢰도가 낮아진다(기존 best-effort 계약 유지).
        """
        from app.services.feasibility.sale_price_resolver import _trade_sale_price_per_pyeong

        # ★`lawd_cd` 를 넘긴다 — 호출부가 이미 PNU 에서 얻은 값이다. 안 넘기면 리졸버가
        #   VWorld 지오코딩으로 **재도출**하고, 그 장애가 분양가 붕괴로 전파된다(C-1).
        res = await _trade_sale_price_per_pyeong(
            dev_type=dev_type, address=address, sigungu5=(lawd_cd or "")[:5] or None,
            building_type=building_type)
        if not res:
            return None
        price, _src, basis, _deg, n = res
        # ★0·음수는 출처로 싣지 않는다. **MAJOR-4 를 고치며 이 가드를 지웠고**,
        #   내 경계 락(`test_sample_floor_propagates…`)이 그것을 잡았다.
        #   *봉합이 다른 가드를 밟는다 — 그래서 경계는 양방향으로 잠근다.*
        if not price or price <= 0:
            return None
        return {
            "source": "molit_real", "label": "주변 실거래(MOLIT)",
            "price_per_pyeong": float(price),
            # ★신뢰도는 **고정 92 가 아니다** — 종전 `min(92, 50+건수)` 는 건수만 봤고
            #   표본 하한도 없었다. 공용 리졸버가 하한을 통과시킨 것만 돌려주므로
            #   여기서는 그 사실을 반영해 92 를 쓴다(하한 미달은 애초에 None 이다).
                        # ★신뢰도는 **표본수의 함수**다. 고정 92 는 근거가 없었다 —
            #   내가 단 근거는 *"리졸버가 하한을 통과시킨 것만 돌려주므로"* 였는데
            #   **그 하한은 5** 이지 옛 식 `min(92, 50+건수)` 가 92 에 닿는 42 가 아니다.
            #   근거가 결론을 지탱하지 못했다(적대 리뷰 M-4).
            #   실측: n=5 에서 블렌딩 신뢰도가 **+24pt** 부풀었고, 그 값은
            #   `project_pipeline` 의 `sale_price_confidence`("분양가 신뢰도(%)")로
            #   **사용자에게 나간다.**
            "confidence": min(92, 50 + n), "weight": 0.65, "count": n, "note": basis[:120],
        }

    async def _molit_avg_per_pyeong(self, lawd_cd: str | None) -> dict[str, Any] | None:
        """★**사용 중지**(2026-09-04) — 단위 불일치로 `_molit_sale_price_source` 로 대체됐다.

        전용면적 기준 **매매가**를 공급면적 기준 **분양가** 자리에 넣고 있었다.
        삭제하지 않고 남기는 이유: 이 함수를 부르는 다른 곳이 없음을 파생형 락이 단언하고,
        **왜 쓰지 않는지**가 코드에 남아야 다음 사람이 되살리지 않는다.

        MOLIT 아파트 실거래 최근 평균 평당가(만원). lawd_cd 없으면 None.
        """
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
