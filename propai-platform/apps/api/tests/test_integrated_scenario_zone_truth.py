"""통합 시나리오가 **틀린 용도지역**으로 수지를 계산해 나갔다 (2026-08-24 라이브 실측).

## 증상 — 한 응답 안에서 용도지역이 세 번 갈렸다

라이브(`POST /api/v1/zoning/integrated-analysis`, 오산 내삼미동 8필지):

    dominant_zone        제2종일반주거지역   (basis: area_weighted)      ← 맞음
    scenario.site        제2종일반주거지역   far 250 / bcr 60            ← 맞음
    scenario.top3        **자연녹지지역**    far 100 / bcr 20            ← **실제 수지가 이걸로**
    scenario.top3        parcel_count=1 · zone_basis="single"            (실제 투입 8필지)

결과: 화면이 *"단독주택·전원주택만 가능, 전부 적자"* 로 보였다. 실제 부지는 제2종일반주거
(용적률 250%)라 완전히 다른 사업모델이 성립한다 — **디벨로퍼·금융이 멀쩡한 부지를 접을 수
있는 크기**의 결함이다.

## 근본 둘이 겹쳤다

1. `auto_recommend_top3` 는 `parcels` 를 받으면 `build_integrated_context` 로 **면적가중
   우세용도**를 채택하는 경로를 **이미 갖고 있었다**(`zone_basis="integrated_dominant"`).
   그런데 호출부가 **그 인자를 안 넘겼다** — 이 저장소가 반복한 *"정의만 하고 소비처 0"*.
2. 그래서 위임은 zone 을 `rep_addr` 로 재도출하는데, 그 값이 **번지 없는 동 단위 주소**
   (`"경기도 오산시 내삼미동"`)라 지오코딩이 엉뚱한 필지를 집었다.
   ★그래서 `zone_basis="representative_parcel"` 이라는 라벨도 **거짓**이었다 —
     대표(첫) 필지조차 제2종일반주거였다.

## ★시니어 오케스트레이터가 왜 못 잡았나 (구조적 사각)

시니어 자문(`attach_senior_consultation`)은 **산출물**을 본다(자기자본비율·ROI 현실성).
자연녹지 far 80% 로 계산한 수지는 **내부적으로 완벽히 정합**하다 — 자문이 통과시키는 게 맞다.
틀린 것은 **입력 전제**이고, 그 층을 보는 감사자가 파이프라인에 없었다(평가기 13종 중
`zone` 을 보는 것은 `land_assembly` 하나 · `auto_zoning.py` 의 senior 참조 **0건**).
이 파일의 `test_C` 가 그 **전제 감사**의 첫 사례다.
"""
from __future__ import annotations

import inspect
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _router_src() -> str:
    """실행되는 줄만 본다 — 주석·독스트링에 적힌 예시가 배선으로 세어지면 안 된다."""
    path = os.path.join(os.path.dirname(__file__), "..", "routers", "auto_zoning.py")
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    return "\n".join(
        ln for ln in src.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    )


def test_A_위임에_parcels_를_넘긴다_안_넘기면_zone_이_재도출된다():
    """★배선 락 — 이 한 줄이 빠지면 위임이 주소로 zone 을 재도출한다.

    `auto_recommend_top3` 내부는 `len(parcels) >= 2` 일 때만 면적가중 우세용도를 채택한다.
    호출부가 안 넘기면 그 경로는 **영원히 죽어 있다**(실제로 그랬다).
    """
    src = _router_src()
    m = re.search(r"kwargs:\s*dict\s*=\s*\{(.*?)\n\s{12}\}", src, re.S)
    assert m, "auto_recommend_top3 kwargs 블록을 찾지 못했다 — 파서가 낡았다"
    block = m.group(1)
    assert '"parcels"' in block, (
        "위임 kwargs 에 parcels 가 없다 — 용도지역이 대표주소로 재도출되어 "
        "통합면적 × 엉뚱한 용도지역 조합이 나간다"
    )
    assert "enriched" in block, "보강 전 원본이 아니라 **보강된 필지**를 넘겨야 한다"


def test_B_zone_basis_를_하드코딩하지_않는다():
    """★거짓 라벨 방지 — 종전 'representative_parcel' 은 실계산과 달랐다.

    라벨은 **위임이 실제로 쓴 기준**에서 와야 한다. 하드코딩하면 값이 바뀌어도 라벨이 따라오지
    않아, 화면이 근거를 잘못 말한다(값보다 근거가 틀린 게 더 나쁘다).
    """
    src = _router_src()
    assert '"zone_basis": "representative_parcel"' not in src, (
        "zone_basis 가 다시 하드코딩됐다 — 실계산 기준과 갈릴 수 있다"
    )
    assert 'site["zone_basis"] = top3.get("zone_basis")' in src, (
        "zone_basis 를 위임 결과에서 가져오지 않는다"
    )


def test_C_전제감사_용도지역_불일치를_조용히_내보내지_않는다():
    """★★이 저장소에 없던 층 — **입력 전제 감사**.

    시니어 자문은 산출물이 말이 되는지만 본다. 입력이 틀리면 산출물은 정합한 채로 틀린다.

    ★**구현이 레지스트리로 승격됐다**(2026-08-24). 종전엔 여기 용도지역 불일치 **하나만**
      손으로 박혀 있었다 — 그러면 다음 불일치는 또 손으로 박아야 하고 결국 빠진다
      (*"사람이 센 목록이 곧 상한이 된다"* §A-4).
      관계별 판정은 `test_premise_audit_registry.py` 가, 배선은 아래가 잠근다.

    ★값을 몰래 고치지 않는다 — 고지한다(무목업·정직 원칙).
    """
    src = _router_src()
    assert "premise_audit.audit(" in src, "전제 감사를 호출하지 않는다"
    # 발견을 **사용자에게 닿는 세 경로**로 모두 보내는가(하나만 있으면 화면이 놓친다).
    for sink, why in (
        ("warnings.append(_msg)", "응답 warnings"),
        ("zone_mismatch_warnings.append(_msg)", "integrity_warnings 합류"),
        ('scenario["premise_audit"]', "기계가 읽는 구조화 필드"),
    ):
        assert sink in src, f"위반을 {why} 로 내보내지 않는다 — 발견이 사람에게 닿지 않는다"
    assert 'scenario["status"] = "tentative"' in src, (
        "위반인데 status 를 강등하지 않는다 — 잠정치가 확정으로 읽힌다"
    )


def test_D_불일치_경고가_integrity_warnings_에_실제로_합류한다():
    """★수집만 하고 합류를 안 하면 **정의만 하고 소비처 0** 이다(이 저장소 반복 실수)."""
    src = _router_src()
    assert "integrity_warnings = list(integrity_warnings or []) + zone_mismatch_warnings" in src, (
        "zone_mismatch_warnings 가 integrity_warnings 에 합류하지 않는다 — 화면이 못 본다"
    )
    # 선언이 사용보다 앞서는가(NameError 방지 — 실제로 한 번 냈다).
    decl = src.index("zone_mismatch_warnings: list[str] = []")
    use = src.index("zone_mismatch_warnings.append(_msg)")
    assert decl < use, "선언이 사용보다 뒤에 있다 — NameError"


def test_E_위임_시그니처가_parcels_를_받는다_계약_대조():
    """★호출부만 잠그면 반대쪽이 무제한이다(§19 양방향).

    위임에서 `parcels` 인자가 사라지면 test_A 는 통과하는데 런타임은 TypeError 다.
    """
    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2

    sig = inspect.signature(FeasibilityServiceV2.auto_recommend_top3)
    assert "parcels" in sig.parameters, (
        "auto_recommend_top3 가 parcels 를 안 받는다 — 호출부 배선이 깨진다"
    )
    # 그 인자를 실제로 소비하는가(받기만 하고 무시하면 배선이 죽은 것과 같다).
    body = inspect.getsource(FeasibilityServiceV2.auto_recommend_top3)
    live = "\n".join(
        ln for ln in body.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    )
    assert "len(parcels) >= 2" in live, "parcels 를 받기만 하고 소비하지 않는다"
    assert 'zone_basis = "integrated_dominant"' in live, (
        "면적가중 우세용도 채택 경로가 사라졌다"
    )
