"""공종분류 SSOT(Single Source Of Truth) — 표준 대공종(WB) 12체계 + 4체계 브리지.

플랫폼 안에 공종분류가 4중으로 흩어져 있다(정합 SSOT 없음):
  A(numeric)  — standard_quantity_estimator 원시 공종코드 8개("01-콘크리트"~"08-전기설비")
                + unit_price_repository/boq_builder 가 쓰는 6개 단가키 별칭
                ("concrete"~"window" — 위 8개 중 6개와 동일 개념의 다른 표기).
  B(ifc)      — ifc_work_map.IFC_WORK_MAP 의 IFC 공종코드 19개(A01~C01, 하위코드 포함).
  C(master)   — boq_master(실적 공내역서 5공종·414섹션) 의 섹션코드. 파일별로 코드 형식이
                달라(예: 건축·기계·전기는 동일 숫자대역이 겹침) "{파일stem}:{섹션코드}"로
                네임스페이스를 부여한다(예: "architecture:010202").
  D(display)  — 화면 분해(지상/지하/조경/간접) — useProjectContextStore.ts CostData 필드명.

이 모듈은 위 4체계를 표준 대공종(WB, 12종 + 간접비 1종 별도축)에 묶어주는 브리지 SSOT다.
매핑은 전부 실제 코드값(grep으로 전수 수집)에 근거하며, 대응 불가 코드는 "unmapped"로
정직 반환한다(발명 금지 — 억지로 아무 WB에나 끼워 맞추지 않는다).

순수 모듈(무DB·stdlib) — master 체계만 boq_master JSON(로컬 파일, boq_master_registry
경유)을 읽어 지연 캐시한다. 결정론(동일 입력은 항상 동일 출력).
"""

from __future__ import annotations

from typing import Any, Literal

SystemName = Literal["numeric", "ifc", "master", "display"]

# ── 표준 대공종(WB) 12종 + 간접비(별도 축) ──
# 한국 건축공사 실무 관례 대분류. 간접비(WB13)는 직접공사비 12종과 별개 축(총공사비의
# 관리·보험·이윤 등 비직접 항목)이라 따로 표기한다.
WB_CATEGORIES: dict[str, str] = {
    "WB01": "가설공사",
    "WB02": "토공사",
    "WB03": "지정·기초공사",
    "WB04": "골조공사(RC·철골)",
    "WB05": "조적·미장공사",
    "WB06": "방수공사",
    "WB07": "창호·유리공사",
    "WB08": "마감공사(내·외장)",
    "WB09": "지붕공사",
    "WB10": "기계설비공사",
    "WB11": "전기·통신공사",
    "WB12": "부대·조경공사",
    "WB13": "간접비",  # 별도 축 — 직접공사비 12종과 구분
}


# ── A(numeric) 브리지 ──
# standard_quantity_estimator.py 의 원시 work_code(8개, 실코드 grep 확인) +
# unit_price_repository.UNIT_PRICES_2026 / boq_builder._WORKCODE_TO_KEY 가 쓰는
# 단가키 별칭(6개 — 위 8개 중 6개와 동일 개념의 다른 표기, 발명 아님·실코드 grep 확인).
_NUMERIC_BRIDGE: dict[str, str | None] = {
    "01-콘크리트": "WB04",
    "02-철근": "WB04",
    "03-거푸집": "WB04",
    "04-조적": "WB05",
    "05-방수": "WB06",
    "06-창호": "WB07",
    "07-기계설비": "WB10",
    "08-전기설비": "WB11",
    # 단가키 별칭(price_key) — 07/08(기계·전기 일식)은 단가키가 없어 별칭도 없음(정직).
    "concrete": "WB04",
    "rebar": "WB04",
    "formwork": "WB04",
    "masonry": "WB05",
    "waterproof": "WB06",
    "window": "WB07",
}

# ── B(ifc) 브리지 ──
# ifc_work_map.IFC_WORK_MAP 의 전체 work_code(19개, 실코드 grep 확인 — 발명 없음).
_IFC_BRIDGE: dict[str, str | None] = {
    "A01": "WB04",       # 철근콘크리트공사
    "A01-01": "WB04",    # 거푸집
    "A01-02": "WB04",    # 철근
    "A01-03": "WB04",    # 콘크리트
    "A02": "WB03",       # 기초공사
    "A03": "WB05",       # 조적공사
    "A04": "WB06",       # 방수공사
    "A05": "WB07",       # 창호공사
    "A05-01": "WB07",    # 문틀
    "A05-02": "WB07",    # 문짝
    "A05-03": "WB07",    # 창호프레임
    "A05-04": "WB07",    # 유리
    "A06": "WB09",       # 지붕공사
    "A07": "WB08",       # 금속공사(마감재)
    "A08": "WB08",       # 도장공사
    "A09": "WB08",       # 수장공사
    "B01": "WB10",       # 배관공사
    "B02": "WB10",       # 덕트공사
    "C01": "WB11",       # 전기배선공사
}

# ── D(display) 브리지 ──
# useProjectContextStore.ts 의 CostData 필드명(5개, 실코드 grep 확인).
# 지상/지하/직접비는 여러 WB에 걸친 집계값이라 단일 대공종으로 정직하게 매핑할 수
# 없다(unmapped) — 조경·간접비만 단일 WB(WB12/WB13)에 대응한다.
_DISPLAY_BRIDGE: dict[str, str | None] = {
    "abovegroundWon": None,   # 지상 — 여러 WB 집계(단일 대공종 아님)
    "undergroundWon": None,   # 지하 — 상동
    "landscapeWon": "WB12",   # 조경
    "directWon": None,        # 직접비 총계 — WB01~12 전체 합산(단일 대공종 아님)
    "indirectWon": "WB13",    # 간접비(별도 축)
}


# ── C(master) 브리지 — boq_master 실적 5공종·414섹션 ──
# 섹션 코드 자체는 건물동/타입별로 반복(예: 010201~010213 이 "동"마다 되풀이)되므로
# 실제 대공종 판별은 섹션 "이름"의 키워드로 한다(boq_bim_merge._SYNONYMS 와 동일 계열
# 접근 — 키워드는 전부 실제 섹션명에서 관측한 문자열, 발명 아님). 첫 매칭 키워드가
# 우선(순서 중요 — 예: "전기"가 "설비"보다 먼저 검사되어야 "전기설비공사"가 WB11로
# 분류된다). 매칭 키워드가 없는 섹션(예: "골재비"/"운반비"/"기타공사" 같은 원가분류
# 성격 라인, 또는 자재별 세부라인)은 unmapped 로 정직 반환한다(억지 분류 금지).
_MASTER_NAME_RULES: list[tuple[str, str]] = [
    ("PRD", "WB03"), ("P.R.D", "WB03"), ("CIP", "WB03"), ("C.I.P", "WB03"),
    ("숏크리트", "WB03"), ("SGR", "WB03"), ("계측", "WB03"), ("흙막이", "WB03"), ("토류벽", "WB03"),
    ("터파기", "WB02"), ("되메우기", "WB02"), ("잔토운반", "WB02"), ("시토장정지", "WB02"),
    ("유용토운반", "WB02"), ("바닥면고르기", "WB02"), ("토공사", "WB02"), ("크람쉘상차", "WB02"),
    ("철근콘크리트", "WB04"), ("철골", "WB04"),
    ("조적", "WB05"), ("미장", "WB05"),
    ("방수", "WB06"),
    ("창호", "WB07"), ("유리", "WB07"),
    ("돌공사", "WB08"), ("목공사", "WB08"), ("수장공사", "WB08"), ("칠공사", "WB08"),
    ("타일", "WB08"), ("판넬", "WB08"), ("가구공사", "WB08"), ("금속", "WB08"), ("잡철물", "WB08"),
    ("지붕", "WB09"), ("홈통", "WB09"),
    # 전기·통신·소방신호 — "설비"/"배관" 등 기계 키워드보다 먼저 검사(순서 중요).
    ("전기", "WB11"), ("통신", "WB11"), ("배선", "WB11"), ("조명", "WB11"), ("전등", "WB11"),
    ("전열", "WB11"), ("동력", "WB11"), ("수변전", "WB11"), ("접지", "WB11"), ("피뢰", "WB11"),
    ("CCTV", "WB11"), ("CATV", "WB11"), ("방송", "WB11"), ("비상벨", "WB11"), ("유도등", "WB11"),
    ("자탐", "WB11"), ("주차관제", "WB11"), ("홈네트워크", "WB11"), ("태양광", "WB11"),
    ("항공장애등", "WB11"), ("전력", "WB11"), ("이동통신", "WB11"), ("무선통신", "WB11"),
    ("원격검침", "WB11"), ("스노우멜팅", "WB11"), ("인터폰", "WB11"), ("택배", "WB11"), ("소방", "WB11"),
    ("배관", "WB10"), ("덕트", "WB10"), ("닥트", "WB10"), ("설비", "WB10"), ("기구", "WB10"),
    ("펌프", "WB10"), ("소화", "WB10"), ("스프링클러", "WB10"), ("EHP", "WB10"), ("열선", "WB10"),
    ("제어", "WB10"), ("여과조", "WB10"), ("가스", "WB10"), ("장비설치", "WB10"),
    ("가설", "WB01"),
    ("포장", "WB12"), ("경계석", "WB12"), ("식재", "WB12"), ("시설공", "WB12"), ("부대", "WB12"),
    ("맨홀", "WB12"), ("관부설", "WB12"), ("상수", "WB12"), ("오수", "WB12"), ("우수", "WB12"),
    ("배수관", "WB12"), ("밸브", "WB12"), ("관보호공", "WB12"), ("관절단", "WB12"), ("연결관", "WB12"),
    ("제수변실", "WB12"), ("수압시험", "WB12"), ("교통안전", "WB12"), ("대중교통", "WB12"),
    ("험프식", "WB12"), ("관대", "WB12"),
]


def _classify_master_name(name: Any) -> str | None:
    """boq_master 섹션명 → WB코드(키워드 첫 매칭). 매칭 없으면 None(정직 unmapped)."""
    normalized = str(name or "").replace(" ", "")
    for keyword, wb_code in _MASTER_NAME_RULES:
        if keyword in normalized:
            return wb_code
    return None


_master_cache: dict[str, str | None] | None = None


def _master_bridge() -> dict[str, str | None]:
    """boq_master 5공종 전체 섹션코드 → WB코드(지연 빌드 + 모듈 캐시).

    키 형식 "{파일stem}:{섹션코드}"(예: "architecture:010202") — 건축·기계·전기 파일이
    같은 숫자 코드대역을 재사용하므로 파일명으로 네임스페이스를 부여해 충돌을 막는다.
    """
    global _master_cache
    if _master_cache is not None:
        return _master_cache

    out: dict[str, str | None] = {}
    try:
        from app.services.cost.boq_master_registry import get_sections, list_disciplines

        for row in list_disciplines():
            discipline = row.get("discipline")
            file_name = str(row.get("file") or "")
            stem = file_name.removesuffix(".json") or str(discipline)
            sections = get_sections(discipline).get("sections") or []
            for sec in sections:
                code = sec.get("code")
                if not code:
                    continue
                out[f"{stem}:{code}"] = _classify_master_name(sec.get("name"))
    except Exception:  # noqa: BLE001 — boq_master 로드 실패해도 SSOT 자체는 죽지 않음(빈 브리지)
        out = {}
    _master_cache = out
    return out


def clear_master_cache() -> None:
    """master 브리지 캐시 초기화(테스트/리로드용) — 동작 결과에는 영향 없음(결정론)."""
    global _master_cache
    _master_cache = None


def _bridge_table(system: SystemName) -> dict[str, str | None]:
    if system == "numeric":
        return _NUMERIC_BRIDGE
    if system == "ifc":
        return _IFC_BRIDGE
    if system == "master":
        return _master_bridge()
    if system == "display":
        return _DISPLAY_BRIDGE
    raise ValueError(f"알 수 없는 체계: {system!r} (numeric/ifc/master/display 중 하나여야 함)")


def resolve(code: str, system: SystemName) -> dict[str, Any]:
    """4체계(numeric/ifc/master/display) 코드 하나를 표준 대공종(WB)으로 변환한다.

    대응하는 WB가 없으면(체계 밖 코드거나, 실존 코드지만 여러 WB에 걸쳐 단일 대공종으로
    표기할 수 없는 경우) unmapped=True 로 정직 반환한다(억지 매핑 금지).
    """
    table = _bridge_table(system)
    wb_code = table.get(code)
    if wb_code is None:
        return {"wb_code": None, "wb_name": None, "unmapped": True}
    return {"wb_code": wb_code, "wb_name": WB_CATEGORIES.get(wb_code), "unmapped": False}


def codes_for(wb_code: str, system: SystemName) -> list[str]:
    """표준 대공종(WB) → 해당 체계의 코드 목록(역방향 조회, 결정론 정렬)."""
    table = _bridge_table(system)
    return sorted(code for code, wb in table.items() if wb == wb_code)
