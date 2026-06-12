"""틸코(Tilko) 등기부등본 조회/발급 API 클라이언트 — IROS ID 로그인 방식(v2.0).

규격(틸코 ApiDoc 확인):
 - 엔드포인트: POST https://api.tilko.net/api/v2.0/Iros2IdLogin/RealtyRegistry
 - 공개키: GET https://api.tilko.net/api/Auth/GetPublicKey?APIkey={API_KEY} → {"PublicKey": base64}
 - 헤더: Content-Type=application/json, API-KEY, ENC-KEY(=RSA(PKCS1v15)로 암호화한 AES키 base64)
 - 암호화: AES-128-CBC, 16B 랜덤키, IV=0x00*16, PKCS7, base64. 민감필드는 "ENC:"+base64(암호문).
 - 민감필드: UserId, UserPassword, EmoneyNo1, EmoneyNo2, EmoneyPwd (Pin·플래그는 평문).

키(시크릿 스토어): TILKO_API_KEY(보안). IROS 자격: IROS_USER_ID·IROS_USER_PW·IROS_EMONEY_NO1·
IROS_EMONEY_NO2·IROS_EMONEY_PWD·IROS_PIN. 미설정/실패 시 graceful 오류 반환(예외 미전파).

⚠ 부동산 식별 필드(소재지/고유번호/등기종류/열람·발급 등)는 호출측 property_params로 주입
(ApiDoc이 {{REQ_JSON}}로 가려 미확정 — 명세서/샘플 확정 후 고정 매핑 예정).
"""

from __future__ import annotations

import base64
import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

def _host() -> str:
    """틸코 호스트 — 운영=api.tilko.net(기본), 데모=dev.tilko.net. TILKO_API_HOST로 무중단 전환."""
    return (os.getenv("TILKO_API_HOST") or "https://api.tilko.net").rstrip("/")


def _pubkey_url() -> str:
    return f"{_host()}/api/Auth/GetPublicKey"


def _realty_url() -> str:
    return f"{_host()}/api/v2.0/Iros2IdLogin/RealtyRegistry"


def _search_url() -> str:
    # 등기물건 주소검색 — 주소 → 부동산 고유번호. IROS 로그인·전자결제 불필요(Tilko API키만).
    return f"{_host()}/api/v2.0/iros/risuconfirmsimplec"
_IV = b"\x00" * 16


def tilko_key() -> str:
    return (os.getenv("TILKO_API_KEY") or "").strip()


def tilko_ready() -> bool:
    return bool(tilko_key())


def iros_creds() -> dict[str, str]:
    """IROS 자격(시크릿 스토어/.env). 비밀번호·전자지급 정보는 평문 채팅 금지·서버에만."""
    return {
        "UserId": (os.getenv("IROS_USER_ID") or "").strip(),
        "UserPassword": (os.getenv("IROS_USER_PW") or "").strip(),
        # 전자지불 선불카드: NO1=앞8자리(영문포함), NO2=뒤4자리(숫자), PWD=비밀번호
        "EmoneyNo1": (os.getenv("IROS_EMONEY_NO1") or "").strip(),
        "EmoneyNo2": (os.getenv("IROS_EMONEY_NO2") or "").strip(),
        "EmoneyPwd": (os.getenv("IROS_EMONEY_PWD") or "").strip(),
        # ※ Pin은 자격이 아니라 '부동산 고유번호'(요청별 인자) — fetch_realty_registry(unique_no=…)로 전달
    }


def iros_ready() -> bool:
    c = iros_creds()
    return bool(c["UserId"] and c["UserPassword"])


async def get_public_key() -> str | None:
    """틸코 RSA 공개키(base64 DER) 조회. 실패 시 None."""
    key = tilko_key()
    if not key:
        return None
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(_pubkey_url(), params={"APIkey": key})
            r.raise_for_status()
            data = r.json()
        return (data or {}).get("PublicKey") or (data or {}).get("publicKey")
    except Exception as e:  # noqa: BLE001
        logger.warning("틸코 공개키 조회 실패", err=str(e)[:140])
        return None


def _build_cipher(public_key_b64: str) -> tuple[str, bytes]:
    """AES-128 랜덤키 생성 → RSA(PKCS1v15)로 암호화한 ENC-KEY(base64) + 평문 AES키 반환."""
    from cryptography.hazmat.primitives.asymmetric import padding as asy_padding
    from cryptography.hazmat.primitives.serialization import load_der_public_key

    aes_key = os.urandom(16)
    pub = load_der_public_key(base64.b64decode(public_key_b64))
    enc_key = base64.b64encode(pub.encrypt(aes_key, asy_padding.PKCS1v15())).decode()  # type: ignore[arg-type]
    return enc_key, aes_key


def _aes_encrypt(value: str, aes_key: bytes) -> str:
    """AES-128-CBC(IV=0)·PKCS7 암호화 → base64.

    ★틸코 공식 샘플(aesEncrypt)은 base64만 반환하고 "ENC:" 프리픽스를 붙이지 않는다.
      이전 구현이 "ENC:"를 붙여 틸코 복호화가 깨지던(HTTP 500) 버그를 수정.
    """
    from cryptography.hazmat.primitives import padding as sym_padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(value.encode("utf-8")) + padder.finalize()
    enc = Cipher(algorithms.AES(aes_key), modes.CBC(_IV)).encryptor()
    ct = enc.update(padded) + enc.finalize()
    return base64.b64encode(ct).decode()


async def search_unique_no(address: str, page: str = "1") -> dict[str, Any]:
    """등기물건 주소검색(RISUConfirmSimpleC) — 주소 → 부동산 고유번호 목록.

    ★IROS 로그인·전자결제 불필요(Tilko API키만). RealtyRegistry 전 단계로 고유번호 확보용.
    반환: {ok, status, items:[{unique_no, gubun, jibun, sangtae}], total, message}
    """
    if not tilko_ready():
        return {"ok": False, "status": "not_configured", "items": [],
                "message": "TILKO_API_KEY 미설정(관리자 키화면 입력 필요)"}
    addr = (address or "").strip()
    if not addr:
        return {"ok": False, "status": "bad_request", "items": [], "message": "검색할 주소가 필요합니다."}

    pub = await get_public_key()
    if not pub:
        return {"ok": False, "status": "provider_error", "items": [], "message": "틸코 공개키 조회 실패(API키 확인)"}

    try:
        enc_key, aes_key = _build_cipher(pub)
        body = {
            "Address": _aes_encrypt(addr, aes_key),   # [필수] 암호화 — 시/군/구 등 검색어 포함
            "Page": _aes_encrypt(str(page or "1"), aes_key),
        }
        import httpx

        headers = {"Content-Type": "application/json", "API-KEY": tilko_key(), "ENC-KEY": enc_key}
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(_search_url(), json=body, headers=headers)
            if r.status_code != 200:
                return {"ok": False, "status": "provider_error", "items": [],
                        "message": f"틸코 주소검색 오류(HTTP {r.status_code})", "raw": r.text[:300]}
            data = r.json()

        err = data.get("ErrorCode")
        if err not in (None, 0, "0"):
            return {"ok": False, "status": "provider_error", "items": [], "error_code": err,
                    "message": data.get("Message") or "주소검색 실패"}

        result = data.get("Result") or {}
        rows = (result.get("Result") if isinstance(result, dict) else None) or []
        if isinstance(rows, dict):
            rows = [rows]
        items = [{
            "unique_no": (it.get("BudongsanGoyubeonho") or "").replace("-", "").strip(),
            "gubun": it.get("Gubun"),
            "jibun": it.get("BudongsanSojaejibeon"),
            "sangtae": it.get("Sangtae"),
        } for it in rows if isinstance(it, dict)]
        total = result.get("TotalCount") if isinstance(result, dict) else len(items)
        return {"ok": True, "status": "ok", "items": items, "total": total,
                "point_balance": data.get("PointBalance")}
    except Exception as e:  # noqa: BLE001
        logger.warning("틸코 주소검색 실패", err=str(e)[:120])
        return {"ok": False, "status": "error", "items": [], "message": str(e)[:200]}


async def fetch_realty_registry(
    *,
    unique_no: str = "",
    cmort_flag: str = "N",     # 공동담보/전세목록 추출(Y/N), 기본 미추출
    trade_seq_flag: str = "N",  # 매매목록 추출(Y/N), 기본 미추출
    abs_cls: str = "11",        # 등기기록유형(11=현재유효, 12=말소포함), 기본 현재유효
    rgs_mttr_smry: str = "",    # 등기사항요약(1=포함, 공백=미포함), 기본 미포함
) -> dict[str, Any]:
    """등기부등본 조회/발급(IROS ID 로그인). 성공 시 {ok, pdf_data, xml_data, ...}.

    ★틸코 명세(v2.0 RealtyRegistry):
      - Pin = 부동산 고유번호(14자리, '-' 제외, 평문) ← 조회 대상 부동산 지정
      - EmoneyNo1 = 전자지불 선불카드 앞 8자리(영문 포함), EmoneyNo2 = 뒤 4자리(숫자),
        EmoneyPwd = 선불카드 비밀번호 (모두 AES 암호화) ← IROS_EMONEY_* 시크릿
    """
    if not tilko_ready():
        return {"ok": False, "status": "not_configured", "message": "TILKO_API_KEY 미설정(관리자 키화면 입력 필요)"}
    if not iros_ready():
        return {"ok": False, "status": "not_configured",
                "message": "IROS 자격(IROS_USER_ID/IROS_USER_PW 등) 미설정(관리자 키화면 입력 필요)"}

    uno = (unique_no or "").replace("-", "").strip()
    if not uno:
        return {"ok": False, "status": "need_unique_no",
                "message": "부동산 고유번호(14자리)가 필요합니다. 주소검색으로 고유번호를 먼저 조회하세요."}

    pub = await get_public_key()
    if not pub:
        return {"ok": False, "status": "provider_error", "message": "틸코 공개키 조회 실패(API키 확인)"}

    try:
        enc_key, aes_key = _build_cipher(pub)
        c = iros_creds()
        body: dict[str, Any] = {
            "Auth": {
                "UserId": _aes_encrypt(c["UserId"], aes_key),
                "UserPassword": _aes_encrypt(c["UserPassword"], aes_key),
            },
            "Pin": uno,  # 부동산 고유번호 14자리(평문)
            "EmoneyNo1": _aes_encrypt(c["EmoneyNo1"], aes_key) if c["EmoneyNo1"] else "",
            "EmoneyNo2": _aes_encrypt(c["EmoneyNo2"], aes_key) if c["EmoneyNo2"] else "",
            "EmoneyPwd": _aes_encrypt(c["EmoneyPwd"], aes_key) if c["EmoneyPwd"] else "",
            "CmortFlag": cmort_flag,
            "TradeSeqFlag": trade_seq_flag,
            "AbsCls": abs_cls,
            "RgsMttrSmry": rgs_mttr_smry,
        }

        import httpx

        headers = {"Content-Type": "application/json", "API-KEY": tilko_key(), "ENC-KEY": enc_key}
        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(_realty_url(), json=body, headers=headers)
            if r.status_code != 200:
                return {"ok": False, "status": "provider_error",
                        "message": f"틸코 응답 오류(HTTP {r.status_code})", "raw": r.text[:300]}
            data = r.json()

        err = int(data.get("ErrorCode") or 0)
        if err != 0:
            return {"ok": False, "status": "provider_error", "error_code": err,
                    "message": data.get("Message") or "틸코 등기 조회 실패",
                    "point_balance": data.get("PointBalance"), "raw": data}
        return {
            "ok": True, "status": "ok", "origin": "tilko",
            "pdf_data": data.get("PdfData"), "xml_data": data.get("XmlData"),
            "transaction_key": data.get("TransactionKey") or data.get("ApiTxKey"),
            "point_balance": data.get("PointBalance"),
            "message": data.get("Message"),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("틸코 등기 조회 예외", err=str(e)[:160])
        return {"ok": False, "status": "error", "message": str(e)[:200]}
