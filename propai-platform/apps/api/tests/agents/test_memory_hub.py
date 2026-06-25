"""MemoryHub recall 단위테스트 — id 위조 금지(R1) + 인프라 부재 graceful.

memory_service.MemoryHubService.recall_experience 의 응답 포맷 경로를 mock 임베딩/Qdrant로
검증한다(실 인프라 불요). ★핵심: 비-UUID Qdrant point id 를 가짜 uuid4 로 날조하지 않고 스킵해
recalled_memory_ids provenance 가 실레코드만 가리키게 하는 회귀 가드. asyncio_mode=auto.
"""
from app.services.memory_hub.memory_service import MemoryHubService


class _Emb:
    """임베딩 모사 — 고정 벡터(망 왕복 없음)."""
    def embed_query(self, q):
        return [0.1] * 8


class _SP:
    """Qdrant ScoredPoint 모사(.id/.score/.payload)."""
    def __init__(self, id, score, domain="far", summary="s"):
        self.id = id
        self.score = score
        self.payload = {"domain": domain, "source_type": "agent_execution", "summary": summary}


async def test_recall_skips_non_uuid_id_no_fabrication():
    # ★위조 금지: 비-UUID point id(정수·비UUID 문자열)는 가짜 uuid4 날조 대신 스킵 → 유효 UUID만 회상
    svc = MemoryHubService()
    svc.embeddings = _Emb()

    class _Q:
        def search(self, **kw):
            return [_SP("11111111-1111-1111-1111-111111111111", 0.93),
                    _SP(12345, 0.81),                      # 정수 id → 스킵(위조 금지)
                    _SP("not-a-valid-uuid-string", 0.70)]  # 대시 있으나 비-UUID → 스킵
    svc.qdrant = _Q()
    out = await svc.recall_experience(query="x", domain="far", top_k=3)
    assert len(out) == 1   # 유효 UUID 1건만(정수·비UUID는 위조 없이 스킵)
    assert str(out[0].id) == "11111111-1111-1111-1111-111111111111"


async def test_recall_valid_uuids_pass_through():
    # 유효 UUID 는 그대로 보존(실레코드 추적 가능)
    svc = MemoryHubService()
    svc.embeddings = _Emb()

    class _Q:
        def search(self, **kw):
            return [_SP("11111111-1111-1111-1111-111111111111", 0.9),
                    _SP("22222222-2222-2222-2222-222222222222", 0.8)]
    svc.qdrant = _Q()
    out = await svc.recall_experience(query="x", domain="far", top_k=2)
    assert [str(m.id) for m in out] == ["11111111-1111-1111-1111-111111111111",
                                        "22222222-2222-2222-2222-222222222222"]


async def test_recall_empty_when_infra_unavailable():
    # 임베딩/Qdrant 미가용 시 정직 빈 회상(가짜 회상 금지)
    svc = MemoryHubService()
    svc.embeddings = None
    svc.qdrant = None
    out = await svc.recall_experience(query="x", domain="far", top_k=3)
    assert out == []
