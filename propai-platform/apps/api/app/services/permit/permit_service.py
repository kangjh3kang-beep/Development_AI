"""인허가 서비스."""


PERMIT_REQUIREMENTS = {
    "building": [
        {"doc": "건축허가신청서", "required": True},
        {"doc": "설계도서", "required": True},
        {"doc": "구조안전확인서", "required": True},
        {"doc": "에너지절약계획서", "required": True},
        {"doc": "토지등기부등본", "required": True},
        {"doc": "환경영향평가서", "required": False},
    ],
    "development": [
        {"doc": "개발행위허가신청서", "required": True},
        {"doc": "사업계획서", "required": True},
        {"doc": "토지이용계획확인서", "required": True},
    ],
}


class PermitService:
    """인허가 요건 점검 서비스."""

    def check_requirements(self, permit_type: str, submitted: list[str] = None) -> dict:
        submitted = submitted or []
        reqs = PERMIT_REQUIREMENTS.get(permit_type, PERMIT_REQUIREMENTS["building"])
        required_docs = [r["doc"] for r in reqs if r["required"]]
        missing = [d for d in required_docs if d not in submitted]
        return {
            "permit_type": permit_type,
            "required_count": len(required_docs),
            "submitted_count": len(submitted),
            "missing": missing,
            "complete": len(missing) == 0,
        }
