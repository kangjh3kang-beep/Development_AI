"""코드리뷰 iter7 — BCR 조례(ordinance_bcr) 우선·미등록 시 시행령+caveat(FAR과 대칭)."""
from app.services.land.remaining_capacity import remaining_capacity


def test_bcr_ordinance_seoul_stricter():
    # 서울 일반상업 조례 건폐율 60%(시행령 80% 아님) — 기존 70% > 60% → 초과(과대관대 해소).
    rc = remaining_capacity("일반상업지역", 1000.0, 5000.0,
                            pnu="1111010100100010000", existing_bcr=70.0)
    assert rc["bcr_limit_pct"] == 60 and "조례" in rc["bcr_source"]
    assert rc["bcr_over_limit"] is True


def test_bcr_unregistered_falls_back_with_caveat():
    # 비서울(조례 미등록) → 시행령 상한 80 + '조례 미등록' caveat 표면화(무음 금지).
    rc = remaining_capacity("일반상업지역", 1000.0, 5000.0,
                            pnu="4111010100100010000", existing_bcr=70.0)
    assert rc["bcr_limit_pct"] == 80 and rc["bcr_source"] == "시행령 상한"
    assert rc["bcr_over_limit"] is False
    assert any("조례 미등록" in c for c in rc["rationale"]["caveats"])
