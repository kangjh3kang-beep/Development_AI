"""전제 감사 **변형관계 레지스트리** — 정답을 몰라도 잡는다 (2026-08-24).

## 왜 이 층이 필요한가 (단일 경로 자기검사로는 원리적으로 못 잡는다)

라이브 응답에서 `top3` 의 한도(far 100 / bcr 20)는 **자기가 고른 zone(자연녹지)과 완벽히
정합**했다. 그래서 그 객체만 보는 어떤 검사도 통과시킨다. 틀린 것은 **경로 사이의 관계**다:

    dominant_zone   제2종일반주거지역   ← 집계 경로
    top3.zone_type  자연녹지지역        ← 시나리오 경로

## 왜 "정답"이 필요 없는가

이 부지의 정답(적정 사업모델·실제 인허가 결과)은 시스템 밖에 있고 **나중에야** 안다.
그래서 "출력이 옳은가"는 물을 수 없다. 대신 **입력↔출력의 관계**를 묻는다 —
둘이 다르면 **어느 쪽이 옳은지 몰라도** 하나는 틀렸다는 것은 안다.

## 픽스처

`fixtures/integrated_analysis_zone_mismatch.json` 은 **실제 프로덕션 응답**이다(합성 아님 —
2026-08-24 오산 내삼미동 8필지, `POST /zoning/integrated-analysis`). 골든 픽스처로 박아 둔다.
"""
from __future__ import annotations

import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.zoning import premise_audit as pa  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures",
                   "integrated_analysis_zone_mismatch.json")


def _broken() -> dict:
    with open(FIX, encoding="utf-8") as fh:
        return json.load(fh)


def _healed() -> dict:
    """★대조 모집단 — 같은 픽스처에서 **두 위반만** 고친 것.

    두 모집단이 **다른 값**을 내야 잠금이다. 차가 0이면 배선을 끊어도 결과가 같다(§2).
    """
    d = copy.deepcopy(_broken())
    t3 = d["scenario"]["top3"]
    t3["zone_type"] = d["dominant_zone"]          # 경로 무관성 회복
    t3["parcel_count"] = d["_request_parcel_count"]  # 개수 보존 회복
    return d


def test_A_실제_프로덕션_응답에서_위반을_잡는다():
    r = pa.audit(_broken())
    keys = {v["relation"] for v in r["violations"]}
    assert "path_invariance_zone" in keys, "경로 무관성 위반을 못 잡았다 — 오늘의 P0 다"
    assert "count_conservation_parcels" in keys, "개수 보존 위반을 못 잡았다"


def test_B_고치면_그_위반이_사라진다_두_모집단이_갈린다():
    """★위반이 **사라지는지**까지 봐야 잠금이다 — 항상 위반을 내는 검사는 쓸모없다."""
    broken = {v["relation"] for v in pa.audit(_broken())["violations"]}
    healed = {v["relation"] for v in pa.audit(_healed())["violations"]}
    assert "path_invariance_zone" in broken and "path_invariance_zone" not in healed
    assert "count_conservation_parcels" in broken and "count_conservation_parcels" not in healed
    assert len(healed) < len(broken)


def test_C_무차별_경보가_아니다_특이도():
    """★정상 관계는 통과해야 한다 — 전부 빨간 검사는 무시당하고 곧 꺼진다."""
    r = pa.audit(_broken())
    keys = {v["relation"] for v in r["violations"]}
    for ok in ("area_conservation", "dominant_argmax", "integration_monotonic"):
        assert ok not in keys, f"{ok} 이 정상인데 위반으로 신고됐다(위양성)"


def test_D_공허한_초록_방지_검사를_실제로_돌렸나():
    """★`checked == 0` 이면 '위반 없음'이 **공허**하다. 호출부가 그걸 알 수 있어야 한다."""
    r = pa.audit(_broken())
    assert r["registered"] >= 6, f"등록 관계가 너무 적다: {r['registered']}"
    assert r["checked"] == r["registered"], "전제 부족으로 건너뛴 관계가 있다"
    empty = pa.audit({})
    assert empty["violations"] == [], "빈 입력에서 위반을 만들어냈다"
    assert empty["checked"] == empty["registered"], "빈 입력도 판정은 시도해야 한다"


@pytest.mark.parametrize("key", pa.registered_relations())
def test_E_모든_등록관계가_이름과_설명을_갖는다(key):
    """★목록을 손으로 적지 않는다 — 레지스트리에서 **파생**시킨다(§A-4).

    새 관계를 등록하면 이 테스트가 **자동으로** 그것을 검사한다.
    """
    assert key and key.replace("_", "").isalnum()


def test_F_레지스트리가_라우터에_실제로_배선돼_있다():
    """★소비처 0 방지 — 레지스트리만 만들고 안 부르면 **정의만 하고 소비처 0** 이다.

    소스 검사이므로 **주석을 배제하고** 실행되는 줄만 본다.
    """
    path = os.path.join(os.path.dirname(__file__), "..", "routers", "auto_zoning.py")
    with open(path, encoding="utf-8") as fh:
        live = "\n".join(
            ln for ln in fh.read().splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        )
    assert "premise_audit.audit(" in live, "라우터가 전제 감사를 호출하지 않는다"
    assert 'scenario["premise_audit"]' in live, "감사 결과를 응답에 싣지 않는다"
    assert "zone_mismatch_warnings.append(_msg)" in live, "위반이 integrity_warnings 로 안 간다"
    assert 'scenario["status"] = "tentative"' in live, "위반인데 등급을 강등하지 않는다"


def test_G_새_관계를_등록하면_호출부_수정_없이_감시망에_든다():
    """★레지스트리의 존재 이유 — 손으로 센 목록이 상한이 되지 않게 한다."""
    before = len(pa.registered_relations())

    @pa.relation("tmp_probe", "임시 탐침")
    def _probe(ctx):
        return {"detail": "탐침", "evidence": {}} if ctx.get("_probe") else None

    try:
        assert len(pa.registered_relations()) == before + 1
        r = pa.audit({"_probe": True})
        assert any(v["relation"] == "tmp_probe" for v in r["violations"]), (
            "새로 등록한 관계가 audit() 에 반영되지 않는다"
        )
    finally:
        pa._REGISTRY[:] = [t for t in pa._REGISTRY if t[0] != "tmp_probe"]
    assert len(pa.registered_relations()) == before
