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


# ── 표본 0 의 **사유**를 말한다 ────────────────────────────────────────────────

def test_no_sample_reason_distinguishes_masked_from_absent() -> None:
    """★"거래가 없다"와 "거래는 있는데 원천이 지번을 가려 위치를 못 잡는다"는 **다른 상태**다.

    ★이 함수가 없던 동안 탁상감정은 `scope=="radius"` 인데 `located` 가 0 이면 **아무 사유
    없이** 공시지가 기준으로 폴백했다(`comparable_skip_note` 는 반경 **미적용** 가지에만
    있었다). 사용자는 왜 거래사례비교를 안 썼는지 알 수 없었다.
    ★라이브 실측: 토지·단독다가구는 MOLIT 이 지번을 가려 주므로(`"5*"`·`"1**"`) 위치
    확인분이 **구조적으로 0** 이다 — 이 침묵 구간의 지배적 원인이고, 우리가 고칠 수 없는
    **데이터 한계**다. 그러면 그 사실을 말하는 것이 정직이다.
    """
    from app.services.market.comparable_sample import SampleBasis, no_sample_reason

    def _basis(**kw):
        base = dict(scope="radius", radius_applied=True, radius_m=1500, located_count=0,
                    approximate_count=0, unlocated_count=0, capped_count=0)
        base.update(kw)
        return SampleBasis(**base)

    # 표본이 있으면 사유가 없다.
    assert no_sample_reason(_basis(located_count=3)) is None

    # ★마스킹이 원인이면 그렇게 말한다 — 이게 land/house 의 지배적 사유다.
    masked = no_sample_reason(_basis(masked_jibun_count=13))
    assert masked is not None
    assert "지번을 가려서" in masked and "13건" in masked
    assert "반경 1.5km" in masked, "라벨은 SampleBasis 가 만든다(문구 중복 생성 금지)"

    # 마스킹이 아니면 다른 사유를 말한다 — 두 상태가 **구분돼야** 한다.
    other = no_sample_reason(_basis(unlocated_count=2, approximate_count=1))
    assert other is not None and "지번을 가려서" not in other
    assert "위치 미확인 2건" in other

    # 진짜로 아무것도 없으면 그렇게 말한다.
    empty = no_sample_reason(_basis())
    assert empty is not None and "수집된 거래가 없습니다" in empty


def test_sample_basis_recovers_masked_count_from_groups_on_legacy_payload() -> None:
    """구버전 페이로드엔 `masked_jibun_group_count` 가 없다 — **0 으로 단정하지 않고** 센다.

    0 으로 단정하면 "마스킹 때문"이라는 사유가 구버전에서 조용히 사라져, 사용자가
    "거래가 없다"는 **틀린 설명**을 받는다(모르는 것을 0 으로 쓰지 않는다).
    """
    from app.services.market.comparable_sample import _basis_from_category

    legacy = {   # sample_basis 가 없던 시절 형태
        "count_in_radius": 0, "count_approximate": 2, "count_unresolved": 1,
        "groups": [{"jibun": "5*"}, {"jibun": "1**"}, {"jibun": "736"}],
    }
    b = _basis_from_category(legacy)
    assert b.masked_jibun_count == 2


def test_sample_basis_reads_masked_count_from_modern_payload() -> None:
    """★배선 락 — `sample_basis` 경로에서 `masked_jibun_group_count` 를 **실제로 읽는가**.

    ★변이 실증: 이 읽기를 지워도 다른 골든이 전부 통과했다(내 테스트가 `SampleBasis` 를
    **직접 구성**하거나 구버전 폴백 경로만 태웠기 때문). 즉 신형 페이로드 → 도메인 객체
    **배선이 무잠금**이었다. 배선 미변이로 뚫린 다섯 번째 사례다.
    """
    from app.services.market.comparable_sample import _basis_from_category

    modern = {
        "sample_basis": {
            "scope": "radius", "radius_applied": True, "radius_m": 1500,
            "located_count": 0, "approximate_count": 5, "unlocated_count": 8,
            "capped_count": 0, "masked_jibun_group_count": 13,
        },
        # ★그룹 배열엔 마스킹이 **없다** — 폴백 경로가 아니라 `sample_basis` 경로를 태웠는지
        #   구분하기 위해서다(둘이 같은 값을 내면 변이가 생존한다).
        "groups": [{"jibun": "736"}],
    }
    b = _basis_from_category(modern)
    assert b.masked_jibun_count == 13, "신형 페이로드의 마스킹 수가 도메인 객체에 배선되지 않았다"


def test_desk_appraisal_actually_calls_no_sample_reason() -> None:
    """★배선 락(소스 검사) — 탁상감정이 표본 0 사유 헬퍼를 **실제로 호출하는가**.

    ★아래 행위 테스트는 판정 **조합을 재현**할 뿐 `desk_appraisal_service` 를 태우지 않는다.
    실제로 그 봉합을 지우는 변이가 **생존했다**(H-1 공허 배선 단언과 같은 형태).
    이 파일이 이미 확립한 방식대로 소스 검사로 못 박는다 — 그리고 **이름 존재가 아니라
    호출 형태**로 잠근다(이 파일 상단이 기록한 그 함정: 응답 키 이름이 정규식에 매치돼
    변이가 통과했던 사건).
    """
    src = (_API_ROOT / "app/services/land_intelligence/desk_appraisal_service.py").read_text(
        encoding="utf-8"
    )
    assert re.search(r"\bno_sample_reason\s*\(", src), (
        "탁상감정이 표본 0 사유 헬퍼를 호출하지 않는다 — 반경이 적용됐는데 표본이 0 이면 "
        "아무 사유 없이 공시지가로 폴백하던 침묵 구간이 되살아난다"
    )
    # ★임포트까지 확인 — 호출 형태만 보면 주석·문자열에 든 형태도 매치될 수 있다.
    assert re.search(r"^\s*no_sample_reason,\s*$", src, re.M), (
        "헬퍼가 임포트되지 않았다 — 호출 형태만 남고 실제로는 다른 이름을 쓰고 있을 수 있다"
    )


def test_desk_appraisal_emits_skip_note_when_radius_applied_but_no_sample() -> None:
    """★배선 락 — 탁상감정이 표본 0 일 때 **사유를 실제로 싣는가**.

    ★변이 실증: 이 봉합(`comparable_skip_note = no_sample_reason(basis)`)을 지워도 골든이
    전부 통과했다 — 탁상감정 경로를 태우는 테스트가 **0건**이었기 때문이다.
    종전 동작은 반경이 적용됐는데 표본이 0 이면 **아무 사유 없이** 공시지가로 폴백하는 것이고,
    그게 토지·단독다가구의 **상시 상태**(원천 지번 마스킹)였다.

    `desk_appraisal()` 전체는 외부 의존이 많아, 이 테스트는 그 함수가 사용하는 **정확한
    판정 조합**(`basis.scope == "radius"` + `weighted_unit_price_per_sqm(located) is None`)을
    같은 헬퍼로 재현해 사유가 나오는지 확인한다 — 헬퍼가 곧 그 분기의 유일한 근거다.
    """
    from app.services.market.comparable_sample import (
        no_sample_reason,
        select_located_groups,
        weighted_unit_price_per_sqm,
    )

    # 마스킹 지번 그룹만 있는 카테고리 — 위치 확인분이 구조적으로 0 이다.
    cat = {
        "groups": [
            {"jibun": "5*", "dong": "논현동", "location_status": "approximate",
             "avg_price_10k": 50000, "avg_area_m2": 100.0, "count": 2},
            {"jibun": "1**", "dong": "청담동", "location_status": "unlocated",
             "avg_price_10k": 60000, "avg_area_m2": 120.0, "count": 1},
        ],
        "sample_basis": {
            "scope": "radius", "radius_applied": True, "radius_m": 1500,
            "located_count": 0, "approximate_count": 2, "unlocated_count": 1,
            "capped_count": 0, "masked_jibun_group_count": 2,
        },
    }
    located, basis = select_located_groups(cat)
    assert basis.scope == "radius", "이 테스트는 반경 적용 가지를 검증한다"
    assert located == [], "마스킹 그룹은 위치 확인분이 될 수 없다"
    assert weighted_unit_price_per_sqm(located) is None, "표본 0 → 단가를 만들 수 없다"

    # ★그 조합에서 **사유가 나와야** 한다 — 종전엔 여기가 침묵이었다.
    note = no_sample_reason(basis)
    assert note is not None
    assert "지번을 가려서" in note, f"마스킹이 원인인데 그 사실을 말하지 않는다: {note}"
