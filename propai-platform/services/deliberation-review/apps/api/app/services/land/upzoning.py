"""종상향(용도지역 상향) 시나리오 — 재건축/재개발·지구단위계획 시 용적률 상향 가능성.

정적 잔여용량(현행 고정)의 한계를 보완: 종상향 위계(주거→상업)를 따라 단계별 용적률 상한과
추가 개발용량을 시나리오로 제시. 실제 가능성은 토지이용계획 신호(촉진/제약)로 별도 판별
(upzoning_signals). 위계 밖(녹지/공업/관리)은 None. 결정론(고정 위계+테이블).
"""
from __future__ import annotations

from datetime import date

from app.contracts.rationale import Rationale, RationaleInput
from app.services.explain.legal_refs import refs
from app.services.land.zone_limits import ZONE_LIMITS, lookup_zone_limit

# 종상향 위계(용적률 오름차순). 주거→상업 일반 경로. 실제 상향은 도시계획 절차·공공기여 수반.
UPZONING_LADDER = [
    "제1종전용주거지역", "제2종전용주거지역",
    "제1종일반주거지역", "제2종일반주거지역", "제3종일반주거지역",
    "준주거지역", "근린상업지역", "일반상업지역", "중심상업지역",
]

# 종상향 촉진/제약 신호(토지이용계획 prposAreaDstrcCodeNm 부분매칭). workflow(도시정비법) 검증.
_PROMOTE = ["지구단위계획", "정비구역", "재정비촉진", "재개발", "재건축", "역세권", "입안",
            "도시정비", "정비예정", "공공주택", "역세권활성화", "개발진흥", "입지규제최소"]
_CONSTRAIN = ["고도지구", "최고고도", "경관지구", "자연경관", "중점경관", "문화재", "역사문화환경",
              "보존", "비행안전", "대공방어", "개발제한구역", "보전", "군사", "검토구역"]
# 높이 봉인 — 용적률 상한 상향해도 높이규제로 실현 불가(상한 상향 ≠ 가용 연면적, workflow 핵심).
_HEIGHT_SEAL = ["고도지구", "최고고도", "고도제한", "경관지구", "자연경관", "중점경관", "비행안전", "대공방어"]
# 개발 자체 봉쇄 — 종상향 논의 대상 제외.
_HARD_BLOCK = ["문화재", "개발제한구역", "그린벨트", "생태경관보전", "보전산지", "군사기지", "통제보호"]


def upzoning_scenarios(current_zone: str | None, area: float | None,
                       existing_floor_area: float | None = 0.0, max_steps: int = 2) -> dict | None:
    """현 용도지역 → 종상향 1~max_steps 단계별 {용적률 상한, 최대 연면적, 추가 가능}. 위계 밖/결손 None."""
    cur = lookup_zone_limit(current_zone)
    if cur is None or not area or area <= 0:
        return None
    matched = cur["zone_matched"]
    if matched not in UPZONING_LADDER:
        return None  # 녹지/공업/관리 등 — 별도 경로
    idx = UPZONING_LADDER.index(matched)
    existing = existing_floor_area or 0.0
    current_max = cur["far_limit_pct"] / 100 * area
    scenarios = []
    for step in range(0, max_steps + 1):
        ti = idx + step
        if ti >= len(UPZONING_LADDER):
            break
        tz = UPZONING_LADDER[ti]
        far = ZONE_LIMITS[tz][0]
        max_total = round(far / 100 * area, 1)
        scenarios.append({
            "step": step,
            "target_zone": tz,
            "far_limit_pct": far,
            "max_total_floor_area": max_total,
            "additional_vs_existing": round(max_total - existing, 1),
            "additional_vs_current_zoning": round(max_total - current_max, 1),
        })
    return {"current_zone": matched, "lot_area": round(area, 1), "scenarios": scenarios}


# 지자체 도시계획조례 용적률(%) — 시행령 §85 범위 내 확정값(workflow 검증). PNU 앞2자리=시도코드.
# 시행령 상한과 다른 핵심값만(없으면 시행령 상한 폴백). 서울=과밀억제로 상업 대폭 하향.
ORDINANCE_FAR: dict[str, dict[str, int]] = {
    "11": {  # 서울특별시
        "제1종전용주거지역": 100, "제2종전용주거지역": 120, "제1종일반주거지역": 150,
        "제2종일반주거지역": 200, "제3종일반주거지역": 250, "준주거지역": 400,
        "근린상업지역": 600, "일반상업지역": 800, "중심상업지역": 1000, "유통상업지역": 600,
        "전용공업지역": 200, "일반공업지역": 200, "준공업지역": 400,
        "보전녹지지역": 50, "생산녹지지역": 50, "자연녹지지역": 50,
    },
}

# 종상향 다중경로(workflow: 도시정비법·서울 조례·운영기준 검증). ladder_jump=위계 상향 단계.
# ref_id=services/explain/legal_refs 사전 키(설명가능성 legal_basis 해소용).
PATHWAYS: list[dict] = [
    {"id": "지구단위계획", "ladder_jump": 1, "contribution_rate": 0.15, "ref_id": "국토계획법§52",
     "public_contribution": "기부채납 면적 비례 인센티브",
     "requirement": "15m↑도로/동일용도지역 경계 접함, 지구단위계획구역 지정", "basis": "국토계획법 §52, 지자체 수립기준"},
    {"id": "정비사업(재건축/재개발)", "ladder_jump": 1, "contribution_rate": 0.10, "ref_id": "도시정비법",
     "public_contribution": "증가 용적률 1/2(서울 1단계 10%)",
     "requirement": "정비구역 지정, 노후·불량 밀집", "basis": "도시정비법, 서울 도시계획조례"},
    {"id": "역세권 활성화", "ladder_jump": 4, "contribution_rate": 0.50, "ref_id": "서울역세권활성화조례",
     "public_contribution": "증가 용적률 50% 공공기여",
     "requirement": "역 승강장 직각 가목 350m/나목 250m, 중심지 위계", "basis": "서울 역세권활성화 조례/운영기준 1-3-1"},
    {"id": "역세권 청년안심주택", "ladder_jump": 2, "contribution_rate": 0.50, "ref_id": "서울청년안심주택조례§2",
     "public_contribution": "증가 용적률 50%↑ 공공주택",
     "requirement": "역 승강장 경계 250m(예외 350m) 준주거/상업", "basis": "서울 청년안심주택 조례 §2"},
    {"id": "도시계획변경 사전협상", "ladder_jump": 2, "contribution_rate": 0.60, "ref_id": "서울사전협상조례",
     "public_contribution": "증가 용적률 60% 토지가치",
     "requirement": "5천㎡↑ 유휴부지/이전적지", "basis": "국토계획법 §51~53, 서울 사전협상조례"},
    {"id": "입지규제최소구역", "ladder_jump": None, "contribution_rate": None, "ref_id": "입지규제최소구역지침",
     "public_contribution": "기반시설 확보 의무",
     "requirement": "거점/역사 1km, 노후밀집", "basis": "국토계획법 입지규제최소구역지침"},
]

# 한시적 용적률 완화 — 검증된 1차출처(docs/VERIFIED_FACTS_zoning.md). 적용일(as_of)이 유효기간 내 +
# 대상 시도/용도지역일 때 '조건부 가능'으로 표면화(단정 금지 — 소규모건축물 등 조건 충족 전제).
_TEMP_RELAX: list[dict] = [
    {"sido": "11", "from": "2025-05-19", "to": "2028-05-18", "ref_id": "서울한시완화2025",
     "zones": {"제2종일반주거지역": 250, "제3종일반주거지역": 300},
     "condition": "소규모건축물(건축허가·자율주택/소규모재건축·재개발, 전용 85㎡ 이하) 한정 — 미충족 시 상시값"},
]


def ordinance_far(pnu: str | None, zone_name: str | None, as_of: date | None = None) -> dict | None:
    """시도 조례 용적률(우선) 또는 시행령 상한. {far_pct, source, ref_id, temporary_relaxation?}. 결손 None.

    as_of(적용일) 제공 + 한시완화 유효기간/대상 매칭 시 temporary_relaxation(조건부 가능)을 부가(단정 금지).
    """
    sido = (pnu or "")[:2]
    base: dict | None = None
    table = ORDINANCE_FAR.get(sido)
    if table and zone_name:
        for k, v in table.items():
            if k in zone_name or zone_name in k:
                ref = "서울도시계획조례§55" if sido == "11" else None
                base = {"far_pct": v, "source": f"{sido} 조례", "ref_id": ref}
                break
    if base is None:
        z = lookup_zone_limit(zone_name)
        if z is None:
            return None
        base = {"far_pct": z["far_limit_pct"], "source": "시행령 상한", "ref_id": "국토계획법시행령§85"}
    # 한시완화 — 조건부 가능(단정 금지). as_of 유효기간 + 대상 용도지역 매칭 + 상시값보다 클 때만.
    if as_of and zone_name:
        for t in _TEMP_RELAX:
            if t["sido"] != sido or not (date.fromisoformat(t["from"]) <= as_of <= date.fromisoformat(t["to"])):
                continue
            for zk, zv in t["zones"].items():
                if (zk in zone_name or zone_name in zk) and zv > base["far_pct"]:
                    base["temporary_relaxation"] = {
                        "far_pct": zv, "until": t["to"], "ref_id": t["ref_id"], "condition": t["condition"]}
                    break
    return base


def multipath_scenarios(current_zone: str | None, area: float | None, signals: dict,
                        pnu: str | None = None, max_jump: int = 4,
                        as_of: date | None = None) -> dict | None:
    """종상향 다중경로별 목표 용도지역·조례 용적률·최대 연면적·공공기여 + 경로별 설명(rationale). 결손 None.

    as_of(적용일) 제공 시 현행/목표 용적률에 한시완화(조건부)를 반영. 위계 밖/결손 None.
    """
    base = lookup_zone_limit(current_zone)
    if base is None or not area or base["zone_matched"] not in UPZONING_LADDER:
        return None
    idx = UPZONING_LADDER.index(base["zone_matched"])
    height_sealed = signals.get("height_sealed")
    # 현행 용도지역 조례 용적률 → 현행 최대 연면적(증가분 기준).
    cur_of = ordinance_far(pnu, base["zone_matched"], as_of)
    current_far = cur_of["far_pct"] if cur_of else base["far_limit_pct"]
    cur_src = cur_of["source"] if cur_of else "시행령 상한"
    current_max = current_far / 100 * area
    paths = []
    for p in PATHWAYS:
        jump = p["ladder_jump"]
        if jump is None:  # 입지규제최소구역 = 구역계획 직접(step 모델 아님)
            paths.append({
                "pathway": p["id"], "type": "구역계획",
                "public_contribution": p["public_contribution"],
                "requirement": p["requirement"], "basis": p["basis"],
                "note": "용도지역 규제 대체 — 구역계획으로 용적률 별도 설정",
                "rationale": Rationale(
                    summary=f"{p['id']}: 용도지역 규제를 구역계획으로 대체 — 용적률·용도 별도 설정(위계 점프 모델 아님)",
                    legal_basis=refs(p["ref_id"]),
                    caveats=[f"적격요건: {p['requirement']}", "구역계획 수립·지정 절차·심의 필요"],
                ).model_dump(),
            })
            continue
        ti = min(idx + min(jump, max_jump), len(UPZONING_LADDER) - 1)
        target = UPZONING_LADDER[ti]
        of = ordinance_far(pnu, target, as_of)
        far = of["far_pct"] if of else ZONE_LIMITS[target][0]
        far_src = of["source"] if of else "시행령"
        bcr = ZONE_LIMITS[target][1]  # 종변경 시 건폐율 상한도 교체
        max_total = round(far / 100 * area, 1)
        # 형질변경(종변경) 재계산: 증가 용적률·공공기여 차감·순증 연면적.
        far_increase = round(max_total - current_max, 1)
        rate = p["contribution_rate"]
        contrib_area = round(max(far_increase, 0.0) * rate, 1) if rate else None
        net_gain = round(far_increase - (contrib_area or 0.0), 1)
        caveats = ["종상향 실현은 도시계획 절차·심의·공공기여 수반(자동 아님)",
                   f"적격요건: {p['requirement']}"]
        if height_sealed:
            caveats.append("⚠️ 고도/경관 제한(height_sealed) — 용적률 상한↑해도 높이규제로 가용 연면적 제약")
        if of and of.get("temporary_relaxation"):
            tr = of["temporary_relaxation"]
            caveats.append(f"목표 용도지역 한시완화 가능(조건부): {tr['far_pct']}%({tr['until']}까지) — {tr['condition']}")
        basis_ids = [p["ref_id"], of["ref_id"] if of and of.get("ref_id") else "국토계획법시행령§85"]
        rationale = Rationale(
            summary=(f"{p['id']}로 {target} {far}%({far_src})까지 → 순증 {net_gain}㎡"
                     f"(증가 {far_increase}㎡ − 공공기여 {contrib_area or 0.0}㎡)"),
            formula="증가연면적=목표상한연면적−현행상한연면적; 공공기여=max(증가,0)×기여율; 순증=증가−공공기여",
            inputs=[
                RationaleInput(name="대지면적(㎡)", value=round(area, 1)),
                RationaleInput(name="현행 용적률상한(%)", value=round(current_far, 1), source=cur_src),
                RationaleInput(name="목표 용적률상한(%)", value=far, source=far_src),
                RationaleInput(name="공공기여율", value=rate),
            ],
            legal_basis=refs(*basis_ids),
            caveats=caveats,
        )
        paths.append({
            "pathway": p["id"], "type": "종상향",
            "target_zone": target, "far_pct": far, "far_source": far_src,
            "target_bcr_pct": bcr,
            "max_total_floor_area": max_total,
            "far_increase_area": far_increase,           # 종상향 증가 연면적
            "contribution_rate": rate,
            "public_contribution_area": contrib_area,    # 공공기여 의무 연면적
            "net_floor_area_gain": net_gain,             # 공공기여 차감 후 순증
            "public_contribution": p["public_contribution"],
            "requirement": p["requirement"], "basis": p["basis"],
            "rationale": rationale.model_dump(),
        })
    return {
        "current_zone": base["zone_matched"], "lot_area": round(area, 1),
        "current_far_pct": round(current_far, 1), "current_far_source": cur_src,
        "likelihood": signals.get("likelihood"), "height_sealed": height_sealed,
        "pathways": paths,
        "note": "다중경로별 최대 용적률(조례 우선) — 실현은 height_sealed/공공기여/심의·시점(조례 개정) 검증 필요",
    }


def upzoning_signals(use_zones_all: list[str] | None) -> dict:
    """토지이용계획 용도지역지구 → 종상향 촉진/제약 분류 + 높이봉인/봉쇄 게이팅. 가능성 판별.

    likelihood: BLOCKED(개발봉쇄) > LOW(높이봉인·제약) > MIXED(촉진+제약) > HIGH(촉진) > UNKNOWN.
    height_sealed=True면 용적률 상향해도 높이규제로 실현 불가(상한 상향 ≠ 가용 연면적) — 별도 표면화.
    """
    zones = use_zones_all or []
    promote = sorted({z for z in zones if any(k in z for k in _PROMOTE)})
    constrain = sorted({z for z in zones if any(k in z for k in _CONSTRAIN)})
    height_sealed = sorted({z for z in zones if any(k in z for k in _HEIGHT_SEAL)})
    hard_block = sorted({z for z in zones if any(k in z for k in _HARD_BLOCK)})

    if hard_block:
        likelihood = "BLOCKED"
    elif height_sealed:
        likelihood = "LOW"  # 종상향 가능해도 높이 봉인 → 실현 제약
    elif promote and not constrain:
        likelihood = "HIGH"
    elif promote and constrain:
        likelihood = "MIXED"
    elif constrain:
        likelihood = "LOW"
    else:
        likelihood = "UNKNOWN"

    notes = ["토지이용계획 신호 기반 정성 판별 — 실제 종상향은 도시계획 절차·공공기여(증가 용적률 일부)·심의 필요"]
    if height_sealed:
        notes.append("⚠️ 고도/경관 제한 — 용적률 상향해도 높이규제로 실현 제약(상한↑ ≠ 가용 연면적, 교차검증 필요)")
    if hard_block:
        notes.append("⚠️ 문화재/그린벨트/군사 등 — 개발 자체 제약(종상향 논의 제외)")
    return {
        "promote_signals": promote,
        "constraint_signals": constrain,
        "height_sealed": bool(height_sealed),
        "height_seal_reason": height_sealed,
        "development_blocked": bool(hard_block),
        "likelihood": likelihood,
        "notes": notes,
    }
