"""R0.5 — 시트역할 확정(L0.5). 분류기/표제란/내용 3원 합의로만 role 확정(INV-8).

- 3원 만장일치 → role 확정(isolated=False).
- 불합의(신호 결손 포함) → isolated=True, 하류 라우팅 제외.
- 분류기 vs 표제란 충돌 → flags에 "conflict" 기록.
confidence = 동의 비율(최다득표 / 유효신호수). 임의 단정 없음.
"""
from __future__ import annotations

from collections import Counter

from app.adapters.vision.sheet_classifier import SheetClassifierAdapter
from app.adapters.vision.titleblock_reader import TitleblockReader
from app.contracts.sheet_role import SheetRole, SheetRoleAssignment

_CLASSIFIER = "CLASSIFIER"
_TITLEBLOCK = "TITLEBLOCK"
_CONTENT = "CONTENT"


def _to_role(value: object) -> SheetRole | None:
    if value is None:
        return None
    if isinstance(value, SheetRole):
        return value
    try:
        return SheetRole[str(value)]
    except KeyError:
        return None


class SheetRoleResolver:
    def __init__(
        self,
        classifier: SheetClassifierAdapter | None = None,
        titleblock_reader: TitleblockReader | None = None,
    ) -> None:
        if classifier is not None:
            self.classifier = classifier
        else:
            # 설정 기반(기본 mock=AT 그린, SHEET_CLASSIFIER=vllm 시 실 VLLM·이미지 없으면 degrade).
            from app.adapters.vision.vllm_sheet_classifier import build_sheet_classifier
            self.classifier = build_sheet_classifier()
        self.titleblock_reader = titleblock_reader or TitleblockReader()

    def resolve(self, sheet: dict) -> SheetRoleAssignment:
        sheet_id = sheet.get("sheet_id", "")

        c = _to_role(self.classifier.classify(sheet))
        t = self.titleblock_reader.read_role(sheet.get("titleblock_text"))
        ct = _to_role(sheet.get("content_role"))

        signals = {_CLASSIFIER: c, _TITLEBLOCK: t, _CONTENT: ct}
        present = {k: v for k, v in signals.items() if v is not None}
        votes = list(present.values())
        provenance = {k: (v.value if v is not None else None) for k, v in signals.items()}

        flags: list[str] = []
        if c is not None and t is not None and c != t:
            flags.append("conflict")

        if not votes:
            return SheetRoleAssignment(
                sheet_id=sheet_id, role=None, isolated=True, method=list(present.keys()),
                confidence=0.0, flags=flags or ["no_signal"], provenance=provenance,
            )

        counts = Counter(votes)
        top_role, top_n = counts.most_common(1)[0]
        unanimous = len(present) == len(signals) and len(set(votes)) == 1
        confidence = top_n / len(present)

        if not unanimous and "conflict" not in flags:
            flags.append("disagreement")

        return SheetRoleAssignment(
            sheet_id=sheet_id,
            role=top_role,
            isolated=not unanimous,
            method=list(present.keys()),
            confidence=confidence,
            flags=flags,
            provenance=provenance,
        )
