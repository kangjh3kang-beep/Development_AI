import math

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

    # ★review_design_parameters가 실제로 판정하는 항목(건폐율·용적률)만 pass/fail 대상이다.
    #   나머지 REVIEW_CHECKLIST 항목은 이 파라미터 검토 범위 밖 → not_checked로 분리(정직).
    CHECKED_ITEMS = ("건폐율_준수", "용적률_준수")

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

    def review_design_parameters(self, design_params: dict, zone_rules: dict) -> dict:
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
        # ★정직 분리(pass_rate 오도 제거): 이 파라미터 검토가 실제로 판정하는 항목은
        #   건폐율·용적률뿐이다. 종전엔 나머지 8개 체크리스트를 '검사도 안 하고' passed로
        #   합산해 pass_rate를 80%대로 부풀렸다(미검사 항목을 통과로 오도). 검사한 항목만
        #   passed/failed로 판정하고, 나머지는 not_checked로 분리한다(검사 안 한 것은 통과 아님).
        checked_items = list(self.CHECKED_ITEMS)
        err_to_check = {"용적률_초과": "용적률_준수", "건폐율_초과": "건폐율_준수"}
        failed_checks = {err_to_check.get(e["item"], e["item"]) for e in errors}
        passed = [item for item in checked_items if item not in failed_checks]
        not_checked = [item for item in self.REVIEW_CHECKLIST if item not in checked_items]
        return {
            "review_status": "pass" if not errors else "correction_required",
            "error_count": len(errors), "errors_detected": errors,
            "correction_items": corrections, "passed_items": passed,
            # 검사하지 않은 항목(일조·주차·피난·방화·장애인·에너지 등)은 별도 표기 —
            # pass_rate는 '검사한 항목(건폐율·용적률)' 기준이며 미검사 항목은 포함하지 않는다(정직).
            "checked_items": checked_items,
            "not_checked_items": not_checked,
            "pass_rate_pct": (
                round(len(passed) / len(checked_items) * 100, 1) if checked_items else None
            ),
            "legal_basis": "건축법 제25조",
            # 법령 원문 근거(law.go.kr 한글주소) — 레지스트리 출력만 사용(additive·graceful).
            "legal_refs": self._build_legal_refs(errors),
        }

    def _build_legal_refs(self, errors: list[dict]) -> list[dict]:
        """체크리스트·오류 항목의 법령 근거를 레지스트리(get_legal_refs)로 직렬화(additive).

        - 키 순서: 오류 항목 근거 우선(시정 대상 원문 확인이 1순위) → 체크리스트 순.
        - URL은 전적으로 legal_reference_registry 출력만 사용(여기서 URL 조립 금지).
        - 레지스트리 미존재/임포트 실패 등 어떤 예외에도 빈 배열로 graceful
          (기존 응답 필드는 무손상 — 하위호환).
        """
        keys: list[str] = []
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

    # ── 사례비교 결합(additive): 인근 인허가 사례 통계 대비 설계 FAR/BCR 위치 ──
    # 표본 부족·통계 미존재 시 통계 비표기(정직) — 가짜 수치 생성 금지.
    MIN_SAMPLE_FOR_STATS = 5

    def compare_with_nearby_cases(self, design_params: dict, case_summary: dict | None) -> dict:
        """설계 FAR/BCR을 인근 인허가 사례 분위(p25/p50/p75)와 비교(additive·결정론 산술, LLM 0).

        - case_summary는 호출자가 PermitCaseService.summarize 출력을 주입한다
          (이 서비스는 직접 외부호출하지 않음 — 결합도 최소).
          기대 형태: {"sample_count": int,
                      "far_stats": {"p25","p50","p75"}, "bcr_stats": {...}}
          (중첩 "far"/"bcr" 또는 평면 "far_p25" 표기도 graceful 수용).
        - case_summary None/빈값/available=False/표본 0 → {"available": False}(정직한 빈결과).
        - 표본 < MIN_SAMPLE_FOR_STATS(5) → available True지만 band="insufficient_sample",
          분위·중위편차(pp) 비표기.
        - pp = percentage point(설계값 − 사례 중위값).
        """
        empty = {
            "available": False, "sample_count": 0,
            "far_position": None, "bcr_position": None,
            "vs_median_far_pp": None, "vs_median_bcr_pp": None,
            "note": "인근 인허가 사례 없음 — 비교 생략",
        }
        if not isinstance(case_summary, dict) or not case_summary:
            return empty
        if case_summary.get("available") is False:
            return empty
        raw_count = self._to_number(case_summary.get("sample_count"))
        sample_count = int(raw_count) if raw_count is not None and raw_count > 0 else 0
        if sample_count <= 0:
            return empty

        params = design_params if isinstance(design_params, dict) else {}
        far_value = self._to_number(params.get("far_applied", params.get("far")))
        bcr_value = self._to_number(params.get("bcr_applied", params.get("bcr")))

        if sample_count < self.MIN_SAMPLE_FOR_STATS:
            insufficient = {"p25": None, "p50": None, "p75": None, "band": "insufficient_sample"}
            return {
                "available": True, "sample_count": sample_count,
                "far_position": {"value": far_value, **insufficient},
                "bcr_position": {"value": bcr_value, **insufficient},
                "vs_median_far_pp": None, "vs_median_bcr_pp": None,
                "note": f"인근 사례 {sample_count}건 — 표본 부족(<{self.MIN_SAMPLE_FOR_STATS})으로 분위 통계 비표기",
            }

        far_stats = self._extract_percentiles(case_summary, "far")
        bcr_stats = self._extract_percentiles(case_summary, "bcr")
        far_band = self._position_band(far_value, far_stats)
        bcr_band = self._position_band(bcr_value, bcr_stats)
        vs_far = (round(far_value - far_stats["p50"], 1)
                  if far_value is not None and far_stats["p50"] is not None else None)
        vs_bcr = (round(bcr_value - bcr_stats["p50"], 1)
                  if bcr_value is not None and bcr_stats["p50"] is not None else None)

        note_parts = [f"인근 인허가 사례 {sample_count}건 비교"]
        if vs_far is not None:
            note_parts.append(f"FAR 중위 대비 {vs_far:+.1f}pp({far_band})")
        if vs_bcr is not None:
            note_parts.append(f"BCR 중위 대비 {vs_bcr:+.1f}pp({bcr_band})")
        if vs_far is None and vs_bcr is None:
            note_parts.append("분위 통계 없음 — 위치 비교 비표기")
        return {
            "available": True, "sample_count": sample_count,
            "far_position": {"value": far_value, **far_stats, "band": far_band},
            "bcr_position": {"value": bcr_value, **bcr_stats, "band": bcr_band},
            "vs_median_far_pp": vs_far, "vs_median_bcr_pp": vs_bcr,
            "note": " · ".join(note_parts),
        }

    @staticmethod
    def _to_number(value) -> float | None:
        """유한 실수만 통과(bool·NaN·inf·비수치 → None) — 가짜 수치 금지."""
        if isinstance(value, bool):
            return None
        try:
            f = float(value)
        except (TypeError, ValueError):
            return None
        return f if math.isfinite(f) else None

    @classmethod
    def _extract_percentiles(cls, case_summary: dict, metric: str) -> dict[str, float | None]:
        """case_summary에서 metric(far|bcr)의 p25/p50/p75 추출 — 표기 변형 graceful 수용.

        우선순위: "{metric}_stats" 중첩 → "{metric}" 중첩 → 평면 "{metric}_p25" 등.
        미존재·비수치는 None(이후 band="insufficient_sample"로 정직 처리).
        """
        out: dict[str, float | None] = {"p25": None, "p50": None, "p75": None}
        for container_key in (f"{metric}_stats", metric):
            block = case_summary.get(container_key)
            if isinstance(block, dict):
                for p in out:
                    if out[p] is None:
                        out[p] = cls._to_number(block.get(p))
        for p in out:
            if out[p] is None:
                out[p] = cls._to_number(case_summary.get(f"{metric}_{p}"))
        return out

    @staticmethod
    def _position_band(value: float | None, stats: dict[str, float | None]) -> str:
        """분위 대비 위치 밴드(결정론). 값·분위 결손 시 insufficient_sample(정직)."""
        p25, p50, p75 = stats.get("p25"), stats.get("p50"), stats.get("p75")
        if value is None or p25 is None or p50 is None or p75 is None:
            return "insufficient_sample"
        if value < p25:
            return "below_p25"
        if value < p50:
            return "p25_p50"
        if value < p75:
            return "p50_p75"
        return "above_p75"
