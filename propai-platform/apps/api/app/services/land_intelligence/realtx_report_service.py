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
    SOURCE_UNAVAILABLE,
    withheld,
)

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
                "transactions": txs_sorted,
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
