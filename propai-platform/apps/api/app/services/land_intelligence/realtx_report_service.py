"""프로젝트 **실거래 신고내역 현황분석** — 필지 목록을 받아 신고 상태를 정리한다.

## 왜 이 서비스가 필요한가

`#837` 이 MOLIT 응답의 **계약상태 6필드**(해제여부·해제일·거래유형·등기일자·매수/매도 법인개인)를
파서에 보존했다. 그런데 **그것을 읽는 화면이 하나도 없다**(2026-08-26 실측 — `is_cancelled` 는
`nearby_map_service` 가 세기만 하고, 나머지 5필드는 `_group_trade` 조립에서 버려진다).
이 서비스는 그 6필드를 **처음으로 사용자에게 보여 주는 통로**다.

## ★원천 한계 — 정직하게 (이것이 이 파일의 가장 중요한 내용)

**필지(PNU) 단위로는 매칭할 수 없다.** MOLIT 토지 실거래는 **지번을 마스킹**한다.

    라이브 실측 2026-08-26 (원본 API 직접 조회 · LAWD_CD=41370 · DEAL_YMD=202607 · 114행)
      지번 마스킹 = **114/114 = 100%**   예: "1*"

따라서 이 보고서는 **법정동 단위**이고, 그 사실을 `parcel_match_absent = masked_by_source`
(보류값 계약 `#832` 의 닫힌 어휘)로 **응답에 싣는다**. 화면이 *"필지별"* 이라고 말하면 거짓이 된다.

★그래도 PNU 를 쓴다 — **법정동(10자리)까지는 정확**하므로 필지가 속한 동을 정확히 고를 수 있다.

## ★쿼터가 구조를 정한다

MOLIT 은 **무과금이지만 일일 쿼터가 진짜 제약**이고 그 키를 **G2B·조달청가격과 공유**한다.
필지마다 조회하면 죽는다. 그래서 **(시군구, 월) 단위로 접는다**:

    라이브 실측 2026-08-26: 필지 **390** 개 → 고유 시군구 **5** 개 = **78배** 절감

★조회 실패(429/403/빈응답)를 **"거래 0건"으로 기록하지 않는다** — 보류값 계약으로 사유를 싣는다.
  그러지 않으면 *"이 동네는 거래가 없었다"* 는 **거짓 사실**이 만들어진다.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from apps.api.app.utils.withheld import (
    MASKED_BY_SOURCE,
    NOT_APPLICABLE,
    SOURCE_UNAVAILABLE,
    withheld,
)

# ★평↔㎡ 계수는 **새로 선언하지 않는다.** `market_report_service.PYEONG_SQM` 이 사실상 정본이고
#   형제 둘(`report/render/market_adapter.py`·프론트 `PricingBandPanel.tsx`)이 자기 주석에
#   *"이 상수의 미러"* 라고 적어 두었다. 저장소에 `3.3058`(121배 부정확)도 공존하므로
#   **뿌리를 늘리지 않는 것**이 이 import 의 요점이다.
from apps.api.app.services.market.market_report_service import PYEONG_SQM

logger = logging.getLogger(__name__)

#: PNU 자릿수 — 법정동코드(10) + 대장구분(1) + 본번(4) + 부번(4)
_PNU_LEN = 19
#: 대장구분 코드 — "1"=일반(대지) · "2"=산
_PNU_SAN = "2"


def lawd_cd_from_pnu(pnu: str | None) -> str | None:
    """PNU → **시군구코드 5자리**(MOLIT `LAWD_CD`). 형식이 아니면 `None`."""
    p = (pnu or "").strip()
    if len(p) != _PNU_LEN or not p.isdigit():
        return None
    return p[:5]


def bjdong_cd_from_pnu(pnu: str | None) -> str | None:
    """PNU → **법정동코드 10자리**. 필지를 동 단위로 접을 때 쓴다."""
    p = (pnu or "").strip()
    if len(p) != _PNU_LEN or not p.isdigit():
        return None
    return p[:10]


def jibun_from_pnu(pnu: str | None) -> str | None:
    """PNU → 사람이 읽는 **지번**(예 `"210-453"` · 산번지는 `"산 1-1"`).

    ★검산(2026-08-26 라이브 데이터): `1159010200102100453` → `"210-453"` 이고
      같은 레코드의 `jibun` 필드가 `"서울특별시 동작구 상도동 210-453"` 이라 **일치**한다.

    ★이 값은 **표시·대조용**이다. MOLIT 토지 응답의 지번은 마스킹되므로
      **이것으로 거래를 필지에 매칭할 수 없다**(모듈 독스트링 참조).
    """
    p = (pnu or "").strip()
    if len(p) != _PNU_LEN or not p.isdigit():
        return None
    bon, bu = int(p[11:15]), int(p[15:19])
    if bon == 0:
        return None
    head = f"산 {bon}" if p[10] == _PNU_SAN else str(bon)
    return f"{head}-{bu}" if bu else head


def fold_parcels_by_lawd(parcels: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """필지 목록을 **시군구코드로 접는다** — 조회 횟수를 결정하는 함수.

    ★쿼터 방어의 핵심이다. 필지 N개가 같은 시군구면 **조회는 1회**여야 한다.
    ★PNU 가 없는 필지는 `""` 키에 모은다 — **버리지 않는다**(보류 사유를 붙여 응답에 싣는다).
    """
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pc in parcels or []:
        if not isinstance(pc, dict):
            continue
        out[lawd_cd_from_pnu(pc.get("pnu")) or ""].append(pc)
    return dict(out)


def month_range(end_ym: str, months: int) -> list[str]:
    """`end_ym`(YYYYMM)에서 과거로 `months` 개월치 `YYYYMM` 목록(오름차순)."""
    s = (end_ym or "").strip()
    if len(s) != 6 or not s.isdigit():
        return []
    y, m = int(s[:4]), int(s[4:])
    if not (1 <= m <= 12):
        return []
    out: list[str] = []
    for _ in range(max(1, months)):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return sorted(out)


# ── 평당 단가 ───────────────────────────────────────────────────────────────────
#
# ★★왜 「금액 ÷ 면적」을 그대로 쓰지 않는가 — 2026-08-28 라이브 실측(역삼동·6개월·71건)
#
#   area= 3.31㎡ → 1.001275평 | 2,000만원 | 1,997.45 만원/평 | 33건
#   area= 6.61㎡ → 1.999525평 | 4,000만원 | 2,000.48 만원/평 | 12건
#
#   **면적이 평의 정수배에 소수 여섯째 자리까지 붙는다.** 즉 원천의 1차 자료는 ㎡ 가 아니라
#   **평당 단가**이고, 총액은 `평 × 단가` 로 만들어진 것이다. 결정적 대조군 — **같은 날
#   서로 다른 면적 3건이 소수 둘째 자리까지 동일 단가**(182.9/139.0/136.2㎡ → 전부 14,623.39).
#   전수: 만원/평이 정수·10단위에 붙는 행 **71/71** · 고유 단가 **21개**(표의 70%가 반복).
#
#   ★그래서 우리 나눗셈은 **역산**이고, 원천이 평→㎡ 를 소수 2자리에서 끊은 탓에
#   **같은 2,000만원/평 거래 45건이 1,997 과 2,000 두 값으로 갈린다** — 우리가 만든 가짜 가격차다.
#   → **유효숫자 3자리**로 표시해 그 허위 정밀도를 걷어낸다(3.31㎡ 의 유효숫자가 3자리다).
#     큰 필지에서는 약간 보수적으로(14,623 → 14,600) 표시되지만, **없는 차이를 만들지 않는 것**을
#     우선한다. 균일한 규칙이라 잠글 수 있다는 것도 이유다.
#
# ★섞으면 무의미하다는 것은 원천 주석이 이미 적어 두었다(`molit_client.py:459`):
#   *"지분 비율이 지역마다 크고 단가 차이도 방향이 제각각 — 강남 0.27배·포항북 2.14배.
#     즉 섞으면 그 값은 무의미하다. ★제외·가중은 **소비처 판단**이다."*
#   이 서비스가 그 소비처다. 우리는 **행 단위로만** 싣고 **평균을 만들지 않는다** —
#   층화 축(지목·지분·해제)이 같은 행에 이미 있어 사용자가 스스로 가를 수 있고,
#   요약 타일에는 그 맥락이 없기 때문이다(라이브 실측: 최빈 행이 **「도로 지분」 73%**).


def _round_sig(x: float, digits: int = 3) -> int:
    """유효숫자 `digits` 자리로 반올림한 정수.

    ★원천 면적의 유효숫자가 3자리(예 `3.31㎡`)라 그보다 많은 자리를 표시하면 **허위 정밀도**다.
    """
    if x <= 0:
        return 0
    import math

    mag = math.floor(math.log10(x))
    q = 10 ** (mag - digits + 1)
    return int(round(x / q) * q)


def per_pyeong_10k(price_10k_won: Any, area_m2: Any) -> int | None:
    """만원/평 — 값이 **둘 다 유효할 때만**. 아니면 `None`(지어내지 않는다)."""
    try:
        p = float(price_10k_won)
        a = float(area_m2)
    except (TypeError, ValueError):
        return None
    if not (p > 0 and a > 0):
        return None
    return _round_sig(p / (a / PYEONG_SQM))


def attach_per_pyeong(txs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """각 거래 행에 `price_per_pyeong_10k` 을 싣는다 — **없으면 사유를 싣는다.**

    ★「모름」을 `0` 이나 `"—"` 로 표현하지 않는다. 이 저장소는 `0㎡ × 0원/㎡` 가 **면제 확정**과
      구별되지 않아 값을 치른 적이 있다. 화면의 `"—"` 는 이미 **면적 결측**이 쓰는 글리프라,
      여기서 재사용하면 「해제라 해당 없음」과 「원천이 가림」이 한 글리프로 뭉개진다.
    """
    out: list[dict[str, Any]] = []
    for t in txs or []:
        if not isinstance(t, dict):
            continue
        row = dict(t)
        # ★해제 거래 — 일어나지 않은 거래에 단가는 **해당 없음**이다.
        #   라이브 실측: 해제 행은 원거래와 **전 필드 동일한 별개 행**으로 오고(102.3㎡/20,150만),
        #   그 평당가는 대지 중앙의 1/22.5 라 **표 최저 이상치가 두 번 찍힌다**.
        if str(row.get("cancel_type") or "").strip():
            row.update(withheld(
                NOT_APPLICABLE,
                "계약이 해제된 신고 건이라 거래 단가를 산정하지 않습니다.",
                field="price_per_pyeong_10k",
            ))
            out.append(row)
            continue
        pp = per_pyeong_10k(row.get("price_10k_won"), row.get("area_m2"))
        if pp is None:
            row.update(withheld(
                MASKED_BY_SOURCE,
                "원천이 면적 또는 거래금액을 제공하지 않아 단가를 산정할 수 없습니다.",
                field="price_per_pyeong_10k",
            ))
        else:
            row["price_per_pyeong_10k"] = pp
        out.append(row)
    return out


def summarize_contract_state(txs: list[dict[str, Any]]) -> dict[str, Any]:
    """거래 목록 → **신고 상태 현황** 집계 — 순수 함수.

    ★`#837` 이 보존한 6필드를 여기서 처음으로 **사용자가 읽는 수**로 만든다.

    ★★정상 건은 `' '`(스페이스)다 — `strip()` 없이 truthy 로 보면 **전건이 해제**가 된다
      (`molit_client` 가 파싱 단계에서 이미 `strip()` 하지만, 이 함수는 **자기 입력을 믿지 않는다**).
    """
    total = len(txs or [])
    cancelled = direct = brokered = registered = corp_buyer = corp_seller = share = 0
    for t in txs or []:
        if not isinstance(t, dict):
            continue
        if str(t.get("cancel_type") or "").strip():
            cancelled += 1
        dt = str(t.get("dealing_type") or "").strip()
        if dt == "직거래":
            direct += 1
        elif dt == "중개거래":
            brokered += 1
        if str(t.get("registered_date") or "").strip():
            registered += 1
        if str(t.get("buyer_type") or "").strip() == "법인":
            corp_buyer += 1
        if str(t.get("seller_type") or "").strip() == "법인":
            corp_seller += 1
        if str(t.get("share_dealing_type") or "").strip() == "지분":
            share += 1
    return {
        "total": total,
        "cancelled": cancelled,
        "cancelled_pct": round(100.0 * cancelled / total, 2) if total else 0.0,
        "direct": direct,
        "brokered": brokered,
        # ★등기일자는 **30.2%만 채워진다**(2026-08-26 실측 3,482건). 낮은 값이 결함이 아니다 —
        #   원천이 그렇다. 화면이 "등기 미완 70%"라고 단정하면 거짓이다.
        "registered": registered,
        "registered_pct": round(100.0 * registered / total, 2) if total else 0.0,
        "corporate_buyer": corp_buyer,
        "corporate_seller": corp_seller,
        "share_deals": share,
    }


def parcel_view(pc: dict[str, Any]) -> dict[str, Any]:
    """필지 1건의 표시용 뷰 — PNU 파생값과 **매칭 불가 사유**를 함께 싣는다."""
    pnu = (pc.get("pnu") or "").strip()
    base = {
        "pnu": pnu or None,
        "jibun_label": pc.get("jibun") or None,
        "jibun_from_pnu": jibun_from_pnu(pnu),
        "lawd_cd": lawd_cd_from_pnu(pnu),
        "bjdong_cd": bjdong_cd_from_pnu(pnu),
        "area_sqm": pc.get("area_sqm"),
        "zone_code": pc.get("zone_code"),
        "owner_type": pc.get("owner_type"),
    }
    if not base["lawd_cd"]:
        # PNU 가 없거나 형식이 아니면 **조회 자체가 불가**하다 — 조용히 빈 결과로 두지 않는다.
        base.update(
            withheld(
                SOURCE_UNAVAILABLE,
                "이 필지에 PNU 가 없어 실거래 조회 대상 지역을 특정하지 못했습니다. "
                "토지조서에서 PNU 를 채우면 조회됩니다.",
                field="transactions",
            ),
        )
    return base


async def build_realtx_report(
    parcels: list[dict[str, Any]],
    *,
    end_ym: str,
    months: int = 6,
    prop_type: str = "land",
    client: Any = None,
) -> dict[str, Any]:
    """필지 목록 → **실거래 신고내역 현황분석**.

    ★조회는 **(시군구, 월)** 단위로 접는다 — 필지 수와 무관하다.
      실측(2026-08-26): 필지 390 → 고유 시군구 5. `months=6` 이면 조회 **30회**이지
      필지마다 부르면 2,340회다(78배).

    ★실패를 **거래 0건으로 기록하지 않는다.** 429/403/예외는 해당 (시군구, 월)에
      보류 사유(`SOURCE_UNAVAILABLE`)를 남긴다 — *"그 달엔 거래가 없었다"* 는 거짓을 만들지 않는다.

    `client` 는 주입 가능하다(테스트가 호출 횟수를 셀 수 있어야 하므로).
    """
    yms = month_range(end_ym, months)
    folded = fold_parcels_by_lawd(parcels)
    lawds = sorted(k for k in folded if k)

    if client is None:  # pragma: no cover - 라이브 경로
        from integrations.molit_client import MolitClient

        client = MolitClient()

    by_bjdong: dict[str, list[dict[str, Any]]] = defaultdict(list)
    fetch_errors: list[dict[str, Any]] = []
    calls = 0
    for lawd in lawds:
        for ym in yms:
            calls += 1
            try:
                rows = await client.get_transactions(lawd, ym, prop_type=prop_type)
            except Exception as e:  # noqa: BLE001 — 개별 실패가 전체를 깨지 않는다(격리)
                logger.warning("실거래 조회 실패 lawd=%s ym=%s: %s", lawd, ym, str(e)[:160])
                fetch_errors.append({"lawd_cd": lawd, "deal_ym": ym, "error": type(e).__name__})
                continue
            for r in rows or []:
                if isinstance(r, dict):
                    by_bjdong[f"{lawd}|{str(r.get('dong') or '').strip()}"].append(r)

    # 필지를 **법정동 이름**이 아니라 코드로 접는다(동명이인 방지) — 다만 MOLIT 은 이름만 준다.
    # 그래서 시군구 안에서 이름으로 맞춘다. 이름이 안 맞으면 그 필지는 **미매칭**으로 남긴다.
    groups: list[dict[str, Any]] = []
    for lawd in lawds:
        pcs = folded[lawd]
        dong_names = {
            n for n in (
                _dong_name_of(pc) for pc in pcs
            ) if n
        }
        for dong in sorted(dong_names):
            txs = by_bjdong.get(f"{lawd}|{dong}", [])
            txs_sorted = sorted(txs, key=lambda t: str(t.get("deal_date") or ""))
            groups.append({
                "lawd_cd": lawd,
                "dong": dong,
                "parcels": [parcel_view(pc) for pc in pcs if _dong_name_of(pc) == dong],
                "summary": summarize_contract_state(txs_sorted),
                "transactions": attach_per_pyeong(txs_sorted),
                # ★이 보고서가 **필지별이 아닌 이유**를 응답에 싣는다(보류값 계약).
                **withheld(
                    MASKED_BY_SOURCE,
                    "국토부 실거래 공개자료는 토지 거래의 **지번을 마스킹**합니다"
                    "(라이브 실측 2026-08-26: 114건 전수 마스킹, 예 '1*'). "
                    "따라서 개별 거래를 특정 필지에 귀속시킬 수 없어 **법정동 단위**로 집계했습니다 "
                    "— 이 동에 속한 아래 필지들의 주변 신고내역입니다.",
                    field="parcel_level_match",
                ),
            })

    unlocated = [parcel_view(pc) for pc in folded.get("", [])]
    return {
        "months": yms,
        "prop_type": prop_type,
        "groups": groups,
        "unlocated_parcels": unlocated,
        "fetch_errors": fetch_errors,
        # ★관측 가능성 — 조회 횟수를 응답에 싣는다. 쿼터 접기가 실제로 작동했는지
        #   소비처가 확인할 수 있어야 한다(주장이 아니라 수).
        "meta": {
            "parcel_count": len(parcels or []),
            "lawd_count": len(lawds),
            "month_count": len(yms),
            "molit_calls": calls,
            "unlocated_count": len(unlocated),
        },
        "note": (
            "실거래 신고내역은 국토교통부 공개자료 기준입니다. "
            "★지번 마스킹으로 **필지 단위 귀속은 불가**하며 법정동 단위 집계입니다. "
            "★등기일자는 원천에서 약 30%만 채워집니다(미기재가 곧 미등기는 아닙니다). "
            "★수집 게이트가 스키마 위반행을 드롭하므로 원천 전수와 다를 수 있습니다."
        ),
    }


def _dong_name_of(pc: dict[str, Any]) -> str:
    """필지 레코드에서 **법정동 이름**을 뽑는다.

    토지조서의 `jibun` 은 `"서울특별시 동작구 상도동 210-453"` 처럼 전체 주소다.
    MOLIT 은 `dong` 을 `"상도동"` 처럼 **동 이름만** 준다 — 그래서 주소에서 동을 뽑아 맞춘다.
    """
    label = str(pc.get("jibun") or pc.get("address") or "").strip()
    if not label:
        return ""
    for tok in reversed(label.split()):
        if tok.endswith(("동", "리", "가")) and not tok[0].isdigit():
            return tok
    return ""
