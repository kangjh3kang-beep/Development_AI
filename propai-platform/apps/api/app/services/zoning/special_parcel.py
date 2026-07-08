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

import math
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


# ──────────────────────────────────────────────────────────────────────────
# 개발행위허가 게이트(국토계획법 §56~58) — 도시지역 내 녹지(자연·생산·보전녹지)는
#   밀도한도(건폐/용적)만으로 '개발가능'을 단정할 수 없다. 건축 前 개발행위허가
#   (규모·경사도·연접개발·도로/배수 기준)와 토지형질변경이 선행/병행돼야 한다(감사 커버리지 갭:
#   전 repo에 §56 개발행위허가 판정 0건 → 107㎡ 자연녹지가 선행관문 안내 없이 '개발가능'으로 표기).
#   기존 _rule_by_* 와 동일 패턴(legal_basis+permit_prerequisites+developability, _RANK 게이트).
#   지목·면적 무관, zone_type이 녹지계열이면 발동. 보전녹지는 원칙적 제한(PRECONDITION)으로 차등.
# ──────────────────────────────────────────────────────────────────────────
def _rule_by_dev_act_permit(result: dict) -> dict[str, Any] | None:
    """개발행위허가(국토계획법 §56) 선행/병행 게이트 — 도시지역 내 녹지계열에서 발동.

    자연녹지·생산녹지 → CONDITIONAL(개발행위허가·형질변경 통과 조건부 가능),
    보전녹지 → PRECONDITION(개발 원칙적 제한 — 더 강한 선행절차 전제).
    녹지계열이 아니면 None(주거·상업·공업 등 일상 도시지역은 게이트 안 함 — 과탐 방지).
    """
    zone = str(result.get("zone_type") or "")
    if _zone_family(zone) != "녹지":
        return None
    # 자연/생산/보전 세분(미상 녹지는 보수적으로 자연녹지 취급 — CONDITIONAL).
    z = zone.replace(" ", "")
    if "보전녹지" in z:
        developability = "PRECONDITION"
        head = (
            "보전녹지지역은 자연환경·경관 보전 목적으로 개발이 원칙적으로 제한되며, 건축 전 "
            "개발행위허가(국토계획법 §56)·토지형질변경 통과가 선행되어야 합니다(허용 범위가 매우 좁음)."
        )
    else:
        developability = "CONDITIONAL"
        kind = "생산녹지지역" if "생산녹지" in z else ("자연녹지지역" if "자연녹지" in z else "녹지지역")
        head = (
            f"{kind}은 도시지역 내 녹지로, 밀도한도(건폐율·용적률) 충족만으로 개발이 확정되지 않습니다. "
            "건축 전 개발행위허가(국토계획법 §56)·토지형질변경이 선행/병행되어야 합니다."
        )
    return {
        "category": "개발행위허가 선행/병행(도시지역 녹지)",
        "developability": developability,
        "implications": [
            head,
            "개발행위허가는 개발규모(면적 상한)·경사도·연접개발(누적 개발면적)·도로/배수 등 "
            "기반시설 기준(국토계획법 §58 개발행위허가기준)을 충족해야 허가됩니다.",
            "토지형질변경(절토·성토·정지·포장)이 수반되면 함께 허가받아야 합니다.",
            "★개발가능 여부·규모는 개발행위허가 판정을 전제로 한 값입니다(밀도한도만으로 단정하지 않습니다).",
        ],
        "legal_basis": [
            "국토의 계획 및 이용에 관한 법률 제56조(개발행위의 허가)",
            "국토의 계획 및 이용에 관한 법률 제58조(개발행위허가의 기준)",
        ],
        "legal_ref_keys": ["dev_act_permit", "dev_act_criteria", "land_form_change"],
        "permit_prerequisites": [
            "개발행위허가(국토계획법 §56)·토지형질변경 병행 필요",
            "개발행위허가기준(§58) 충족 확인 — 규모 상한·평균경사도·연접개발·도로/배수 기반시설",
        ],
        "caveat": (
            "도시지역 내 녹지는 건축 전 개발행위허가(규모·경사도·연접개발·도로/배수 기준) "
            "선행/병행 필요. 개발가능 여부는 개발행위허가 판정 전제."
        ),
    }


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
        # ─────────────────────────────────────────────────────────────────
        # P2 구역 규칙(additive) — 위 기존 4개 규칙·등급은 절대 불변, 아래는 가산 전용.
        #   등급 선택의 법적 근거(보수적):
        #     · 법률상 '원칙 금지/행위제한'형 구역(허가로 통상 해소 불가) → PRECONDITION
        #     · '허가·협의·조사 통과 시 가능'형 → CONDITIONAL
        #     · '계획 부합 시 통상 허가(완화 혜택 병존)'형 → CAUTION
        #   오탐 방어: 광역 단어('상수원'·'수변' 등) 대신 구역명 명시 키워드('상수원보호'·'수변구역')만 매칭.
        #   ★기존 광역 키워드 규칙(상수원/수변/군사/문화재)과 중복 발동 가능 — 종합 게이트는 _RANK
        #   최댓값 병합이라 등급 상향(①⑧) 또는 동급 유지(②③)이며 기존 규칙 산출은 그대로 보존된다.
        #   legal_ref_keys: 레지스트리 기존 키(buried_heritage·steep_slope_disaster·cultural_heritage)
        #   재사용 + B-registry 추가 예정 키(문자열 참조 — get_legal_refs가 미존재 키는 건너뛰어 안전).
        # ─────────────────────────────────────────────────────────────────
        # ① 상수원보호구역 — 수도법 제7조: 구역 내 건축물 신축·증개축 등 원칙 금지(제한적 예외만
        #   허가·신고). '원칙 행위제한'형이라 CONDITIONAL이 아닌 PRECONDITION(구역 변경·해제 또는
        #   예외 해당이 선행돼야 일반 개발 가능).
        (("상수원보호",), {"category": "상수원보호구역(수도법 원칙 행위제한)", "developability": "PRECONDITION",
            "implications": [
                "상수원보호구역으로 지정되어 수도법 제7조에 따라 건축물 신축·증개축, 공작물 설치 등 "
                "개발행위가 원칙적으로 금지됩니다(제한적 예외만 허가·신고).",
                "일반 분양개발은 보호구역 변경·해제 또는 예외 허가대상 해당이 선행되어야 하며, "
                "통상 개별 사업으로 해소되지 않습니다.",
                "세부 행위제한·구역 경계는 관할 지자체(환경부서)·수도사업자 확인이 필수입니다.",
            ],
            "legal_basis": ["수도법 제7조(상수원보호구역 지정 등 — 구역 내 행위제한)"],
            "legal_ref_keys": ["water_source_protection"],
            "permit_prerequisites": ["상수원보호구역 지정·경계 열람(토지이용계획확인원)",
                                     "예외 허가·신고 대상 행위 해당 여부 확인(관할 지자체)"]}),
        # ② 군사기지·군사시설 보호구역 — 군사기지 및 군사시설 보호법: 보호구역 내 건축·개발은
        #   국방부(관할부대장 등) 협의 대상. 협의 통과 시 가능한 '협의형'이라 CONDITIONAL.
        (("군사기지", "군사시설보호"), {"category": "군사기지·군사시설 보호구역(국방부 협의)",
            "developability": "CONDITIONAL",
            "implications": [
                "군사기지 및 군사시설 보호법상 보호구역(통제보호구역·제한보호구역·비행안전구역 등)으로, "
                "건축·개발 시 국방부(관할부대장 등) 협의가 선행됩니다.",
                "통제보호구역은 사실상 개발이 곤란하고, 제한보호구역·비행안전구역은 고도·용도 제한 협의 "
                "결과에 따라 달라집니다.",
                "세부 행위제한(구역 종류·고도기준)은 관할 지자체·관할부대 확인이 필수입니다.",
            ],
            "legal_basis": ["군사기지 및 군사시설 보호법(보호구역 내 행위 협의)"],
            "legal_ref_keys": ["military_protection_zone"],
            "permit_prerequisites": ["보호구역 종류(통제/제한/비행안전) 확인", "국방부·관할부대 협의"]}),
        # ③ 문화재보호구역·역사문화환경보존지역 — 문화유산법: 건설공사 전 현상변경 허가(허가형)
        #   → CONDITIONAL. 기존 통합 규칙(문화재/역사문화환경)과 동급이라 게이트 불변(심화 고지 가산).
        (("문화재보호구역", "역사문화환경보존"), {"category": "문화재보호구역·역사문화환경보존지역(현상변경 허가)",
            "developability": "CONDITIONAL",
            "implications": [
                "문화재(문화유산)보호구역 또는 역사문화환경보존지역으로, 건설공사 전 현상변경 허가"
                "(또는 행위 사전검토)가 필요합니다.",
                "보존지역 내 건축은 높이·형태 등 허가기준 심의 결과에 따라 제한될 수 있습니다.",
                "세부 행위제한(보존지역 범위·허가기준)은 관할 지자체·국가유산청 확인이 필수입니다.",
            ],
            "legal_basis": ["문화유산의 보존 및 활용에 관한 법률(보호구역·역사문화환경 보존지역 내 현상변경 허가)"],
            "legal_ref_keys": ["cultural_heritage", "cultural_heritage_env"],
            "permit_prerequisites": ["역사문화환경 보존지역 범위·허가기준 확인", "현상변경 허가(해당 시)"]}),
        # ④ 매장유산 유존지역·지표조사 대상 — 매장유산법: 일정 규모 이상 개발사업은 착공 전
        #   지표조사 선행(조사 통과형) → CONDITIONAL.
        (("매장유산", "매장문화재", "유존지역", "문화재 지표조사"), {"category": "매장유산 유존지역(사업 전 지표조사)",
            "developability": "CONDITIONAL",
            "implications": [
                "매장유산(매장문화재) 유존지역 또는 지표조사 대상지로, 일정 규모 이상 개발사업은 "
                "착공 전 문화재 지표조사가 선행되어야 합니다.",
                "지표조사·시굴 결과 유구가 확인되면 발굴조사·보존조치로 사업 일정·범위가 변경될 수 있습니다.",
                "세부 대상 여부(사업면적 기준)·행위제한은 관할 지자체·국가유산청 확인이 필수입니다.",
            ],
            "legal_basis": ["매장유산 보호 및 조사에 관한 법률(지표조사·발굴조사)"],
            "legal_ref_keys": ["buried_heritage"],
            "permit_prerequisites": ["매장유산 유존지역 여부·지표조사 대상 규모 확인", "문화재 지표조사(착공 전)"]}),
        # ⑤ 비오톱 1등급 — 서울특별시 도시계획 조례: 1등급 토지는 대상지 전체 보전 원칙으로
        #   개발행위허가 제한(개발 불가 소지 높음). 전국 일반화 불가(조례 운영 지자체 한정)·등급
        #   경계 정밀조사 여지가 있어 BLOCKED가 아닌 PRECONDITION + 강한 경고(보수·정직).
        #   오탐 방어: '비오톱' 단독이 아닌 '1등급' 명시에만 발동(2·3등급 오탐 차단).
        (("비오톱1등급", "비오톱 1등급"), {"category": "비오톱 1등급(개발행위 제한 — 강한 경고)",
            "developability": "PRECONDITION",
            "implications": [
                "★강한 경고: 비오톱 1등급 토지는 서울특별시 도시계획 조례상 대상지 전체 보전이 원칙으로, "
                "개발행위허가가 제한되어 개발 자체가 불가능할 소지가 높습니다.",
                "등급 경계·현장 정밀조사 결과에 따라 판정이 달라질 수 있으나, 1등급 존치 구역은 "
                "사업구역 제외가 사실상 전제됩니다.",
                "세부 행위제한·등급 경계는 관할 지자체(서울시 등 조례 운영 지자체) 확인이 필수입니다.",
            ],
            "legal_basis": ["서울특별시 도시계획 조례(비오톱 1등급 토지 — 개발행위허가 제한)"],
            "legal_ref_keys": ["biotope_grade1"],
            "permit_prerequisites": ["비오톱 등급·경계 확인(도시생태현황도)",
                                     "1등급 구역 제외·사업구역 재획정 검토"]}),
        # ⑥ 급경사지 붕괴위험지역 — 급경사지 재해예방에 관한 법률: 지정 구역 내 행위제한·안전조치.
        #   사면 안정화 대책·협의로 해소 가능한 '대책 통과형' → CONDITIONAL.
        (("급경사지", "붕괴위험지역"), {"category": "급경사지 붕괴위험지역(급경사지법)",
            "developability": "CONDITIONAL",
            "implications": [
                "급경사지 붕괴위험지역으로 지정되어 재해예방을 위한 행위제한·안전조치"
                "(정비사업·재해영향 검토)가 적용됩니다.",
                "개발 시 붕괴위험 해소 대책(사면 안정화 등)과 관계기관 협의가 선행되어야 합니다.",
                "세부 행위제한·지정 현황은 관할 지자체(재난부서) 확인이 필수입니다.",
            ],
            "legal_basis": ["급경사지 재해예방에 관한 법률(붕괴위험지역 지정·행위제한)"],
            "legal_ref_keys": ["steep_slope_disaster"],
            "permit_prerequisites": ["붕괴위험지역 지정 현황·등급 확인",
                                     "사면 안전대책·재해영향 검토(관계기관 협의)"]}),
        # ⑦ 성장관리계획구역 — 국토계획법 제75조의2(지정)·제75조의3(수립): 계획 부합 시 통상
        #   허가되고 미부합 시 제한되는 '계획 정합형'이라 CONDITIONAL보다 낮은 CAUTION(사전확인).
        #   완화 혜택(건폐율·용적률) 존재도 정직 안내(제한만 부각하지 않음 — 무날조: 구체 수치는
        #   성장관리계획·조례로 확정해야 하므로 수치 단정 금지).
        (("성장관리계획", "성장관리방안", "성장관리구역"), {"category": "성장관리계획구역(계획 부합 시 허가)",
            "developability": "CAUTION",
            "implications": [
                "성장관리계획구역(국토계획법 제75조의2·제75조의3)으로, 개발행위·건축은 성장관리계획에 "
                "부합해야 허가되며 계획에 맞지 않으면 제한됩니다.",
                "반대로 계획에 부합하면 계획관리지역 등에서 건폐율·용적률 완화 혜택이 부여될 수 있습니다"
                "(구체 완화 폭은 성장관리계획·지자체 조례로 확정).",
                "세부 행위제한·계획 내용(허용용도·기반시설 계획)은 관할 지자체 확인이 필수입니다.",
            ],
            "legal_basis": ["국토의 계획 및 이용에 관한 법률 제75조의2(성장관리계획구역의 지정 등)"
                            "·제75조의3(성장관리계획의 수립 등)"],
            "legal_ref_keys": ["growth_management_zone"],
            "permit_prerequisites": ["성장관리계획 내용(허용용도·완화 조항) 열람",
                                     "개발계획의 성장관리계획 부합 여부 확인"]}),
        # ⑧ 수변구역 — 한강수계 상수원수질개선 및 주민지원 등에 관한 법률(낙동강·금강·영산강 수계법
        #   동일 취지): 오염유발 시설 신규 입지 원칙 제한. 제한 대상이면 통상 인허가로 해소되지 않는
        #   '원칙 행위제한'형 → PRECONDITION. 오탐 방어: '수변' 단독이 아닌 '수변구역' 명시에만 발동.
        (("수변구역",), {"category": "수변구역(수계법 행위제한)", "developability": "PRECONDITION",
            "implications": [
                "수변구역(한강수계 상수원수질개선 및 주민지원 등에 관한 법률 등 4대강 수계법)으로, "
                "음식점·숙박시설·공동주택 등 오염유발 시설의 신규 입지가 원칙적으로 제한됩니다.",
                "제한 대상 시설·규모에 해당하면 통상 인허가로 해소되지 않으며, 구역 변경·해제 또는 "
                "비제한 용도로의 계획 변경이 전제됩니다.",
                "세부 행위제한(수계별·시설별)은 관할 지자체·유역환경청 확인이 필수입니다.",
            ],
            "legal_basis": ["한강수계 상수원수질개선 및 주민지원 등에 관한 법률"
                            "(수변구역 지정·행위제한 — 낙동강·금강·영산강 수계법 동일 취지)"],
            "legal_ref_keys": ["riparian_zone"],
            "permit_prerequisites": ["수변구역 지정·경계 열람", "행위제한 대상 시설(용도) 해당 여부 확인"]}),
        # ⑨ 하천구역·소하천구역 — 하천법 제33조(하천점용허가)·소하천정비법(소하천 점용): 점용허가
        #   통과 시 제한적 이용 가능한 '허가형' → CONDITIONAL. (지목 '하천'의 공공용지 BLOCKED
        #   규칙과는 별개 경로 — 구역 지정 정보 기반 가산.)
        (("하천구역", "소하천"), {"category": "하천구역·소하천구역(점용허가)", "developability": "CONDITIONAL",
            "implications": [
                "하천구역(하천법) 또는 소하천구역(소하천정비법)에 해당해, 토지 점용·공작물 설치 등에는 "
                "하천점용허가(소하천은 소하천 점용허가)가 선행됩니다.",
                "하천구역 내 건축은 원칙적으로 크게 제한되며, 점용허가는 치수·하천관리에 지장이 없는 "
                "범위에서만 가능합니다.",
                "세부 행위제한·구역 경계(하천구역선)는 관할 하천관리청 확인이 필수입니다.",
            ],
            "legal_basis": ["하천법 제33조(하천의 점용허가 등)", "소하천정비법(소하천구역 점용 등)"],
            "legal_ref_keys": ["river_occupation"],
            "permit_prerequisites": ["하천구역·소하천구역 경계 확인(하천관리청)", "하천(소하천) 점용허가"]}),
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


# ──────────────────────────────────────────────────────────────────────────
# T1/T3 — 임야(산지) 관측데이터 배선 + 예비판정(preliminary assessment).
#   SRTM 30m DEM 경사도(terrain_facts)·산림청 커넥터(forest_data)를 forest_facts에 주입하고,
#   산지관리법 시행령 별표4 기준(경사도 25도·관할평균 입목축적 150%) 대비 '예비판정'만 가산한다.
#   ★비협상(정직 게이트 보존): developability(NEEDS_OFFICIAL_SURVEY)·official_survey_required·
#   blocking_unknown은 어떤 관측값에서도 절대 완화·변경하지 않는다 — DEM은 공식 평균경사도조사서가
#   아니고 API 조회값은 공식 산림조사서가 아니므로, 확정판정은 여전히 공식조사 확보 후에만 가능하다.
# ──────────────────────────────────────────────────────────────────────────

# 산지관리법 시행령 제20조 별표4 — 산지전용허가기준의 국가기준(지자체 조례로 강화 가능):
#   평균경사도 25도 이하, ha당 입목축적이 관할 시군구 평균의 150% 이하.
_FOREST_SLOPE_DEFAULT_DEG = 25.0
_FOREST_STOCK_LIMIT_PCT = 150.0
_DEM_ACCURACY_CAVEAT = "30m DEM 근사 — 공식 평균경사도조사서 아님"

# 예비판정 라벨(계획서 T1 §3) — 기준×0.8 이하 / 기준 이하 / 기준 초과.
_PRELIM_FIT = "예비 적합 가능성"
_PRELIM_BORDER = "경계 — 공식조사 필수"
_PRELIM_EXCEED = "예비 초과 — 부적합 가능성 높음(대체부지 검토 권고)"


def _deg_to_pct(deg: float) -> float:
    """경사 도(°) → 퍼센트(%) 변환 — pct = tan(deg)×100 (예: tan(25°)≈46.6%)."""
    return math.tan(math.radians(deg)) * 100.0


def _pct_to_deg(pct: float) -> float:
    """경사 퍼센트(%) → 도(°) 변환 — deg = atan(pct/100)."""
    return math.degrees(math.atan(pct / 100.0))


def _slope_preliminary(dem_pct: float, slope_criteria: dict | None, source: str) -> dict[str, Any]:
    """DEM 평균경사도(%) vs 기준(조례 우선, 없으면 별표4 25°)의 예비판정(확정 아님).

    slope_criteria는 ordinance_service.resolve_slope_criteria(T2)의 성공 계약
    {"slope_deg": float, "ordinance_name": str, "verified": "api_parsed"} — None이면
    국가기준 25°로 폴백하고 "지자체 조례 별도 확인" 캐비앳을 부착한다(무날조).
    """
    caveats: list[str] = []
    ord_deg = _num((slope_criteria or {}).get("slope_deg"))
    if ord_deg is not None and ord_deg > 0:
        criteria_deg = float(ord_deg)
        ord_name = str(slope_criteria.get("ordinance_name") or "지자체 도시계획조례")
        criteria_source = (f"지자체 조례 기준 — {ord_name}"
                           f"(개발행위허가 경사도, verified={slope_criteria.get('verified')})")
    else:
        criteria_deg = _FOREST_SLOPE_DEFAULT_DEG
        criteria_source = "산지관리법 시행령 제20조 별표4 — 국가기준 평균경사도 25도 이하"
        caveats.append("지자체 조례가 더 엄격한 기준(예: 17.5도/20도)을 둘 수 있음 — 해당 지자체 조례 별도 확인 필요")
    criteria_pct = round(_deg_to_pct(criteria_deg), 2)
    dem_deg = round(_pct_to_deg(dem_pct), 2)
    if dem_pct <= criteria_pct * 0.8:
        judgment = _PRELIM_FIT
    elif dem_pct <= criteria_pct:
        judgment = _PRELIM_BORDER
    else:
        judgment = _PRELIM_EXCEED
    return {
        "judgment": judgment,
        "value_pct": dem_pct,
        "value_deg": dem_deg,
        "criteria_deg": criteria_deg,
        "criteria_pct": criteria_pct,
        "criteria_source": criteria_source,
        "formula": (
            f"%↔도 변환: pct = tan(도)×100 — 기준 {criteria_deg}° = tan({criteria_deg}°)×100 ≈ {criteria_pct}%. "
            f"판정: DEM {dem_pct}%(≈{dem_deg}°)를 기준×0.8({round(criteria_pct * 0.8, 2)}%)"
            f"·기준({criteria_pct}%)과 비교"
        ),
        "legal_basis": ["산지관리법 시행령 제20조(산지전용허가의 기준 등)·별표4"],
        "legal_ref_keys": ["forest_permit_criteria"],
        "source": source,
        "caveats": caveats,
        "limitations": [
            f"{_DEM_ACCURACY_CAVEAT}(확정판정 불가 — 공식조사로만 확정)",
            "예비판정은 참고용이며 developability(NEEDS_OFFICIAL_SURVEY)를 변경하지 않음",
        ],
    }


def _stocking_preliminary(stock: float, district_avg: float, source: str | None) -> dict[str, Any]:
    """ha당 입목축적 vs 관할 시군구 평균의 150% 비교(별표4) 예비판정(확정 아님)."""
    ratio = round(stock / district_avg * 100.0, 1)
    judgment = _PRELIM_FIT if ratio <= _FOREST_STOCK_LIMIT_PCT else _PRELIM_EXCEED
    return {
        "judgment": judgment,
        "입목축적_비율_pct": ratio,
        "criteria": f"관할 시군구 평균 입목축적의 {_FOREST_STOCK_LIMIT_PCT:.0f}% 이하",
        "formula": f"비율 = 필지 입목축적({stock}㎥/ha) ÷ 관할평균({district_avg}㎥/ha) × 100 = {ratio}%",
        "legal_basis": ["산지관리법 시행령 제20조 별표4(산지전용허가기준 — 임목축적)"],
        "legal_ref_keys": ["forest_permit_criteria"],
        "source": source,
        "limitations": [
            "API 조회값 — 공식 산림조사서 아님(확정판정 불가)",
            "예비판정은 참고용이며 developability(NEEDS_OFFICIAL_SURVEY)를 변경하지 않음",
        ],
    }


def _inject_forest_observations(
    factor: dict[str, Any],
    terrain_facts: dict | None,
    forest_data: dict | None,
    slope_criteria: dict | None,
) -> dict[str, Any] | None:
    """임야 요인의 forest_facts에 관측데이터(T1 DEM·T3 산림청 커넥터)를 주입하고 예비판정을 가산.

    ★게이트 불변: developability/official_survey_required/blocking_unknown은 여기서 절대 건드리지
    않는다(예비판정 필드 가산만). 값 미확보 항목은 skip+사유(무날조 — 비율·판정 날조 금지).
    """
    facts = factor.get("forest_facts")
    if not isinstance(facts, dict):
        return None

    pa: dict[str, Any] = {"slope": None, "stocking": None}

    # ── T1: DEM 평균경사도 주입 + 예비판정(조례 우선 → 별표4 25°) ──
    dem_pct = _num((terrain_facts or {}).get("평균경사도_pct"))
    if dem_pct is not None:
        src = str((terrain_facts or {}).get("source") or "SRTM30_DEM")
        facts["평균경사도_pct"] = dem_pct
        facts["경사도_source"] = src
        facts["경사도_정확도한계"] = _DEM_ACCURACY_CAVEAT
        pa["slope"] = _slope_preliminary(dem_pct, slope_criteria, src)
    else:
        pa["slope_skip_reason"] = "평균경사도(DEM terrain_facts) 미확보 — 경사도 예비판정 생략(무날조)"

    # ── T3: 산림청 커넥터 값 주입 + 별표4 150% 비교(두 값 모두 확보 시에만) ──
    if forest_data:
        stock = _num(forest_data.get("입목축적_per_ha"))
        district_avg = _num(forest_data.get("관할평균_입목축적_per_ha"))
        forest_class = forest_data.get("산지구분")
        src = forest_data.get("source")
        injected = False
        if stock is not None:
            facts["입목축적_per_ha"] = stock
            injected = True
        if district_avg is not None:
            facts["관할평균_입목축적_per_ha"] = district_avg
            injected = True
        if forest_class not in (None, ""):
            facts["산지구분"] = str(forest_class)
            injected = True
        if injected and src:
            facts["official_data_source"] = str(src)
        if stock is not None and stock < 0:
            # ★음수 입목축적은 비정상 관측값 — 비율(-x%)이 150% 이하 조건을 오통과해
            # '예비 적합'을 날조하므로 판정 생략(무날조·정직게이트 불변).
            pa["stocking_skip_reason"] = (
                f"필지 입목축적 음수({stock}㎥/ha) — 비정상 관측값으로 "
                "별표4 150% 비교 생략(무날조, 비율 날조 금지)"
            )
        elif stock is not None and district_avg is not None and district_avg > 0:
            pa["stocking"] = _stocking_preliminary(stock, district_avg, str(src) if src else None)
        else:
            missing = []
            if stock is None:
                missing.append("필지 입목축적")
            if district_avg is None or (district_avg is not None and district_avg <= 0):
                missing.append("관할평균 입목축적")
            pa["stocking_skip_reason"] = (
                "·".join(missing) + " 미확보 — 별표4 150% 비교 생략(무날조, 비율 날조 금지)"
            )
    else:
        pa["stocking_skip_reason"] = "산림청 데이터(forest_data) 미확보 — 별표4 150% 비교 생략(무날조)"

    pa["disclaimer"] = (
        "예비판정(참고용) — 확정 아님. DEM·API 조회값은 공식 평균경사도조사서·산림조사서가 아니므로 "
        "developability(NEEDS_OFFICIAL_SURVEY)는 변경되지 않으며, 확정판정은 공식조사 확보 후에만 가능합니다."
    )
    factor["preliminary_assessment"] = pa
    return pa


# ──────────────────────────────────────────────────────────────────────────
# T4 — 농지/임야 전용 부담금 존재 고지 + verified legal_ref 연결.
#   산식·법령은 land_conversion_charges(C 브리지)·legal_reference_registry(A)를 소비한다.
#   공시지가·면적이 확보된 경우에만 추정액을 산출(무날조 — 미확보 시 산식 고지만).
# ──────────────────────────────────────────────────────────────────────────

# result에서 개별공시지가(원/㎡)·면적(㎡)을 찾는 후보 키(호출부별 명칭 편차 흡수 — 없으면 None).
_PRICE_KEYS = ("official_land_price_per_m2", "official_land_price", "개별공시지가_원_per_m2", "개별공시지가")
_AREA_KEYS = ("area_sqm", "land_area_sqm", "total_area_sqm", "area")


def _first_num(result: dict, keys: tuple[str, ...]) -> float | None:
    for k in keys:
        v = _num(result.get(k))
        if v is not None and v > 0:
            return v
    return None


def _augment_charge_disclosures(factors: list[dict[str, Any]], result: dict) -> list[str]:
    """농지/임야 요인에 charge_notice(부담금 존재 고지)를 가산하고 honest_disclosure용 문장을 반환.

    legal_ref_keys는 기존 키 보존 + 가산(중복 없이) — 이후 _factor_legal_refs가 verified 링크로
    직렬화한다. 추정액은 C 브리지(land_conversion_charges) 산식으로만 산출(무날조).
    """
    sentences: list[str] = []
    price = _first_num(result, _PRICE_KEYS)
    area = _first_num(result, _AREA_KEYS)

    def _extend_keys(f: dict, keys: list[str]) -> None:
        existing = list(f.get("legal_ref_keys") or [])
        f["legal_ref_keys"] = existing + [k for k in keys if k not in existing]

    for f in factors:
        cat = str(f.get("category") or "")
        if cat.startswith("농지"):
            estimate = None
            estimate_note = "개별공시지가·전용면적 미확보 — 추정액 미산출(산식만 고지, 무날조)"
            if price is not None and area is not None:
                try:
                    from app.services.feasibility.land_conversion_charges import (
                        calc_farmland_preservation_charge,
                    )

                    estimate = calc_farmland_preservation_charge(
                        official_land_price_per_m2=price, conversion_area_m2=area)
                    estimate_note = "개별공시지가×30%(㎡당 상한 5만원)×전용면적 — 감면 미반영 추정치(확정 부과액 아님)"
                except Exception:  # noqa: BLE001 — 브리지 실패는 고지만 유지(게이트 무영향).
                    estimate = None
            f["charge_notice"] = {
                "charge_name": "농지보전부담금",
                "notice": ("농지전용허가·협의 시 농지보전부담금이 부과됩니다"
                           "(농지법 제38조 — 개별공시지가×30%, ㎡당 상한 50,000원)."),
                "formula": "농지보전부담금 = 개별공시지가 × 30% (㎡당 상한 50,000원) × 전용면적",
                "legal_ref_keys": ["farmland_preservation_charge"],
                "estimate": estimate,
                "estimate_note": estimate_note,
            }
            _extend_keys(f, ["farmland_preservation_charge", "farmland_conversion_report"])
            sentences.append("참고: 농지전용 시 농지보전부담금(농지법 제38조)이 부과됩니다.")
        elif cat.startswith("임야"):
            f["charge_notice"] = {
                "charge_name": "대체산림자원조성비",
                "notice": ("산지전용허가 시 대체산림자원조성비가 부과됩니다"
                           "(산지관리법 제19조 — (연도별 고시 단가 + 개별공시지가×1%) × 전용면적)."),
                "formula": "대체산림자원조성비 = (연도별 고시 단가[원/㎡] + 개별공시지가 × 1%) × 전용면적",
                "legal_ref_keys": ["forest_replacement_charge"],
                # 연도별 고시 단가(산림청 고시)는 명시 주입 전용(무날조) — 미주입이므로 추정액 없음.
                "estimate": None,
                "estimate_note": ("연도별 고시 단가(산림청 '대체산림자원조성비 부과기준' 고시) 미주입 — "
                                  "추정액 미산출(산식만 고지, 무날조)"),
            }
            _extend_keys(f, ["forest_replacement_charge", "forest_land_classification"])
            sentences.append("참고: 산지전용 시 대체산림자원조성비(산지관리법 제19조)가 부과됩니다.")
    return sentences


def detect_special_parcel(
    result: dict,
    *,
    terrain_facts: dict | None = None,
    forest_data: dict | None = None,
    slope_criteria: dict | None = None,
) -> dict[str, Any] | None:
    """부지분석 결과(result)에서 특이부지 요인을 종합 판정. 특이 없으면 None.

    반환: {is_special, developability(종합 게이트), severity_label, factors[...],
           warnings[...], development_caveat} — 모두 추가(additive) 필드.

    additive 옵션 인자(기본 None=현행 동작 100% 보존 — 기존 호출부 무수정 호환):
      terrain_facts   {"평균경사도_pct": float, "최대경사도_pct": float, "source": "SRTM30_DEM"}
                      — terrain_service DEM 산출(T1). 임야 요인 forest_facts에 주입+예비판정.
      forest_data     get_forest_facts(pnu) 계약(T3) — {"입목축적_per_ha", "관할평균_입목축적_per_ha",
                      "산지구분", "source"}. 두 값 확보 시에만 별표4 150% 비교.
      slope_criteria  resolve_slope_criteria(sigungu) 계약(T2) — {"slope_deg", "ordinance_name",
                      "verified"}. 경사도 예비판정 기준으로 조례값 우선 사용(없으면 별표4 25°).
    ★관측데이터가 주입돼도 developability(NEEDS_OFFICIAL_SURVEY)는 절대 완화되지 않는다(예비판정만).
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
    # 개발행위허가 게이트(도시지역 녹지) — 지목·면적 무관, zone_type이 녹지계열이면 발동.
    #   자연/생산녹지=CONDITIONAL, 보전녹지=PRECONDITION(원칙적 제한). 그 외 zone은 None(과탐 방지).
    fdev = _rule_by_dev_act_permit(result)
    if fdev:
        factors.append(fdev)
    # 규모·입지 임계 기반 선행절차 규제(소방 PBD·도로법 접도/연결·하수도 원인자부담·소규모 환경영향평가).
    #   기존 지목/구역/접도 요인과 동일 구조로 가산(임계 미만/미상이면 아무것도 추가 안 함).
    factors.extend(_rules_by_regulation_thresholds(result))

    mismatch = _zone_category_mismatch(land_category, zone_type)

    if not factors:
        return None  # 일상적 개발부지 — 특이 없음(정직)

    # ── T1/T3: 관측데이터(DEM·산림청 커넥터) 주입 + 예비판정 — 임야 요인에만, 제공 시에만
    #    (미제공이면 현행과 바이트 단위 동일 — 회귀 0). ★게이트(developability)는 절대 불변. ──
    forest_pa: dict[str, Any] | None = None
    if terrain_facts or forest_data:
        for f in factors:
            if isinstance(f.get("forest_facts"), dict):
                forest_pa = _inject_forest_observations(f, terrain_facts, forest_data, slope_criteria)
                break

    # ── T4: 농지/임야 전용 부담금 존재 고지 + legal_ref 가산(직렬화 前에 키 확장) ──
    charge_sentences = _augment_charge_disclosures(factors, result)

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

    # T4: 농지/임야는 전용 부담금 존재를 honest_disclosure에 명시 고지(가산 — 기존 문구 보존).
    if charge_sentences:
        honest = honest + " " + " ".join(charge_sentences)

    out: dict[str, Any] = {
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
    # T1/T3 예비판정(참고용)이 산출된 경우에만 최상위에도 노출(additive — 미제공 시 키 자체 없음).
    if forest_pa is not None:
        out["forest_preliminary_assessment"] = forest_pa
    return out


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
    # ── P2: 하천구역·소하천(점용허가형) — 공공용지(지목 하천)의 용도폐지 분기와 해결경로가
    #   다르므로 먼저 분기한다. 기존 지목 규칙 category("공공·기반시설 용지(…)")를 가로채지
    #   않도록 '공공' 접두는 제외(기존 규칙 산출 절대 불변).
    if ("하천구역" in c or "소하천" in c) and not c.startswith("공공"):
        return {"resolvable": "CONDITIONAL",
                "resolution_paths": ["하천(소하천) 점용허가 취득(하천관리청)",
                                     "치수·하천관리에 지장 없는 범위로 계획 조정"],
                "alternatives": ["하천구역선 밖으로 배치 조정", "해당 구역 제외·사업구역 재획정"]}
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
    # ── 개발행위허가(도시지역 녹지) — 개발행위허가·형질변경으로 해결(보전녹지는 조건부·좁음) ──
    if "개발행위허가" in c:
        # 보전녹지(PRECONDITION)는 원칙적 제한이라 CONDITIONAL(조건부·통상 어려움)로,
        #   자연/생산녹지(CONDITIONAL)는 개발행위허가 통과로 해결 가능(전용·부담금형 YES).
        cond = developability == "PRECONDITION"
        return {"resolvable": "CONDITIONAL" if cond else "YES",
                "resolution_paths": [
                    "개발행위허가(국토계획법 §56) 신청·취득(규모·경사도·연접·기반시설 기준 충족)",
                    "토지형질변경 병행 허가(절토·성토·정지·포장)",
                    "개발행위허가기준(§58) 충족 — 도로/배수 등 기반시설 확보",
                ],
                "alternatives": [
                    "허용 규모·경사도 이내로 개발계획 조정(부분개발)",
                    "개발행위허가 비용·기반시설 부담을 사업수지에 반영",
                ] + (["보전녹지는 개발이 원칙 제한 — 허용용도(별표15) 중심 계획 또는 구역 외 대체부지 검토"]
                     if cond else [])}
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
    # ── P2 구역 규칙 해결경로(additive) — 기존 category 어디에도 없는 신규 키워드만 사용해
    #   기존 규칙의 resolution 산출을 절대 가로채지 않는다. ──
    if "비오톱" in c:
        # 1등급은 조례상 원칙 보전 — 등급 해제·변경은 개별 사업자가 좌우할 수 없음(조건부·좁음).
        return {"resolvable": "CONDITIONAL",
                "resolution_paths": ["비오톱 등급·경계 정밀 확인(도시생태현황도·현장조사)",
                                     "1등급 존치 구역 제외 후 잔여 부지 계획"],
                "alternatives": ["사업구역 재획정(1등급 구역 제외)", "대체부지 검토"]}
    if "매장유산" in c:
        return {"resolvable": "CONDITIONAL",
                "resolution_paths": ["문화재 지표조사(착공 전)", "유구 확인 시 발굴조사·보존조치 협의"],
                "alternatives": ["조사결과 반영 설계 변경", "유존 구역 회피 배치"]}
    if "급경사지" in c or "붕괴위험" in c:
        return {"resolvable": "CONDITIONAL",
                "resolution_paths": ["사면 안정화 등 붕괴위험 해소 대책 수립", "관할 지자체(재난부서) 협의"],
                "alternatives": ["위험구역 회피 배치", "정비사업 완료 후 단계적 개발"]}
    if "성장관리" in c:
        # 계획 부합 시 통상 허가되는 '계획 정합형' — 표준 절차로 해결 가능(YES).
        return {"resolvable": "YES",
                "resolution_paths": ["성장관리계획 부합 여부 확인·계획 정합 설계",
                                     "부합 시 통상 개발행위허가 절차 진행"],
                "alternatives": ["계획 부합 범위로 용도·규모 조정", "완화 혜택(건폐율·용적률) 활용 검토"]}
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


# ──────────────────────────────────────────────────────────────────────────
# S3-A — 국계법 제84조 걸침(혼재) 규정(zone_straddle_ruling).
#
# ★조문 인용(무날조 — 2026-07-03 법제처 국가법령정보센터 검색결과·casenote 원문 대조 확인.
#   확신도: 내용 구조·수치(330/660㎡)·적용방식은 '상(확인됨)', 아래 문구 중 따옴표 부분은
#   원문 그대로, 그 외는 확인된 요지):
#
# 국토의 계획 및 이용에 관한 법률 제84조(둘 이상의 용도지역·용도지구·용도구역에 걸치는
# 대지에 대한 적용 기준)
#   ① "하나의 대지가 둘 이상의 용도지역·용도지구 또는 용도구역에 걸치는 경우로서 각
#      용도지역등에 걸치는 부분 중 가장 작은 부분의 규모가 대통령령으로 정하는 규모 이하인
#      경우에는 전체 대지의 건폐율 및 용적률은 각 부분이 전체 대지 면적에서 차지하는 비율을
#      고려하여 각 용도지역등별 건폐율 및 용적률을 가중평균한 값을 적용" 하고, 그 밖의 건축
#      제한 등에 관한 사항은 그 대지 중 가장 넓은 면적이 속하는 용도지역등에 관한 규정을
#      적용한다(요지). 다만 건축물이 고도지구에 걸쳐 있는 경우에는 그 건축물 및 대지 전부에
#      고도지구 규정을 적용한다(단서 요지).
#   ② "하나의 건축물이 방화지구와 그 밖의 용도지역·용도지구 또는 용도구역에 걸쳐 있는
#      경우에는" 그 전부에 방화지구 규정을 적용하되, 방화벽으로 구획되는 경우 예외(요지).
#   ③ 하나의 대지가 녹지지역과 그 밖의 용도지역등에 걸쳐 있는 경우(가장 작은 부분이
#      녹지지역으로서 제1항의 대통령령으로 정하는 규모 이하인 경우는 제외)에는 각각의
#      용도지역등의 건축물 및 토지에 관한 규정을 적용한다(요지).
#
# 같은 법 시행령 제94조(2 이상의 용도지역에 걸치는 토지에 대한 적용기준 — 확인됨):
#   법 제84조 제1항의 "대통령령으로 정하는 규모"는 330제곱미터. 다만 "도로변에 띠 모양으로
#   지정된 상업지역에 걸쳐 있는 토지의 경우에는 660제곱미터".
#
# 구현 범위(정직 고지): ①·③(건폐율·용적률·그 밖의 규정, 녹지 걸침)만 판정한다.
# ① 단서(고도지구)·②(방화지구)는 용도지구 걸침 데이터가 배선되지 않아 미평가 —
# honest_notes 로 관할 확인을 고지한다(임의 판정 금지). 660㎡ 단서의 '도로변 띠 모양
# 상업지역' 여부는 데이터로 자동판별 불가 → 옵션 플래그 주입 전용(기본 330㎡, 보수측).
# 레지스트리 근거 키: mixed_zone_rule(법 §84)·mixed_zone_rule_dec(령 §94) — 기존 키 재사용.
# ──────────────────────────────────────────────────────────────────────────

STRADDLE_THRESHOLD_SQM = 330.0                       # 령 §94 본문
STRADDLE_THRESHOLD_ROADSIDE_COMMERCIAL_SQM = 660.0   # 령 §94 단서(도로변 띠 모양 상업지역)
STRADDLE_RULE_WEIGHTED_AVERAGE = "가중평균+과반"        # §84① — 건폐·용적 가중평균 + 그 밖은 최광부분
STRADDLE_RULE_EACH_PART = "부분별각각"                  # 초과형·§84③ 녹지 걸침 — 부분별 각각 적용


def _zone_straddle_ruling(
    zone_area: dict[str, float],
    *,
    roadside_strip_commercial: bool = False,
) -> dict[str, Any]:
    """§84 걸침 판정(순수함수) — zone별 면적 맵에서 적용규정을 도출한다.

    반환: {straddle, applied_rule, threshold_sqm, threshold_basis, roadside_strip_commercial,
           smallest_part, largest_part, green_zone_rule_applied, per_zone_breakdown,
           bcr_far_treatment, other_regulations_treatment, legal_refs, rationale, honest_notes}.
    ★기존 blended_*_pct 계산에는 일절 관여하지 않는다(additive 판정 전용).
    """
    threshold = (STRADDLE_THRESHOLD_ROADSIDE_COMMERCIAL_SQM if roadside_strip_commercial
                 else STRADDLE_THRESHOLD_SQM)
    threshold_basis = ("국토계획법 시행령 제94조 — 330㎡"
                       "(도로변에 띠 모양으로 지정된 상업지역에 걸쳐 있는 토지는 660㎡)")
    real = sorted(
        ((z, a) for z, a in (zone_area or {}).items() if z != "미상" and a > 0),
        key=lambda kv: kv[1], reverse=True,
    )
    total = sum(a for _z, a in real)
    breakdown = [{"zone": z, "area_sqm": round(a, 2),
                  "share_pct": round(a / total * 100, 1) if total else None}
                 for z, a in real]
    legal_refs = _factor_legal_refs(["mixed_zone_rule", "mixed_zone_rule_dec"])
    honest_notes: list[str] = [
        "§84① 단서(고도지구)·②(방화지구) 걸침은 용도지구 데이터 미배선으로 판정하지 않았습니다 "
        "— 고도지구·방화지구 해당 여부는 관할(토지이용계획확인서)에서 별도 확인이 필요합니다.",
        "다필지 세트에 대한 §84 적용은 필지들을 '하나의 대지'(합필·일단의 대지)로 보는 전제의 "
        "판정입니다 — 합필(토지합병)·일단의 토지 인정 여부는 관할 확인이 필요합니다.",
    ]
    if not roadside_strip_commercial:
        honest_notes.append(
            "'도로변에 띠 모양으로 지정된 상업지역'(령 §94 단서, 660㎡) 해당 여부는 자동판별이 "
            "불가하여 기본 임계 330㎡를 보수 적용했습니다(해당 시 옵션 주입으로 660㎡ 적용).")
    unknown_area = (zone_area or {}).get("미상")
    if unknown_area:
        honest_notes.append("용도지역 미상 면적이 있어 걸침 판정에서 제외했습니다(공부 확보 후 재판정 필요).")

    base = {
        "threshold_sqm": threshold,
        "threshold_basis": threshold_basis,
        "roadside_strip_commercial": bool(roadside_strip_commercial),
        "per_zone_breakdown": breakdown,
        "legal_refs": legal_refs,
        "green_zone_rule_applied": False,
        "blended_metrics_note": (
            "'blended_*_pct'(면적가중 건폐·용적)는 §84① 가중평균 산식에 해당하는 값입니다 — "
            "'가중평균+과반' 적용 시 법적 적용치, '부분별각각' 적용 시 참고치."),
    }

    if len(real) < 2:
        return {
            **base,
            "straddle": False,
            "applied_rule": None,
            "smallest_part": None,
            "largest_part": ({"zone": real[0][0], "area_sqm": round(real[0][1], 2)}
                             if real else None),
            "bcr_far_treatment": "단일 용도지역 — 해당 용도지역 한도 그대로 적용(§84 미적용)",
            "other_regulations_treatment": "단일 용도지역 규정 적용",
            "rationale": "유효(면적 확보) 용도지역이 1개 이하 — §84 걸침 규정 미적용.",
            "honest_notes": honest_notes,
        }

    smallest_zone, smallest_area = real[-1]
    largest_zone, largest_area = real[0]
    greens = {z for z, _a in real if _zone_family(z) == "녹지"}
    has_green_mix = bool(greens) and len(greens) < len(real)

    if len(real) > 2:
        honest_notes.append(
            "셋 이상의 용도지역 걸침 — §84 적용은 부분 조합별 정밀 검토가 필요할 수 있어 "
            "가장 작은 부분 기준의 보수 판정입니다(관할 확인 권고).")

    green_rule_applied = False
    if has_green_mix and not (smallest_zone in greens and smallest_area <= threshold):
        # §84③ — 녹지지역 걸침은 각각 적용(가장 작은 부분이 녹지이고 임계 이하인 경우만 ①로).
        applied_rule = STRADDLE_RULE_EACH_PART
        green_rule_applied = True
        rationale = (
            f"녹지지역({'·'.join(sorted(greens))})과 그 밖의 용도지역에 걸치는 대지 — §84③에 따라 "
            "각각의 용도지역 규정을 부분별로 적용합니다(가장 작은 부분이 녹지지역으로서 임계 이하인 "
            f"경우가 아님: 가장 작은 부분={smallest_zone} {smallest_area:,.0f}㎡).")
    elif smallest_area <= threshold:
        applied_rule = STRADDLE_RULE_WEIGHTED_AVERAGE
        rationale = (
            f"가장 작은 부분({smallest_zone} {smallest_area:,.0f}㎡)이 임계 {threshold:,.0f}㎡ 이하 — "
            "§84①에 따라 전체 대지의 건폐율·용적률은 면적비율 가중평균을 적용하고, 그 밖의 건축 제한 "
            f"등은 가장 넓은 부분({largest_zone})의 규정을 적용합니다.")
        if has_green_mix:
            rationale += " (가장 작은 부분이 녹지지역으로서 임계 이하 — §84③ 괄호 예외로 ① 적용.)"
    else:
        applied_rule = STRADDLE_RULE_EACH_PART
        rationale = (
            f"가장 작은 부분({smallest_zone} {smallest_area:,.0f}㎡)이 임계 {threshold:,.0f}㎡ 초과 — "
            "§84① 요건 불충족으로 각 부분별로 해당 용도지역 규정을 각각 적용합니다(사실상 분리 검토).")

    if applied_rule == STRADDLE_RULE_EACH_PART:
        honest_notes.append(
            "부분별각각 적용 — 면적가중(blended) 건폐·용적 지표는 법적 적용치가 아닌 참고치입니다. "
            "부분별 개별 성립성(각 부분 한도·건축제한)을 확인하십시오.")
        bcr_far_treatment = "각 부분별 해당 용도지역의 건폐율·용적률을 각각 적용(통합 가중평균 아님)"
        other_treatment = "각 부분별 해당 용도지역 규정을 각각 적용"
    else:
        bcr_far_treatment = "전체 대지에 대해 용도지역별 건폐율·용적률의 면적비율 가중평균 적용(§84①)"
        other_treatment = f"그 밖의 건축 제한 등은 가장 넓은 부분({largest_zone})의 규정 적용(§84①)"

    return {
        **base,
        "straddle": True,
        "applied_rule": applied_rule,
        "smallest_part": {"zone": smallest_zone, "area_sqm": round(smallest_area, 2)},
        "largest_part": {"zone": largest_zone, "area_sqm": round(largest_area, 2)},
        "green_zone_rule_applied": green_rule_applied,
        "bcr_far_treatment": bcr_far_treatment,
        "other_regulations_treatment": other_treatment,
        "rationale": rationale,
        "honest_notes": honest_notes,
    }


def _aggregate_integrated_zoning(
    enriched: list[dict], *, roadside_strip_commercial: bool = False,
) -> dict[str, Any]:
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
           integrated_gfa_sqm, integrated_footprint_sqm, gfa_basis, far_basis_note, warnings,
           zone_straddle_ruling(S3-A additive — §84 걸침 적용규정 판정)}.
    미확보·산출불가 항목은 null(무목업) + warnings에 정직 기재.
    ★additive: roadside_strip_commercial(령 §94 단서 660㎡ 임계, 기본 False=330㎡)와
      zone_straddle_ruling 키만 추가 — 기존 키·산식은 전부 불변(blended_*는 §84① 가중평균
      산식에 해당하며, '부분별각각' 판정 시 참고치임을 ruling이 라벨로 정확화한다).
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
        # S3-A additive — §84 걸침(혼재) 적용규정 판정(기존 키·산식 불변, 판정 전용).
        "zone_straddle_ruling": _zone_straddle_ruling(
            zone_area, roadside_strip_commercial=roadside_strip_commercial),
    }


def _multi_parcel_addons(
    parcels: list[dict],
    per: list[dict[str, Any]],
    blocking: list[dict[str, Any]],
    refresh_fn,
    roadside_strip_commercial: bool,
) -> dict[str, Any]:
    """W1 합류(S3-B/C·S4·S5) — detect_multi_parcel 반환에 additive 로 붙는 키들을 조립한다.

    usable_area(3계층)·area_verification(면적 3원 교차검증)·zone_straddle_ruling(§84)·
    senior_review(합필 정량평가)·exclusion_scenario(차단 전부 제외 what-if — 제외 후 통합한도는
    remaining 으로 _aggregate_integrated_zoning 재실행). 전부 순수·결정론(refresh_fn 주입 시에만
    재보강 콜백 실행). 기존 detect_multi_parcel 키에는 일절 관여하지 않는다.
    """
    # 순환 임포트 방지(usable_area 모듈 docstring 계약)·지연 로딩 — 함수 내 임포트.
    from app.services.land_intelligence.parcel_verification import verify_parcel_areas
    from app.services.senior_agents.evaluators.land_assembly import evaluate_land_assembly
    from app.services.zoning.usable_area import compute_usable_area, simulate_exclusion

    items = list(parcels or [])

    # ── S3-B: 실사용가능용지 3계층(per_parcel 은 area_sqm·special 을 이미 가짐) ──
    usable = compute_usable_area(per)

    # ── S4: 면적 3원 교차검증(원본 parcel dict 기준 — geometry·입력면적 신호 포함) ──
    verification = verify_parcel_areas(items, refresh_fn)

    # ── S3-A: §84 걸침 판정(zone별 면적 맵 — _AREA_KEYS 관례로 면적 탐색) ──
    zone_area: dict[str, float] = {}
    for p in items:
        z = (p.get("zone_type") or "").strip() or "미상"
        a = _first_num(p, _AREA_KEYS) or 0.0
        zone_area[z] = zone_area.get(z, 0.0) + a
    ruling = _zone_straddle_ruling(zone_area, roadside_strip_commercial=roadside_strip_commercial)

    # ── S5: 시니어 정량평가 입력 — blocked_sqm 은 게이트(BLOCKED/NO) 사유 제외분만
    #   (도로·구거 등 지목 제외분과 구분 — 평가기의 보수 대체 폴백을 쓰지 않고 정밀값 주입). ──
    blocked_sqm = 0.0
    for e in usable.get("excluded_parcels") or []:
        codes = {r.get("code") for r in e.get("reasons") or []}
        if codes & {"developability_blocked", "resolvable_no"} and e.get("area_sqm") is not None:
            blocked_sqm += e["area_sqm"]
    senior_evals = evaluate_land_assembly({
        "gross_sqm": usable["gross_sqm"],
        "usable_confirmed_sqm": usable["usable_confirmed_sqm"],
        "usable_conditional_sqm": usable["usable_conditional_sqm"],
        "excluded_sqm": usable["excluded_sqm"],
        "blocked_sqm": round(blocked_sqm, 2),
        "unverified_parcel_count": verification["discrepancy_count"],
        "zone_straddle": ruling["straddle"],
        "straddle_applied_rule": ruling["applied_rule"],
    })
    senior_review = [ev.to_dict() for ev in senior_evals]

    # ── S3-C: 추천 제외 시나리오(차단 전부 제외안) — 차단필지 있을 때만 1건 동반 ──
    scenario: dict[str, Any] | None = None
    if blocking:
        pnus = [str(b["pnu"]) for b in blocking if b.get("pnu")]
        sim = simulate_exclusion(items, pnus)
        remaining = sim["remaining_parcels"]
        # 원본 dict 리스트(내부 _far_eff 등 포함)는 응답에 싣지 않는다 — 비대·내부키 누출 방지.
        scenario = {k: v for k, v in sim.items() if k != "remaining_parcels"}
        scenario["scenario"] = "차단(해결불가) 필지 전부 제외안 — 추천 what-if"
        scenario["integrated_zoning_after_exclusion"] = _aggregate_integrated_zoning(
            remaining, roadside_strip_commercial=roadside_strip_commercial)
        unmatched = len(blocking) - len(pnus)
        if unmatched:
            scenario["note_unmatched"] = (
                f"차단필지 {unmatched}건은 pnu 미확보로 제외안에서 식별하지 못했습니다"
                "(공부 pnu 확보 후 재산정 필요).")

    return {
        "usable_area": usable,
        "area_verification": verification,
        "zone_straddle_ruling": ruling,
        "senior_review": senior_review,
        "exclusion_scenario": scenario,
    }


def detect_multi_parcel(
    parcels: list[dict],
    *,
    refresh_fn=None,
    roadside_strip_commercial: bool = False,
) -> dict[str, Any]:
    """다필지 종합 특이부지 판정 — 한 필지의 특이성이 사업 전체를 제약할 수 있으므로,
    필지별 감지 후 가장 제약 큰 게이트로 사업 전체를 판정하고, 차단필지·대안을 도출한다.

    parcels: 각 원소는 부지분석 result dict(또는 최소 land_category/zone_type/pnu 포함).

    additive(계획서 S3~S5 합류 — 기존 반환 키 전부 불변):
      per_parcel[].area_sqm — 공부 면적(_AREA_KEYS 관례, 미확보 None).
      usable_area           — 실사용가능용지 3계층(compute_usable_area).
      area_verification     — 면적 3원 교차검증(verify_parcel_areas; refresh_fn 주입 시
                              괴리 필지 1회 재보강 — 자동 보정 없음·원본 불변).
      zone_straddle_ruling  — §84 걸침 적용규정 판정.
      senior_review         — 합필 정량평가(evaluate_land_assembly → to_dict 리스트).
      exclusion_scenario    — 차단필지 전부 제외 what-if(제외 후 통합한도 재산정 동반) | None.
    """
    per: list[dict[str, Any]] = []
    for i, p in enumerate(parcels or []):
        sp = detect_special_parcel(p)
        per.append({
            "index": i, "pnu": p.get("pnu"), "address": p.get("address"),
            "land_category": p.get("land_category"),
            "area_sqm": _first_num(p, _AREA_KEYS),  # additive — usable 3계층·matrix 재료
            "special": sp,  # None 이면 일상필지
        })

    specials = [x for x in per if x["special"]]
    if not specials:
        out = {"parcel_count": len(per), "special_count": 0, "developability": "POSSIBLE",
               "resolvable": "YES", "blocking_parcels": [], "per_parcel": per,
               "honest_disclosure": "전 필지가 일상적 개발부지로 특이 제약이 없습니다.",
               "summary": f"{len(per)}개 필지 모두 특이사항 없음 — 통상 개발 가능."}
        out.update(_multi_parcel_addons(parcels, per, [], refresh_fn, roadside_strip_commercial))
        return out

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

    out = {
        "parcel_count": len(per), "special_count": len(specials),
        "developability": gate, "resolvable": resolvable,
        "blocking_parcels": blocking, "per_parcel": per,
        "honest_disclosure": disclosure, "recommendation": recommendation,
        "note": "다필지 종합 — 가장 제약 큰 필지가 사업 전체를 좌우(연결개발 전제). 비인접/제외 시 잔여로 재산정.",
    }
    out.update(_multi_parcel_addons(parcels, per, blocking, refresh_fn, roadside_strip_commercial))
    return out


# 시니어 판정 심각도(worst 집계용) — evaluators/base 의 PASS/WARN/BLOCK 서열과 동일 계약.
_SENIOR_SEVERITY = {"PASS": 0, "WARN": 1, "BLOCK": 2}


def build_multi_parcel_report(
    parcels: list[dict],
    *,
    refresh_fn=None,
    roadside_strip_commercial: bool = False,
) -> dict[str, Any]:
    """다필지 통합분석 최종 보고(S5 계약) — 순수 조립(결정론, refresh_fn 주입 시에만 콜백).

    반환:
      report_type            "multi_parcel_report"
      parcel_count           필지 수
      matrix                 필지×속성×판정 행렬 — [{index, pnu, address, land_category,
                             zone_type, area_sqm, developability, resolvable, gate(BLOCK/
                             TENTATIVE/PASS), usable_tier(confirmed|conditional|excluded),
                             verification_status(consistent|discrepancy|insufficient),
                             factor_categories[]}]
      usable_area            실사용가능용지 3계층(compute_usable_area 결과 그대로)
      zone_straddle_ruling   §84 걸침 적용규정 판정(근거 legal_refs·honest_notes 동반)
      integrated_zoning      _aggregate_integrated_zoning(전 필지) — 통합 한도·혼재 경고
      charges                {per_parcel[{index,pnu,charge_name,amount_won,estimate_note,
                             formula,legal_ref_keys}], total_estimated_won(전부 미산출이면
                             None — 0 날조 금지), estimated: True, unestimated_count,
                             basis, honest_note} — 필지별 charge_notice 합산(추정)
      verification           면적 3원 교차검증(verify_parcel_areas 결과 그대로)
      senior_review          합필 정량평가 to_dict 리스트(근거·임계 동반)
      senior_verdict         시니어 최악 판정(PASS|WARN|BLOCK) | None(평가 없음)
      exclusion_scenario     차단필지 전부 제외 what-if(제외 후 통합한도 재산정) | None
      developability/resolvable/blocking_parcels/honest_disclosure/recommendation
                             detect_multi_parcel 종합 게이트 미러(SSOT 동일값)
      honest_limitations     정직 한계 고지 목록(중복 제거)
      basis                  조립 근거 설명
    ★모든 수치는 하위 산출물의 근거(법령 ref·산식·한계)를 그대로 동반한다(설명가능성 기본화).
    """
    items = list(parcels or [])
    detection = detect_multi_parcel(
        items, refresh_fn=refresh_fn, roadside_strip_commercial=roadside_strip_commercial)
    integrated = _aggregate_integrated_zoning(
        items, roadside_strip_commercial=roadside_strip_commercial)
    usable = detection["usable_area"]
    verification = detection["area_verification"]
    ruling = detection["zone_straddle_ruling"]

    # ── matrix: 필지×속성×판정 ──
    tier_by_index: dict[Any, str] = {}
    for tier, entries in (("confirmed", usable.get("confirmed_parcels")),
                          ("conditional", usable.get("conditional_parcels")),
                          ("excluded", usable.get("excluded_parcels"))):
        for e in entries or []:
            tier_by_index[e.get("index")] = tier
    ver_by_index = {e.get("index"): e.get("status")
                    for e in verification.get("per_parcel") or []}
    matrix: list[dict[str, Any]] = []
    for x in detection["per_parcel"]:
        i = x.get("index")
        src = items[i] if isinstance(i, int) and 0 <= i < len(items) else {}
        sp = x.get("special") if isinstance(x.get("special"), dict) else {}
        dev = sp.get("developability") or "POSSIBLE"
        res = sp.get("resolvable") or "YES"
        matrix.append({
            "index": i, "pnu": x.get("pnu"), "address": x.get("address"),
            "land_category": x.get("land_category"),
            "zone_type": src.get("zone_type"),
            "area_sqm": x.get("area_sqm"),
            "developability": dev, "resolvable": res,
            "gate": gate_decision(dev, res),
            "usable_tier": tier_by_index.get(i),
            "verification_status": ver_by_index.get(i),
            "factor_categories": [f.get("category") for f in sp.get("factors") or []
                                  if f.get("category")],
        })

    # ── charges 통합 합산: 필지별 charge_notice(추정) 합 — 미산출은 합산 제외+명세(무날조) ──
    charge_rows: list[dict[str, Any]] = []
    total = 0.0
    has_estimate = False
    unestimated = 0
    for x in detection["per_parcel"]:
        sp = x.get("special") if isinstance(x.get("special"), dict) else {}
        for f in sp.get("factors") or []:
            cn = f.get("charge_notice")
            if not cn:
                continue
            amount = ((cn.get("estimate") or {}).get("amount_won")
                      if isinstance(cn.get("estimate"), dict) else None)
            charge_rows.append({
                "index": x.get("index"), "pnu": x.get("pnu"),
                "charge_name": cn.get("charge_name"),
                "amount_won": amount,
                "estimate_note": cn.get("estimate_note"),
                "formula": cn.get("formula"),
                "legal_ref_keys": cn.get("legal_ref_keys"),
            })
            if amount is not None:
                total += amount
                has_estimate = True
            else:
                unestimated += 1
    charges = {
        "per_parcel": charge_rows,
        "total_estimated_won": round(total, 2) if has_estimate else None,
        "estimated": True,
        "unestimated_count": unestimated,
        "basis": ("필지별 charge_notice(농지보전부담금·대체산림자원조성비 등) 추정액 합산 — "
                  "개별 산식·법령 근거는 각 행의 formula·legal_ref_keys 참조"),
        "honest_note": ("합산액은 감면·부과시점 미반영 추정치로 확정 부과액 아님. 추정액 미산출 "
                        "항목(unestimated_count)은 합산에서 제외되어 실제 총 부담금은 이보다 "
                        "클 수 있습니다(관할청 산정으로 확정)."),
    }

    # ── senior 최악 판정 ──
    senior_review = detection["senior_review"]
    senior_verdict = (max((str(e.get("verdict")) for e in senior_review),
                          key=lambda v: _SENIOR_SEVERITY.get(v, 0))
                      if senior_review else None)

    # ── honest_limitations(중복 제거·순서 보존) ──
    limitations: list[str] = [
        "다필지 통합 지표는 대상 필지들을 하나의 사업부지(합필·일단의 대지)로 연결개발하는 "
        "전제의 산출입니다 — 합필(토지합병)·일단의 토지 인정 여부는 관할 확인이 필요합니다.",
    ]
    limitations.extend(usable.get("honest_notes") or [])
    limitations.extend(ruling.get("honest_notes") or [])
    policy_note = ((verification.get("policy") or {}).get("note") or "").strip()
    if policy_note:
        limitations.append(f"면적 3원 교차검증: {policy_note}")
    if charge_rows:
        limitations.append(charges["honest_note"])
    seen: set[str] = set()
    honest_limitations = [s for s in limitations if not (s in seen or seen.add(s))]

    return {
        "report_type": "multi_parcel_report",
        "parcel_count": detection["parcel_count"],
        "matrix": matrix,
        "usable_area": usable,
        "zone_straddle_ruling": ruling,
        "integrated_zoning": integrated,
        "charges": charges,
        "verification": verification,
        "senior_review": senior_review,
        "senior_verdict": senior_verdict,
        "exclusion_scenario": detection["exclusion_scenario"],
        "developability": detection["developability"],
        "resolvable": detection["resolvable"],
        "blocking_parcels": detection["blocking_parcels"],
        "honest_disclosure": detection["honest_disclosure"],
        "recommendation": detection.get("recommendation"),
        "honest_limitations": honest_limitations,
        "basis": ("특이부지 감지 SSOT(detect_multi_parcel) + 실사용가능용지 3계층(usable_area) + "
                  "국토계획법 §84 걸침 판정 + 면적 3원 교차검증(parcel_verification) + 합필 시니어 "
                  "정량평가(land_assembly)를 결정론으로 조립 — 모든 수치에 근거·법령·한계 동반."),
    }

