"""SP6 회의방 의견교환 순수 규칙 — 본문검증·앵커/해결 루트제약·부모검증·삭제본문 은닉(결정론·부작용 0).

라우터가 본 규칙으로 입력을 검증한다. anchor·resolved는 루트(parent_id=None) 전용. 본문은 trim 후
비어있지 않고 최대 길이 이내. 삭제(soft) 댓글의 본문은 응답에서 가린다(트리 보존·정직 표기).
"""

from __future__ import annotations

from typing import Optional

MAX_COMMENT_BODY = 4000


def validate_comment_body(body: Optional[str]) -> str:
    """본문 정규화 — trim 후 비어있지 않고 MAX_COMMENT_BODY 이내. 위반은 ValueError(가짜 댓글 금지)."""
    text = (body or "").strip()
    if not text:
        raise ValueError("댓글 본문이 비어 있습니다")
    if len(text) > MAX_COMMENT_BODY:
        raise ValueError(f"댓글 본문이 너무 깁니다(최대 {MAX_COMMENT_BODY}자)")
    return text


def is_root(parent_id) -> bool:
    """루트 댓글 여부 — parent_id 없음."""
    return parent_id is None


def anchor_allowed(parent_id) -> bool:
    """anchor 허용 — 루트 전용(답변은 부모 컨텍스트 상속)."""
    return is_root(parent_id)


def resolve_allowed(parent_id) -> bool:
    """resolved 토글 허용 — 루트 전용(스레드 단위 해결)."""
    return is_root(parent_id)


def parent_is_valid(parent_status: Optional[str], parent_document_id, document_id) -> bool:
    """답변의 부모 유효성 — 부모가 active이고 동일 문서일 때만(타문서·삭제부모 금지)."""
    return parent_status == "active" and str(parent_document_id) == str(document_id)


def visible_body(status: str, body: Optional[str]) -> Optional[str]:
    """응답 본문 — 삭제(soft)된 댓글은 본문 은닉(None). active만 원문 노출(정직)."""
    return body if status == "active" else None
