"""INC-13 — 공급측 수집물 관계형 DB 영속(source_document / precedent_case). 멱등 upsert.

프로세스 재시작 휘발 제거·다중워커 공유. 소비 경로와 분리(공급측 전용). 출처 강제(INV-23) 보존.
테이블은 0005(r2)·0008(l4)에 존재 — 신규 마이그레이션 불필요.
"""
from __future__ import annotations

import uuid


async def persist_documents(session, documents) -> int:
    """수집 원천 문서(SourceDocument[]) → source_document upsert(doc_id 멱등). 영속 수 반환."""
    from sqlalchemy import func
    from sqlalchemy.dialects.postgresql import insert

    from app.db.models.r2_models import SourceDocumentModel as M

    if not documents:
        return 0
    for d in documents:
        tier = d.tier.value if hasattr(d.tier, "value") else str(d.tier)
        stmt = insert(M).values(
            id=uuid.uuid4(), doc_id=d.doc_id, tier=tier, uri=d.uri,
            content_hash=d.content_hash, jurisdiction=d.jurisdiction, title=d.title,
        ).on_conflict_do_update(
            index_elements=[M.doc_id],
            set_={"tier": tier, "uri": d.uri, "content_hash": d.content_hash,
                  "jurisdiction": d.jurisdiction, "title": d.title, "updated_at": func.now()},
        )
        await session.execute(stmt)
    await session.commit()
    return len(documents)


async def persist_cases(session, cases) -> int:
    """의결서 코퍼스(PrecedentCase[]) → precedent_case upsert(case_id 멱등). 출처 강제(emit, INV-23)."""
    from sqlalchemy import func
    from sqlalchemy.dialects.postgresql import insert

    from app.contracts.precedent import emit
    from app.db.models.l4_models import PrecedentCaseModel as M

    n = 0
    for c in cases:
        emit(c)  # 출처 없는 사례 금지(INV-23) — 영속 전 강제
        dtype = c.decision_type.value if c.decision_type else None
        stmt = insert(M).values(
            id=uuid.uuid4(), case_id=c.case_id, source=c.source, jurisdiction=c.jurisdiction,
            decision_type=dtype, issue_labels=list(c.issue_labels), conditions=list(c.conditions),
        ).on_conflict_do_update(
            index_elements=[M.case_id],
            set_={"source": c.source, "jurisdiction": c.jurisdiction, "decision_type": dtype,
                  "issue_labels": list(c.issue_labels), "conditions": list(c.conditions),
                  "updated_at": func.now()},
        )
        await session.execute(stmt)
        n += 1
    await session.commit()
    return n
