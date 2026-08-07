"""하이픈(Hyphen Data Market) 부동산등기부등본 연동 API 클라이언트.

명세: https://api.hyphen.im (REST POST)
엔드포인트:
 - 주소검색: /in0004000168(간편주소), /in0004000167(도로명), /in0004000166(지번), /in0004000169(고유번호)
 - 등기부 열람: /in0004000948(민원캐시 차감 열람), /in0004000949(비회원 열람), /in0004001436(회원 발급)

인증:
 - Headers: HKey (HYPHEN_HKEY), User-Id (HYPHEN_USER_ID)
"""

from __future__ import annotations

import base64
import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _host() -> str:
    return (os.getenv("HYPHEN_API_HOST") or "https://api.hyphen.im").rstrip("/")


def hyphen_hkey() -> str:
    return (os.getenv("HYPHEN_HKEY") or os.getenv("HYPHEN_API_KEY") or "").strip()


def hyphen_user_id() -> str:
    return (os.getenv("HYPHEN_USER_ID") or "").strip()


def hyphen_ready() -> bool:
    return bool(hyphen_hkey() and hyphen_user_id())


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "HKey": hyphen_hkey(),
        "User-Id": hyphen_user_id(),
    }


# ── API 권한 실도달성 점검 ────────────────────────────────────────────────
# 키가 있다고 "연결됨"이라 말하면 안 된다 — 하이픈은 키가 유효해도 계약에 없는
# API는 errYn=Y "권한이 없는 API 입니다"로 거절한다(라이브에서 실제 발생).
# 틸코가 공개키를 실제로 받아와 검증(public_key_ok)하는 것과 대칭을 맞춘다.
_ACCESS_CACHE: dict[str, Any] = {}
_ACCESS_TTL_SEC = 300.0
# 권한 거절을 알리는 벤더 문구(부분일치). 문구가 바뀌어도 오탐이 나지 않도록
# '권한' + 'API' 동시 포함을 기본 신호로 쓰고, 알려진 원문도 함께 본다.
_FORBIDDEN_HINTS = ("권한이 없는 API", "권한이 없습니다", "권한 없음")


def _is_forbidden_message(msg: str) -> bool:
    m = (msg or "").strip()
    if not m:
        return False
    if any(h in m for h in _FORBIDDEN_HINTS):
        return True
    return ("권한" in m) and ("API" in m.upper())


async def probe_api_access(force: bool = False) -> dict[str, Any]:
    """하이픈 계정이 등기 조회 API를 실제로 호출할 수 있는지 점검.

    반환: {"access": "ok"|"forbidden"|"unreachable"|"not_configured",
           "checked": bool, "message": str}

    - 과금되지 않는 검색 API(고유번호검색)로 확인한다(열람 API는 1,200원 차감이라 금지).
    - 데이터가 없어서 나는 오류(존재하지 않는 고유번호)는 '권한 있음'으로 본다 —
      요청이 계약 관문을 통과했다는 뜻이기 때문이다.
    - 결과는 짧게 캐시한다(상태 조회마다 벤더를 두드리지 않도록).
    """
    import time

    if not hyphen_ready():
        return {"access": "not_configured", "checked": False,
                "message": "HYPHEN_HKEY / HYPHEN_USER_ID 미설정"}

    now = time.monotonic()
    hit = _ACCESS_CACHE.get("v")
    if hit and not force and (now - hit[0]) < _ACCESS_TTL_SEC:
        return dict(hit[1])

    import httpx

    out: dict[str, Any]
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            # 고유번호검색(/in0004000169) — 조회 전용·무과금. 더미 번호로 관문만 통과 확인.
            resp = await client.post(f"{_host()}/in0004000169", headers=_headers(),
                                     json={"uniqNo": "00000000000000"})
            if resp.status_code != 200:
                out = {"access": "unreachable", "checked": True,
                       "message": f"하이픈 응답 오류(HTTP {resp.status_code})"}
            else:
                data = resp.json()
                common = data.get("common") or {}
                err_msg = str(common.get("errMsg") or "")
                if _is_forbidden_message(err_msg):
                    out = {"access": "forbidden", "checked": True,
                           "message": ("하이픈 키는 정상이나 등기 조회 API 사용 권한이 없습니다 — "
                                       "하이픈에 부동산등기 API(주소검색·고유번호검색·등기열람) "
                                       "이용 권한 활성화를 요청하세요.")}
                else:
                    # errYn=Y여도 '권한' 사유가 아니면 관문은 통과한 것(데이터 없음 등)
                    out = {"access": "ok", "checked": True,
                           "message": "하이픈 등기 API 호출 권한 확인됨"}
    except Exception as e:  # noqa: BLE001
        logger.warning("하이픈 권한 점검 예외", err=str(e)[:120])
        out = {"access": "unreachable", "checked": True,
               "message": f"하이픈 연결 실패: {str(e)[:80]}"}

    _ACCESS_CACHE["v"] = (now, dict(out))
    return out


def normalize_address_candidates(address: str) -> list[str]:
    """임야/산지 지번(산 1-1 ↔ 산1-1) 등 띄어쓰기·지번 형태 변형 후보를 자동 생성.

    1차 주소검색 실패 시 자동 폴백하여 벤더 주소검색 파서의 미세한 포맷 차이에 따른
    주소검색 누락(no_match)을 자동 보정한다.
    """
    import re

    addr = (address or "").strip()
    if not addr:
        return []
    candidates = [addr]
    # 1. "산 1-1" → "산1-1" (산과 본번 사이 띄어쓰기 제거)
    v1 = re.sub(r"산\s+(\d+)", r"산\1", addr)
    if v1 != addr and v1 not in candidates:
        candidates.append(v1)
    # 2. "산1-1" → "산 1-1" (산과 본번 사이 띄어쓰기 추가)
    v2 = re.sub(r"산(\d+)", r"산 \1", addr)
    if v2 != addr and v2 not in candidates:
        candidates.append(v2)
    return candidates


async def _search_single_address(
    address: str,
    kindcls: str = "0",
    cls_flag: str = "1",
    limit_page: str = "1",
    page_no: str = "1",
) -> dict[str, Any]:
    """단일 주소 원시 검색 (POST /in0004000168)."""
    import httpx

    url = f"{_host()}/in0004000168"
    body = {
        "kindcls": kindcls,
        "simple_address": address,
        "cls_flag": cls_flag,
        "limitPage": limit_page,
        "pageNo": page_no,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=_headers(), json=body)
            if resp.status_code != 200:
                return {
                    "ok": False,
                    "status": "provider_error",
                    "items": [],
                    "message": f"하이픈 주소검색 오류 (HTTP {resp.status_code})",
                }
            data = resp.json()

        common = data.get("common") or {}
        err_yn = common.get("errYn")
        if err_yn and err_yn != "N":
            return {
                "ok": False,
                "status": "provider_error",
                "items": [],
                "message": common.get("errMsg") or "주소검색 실패",
                "raw": data,
            }

        res_data = data.get("data") or {}
        raw_list = res_data.get("list") or []
        items = []
        for item in raw_list:
            if isinstance(item, dict):
                items.append({
                    "unique_no": (item.get("get부동산고유번호") or "").replace("-", "").strip(),
                    "gubun": item.get("get구분"),
                    "owner": item.get("get소유자"),
                    "jibun": item.get("get부동산소재지번"),
                    "sangtae": item.get("get상태"),
                })

        return {
            "ok": True,
            "status": "ok",
            "items": items,
            "total": res_data.get("totCnt") or len(items),
            "raw": data,
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("하이픈 간편주소검색 예외", err=str(e)[:120])
        return {"ok": False, "status": "error", "items": [], "message": str(e)[:200]}


async def search_by_simple_address(
    address: str,
    kindcls: str = "0",
    cls_flag: str = "1",
    limit_page: str = "1",
    page_no: str = "1",
) -> dict[str, Any]:
    """간편주소로 부동산 고유번호 검색 (POST /in0004000168).

    산지/임야 지번(산 1-1 ↔ 산1-1) 등 띄어쓰기 변형 후보를 자동 폴백 시도하여
    주소검색 누락을 자동 보정한다.
    """
    if not hyphen_ready():
        return {
            "ok": False,
            "status": "not_configured",
            "items": [],
            "message": "HYPHEN_HKEY / HYPHEN_USER_ID 미설정",
        }

    addr = (address or "").strip()
    if not addr:
        return {"ok": False, "status": "bad_request", "items": [], "message": "주소가 필요합니다."}

    candidates = normalize_address_candidates(addr)
    last_res: dict[str, Any] | None = None
    for cand in candidates:
        res = await _search_single_address(
            cand, kindcls=kindcls, cls_flag=cls_flag, limit_page=limit_page, page_no=page_no
        )
        if res.get("ok") and res.get("items"):
            if cand != addr:
                logger.info("하이픈 주소검색 자동보정 성공", original=addr, corrected=cand, count=len(res["items"]))
            return res
        last_res = res

    return last_res or {"ok": False, "status": "no_match", "items": [], "message": "주소 검색 결과가 없습니다."}



async def search_by_unique_no(unique_no: str) -> dict[str, Any]:
    """고유번호로 주소 검색 (POST /in0004000169)."""
    if not hyphen_ready():
        return {"ok": False, "status": "not_configured", "items": [], "message": "HYPHEN 인증키 미설정"}

    uno = (unique_no or "").replace("-", "").strip()
    if not uno:
        return {"ok": False, "status": "bad_request", "items": [], "message": "고유번호가 필요합니다."}

    import httpx

    url = f"{_host()}/in0004000169"
    body = {"uniqNo": uno}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=_headers(), json=body)
            resp.raise_for_status()
            data = resp.json()

        res_data = data.get("data") or {}
        raw_list = res_data.get("list") or []
        items = [
            {
                "unique_no": (it.get("get부동산고유번호") or "").replace("-", "").strip(),
                "gubun": it.get("get구분"),
                "owner": it.get("get소유자"),
                "jibun": it.get("get부동산소재지번"),
                "sangtae": it.get("get상태"),
            }
            for it in raw_list
            if isinstance(it, dict)
        ]
        return {"ok": True, "status": "ok", "items": items, "raw": data}
    except Exception as e:  # noqa: BLE001
        logger.warning("하이픈 고유번호검색 예외", err=str(e)[:120])
        return {"ok": False, "status": "error", "items": [], "message": str(e)[:200]}


async def fetch_realty_registry(
    *,
    unique_no: str,
    user_id: str | None = None,
    user_pw: str | None = None,
    user_pw_enc: str | None = None,
    pay_no: str | None = None,
    pay_pw: str | None = None,
    pay_pw_enc: str | None = None,
    cmort_check: str = "N",
    trade_check: str = "N",
    display: str = "2",
) -> dict[str, Any]:
    """등기부등본 민원캐시 차감 열람 (POST /in0004000948)."""
    if not hyphen_ready():
        return {
            "ok": False,
            "status": "not_configured",
            "message": "HYPHEN_HKEY 및 HYPHEN_USER_ID 환경변수가 필요합니다.",
        }

    uno = (unique_no or "").replace("-", "").strip()
    if not uno:
        return {"ok": False, "status": "need_unique_no", "message": "부동산 고유번호(14자리)가 필요합니다."}

    uid = user_id or os.getenv("HYPHEN_IROS_USER_ID") or ""
    upw = user_pw or os.getenv("HYPHEN_IROS_USER_PW") or ""
    upw_enc = user_pw_enc or os.getenv("HYPHEN_IROS_USER_PW_ENC") or ""
    pno = pay_no or os.getenv("HYPHEN_PAY_NO") or ""
    ppw = pay_pw or os.getenv("HYPHEN_PAY_PW") or ""
    ppw_enc = pay_pw_enc or os.getenv("HYPHEN_PAY_PW_ENC") or ""

    import httpx

    url = f"{_host()}/in0004000948"
    body: dict[str, Any] = {
        "userId": uid,
        "searchDiv": "uniqNo",
        "uniqNo": uno,
        "cmortCheck": cmort_check,
        "tradeCheck": trade_check,
        "pdfHex": "Y",
        "xmlYn": "N",
        "display": display,
        "payDiv": "0",
        "payNo": pno,
        "dupChk": "Y",
    }
    if upw_enc:
        body["userPwEnc"] = upw_enc
    else:
        body["userPw"] = upw

    if ppw_enc:
        body["payPwEnc"] = ppw_enc
    else:
        body["payPw"] = ppw

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(url, headers=_headers(), json=body)
            if resp.status_code != 200:
                return {
                    "ok": False,
                    "status": "provider_error",
                    "message": f"하이픈 열람 응답 오류 (HTTP {resp.status_code})",
                    "raw": resp.text[:300],
                }
            data = resp.json()

        common = data.get("common") or {}
        err_yn = common.get("errYn")
        if err_yn and err_yn != "N":
            return {
                "ok": False,
                "status": "provider_error",
                "error_code": common.get("errCd"),
                "message": common.get("errMsg") or "하이픈 등기부 열람 실패",
                "raw": data,
            }

        res_data = data.get("data") or {}
        pdf_hex = res_data.get("pdfHex") or ""
        pdf_b64 = None
        if pdf_hex:
            try:
                pdf_bytes = bytes.fromhex(pdf_hex)
                pdf_b64 = base64.b64encode(pdf_bytes).decode()
            except Exception as pe:  # noqa: BLE001
                logger.warning("하이픈 pdfHex 변환 실패", err=str(pe)[:80])

        out_list = res_data.get("outList") or {}
        owner = None
        if isinstance(out_list, dict):
            owner = out_list.get("get소유자")
        elif isinstance(out_list, list) and out_list:
            owner = out_list[0].get("get소유자")

        return {
            "ok": True,
            "status": "ok",
            "origin": "hyphen",
            "unique_no": uno,
            "pdf_base64": pdf_b64,
            "has_pdf": bool(pdf_b64),
            "owner": owner,
            "out_list": out_list,
            "raw": data,
            "message": "하이픈 부동산 등기부 열람 성공",
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("하이픈 등기부 열람 예외", err=str(e)[:160])
        return {"ok": False, "status": "error", "message": str(e)[:200]}


async def fetch_registry_by_address(
    address: str,
    realty_type: str | None = None,
    dong: str | None = None,
    ho: str | None = None,
) -> dict[str, Any]:
    """주소입력 → 1차 주소검색 → 2차 등기부 열람 2단계 통합 호출.

    한 주소에 여러 물건(토지·건물·집합건물 각 호)이 나오므로, 사용자가 고른
    부동산 구분·동·호에 맞는 물건을 공용 선택기로 고른다(무조건 첫 번째 금지).
    좁히지 못하면 조회는 계속하되 그 사실을 select_note로 정직하게 전달한다.
    """
    from app.services.registry.realty_kind import select_registry_item

    search_res = await search_by_simple_address(address)
    if not search_res.get("ok") or not search_res.get("items"):
        msg = search_res.get("message") or "주소 검색 결과가 없습니다."
        return {"address": address, "status": "no_match", "message": msg}

    picked, note = select_registry_item(search_res["items"], realty_type, dong, ho)
    uno = (picked or {}).get("unique_no")
    if not uno:
        return {"address": address, "status": "no_match", "message": "부동산 고유번호를 찾을 수 없습니다."}

    fetch_res = await fetch_realty_registry(unique_no=uno)
    fetch_res["address"] = address
    fetch_res["realty_gubun"] = (picked or {}).get("gubun")
    if note:
        fetch_res["select_note"] = note
    return fetch_res
