"""L3-C — 정성 등급화 평가(LLM, temp0/모델핀). 접지된 (사실, 기준항목) 부합도 등급화.

INV-31: 인용접지(grounding) 통과만 등급화. INV-32: temperature 0 + 모델버전 핀 + 캐싱(재현성).
INV-33: 등급만 표현, 법적 단정 금지(규칙 신설/위반 단정 안 함).
LLM은 결정론 mock(temp0 등가) — 동일 입력+스냅샷+모델 → 동일 결과.
"""
from __future__ import annotations

from app.contracts.qualitative import QualAssessment, QualGrade, QualStatus, emit
from app.core.hashing import input_hash
from app.services.qualitative.cache import QualCache, default_cache
from app.services.qualitative.rubric_grounding import RubricGrounding

_MODEL_PIN = "qual-model-v1"


class QualEvaluator:
    def __init__(
        self,
        grounding: RubricGrounding | None = None,
        cache: QualCache | None = None,
        model_version: str = _MODEL_PIN,
    ) -> None:
        self.grounding = grounding or RubricGrounding()
        self.cache = cache or default_cache()
        self.model_version = model_version
        self.temperature = 0  # temp0 핀(INV-32)

    def evaluate(self, fact: dict, snapshot: object = None, model: str | None = None) -> QualAssessment:
        model = model or self.model_version
        snap_id = getattr(snapshot, "snapshot_id", snapshot) or ""
        key = input_hash({"fact": fact, "snapshot": snap_id, "model": model})

        cached = self.cache.get(key)
        if cached is not None:
            return cached

        grounding = self.grounding.ground(fact)
        item = fact.get("feature")

        if grounding.status == QualStatus.DISCRETION_HELD:
            assessment = QualAssessment(
                item=item, status=QualStatus.DISCRETION_HELD, citation=None,
                is_grade=True, asserts_legal_verdict=False,
                snapshot_id=str(snap_id), model_version=model,
            )
        elif grounding.status == QualStatus.HELD:
            assessment = QualAssessment(
                item=item, status=QualStatus.HELD, citation=None, confidence=grounding.confidence,
                is_grade=True, asserts_legal_verdict=False,
                snapshot_id=str(snap_id), model_version=model,
            )
        else:
            assessment = QualAssessment(
                item=item, status=QualStatus.GRADED, grade=self._grade(fact),
                citation=grounding.citation, confidence=grounding.confidence,
                is_grade=True, asserts_legal_verdict=False,
                snapshot_id=str(snap_id), model_version=model,
            )

        assessment = emit(assessment)  # 인용접지 강제(INV-31)
        self.cache.put(key, assessment)
        return assessment

    @staticmethod
    def _grade(fact: dict) -> QualGrade:
        # 결정론 등급화(부합도 점수 → 등급). 법적 단정 아님(등급만).
        score = float(fact.get("compatibility", 0.5))
        if score >= 0.66:
            return QualGrade.HIGH
        if score >= 0.33:
            return QualGrade.MEDIUM
        return QualGrade.LOW
