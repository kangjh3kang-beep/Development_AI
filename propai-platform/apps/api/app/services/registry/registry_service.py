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

from app.services.common.exc_detail import (
    balance_shortage_notice,
    exc_detail,
    is_balance_shortage,
)

logger = structlog.get_logger(__name__)


# ── 발급 재사용 캐시 — **유료 길목 하나**에 둔다 ────────────────────────────────
#
# ★왜 여기인가(2026-08-24). 등기부 발급은 민원캐시(선불 잔액)를 차감한다. 그런데 이 층에는
#   캐시가 전혀 없었고(실측: 이 파일에 cache 참조 0건), 위층 분석 캐시는 **성공한 분석만**
#   저장한다. 그래서 ①해석이 실패한 필지 ②`/registry/bulk` 재실행 이 **매번 재발급**됐다.
#   위층에서만 고치면 `bulk` 이 남는다 — 저장소 정책대로 **한 곳을 고쳐 전역이 따라오게** 한다.
#
# ★신선도·개인정보: 인메모리 전용, TTL 6시간, 항목 수 상한. 등기부 본문·PDF 는 **영속화하지
#   않는다**(`charge_idempotency.py` 가 경고한 "무기한 쌓이는 등기부 사본"을 만들지 않기 위함).
#   등기는 시점 문서라 짧은 창이 안전하다.
#
# ★탈출구: `force_reissue=True` 면 캐시를 건너뛴다. 발급본이 쓸모없었던 경우(이미지 PDF 등)에
#   갇히지 않아야 한다 — 돈이 드는 행위라 호출측이 명시할 때만.
_ISSUE_TTL_S = 6 * 3600.0
_ISSUE_MAX = 200                      # PDF(base64)를 들고 있으므로 개수를 묶는다
_ISSUE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _issue_key(pnu, address, unique_no, realty_type, dong, ho) -> str:
    """같은 물건이면 같은 키. 구분·동·호가 다르면 **다른 물건**이므로 키도 달라야 한다."""
    base = " ".join((address or "").split()).strip() or (pnu or "") or (unique_no or "")
    return f"{base}|{realty_type or '2'}|{dong or ''}|{ho or ''}"


def _issue_cache_get(key: str) -> dict[str, Any] | None:
    hit = _ISSUE_CACHE.get(key)
    if not hit:
        return None
    import time as _t

    if (_t.time() - hit[0]) >= _ISSUE_TTL_S:
        _ISSUE_CACHE.pop(key, None)
        return None
    return hit[1]


def _issue_cache_put(key: str, value: dict[str, Any]) -> None:
    import time as _t

    # 상한 초과 시 가장 오래된 항목부터 버린다(무한 성장 방지).
    if len(_ISSUE_CACHE) >= _ISSUE_MAX:
        for k in sorted(_ISSUE_CACHE, key=lambda k: _ISSUE_CACHE[k][0])[: max(1, _ISSUE_MAX // 10)]:
            _ISSUE_CACHE.pop(k, None)
    _ISSUE_CACHE[key] = (_t.time(), value)



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
        # ★상태는 **실제 동작과 같은 기준**으로 말해야 한다(2026-08-08 전역 스윕).
        #   `get_one` 이 `forbidden` 일 때만 하이픈을 건너뛰도록 바뀌었는데, 여기만 `!= "ok"` 로
        #   남아 있으면 **조회는 하이픈으로 가는데 상태는 '준비 안 됨'** 이라고 말하는 발산이 생긴다.
        #   · forbidden(자격증명 거부) → 정말 못 쓴다. ready 를 내리고 사유를 말한다.
        #   · unreachable(점검을 못 했다) → 본 호출은 시도하므로 ready 는 유지하되,
        #     **점검이 실패했다는 사실은 숨기지 않는다**(관리자가 원인을 봐야 한다).
        if probe.get("access") == "forbidden":
            out["register_ready"] = bool(out.get("tilko_ready"))
            out["message"] = probe.get("message") or out.get("message")
        elif probe.get("access") != "ok":
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
        force_reissue: bool = False,
    ) -> dict[str, Any]:
        """발급 **재사용 래퍼** — 실제 조회는 `_issue_uncached`.

        ★래퍼로 감싼 이유: 실제 조회 함수에는 반환 지점이 열 곳이 넘는다. 각 지점에 캐시
          저장을 손으로 붙이면 **반드시 하나를 빠뜨린다**(그 하나가 곧 재과금 경로가 된다).
          들어오고 나가는 길을 하나로 만들어 구조적으로 못 빠뜨리게 한다.

        ★`pdf_input` 경로는 사용자가 올린 파일을 파싱할 뿐 **무과금**이라 캐시를 태우지 않는다.
        ★성공한 발급만 보관한다 — 실패는 받은 것이 없으므로 재시도가 새로 발급하는 것이 옳다.
        """
        if pdf_input:
            return await self._issue_uncached(
                pnu=pnu, address=address, unique_no=unique_no, pdf_input=pdf_input,
                realty_type=realty_type, dong=dong, ho=ho,
            )

        key = _issue_key(pnu, address, unique_no, realty_type, dong, ho)
        if not force_reissue:
            hit = _issue_cache_get(key)
            if hit is not None:
                # 재사용 사실을 숨기지 않는다 — 위층·화면이 그 사실을 말할 수 있어야 한다.
                logger.info("등기부 발급 재사용(무과금)", key=key[:60])
                return {**hit, "reused_issue": True}

        out = await self._issue_uncached(
            pnu=pnu, address=address, unique_no=unique_no, pdf_input=None,
            realty_type=realty_type, dong=dong, ho=ho,
        )
        if isinstance(out, dict) and out.get("status") == "ok":
            _issue_cache_put(key, out)
        return out

    async def _issue_uncached(
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
        # ★이 경로는 **무과금**(사용자가 올린 파일)이라 재사용 캐시를 태우지 않는다.
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

        # ★상류가 말한 실패 사유를 모은다(2026-08-12 라이브 진단으로 추가).
        #   종전에는 각 프로바이더의 실패가 `logger.warning` 으로만 남고 **응답에는 실리지
        #   않아**, 최종적으로 "API 미설정 또는 장애 발생" 한 문장으로 뭉개졌다.
        #   실제 상류 응답은 하이픈의 `[C0000-002] 입력하신 검색조건에 대한 결과가 없습니다`
        #   였는데, 사용자는 **시스템 장애로 오인**하고 진짜 단서(주소·검색 결과)를 잃었다.
        #   원인을 아는 쪽(상류)의 말을 사용자에게 그대로 전달한다.
        attempts: list[dict[str, Any]] = []

        # 1순위: 하이픈 (Hyphen)
        if (p == "hyphen" or not p) and hyphen_ready():
            probe = await probe_api_access()
            # ★"권한 없음(forbidden)"과 "점검 자체를 못 했다(unreachable)"를 **구분한다**.
            #   종전엔 `access == "ok"` 만 통과시켜, 권한점검의 **일시 오류 하나로 주 프로바이더를
            #   통째로 건너뛰고** 2순위(Tilko)로 갔다 — 점검이 주 경로 앞의 단일 실패점이 된 셈이다.
            #   점검을 못 했다면 본 호출을 **시도해 보는 것**이 옳다: 하이픈이 정말 죽었으면 그
            #   호출이 실패해 그때 폴백하면 되고(호출 1회 손해), 일시 오류였으면 정상 조회된다.
            #   자격증명이 거부된 경우(forbidden)만 시도할 가치가 없으므로 즉시 폴백한다.
            if probe.get("access") != "forbidden":
                if unique_no:
                    h_res = await fetch_realty_registry(unique_no=unique_no)
                elif address:
                    h_res = await fetch_registry_by_address(
                        address=address, realty_type=realty_type, dong=dong, ho=ho
                    )
                else:
                    # ★조기반환도 `attempts` 키를 싣는다 — 응답 계약을 한 모양으로 고정한다.
                    #   정직하게 적어 둔다: 이 지점의 값은 **항상 `[]`** 이고(여기까지
                    #   `attempts.append` 가 한 번도 실행되지 않는다), 현재 이 필드를 읽는
                    #   소비처는 **0곳**이다(프론트·registry_analysis_service 전수 확인).
                    #   향후 소비처를 위한 계약 고정이지, 지금 무엇을 해결하지는 않는다.
                    return {**item, "status": "bad_request",
                            "message": "주소 또는 고유번호가 필요합니다.", "attempts": attempts}

                if h_res.get("status") == "ok":
                    return {**item, **h_res}

                logger.warning("하이픈 등기 조회 실패, 2순위 Tilko 폴백 시도", err=h_res.get("message"))
                # ★사유가 비면 **무엇이라도** 남긴다(라이브 실측 2026-08-24).
                #   프로덕션이 사용자에게 `"hyphen: error"` 만 돌려주고 있었다 —
                #   `status` 도 `message` 도 비어 위 `or "error"` 만 남은 것이다.
                #   그 한 단어로는 **네트워크 차단·벤더 장애·민원캐시(선불) 잔액 소진·자격 문제**를
                #   전혀 가를 수 없다. 등기 발급은 `/in0004000948`(민원캐시 **차감**)이라
                #   *"수십 건 성공 후 갑자기 중단"* 이면 잔액 소진이 유력한데, 사유를 버리면
                #   그 확인조차 못 한다.
                #   벤더가 준 코드(errCd)·원문(raw)이 있으면 그것을 싣고, 아무것도 없으면
                #   **응답에 무엇이 들어 있었는지**라도 남긴다(빈 문자열 금지).
                _hmsg = h_res.get("message") or h_res.get("err_msg") or h_res.get("errMsg")
                _hcode = h_res.get("err_code") or h_res.get("errCd")
                if not _hmsg:
                    _keys = ",".join(sorted(k for k in h_res if k != "raw")) or "(빈 응답)"
                    _hmsg = f"사유 미제공 — 응답 키: {_keys}"
                _hdetail = f"[{_hcode}] {_hmsg}" if _hcode else _hmsg
                # ★잔액 부족은 **사용자가 직접 해결할 수 있는** 유일한 부류다(충전하면 끝).
                #   다른 장애와 뭉개면 복구 가능한 문제가 복구 불가처럼 보인다(2026-08-24 실장애).
                _shortage = is_balance_shortage(_hmsg, _hcode)
                attempts.append({
                    "provider": "hyphen",
                    "status": "balance_shortage" if _shortage else (h_res.get("status") or "error"),
                    "message": (balance_shortage_notice("하이픈", _hdetail)
                                if _shortage else _hdetail),
                })
            else:
                logger.warning("하이픈 자격증명 거부(forbidden), 2순위 Tilko 폴백 시도", msg=probe.get("message"))
                attempts.append({
                    "provider": "hyphen",
                    "status": "forbidden",
                    "message": probe.get("message"),
                })
        elif p in ("", None, "hyphen"):
            attempts.append({
                "provider": "hyphen",
                "status": "not_configured",
                "message": "HYPHEN_HKEY / HYPHEN_USER_ID 미설정",
            })

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
                attempts.append({
                    "provider": "tilko",
                    "status": t_res.get("status") or "error",
                    "message": t_res.get("message"),
                })
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
                    attempts.append({
                        "provider": "tilko",
                        "status": t_res.get("status") or "error",
                        "message": t_res.get("message"),
                    })
                else:
                    # 주소검색 자체가 실패/무결과 — 이 사유가 사용자에게 도달해야 한다.
                    attempts.append({
                        "provider": "tilko",
                        "status": s_res.get("status") or "no_match",
                        "message": s_res.get("message"),
                    })
            else:
                # ★pnu 만 들어온 경로. 종전에는 여기서 **아무 것도 남기지 않아** `attempts` 가
                #   비었고, 최종 판정이 `configured_any=False` → **"API 미설정"** 으로 뒤집혔다.
                #   키는 멀쩡한데 관리자에게 "키를 설정하라" 고 말하는 오진이다.
                attempts.append({
                    "provider": "tilko",
                    "status": "bad_request",
                    "message": "주소 또는 고유번호가 필요합니다(PNU 만으로는 조회할 수 없습니다).",
                })
        else:
            attempts.append({
                "provider": "tilko",
                "status": "not_configured",
                "message": "TILKO_API_KEY 미설정",
            })

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
                logger.warning("커스텀 등기부 API 조회 실패", err=exc_detail(e, limit=120))
                # ★로그에만 남기면 사용자에게 도달하지 않는다 — 이 PR 이 고치려던 결함
                #   그 자체(사유가 응답에 안 실려 "미설정 또는 장애" 로 뭉개짐)가
                #   커스텀 경로에 **그대로 남아 있었다**. 세 프로바이더를 같은 규칙으로 싣는다.
                attempts.append({
                    "provider": "custom",
                    "status": "provider_error",
                    "message": exc_detail(e, limit=200),
                })

        # ★"미설정" 과 "조회 실패" 를 구분한다. 종전에는 둘 다 `not_configured` 로 뭉개
        #   "API 미설정 또는 장애 발생" 이라 답했다 — 실제로는 자격증명이 멀쩡하고 상류가
        #   "검색 결과가 없다" 고 답한 경우까지 시스템 장애로 오인하게 만들었다(라이브 실측).
        #   원인을 아는 쪽의 말을 그대로 싣고, 상태도 실제에 맞춘다.
        configured_any = any(a.get("status") != "not_configured" for a in attempts)
        # ★입력 오류를 "프로바이더 오류" 라 부르지 않는다. 같은 입력(pnu 만)이 hyphen 경로에서는
        #   `bad_request`(위 조기반환)인데 tilko 경로에서는 `provider_error` 로 갈리던 비대칭을
        #   없앤다 — **상류는 호출조차 되지 않았다**. 상태 의미가 오염되면 재시도·알림 로직이
        #   잘못 걸린다.
        only_bad_request = bool(attempts) and all(a.get("status") == "bad_request" for a in attempts)
        detail = " / ".join(
            f"{a['provider']}: {a.get('message') or a.get('status')}"
            for a in attempts
            if a.get("message") or a.get("status")
        )
        if only_bad_request:
            msg = f"등기부를 조회하려면 주소 또는 부동산 고유번호가 필요합니다 — {detail}."
        elif configured_any:
            msg = (
                f"등기부 조회에 실패했습니다 — {detail}. "
                "주소를 확인하거나 '비상 등기부 PDF 직접 업로드' 를 이용하세요."
                if detail
                # ★`detail` 이 빈 경우의 폴백 — 실제로는 도달하기 어렵다(모든 attempt 가
                #   status 를 싣고, detail 은 status 만으로도 채워진다). 변이가 생존하는
                #   이유가 그것이다. 신규 경로가 message·status 를 모두 빠뜨릴 때의 방어.
                else "등기부 조회에 실패했습니다. '비상 등기부 PDF 직접 업로드' 를 이용하세요."
            )
        else:
            msg = (
                "등기부 API(Hyphen/Tilko) 미설정 — 관리자 키 설정이 필요합니다. "
                "'비상 등기부 PDF 직접 업로드' 를 이용하세요."
            )
        return {
            **item,
            # 자격증명이 있는데 조회가 안 된 것은 `provider_error` 다 — `not_configured` 가 아니다.
            # 입력이 모자란 것은 둘 다 아니다 — `bad_request` 로 hyphen 경로와 표기를 맞춘다.
            "status": ("bad_request" if only_bad_request
                       else "not_configured" if not configured_any else "provider_error"),
            "message": msg,
            "attempts": attempts,
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
