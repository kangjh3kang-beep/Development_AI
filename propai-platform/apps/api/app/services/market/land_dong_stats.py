"""동 단위 토지 실거래 통계 — 좌표 없이 말할 수 있는 것만 말한다.

## 왜 이 모듈이 있는가

토지 실거래는 **좌표를 만들 수 없다**. 원천(MOLIT)이 지번을 가려서 주기 때문이다
(`5*`·`1**`·`산1**`). 라이브 실측 2026-08-06: 3지역 30개월 **3,113건 전수 마스킹**.
그래서 반경 통계(100m/500m/1km)는 **원천적으로 불가능**하다 — 거리를 계산할 좌표가 없다.

그런데 원천은 **법정동·용도지역·지목을 100% 채워서 준다**(같은 실측). 토지 가격은 위치보다
용도지역이 지배적이므로, **행정구역+용도 축의 층화**가 반경을 대신할 수 있다.

★현재 토지 시세는 `공시지가 × 하드코딩 배율`(강남 1.8배 … 기본 1.2배)로만 나온다.
`field_audit/market_methodology` 가 그 사실을 P2 배지로 상시 고지하고 있다 —
"표시 토지 시세는 **항상** 공시지가×배수". 이 모듈은 그 자리에 **실거래 근거**를 놓기 위한
첫 걸음이고, 이번 단계에서는 **채택 단가를 바꾸지 않는다**(관측 먼저).

## 설계 근거 — 전부 실측으로 확정했다(2026-08-06)

- **창(window)**: 6개월로는 강남조차 무너진다(전처리 후 36건). **30개월**이면 동 단위가
  성립한다 — 강남 12조합 중앙 17건(≥5건 11/12) · 해운대 8조합 중앙 42건(≥5건 8/8).
- **층 깊이**: `동+용도지역` 은 절반만 성립(17/42 · 17/33), `동+용도+지목` 은 불가(중앙 1건).
  → 최심층을 `동+용도` 로 두고 표본이 모자라면 위로 올라간다.
- **지분거래 분리**: 지분/일반 ㎡당 중앙값 비가 **지역마다 방향까지 다르다**
  (강남 0.27배 · 해운대 0.65배 · 포항북 2.14배). 섞으면 그 값이 무엇인지 말할 수 없다.
  원천이 `shareDealingType` 으로 **명시**해 주므로 분리는 추측이 아니다.
  ★단 **중복은 제거하지 않는다** — 같은 `(동·지번·금액·면적·날짜)`가 최다 29회 반복되는데
  중복 신고인지 여럿이 나눠 산 실제 지분거래인지 **구분할 수 없다**. 구분 못 하는 것을
  지우면 실거래를 없앤다(무날조).
- **시점수정**: 30개월이면 지가가 유의하게 움직인다(R-ONE 24개월 누적 실측 1.1018 = +10%).
  월별 변동률 시계열로 각 거래를 가격시점으로 끌어올린다. 시계열이 없으면 **보정하지 않고
  그 사실을 밝힌다**(`time_adjusted=False`).

## ★수집은 이 모듈이 하지 않는다 — 쿼터 때문이다 (실측)

30개월 창이 필요한데, 수집 비용을 세 번 재측정하면서 판단이 두 번 뒤집혔다:

1. "요청마다 30개월 호출은 비현실적" — **근거 없이** 내린 추정이었다.
2. 30개월 **병렬 호출 0.7초**(30/30 성공, 개별 중앙 0.11초) → "온디맨드로 충분".
   속도만 본 판단이었다.
3. 이어서 **HTTP 429 Too Many Requests × 60건** — MOLIT 는 **일일 호출 한도**가 있고,
   30개월 × 여러 지역이면 금방 소진된다. 속도가 아니라 **쿼터**가 제약이다.

→ 그래서 이 모듈은 **순수 함수**다. 행(rows)을 받아 통계만 낸다. 수집·캐시·쿼터 정책은
  호출부의 책임이고, 그 설계가 정해지기 전에는 배선하지 않는다.
  (참고: `BaseAPIClient` 는 `HTTPStatusError` 를 재시도하므로 **429 에도 재시도**한다 —
  쿼터 초과에는 역효과다. 배선 전에 함께 손봐야 한다.)

## 이 모듈이 하지 않는 것

- 좌표를 만들지 않는다(마스킹 역산 없음 — 원천이 가린 것을 복원하지 않는다).
- 채택 단가를 바꾸지 않는다. 산출물은 **참고 통계**이고, 소비처가 그렇게 표시해야 한다.
- 표본이 모자라면 값을 만들지 않는다(`None`). 없는 것을 있다고 하지 않는다.
"""

from __future__ import annotations

import statistics
from typing import Any

from app.services.data_validation.price_stats import robust_price_stats
from app.services.market.comparable_sample import is_masked_jibun

# ── 층 정의 ────────────────────────────────────────────────────────────────
# 좁은 층부터. 표본이 모자라면 다음(넓은) 층으로 내려간다.
# ★★2026-08-08 실측으로 **지목 축을 넣었다**. 앞서 "동+용도+지목은 중앙 1건이라 성립하지
#   않는 층"이라며 뺐는데, 그 판단이 과했다 — `MIN_SAMPLE` 가드가 이미 성립 여부를 막으므로
#   **넣어 두고 안 되면 폴백**하는 것이 손해가 없다. 오히려 안 넣어서 왜곡이 남았다.
#
#   ★거래 커버율 실측(6개월·지분 제외·최소 5건):
#       강남구   동+지목 **66%** · 동+용도 15% · 동 79%
#       해운대구 동+지목 53%     · 동+용도 59% · 동 92%
#   즉 `동+지목` 이 `동+용도` 만큼(강남은 4배) 덮는다. 그리고 **지목은 가격을 자릿수로
#   가르는 축**이다(대 vs 도로). 용도지역은 배수 차이라 우선순위가 낮다.
#   → 지목을 용도지역보다 **앞에** 둔다.
#
#   ★왜곡 사례: 논현동 1-1 은 실제 **일반상업지역**이라 `동+용도` 가 실패하고 `동` 으로
#   떨어졌고, 그 통에 주거지 거래와 도로가 섞여 공시지가의 0.54배가 나왔다.
LAYERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dong_zone_jimok", ("dong", "land_use", "jimok")),
    ("dong_jimok", ("dong", "jimok")),
    ("dong_zone", ("dong", "land_use")),
    ("dong", ("dong",)),
    ("sigungu_jimok", ("jimok",)),
    ("sigungu_zone", ("land_use",)),
    ("sigungu", ()),
)

LAYER_LABELS = {
    "dong_zone_jimok": "법정동 · 용도지역 · 지목",
    "dong_jimok": "법정동 · 지목",
    "dong_zone": "법정동 · 용도지역",
    "dong": "법정동",
    "sigungu_jimok": "시군구 · 지목",
    "sigungu_zone": "시군구 · 용도지역",
    "sigungu": "시군구",
}

# 층이 성립한다고 볼 최소 표본. 실측에서 `동+용도` 의 절반이 이 선을 넘었다.
MIN_SAMPLE = 5


def _norm(v: Any) -> str:
    return str(v or "").strip()


def _unit_price_per_sqm(row: dict[str, Any]) -> float | None:
    """㎡당 단가(원). 면적·금액이 없으면 None(0으로 만들지 않는다)."""
    try:
        area = float(row.get("area_m2") or 0)
        # `price_10k_won` 은 만원 단위(molit_client 표준화 필드).
        won = int(row.get("price_10k_won") or 0) * 10_000
    except (TypeError, ValueError):
        return None
    if area <= 0 or won <= 0:
        return None
    return won / area


def _deal_ym(row: dict[str, Any]) -> str | None:
    """거래 시점 `YYYYMM`. `deal_date`(예: "2026년 7월 3일") 파싱."""
    raw = _norm(row.get("deal_date"))
    if not raw:
        return None
    digits: list[str] = []
    cur = ""
    for ch in raw:
        if ch.isdigit():
            cur += ch
        elif cur:
            digits.append(cur)
            cur = ""
    if cur:
        digits.append(cur)
    if len(digits) < 2:
        return None
    year, month = digits[0], digits[1]
    if len(year) != 4 or not month:
        return None
    return f"{year}{int(month):02d}"


def _time_factor(deal_ym: str, now_ym: str, series: list[tuple[str, float]]) -> float | None:
    """거래시점 → 가격시점 누적 변동계수. 시계열이 그 구간을 못 덮으면 None.

    ★`cumulative_factor_from_rows` 와 같은 산식(∏(1+r/100))이되, **구간을 거래시점부터**
    잡는다. 전체 누적계수 하나로 30개월치를 일괄 보정하면 최근 거래가 과보정된다.
    """
    if not series or not deal_ym or not now_ym or deal_ym > now_ym:
        return None
    seg = [r for ym, r in series if deal_ym < ym <= now_ym]
    if not seg:
        # 거래가 가장 최근 달이면 보정할 구간이 없다 — 1.0 은 "보정 불필요"라는 사실이다.
        return 1.0 if any(ym <= now_ym for ym, _ in series) else None
    factor = 1.0
    for rate in seg:
        factor *= 1 + rate / 100.0
    return factor


def _matches(row: dict[str, Any], keys: tuple[str, ...], target: dict[str, str]) -> bool:
    return all(_norm(row.get(k)) == target.get(k, "") for k in keys)


def dong_land_stats(
    rows: list[dict[str, Any]],
    *,
    target_dong: str,
    target_land_use: str = "",
    target_jimok: str = "",
    rate_series: list[tuple[str, float]] | None = None,
    now_ym: str = "",
    min_sample: int = MIN_SAMPLE,
) -> dict[str, Any] | None:
    """토지 실거래를 층화해 ㎡당 대표 단가를 낸다. 어느 층에서도 못 세면 **None**.

    반환에는 **값과 함께 그 값이 무엇인지**가 들어간다 — 어느 층에서 나왔는지(`layer`),
    표본이 몇 건인지(`sample_count`), 시점수정을 했는지(`time_adjusted`), 지분거래가
    몇 건 있었는지(`share_deal_count_excluded`). 값만 주면 소비처가 오독한다.
    """
    if not rows:
        return None

    target = {
        "dong": _norm(target_dong),
        "land_use": _norm(target_land_use),
        "jimok": _norm(target_jimok),
    }
    series = rate_series or []

    # ── 지분 분리 — 원천이 명시한 구분이라 추측이 아니다 ──
    usable: list[dict[str, Any]] = []
    share_seen = 0
    for r in rows:
        if _norm(r.get("share_dealing_type")) == "지분":
            share_seen += 1
            continue
        usable.append(r)

    for layer, keys in LAYERS:
        # 층에 필요한 타깃이 비어 있으면 그 층은 판정 불가 — 건너뛴다(빈값끼리 매칭 금지).
        if any(not target.get(k) for k in keys):
            continue
        bucket = [r for r in usable if _matches(r, keys, target)]
        # ★이 검사만 지우는 변이는 **생존한다**(실측) — 아래 `adjusted` 검사가 같은 선을
        #   한 번 더 지키는 **이중 가드**이기 때문이다. 둘 다 지우면 죽는다(확인함).
        #   여기 것은 단가를 못 뽑는 행을 계산하기 전에 걸러 내는 **조기 컷**이고,
        #   아래 것이 실제 표본 수를 지키는 **최종 컷**이다. 하나가 뚫려도 값은 옳다.
        if len(bucket) < min_sample:
            continue

        adjusted: list[float] = []
        n_adjusted = 0
        for r in bucket:
            unit = _unit_price_per_sqm(r)
            if unit is None:
                continue
            ym = _deal_ym(r)
            f = _time_factor(ym, now_ym, series) if (ym and now_ym) else None
            if f is not None:
                unit *= f
                n_adjusted += 1
            adjusted.append(unit)

        if len(adjusted) < min_sample:
            continue

        # 이상치 제거는 공용 헬퍼 재사용(로그 IQR) — 새 산식을 만들지 않는다.
        stats = robust_price_stats([int(v) for v in adjusted])
        if not stats.get("count"):
            continue

        return {
            "unit_price_per_sqm": int(statistics.median(adjusted)),
            "avg_per_sqm": int(stats["avg"]),
            "min_per_sqm": int(stats["min"]),
            "max_per_sqm": int(stats["max"]),
            "sample_count": len(adjusted),
            "excluded_outliers": int(stats.get("excluded") or 0),
            "layer": layer,
            "layer_label": LAYER_LABELS[layer],
            # ★어느 범위의 거래인지 — 소비처가 "내 땅 시세"로 오독하지 않게 한다.
            "scope_label": _scope_label(layer, target),
            # 시점수정을 **전부** 했는지, 일부만 했는지 구분해서 말한다.
            "time_adjusted": n_adjusted == len(adjusted) and n_adjusted > 0,
            "time_adjusted_count": n_adjusted,
            # 지분거래는 통계에서 뺐지만 **몇 건이었는지는 밝힌다**(버린 사실도 사실이다).
            "share_deal_count_excluded": share_seen,
            "masked_jibun_count": sum(1 for r in bucket if is_masked_jibun(r.get("jibun"))),
            # ★★2026-08-07 라이브 실측으로 추가 — **지목이 섞이면 값이 크게 왜곡된다**.
            #   같은 동 안에서도 `대`(대지)와 `도로`·`전`·`답`은 단가가 자릿수로 다르다.
            #   실측(프로덕션 5지역): 강남 논현동 실거래 중앙값이 **공시지가의 0.54배**로
            #   나왔다 — 대지 시세가 공시지가보다 낮을 수 없으므로 혼입의 증거다.
            #   반대로 수원 영통은 9.62배(넓은 층에 상업지 대지가 섞임).
            #   ★층을 더 쪼개면 표본이 사라지므로(동+용도+지목 중앙 1건) **구성을 밝힌다** —
            #   값을 왜곡하지 않으면서 "이 값이 무엇으로 이뤄졌는지"를 소비처가 알 수 있다.
            "jimok_mix": _mix_of(bucket, "jimok"),
            # ★★2026-08-08 라이브가 시킨 것 — **용도지역 구성**도 밝힌다.
            #   지목만으로는 부족했다. 논현동 1-1(일반상업지역) 조회에서 `dong_zone` 이
            #   표본 부족으로 실패해 `dong` 으로 떨어졌는데, 그 표본은 **전부 주거지역**
            #   거래였다(제1·2·3종). 상업지 대상에 주거지 시세를 "논현동 시세"로 준 것이다.
            #   ★그 결과가 "공시지가의 0.54배" 였다 — **혼입도 왜곡도 아니고 모집단이 다른**
            #   것이었는데, `scope_label` 이 "논현동" 뿐이라 사용자는 구분할 수 없다.
            #   → 값을 막지 않고(막으면 아무 정보도 없다) **무엇으로 이뤄졌는지** 밝힌다.
            "land_use_mix": _mix_of(bucket, "land_use"),
        }

    return None


def _mix_of(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    """표본의 **구성**(많은 순). 값을 바꾸지 않고 무엇이 섞였는지만 밝힌다.

    ★`jimok`(지목)과 `land_use`(용도지역) 둘 다 이 함수를 쓴다 — 두 축 모두
    "값이 무엇으로 이뤄졌는지"를 말해야 하고, 산식이 같은데 두 벌로 두면 갈린다.

    ★왜 필터가 아니라 구성인가: 지목까지 좁히면 표본이 사라진다(실측상 `동+용도+지목`은
    중앙 1건). 그렇다고 섞인 채 값만 주면 사용자는 대지 시세로 읽는다.
    → **거르지 말고 밝힌다**. 판단에 필요한 것을 주되, 없는 정밀도를 지어내지 않는다.
    """
    counts: dict[str, int] = {}
    for r in rows:
        key = _norm(r.get(field)) or "미상"
        counts[key] = counts.get(key, 0) + 1
    total = sum(counts.values())
    # ★정직 표기 — 이 가드는 **도달 불가**다(변이 생존 실측). 호출부가 최소 표본을 이미
    #   보장하므로 `rows` 가 비어 오지 않는다. 0 나눗셈 방어로 남기되 "잠갔다"고 세지 않는다.
    if not total:
        return []
    return [
        {field: k, "count": v, "share_pct": round(v * 100 / total, 1)}
        for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def _scope_label(layer: str, target: dict[str, str]) -> str:
    """사용자가 읽을 범위 문구. **어느 축으로 좁혔는지**가 그대로 드러나야 한다."""
    dong, use, jimok = target["dong"], target["land_use"], target["jimok"]
    return {
        "dong_zone_jimok": f"{dong} · {use} · {jimok}",
        "dong_jimok": f"{dong} · {jimok}",
        "dong_zone": f"{dong} · {use}",
        "dong": dong,
        "sigungu_jimok": f"시군구 전체 · {jimok}",
        "sigungu_zone": f"시군구 전체 · {use}",
    }.get(layer, "시군구 전체")


def stats_note(stats: dict[str, Any] | None, window_months: int) -> str | None:
    """통계에 붙일 정직 고지. 통계가 없으면 None.

    ★값만 보여 주면 사용자는 "내 땅 시세"로 읽는다. 이 값이 **무엇의 대표값인지**,
    **위치가 반영되지 않았다는 것**을 같은 자리에서 말해야 한다.
    """
    if not stats:
        return None
    bits = [
        f"{stats['scope_label']} 최근 {window_months}개월 실거래 {stats['sample_count']:,}건의 중앙값"
    ]
    if not stats.get("time_adjusted"):
        bits.append("시점수정 미적용")
    if stats.get("share_deal_count_excluded"):
        bits.append(f"지분거래 {stats['share_deal_count_excluded']:,}건 제외")
    head = " · ".join(bits)
    # ★정직 표기 — 이 초기화도 변이로 잠기지 않는다(위와 같은 이유로 `mix` 가 항상 비지
    #   않는다). 아래 분기가 늘어날 때를 위한 방어다.
    tail = ""
    jm = stats.get("jimok_mix") or []
    lm = stats.get("land_use_mix") or []
    bits2: list[str] = []
    if lm:
        # ★★용도지역 구성이 **먼저**다 — 라이브에서 실제로 이것 때문에 오독이 났다.
        #   상업지 대상인데 표본이 전부 주거지였고, 범위 문구는 "논현동" 뿐이라
        #   사용자는 "논현동 시세"로 읽었다(공시지가의 0.54배가 그렇게 나왔다).
        bits2.append("용도지역 " + " · ".join(f"{m['land_use']} {m['share_pct']:g}%" for m in lm[:3]))
    if jm:
        # 지목은 단가를 자릿수로 가른다(대 vs 도로).
        bits2.append("지목 " + " · ".join(f"{m['jimok']} {m['share_pct']:g}%" for m in jm[:3]))
    if bits2:
        tail = (
            f" 이 표본의 구성은 {' / '.join(bits2)} 입니다 — "
            "대상지와 다른 용도지역·지목이 섞여 있으면 단가가 크게 다를 수 있습니다."
        )
    return (
        f"{head}입니다. 공개 실거래 자료가 지번을 가려서 제공해 **개별 필지 위치는 "
        f"반영되지 않았습니다** — 같은 구역 안에서도 필지별 차이가 클 수 있습니다.{tail}"
    )
