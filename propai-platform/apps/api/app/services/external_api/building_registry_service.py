"""건축물대장 정보 조회 서비스.

공공데이터포털 건축물대장정보 서비스 (건축HUB) 연동.
엔드포인트: http://apis.data.go.kr/1613000/BldRgstHubService/

PNU 또는 시군구코드+법정동코드 기반으로 건축물 현황을 조회.
"""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService"


class BuildingRegistryService:
    """건축물대장 조회 서비스."""

    # 마지막 조회 상태(no_key/unauthorized/error/no_data/ok). 상위 서비스가 "나대지 단정" 판단에 사용.
    last_status: str = "unknown"

    async def get_building_info(
        self, sigungu_cd: str, bjdong_cd: str, bun: str = "", ji: str = "",
    ) -> dict[str, Any] | None:
        """시군구코드+법정동코드로 건축물대장 기본개요를 조회.

        Args:
            sigungu_cd: 시군구코드 (5자리, 예: 11680=강남구)
            bjdong_cd: 법정동코드 (5자리, 예: 10300=역삼동)
            bun: 본번 (4자리, 선택)
            ji: 부번 (4자리, 선택)
        """
        # last_status: 마지막 조회 결과 상태(상위에서 "나대지 단정" 여부 판단에 사용)
        #   no_key=키없음 / unauthorized=미승인(401·Unauthorized) / error=호출오류
        #   no_data=조회성공·무건축물(=나대지 추정) / ok=건축물 있음
        if not settings.MOLIT_API_KEY:
            self.last_status = "no_key"
            return None

        params: dict[str, str] = {
            "serviceKey": settings.MOLIT_API_KEY,
            "sigunguCd": sigungu_cd,
            "bjdongCd": bjdong_cd,
            "numOfRows": "1",
            "pageNo": "1",
            "_type": "json",
        }
        if bun:
            params["bun"] = bun.zfill(4)
        if ji:
            params["ji"] = ji.zfill(4)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{BASE_URL}/getBrBasisOulnInfo", params=params)
                # 401/403 또는 "Unauthorized" 본문 → 미승인(활용신청 필요)
                if resp.status_code in (401, 403) or resp.text.strip().lower().startswith("unauthorized"):
                    self.last_status = "unauthorized"
                    logger.warning("건축물대장 API 미승인(활용신청 필요): %s", resp.status_code)
                    return None
                resp.raise_for_status()
                data = resp.json()

            header = data.get("response", {}).get("header", {})
            if header.get("resultCode") != "00":
                # 인증 관련 결과코드(예: 30 서비스키 오류) → 미승인으로 분류
                rc = str(header.get("resultCode", ""))
                self.last_status = "unauthorized" if rc in ("30", "31", "20", "22") else "error"
                logger.warning("건축물대장 조회 실패: %s", header.get("resultMsg"))
                return None

            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            if not items:
                self.last_status = "no_data"  # 조회 성공·건축물 없음 → 나대지 추정 가능
                return None

            self.last_status = "ok"
            item = items[0] if isinstance(items, list) else items
            return {
                "building_name": item.get("bldNm", ""),
                "main_purpose": item.get("mainPurpsCdNm", ""),
                "total_area_sqm": float(item.get("totArea", 0) or 0),
                "building_area_sqm": float(item.get("archArea", 0) or 0),
                "bcr_pct": float(item.get("bcRat", 0) or 0),
                "far_pct": float(item.get("vlRat", 0) or 0),
                "ground_floors": int(item.get("grndFlrCnt", 0) or 0),
                "underground_floors": int(item.get("ugrndFlrCnt", 0) or 0),
                "structure": item.get("strctCdNm", ""),
                "use_approval_date": item.get("useAprDay", ""),
                "household_count": int(item.get("hhldCnt", 0) or 0),  # 세대수
                "family_count": int(item.get("fmlyCnt", 0) or 0),  # 가구수
                "ho_count": int(item.get("hoCnt", 0) or 0),  # 호수
                "new_old_code": item.get("newOldRegstrGbCdNm", ""),
                "address": item.get("platPlc", ""),
                "road_address": item.get("newPlatPlc", ""),
            }
        except Exception as e:
            self.last_status = "error"
            logger.warning("건축물대장 API 오류: %s", str(e))
            return None

    async def get_building_by_pnu(self, pnu: str) -> dict[str, Any] | None:
        """PNU(19자리)에서 시군구코드/법정동코드/본번/부번을 추출하여 조회."""
        if len(pnu) < 19:
            return None

        sigungu_cd = pnu[:5]
        bjdong_cd = pnu[5:10]
        # PNU 구조: 시군구(5) + 법정동(5) + 대지구분(1) + 본번(4) + 부번(4)
        bun = pnu[11:15]
        ji = pnu[15:19]

        return await self.get_building_info(sigungu_cd, bjdong_cd, bun, ji)

    async def get_title_by_pnu(self, pnu: str) -> dict[str, Any] | None:
        """PNU 기반 표제부(getBrTitleInfo) 조회 — 사용승인일·구조·세대수가 충실.

        총괄표제부(getBrBasisOulnInfo)가 사용승인일을 비워두는 경우가 많아,
        노후도·세대수 산정에는 표제부를 사용한다.

        멸실여부·미준공(공사중) 여부도 표제부 상태 필드로 best-effort 판정한다.
        키 미설정/호출실패/무자료 시 None(가짜데이터 생성 금지).
        """
        if len(pnu) < 19 or not settings.MOLIT_API_KEY:
            return None
        params = {
            "serviceKey": settings.MOLIT_API_KEY,
            "sigunguCd": pnu[:5], "bjdongCd": pnu[5:10],
            "bun": pnu[11:15], "ji": pnu[15:19],
            "numOfRows": "10", "pageNo": "1", "_type": "json",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{BASE_URL}/getBrTitleInfo", params=params)
                resp.raise_for_status()
                items = (resp.json().get("response", {}).get("body", {})
                         .get("items", {}) or {}).get("item")
            return self._parse_title_items(items)
        except Exception as e:  # noqa: BLE001
            logger.warning("표제부 조회 실패: %s (%s)", pnu, str(e))
            return None

    async def _list_by_bjdong(
        self, endpoint: str, sigungu_cd: str, bjdong_cd: str, *, max_rows: int = 300, max_pages: int = 3,
    ) -> list[dict[str, Any]]:
        """법정동 단위 건축물대장 벌크 조회 공용 — getBrTitleInfo(표제부)·getBrRecapTitleInfo(총괄표제부).

        반환 record 키 = get_building_*와 동일 계약(main_purpose·bcr_pct·far_pct·ground_floors·
        total_area_sqm·address) → aggregate_mass_templates가 그대로 소비. 키 미설정/무자료/오류 → [](가짜 생성 금지).
        """
        if not settings.MOLIT_API_KEY:
            self.last_status = "no_key"
            return []
        base = {
            "serviceKey": settings.MOLIT_API_KEY, "sigunguCd": sigungu_cd, "bjdongCd": bjdong_cd,
            "numOfRows": str(max_rows), "_type": "json",
        }
        out: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                for page in range(1, max_pages + 1):
                    resp = await client.get(f"{BASE_URL}/{endpoint}", params={**base, "pageNo": str(page)})
                    resp.raise_for_status()
                    body = resp.json().get("response", {}).get("body", {}) or {}
                    items = (body.get("items", {}) or {}).get("item")
                    if not items:
                        break
                    rows = items if isinstance(items, list) else [items]
                    for it in rows:
                        out.append({
                            "main_purpose": it.get("mainPurpsCdNm", "") or "",
                            "bcr_pct": float(it.get("bcRat", 0) or 0),
                            "far_pct": float(it.get("vlRat", 0) or 0),
                            "ground_floors": int(float(it.get("grndFlrCnt", 0) or 0)),
                            "total_area_sqm": float(it.get("totArea", 0) or 0),
                            "address": it.get("platPlc", "") or "",
                        })
                    try:
                        total = int(body.get("totalCount") or 0)
                    except (TypeError, ValueError):
                        total = 0
                    if len(out) >= total or len(rows) < max_rows:
                        break  # 다 모았거나 마지막 페이지
            self.last_status = "ok" if out else "no_data"
        except Exception as e:  # noqa: BLE001
            self.last_status = "error"
            logger.warning("대장 벌크 조회 실패 %s %s-%s: %s", endpoint, sigungu_cd, bjdong_cd, str(e)[:120])
        return out

    async def list_titles_by_bjdong(
        self, sigungu_cd: str, bjdong_cd: str, *, max_rows: int = 300, max_pages: int = 3,
    ) -> list[dict[str, Any]]:
        """법정동 단위 표제부(getBrTitleInfo) 벌크 — 동별(개별 건물). 신도시 매스 백본 시드 기본 소스.

        ★공동주택(아파트)은 표제부가 동별이라 건폐/용적(bcRat/vlRat)이 비어있는 경우가 많다 →
          총괄표제부(list_recap_titles_by_bjdong)로 건폐/용적을 보강한다.
        """
        return await self._list_by_bjdong(
            "getBrTitleInfo", sigungu_cd, bjdong_cd, max_rows=max_rows, max_pages=max_pages,
        )

    async def list_recap_titles_by_bjdong(
        self, sigungu_cd: str, bjdong_cd: str, *, max_rows: int = 300, max_pages: int = 3,
    ) -> list[dict[str, Any]]:
        """법정동 단위 총괄표제부(getBrRecapTitleInfo) 벌크 — 집합건물 '단지' 단위.

        공동주택 등 집합건물의 건폐/용적(bcRat/vlRat)이 단지 기준으로 충실해, 표제부가 비운 건폐/용적을
        보강하는 용도. ★단, total_area_sqm은 단지 총연면적이라 동별 표제부 면적과 섞으면 안 된다(보강은
        건폐/용적만; 면적·층수는 표제부 기준 유지 — collect_region 병합 규칙 참조).
        """
        return await self._list_by_bjdong(
            "getBrRecapTitleInfo", sigungu_cd, bjdong_cd, max_rows=max_rows, max_pages=max_pages,
        )

    async def get_exclusive_units_by_pnu(
        self, pnu: str, page_size: int = 1000, max_pages: int = 30,
    ) -> list[dict[str, Any]] | None:
        """PNU 기반 집합건축물 전유공용면적(getBrExposPubuseAreaInfo) → 호별 전유면적 집계.

        공동주택/집합상가는 한 단지에 전유+공용 행이 수만 건(예: 1,584세대=10,494행)이라
        ★반드시 totalCount까지 페이지네이션해야 모든 세대를 빠짐없이 집계한다(단일 호출 시
        앞쪽 공용 행에 밀려 일부 세대만 잡혀 대지지분이 과대 배분되는 버그가 생긴다).
        반환: [{dong, ho, exclusive_area_sqm, purpose}] (전유부만, 호 단위 합산).
        키 미설정/실패/무자료 → None(가짜 생성 금지).
        """
        if len(pnu) < 19 or not settings.MOLIT_API_KEY:
            return None

        def _f(x: dict, k: str) -> float:
            try:
                return float(x.get(k, 0) or 0)
            except (TypeError, ValueError):
                return 0.0

        base_params = {
            "serviceKey": settings.MOLIT_API_KEY,
            "sigunguCd": pnu[:5], "bjdongCd": pnu[5:10],
            "bun": pnu[11:15], "ji": pnu[15:19],
            "numOfRows": str(page_size), "_type": "json",
        }
        agg: dict[tuple, dict[str, Any]] = {}
        collected = 0
        total_count = None
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                for page in range(1, max_pages + 1):
                    resp = await client.get(
                        f"{BASE_URL}/getBrExposPubuseAreaInfo",
                        params={**base_params, "pageNo": str(page)},
                    )
                    resp.raise_for_status()
                    body = resp.json().get("response", {}).get("body", {}) or {}
                    if total_count is None:
                        try:
                            total_count = int(body.get("totalCount") or 0)
                        except (TypeError, ValueError):
                            total_count = 0
                    items = (body.get("items", {}) or {}).get("item")
                    if not items:
                        break
                    rows = items if isinstance(items, list) else [items]
                    collected += len(rows)
                    for r in rows:
                        gb = str(r.get("exposPubuseGbCdNm", "") or "")
                        if "전유" not in gb:
                            continue  # 공용부 제외(대지지분은 전유 기준)
                        dong = str(r.get("dongNm", "") or "").strip()
                        ho = str(r.get("hoNm", "") or "").strip()
                        key = (dong, ho)
                        cur = agg.setdefault(key, {
                            "dong": dong, "ho": ho, "exclusive_area_sqm": 0.0,
                            "purpose": str(r.get("mainPurpsCdNm", "") or ""),
                        })
                        cur["exclusive_area_sqm"] += _f(r, "area")
                    # totalCount까지 다 모았으면 종료(불필요한 호출 방지).
                    if total_count and collected >= total_count:
                        break
                else:
                    # max_pages 소진(초대형 단지) — 일부 누락 가능. count 교차검증이 비신뢰로 표기.
                    logger.warning("전유공용면적 페이지 상한 도달(%s rows≥%s, total=%s) — 일부 누락 가능: %s",
                                   collected, page_size * max_pages, total_count, pnu)
        except Exception as e:  # noqa: BLE001
            logger.warning("전유공용면적 조회 실패: %s (%s)", pnu, str(e))
            # 부분 수집이라도 있으면 활용(교차검증이 신뢰도 판단). 없으면 None.
            if not agg:
                return None

        units = [
            {**u, "exclusive_area_sqm": round(u["exclusive_area_sqm"], 4)}
            for u in agg.values() if u["exclusive_area_sqm"] > 0
        ]
        units.sort(key=lambda u: (u["dong"], u["ho"]))
        return units or None

    @staticmethod
    def _parse_title_items(items: Any) -> dict[str, Any] | None:
        """getBrTitleInfo item(s)를 표제부 상세 dict로 파싱(순수함수, 외부호출 없음).

        멸실여부·미준공여부를 확실히 제공되는 필드만으로 best-effort 판정한다.
        - 멸실: regstrKindCdNm/regstrGbCdNm 등에 '멸실' 포함, 또는 별도 상태표기.
          건축HUB 표제부는 멸실 전용 불리언을 제공하지 않으므로 텍스트 기반 추정.
        - 미준공: 사용승인일(useAprDay) 공란 = 사용승인 미완료(공사중/미준공) 추정.
        무자료(items 없음) → None.
        """
        if not items:
            return None
        rows = items if isinstance(items, list) else [items]

        def _f(x: dict, k: str) -> float:
            try:
                return float(x.get(k, 0) or 0)
            except (TypeError, ValueError):
                return 0.0

        # 주된 동(연면적 최대) 선택
        main = max(rows, key=lambda x: _f(x, "totArea"))
        use_approval_date = str(main.get("useAprDay", "") or "").strip()

        # 멸실 best-effort: 상태/대장종류 텍스트에 '멸실' 포함 여부
        status_text = " ".join(
            str(main.get(k, "") or "")
            for k in ("regstrKindCdNm", "regstrGbCdNm", "bldNm", "etcPurps")
        )
        is_demolished = "멸실" in status_text
        # 멸실일: 건축HUB 표제부에 전용 필드가 없어 best-effort(불명 시 빈값)
        demolition_date = str(main.get("crtnDay", "") or "").strip() if is_demolished else ""

        # 미준공 best-effort: 사용승인일 공란 → 사용승인 미완료(공사중/미준공) 추정
        is_uncompleted = (not use_approval_date) and (not is_demolished)

        return {
            "building_name": main.get("bldNm", ""),
            "use_approval_date": use_approval_date,
            "structure": main.get("strctCdNm", ""),
            "main_purpose": main.get("mainPurpsCdNm", ""),
            "ground_floors": int(_f(main, "grndFlrCnt")),
            "underground_floors": int(_f(main, "ugrndFlrCnt")),
            "total_area_sqm": _f(main, "totArea"),
            "plat_area_sqm": _f(main, "platArea"),   # 대지면적(공동주택 대지지분 산정 기준)
            "household_count": int(_f(main, "hhldCnt")),
            "ho_count": int(_f(main, "hoCnt")),
            "family_count": int(_f(main, "fmlyCnt")),
            "dong_count": len(rows),
            # 멸실(best-effort, 표제부 텍스트 기반 추정 — 확인필요)
            "is_demolished": is_demolished,
            "demolition_date": demolition_date,
            "demolition_basis": (
                "표제부 상태텍스트 '멸실' 감지(추정·확인필요)"
                if is_demolished else ""
            ),
            # 미준공(best-effort, 사용승인일 부재 기반 추정 — 확인필요)
            "is_uncompleted": is_uncompleted,
            "uncompleted_basis": (
                "표제부 사용승인일 부재 → 미준공(공사중) 추정·확인필요"
                if is_uncompleted else ""
            ),
        }
