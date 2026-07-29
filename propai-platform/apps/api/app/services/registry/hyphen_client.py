"""하이픈(Hyphen Data Market) 부동산등기부등본 연동 API 클라이언트.

명세: https://api.hyphen.im (REST POST)
엔드포인트:
 - 주소검색: /in0004000168(간편주소), /in0004000167(도로명), /in0004000166(지번), /in0004000169(고유번호)
 - 등기부 열람: /in0004000948(민원캐시 차감 열람), /in0004000949(비회원 열람), /in0004001436(회원 발급)

인증:
 - Headers: HKey (HYPHEN_HKEY), User-Id (HYPHEN_USER_ID)
"""

from __future__ import annotations

import asyncio
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
_ACCESS_LOCKS: dict[str, asyncio.Lock] = {}   # 자격증명별 single-flight
_ACCESS_TTL_SEC = 300.0          # 성공 판정만 길게 캐시
_ACCESS_FAIL_TTL_SEC = 30.0      # 실패는 짧게 — 벤더 복구·권한 활성화가 즉시 반영돼야 한다

# 데이터가 없어서 나는 오류코드(= 관문은 통과했다는 증거). 라이브 실측:
#   C0000-002 검색조건에 대한 결과가 없습니다 / C0000-088 고유번호에 해당하는 소재지번 없음
_DATA_LEVEL_ERR_CODES = {"C0000-002", "C0000-088"}
_DATA_LEVEL_HINTS = ("결과가 없습니다", "확인할 수 없습니다", "조회 결과가 없")
# 권한 거절 문구(라이브 실측: "권한이 없는 API 입니다")
_FORBIDDEN_HINTS = ("권한이 없는 API", "미승인", "승인되지 않은")


def _err_code_of(payload: dict[str, Any]) -> str:
    common = payload.get("common") or {}
    raw = str(common.get("errCd") or "").strip()
    if raw:
        return raw
    # errCd가 비어도 메시지 앞머리에 [C0000-002] 형태로 오는 경우가 있다(라이브 실측).
    msg = str(common.get("errMsg") or "")
    if msg.startswith("["):
        end = msg.find("]")
        if end > 1:
            return msg[1:end].strip()
    return ""


def _is_forbidden_message(msg: str) -> bool:
    m = (msg or "").strip()
    if not m:
        return False
    if any(h in m for h in _FORBIDDEN_HINTS):
        return True
    return ("권한" in m) and ("API" in m.upper())


def classify_probe_response(payload: dict[str, Any]) -> tuple[str, str]:
    """벤더 응답 → (access, message).

    ★기본값을 낙관에서 비관으로 뒤집는다: 이전 구현은 '권한' 문구가 없으면 무조건 ok라
    인증키 무효·IP 미허용·계약 만료 같은 거절을 전부 '연결됨'으로 통과시켰다.
    이제 errYn을 1차 신호로 쓰고, errYn=Y는 **데이터 레벨 오류만** ok로 인정한다.
    """
    common = payload.get("common") or {}
    err_yn = str(common.get("errYn") or "").strip().upper()
    err_msg = str(common.get("errMsg") or "").strip()
    code = _err_code_of(payload)

    if err_yn == "N":
        return "ok", "하이픈 등기 API 호출 권한 확인됨"
    if _is_forbidden_message(err_msg):
        return "forbidden", ("하이픈 키는 정상이나 등기 조회 API 사용 권한이 없습니다 — "
                             "하이픈에 부동산등기 API(주소검색·등기열람) 이용 권한 활성화를 요청하세요.")
    if code in _DATA_LEVEL_ERR_CODES or any(h in err_msg for h in _DATA_LEVEL_HINTS):
        # 데이터가 없을 뿐 관문은 통과 — 권한 있음.
        return "ok", "하이픈 등기 API 호출 권한 확인됨"
    if err_yn == "Y":
        return "degraded", (f"하이픈이 요청을 거절했습니다: {err_msg or code or '사유 미상'} — "
                            "키·계약·허용 IP 설정을 확인하세요.")
    return "unknown", "하이픈 응답을 해석할 수 없습니다(형식 상이) — 관리자 확인 필요."


async def probe_api_access(force: bool = False) -> dict[str, Any]:
    """하이픈 계정이 등기 조회 API를 실제로 호출할 수 있는지 점검.

    반환: {"access": "ok"|"forbidden"|"unreachable"|"not_configured",
           "checked": bool, "message": str}

    - 과금되지 않는 검색 API(고유번호검색)로 확인한다(열람 API는 1,200원 차감이라 금지).
    - 데이터가 없어서 나는 오류(존재하지 않는 고유번호)는 '권한 있음'으로 본다 —
      요청이 계약 관문을 통과했다는 뜻이기 때문이다.
    - 결과는 짧게 캐시한다(상태 조회마다 벤더를 두드리지 않도록).
    """
    import hashlib
    import time

    if not hyphen_ready():
        return {"access": "not_configured", "checked": False,
                "message": "HYPHEN_HKEY / HYPHEN_USER_ID 미설정"}

    # 캐시 키에 자격증명을 포함한다 — 키를 바꾸거나 권한을 켠 직후에도 옛 판정이
    # 남아 관리자 '테스트'가 계속 거짓말하던 문제를 막는다.
    cred = hashlib.sha256(f"{hyphen_hkey()}|{hyphen_user_id()}|{_host()}".encode()).hexdigest()[:16]
    now = time.monotonic()
    hit = _ACCESS_CACHE.get(cred)
    if hit and not force:
        ttl = _ACCESS_TTL_SEC if hit[1].get("access") == "ok" else _ACCESS_FAIL_TTL_SEC
        if (now - hit[0]) < ttl:
            return dict(hit[1])

    # 동시 요청이 벤더를 동시에 두드리지 않도록 자격증명별 단일 실행(single-flight).
    lock = _ACCESS_LOCKS.setdefault(cred, asyncio.Lock())
    async with lock:
        hit = _ACCESS_CACHE.get(cred)
        if hit and not force:
            ttl = _ACCESS_TTL_SEC if hit[1].get("access") == "ok" else _ACCESS_FAIL_TTL_SEC
            if (time.monotonic() - hit[0]) < ttl:
                return dict(hit[1])

        import httpx

        out: dict[str, Any]
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                # 고유번호검색(/in0004000169) — 조회 전용. 더미 번호로 관문 통과만 확인한다.
                # 발급·열람(163/165/1437/1438)은 민원캐시가 차감되므로 점검에 쓰지 않는다.
                resp = await client.post(f"{_host()}/in0004000169", headers=_headers(),
                                         json={"uniqNo": "00000000000000"})
                if resp.status_code != 200:
                    out = {"access": "unreachable", "checked": True,
                           "message": "하이픈 응답 오류 — 잠시 후 다시 시도하세요."}
                else:
                    access, message = classify_probe_response(resp.json())
                    out = {"access": access, "checked": True, "message": message}
        except Exception as e:  # noqa: BLE001
            logger.warning("하이픈 권한 점검 예외", err=str(e)[:120])
            out = {"access": "unreachable", "checked": True,
                   "message": "하이픈 연결에 실패했습니다 — 잠시 후 다시 시도하세요."}

        # 점검 호출은 관측 가능해야 한다(호출량·비용 사후 검증용).
        logger.info("하이픈 권한 점검", access=out.get("access"))
        _ACCESS_CACHE[cred] = (time.monotonic(), dict(out))
        return out


# 하이픈 검색 파라미터는 코드가 아니라 **한글 값**을 받는다(명세·라이브 확증).
KINDCLS_BY_CODE: dict[str, str] = {"0": "전체", "1": "집합건물", "2": "토지", "3": "건물"}


def kindcls_value(realty_type: str | None) -> str:
    """구분코드(0/1/2/3) → 하이픈이 받는 한글 값. 미지·미지정은 '전체'(필터 없음)."""
    return KINDCLS_BY_CODE.get((realty_type or "").strip(), "전체")


def _search_item(item: dict[str, Any]) -> dict[str, Any]:
    """검색결과 1건 → 내부 공통 형태.

    ★응답 키에는 'get' 접두사가 없다(명세 표기와 실제 응답이 다름 — 라이브 확증).
      과거 구현이 get* 키를 읽어 모든 값이 None이었다. 옛 표기도 함께 받아 안전하게 둔다.
    """
    def pick(*names: str) -> Any:
        for n in names:
            v = item.get(n)
            if v not in (None, ""):
                return v
        return None

    uno = pick("부동산고유번호", "get부동산고유번호") or ""
    return {
        "unique_no": str(uno).replace("-", "").strip(),
        "gubun": pick("구분", "get구분"),
        "owner": pick("소유자", "get소유자"),
        "jibun": pick("부동산소재지번", "get부동산소재지번"),
        "sangtae": pick("상태", "get상태"),
    }


async def search_by_simple_address(
    address: str,
    kindcls: str = "전체",
    cls_flag: str = "현행",
    limit_page: str = "1",
    page_no: str = "1",
    admin_regn1: str = "전체",
    detail_yn: str = "Y",
) -> dict[str, Any]:
    """간편주소로 부동산 고유번호 검색 (POST /in0004000168).

    ★벤더 명세·라이브 확증 사항(이전 구현이 전부 0건이던 원인):
      · admin_regn1(시/도)은 **필수** — 빠지면 항상 "결과 없음"이 돌아온다.
      · kindcls·cls_flag는 코드("0"/"1")가 아니라 **한글 값**을 받는다.
      · limitPage는 '입력한 페이지까지 조회'로 1페이지 = 10건(1건 아님).
        전체 건수는 grdTotCnt, 페이지 수는 totPage로 온다.
      · 응답 항목 키에는 'get' 접두사가 없다(명세 표기와 실제 응답이 다름).
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

    import httpx

    url = f"{_host()}/in0004000168"
    body = {
        "kindcls": kindcls,
        "admin_regn1": admin_regn1,   # ★필수 — 누락 시 항상 결과 0건
        "cls_flag": cls_flag,
        "simple_address": addr,
        "detailYn": detail_yn,        # Y여야 소유자가 함께 온다
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
        items = [_search_item(it) for it in (res_data.get("list") or []) if isinstance(it, dict)]

        return {
            "ok": True,
            "status": "ok",
            "items": items,
            "total": res_data.get("totCnt") or len(items),
            # 전체 건수·페이지 수 — 수집분이 일부임을 소비처가 알 수 있어야 한다.
            "total_all": res_data.get("grdTotCnt"),
            "total_pages": res_data.get("totPage"),
            "raw": data,
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("하이픈 간편주소검색 예외", err=str(e)[:120])
        return {"ok": False, "status": "error", "items": [], "message": str(e)[:200]}


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
        # 검색 응답 형태는 간편주소와 동일 — 같은 매퍼를 쓴다(키 결함이 한 곳만 고쳐지지 않도록).
        items = [_search_item(it) for it in (res_data.get("list") or []) if isinstance(it, dict)]
        return {"ok": True, "status": "ok", "items": items,
                "total": res_data.get("totCnt") or len(items), "raw": data}
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
    """등기부등본 열람 (POST /in0004000163 — 회원 열람, 민원캐시 차감).

    ★엔드포인트 교정: 기존 /in0004000948은 벤더 명세의 제공 엔드포인트 목록에 없다
      (목록: 163 열람 · 165 비회원열람 · 1438 발급 · 1437 비회원발급 · 166~169 주소검색).
      필수 본문은 userId/userPw(인터넷등기소 자격) · searchDiv='uniqNo' · uniqNo.
    """
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

    if not (uid and (upw or upw_enc)):
        # 열람은 인터넷등기소 자격이 필수 — 없으면 호출해도 실패하므로 미리 정직하게 알린다.
        return {
            "ok": False,
            "status": "not_configured",
            "message": ("인터넷등기소 자격(HYPHEN_IROS_USER_ID / HYPHEN_IROS_USER_PW)이 필요합니다 — "
                        "관리자 키 화면에서 입력하세요."),
        }

    url = f"{_host()}/in0004000163"
    body: dict[str, Any] = {
        "userId": uid,
        "searchDiv": "uniqNo",
        "uniqNo": uno,
        "cmortCheck": cmort_check,
        "tradeCheck": trade_check,
        "pdfHex": "Y",
        "xmlYn": "N",
        "display": display,
        "dupChk": "Y",
    }
    if upw_enc:
        body["userPwEnc"] = upw_enc
    else:
        body["userPw"] = upw
    # 선불전자지급수단은 명세상 열람(163) 본문에 없다 — 값이 있을 때만 덧붙인다(하위호환).
    if pno:
        body["payNo"] = pno
    if ppw_enc:
        body["payPwEnc"] = ppw_enc
    elif ppw:
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

    # 구분을 검색 단계에서도 좁힌다 — 한 주소에 수십 건이 잡히므로(호미곶 78건 실측)
    # 전부 받아 뒤에서 고르면 원하는 물건이 1페이지 밖으로 밀려날 수 있다.
    search_res = await search_by_simple_address(address, kindcls=kindcls_value(realty_type))
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
    # 수집분이 전체의 일부일 때는 그 사실을 알린다(선택이 부분집합 위에서 이뤄졌음).
    total_all = search_res.get("total_all")
    try:
        if total_all and int(total_all) > len(search_res["items"]):
            fetch_res.setdefault(
                "select_note",
                f"주소 검색 결과 {total_all}건 중 {len(search_res['items'])}건만 조회해 그중에서 골랐습니다. "
                "원하는 물건이 아니면 지번을 더 구체적으로 입력하세요.",
            )
    except (TypeError, ValueError):
        pass
    return fetch_res
