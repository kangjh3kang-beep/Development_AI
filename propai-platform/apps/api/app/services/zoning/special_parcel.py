"""특이부지 감지 레이어 — 비일상 토지특성(학교용지·공공용지·농지·산지·맹지·규제구역 등)을
지목(land_category)·용도지역·구역·접도 데이터에서 규칙기반으로 잡아내, 법적/인허가 특이사항과
개발가능성 게이트를 도출한다.

배경: 부지분석이 지목('학교용지')은 읽지만 그 법적 함의를 반영 못 해, 도시계획시설(학교) 부지를
일반 상업지처럼 '최대 연면적 58,825평 가능'으로 오분석하는 결함이 있었다(의정부동224 사례).
이 레이어가 그런 특이상태를 명시 경고·선행절차·개발가능성으로 환원한다. 규칙기반(LLM 무의존)이라
결정적·정직하며, 추가(additive)로 기존 응답을 손상하지 않는다.

developability(개발가능성 게이트):
  POSSIBLE              일반 개발 가능(특이 없음)
  CAUTION               가능하나 사전확인 필요(경미)
  CONDITIONAL           조건부 — 인허가/전용/협의 등 선행절차 통과 시 가능
  NEEDS_OFFICIAL_SURVEY 공식 산림데이터(산지구분·경사도·입목축적) 미확보 — 확정 판단 불가,
                        참고용 예비안만 산출(확정 설계 차단). CONDITIONAL과 같은 잠정 등급.
  PRECONDITION          선행 도시계획 변경/시설폐지 등 중대한 선행절차 필수
  BLOCKED               원칙적으로 일반 개발 불가
"""
from __future__ import annotations

from typing import Any

# 심각도 순위(높을수록 제약 큼) — 여러 특이요인 중 최댓값을 부지 종합 게이트로 채택.
#   NEEDS_OFFICIAL_SURVEY = CONDITIONAL과 같은 '잠정' 등급(값 2). 공식 산림데이터 미확보로
#   확정 설계는 막되(참고안만), CONDITIONAL과 동일 심각도로 취급한다(기존 값 불변).
_RANK = {"POSSIBLE": 0, "CAUTION": 1, "CONDITIONAL": 2, "NEEDS_OFFICIAL_SURVEY": 2,
         "PRECONDITION": 3, "BLOCKED": 4}


def _factor_legal_refs(legal_ref_keys: list[str] | None) -> list[dict]:
    """특이요인의 legal_ref_keys를 레지스트리(get_legal_refs)로 직렬화해 verified 법령 링크 반환.

    - url_status='verified'(law.go.kr 딥링크)만 프론트가 클릭 링크로, 그 외/빈값은 텍스트 폴백.
    - 키가 없거나 레지스트리 실패 시 빈 리스트(legal_basis 텍스트로만 정직 표기 — 날조 링크 금지).
    - URL은 전적으로 레지스트리 출력만 사용한다(여기서 URL 조립 절대 금지).
    """
    keys = legal_ref_keys or []
    if not keys:
        return []
    try:
        from app.services.legal.legal_reference_registry import get_legal_refs

        return get_legal_refs(keys)
    except Exception:  # noqa: BLE001 — 레지스트리 실패는 텍스트 legal_basis로 graceful degrade.
        return []


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
# NEEDS_OFFICIAL_SURVEY(임야/산지 공식 산림데이터 미확보)도 잠정으로 분류한다 —
#   gate_decision()이 "TENTATIVE"를 반환해 소비처가 '참고안(확정 아님)'으로 안전하게 다룬다.
#   (확정 % / 확정 설계 없음 — 공식 산림조사서·경사도조사 확보 전까지 예비안만.)
GATE_TENTATIVE_DEVELOPABILITY = {"PRECONDITION", "CONDITIONAL", "NEEDS_OFFICIAL_SURVEY"}
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
    elif dev == "NEEDS_OFFICIAL_SURVEY":
        # 임야/산지 — 공식 산림데이터(산림청 조사) 미확보. 확정 설계 불가, 참고용 예비안만.
        head = ("공식 산림데이터(산지구분·보전산지 여부·평균경사도·입목축적) 미확보 — 산지전용 확정 판단 "
                "불가, 참고용 예비안입니다(확정 아님). 산림조사서·평균경사도조사서 등 공식 조사가 필요합니다.")
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
            # verified 법령링크용 레지스트리 키(학교용지 특례법). 도시계획시설(국토계획법 제30·43조)·
            #   사립학교법은 verified 딥링크 키가 없어 legal_basis 텍스트로만 정직 표기(날조 링크 금지).
            "legal_ref_keys": ["school_land_special"],
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
            # 국공유 용도폐지·처분(verified). 도시계획시설 결정·건축법 제44조는 verified 키 없음 → 텍스트 유지.
            "legal_ref_keys": ["state_property", "public_property"],
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
            "legal_ref_keys": ["public_property"],
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
            "legal_ref_keys": ["farmland_conversion"],
            "permit_prerequisites": ["농지전용허가/협의", "농지보전부담금 산정"],
        }
    if "임야" in c or "산림" in c:  # ★'산' 접두 매칭 제거 — 지목 "산업용지"(공업)를 임야로 오탐하던 버그.
        # ★임야(산지)는 산림청 공식 조사데이터(산지구분·평균경사도·입목축적 등)가 있어야만
        #   산지전용 확정 판단이 가능하다(레드팀 P1-2: 임목본수도·경사도는 인허가급 데이터 아님).
        #   그 데이터가 아직 배선되지 않았으므로(E3 커넥터에서 채울 예정), 확정 설계를 막고
        #   참고용 예비안만 허용하는 NEEDS_OFFICIAL_SURVEY 게이트를 건다(정직-실패 게이트).
        return {
            "category": "임야(산지)", "developability": "NEEDS_OFFICIAL_SURVEY",
            # 공식 산림데이터가 채워질 자리(현재는 전부 미상=None) — E3 커넥터가 실측값을 주입한다.
            #   전부 None인 동안은 아래 항목을 '실제 판정'이 아닌 '공식조사 필요'로만 고지한다(무날조).
            "forest_facts": {
                "보전산지_여부": None,          # 보전산지(임업용/공익용) 포함 여부 — 포함 시 전용 강한 제약
                "산지구분": None,              # 보전산지/준보전산지 구분
                "평균경사도_pct": None,         # 평균경사도(%) — 25도/30도 등 지자체 조례 기준 대비
                "표고비율_pct": None,          # 표고(고도) 기준 대비 비율
                "입목축적_per_ha": None,        # ha당 입목축적(㎥/ha)
                "관할평균_입목축적_per_ha": None,  # 관할 시군구 평균 입목축적(비교 기준)
                "임상": None,                 # 임상(침엽수/활엽수/혼효림 등)
                "official_data_source": None,  # 공식 데이터 출처(산림청 등) — 확보 시 기재
            },
            # 확정 판단에 필요한 공식 조사가 미확보라 확정 설계를 막는 신호(소비처/게이트가 참고안으로 강등).
            "official_survey_required": True,
            "blocking_unknown": True,
            "implications": [
                "지목이 임야로, 개발을 위해서는 산지전용허가가 필요하며 경사도·표고·입목축적 기준을 충족해야 합니다.",
                "★확정 판단에는 산림청 공식 조사데이터가 필요합니다(현재 미확보 — 아래 항목은 공식조사로 산정해야 하며 아직 계산되지 않았습니다):",
                "  · 평균경사도 — 지자체 조례상 산지전용 허용 기준(통상 평균경사도 25도 또는 30도 이하)에 부합하는지 공식 평균경사도조사서로 확인해야 합니다.",
                "  · 입목축적 — ha당 입목축적이 관할 시군구 평균 대비 일정 배수(예: 150% 이하) 이내인지 산림조사서로 확인해야 합니다.",
                "  · 보전산지 포함 여부 — 보전산지(임업용·공익용)가 포함되면 전용이 크게 제한되므로 산지구분 확인이 선행됩니다.",
                "  · 660㎡ 미만 등 소규모 예외 해당 여부도 공식 자료로 판정해야 합니다.",
                "이 항목들은 아직 실제로 계산되지 않았으며, 공식 산림조사 확보 전까지는 참고용 예비안만 제시합니다(확정 아님).",
                "대체산림자원조성비가 부과됩니다.",
            ],
            "legal_basis": ["산지관리법 제14조(산지전용허가)", "대체산림자원조성비"],
            "legal_ref_keys": ["forest_conversion"],
            "permit_prerequisites": [
                "산지전용허가",
                "경사도/표고/입목축적 검토",
                "산림조사서·평균경사도조사서 작성(산림기술사 등 자격)",
                "대체산림자원조성비 산정",
            ],
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
            "legal_ref_keys": ["greenbelt"],
            "permit_prerequisites": ["GB 해제 또는 예외 허가대상 여부 확인"]}),
        (("문화재", "역사문화환경"), {"category": "문화재보호구역/역사문화환경 보존지역", "developability": "CONDITIONAL",
            "implications": ["문화재 인근으로 현상변경 허가 및 매장문화재 지표·발굴조사가 필요할 수 있습니다."],
            "legal_basis": ["문화유산의 보존 및 활용에 관한 법률", "매장유산 보호 및 조사에 관한 법률"],
            "legal_ref_keys": ["cultural_heritage", "buried_heritage"],
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


# ──────────────────────────────────────────────────────────────────────────
# 규제 선행절차 레이어(가산) — 지목/구역이 아닌 '개발규모·입지' 임계로 작동하는 인허가
#   선행요건(소방 성능위주설계·도로법 접도구역/연결허가·하수도 원인자부담금·소규모 환경영향평가).
#   기존 _rule_by_* 와 동일 패턴(legal_basis+permit_prerequisites+developability), _RANK 게이트 활용.
#   값(연면적/층수/도로폭/면적)이 임계 미만이거나 미상이면 None(과탐 방지·정직).
# ──────────────────────────────────────────────────────────────────────────

# 성능위주설계 대상(소방시설법 시행령) — 일반 임계(보수): 연면적 20만㎡↑ 또는 층수 30층↑(높이 120m↑),
#   지하층 포함 30층↑, 아파트는 50층↑(높이 200m↑). 정밀요건은 소방서 사전협의로 확정.
_PWD_GFA_SQM = 200_000.0
_PWD_FLOORS = 30


def _num(v) -> float | None:
    """숫자 변환(실패/None → None). 임계 비교 전 안전 캐스팅."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _rule_by_fire_performance(result: dict) -> dict[str, Any] | None:
    """소방 성능위주설계(PBD) 대상 규모 임계 판정 — 연면적/층수 기반 선행 사전검토.

    대형 개발만 해당(임계 미만은 None). 일반건축물 인허가에 앞서 소방 성능위주설계 평가단
    심의가 선행되므로 CONDITIONAL(선행절차형)로 고지한다.
    """
    gfa = _num(result.get("total_floor_area_sqm")) or _num(result.get("gfa_sqm")) \
        or _num(result.get("max_gfa_sqm"))
    floors = _num(result.get("floors")) or _num(result.get("floor_count")) \
        or _num(result.get("ground_floors"))
    triggers: list[str] = []
    if gfa is not None and gfa >= _PWD_GFA_SQM:
        triggers.append(f"연면적 {gfa:,.0f}㎡(≥20만㎡)")
    if floors is not None and floors >= _PWD_FLOORS:
        triggers.append(f"지상 {int(floors)}층(≥30층)")
    if not triggers:
        return None
    return {
        "category": "소방 성능위주설계(PBD) 대상",
        "developability": "CONDITIONAL",
        "implications": [
            "개발규모(" + ", ".join(triggers) + ")가 성능위주설계 대상 임계에 해당해, 일반 건축허가에 앞서 "
            "소방 성능위주설계(PBD) 평가단 사전검토·심의가 선행됩니다.",
            "정밀 대상 여부·요건은 관할 소방서 사전협의로 확정해야 합니다.",
        ],
        "legal_basis": ["소방시설 설치 및 관리에 관한 법률 제8조(성능위주설계)"],
        "legal_ref_keys": ["fire_performance_design"],
        "permit_prerequisites": ["소방 성능위주설계 대상 여부 확인", "관할 소방서 사전협의·평가단 심의"],
    }


def _rule_by_road_law(result: dict) -> dict[str, Any] | None:
    """도로법 접도구역·연결허가 판정 — 도로(특히 국도·고속국도) 인접 시 선행 협의·허가.

    접도구역(도로 경계로부터 일정거리 건축제한)·도로 연결허가(진출입로 설치)는 도로관리청
    선행 협의 대상이므로 CONDITIONAL로 고지한다. 신호 없으면 None.
    """
    blob = " ".join(str(x) for x in (result.get("special_districts") or [])) \
        + " " + str(result.get("road_type") or "") + " " + str(result.get("abutting_road_name") or "")
    has_abutting_zone = result.get("road_abutting_zone") is True or "접도구역" in blob
    near_managed_road = any(k in blob for k in ("국도", "고속국도", "일반국도", "지방도", "도로법"))
    if not (has_abutting_zone or near_managed_road):
        return None
    impl = []
    if has_abutting_zone:
        impl.append("접도구역(도로 경계선에서 일정거리)에 해당해 건축물 신축·증축 등에 도로관리청 협의·허가가 필요합니다.")
    if near_managed_road:
        impl.append("도로법상 도로(국도·지방도 등)에 진출입로를 설치하려면 도로 연결허가(연결로 구조·간격 기준)가 선행됩니다.")
    return {
        "category": "도로법 접도구역·연결허가 대상",
        "developability": "CONDITIONAL",
        "implications": impl,
        "legal_basis": [
            "도로법 제40조(접도구역의 지정)",
            "도로법 제52조(도로와 다른 시설의 연결)",
        ],
        "legal_ref_keys": ["road_abutting_zone", "road_connection_permit"],
        "permit_prerequisites": [
            "접도구역 해당 여부·건축제한 확인(도로관리청)",
            "도로 연결(진출입로) 허가 신청·구조기준 충족",
        ],
    }


def _rule_by_sewer(result: dict) -> dict[str, Any] | None:
    """하수도법 원인자부담금·개인하수처리시설 판정 — 신·증축으로 오수 발생량 증가 시 선행 부담.

    하수처리구역 내 신·증축은 원인자부담금, 하수처리구역 밖은 개인하수처리시설 설치가
    수반되므로 CAUTION(사전확인)으로 고지한다. 명시 신호 없으면 None(과탐 방지).
    """
    in_sewer_area = result.get("in_sewer_service_area")
    blob = str(result.get("sewer_status") or "") + " " \
        + " ".join(str(x) for x in (result.get("special_districts") or []))
    has_signal = in_sewer_area is not None or any(
        k in blob for k in ("하수처리구역", "개인하수처리", "원인자부담", "정화조")
    )
    if not has_signal:
        return None
    impl = ["신·증축으로 오수 발생량이 늘면 하수도 원인자부담금이 부과될 수 있습니다."]
    prereq = ["오수 발생량 산정·원인자부담금 추정"]
    if in_sewer_area is False or "개인하수처리" in blob or "정화조" in blob:
        impl.append("하수처리구역 밖이면 개인하수처리시설(정화조·오수처리시설) 설치·신고가 선행됩니다.")
        prereq.append("개인하수처리시설 설치·신고(하수처리구역 외)")
    return {
        "category": "하수도 원인자부담금·개인하수처리시설",
        "developability": "CAUTION",
        "implications": impl,
        "legal_basis": [
            "하수도법 제61조(원인자부담금 등)",
            "하수도법 제34조(개인하수처리시설의 설치)",
        ],
        "legal_ref_keys": ["sewer_cause_charge", "private_sewage_facility"],
        "permit_prerequisites": prereq,
    }


def _rule_by_small_eia(result: dict) -> dict[str, Any] | None:
    """소규모 환경영향평가 규모 임계 판정 — 보전·관리·녹지·농림 등에서 일정 면적↑ 개발 시 선행.

    소규모 환경영향평가는 보전이 필요한 지역(관리·농림·자연환경보전·녹지 등)에서 사업면적이
    대상 규모(지역별 5,000~60,000㎡ 등) 이상이면 선행되므로 CONDITIONAL로 고지한다.
    용도지역이 도시지역(주거·상업·공업)이거나 면적 미상/소규모면 None.
    """
    zone = str(result.get("zone_type") or "")
    family = _zone_family(zone)
    # 소규모 환경영향평가는 비도시(관리·농림·자연환경보전)·녹지에서 주로 작동.
    target_family = family in ("관리", "농림", "자연환경보전", "녹지")
    if not target_family:
        return None
    area = _num(result.get("area_sqm")) or _num(result.get("land_area_sqm")) \
        or _num(result.get("total_area_sqm")) or _num(result.get("area"))
    # 보수적 일반 임계: 관리·농림·자연환경보전 5,000㎡↑(개발사업 일반 하한).
    # ★면적이 확보(>0)되고 임계를 충족할 때만 게이트한다. 면적 미상이면 None(게이트 안 함=일상부지 보존).
    #   다른 _rule_by_* 게이트의 '면적/규모 미상 시 None' 패턴과 일관 — 면적 미상 필지를 거짓 환경평가
    #   경고로 강등하던 무회귀 위반(계획관리·녹지 일상필지 오탐)을 제거한다.
    THRESH_SQM = 5_000.0
    if area is None or area < THRESH_SQM:
        return None
    size_note = f"사업면적 {area:,.0f}㎡"
    return {
        "category": "소규모 환경영향평가 대상(규모 임계)",
        "developability": "CONDITIONAL",
        "implications": [
            f"보전·관리 성격 용도지역({zone})에서 {size_note}의 개발은 소규모 환경영향평가 대상에 해당할 수 있어, "
            "사업계획 승인·인허가에 앞서 평가 협의가 선행됩니다.",
            "정확한 대상 규모는 지역·사업유형별 기준(환경영향평가법 시행령)으로 확정해야 합니다.",
        ],
        "legal_basis": ["환경영향평가법 제43조(소규모 환경영향평가의 대상)"],
        "legal_ref_keys": ["small_eia"],
        "permit_prerequisites": [
            "소규모 환경영향평가 대상 규모 해당 여부 확인",
            "환경영향평가 협의(승인기관 경유)",
        ],
    }


def _rules_by_regulation_thresholds(result: dict) -> list[dict[str, Any]]:
    """규모·입지 임계 기반 선행절차 규제 묶음(소방·도로법·하수도·소규모 환경영향평가)."""
    out: list[dict[str, Any]] = []
    for fn in (_rule_by_fire_performance, _rule_by_road_law, _rule_by_sewer, _rule_by_small_eia):
        r = fn(result)
        if r:
            out.append(r)
    return out


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
    # 규모·입지 임계 기반 선행절차 규제(소방 PBD·도로법 접도/연결·하수도 원인자부담·소규모 환경영향평가).
    #   기존 지목/구역/접도 요인과 동일 구조로 가산(임계 미만/미상이면 아무것도 추가 안 함).
    factors.extend(_rules_by_regulation_thresholds(result))

    mismatch = _zone_category_mismatch(land_category, zone_type)

    if not factors:
        return None  # 일상적 개발부지 — 특이 없음(정직)

    # 각 요인에 대안·해결방안·해결가능성(resolvable)을 부착.
    for f in factors:
        f.update(_resolution_for(f.get("category", ""), f.get("developability", "")))
        # verified 법령링크(레지스트리 단일출처) — 프론트가 LegalRefChip로 클릭 링크/텍스트 폴백.
        #   legal_ref_keys가 없는 요인은 빈 리스트(legal_basis 텍스트로만 정직 표기).
        f["legal_refs"] = _factor_legal_refs(f.get("legal_ref_keys"))

    # 종합 게이트 = 가장 제약 큰 요인.
    gate = max(factors, key=lambda f: _RANK.get(f.get("developability", "POSSIBLE"), 0))["developability"]
    label = {
        "BLOCKED": "원칙적 개발 불가",
        "PRECONDITION": "중대한 선행절차 필수(도시계획시설 폐지·용도변경 등)",
        "CONDITIONAL": "조건부 가능(인허가·전용·협의 선행)",
        "NEEDS_OFFICIAL_SURVEY": "공식 산림조사 필요(참고안 — 확정 아님)",
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
    # ★전역전파방지(SSOT): caveat/honest 분기를 개발가능성 값의 하드코딩 튜플이 아니라
    #   gate_decision()/GATE_TENTATIVE_DEVELOPABILITY 멤버십으로 판정한다. 이렇게 하면
    #   NEEDS_OFFICIAL_SURVEY 등 새 잠정 등급이 자동으로 '확정 아님' 정직 문구를 받아,
    #   임야(gate=NEEDS_OFFICIAL_SURVEY, resolvable=YES)가 "개발 가능"으로 오고지되지 않는다.
    decision = gate_decision(gate, resolvable_overall)
    if resolvable_overall == "NO":
        caveat = (
            f"개발가능성: {label}. 통상적 절차로 해결 불가능한 제약이 포함되어 현 상태로는 일반 "
            "분양개발이 불가합니다. 개발규모를 단정해 제시하지 않습니다."
        )
    elif decision == "TENTATIVE":
        # PRECONDITION/CONDITIONAL/NEEDS_OFFICIAL_SURVEY 등 잠정 등급 — tentative_marker가
        #   각 등급에 맞는 '확정 아님' 사유(산림조사 필요 등)를 반환하므로 그대로 사용한다.
        caveat = tentative_marker(gate, resolvable_overall, label)
    else:
        caveat = "사전확인 사항이 있으나 일반 개발은 가능합니다."
    if resolvable_overall == "NO":
        honest = ("⚠ 정직 고지: 이 부지에는 통상적 절차로 해결 불가능한 제약(예: 개발제한구역·공공기반시설 용지)이 "
                  "포함되어 있어, 현 상태로는 일반 분양개발이 불가합니다. 무리한 개발규모 산정은 제시하지 않습니다.")
    elif gate in GATE_TENTATIVE_DEVELOPABILITY:
        # ★developability 우선: 개발가능성 게이트가 잠정(NEEDS_OFFICIAL_SURVEY 포함)이면
        #   resolvable이 YES여도 '확정 아님·참고안·공식조사 필요'로 정직 고지한다(임야가
        #   resolvable=YES라 "표준 절차로 해결 가능"으로 새던 회귀 차단).
        honest = tentative_marker(gate, resolvable_overall, label)
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
    # ★도로법(접도구역·연결허가)은 도로 지목(도시계획시설 도로 폐도)과 다른 해결경로를 가지므로,
    #   '도로' 부분문자열이 이 신규 규제요인을 가로채지 않도록 먼저 제외한다(아래 전용 분기로 위임).
    #   (category에 "도로법/접도구역/연결허가"가 들어가면 도시계획시설 도로 폐도 분기로 새지 않는다.)
    if "도로" in c and not any(k in c for k in ("도로법", "접도구역", "연결허가")):
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
    # ── 규모·입지 임계 기반 선행절차 규제(소방·도로법·하수도·환경영향평가) — 표준 절차로 해결 가능 ──
    if "성능위주설계" in c or "PBD" in c or "소방" in c:
        return {"resolvable": "YES",
                "resolution_paths": ["소방 성능위주설계 평가단 사전검토·심의 통과", "관할 소방서 사전협의"],
                "alternatives": ["대상 임계 미만으로 규모 조정", "설계에 소방 성능설계 비용·일정 반영"]}
    if "도로법" in c or "접도구역" in c or "연결허가" in c:
        return {"resolvable": "CONDITIONAL",
                "resolution_paths": ["도로관리청 접도구역 협의·건축제한 확인", "도로 연결(진출입로) 허가 취득"],
                "alternatives": ["접도구역 회피 배치(이격거리 확보)", "대체 진출입 동선 확보", "허가비용·구조기준 설계 반영"]}
    if "하수도" in c or "원인자부담" in c or "개인하수처리" in c:
        return {"resolvable": "YES",
                "resolution_paths": ["원인자부담금 산정·납부", "하수처리구역 외는 개인하수처리시설 설치·신고"],
                "alternatives": ["부담금·시설비를 사업수지에 반영", "오수 발생량 저감 설계"]}
    if "환경영향평가" in c:
        return {"resolvable": "CONDITIONAL",
                "resolution_paths": ["소규모 환경영향평가 협의(승인기관 경유)", "대상 규모 해당 여부 사전확인"],
                "alternatives": ["대상 규모 미만으로 사업면적 조정", "협의 의견 반영 설계 변경"]}
    return {"resolvable": "CONDITIONAL", "resolution_paths": ["관계기관 협의"], "alternatives": ["해당 필지 제외 검토"]}


def _zone_family(zone_type: str | None) -> str | None:
    """용도지역명 → 규제성격 대분류(상업/주거/공업/녹지/관리/농림/자연환경).

    혼재 판정(상업+주거 등 성격 상이)에서 '임의 단일화 금지'를 위한 분류용. 매칭 안 되면 None.
    """
    z = (zone_type or "").replace(" ", "").strip()
    if not z:
        return None
    # 순서 주의: '자연녹지'·'자연환경보전' 등 '자연' 접두가 녹지/보전 어느 쪽인지 명확히 분기.
    if "상업" in z:
        return "상업"
    if "공업" in z:
        return "공업"
    if "녹지" in z:
        return "녹지"
    if "주거" in z:
        return "주거"
    if "자연환경보전" in z or ("자연" in z and "보전" in z):
        return "자연환경보전"
    if "관리" in z:
        return "관리"
    if "농림" in z:
        return "농림"
    return None


def _aggregate_integrated_zoning(enriched: list[dict]) -> dict[str, Any]:
    """다필지 통합 용도지역·실효/법정 한도·통합 GFA를 면적가중으로 집계(순수함수·외부콜 0).

    입력(enriched): 각 필지 dict는 `_enrich_effective_and_special`가 in-place로 부착한
      _far_eff/_bcr_eff(실효=조례), _far_legal/_bcr_legal(법정상한), _far_basis(실효 근거),
      그리고 area_sqm(=areaSqm)·zone_type을 갖는다. (이 함수는 그 키만 읽고 재계산하지 않는다.)

    산식 핵심:
      ① dominant_zone: zone별 면적합산 → max(면적). dominant_basis="area_weighted".
         동률(상위 두 zone 면적이 ±5% 이내) 또는 규제성격 상이(상업+주거 등 _zone_family 혼재)면
         "mixed_review_required"로 표기(임의 단일화 금지).
      ② blended_*_eff = Σ(area_i×eff_i)/Σarea — 결측(eff None) 필지는 가중에서 제외 + warning.
         blended_*_legal도 동일 방식으로 별도 산출(실효=조례, 법정=*_legal 분리).
      ③ integrated_gfa = Σ(area_i×far_eff_i/100) — ★단순 통합면적×blended_far 금지(혼재 과대방지).
         gfa_basis="per_parcel_effective_sum". 통합 건폐 바닥면적도 Σ(area_i×bcr_eff_i/100).
      far_basis_note: 조례 미확보로 법정폴백된 필지 수를 명시(_far_basis가 법정폴백 신호일 때).

    반환: {parcel_count, zone_mix[...], dominant_zone, dominant_basis, blended_far_eff_pct,
           blended_bcr_eff_pct, blended_far_legal_pct, blended_bcr_legal_pct, total_area_sqm,
           integrated_gfa_sqm, integrated_footprint_sqm, gfa_basis, far_basis_note, warnings}.
    미확보·산출불가 항목은 null(무목업) + warnings에 정직 기재.
    """
    parcels = list(enriched or [])
    warnings: list[str] = []

    def _area(p: dict) -> float:
        try:
            a = float(p.get("area_sqm") or 0)
        except (TypeError, ValueError):
            a = 0.0
        return a if a > 0 else 0.0

    def _num(v) -> float | None:
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    total_area = round(sum(_area(p) for p in parcels), 2)

    # ── ① zone별 면적합산 + zone_mix(필지 한도 분포) ──
    zone_area: dict[str, float] = {}
    # zone별 대표 한도(같은 zone은 법정한도 동일 → 첫 유효값 채택, 실효는 필지별이라 면적가중 별도).
    zone_legal: dict[str, dict] = {}
    zone_eff_acc: dict[str, dict] = {}  # zone별 실효 가중합 누적(면적가중)
    for p in parcels:
        z = (p.get("zone_type") or "").strip() or "미상"
        a = _area(p)
        zone_area[z] = zone_area.get(z, 0.0) + a
        zl = zone_legal.setdefault(z, {"bcr_legal": None, "far_legal": None})
        if zl["bcr_legal"] is None:
            zl["bcr_legal"] = _num(p.get("_bcr_legal"))
        if zl["far_legal"] is None:
            zl["far_legal"] = _num(p.get("_far_legal"))
        acc = zone_eff_acc.setdefault(z, {"a_bcr": 0.0, "w_bcr": 0.0, "a_far": 0.0, "w_far": 0.0})
        be, fe = _num(p.get("_bcr_eff")), _num(p.get("_far_eff"))
        if a > 0 and be is not None:
            acc["a_bcr"] += a
            acc["w_bcr"] += a * be
        if a > 0 and fe is not None:
            acc["a_far"] += a
            acc["w_far"] += a * fe

    zone_mix: list[dict[str, Any]] = []
    for z, a in sorted(zone_area.items(), key=lambda kv: kv[1], reverse=True):
        acc = zone_eff_acc.get(z, {})
        bcr_eff = round(acc["w_bcr"] / acc["a_bcr"], 1) if acc.get("a_bcr") else None
        far_eff = round(acc["w_far"] / acc["a_far"], 1) if acc.get("a_far") else None
        zone_mix.append({
            "zone": z,
            "area_sqm": round(a, 2),
            "share_pct": round(a / total_area * 100, 1) if total_area else None,
            "bcr_legal": zone_legal.get(z, {}).get("bcr_legal"),
            "far_legal": zone_legal.get(z, {}).get("far_legal"),
            "bcr_eff": bcr_eff,
            "far_eff": far_eff,
        })

    # ── dominant_zone 판정(동률·규제성격 혼재 시 mixed_review_required) ──
    dominant_zone: str | None
    dominant_basis = "area_weighted"
    real_zones = [(z, a) for z, a in zone_area.items() if z != "미상" and a > 0]
    if not real_zones:
        dominant_zone = None
        warnings.append("용도지역 미확보 — 대표 용도지역을 산정할 수 없습니다(통합 한도 산출 제한).")
    else:
        ranked = sorted(real_zones, key=lambda kv: kv[1], reverse=True)
        top_zone, top_area = ranked[0]
        # 규제성격 혼재(상업+주거 등): 성격 대분류가 2개 이상이면 임의 단일화 금지.
        families = {f for f in (_zone_family(z) for z, _a in real_zones) if f}
        mixed_family = len(families) >= 2
        # 동률: 상위 두 zone 면적이 ±5% 이내.
        tie = False
        if len(ranked) >= 2:
            second_area = ranked[1][1]
            if top_area > 0 and abs(top_area - second_area) / top_area <= 0.05:
                tie = True
        if mixed_family or tie:
            dominant_zone = "mixed_review_required"
            reason = []
            if mixed_family:
                reason.append(f"규제성격 상이({'·'.join(sorted(families))})")
            if tie:
                reason.append("상위 용도지역 면적 동률(±5% 이내)")
            warnings.append(
                "용도지역 혼재 — 대표 용도지역을 단일화하지 않고 검토 필요로 표기합니다("
                + ", ".join(reason) + "). 통합 한도는 면적가중 실효치로 산출됩니다."
            )
        else:
            dominant_zone = top_zone

    # ── ② blended(면적가중) — 결측 필지는 가중 제외 + warning ──
    def _blended(key: str, label: str) -> float | None:
        a_sum = 0.0
        w_sum = 0.0
        missing = 0
        for p in parcels:
            a = _area(p)
            v = _num(p.get(key))
            if a > 0 and v is not None:
                a_sum += a
                w_sum += a * v
            elif a > 0 and v is None:
                missing += 1
        if missing:
            warnings.append(f"{label} 결측 {missing}개 필지 — 면적가중에서 제외하고 산출했습니다.")
        return round(w_sum / a_sum, 1) if a_sum else None

    blended_far_eff = _blended("_far_eff", "실효 용적률")
    blended_bcr_eff = _blended("_bcr_eff", "실효 건폐율")
    blended_far_legal = _blended("_far_legal", "법정 용적률")
    blended_bcr_legal = _blended("_bcr_legal", "법정 건폐율")

    # ── ③ integrated_gfa = Σ(area_i×far_eff_i/100) — 통합면적×blended_far 사용 금지 ──
    integrated_gfa = 0.0
    integrated_footprint = 0.0
    gfa_area_used = 0.0
    for p in parcels:
        a = _area(p)
        fe = _num(p.get("_far_eff"))
        be = _num(p.get("_bcr_eff"))
        if a > 0 and fe is not None:
            integrated_gfa += a * fe / 100.0
            gfa_area_used += a
        if a > 0 and be is not None:
            integrated_footprint += a * be / 100.0
    integrated_gfa_val = round(integrated_gfa, 2) if gfa_area_used else None
    integrated_footprint_val = round(integrated_footprint, 2) if gfa_area_used else None

    # far_basis_note: 조례 미확보로 법정폴백된 필지 수(_far_basis가 법정 신호일 때).
    #   far_tier_service의 far_basis 문자열에 '법정'이 들어가면 조례 미반영 폴백으로 본다.
    legal_fallback = 0
    for p in parcels:
        if (p.get("zone_type") or "").strip():
            basis = str(p.get("_far_basis") or "")
            if not basis or "법정" in basis:
                legal_fallback += 1
    if legal_fallback:
        far_basis_note = (
            f"{legal_fallback}개 필지는 조례 실효 용적률 미확보로 법정상한을 폴백 적용했습니다"
            "(실효치는 조례 확정 시 하향될 수 있음)."
        )
    else:
        far_basis_note = "전 필지 조례 실효 용적률 반영(법정폴백 없음)."

    return {
        "parcel_count": len(parcels),
        "total_area_sqm": total_area or None,
        "zone_mix": zone_mix,
        "dominant_zone": dominant_zone,
        "dominant_basis": dominant_basis,
        "blended_far_eff_pct": blended_far_eff,
        "blended_bcr_eff_pct": blended_bcr_eff,
        "blended_far_legal_pct": blended_far_legal,
        "blended_bcr_legal_pct": blended_bcr_legal,
        "integrated_gfa_sqm": integrated_gfa_val,
        "integrated_footprint_sqm": integrated_footprint_val,
        "gfa_basis": "per_parcel_effective_sum",
        "far_basis_note": far_basis_note,
        "warnings": warnings,
    }


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

    # ★전역전파방지(SSOT): 다필지 disclosure도 resolvable만이 아니라 개발가능성 게이트로 판정한다.
    #   임야 필지(resolvable=YES)가 다필지 세트에 섞여 있어도 사업 게이트가 잠정(NEEDS_OFFICIAL_SURVEY
    #   포함)이면 "표준 절차로 해결 가능"으로 새지 않고 '확정 아님·참고안' 정직 고지를 준다.
    survey_parcels = [
        x for x in specials
        if x["special"]["developability"] == "NEEDS_OFFICIAL_SURVEY"
    ]
    if resolvable == "NO":
        disclosure = (f"⚠ 정직 고지: {len(blocking)}개 필지에 통상 절차로 해결 불가능한 제약이 있어 현 사업구역 전체의 "
                      "일반 개발이 불가합니다. 해당 필지를 제외(사업구역 재획정)하거나 대체부지를 확보해야 하며, "
                      "전체 부지 기준의 개발규모(연면적/세대수)는 제시하지 않습니다.")
        recommendation = "차단필지 제외 후 잔여 필지로 재산정하거나, 사업 자체의 타당성을 재검토하십시오."
    elif resolvable == "CONDITIONAL":
        disclosure = ("이 사업은 일부 필지의 인허가·도시계획 변경·전용·협의 등 선행절차 통과를 조건으로만 개발이 가능합니다. "
                      "선행절차 확정 전 개발규모는 '잠재치'이며, 미통과 시 해당 필지 제외가 필요합니다.")
        recommendation = "선행절차별 인허가 로드맵을 수립하고, 통과 실패 시나리오(필지 제외)의 잔여 개발규모를 병기하십시오."
    elif gate in GATE_TENTATIVE_DEVELOPABILITY or survey_parcels:
        # resolvable=YES여도 사업 게이트가 잠정(임야 공식조사 필요 등)이면 tentative_marker로 정직 강등.
        disclosure = tentative_marker(gate, resolvable)
        if survey_parcels:
            recommendation = (f"임야(산지) {len(survey_parcels)}개 필지는 산림조사서·평균경사도조사서 등 공식 산림데이터를 "
                              "확보한 뒤 산지전용 가능규모를 확정하십시오(현 규모는 참고용 예비안).")
        else:
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

