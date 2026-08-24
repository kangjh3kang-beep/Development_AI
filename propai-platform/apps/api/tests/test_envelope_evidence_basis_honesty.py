"""건축가능범위 근거가 **틀린 법령을 인용하지 않는다** — 라이브 실측(2026-08-24).

## 프로덕션에서 본 것

`4t8t.net` 역삼동 736(3필지·일반상업) "건축 가능 범위 산출 근거" 블록:

    용적률 허용 연면적  = 256,336㎡  (대지면적 × 용적률 158.2%)          ← 정직
    법정 건폐율        = 25.7%      (…국토계획법 시행령 제84조)          ← ★틀렸다

같은 페이지가 다른 칸에서는 그 25.7% 를 **"통합 건폐/용적(실효)"** 이라 부른다.
**일반상업지역의 법정 건폐율은 80%** 다. 즉 라벨은 "법정", 값은 "실효", 인용은 "제84조".

## 왜 없는 근거보다 나쁜가

읽는 사람이 조문을 확인하러 갔다가 숫자가 안 맞으면 **그 뒤의 모든 값을 의심**한다.
근거를 다는 일의 목적이 정반대로 작동한다.

## 원인 — 호출자가 실효를 넘기는데 라우터가 무조건 "법정"이라 불렀다

    ProjectAnalysisSummary → integratedBcrPct = blended_bcr_eff_pct(면적가중 실효)
      → POST /site-score/envelope { bcr_limit_pct: 25.7 }
      → solar_envelope 이 그대로 bcr_pct 로 반환
      → routers/site_score.py 가 "법정 건폐율" + 제84조 로 라벨링

판정은 추측하지 않는다 — **요청에 한도가 실려 왔는지**로 가른다.
실려 왔으면 호출자가 계산한 **적용(실효)** 한도, 아니면 서비스가 용도지역 표에서 가져온
**법정 상한**이다.

## 이 파일이 잠그는 것

1. 호출자가 한도를 넘기면 라벨이 **"법정"이 아니다**
2. 그때 **법령 링크(legal_ref_key)를 달지 않는다** — 그 조문은 이 숫자를 만들지 않는다
3. 대조군 — 넘기지 **않으면** 종전대로 "법정 건폐율" + 제84조 (무회귀)
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _envelope(payload: dict) -> dict:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/api/v1/site-score/envelope", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _row(body: dict, needle: str) -> dict | None:
    for e in body.get("evidence") or []:
        if needle in str(e.get("label", "")):
            return e
    return None


BASE = {"land_area_sqm": 162033.0, "zone": "일반상업지역", "floor_height_m": 3.0}


@pytest.mark.asyncio
async def test_실효한도를_넘기면_법정이라_부르지_않는다() -> None:
    """★라이브 재현 — 호출자가 면적가중 실효(25.7%)를 넘긴 경우."""
    body = await _envelope({**BASE, "bcr_limit_pct": 25.7, "far_limit_pct": 158.2})

    # 전제 가드 — 근거 블록이 실제로 있어야 아래 단언이 의미를 갖는다.
    assert body.get("evidence"), "evidence 블록이 없다 — 검사 대상이 없는 초록"

    bcr = _row(body, "건폐율")
    assert bcr is not None, f"건폐율 근거 행이 없다: {[e.get('label') for e in body['evidence']]}"
    # ①라벨이 '법정'이라 말하지 않는다.
    assert "법정" not in bcr["label"], f"실효값인데 라벨이 법정이다: {bcr}"
    assert "실효" in bcr["label"]
    # ②법령 링크를 달지 않는다 — 제84조는 이 숫자를 만들지 않는다.
    assert "legal_ref_key" not in bcr, f"실효값에 법령 링크가 달렸다: {bcr}"
    # ③그래도 법정 상한이 어디서 정해지는지는 알려 준다(정보를 지우지 않는다).
    assert "제84조" in bcr["basis"]
    assert "법정 상한이 아니" in bcr["basis"]

    far = _row(body, "용적률 허용 연면적")
    assert far is not None
    assert "실효" in far["basis"], f"용적률 근거가 실효임을 말하지 않는다: {far}"
    assert "legal_ref_key" not in far
    # ★근거는 **산식과 값**을 함께 말해야 한다 — 문구만 보면 응답에서 far_pct 가
    #   사라져도(`—` 로 떨어져도) 이 단언이 통과한다(변이 생존으로 드러났다).
    assert "적용 용적률" in far["basis"]
    assert "158.2" in far["basis"], f"적용 용적률 값이 근거에 없다: {far}"
    assert body.get("far_pct") == 158.2, f"응답이 적용 용적률을 싣지 않는다: {body.get('far_pct')}"
    # 허용 연면적도 실제 수치여야 한다(0㎡ 로 떨어지면 근거가 무의미하다).
    assert body.get("far_gfa_sqm"), "far_gfa_sqm 이 비었다"
    assert "㎡" in str(far["value"]) and str(far["value"]) != "0㎡"


@pytest.mark.asyncio
async def test_대조군_한도를_안_넘기면_종전대로_법정이라_부른다() -> None:
    """★무회귀 — 서비스가 용도지역 표에서 법정 상한을 가져온 경우는 '법정'이 맞다.

    이 대조군이 없으면 **"무엇이든 실효라 부르는"** 처리도 초록이 된다.
    """
    body = await _envelope(BASE)
    assert body.get("evidence"), "evidence 블록이 없다"

    bcr = _row(body, "건폐율")
    assert bcr is not None
    assert bcr["label"] == "법정 건폐율", f"법정 경로인데 라벨이 바뀌었다: {bcr}"
    assert bcr.get("legal_ref_key") == "bcr_limit", f"법정인데 법령 링크가 없다: {bcr}"
    assert "제84조" in bcr["basis"]

    far = _row(body, "용적률 허용 연면적")
    assert far is not None
    assert far.get("legal_ref_key") == "far_limit"
    assert "법정 용적률" in far["basis"]
    # 대조군에서도 값이 실려야 한다 — 일반상업 법정 용적률 1300%.
    assert body.get("far_pct") == 1300.0, f"법정 경로인데 far_pct 가 {body.get('far_pct')}"
    assert "1300" in far["basis"]
    assert body.get("far_gfa_sqm"), "far_gfa_sqm 이 비었다"


@pytest.mark.asyncio
async def test_두_경로가_서로_다른_라벨을_낸다() -> None:
    """★대조군의 대조군 — 두 경우가 같은 화면을 내면 이 락은 아무것도 잠그지 않는다."""
    legal = _row(await _envelope(BASE), "건폐율")
    effective = _row(await _envelope({**BASE, "bcr_limit_pct": 25.7}), "건폐율")
    assert legal is not None and effective is not None
    assert legal["label"] != effective["label"]
    assert ("legal_ref_key" in legal) is not ("legal_ref_key" in effective)


@pytest.mark.asyncio
async def test_값_자체는_지우지_않는다() -> None:
    """★이 캠페인의 처방은 언제나 **라벨·고지**이지 값 삭제가 아니다."""
    body = await _envelope({**BASE, "bcr_limit_pct": 25.7})
    bcr = _row(body, "건폐율")
    assert bcr is not None and "25.7" in str(bcr["value"])
