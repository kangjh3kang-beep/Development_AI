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
# 권한 거절 및 인증 실패를 알리는 벤더 문구/코드
_FORBIDDEN_HINTS = (
    "권한이 없는 API",
    "권한이 없습니다",
    "권한 없음",
    "UserId 또는 HKey가 올바르지 않습니다",
    "HKey가 올바르지 않습니다",
    "회원 정보가 존재하지 않습니다",
    "올바르지 않습니다",
)


def _is_forbidden_message(msg: str) -> bool:
    m = (msg or "").strip()
    if not m:
        return False
    if any(h in m for h in _FORBIDDEN_HINTS):
        return True
    return ("권한" in m or "HKey" in m or "UserId" in m) and ("API" in m.upper() or "올바르지" in m or "없습니다" in m)


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
                err_yn = common.get("errYn")
                err_cd = str(common.get("errCd") or "")
                err_msg = str(common.get("errMsg") or "")

                if err_yn == "Y":
                    if err_cd in ("HDM009", "HDM008") or _is_forbidden_message(err_msg):
                        out = {
                            "access": "forbidden",
                            "checked": True,
                            "message": f"하이픈 인증 실패 ({err_msg or 'UserId 또는 HKey가 올바르지 않습니다'}) — 설정에서 HKey 및 User-Id를 확인하세요.",
                        }
                    else:
                        # errYn=Y여도 '권한/인증' 사유가 아니면 관문은 통과한 것(데이터 없음 등)
                        out = {"access": "ok", "checked": True, "message": "하이픈 등기 API 호출 권한 확인됨"}
                else:
                    out = {"access": "ok", "checked": True, "message": "하이픈 등기 API 호출 권한 확인됨"}
    except Exception as e:  # noqa: BLE001
        logger.warning("하이픈 권한 점검 예외", err=str(e)[:120])
        out = {"access": "unreachable", "checked": True,
               "message": f"하이픈 연결 실패: {str(e)[:80]}"}

    _ACCESS_CACHE["v"] = (now, dict(out))
    return out


def normalize_address_candidates(address: str) -> list[str]:
    """임야/산지 지번(산 1-1 ↔ 산1-1) 및 광역시/도 축약 주소 변형 후보를 자동 생성.

    1차 주소검색 실패 시 자동 폴백하여 벤더 주소검색 파서의 미세한 포맷 차이에 따른
    주소검색 누락(no_match)을 자동 보정한다.
    """
    import re

    addr = " ".join((address or "").split()).strip()
    if not addr:
        return []

    candidates: list[str] = []

    def _add(s: str) -> None:
        s = " ".join(s.split()).strip()
        if s and s not in candidates:
            candidates.append(s)

    _add(addr)

    # 1. "산 1-1" ↔ "산1-1" (산과 본번 사이 띄어쓰기 변형)
    v1 = re.sub(r"산\s+(\d+)", r"산\1", addr)
    _add(v1)
    v2 = re.sub(r"산(\d+)", r"산 \1", addr)
    _add(v2)

    # 2. 광역시/도 제거 및 시/군/구 이하 축약 주소 후보 생성
    parts = addr.split()
    if len(parts) >= 3:
        # 광역시/도 제거
        if any(parts[0].endswith(e) for e in ("도", "시", "특별시", "광역시", "특별자치도", "특별자치시")):
            without_do = " ".join(parts[1:])
            _add(without_do)
            _add(re.sub(r"산\s+(\d+)", r"산\1", without_do))
            _add(re.sub(r"산(\d+)", r"산 \1", without_do))

        # 읍/면/동/리 + 지번 축약
        for i in range(1, len(parts) - 1):
            sub = " ".join(parts[i:])
            if re.search(r"(?:산\s*)?\d+", sub):
                _add(sub)
                _add(re.sub(r"산\s+(\d+)", r"산\1", sub))
                _add(re.sub(r"산(\d+)", r"산 \1", sub))

    return candidates



# ★하이픈 주소검색은 **한글 문자열**을 받는다 — 숫자 코드가 아니다(2026-08-12 명세 확인).
#   내부 구분 코드(realty_kind: "1"집합건물 "2"토지 "3"건물 "0"/None 전체)를 그 표기로 옮긴다.
_KINDCLS_KO = {"0": "전체", "1": "집합건물", "2": "토지", "3": "건물", "": "전체"}
#   등기등록상태도 마찬가지다(현행/폐쇄/현행+폐쇄).
_CLSFLAG_KO = {"1": "현행", "2": "폐쇄", "3": "현행+폐쇄", "": "현행"}

# 시/도 표기(`admin_regn1`)는 **필수**인데 종전 요청에는 아예 없었다.
_SIDO = (
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시",
    "울산광역시", "세종특별자치시", "경기도", "강원특별자치도", "강원도",
    "충청북도", "충청남도", "전북특별자치도", "전라북도", "전라남도",
    "경상북도", "경상남도", "제주특별자치도",
)
# 축약 표기도 흔히 들어온다("서울 강남구 …").
_SIDO_ALIAS = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
    "제주": "제주특별자치도",
}


def pick_field(d: dict[str, Any], name: str) -> Any:
    """응답에서 필드를 읽는다 — `get` 접두사 유무를 **양쪽 다** 본다.

    ★2026-08-12 라이브 실측: 실제 응답 키에는 `get` 접두사가 **없다**(`부동산고유번호`).
    그런데 벤더 명세 화면의 스키마는 `get부동산고유번호` 로 표시한다. 그 표기를 믿고 짠
    파서는 **검색이 성공해도** 값을 못 읽어 `unique_no` 가 빈 문자열이 됐다.

    ★모듈 레벨 공용 헬퍼인 이유: 같은 파일 안에 같은 파서가 **셋**(주소검색·고유번호검색·
    등기부 열람) 있는데 처음엔 한 곳만 고쳤다. 리뷰가 "형제 미스윕" 으로 잡았다 —
    한 곳을 고치면 전역이 따라오게 공용화한다(CLAUDE.md 전역 전파방지).

    ★빈 문자열은 값으로 인정하지 않는다 — 두 표기가 공존하고 한쪽이 비어 있을 때
    비어 있는 쪽을 채택하면 결함이 그대로 남는다.
    """
    v = d.get(name)
    if v is None or v == "":
        v2 = d.get(f"get{name}")
        return v if v2 is None or v2 == "" else v2
    return v


def extract_sido(address: str) -> str:
    """주소 문자열에서 시/도(`admin_regn1`)를 뽑는다. 못 뽑으면 빈 문자열.

    ★이 값이 **필수**다. 빠지면 하이픈은 `[C0000-002] 검색조건에 대한 결과가 없습니다`
    를 돌려준다 — "결과 없음" 처럼 보이지만 실제로는 **요청이 불완전**한 것이다.
    그 오해 때문에 "등기 열람이 안 된다" 가 오래 방치됐다.
    """
    a = (address or "").strip()
    for s in _SIDO:
        if a.startswith(s):
            return s
    head = a.split()[0] if a.split() else ""
    return _SIDO_ALIAS.get(head, "")


async def _search_single_address(
    address: str,
    kindcls: str = "0",
    cls_flag: str = "1",
    limit_page: str = "1",
    page_no: str = "1",
) -> dict[str, Any]:
    """단일 주소 원시 검색 (POST /in0004000168).

    ★2026-08-12 명세 대조로 두 결함을 고쳤다(라이브 실측으로 확증):
      1) 값 형식 — `kindcls`·`cls_flag` 는 **한글 문자열**인데 숫자 코드를 보내고 있었다.
      2) 필수 누락 — `admin_regn1`(시/도)를 아예 안 보냈다.
    둘 다 `[C0000-002] 결과가 없습니다` 로 나타나 **데이터가 없는 것처럼 보였다.**
    """
    import httpx

    url = f"{_host()}/in0004000168"
    sido = extract_sido(address)
    body = {
        "kindcls": _KINDCLS_KO.get(kindcls, kindcls or "전체"),
        # 시/도를 못 뽑으면 "전체" 로 둔다(문서상 기본값) — 빈 문자열은 VALID 오류다.
        "admin_regn1": sido or "전체",
        "cls_flag": _CLSFLAG_KO.get(cls_flag, cls_flag or "현행"),
        "simple_address": address,
        "detailYn": "Y",
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
                    "unique_no": (pick_field(item, "부동산고유번호") or "").replace("-", "").strip(),
                    "gubun": pick_field(item, "구분"),
                    "owner": pick_field(item, "소유자"),
                    "jibun": pick_field(item, "부동산소재지번"),
                    "sangtae": pick_field(item, "상태"),
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

    # 1차: 원본 주소 즉시 검색
    first_res = await _search_single_address(
        candidates[0], kindcls=kindcls, cls_flag=cls_flag, limit_page=limit_page, page_no=page_no
    )
    if first_res.get("ok") and first_res.get("items"):
        return first_res

    # 2차: 1차 실패 시 나머지 후보들을 병렬로 동시 검색(지연 및 타임아웃 방지)
    import asyncio

    if len(candidates) > 1:
        tasks = [
            _search_single_address(cand, kindcls=kindcls, cls_flag=cls_flag, limit_page=limit_page, page_no=page_no)
            for cand in candidates[1:]
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # ★`strict=True` — `tasks` 가 바로 위에서 `candidates[1:]` 로 생성되므로 길이가
        #   **항상 같다**. 어긋나는 일이 생기면 조용히 잘리는 대신 드러나는 편이 안전하다.
        #   (이 줄의 B905 로 main CI 가 막혀 **모든 PR** 이 함께 멈춰 있었다.)
        for cand, res in zip(candidates[1:], results, strict=True):
            if isinstance(res, dict) and res.get("ok") and res.get("items"):
                logger.info("하이픈 주소검색 병렬 자동보정 성공", original=addr, corrected=cand, count=len(res["items"]))
                return res

    return first_res or {"ok": False, "status": "no_match", "items": [], "message": "주소 검색 결과가 없습니다."}



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
                "unique_no": (pick_field(it, "부동산고유번호") or "").replace("-", "").strip(),
                "gubun": pick_field(it, "구분"),
                "owner": pick_field(it, "소유자"),
                "jibun": pick_field(it, "부동산소재지번"),
                "sangtae": pick_field(it, "상태"),
            }
            for it in raw_list
            if isinstance(it, dict)
        ]
        return {"ok": True, "status": "ok", "items": items, "raw": data}
    except Exception as e:  # noqa: BLE001
        logger.warning("하이픈 고유번호검색 예외", err=str(e)[:120])
        return {"ok": False, "status": "error", "items": [], "message": str(e)[:200]}


# ── 등기부 열람 응답 파서 ──────────────────────────────────────────────────
# ★2026-08-15 프로덕션 실측으로 드러난 **마지막 구간 결함**. 열람은 계속 성공하고
#   있었다(`errYn: N`, `열람일시` 기록). 벤더는 127KB PDF 와 26KB 구조화 등기 데이터를
#   매번 보냈다. 그런데 우리 파서가 **키 이름을 틀려** 둘 다 버렸다:
#     · PDF   : 우리가 읽은 `pdfHex` ↔ 실제 `pdfHexString`
#     · 소유자: 우리가 읽은 `소유자` ↔ 실제 `소유지분현황_갑구[].등기명의인`
#   결과는 `ok: True` + `has_pdf: False` + `owner: None` — **문서 없는 성공**이었고,
#   사용자에게는 "열람이 안 된다" 로 보였다. RC-1(주소검색 키)과 **같은 결함 클래스**다.
# ★그래서 이름 후보를 표로 두고 **하나라도 맞으면** 쓴다 — 벤더가 표기를 바꿔도 견딘다.
_PDF_HEX_KEYS = ("pdfHexString", "pdfHex", "pdf_hex", "pdfHexStr")
# 소유자는 갑구 여러 표에 흩어져 있다. 앞의 것이 더 직접적이다.
_OWNER_TABLES = ("소유지분현황_갑구", "소유권에_관한_사항_갑구")
_OWNER_FIELDS = ("등기명의인", "소유자", "권리자_및_기타사항")


def extract_pdf_hex(res_data: dict[str, Any]) -> str:
    """열람 응답에서 PDF 16진 문자열을 찾는다 — 표기 후보를 **전부** 본다."""
    for k in _PDF_HEX_KEYS:
        v = res_data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _clean(v: Any) -> str:
    """벤더 값에는 줄바꿈(`\r\n`)이 섞여 온다 — 표시용으로 한 줄로 만든다."""
    return " ".join(str(v or "").split())


def extract_owner(out_list: Any) -> str | None:
    """등기 본문에서 소유자(등기명의인)를 뽑는다.

    ★`outList` 는 dict 이고 그 안의 갑구 표들이 **JSON 문자열 또는 리스트**로 온다.
      실측 형태: `{"소유지분현황_갑구": [{"등기명의인": "○○주식회사 (소유자)", ...}]}`
    """
    import json

    if isinstance(out_list, list):
        out_list = out_list[0] if out_list else {}
    if not isinstance(out_list, dict):
        return None

    # 종전 표기(평평한 `소유자` 필드)도 계속 지원한다 — 있으면 그대로 쓴다.
    flat = pick_field(out_list, "소유자")
    if flat:
        return _clean(flat)

    for table in _OWNER_TABLES:
        rows = out_list.get(table)
        if isinstance(rows, str):
            try:
                rows = json.loads(rows)
            except Exception:  # noqa: BLE001
                continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            for f in _OWNER_FIELDS:
                v = _clean(row.get(f))
                if v:
                    return v
    return None


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
        pdf_hex = extract_pdf_hex(res_data)
        pdf_b64 = None
        if pdf_hex:
            try:
                pdf_bytes = bytes.fromhex(pdf_hex)
                pdf_b64 = base64.b64encode(pdf_bytes).decode()
            except Exception as pe:  # noqa: BLE001
                logger.warning("하이픈 등기부 PDF 변환 실패", err=str(pe)[:80])

        out_list = res_data.get("outList") or {}
        owner = extract_owner(out_list)

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
