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

_HOST = "https://api.tilko.net"
_PUBKEY_URL = f"{_HOST}/api/Auth/GetPublicKey"
_REALTY_URL = f"{_HOST}/api/v2.0/Iros2IdLogin/RealtyRegistry"
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
        "EmoneyNo1": (os.getenv("IROS_EMONEY_NO1") or "").strip(),
        "EmoneyNo2": (os.getenv("IROS_EMONEY_NO2") or "").strip(),
        "EmoneyPwd": (os.getenv("IROS_EMONEY_PWD") or "").strip(),
        "Pin": (os.getenv("IROS_PIN") or "").strip(),
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
            r = await client.get(_PUBKEY_URL, params={"APIkey": key})
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
    """AES-128-CBC(IV=0)·PKCS7 암호화 → "ENC:"+base64."""
    from cryptography.hazmat.primitives import padding as sym_padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(value.encode("utf-8")) + padder.finalize()
    enc = Cipher(algorithms.AES(aes_key), modes.CBC(_IV)).encryptor()
    ct = enc.update(padded) + enc.finalize()
    return "ENC:" + base64.b64encode(ct).decode()


async def fetch_realty_registry(
    *,
    property_params: dict[str, Any] | None = None,
    cmort_flag: str = "0",
    trade_seq_flag: str = "0",
    abs_cls: str = "0",
    rgs_mttr_smry: str = "0",
) -> dict[str, Any]:
    """등기부등본 조회/발급(IROS ID 로그인). 성공 시 {ok, pdf_data, xml_data, ...}.

    property_params: 부동산 식별 필드(소재지/고유번호/등기종류 등) — 명세 확정 후 주입.
    """
    if not tilko_ready():
        return {"ok": False, "status": "not_configured", "message": "TILKO_API_KEY 미설정(관리자 키화면 입력 필요)"}
    if not iros_ready():
        return {"ok": False, "status": "not_configured",
                "message": "IROS 자격(IROS_USER_ID/IROS_USER_PW 등) 미설정(관리자 키화면 입력 필요)"}

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
            "Pin": c["Pin"],  # 평문(있으면)
            "EmoneyNo1": _aes_encrypt(c["EmoneyNo1"], aes_key) if c["EmoneyNo1"] else "",
            "EmoneyNo2": _aes_encrypt(c["EmoneyNo2"], aes_key) if c["EmoneyNo2"] else "",
            "EmoneyPwd": _aes_encrypt(c["EmoneyPwd"], aes_key) if c["EmoneyPwd"] else "",
            "CmortFlag": cmort_flag,
            "TradeSeqFlag": trade_seq_flag,
            "AbsCls": abs_cls,
            "RgsMttrSmry": rgs_mttr_smry,
        }
        if property_params:
            body.update(property_params)   # 부동산 식별 필드(소재지/고유번호 등)

        import httpx

        headers = {"Content-Type": "application/json", "API-KEY": tilko_key(), "ENC-KEY": enc_key}
        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(_REALTY_URL, json=body, headers=headers)
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
