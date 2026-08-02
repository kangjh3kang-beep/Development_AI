"""주변 실거래 표본 셀렉터 배선 불변식 — 미발견 소비처를 **시끄럽게** 만든다.

## 왜 소스 검사인가

이 규칙은 lint 로 걸 수 없다:

- `ruff` 는 **커스텀 규칙 플러그인을 지원하지 않는다** — 백엔드 소비처에 원리적으로 도달 불가.
- eslint 로 프론트만 거는 것도 반쪽이고, 이 저장소 CI 는 `--max-warnings` 미설정이라
  경고 수준 규칙은 **아무것도 차단하지 않는다**(워크플로우에 명문화돼 있다).

그래서 **CI 가 이미 실패시키는 레인**(pytest)에 소스 검사로 넣는다.

## 무엇을 막는가

`nearby-map` 응답의 `categories[*].groups` 는 성격이 다른 셋이 섞인 리스트다
(위치 확인 / 위치 개략(동 단위) / 위치 미확인). 이걸 그냥 순회해 평균·단가를 만들고
"반경 N" 라벨을 붙이면 거짓 진술이 된다 — 2026-08-02 실측에서 표시 표본의 60~100%가
위치 확인분이 아니었다.

그런데 이 오염은 **조용하다**: 좌표가 있는 그룹도 법정동 대표점이거나 동명 물건이 여러 동에
병합된 것일 수 있어 `lat is not None` 검사로는 안 걸리고, 값도 그럴듯하게 나온다.
2026-08-02 감사에서 소비처 6곳 중 4곳이 이 상태였다.

## 스코프를 좁게 잡은 이유(과도스코프 금지)

"`avg_price_10k` 를 어디서도 쓰지 마라"로 넓히면 **MOLIT 를 직접 쓰는 정상 경로**
(`market_report_service`·`conversational_market_ai`·`comprehensive_analysis_service` 등)가
전부 걸려 기준선에서 실패한다. 그런 규칙은 `# noqa` 한 줄로 영구 무력화된다.

따라서 조건을 **교집합**으로 좁힌다: *nearby-map 을 소비하면서* + *그룹 가격을 집계하면*
→ 셀렉터를 거쳐야 한다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_API_ROOT = Path(__file__).resolve().parents[1]

# nearby-map 응답을 손에 쥐는 파일인가(생산처 호출 또는 라우터 반환)
_CONSUMES_NEARBY = re.compile(r"NearbyMapService|nearby_map_service")

# 그룹 단위 가격/보증금/월세를 만지는가
# ★리뷰(M-3) — `deals[].price_10k_won` 을 누산하는 형태(프론트 ConversationalMarketPanel 이
#   정확히 그 모양)가 교집합에서 빠져 있었다. 백엔드에 동형 소비처가 생기면 무음 통과한다.
#   현재 백엔드 오펜더 0건임을 확인하고 넓혔다(기준선 안전).
_TOUCHES_GROUP_PRICE = re.compile(
    r"avg_price_10k|avg_deposit_10k|avg_monthly_10k|price_10k_won"
)

# 셀렉터를 거치는가
# ★2026-08-02 자체 적발: 처음엔 `comparable_sample|select_located_groups` 라는 **이름 존재**
#   검사였는데, 변이 주입(desk_appraisal 에서 셀렉터를 걷어내고 groups 전수 순회로 복원)이
#   **통과**했다. 응답 dict 의 키 이름 `"comparable_sample"` 이 그대로 남아 정규식에 매치됐기
#   때문이다. 이름이 어딘가에 있다는 것과 그 함수를 **호출한다**는 것은 다르다 —
#   임포트문 또는 호출 형태(괄호까지)로 못 박는다.
_USES_SELECTOR = re.compile(
    r"from\s+app\.services\.market\.comparable_sample\s+import"
    r"|select_located_groups\s*\("
    r"|weighted_unit_price_per_sqm\s*\("
    r"|weighted_avg_price_10k\s*\("
)

# 규칙의 적용을 면제받는 파일과 그 사유(면제는 **이유와 함께**만 존재한다).
_EXEMPT: dict[str, str] = {
    "app/services/land_intelligence/nearby_map_service.py":
        "생산처 본인 — groups 를 만드는 쪽이라 셀렉터의 입력이지 소비처가 아니다.",
    "app/services/market/comparable_sample.py":
        "셀렉터 본인 — 자기 자신을 거치라고 요구할 수 없다(순환).",
}


def _strip_comments_and_docstrings(src: str) -> str:
    """주석·독스트링을 걷어낸 **코드만** 남긴다.

    ★리뷰(M-3) — 이 검사는 문자열 포함이라 **주석/독스트링의 언급이 조건을 충족**한다.
    예: `# select_located_groups(cat) 로 바꿔야 함(TODO)` 한 줄이면 배선을 되돌려도 초록.
    프론트 `assertWiredThrough` 에서 같은 구멍이 실증됐고(주석 5/5 우회), 여기도 같은 계열이다.
    """
    # 독스트링/멀티라인 문자열 제거(비탐욕) → 줄 주석 제거
    src = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', "", src)
    return re.sub(r"#.*$", "", src, flags=re.MULTILINE)


def _scan() -> list[tuple[str, str]]:
    """(상대경로, **주석 제거된** 본문) — 검사 대상 파이썬 소스."""
    out: list[tuple[str, str]] = []
    for base in ("app", "routers"):
        root = _API_ROOT / base
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            rel = p.relative_to(_API_ROOT).as_posix()
            try:
                out.append((rel, _strip_comments_and_docstrings(p.read_text(encoding="utf-8"))))
            except (OSError, UnicodeDecodeError):  # pragma: no cover - 읽기 실패는 스킵
                continue
    return out


def test_scan_actually_reads_sources() -> None:
    """★공허진리 차단 — 스캔이 0개 파일을 읽고도 '전부 통과'로 보고하는 것을 막는다.

    경로 오타·리팩터로 스캔이 빈 집합이 되면 아래 계약 테스트는 전건 통과해버린다.
    이 저장소는 "검사는 병기하고 하한을 함께 건다"는 규율을 이미 세웠다.
    """
    files = _scan()
    assert len(files) > 200, f"소스 스캔이 비정상적으로 적다({len(files)}개) — 경로 계약이 깨졌다"
    assert any(rel.endswith("nearby_map_service.py") for rel, _ in files), (
        "생산처 파일이 스캔에 안 잡힌다 — 스캔 루트가 잘못됐다"
    )


def test_nearby_map_price_consumers_go_through_selector() -> None:
    """nearby-map 을 소비하면서 그룹 가격을 집계하는 파일은 셀렉터를 거쳐야 한다.

    새 소비처가 생기면 이 테스트가 **저자에게 결정을 강요한다** — 셀렉터를 쓰거나,
    면제 사유를 명시하거나. 조용히 통과하는 길이 없다.
    """
    offenders: list[str] = []
    for rel, src in _scan():
        if rel in _EXEMPT:
            continue
        if not _CONSUMES_NEARBY.search(src):
            continue
        if not _TOUCHES_GROUP_PRICE.search(src):
            continue
        if not _USES_SELECTOR.search(src):
            offenders.append(rel)

    assert not offenders, (
        "nearby-map 그룹 가격을 셀렉터 없이 집계하는 소비처가 있다.\n"
        "위치 미확인·개략 그룹이 섞여 '반경 N' 라벨 아래 거짓 평균이 만들어진다.\n"
        "→ app.services.market.comparable_sample.select_located_groups 를 쓰거나,\n"
        "   정말 면제 대상이면 이 테스트의 _EXEMPT 에 **사유와 함께** 등록하라.\n"
        f"위반: {offenders}"
    )


def test_exempt_entries_are_real_files_with_reasons() -> None:
    """면제 목록이 유령을 가리키거나 사유 없이 늘어나는 것을 막는다.

    면제는 시간이 지나면 "왜 있는지 아무도 모르는 목록"이 된다. 파일 실재와 사유를
    함께 잠가야 다음 사람이 판단할 수 있다.
    """
    for rel, reason in _EXEMPT.items():
        assert (_API_ROOT / rel).exists(), f"면제 목록의 파일이 없다: {rel}"
        assert len(reason.strip()) >= 10, f"면제 사유가 비었거나 너무 짧다: {rel}"


@pytest.mark.parametrize(
    "rel",
    [
        "app/services/land_intelligence/desk_appraisal_service.py",
        "app/services/ai/assistant_agent.py",
    ],
)
def test_known_consumers_are_actually_wired(rel: str) -> None:
    """★배선 하한 — 2026-08-02 에 봉합한 소비처가 **지금도** 셀렉터를 거치는지 고정한다.

    위 계약 테스트는 "nearby-map + 가격" 교집합에만 발화한다. 누군가 소비처에서
    가격 참조만 지우고 셀렉터도 함께 걷어내면 교집합에서 빠져나가 조용히 통과한다.
    실제 봉합 지점을 이름으로 못 박아 그 탈출로를 닫는다(상한만으론 샌다 — 양쪽 결박).
    """
    src = (_API_ROOT / rel).read_text(encoding="utf-8")
    assert _CONSUMES_NEARBY.search(src), f"{rel} 이 더는 nearby-map 소비처가 아니다 — 계약 재확인 필요"
    assert _USES_SELECTOR.search(src), (
        f"{rel} 이 셀렉터를 거치지 않는다 — 위치 미확인·개략 표본이 다시 섞인다"
    )
