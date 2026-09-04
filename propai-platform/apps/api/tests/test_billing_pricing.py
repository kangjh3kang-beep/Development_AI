"""LLM 단가표 계약 잠금 — 과다/과소 청구 재발 방지.

★배경(2026-08-01 실측): 종전 표는 세대 3키(opus/sonnet/haiku)뿐이었고
  ①`opus` $15/$75 = Opus 3 시절 단가(실제 Opus 4.5~5는 $5/$25) → 원가 3배 과다
  ②OpenAI·Google 모델은 미등재라 전부 sonnet 단가로 폴백(gpt-4o-mini는 20배 이상 과다)
이 표의 값에 등급 할증(50/40/30%)이 곱해져 청구액이 되므로 오차가 그대로 사용자에게 간다.
"""

from __future__ import annotations

import pytest

from app.core.billing import (
    MODEL_PRICING_USD_PER_MTOK,
    model_cost_usd,
    resolve_model_pricing,
)
from app.services.ai.llm_provider import PROVIDERS

# ── ★핵심 불변식: 노출 모델 ⊆ 단가 등재 모델 ────────────────────────────────

def test_every_offered_model_has_pricing():
    """★구조적 봉합: 드롭다운에 뜨는 모델은 전부 단가가 등재돼 있어야 한다.

    새 모델을 PROVIDERS에 추가하면서 단가 등재를 잊으면 조용히 폴백 단가로 청구된다.
    이 테스트가 그 누락을 CI에서 잡는다(한 곳을 고치면 전역이 따라오는 지점).
    """
    missing: list[str] = []
    for pkey, prov in PROVIDERS.items():
        for m in prov.get("models", []):
            model_id = str(m.get("id", ""))
            _pricing, matched = resolve_model_pricing(model_id)
            if matched is None:
                missing.append(f"{pkey}/{model_id}")
    assert not missing, f"단가 미등재 모델(폴백으로 잘못 청구됨): {missing}"


# ── 정정된 값이 실제 단가와 일치하는가 ──────────────────────────────────────

@pytest.mark.parametrize(
    ("model", "expect_in", "expect_out"),
    [
        # ★회귀락: 이 값이 $15/$75로 되돌아가면 원가 3배 과다계상이 재발한다.
        ("claude-opus-4-8", 5.0, 25.0),
        ("claude-opus-5", 5.0, 25.0),
        ("claude-sonnet-4-6", 3.0, 15.0),
        ("claude-haiku-4-5-20251001", 1.0, 5.0),
        ("gpt-4o-mini", 0.15, 0.60),
        ("gpt-4o", 2.50, 10.0),
        ("gemini-2.5-flash", 0.30, 2.50),
    ],
)
def test_pricing_matches_published_rates(model: str, expect_in: float, expect_out: float):
    pricing, matched = resolve_model_pricing(model)
    assert matched is not None, f"{model} 미등재"
    assert pricing["in"] == expect_in
    assert pricing["out"] == expect_out


def test_no_model_is_priced_at_retired_opus3_rate():
    """★어떤 등재 모델도 Opus 3 시절 단가($15/$75)를 쓰지 않는다."""
    for key, p in MODEL_PRICING_USD_PER_MTOK.items():
        assert not (p["in"] == 15.0 and p["out"] == 75.0), f"{key}가 구형 Opus 단가"


# ── ★긴 키 우선 매칭(세대 키가 정확 ID를 가리지 않는다) ────────────────────

def test_exact_model_id_wins_over_family_key():
    """`claude-opus-5`는 세대 키 `opus`가 아니라 정확 ID에 걸려야 한다."""
    _p, matched = resolve_model_pricing("claude-opus-5")
    assert matched == "claude-opus-5", f"세대 키에 잘못 매칭: {matched}"

    _p2, matched2 = resolve_model_pricing("claude-haiku-4-5-20251001")
    assert matched2 == "claude-haiku-4-5", f"세대 키에 잘못 매칭: {matched2}"


def test_longest_key_wins_regardless_of_dict_order(monkeypatch):
    """★메커니즘 잠금: **정렬**이 우선순위를 만들어야 한다 — dict 삽입순서가 아니라.

    현재 표는 정확 ID가 세대 키보다 앞에 있어서, 정렬을 지워도 삽입순서 덕에 우연히 통과한다
    (실제 변이검증에서 이 생존을 확인했다). 그래서 **세대 키를 앞에 둔 적대적 순서**로
    표를 바꿔치고도 정확 ID가 이기는지를 본다. 정렬을 제거하면 여기서 즉시 깨진다.
    """
    adversarial = {
        "opus": {"in": 5.0, "out": 25.0},            # 세대 키를 일부러 먼저
        "claude-opus-4-8": {"in": 5.0, "out": 25.0},
        "sonnet": {"in": 3.0, "out": 15.0},
        "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    }
    monkeypatch.setattr(
        "app.core.billing.MODEL_PRICING_USD_PER_MTOK", adversarial, raising=True
    )

    _p, matched = resolve_model_pricing("claude-opus-4-8")
    assert matched == "claude-opus-4-8", (
        f"세대 키가 정확 ID를 가렸다(삽입순서 의존 — 신형 모델이 구형 단가로 청구됨): {matched}"
    )
    _p2, matched2 = resolve_model_pricing("claude-sonnet-4-6")
    assert matched2 == "claude-sonnet-4-6", f"세대 키가 정확 ID를 가렸다: {matched2}"


def test_family_key_still_covers_unlisted_new_model():
    """미등재 신모델은 세대 안전망에 걸린다(폴백보다 정확)."""
    _p, matched = resolve_model_pricing("claude-opus-9-99")
    assert matched == "opus"


# ── 미등재는 조용히 넘어가지 않는다 ─────────────────────────────────────────

def test_unknown_model_is_flagged_not_silent():
    """★완전 미상 모델은 경고를 남긴다(종전엔 말없이 sonnet 단가였다).

    ★structlog 로거이므로 pytest caplog가 아니라 structlog.testing.capture_logs로 잡는다
    (caplog로 단언하면 경고가 실제로 나가는데도 실패해 '가드 없음'으로 오판한다).
    """
    from structlog.testing import capture_logs

    _p, matched = resolve_model_pricing("완전히-모르는-모델")
    assert matched is None

    with capture_logs() as logs:
        cost = model_cost_usd("완전히-모르는-모델", 1_000_000, 0)
    assert cost > 0  # 청구 파이프라인을 죽이지는 않는다
    assert any(
        "단가 미등재" in str(entry.get("event", "")) and entry.get("log_level") == "warning"
        for entry in logs
    ), f"미등재 모델인데 경고가 없다(조용한 오청구 재발): {logs}"


def test_registered_model_does_not_warn():
    """★대조군: 등재 모델은 경고를 내지 않는다(경고가 상시 발생하면 무의미해진다)."""
    from structlog.testing import capture_logs

    with capture_logs() as logs:
        model_cost_usd("claude-opus-4-8", 1_000, 1_000)
    assert not [e for e in logs if "단가 미등재" in str(e.get("event", ""))]


# ── 원가 계산 산식 ──────────────────────────────────────────────────────────

def test_cost_math():
    """100만 입력 + 100만 출력 = in + out 단가 합."""
    assert model_cost_usd("claude-opus-4-8", 1_000_000, 1_000_000) == pytest.approx(30.0)
    assert model_cost_usd("gpt-4o-mini", 1_000_000, 1_000_000) == pytest.approx(0.75)


def test_opus_cost_is_one_third_of_previous_table():
    """정정 전(15/75) 대비 정확히 1/3 — 과다청구 규모를 회귀락으로 박제."""
    now = model_cost_usd("claude-opus-4-8", 1_000_000, 1_000_000)
    before = (1_000_000 / 1_000_000) * 15.0 + (1_000_000 / 1_000_000) * 75.0
    assert before / now == pytest.approx(3.0)
