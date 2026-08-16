"""심의 결과 평면화 계약 — 화면이 읽는 필드가 봉투에 실제로 실린다.

★왜 (9차원 재감사 차원3·파이프라인):
  `/deliberation-review` 화면의 **공학지표(L3-B)·유사사례(L4)·정성평가(L3-C)** 세 섹션이
  프로덕션에서 **항상 비어** 있었다. 계산도 직렬화도 정상이고, **평면화 목록에서만 누락**됐다.

      소비처 `DeliberationResultPanel.tsx:195`  →  `result?.sim_metrics`  (최상위에서 읽음)
      `_compat_fields` 가 내보내던 것            →  complianceScore·finalStatus·findings·sections·
                                                    skipped·snapshot_id·input_hash  (세 필드 없음)

  ★대조: 형제 소비처 `DeliberationConsole.tsx:277` 은 **중첩 경로**로 읽어 정상이었다.
    같은 데이터의 두 소비처가 서로 다른 계약을 가정했고, 평면화가 **한쪽만** 만족시켰다.

★이 픽스처는 **두 모집단을 가른다** — 엔진이 값을 준 경우와 안 준 경우가 **서로 다른 결과**를
  내야 이 테스트가 배선을 잠근다(차가 0인 픽스처는 잠금이 아니다).
"""

from app.routers.deliberation import _compat_fields

# 엔진 원시 응답 형태(계약: services/deliberation-review/apps/api/app/contracts/analysis.py).
ENGINE_RESULT = {
    "report": {"sections": {"CONFIRMED": [{"id": "a"}], "BLOCKED": []}},
    "findings": [{"id": "f1"}],
    "sim_metrics": [{"name": "sunlight", "value": 3.2}],
    "precedent": {"status": "ok", "n": 7, "distribution": {"승인": 5}},
    "qualitative": [{"axis": "경관", "note": "양호"}],
}


def test_화면이_읽는_세_필드가_봉투에_실린다():
    out = _compat_fields(ENGINE_RESULT)
    assert out["sim_metrics"] == [{"name": "sunlight", "value": 3.2}]
    assert out["precedent"] == {"status": "ok", "n": 7, "distribution": {"승인": 5}}
    assert out["qualitative"] == [{"axis": "경관", "note": "양호"}]


def test_두_모집단이_갈린다():
    """★엔진이 값을 준 경우와 안 준 경우가 **다른 결과**를 내야 배선이 잠긴다.

    두 모집단의 차가 0이면 평면화를 지워도 이 테스트가 통과한다.
    """
    with_vals = _compat_fields(ENGINE_RESULT)
    without = _compat_fields({k: v for k, v in ENGINE_RESULT.items()
                              if k not in ("sim_metrics", "precedent", "qualitative")})

    assert with_vals["sim_metrics"] != without["sim_metrics"], "차가 0 — 잠금이 아니다"
    assert with_vals["precedent"] != without["precedent"], "차가 0 — 잠금이 아니다"
    assert with_vals["qualitative"] != without["qualitative"], "차가 0 — 잠금이 아니다"


def test_값이_없으면_빈_값으로_정직하게_준다():
    """★없는 것을 지어내지 않는다. 리스트는 `[]`, 단일 객체는 `None`."""
    out = _compat_fields({"report": {"sections": {}}})
    assert out["sim_metrics"] == []
    assert out["qualitative"] == []
    assert out["precedent"] is None


def test_기존_평면_필드가_회귀하지_않는다():
    """★추가가 기존 계약을 깨지 않는지 — 종전 소비처(node-registry audit 노드 등)를 지킨다."""
    out = _compat_fields(ENGINE_RESULT)
    for key in ("complianceScore", "finalStatus", "findings", "sections",
                "skipped", "snapshot_id", "input_hash"):
        assert key in out, f"기존 평면 필드 {key} 가 사라졌다"
    assert out["findings"] == [{"id": "f1"}]
    assert out["finalStatus"] == "CONFIRMED"


def test_비정상_입력에도_키가_존재한다():
    """소비처가 `?.` 없이 읽어도 터지지 않도록 — 계약은 항상 키를 준다."""
    out = _compat_fields(None)
    assert out["findings"] == []
    assert out["sections"] == {}
