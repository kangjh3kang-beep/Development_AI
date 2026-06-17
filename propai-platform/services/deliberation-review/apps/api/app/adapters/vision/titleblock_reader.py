"""R0.5 — 표제란 텍스트 → 시트역할 해석. 3원 합의의 한 축(INV-8).

키워드 매핑은 표제 명칭 규칙(법정 수치 아님). 미일치 텍스트는 None(임의 단정 금지).
"""
from __future__ import annotations

from app.contracts.sheet_role import SheetRole

# 더 구체적인 키워드를 앞에 둔다(지구단위 등).
_TITLE_KEYWORDS: tuple[tuple[str, SheetRole], ...] = (
    ("지구단위", SheetRole.DISTRICT_UNIT),
    ("배치", SheetRole.SITE),
    ("평면", SheetRole.PLAN),
    ("입면", SheetRole.ELEVATION),
    ("단면", SheetRole.SECTION),
    ("면적", SheetRole.AREA_TABLE),
    ("주차", SheetRole.PARKING),
    ("일조", SheetRole.SUNLIGHT),
)


class TitleblockReader:
    def read_role(self, text: str | None) -> SheetRole | None:
        if not text:
            return None
        for keyword, role in _TITLE_KEYWORDS:
            if keyword in text:
                return role
        return None
