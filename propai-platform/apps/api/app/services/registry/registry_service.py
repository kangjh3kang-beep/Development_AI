"""부동산 등기부(소유관계) 연동 — 하이픈(Hyphen) 1순위 + Tilko & PDF 업로드 3단계 파이프라인.

기존 apick 및 CODEF 모듈은 사용 불가하여 완전 제거되었으며,
하이픈(Hyphen Data Market) API를 기본 1순위 공급자로 사용합니다.

파이프라인:
 1순위: 하이픈 (Hyphen) API (HYPHEN_HKEY, HYPHEN_USER_ID)
 2순위: 틸코 (Tilko) API (TILKO_API_KEY, IROS_USER_ID)
 3순위: 비상 등기부 PDF 직접 업로드 (parse_registry_pdf)
"""

from __future__ import annotations

import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _config() -> dict[str, str]:
    return {
        "url": (os.getenv("REGISTRY_API_URL") or "").strip(),
        "key": (os.getenv("REGISTRY_API_KEY") or "").strip(),
        "provider": (os.getenv("REGISTRY_PROVIDER") or "hyphen").strip().lower(),
    }


def is_configured() -> bool:
    from app.services.registry.hyphen_client import hyphen_ready
    from app.services.registry.tilko_client import tilko_ready

    cfg = _config()
    if cfg["provider"] == "tilko":
        return tilko_ready()
    # 기본은 hyphen
    return hyphen_ready() or tilko_ready() or bool(cfg["url"] and cfg["key"])


class RegistryService:
    def status(self) -> dict[str, Any]:
        from app.services.registry.hyphen_client import hyphen_ready
        from app.services.registry.tilko_client import tilko_ready

        cfg = _config()
        p = cfg["provider"]

        if p == "tilko":
            ok = tilko_ready()
            return {
                "configured": ok,
                "provider": "tilko",
                "register_ready": ok,
                "message": (
                    "Tilko 등기부 API 연결됨" if ok else "Tilko 미설정 — TILKO_API_KEY / IROS 자격 필요"
                ),
            }

        # 기본 하이픈 (hyphen)
        h_ok = hyphen_ready()
        t_ok = tilko_ready()
        return {
            "configured": h_ok or t_ok,
            "provider": "hyphen" if h_ok else ("tilko" if t_ok else "pdf_upload"),
            "register_ready": h_ok or t_ok,
            "hyphen_ready": h_ok,
            "tilko_ready": t_ok,
            "message": (
                "하이픈(Hyphen) 부동산 등기부 API 1순위 연결됨"
                if h_ok
                else (
                    "Tilko 보조 등기부 API 연결됨 (하이픈 미설정)"
                    if t_ok
                    else "상용 등기 API 미설정 — HYPHEN_HKEY & HYPHEN_USER_ID 필요 (비상 PDF 업로드 기능 이용 가능)"
                )
            ),
        }

    async def live_status(self) -> dict[str, Any]:
        """status()에 '실제 호출 가능한가'를 더한 정직한 상태.

        왜 필요한가: status()는 키 존재만 보므로, 키가 유효해도 계약에 없는 API라
        벤더가 거절하는 상태(하이픈 "권한이 없는 API 입니다")를 '연결됨'으로 표시했다.
        키 입력 후 "테스트"를 눌러 초록을 본 사용자가 정작 조회에 실패하는 원인이다.
        틸코가 공개키를 실제로 받아 검증하는 것과 대칭을 맞춘다.

        기존 status()의 키·형태는 그대로 두고 additive로만 덧붙인다(소비처 무영향).
        """
        from app.services.registry.hyphen_client import probe_api_access

        out = dict(self.status())
        if not out.get("hyphen_ready"):
            return out

        probe = await probe_api_access()
        out["hyphen_access"] = probe.get("access")
        out["hyphen_access_message"] = probe.get("message")
        if probe.get("access") != "ok":
            # 실제로 못 쓰는 상태를 '연결됨'이라 말하지 않는다.
            out["register_ready"] = bool(out.get("tilko_ready"))
            out["message"] = probe.get("message") or out.get("message")
        return out

    async def get_one(
        self,
        pnu: str | None = None,
        address: str | None = None,
        unique_no: str | None = None,
        pdf_input: bytes | str | None = None,
        realty_type: str | None = None,
        dong: str | None = None,
        ho: str | None = None,
    ) -> dict[str, Any]:
        """단건 등기부 조회/발급/파싱.

        - pdf_input 전달 시: 비상 PDF 업로드 파서(parse_registry_pdf) 즉시 실행
        - 1순위: 하이픈 (Hyphen)
        - 2순위: 틸코 (Tilko)
        - 3순위: PDF 파싱 안내

        realty_type/dong/ho: 사용자가 고른 부동산 구분(1집합건물·2토지·3건물)과
        집합건물의 동·호. 주소검색 결과가 여러 건일 때 맞는 물건을 고르는 데 쓴다.
        (구분 코드체계·선택규칙은 realty_kind 모듈이 단일 출처.)
        """
        item = {"pnu": pnu, "address": address, "unique_no": unique_no}

        # 3순위 (우선): 직접 전달된 PDF 파싱 처리
        if pdf_input:
            from app.services.registry.registry_pdf_parser import parse_registry_pdf

            res = parse_registry_pdf(pdf_input)
            return {**item, **res}

        from app.services.registry.hyphen_client import (
            fetch_realty_registry,
            fetch_registry_by_address,
            hyphen_ready,
            probe_api_access,
        )
        from app.services.registry.tilko_client import fetch_realty_registry as fetch_tilko_registry
        from app.services.registry.tilko_client import tilko_ready

        cfg = _config()
        p = cfg["provider"]

        # 1순위: 하이픈 (Hyphen)
        if (p == "hyphen" or not p) and hyphen_ready():
            probe = await probe_api_access()
            if probe.get("access") == "ok":
                if unique_no:
                    h_res = await fetch_realty_registry(unique_no=unique_no)
                elif address:
                    h_res = await fetch_registry_by_address(
                        address=address, realty_type=realty_type, dong=dong, ho=ho
                    )
                else:
                    return {**item, "status": "bad_request", "message": "주소 또는 고유번호가 필요합니다."}

                if h_res.get("status") == "ok":
                    return {**item, **h_res}

                logger.warning("하이픈 등기 조회 실패, 2순위 Tilko 폴백 시도", err=h_res.get("message"))
            else:
                logger.warning("하이픈 API 인증/권한 실패, 2순위 Tilko 폴백 시도", msg=probe.get("message"))

        # 2순위: 틸코 (Tilko)
        if tilko_ready():
            if unique_no:
                t_res = await fetch_tilko_registry(unique_no=unique_no)
                if t_res.get("ok"):
                    return {
                        **item,
                        "status": "ok",
                        "origin": "tilko",
                        "pdf_base64": t_res.get("pdf_data"),
                        "has_pdf": bool(t_res.get("pdf_data")),
                        "message": "Tilko 등기부 조회 성공",
                    }
            elif address:
                from app.services.registry.realty_kind import select_registry_item
                from app.services.registry.tilko_client import search_unique_no

                s_res = await search_unique_no(address)
                if s_res.get("ok") and s_res.get("items"):
                    # 하이픈과 동일 규칙으로 구분·동·호에 맞는 물건 선택(첫 건 맹목 선택 금지)
                    picked, note = select_registry_item(s_res["items"], realty_type, dong, ho)
                    uno = (picked or {}).get("unique_no")
                    t_res = await fetch_tilko_registry(unique_no=uno) if uno else {}
                    if t_res.get("ok"):
                        return {
                            **item,
                            "status": "ok",
                            "origin": "tilko",
                            "unique_no": uno,
                            "realty_gubun": (picked or {}).get("gubun"),
                            **({"select_note": note} if note else {}),
                            "pdf_base64": t_res.get("pdf_data"),
                            "has_pdf": bool(t_res.get("pdf_data")),
                            "message": "Tilko 등기부 조회 성공",
                        }

        # 커스텀 URL 방식 (설정 시)
        if cfg["url"] and cfg["key"]:
            import httpx

            try:
                async with httpx.AsyncClient(timeout=40.0) as client:
                    resp = await client.post(
                        cfg["url"],
                        headers={"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"},
                        json={"pnu": pnu, "address": address},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                return {
                    **item,
                    "status": "ok",
                    "origin": "custom",
                    "owner": data.get("owner"),
                    "summary": data.get("summary"),
                    "pdf_url": data.get("pdf_url"),
                    "raw": data,
                }
            except Exception as e:  # noqa: BLE001
                logger.warning("커스텀 등기부 API 조회 실패", err=str(e)[:120])

        return {
            **item,
            "status": "not_configured",
            "message": "등기부 API(Hyphen/Tilko) 미설정 또는 장애 발생 — '비상 등기부 PDF 직접 업로드' 기능을 이용하세요.",
        }

    async def bulk(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """다필지 일괄 등기부 조회."""
        import asyncio

        if not items:
            return {"configured": is_configured(), "count": 0, "results": []}

        sem = asyncio.Semaphore(5)

        async def one(it: dict) -> dict:
            async with sem:
                # 다필지 일괄(토지조서)도 구분을 넘긴다 — 안 넘기면 주소검색 결과에서
                # 첫 물건이 맹목 선택되고, realty_type이 없어 고지조차 생성되지 않는다.
                return await self.get_one(
                    pnu=it.get("pnu"),
                    address=it.get("address"),
                    unique_no=it.get("unique_no"),
                    realty_type=it.get("realty_type") or "2",  # 토지조서 기본=토지
                    dong=it.get("dong"),
                    ho=it.get("ho"),
                )

        results = await asyncio.gather(*[one(it) for it in items])
        return {"configured": is_configured(), "count": len(results), "results": list(results)}
