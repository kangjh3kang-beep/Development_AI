"""특이부지 감지 레이어 — 비일상 토지특성(학교용지·공공용지·농지·산지·맹지·규제구역 등)을
지목(land_category)·용도지역·구역·접도 데이터에서 규칙기반으로 잡아내, 법적/인허가 특이사항과
개발가능성 게이트를 도출한다.

배경: 부지분석이 지목('학교용지')은 읽지만 그 법적 함의를 반영 못 해, 도시계획시설(학교) 부지를
일반 상업지처럼 '최대 연면적 58,825평 가능'으로 오분석하는 결함이 있었다(의정부동224 사례).
이 레이어가 그런 특이상태를 명시 경고·선행절차·개발가능성으로 환원한다. 규칙기반(LLM 무의존)이라
결정적·정직하며, 추가(additive)로 기존 응답을 손상하지 않는다.

developability(개발가능성 게이트):
  POSSIBLE     일반 개발 가능(특이 없음)
  CAUTION      가능하나 사전확인 필요(경미)
  CONDITIONAL  조건부 — 인허가/전용/협의 등 선행절차 통과 시 가능
  PRECONDITION 선행 도시계획 변경/시설폐지 등 중대한 선행절차 필수
  BLOCKED      원칙적으로 일반 개발 불가
"""
from __future__ import annotations

from typing import Any

# 심각도 순위(높을수록 제약 큼) — 여러 특이요인 중 최댓값을 부지 종합 게이트로 채택.
_RANK = {"POSSIBLE": 0, "CAUTION": 1, "CONDITIONAL": 2, "PRECONDITION": 3, "BLOCKED": 4}


# ──────────────────────────────────────────────────────────────────────────
# 게이트 정책 SSOT — 특이부지 게이트가 시나리오 산출에 어떻게 반영돼야 하는지의 단일 기준.
#   (auto_recommend_top3 / integrated_recommender 양쪽이 같은 함수를 써서 정책 분기를 일원화한다.
#    국소 패치 금지 — 두 게이트가 서로 다른 임계로 갈라지는 회귀를 막는다.)
# ──────────────────────────────────────────────────────────────────────────

# 원천 차단 — 통상 절차로 해결 불가(NO) 또는 원칙적 개발 불가(BLOCKED). 후보 미생성·정직고지만.
GATE_BLOCK_DEVELOPABILITY = {"BLOCKED"}
GATE_BLOCK_RESOLVABLE = {"NO"}

# 잠정(조건부) 강등 — 선행 도시계획변경/시설폐지(PRECONDITION) 또는 인허가·협의·전용(CONDITIONAL),
#   혹은 해결가능성이 조건부(CONDITIONAL)인 경우. 후보는 산출하되 '확정 아님·선행절차 전제 잠정치'로
#   강등하고, 비현실 확신 % 표시를 억제한다(도로 단독 PRECONDITION → 타운하우스88% 할루시네이션 차단).
GATE_TENTATIVE_DEVELOPABILITY = {"PRECONDITION", "CONDITIONAL"}
GATE_TENTATIVE_RESOLVABLE = {"CONDITIONAL"}


def gate_decision(developability: str | None, resolvable: str | None) -> str:
    """특이부지 게이트(developability·resolvable)를 시나리오 산출 정책으로 환원한다.

    반환:
      "BLOCK"     — 후보 미생성(개발규모/수지 미산정·정직고지만). 가짜 % 차단.
      "TENTATIVE" — 후보 산출하되 '선행절차 전제·잠정치(확정 아님)'로 강등 + 확신 % 억제.
      "PASS"      — 일상 개발부지(특이 없음/경미) — 통상 산출.
    ★단일 기준: 두 게이트(auto_recommend_top3·integrated_recommender)가 동일 분기를 쓴다.
    """
    dev = (developability or "").strip().upper()
    res = (resolvable or "").strip().upper()
    if dev in GATE_BLOCK_DEVELOPABILITY or res in GATE_BLOCK_RESOLVABLE:
        return "BLOCK"
    if dev in GATE_TENTATIVE_DEVELOPABILITY or res in GATE_TENTATIVE_RESOLVABLE:
        return "TENTATIVE"
    return "PASS"


def tentative_marker(developability: str | None, resolvable: str | None, severity_label: str | None = None) -> str:
    """잠정 강등 시나리오에 붙일 정직 사유 문구(확정 아님·선행절차 전제) — UI/응답 공용."""
    dev = (developability or "").strip().upper()
    res = (resolvable or "").strip().upper()
    label = (severity_label or "").strip()
    if dev == "PRECONDITION":
        head = "선행 도시계획변경·시설폐지 등 중대한 선행절차 통과를 전제로 한 잠정치입니다(확정 아님)."
    elif dev == "CONDITIONAL" or res == "CONDITIONAL":
        # CONDITIONAL(인허가·전용·협의) 또는 해결가능성 조건부(예: 맹지·진입로 확보) — 동일하게 조건부 잠정.
        head = "인허가·전용·협의 등 선행절차 통과를 조건으로 한 잠정치입니다(확정 아님)."
    else:
        head = "선행절차 통과를 전제로 한 잠정치입니다(확정 아님)."
    if label:
        head = f"{head} 개발가능성: {label}."
    return head + " 선행절차가 확정되기 전의 개발규모·수익성은 참고용이며 단정이 아닙니다."


def _rule_by_land_category(cat: str) -> dict[str, Any] | None:
    """지목(land_category) 기반 특이 판정. cat 은 NED 토지특성 지목명(예: 학교용지)."""
    c = (cat or "").strip()
    # 도시계획시설/공공용지 계열 — 그 용도로 결정돼 있으면 일반 개발 불가, 시설폐지/용도변경 선행.
    if "학교" in c:
        return {
            "category": "학교용지(도시계획시설 가능성)",
            "developability": "PRECONDITION",
            "implications": [
                "지목이 학교용지로, 「도시·군계획시설(학교)」로 결정된 부지일 가능성이 높습니다.",
                "도시계획시설로 결정돼 있으면 학교 외 용도의 일반 건축이 불가하며, 분양개발을 위해서는 도시계획시설(학교) 폐지(실효) 또는 도시·군관리계획 변경이 선행되어야 합니다.",
                "공립이면 교육청(교육지원청) 협의·용도폐지, 사립이면 학교법인의 기본재산 처분(관할청 허가)·수익용 재산 전환 등 별도 절차가 수반됩니다.",
            ],
            "legal_basis": [
                "국토의 계획 및 이용에 관한 법률 제30조(도시·군관리계획의 결정)·제43조(도시·군계획시설)",
                "학교용지 확보 등에 관한 특례법",
                "사립학교법 제28조(재산의 관리·보호) — 사립학교 기본재산 처분 시 관할청 허가",
            ],
            "permit_prerequisites": [
                "해당 부지의 도시계획시설(학교) 결정 여부 열람(토지이용계획확인원·도시계획 결정도)",
                "도시계획시설 폐지/변경 또는 실효 여부 확인 및 절차 착수",
                "교육청 협의(공립) 또는 학교법인 처분 허가(사립)",
            ],
        }
    if "종교" in c:
        return {
            "category": "종교용지", "developability": "CONDITIONAL",
            "implications": ["지목이 종교용지로, 종교시설 목적 외 개발 시 용도변경·처분 제한이 있을 수 있습니다.",
                             "재단/종교법인 소유면 기본재산 처분 절차가 수반될 수 있습니다."],
            "legal_basis": ["국토계획법(도시·군관리계획)", "민법상 재단법인 기본재산 처분 제한"],
            "permit_prerequisites": ["소유주체·도시계획시설 여부 확인", "용도변경 가능성 검토"],
        }
    if "도로" in c:
        # ★도로는 단정적 '불가'(BLOCKED)가 아니라 '폐도 경우의 수'가 있는 선행절차형(PRECONDITION).
        #   폐도(도로 폐지)가 가능한 경우/불가능한 경우가 갈리고, 도로 기능·주민동의 등에 따라 달라진다.
        return {
            "category": "공공·기반시설 용지(도로)", "developability": "PRECONDITION",
            "implications": [
                "지목이 도로로 공공용지/기반시설에 해당해 현 상태로는 일반 분양개발이 어렵습니다(단정적 불가 아님).",
                "폐도(도로 폐지)로 개발이 가능해지는 경우가 있습니다 — 도시계획시설(도로) 폐지·변경(지구단위계획/도시관리계획), 이해관계인·주민 의견청취·동의, 대체도로 확보가 선행되어야 합니다.",
                "폐도 가능 여부는 도로 기능(간선/국지/현황)·연결성·대체도로·통행영향·주민동의·계획 정합성에 따라 달라집니다(현황 필수도로·간선도로는 폐도 곤란).",
                "국공유 도로는 용도폐지 후 매각/양여(국유재산법·공유재산법)가 선행됩니다.",
            ],
            "legal_basis": [
                "국토계획법(도시·군계획시설 결정·변경)",
                "국유재산법·공유재산 및 물품 관리법(용도폐지·매각/양여)",
                "건축법 제44조(대지와 도로의 관계)",
            ],
            "permit_prerequisites": [
                "도시계획시설(도로) 폐지·변경 가능성 확인(지구단위계획/도시관리계획)",
                "이해관계인·주민 의견청취 및 동의", "대체도로 확보·교통영향 검토",
            ],
        }
    if any(k in c for k in ("구거", "하천", "제방", "유지", "수도", "철도")):
        return {
            "category": f"공공·기반시설 용지({c})", "developability": "BLOCKED",
            "implications": [f"지목이 {c}(으)로 공공용지/기반시설에 해당해, 사실상 일반 분양개발이 불가합니다.",
                             "용도폐지·교환·불용처분 등 행정절차 없이는 건축이 불가합니다."],
            "legal_basis": ["국토계획법 도시·군계획시설", "공유재산 및 물품 관리법(국공유 시)"],
            "permit_prerequisites": ["용도폐지·불용처분 가능성 확인", "대체부지 검토"],
        }
    if "공원" in c or "유원지" in c or "체육" in c:
        return {
            "category": f"도시계획시설({c})", "developability": "PRECONDITION",
            "implications": [f"지목이 {c}(으)로 도시계획시설일 가능성이 높아, 시설폐지/변경 선행 없이는 일반 개발이 불가합니다."],
            "legal_basis": ["국토계획법 제43조(도시·군계획시설)"],
            "permit_prerequisites": ["도시계획시설 결정·실효 여부 확인", "도시·군관리계획 변경 절차"],
        }
    if "묘지" in c:
        return {
            "category": "묘지", "developability": "CONDITIONAL",
            "implications": ["지목이 묘지로, 분묘기지권·개장(이장) 및 「장사 등에 관한 법률」상 절차가 필요합니다."],
            "legal_basis": ["장사 등에 관한 법률", "분묘기지권(판례)"],
            "permit_prerequisites": ["분묘 현황·연고자 확인", "개장 신고·이장 절차"],
        }
    if any(k in c for k in ("전", "답", "과수원", "목장")):
        # 단, '대' 등과의 혼동 방지를 위해 정확 매칭은 호출부에서 1글자 지목도 처리.
        return {
            "category": f"농지({c})", "developability": "CONDITIONAL",
            "implications": [f"지목이 {c}(으)로 농지에 해당해, 개발을 위해서는 농지전용허가가 필요합니다(농지보전부담금 부과).",
                             "도시지역(상업·주거)이라도 농지전용 협의/신고 대상일 수 있습니다."],
            "legal_basis": ["농지법 제34조(농지전용허가)·제38조(농지보전부담금)"],
            "permit_prerequisites": ["농지전용허가/협의", "농지보전부담금 산정"],
        }
    if "임야" in c or "산림" in c:  # ★'산' 접두 매칭 제거 — 지목 "산업용지"(공업)를 임야로 오탐하던 버그.
        return {
            "category": "임야(산지)", "developability": "CONDITIONAL",
            "implications": ["지목이 임야로, 개발을 위해서는 산지전용허가가 필요하며 경사도·표고·입목축적 기준을 충족해야 합니다.",
                             "대체산림자원조성비가 부과됩니다."],
            "legal_basis": ["산지관리법 제14조(산지전용허가)", "대체산림자원조성비"],
            "permit_prerequisites": ["산지전용허가", "경사도/표고/입목축적 검토"],
        }
    return None


def _rules_by_districts(special_districts: list, zone_type: str) -> list[dict[str, Any]]:
    """용도지구/구역(special_districts)·용도지역 기반 특이 판정(복수 가능)."""
    out: list[dict[str, Any]] = []
    blob = " ".join([str(x) for x in (special_districts or [])]) + " " + (zone_type or "")
    table = [
        (("개발제한구역", "그린벨트", "GB"), {"category": "개발제한구역(GB)", "developability": "BLOCKED",
            "implications": ["개발제한구역으로 원칙적으로 신축·개발이 금지됩니다(예외 행위만 허가)."],
            "legal_basis": ["개발제한구역의 지정 및 관리에 관한 특별조치법"],
            "permit_prerequisites": ["GB 해제 또는 예외 허가대상 여부 확인"]}),
        (("문화재", "역사문화환경"), {"category": "문화재보호구역/역사문화환경 보존지역", "developability": "CONDITIONAL",
            "implications": ["문화재 인근으로 현상변경 허가 및 매장문화재 지표·발굴조사가 필요할 수 있습니다."],
            "legal_basis": ["문화유산의 보존 및 활용에 관한 법률", "매장유산 보호 및 조사에 관한 법률"],
            "permit_prerequisites": ["현상변경 허가", "매장문화재 지표조사"]}),
        (("군사", "군사시설"), {"category": "군사시설보호구역", "developability": "CONDITIONAL",
            "implications": ["군사시설보호구역으로 건축 시 군부대 협의(고도·용도 제한)가 필요합니다."],
            "legal_basis": ["군사기지 및 군사시설 보호법"], "permit_prerequisites": ["관할 부대 협의"]}),
        (("상수원", "수변", "수질보전"), {"category": "상수원보호구역/수변구역", "developability": "CONDITIONAL",
            "implications": ["상수원/수변 보호 목적의 행위제한(오·폐수 배출시설 제한 등)이 적용됩니다."],
            "legal_basis": ["수도법", "한강수계 상수원수질개선 및 주민지원 등에 관한 법률"],
            "permit_prerequisites": ["행위제한 확인"]}),
    ]
    for keys, rule in table:
        if any(k in blob for k in keys):
            out.append(rule)
    return out


def _rule_by_road(result: dict) -> dict[str, Any] | None:
    """접도(맹지) 판정 — 도로 미접이면 건축법 접도의무 미충족."""
    # road_contact/road_width/abutting_road 등 가용 필드에서 접도 여부 추정.
    rc = result.get("road_contact")
    # ★0(도로 미접)이 falsy라 `a or b`로 묶으면 road_width_m=0이 b로 새어 맹지를 놓친다.
    #   None일 때만 대체값을 쓰도록 분리해 0을 보존한다.
    rw = result.get("road_width_m")
    if rw is None:
        rw = result.get("road_width")
    if rc is False or (isinstance(rw, (int, float)) and rw == 0):
        return {
            "category": "맹지(도로 미접)", "developability": "CONDITIONAL",
            "implications": ["도로에 접하지 않는 맹지로, 건축법상 접도의무(4m 이상 도로에 2m 이상 접함) 미충족 시 건축허가가 불가합니다.",
                             "진입로(사도/지역권) 확보가 선행되어야 합니다."],
            "legal_basis": ["건축법 제44조(대지와 도로의 관계)"],
            "permit_prerequisites": ["진입도로 확보(사도 개설·지역권 설정)", "현황도로 인정 여부 확인"],
        }
    return None


def _zone_category_mismatch(land_category: str, zone_type: str) -> str | None:
    """지목과 용도지역의 비일상 조합 주석(예: 학교용지가 일반상업지역)."""
    c, z = (land_category or ""), (zone_type or "")
    if "학교" in c and "상업" in z:
        return f"지목({c})과 용도지역({z})의 조합이 이례적입니다 — 상업지역 내 학교부지로, 용도지역상 한도(고용적률)는 학교 폐지·용도변경을 전제로만 실현됩니다."
    return None


def detect_special_parcel(result: dict) -> dict[str, Any] | None:
    """부지분석 결과(result)에서 특이부지 요인을 종합 판정. 특이 없으면 None.

    반환: {is_special, developability(종합 게이트), severity_label, factors[...],
           warnings[...], development_caveat} — 모두 추가(additive) 필드.
    """
    land_category = str(result.get("land_category") or "")
    zone_type = str(result.get("zone_type") or "")
    special_districts = result.get("special_districts") or []

    factors: list[dict[str, Any]] = []
    f0 = _rule_by_land_category(land_category)
    if f0:
        factors.append(f0)
    factors.extend(_rules_by_districts(special_districts, zone_type))
    fr = _rule_by_road(result)
    if fr:
        factors.append(fr)

    mismatch = _zone_category_mismatch(land_category, zone_type)

    if not factors:
        return None  # 일상적 개발부지 — 특이 없음(정직)

    # 각 요인에 대안·해결방안·해결가능성(resolvable)을 부착.
    for f in factors:
        f.update(_resolution_for(f.get("category", ""), f.get("developability", "")))

    # 종합 게이트 = 가장 제약 큰 요인.
    gate = max(factors, key=lambda f: _RANK.get(f.get("developability", "POSSIBLE"), 0))["developability"]
    label = {
        "BLOCKED": "원칙적 개발 불가",
        "PRECONDITION": "중대한 선행절차 필수(도시계획시설 폐지·용도변경 등)",
        "CONDITIONAL": "조건부 가능(인허가·전용·협의 선행)",
        "CAUTION": "사전확인 필요", "POSSIBLE": "개발 가능",
    }.get(gate, gate)

    warnings: list[str] = [f"[특이부지] {f['category']}: {f['implications'][0]}" for f in factors]
    if mismatch:
        warnings.append(f"[특이조합] {mismatch}")

    # 해결가능성 종합(정직 고지) — 해결불가(NO) 요인이 있으면 명시 고지해 할루시네이션 차단.
    worst_resolvable = min((_RES_RANK.get(f.get("resolvable", "YES"), 2) for f in factors), default=2)
    resolvable_overall = {0: "NO", 1: "CONDITIONAL", 2: "YES"}[worst_resolvable]

    # 고지 정합: 해결불가(NO)면 게이트와 무관하게 '불가'로 단일화한다(caveat=게이트 기준,
    #   honest=resolvable 기준이라 BLOCKED↔CONDITIONAL에서 메시지가 엇갈리던 모순 제거).
    if resolvable_overall == "NO":
        caveat = (
            f"개발가능성: {label}. 통상적 절차로 해결 불가능한 제약이 포함되어 현 상태로는 일반 "
            "분양개발이 불가합니다. 개발규모를 단정해 제시하지 않습니다."
        )
    elif gate in ("PRECONDITION", "BLOCKED", "CONDITIONAL"):
        caveat = (
            "이 부지는 특이 토지특성으로 인해 용도지역상 법정 최대 연면적/용적률이 그대로 실현되지 "
            f"않을 수 있습니다. 개발가능성: {label}. 선행절차 통과 여부에 따라 실제 개발규모가 결정됩니다."
        )
    else:
        caveat = "사전확인 사항이 있으나 일반 개발은 가능합니다."
    if resolvable_overall == "NO":
        honest = ("⚠ 정직 고지: 이 부지에는 통상적 절차로 해결 불가능한 제약(예: 개발제한구역·공공기반시설 용지)이 "
                  "포함되어 있어, 현 상태로는 일반 분양개발이 불가합니다. 무리한 개발규모 산정은 제시하지 않습니다.")
    elif resolvable_overall == "CONDITIONAL":
        honest = ("이 부지는 인허가·협의·도시계획 변경 등 선행절차 통과를 조건으로만 개발이 가능합니다. "
                  "선행절차 결과가 확정되기 전의 개발규모는 '잠재치'이며 확정치가 아닙니다.")
    else:
        honest = "표준 인허가 절차로 해결 가능한 특이사항입니다."

    return {
        "is_special": True,
        "developability": gate,
        "severity_label": label,
        "resolvable": resolvable_overall,
        "factors": factors,
        "zone_category_mismatch": mismatch,
        "warnings": warnings,
        "development_caveat": caveat,
        "honest_disclosure": honest,
        "note": "특이부지 감지(규칙기반). 실제 개발가능 여부·선행절차는 토지이용계획확인원·도시계획 결정도 열람으로 확정하십시오.",
    }


# 해결가능성 순위(낮을수록 어려움) — 다필지/종합 판정에 사용.
_RES_RANK = {"NO": 0, "CONDITIONAL": 1, "YES": 2}


def _resolution_for(category: str, developability: str) -> dict[str, Any]:
    """특이요인별 대안·해결방안 + 해결가능성(resolvable: YES/CONDITIONAL/NO)."""
    c = category or ""
    if "학교" in c or "공원" in c or "유원지" in c or "체육" in c:
        return {"resolvable": "CONDITIONAL",
                "resolution_paths": ["도시계획시설 폐지/변경(도시·군관리계획 변경 입안·결정)",
                                     "교육청 협의(공립)·학교법인 처분허가(사립)", "장기미집행 도시계획시설 실효 활용"],
                "alternatives": ["시설 존치 전제 시 해당 필지를 사업구역에서 제외", "용도변경 후 단계적 개발", "공공기여형 사업방식(기부채납 연계) 검토"]}
    if "개발제한구역" in c or "GB" in c:
        return {"resolvable": "NO",
                "resolution_paths": ["GB 해제는 국가·광역 도시계획 차원으로 개별 사업자가 해결 불가"],
                "alternatives": ["예외적 허가행위(GB 내 허용용도)만 검토", "해당 필지 제외·사업구역 재획정", "GB 경계 외 대체부지"]}
    if "도로" in c:
        # ★도로 폐도 경우의 수 — 단정 불가 아님. 도로 기능·주민동의·대체도로에 따라 가능/불가 갈림.
        return {"resolvable": "CONDITIONAL",
                "resolution_paths": ["도시계획시설(도로) 폐지·변경(지구단위계획/도시관리계획 입안·결정)",
                                     "이해관계인·주민 의견청취 및 동의 확보", "대체도로 확보·교통영향 검토",
                                     "국공유 도로는 용도폐지 후 매각/양여(국유재산법·공유재산법)"],
                "alternatives": ["현황 필수도로·간선도로면 존치·우회 설계(잔여 필지만 개발)",
                                 "폐도 고시·동의 확보 후 단계적 개발", "해당 도로 필지 제외·사업구역 재획정"]}
    if "공공" in c or "기반시설" in c or "하천" in c or "구거" in c or "제방" in c:
        return {"resolvable": "CONDITIONAL",
                "resolution_paths": ["용도폐지·불용처분(관리청 협의)", "공유재산 매각·교환"],
                "alternatives": ["해당 필지 제외", "현황 유지하며 잔여 필지만 개발", "대체 기반시설 제공 조건 협의"]}
    if "농지" in c:
        return {"resolvable": "YES",
                "resolution_paths": ["농지전용허가/협의 + 농지보전부담금 납부"],
                "alternatives": ["전용비용을 사업수지에 반영", "전용 불가 시 해당 필지 제외"]}
    if "임야" in c or "산지" in c:
        return {"resolvable": "YES",
                "resolution_paths": ["산지전용허가 + 대체산림자원조성비 납부", "경사도·표고·입목축적 기준 충족"],
                "alternatives": ["전용비용 반영", "기준 초과 구역 제외(부분개발)"]}
    if "맹지" in c:
        return {"resolvable": "CONDITIONAL",
                "resolution_paths": ["진입도로 확보(인접 필지 매입·사도개설·지역권 설정)", "현황도로 인정 협의"],
                "alternatives": ["접도 가능한 인접 필지 추가 편입", "맹지 필지 제외"]}
    if "묘지" in c:
        return {"resolvable": "CONDITIONAL",
                "resolution_paths": ["분묘 개장(이장) 신고·절차", "연고자 협의·보상"],
                "alternatives": ["무연고 분묘 개장 공고 절차", "분묘 구역 존치·우회 설계"]}
    if "문화재" in c or "역사문화" in c:
        return {"resolvable": "CONDITIONAL",
                "resolution_paths": ["현상변경 허가", "매장문화재 지표·발굴조사"],
                "alternatives": ["조사결과 반영 설계 변경", "보존구역 회피 배치"]}
    if "군사" in c:
        return {"resolvable": "CONDITIONAL", "resolution_paths": ["관할 부대 협의(고도·용도 제한 반영)"],
                "alternatives": ["제한고도 내 계획 조정"]}
    if "상수원" in c or "수변" in c:
        return {"resolvable": "CONDITIONAL", "resolution_paths": ["행위제한 준수 설계(오·폐수 무방류 등)"],
                "alternatives": ["허용용도 중심 계획", "구역 외 부지 검토"]}
    if "종교" in c:
        return {"resolvable": "CONDITIONAL", "resolution_paths": ["용도변경 검토", "종교법인 기본재산 처분 절차"],
                "alternatives": ["존치 전제 부분개발", "해당 필지 제외"]}
    return {"resolvable": "CONDITIONAL", "resolution_paths": ["관계기관 협의"], "alternatives": ["해당 필지 제외 검토"]}


def detect_multi_parcel(parcels: list[dict]) -> dict[str, Any]:
    """다필지 종합 특이부지 판정 — 한 필지의 특이성이 사업 전체를 제약할 수 있으므로,
    필지별 감지 후 가장 제약 큰 게이트로 사업 전체를 판정하고, 차단필지·대안을 도출한다.

    parcels: 각 원소는 부지분석 result dict(또는 최소 land_category/zone_type/pnu 포함).
    """
    per: list[dict[str, Any]] = []
    for i, p in enumerate(parcels or []):
        sp = detect_special_parcel(p)
        per.append({
            "index": i, "pnu": p.get("pnu"), "address": p.get("address"),
            "land_category": p.get("land_category"),
            "special": sp,  # None 이면 일상필지
        })

    specials = [x for x in per if x["special"]]
    if not specials:
        return {"parcel_count": len(per), "special_count": 0, "developability": "POSSIBLE",
                "resolvable": "YES", "blocking_parcels": [], "per_parcel": per,
                "honest_disclosure": "전 필지가 일상적 개발부지로 특이 제약이 없습니다.",
                "summary": f"{len(per)}개 필지 모두 특이사항 없음 — 통상 개발 가능."}

    # 사업 전체 게이트 = 가장 제약 큰 필지.
    gate = max(specials, key=lambda x: _RANK.get(x["special"]["developability"], 0))["special"]["developability"]
    worst_res = min((_RES_RANK.get(x["special"]["resolvable"], 2) for x in specials), default=2)
    resolvable = {0: "NO", 1: "CONDITIONAL", 2: "YES"}[worst_res]
    blocking = [{"pnu": x["pnu"], "land_category": x["land_category"],
                 "developability": x["special"]["developability"], "resolvable": x["special"]["resolvable"],
                 "category": x["special"]["factors"][0]["category"] if x["special"]["factors"] else None}
                for x in specials if x["special"]["resolvable"] == "NO"]

    if resolvable == "NO":
        disclosure = (f"⚠ 정직 고지: {len(blocking)}개 필지에 통상 절차로 해결 불가능한 제약이 있어 현 사업구역 전체의 "
                      "일반 개발이 불가합니다. 해당 필지를 제외(사업구역 재획정)하거나 대체부지를 확보해야 하며, "
                      "전체 부지 기준의 개발규모(연면적/세대수)는 제시하지 않습니다.")
        recommendation = "차단필지 제외 후 잔여 필지로 재산정하거나, 사업 자체의 타당성을 재검토하십시오."
    elif resolvable == "CONDITIONAL":
        disclosure = ("이 사업은 일부 필지의 인허가·도시계획 변경·전용·협의 등 선행절차 통과를 조건으로만 개발이 가능합니다. "
                      "선행절차 확정 전 개발규모는 '잠재치'이며, 미통과 시 해당 필지 제외가 필요합니다.")
        recommendation = "선행절차별 인허가 로드맵을 수립하고, 통과 실패 시나리오(필지 제외)의 잔여 개발규모를 병기하십시오."
    else:
        disclosure = "특이 필지가 있으나 표준 인허가 절차(전용·협의 등)로 해결 가능합니다."
        recommendation = "전용비용·부담금을 사업수지에 반영하여 진행하십시오."

    return {
        "parcel_count": len(per), "special_count": len(specials),
        "developability": gate, "resolvable": resolvable,
        "blocking_parcels": blocking, "per_parcel": per,
        "honest_disclosure": disclosure, "recommendation": recommendation,
        "note": "다필지 종합 — 가장 제약 큰 필지가 사업 전체를 좌우(연결개발 전제). 비인접/제외 시 잔여로 재산정.",
    }

