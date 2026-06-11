from typing import Dict, List
import structlog

logger = structlog.get_logger()

class DesignReviewService:
    """AI 설계 자동 검토 피드백 (건축법 제25조)"""

    REVIEW_CHECKLIST = {
        "건폐율_준수": "건축법 제55조", "용적률_준수": "건축법 제56조",
        "이격거리_준수": "건축법 제58조", "높이제한_준수": "건축법 제60조",
        "일조권_준수": "건축법 제61조", "주차장_설치기준": "주차장법 제19조",
        "피난시설_적합": "건축법 제49조", "방화구획_적합": "건축법 제49조",
        "장애인_편의시설": "장애인복지법 제24조", "에너지절약_기준": "건축물에너지절약설계기준",
    }

    # ── 신뢰 레이어(additive): 체크/오류 항목 → 법령 레지스트리 근거키 매핑 ──
    # legal_reference_registry에 "존재가 검증된 키"만 매핑한다(할루시네이션 링크 금지).
    # 레지스트리에 없는 근거(건축법 제60조 높이제한·장애인복지법 제24조·
    # 건축물에너지절약설계기준 등)는 매핑하지 않음 → 기존 legal_basis 자유문자열(텍스트)만 유지.
    CHECKLIST_REF_KEYS = {
        "건폐율_준수": "bldg_bcr",          # 건축법 제55조
        "용적률_준수": "bldg_far",          # 건축법 제56조
        "이격거리_준수": "site_open_space",  # 건축법 제58조
        "일조권_준수": "daylight_height",    # 건축법 제61조
        "주차장_설치기준": "parking_min",    # 주차장법 제19조
        "피난시설_적합": "evacuation",       # 건축법 제49조
        "방화구획_적합": "evacuation",       # 건축법 제49조(피난·방화 동일 조문)
        # 오류 항목(errors_detected.item)도 동일 레지스트리 키로 해석한다.
        "용적률_초과": "bldg_far",
        "건폐율_초과": "bldg_bcr",
    }

    def review_design_parameters(self, design_params: Dict, zone_rules: Dict) -> Dict:
        errors, corrections = [], []
        far = design_params.get("far_applied", 0)
        bcr = design_params.get("bcr_applied", 0)
        max_far = zone_rules.get("max_far", 300)
        max_bcr = zone_rules.get("max_bcr", 60)
        if far > max_far:
            errors.append({"item": "용적률_초과", "current": far, "limit": max_far,
                           "legal_basis": "건축법 제56조", "severity": "critical"})
            corrections.append(f"용적률 {far}% -> {max_far * 0.9:.0f}%로 축소")
        if bcr > max_bcr:
            errors.append({"item": "건폐율_초과", "current": bcr, "limit": max_bcr,
                           "legal_basis": "건축법 제55조", "severity": "critical"})
            corrections.append(f"건폐율 {bcr}% -> {max_bcr * 0.9:.0f}%로 축소")
        # 오류 항목에 레지스트리 근거키를 가산(additive — 기존 키·값 불변, 프론트 매칭용).
        for e in errors:
            ref_key = self.CHECKLIST_REF_KEYS.get(e.get("item", ""))
            if ref_key:
                e.setdefault("legal_ref_key", ref_key)
        passed = [item for item in self.REVIEW_CHECKLIST if item not in [e["item"] for e in errors]]
        return {
            "review_status": "pass" if not errors else "correction_required",
            "error_count": len(errors), "errors_detected": errors,
            "correction_items": corrections, "passed_items": passed,
            "pass_rate_pct": round(len(passed) / len(self.REVIEW_CHECKLIST) * 100, 1),
            "legal_basis": "건축법 제25조",
            # 법령 원문 근거(law.go.kr 한글주소) — 레지스트리 출력만 사용(additive·graceful).
            "legal_refs": self._build_legal_refs(errors),
        }

    def _build_legal_refs(self, errors: List[Dict]) -> List[Dict]:
        """체크리스트·오류 항목의 법령 근거를 레지스트리(get_legal_refs)로 직렬화(additive).

        - 키 순서: 오류 항목 근거 우선(시정 대상 원문 확인이 1순위) → 체크리스트 순.
        - URL은 전적으로 legal_reference_registry 출력만 사용(여기서 URL 조립 금지).
        - 레지스트리 미존재/임포트 실패 등 어떤 예외에도 빈 배열로 graceful
          (기존 응답 필드는 무손상 — 하위호환).
        """
        keys: List[str] = []
        for e in errors or []:
            ref_key = self.CHECKLIST_REF_KEYS.get(e.get("item", "")) if isinstance(e, dict) else None
            if ref_key and ref_key not in keys:
                keys.append(ref_key)
        for item in self.REVIEW_CHECKLIST:
            ref_key = self.CHECKLIST_REF_KEYS.get(item)
            if ref_key and ref_key not in keys:
                keys.append(ref_key)
        if not keys:
            return []
        try:
            from app.services.legal.legal_reference_registry import get_legal_refs

            return get_legal_refs(keys)
        except Exception as e:  # noqa: BLE001
            logger.warning("설계검토 법령근거 부착 스킵", error=str(e)[:120])
            return []
