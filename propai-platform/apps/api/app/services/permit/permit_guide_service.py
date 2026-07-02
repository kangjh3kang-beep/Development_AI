"""쉬운 규제안내서 — 시설물(건축물 용도)별 인허가 절차(단계별) + 관련법령 + 제출서류.

토지이음 '규제안내서 > 쉬운 규제안내서'의 법령엔진 연계판. 건축을 하는 경우의 인허가를
 ① 계획·건축인허가 단계  ② 사업시행·공사 단계  ③ 사용·등록·신고 단계
로 나눠, 각 단계의 절차·관련법령(law.go.kr verified 링크는 legal_reference_registry 단일경유)·
제출서류를 결정론으로 제공한다. 주택류(단독·공동·다세대·다가구)는 주택법 절차를 추가한다.
무날조: 법령 링크는 레지스트리 verified만(가짜 링크 금지).
"""
from __future__ import annotations

from typing import Any

from app.services.legal.legal_reference_registry import get_legal_refs

# 시설물 → 절차 그룹. 주택류는 주택법(사업계획승인·주택공급) 절차 추가.
_HOUSING_FACILITIES = (
    "단독주택", "다중주택", "다가구주택", "공관",
    "공동주택", "아파트", "연립주택", "다세대주택", "기숙사",
)


def _facility_group(facility_type: str | None) -> str:
    f = (facility_type or "").replace(" ", "")
    if any(h in f for h in _HOUSING_FACILITIES) or "주택" in f:
        return "housing"
    return "building"


def get_permit_guide(facility_type: str = "단독주택", *, sigungu: str | None = None) -> dict[str, Any]:
    """시설물별 인허가 절차(단계별) — 절차·관련법령·제출서류. 주택류는 주택법 절차 추가."""
    group = _facility_group(facility_type)
    is_housing = group == "housing"

    # ── ① 계획·건축인허가 단계 ──
    stage1_proc = [
        {"name": "사전결정", "desc": "건축허가 신청 전, 해당 대지에 건축이 허용되는지 사전결정을 신청할 수 있습니다."},
        {"name": "건축허가", "desc": "건축·대수선·용도변경 허가신청서에 구비서류를 첨부해 허가권자에게 제출합니다."},
        {"name": "건축신고", "desc": "소규모 건축·재축·증축·대수선 등은 건축신고로도 가능합니다."},
        {"name": "용도변경", "desc": "건축물 용도를 변경하려는 경우 용도변경 허가(신고)를 받습니다."},
    ]
    stage1_keys = ["building_pre_decision", "building_permit", "building_report", "use_change"]
    stage1_docs = ["건축·대수선·용도변경 (변경)허가신청서", "건축·대수선·용도변경 (변경)신고서", "사전결정 신청서"]
    if is_housing:
        stage1_proc.append({
            "name": "주택건설(대지조성)사업계획 승인",
            "desc": "일정 규모 이상(단독 30호·공동 30세대 등)은 주택법에 따라 사업계획승인을 받습니다.",
        })
        stage1_keys.append("housing_approval")
        stage1_docs.append("[별지 제15호서식] 사업계획 (승인·변경승인) 신청서")

    # ── ② 사업시행·공사 단계 ──
    stage2_proc = [
        {"name": "공사감리", "desc": "건축주는 공사 감리자를 지정하여 공사감리를 하게 하여야 합니다."},
        {"name": "착공신고", "desc": "건축주는 허가권자에게 공사계획(착공)을 신고하여야 합니다."},
        {"name": "건축시공", "desc": "설계도서 및 허가조건에 적법하게 시공하여야 합니다."},
    ]
    stage2_keys = ["construction_supervision", "construction_start"]
    if is_housing:
        stage2_keys.append("housing_approval")
    stage2_docs = ["착공신고서"]

    # ── ③ 사용·등록·신고 단계 ──
    stage3_proc = [
        {"name": "사용승인(검사)",
         "desc": "공사 완료 후 감리완료보고서·공사완료도서 등을 첨부해 사용승인을 신청합니다."},
        {"name": "분양신고",
         "desc": "분양하려는 경우 분양신고서에 구비서류를 첨부해 허가권자에게 제출합니다(분양 대상 시)."},
    ]
    stage3_keys = ["use_permission", "building_sales_filing"]
    stage3_docs = ["사용검사(임시사용승인)신청서", "분양신고서"]
    if is_housing:
        stage3_proc.append({"name": "주택공급승인신청",
                            "desc": "입주자모집 공고 등 구비서류를 첨부해 시장·군수·구청장의 승인을 얻습니다."})
        stage3_keys.append("housing_supply_approval")

    def _stage(name: str, desc: list[str], proc, keys, docs) -> dict[str, Any]:
        return {
            "stage": name, "basic_desc": desc, "procedures": proc,
            "legal_refs": get_legal_refs(keys, sigungu=sigungu),
            "documents": docs,
        }

    stages = [
        _stage("계획·건축인허가 단계",
               ["건축법에 따라 건축허가 전 사전결정을 신청할 수 있고, 건축·대수선은 건축허가/건축신고를 받습니다.",
                "용도변경은 용도변경 허가(신고)를 받습니다."
                + (" 일정 규모 이상 주택은 주택법 사업계획승인을 받습니다." if is_housing else "")],
               stage1_proc, stage1_keys, stage1_docs),
        _stage("사업시행·공사 단계",
               ["공사감리자 지정·착공신고 후 적법하게 시공하며, 철거·멸실 시 신고가 필요합니다."],
               stage2_proc, stage2_keys, stage2_docs),
        _stage("사용·등록·신고 단계",
               ["공사 완료 후 사용승인을 신청하고, 분양·공급하려는 경우 신고·승인을 받습니다."],
               stage3_proc, stage3_keys, stage3_docs),
    ]
    return {
        "facility_type": facility_type, "group": group,
        "build_case": True, "stages": stages,
        "basis": "건축법(허가·신고·사용승인)" + ("·주택법(사업계획승인·주택공급)" if is_housing else "")
                 + " — 토지이음 쉬운 규제안내서 등가",
        "note": "실제 인허가는 시·군·구 조례·개별 입지규제에 따라 달라질 수 있어 관계기관 확인이 필요합니다.",
    }
