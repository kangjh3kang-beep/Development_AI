"""`scripts/orphan_routes.py` **자체**를 잠근다 — 종전에는 이 도구에 테스트가 0건이었다.

【왜 생겼나 — 2026-08-20】
래칫(`test_orphan_routes_ratchet.py`)은 도구의 **출력**을 잠갔지만 도구의 **판정**은
아무도 잠그지 않았다. 그 사이 도구가 **양방향으로** 틀렸고, 그 수치로 결함 후보 약 40건이
보드에 공표됐다. 두 결함을 각각 여기서 잠근다:

  ① 마지막 세그먼트를 **동적으로** 넣는 호출을 못 보고 고아로 신고했다(위양성)
  ② 소스를 통째로 이어 붙여 **주석 안의 경로도 소비로 셌다**(위음성 = 놓친 고아)

【픽스처 설계 — 규율 "두 모집단을 갈라야 잠금이다"】
아래 픽스처는 **한 blob 안에** 두 모집단을 같이 넣는다. 분류가 둘을 **다른 칸**으로
보내야만 초록이다. 둘이 같은 칸으로 가면(=배선을 끊으면) 빨강이 된다.
"""
from __future__ import annotations

import os
import sys

import pytest

_SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))
sys.path.insert(0, _SCRIPTS)

from orphan_routes import (  # type: ignore[import-not-found]  # noqa: E402
    _strip_js_comments,
    classify,
    is_consumed,
    is_dynamically_reachable,
)

# ─────────────────────────────────────────────────────────────────────────────
# 픽스처 — 두 모집단을 한 blob 에 함께 둔다.
#   모집단 A(동적 소비): `/market/report/${fmt}` — 마지막 세그먼트가 동적
#   모집단 B(진짜 고아): 어디에도 없는 경로
#   모집단 C(리터럴 소비): 실행줄에 리터럴로 있는 경로
#   모집단 D(주석에만 있음): 주석에만 있는 경로 — 소비로 세면 안 된다
_BLOB = """
import { apiClient } from "@/lib/api-client";
// 주석: /api/v1/only-in-a-line-comment 는 예전에 쓰던 경로다
/* 블록 주석: /api/v1/only-in-a-block-comment 도 이제 안 쓴다 */
export async function run(fmt: "pdf" | "pptx") {
  await fetch(`${base()}/market/report/${fmt}`, { method: "POST" });
  await apiClient.post("/land-price/estimate", {});
  await apiClient.get(`/permits/${projectId}/latest`);
  const re = /https?:\\/\\/example\\.com/;   // 정규식 이스케이프가 스트리퍼를 깨지 않아야 한다
  const url = "https://example.com/api/v1/inside-a-string";
}
"""

# ★실제 파이프라인과 **같은 순서**로 태운다: frontend_blob() 이 주석을 지운 뒤 is_consumed 가
#   본다. 원본을 그대로 넘기면 결함②가 그대로 재현된다(이 픽스처를 처음 그렇게 썼다가
#   아래 대조군에 걸렸다 — 락이 자기 픽스처의 오류부터 잡았다).
_SCANNED = _strip_js_comments(_BLOB)


def test_주석은_소비로_세지_않고_실행줄은_센다():
    """★결함② 잠금 — 대조군 한 쌍으로 스트리퍼의 **생존**을 함께 증명한다."""
    # 공허 진리 가드: 실행줄 경로가 실제로 잡혀야 이 대조가 의미를 가진다.
    assert is_consumed("/api/v1/land-price/estimate", _SCANNED), (
        "실행줄의 리터럴 경로를 못 잡았다 — 대조군이 죽었으므로 아래 단언은 공허하다"
    )
    assert not is_consumed("/api/v1/only-in-a-line-comment", _SCANNED), "줄 주석이 소비로 세어졌다"
    assert not is_consumed("/api/v1/only-in-a-block-comment", _SCANNED), "블록 주석이 소비로 세어졌다"


def test_문자열_안의_슬래시슬래시는_주석이_아니다():
    """★`source-invariant.ts` 가 기록한 함정 — URL 의 `//` 를 주석으로 오인하면 코드를 삼킨다."""
    kept = _strip_js_comments(_BLOB)
    assert "/api/v1/inside-a-string" in kept, "문자열 안의 URL 을 주석으로 오인해 삼켰다"
    assert "/land-price/estimate" in kept, "정규식 리터럴 뒤 코드가 삼켜졌다"
    # 스트리퍼가 아무것도 안 지우면 위 두 단언은 공허하게 참이 된다 → 지웠음을 직접 확인.
    assert "only-in-a-line-comment" not in kept
    assert "only-in-a-block-comment" not in kept
    assert len(kept) == len(_BLOB), "길이 보존(공백 치환)이 깨졌다 — 오프셋 기반 후속 검사가 어긋난다"


def test_동적세그먼트와_진짜고아가_다른_칸으로_간다():
    """★결함① 잠금 — **두 모집단이 갈라져야** 잠금이다. 같은 칸이면 배선을 끊어도 초록이다."""
    dynamic_route = "/api/v1/market/report/pdf"   # 프론트가 `${fmt}` 로 부르는 자리
    real_orphan = "/api/v1/nobody/calls-this"        # 어디에도 없는 경로

    # 공허 진리 가드 — 둘 다 "리터럴 소비"가 아니어야 이 대조가 성립한다.
    assert not is_consumed(dynamic_route, _SCANNED)
    assert not is_consumed(real_orphan, _SCANNED)

    assert is_dynamically_reachable(dynamic_route, _SCANNED), "동적 세그먼트 호출을 못 봤다(결함① 재발)"
    assert not is_dynamically_reachable(real_orphan, _SCANNED), "진짜 고아가 판정 불가로 새어 나갔다"


def test_동적세그먼트는_경로의_마지막일_때만_인정한다():
    """★`/permits/${projectId}/latest` 가 `/permits/compliance-check` 를 설명해선 안 된다(실측)."""
    assert not is_dynamically_reachable("/api/v1/permits/compliance-check", _SCANNED)
    # 대조군 — 같은 부모라도 **마지막**이 동적이면 인정된다.
    assert is_dynamically_reachable("/api/v1/market/report/pptx", _SCANNED)


def test_다른_경로의_앞토막에_걸리지_않는다():
    """★`/api/v1/avm` 이 `/api/v1/avm-vision/analyze` 에 걸려 소비로 세어졌다(실측 위양성)."""
    blob = 'apiClient.post("/avm-vision/analyze", {});'
    assert not is_consumed("/api/v1/avm", blob), "오른쪽 세그먼트 경계가 사라졌다"
    # 대조군 — 진짜 그 경로면 잡아야 한다(경계 검사가 전부를 막아버리면 도구가 죽는다).
    assert is_consumed("/api/v1/avm-vision/analyze", blob)
    assert is_consumed("/api/v1/avm", 'apiClient.post("/avm", {});')


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        # 실측으로 확정한 것만 넣는다(추정 금지).
        ("/api/v1/market/report/pdf", "undecided"),   # ①의 실증 사례
        ("/api/v1/avm/estimate", "orphan"),           # ②의 실증 사례(주석에만 있었다)
        ("/api/v1/finance/monte-carlo", "orphan"),    # ②의 실증 사례(JSX 주석에만 있었다)
        ("/api/v1/land-price/estimate", "consumed"),  # 대조군 — 정상 소비
    ],
)
def test_실제_저장소에서도_세_칸으로_갈린다(route: str, expected: str):
    """★순수 함수만 잠그면 **실제 스캔 경로**는 우회된다 — 진짜 파이프라인을 태운다."""
    confirmed, undecided = classify()
    conf, und = {f for f, _m, _p in confirmed}, {f for f, _m, _p in undecided}

    # 공허 진리 가드 — 세 칸이 모두 유의미한 크기여야 아래 판정이 의미를 가진다.
    assert len(conf) > 50, "확정 고아가 비정상적으로 적다 — 스캐너가 죽었을 가능성"
    assert len(und) > 5, "판정 불가가 비정상적으로 적다 — 동적 분류기가 죽었을 가능성"

    actual = "orphan" if route in conf else "undecided" if route in und else "consumed"
    assert actual == expected, f"{route} 가 {expected} 가 아니라 {actual} 로 분류됐다"
