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

    # ★R2 리뷰(M-6) — `approximate` 항이 무테스트였다(그 두 줄을 지워도 전건 통과했다).
    assert "동 단위까지만 확인 1건" in other, "동 단위 확인분이 문장에서 사라진다"

    # 진짜로 아무것도 없으면 그렇게 말한다.
    empty = no_sample_reason(_basis())
    assert empty is not None and "수집된 거래가 없습니다" in empty


def test_masked_skew_branch_is_locked_by_literal() -> None:
    """★★R2 리뷰(M-2) — 스큐 갈래(`masked > unlocated`)를 **출력 문자열로** 잠근다.

    ★그 갈래는 무테스트였다(포함 관계 상한과 별도 항을 통째로 지워도 56 passed 생존).
    유일하게 관련 있던 테스트가 `b.no_sample_reason() == no_sample_reason(b)` 라
    **동어반복**이었다 — 양변이 함께 변이하므로 아무것도 잠그지 못한다.

    ★그리고 초판의 스큐 문장은 세 결함을 한꺼번에 가졌다:
      (a) 실거래 3건이 `1 + 3 + 2 = 6건`으로 읽히는 **이중계수**(M-3 이 없애려던 그 문제)
      (b) `—` 가 한 문장에 두 번 나와 절 구조 붕괴
      (c) `…확인할 수 없습니다은 단가 산정에…` **비문**(m-4 가 고친 결합 결함의 재생산)
    """
    from app.services.market.comparable_sample import SampleBasis, no_sample_reason

    skew = SampleBasis(
        scope="radius", radius_applied=True, radius_m=1500,
        located_count=0, approximate_count=2, unlocated_count=1,
        capped_count=0, masked_jibun_count=3, masked_jibun_group_count=2,
    )
    got = no_sample_reason(skew)
    assert got == (
        "반경 1.5km 내에서 위치가 확인된 거래가 없습니다 — "
        "위치 미확인 1건 · 동 단위까지만 확인 2건은 단가 산정에 쓰지 않습니다. "
        "지번이 가려진 거래는 3건으로 집계됐습니다(위 '위치 미확인' 건수에 포함되는지는 "
        "확인할 수 없습니다) — 공개 실거래 자료가 지번을 가려서 제공해(예: 5*, 1**) "
        "위치를 확인할 수 없습니다."
    ), got
    # 카운트 항에 마스킹을 **더하지 않는다**(더하면 같은 거래를 두 번 센다).
    assert "지번이 가려진 거래 3건 ·" not in got
    # ★R3 리뷰(F-5) — "그 밖에"는 **서로소를 적극 주장**해 독자가 1+3+2=6건으로 읽는다.
    #   M-2 가 없앤 이중계수의 어법판이라 문구를 바꿨다. 되돌아오면 이 단언이 잡는다.
    assert "그 밖에" not in got, "서로소를 단정하는 어법이 되살아났다"
    assert "포함되는지는 확인할 수 없습니다" in got
    # ★R4 리뷰(M-1·M-2) — "위 건수"는 지시 대상이 없거나(앞 건수 0) 틀린 대상(동 단위
    #   확인분)을 가리켰다. 대상을 **명시**하고, 앞 건수가 없으면 괄호를 생략한다.
    assert "위 '위치 미확인' 건수" in got, "지시 대상이 모호한 문구가 되살아났다"
    # `—` 는 절 구분자로 쓰되 한 문장에 하나씩만.
    assert got.count(" — ") == 2, f"절 구조가 무너졌다: {got}"


def test_sample_basis_recovers_masked_count_from_groups_on_legacy_payload() -> None:
    """구버전 페이로드엔 `masked_jibun_group_count` 가 없다 — **0 으로 단정하지 않고** 센다.

    0 으로 단정하면 "마스킹 때문"이라는 사유가 구버전에서 조용히 사라져, 사용자가
    "거래가 없다"는 **틀린 설명**을 받는다(모르는 것을 0 으로 쓰지 않는다).
    """
    from app.services.market.comparable_sample import _basis_from_category

    # ★그룹 수(2)와 거래 건수(7)를 **실제로 가른다** — 같으면 단위 변이가 생존한다.
    legacy = {   # sample_basis 가 없던 시절 형태
        "count_in_radius": 0, "count_approximate": 2, "count_unresolved": 1,
        "groups": [
            {"jibun": "5*", "count": 3},
            {"jibun": "1**", "count": 4},
            {"jibun": "736", "count": 9},   # 정상 지번 — 마스킹 집계에 들어오면 안 된다
        ],
    }
    b = _basis_from_category(legacy)
    assert b.masked_jibun_count == 7, "거래 건수"
    assert b.masked_jibun_group_count == 2, "물건 수"


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
            # ★두 축이 **서로 다른 값**이어야 단위 배선이 판별된다.
            "masked_jibun_count": 13, "masked_jibun_group_count": 4,
            "capped_count": 0,
        },
        # ★그룹 배열엔 마스킹이 **없다** — 폴백 경로가 아니라 `sample_basis` 경로를 태웠는지
        #   구분하기 위해서다(둘이 같은 값을 내면 변이가 생존한다).
        "groups": [{"jibun": "736", "count": 99}],
    }
    b = _basis_from_category(modern)
    assert b.masked_jibun_count == 13, "신형 페이로드의 마스킹 거래 건수가 배선되지 않았다"
    assert b.masked_jibun_group_count == 4, "신형 페이로드의 마스킹 물건 수가 배선되지 않았다"


def test_sample_basis_does_not_assume_zero_when_masked_key_is_absent() -> None:
    """★★R1 리뷰(M-5) — `sample_basis` 는 있는데 **마스킹 키만 없는** 배포 스큐.

    초판이 방어한 것은 `sample_basis` **자체가 없는** 아주 옛 응답인데, 그 필드는 W1-b
    이후 상시 존재한다. 즉 **실제로 일어나는 스큐는 이 형태**(프론트 캐시·백엔드 롤아웃
    지연)이고, 초판은 여기서 `or 0` 으로 **0 이라고 단정**했다 — "모르는 것을 0 으로
    단정하지 않는다"는 이 모듈의 선언이 정작 실제 스큐 구간에서 거짓이 되고, 그동안
    마스킹 사유가 조용히 사라진다.

    ★값 **0** 과 키 **부재**를 구분해야 한다 — 0 이면 그대로 0 을 쓴다(아래 두 번째 단언).
    """
    from app.services.market.comparable_sample import _basis_from_category

    skewed = {
        "sample_basis": {   # 마스킹 키가 **없다**
            "scope": "radius", "radius_applied": True, "radius_m": 1500,
            "located_count": 0, "approximate_count": 0, "unlocated_count": 5,
            "capped_count": 0,
        },
        "groups": [{"jibun": "5*", "count": 3}, {"jibun": "1**", "count": 2}],
    }
    b = _basis_from_category(skewed)
    assert b.masked_jibun_count == 5, "키 부재를 0 으로 단정했다 — 그룹에서 복원해야 한다"
    assert b.masked_jibun_group_count == 2

    # ★키가 있고 값이 0 이면 **그대로 0** 이다(복원 경로가 0 을 덮어써서는 안 된다).
    explicit_zero = {
        "sample_basis": dict(skewed["sample_basis"], masked_jibun_count=0,
                             masked_jibun_group_count=0),
        "groups": skewed["groups"],
    }
    assert _basis_from_category(explicit_zero).masked_jibun_count == 0


@pytest.mark.asyncio
async def test_desk_appraisal_really_emits_masked_reason_end_to_end() -> None:
    """★★R1 리뷰(M-2) — `desk_appraisal()` 을 **실제로 호출**해 사유가 응답에 실리는지 본다.

    ★이 테스트가 없던 동안 이 봉합의 **행위 커버리지는 0** 이었다. 리뷰어가 넣은 변이
    3종이 전부 **생존**했다:
      1. 판정 분기(`comparable_avg_per_sqm is None`)를 항상 거짓으로  → 51 통과
      2. 같은 변이 + 관련 11개 테스트파일 전량                        → 198 통과
      3. **봉합 2줄을 지우고 주석으로 남기되 임포트는 유지**          → 51 통과

    3번이 특히 뼈아프다 — 아래 소스 검사 락은 그 함정을 **안다고 주석에 적어 뒀는데**
    (임포트까지 본다) 임포트를 남기면 두 정규식이 **모두 통과**한다. 소스 검사는 텍스트를
    볼 뿐 **행위를 태우지 않는다**. 공허진리는 한 층 더 아래에 있었다.

    ★외부 의존은 넷뿐이고(아래 patch) 전부 `try/except` 로 감싸져 있어, 이 테스트는
    **실제 분기**를 그대로 통과시킨다 — 판정 조합을 재현하는 것이 아니다.
    """
    from app.services.land_intelligence import desk_appraisal_service as das

    class _StubNearby:
        async def build(self, **_kw):
            return {
                "categories": {
                    "land_trade": {
                        # 마스킹 지번뿐 — 위치 확인분이 구조적으로 0 이다(라이브 상시 상태).
                        "groups": [
                            {"jibun": "5*", "dong": "논현동", "location_status": "unlocated",
                             "avg_price_10k": 50000, "avg_area_m2": 100.0, "count": 3},
                            {"jibun": "1**", "dong": "논현동", "location_status": "unlocated",
                             "avg_price_10k": 60000, "avg_area_m2": 120.0, "count": 2},
                        ],
                        "sample_basis": {
                            "scope": "radius", "radius_applied": True, "radius_m": 1500,
                            "located_count": 0, "approximate_count": 0, "unlocated_count": 5,
                            "capped_count": 0,
                            "masked_jibun_count": 5, "masked_jibun_group_count": 2,
                        },
                    }
                }
            }

    async def _ta(*_a, **_k):
        return {"factor": 1.0, "rationale": "테스트 고정"}

    async def _ms(*_a, **_k):
        return None

    import app.services.land_intelligence.land_price_index as lpi
    import app.services.land_intelligence.nearby_map_service as nms
    import app.services.land_intelligence.reb_statistics_service as reb

    _orig = (nms.NearbyMapService, lpi.time_adjust_factor_async, reb.get_market_stats)
    nms.NearbyMapService = _StubNearby            # type: ignore[assignment]
    lpi.time_adjust_factor_async = _ta            # type: ignore[assignment]
    reb.get_market_stats = _ms                    # type: ignore[assignment]
    try:
        # `official_price_per_sqm` 을 주면 VWorld 조회 경로를 타지 않는다(네트워크 없음).
        result = await das.desk_appraisal(
            pnu="1168010100100010000", address="서울특별시 강남구 논현동 1-1",
            area_sqm=300.0, official_price_per_sqm=5_000_000.0,
        )
    finally:
        nms.NearbyMapService, lpi.time_adjust_factor_async, reb.get_market_stats = _orig

    assert result.get("ok") is not False, f"탁상감정이 실패했다: {result.get('message')}"
    note = result.get("comparable_skipped_reason")
    assert note, "반경이 적용됐는데 표본이 0 인데도 **사유가 응답에 없다**(침묵 구간 복원)"
    assert "지번을 가려서" in note, f"마스킹이 원인인데 그 사실을 말하지 않는다: {note}"
    # ★거래사례비교법이 실제로 빠졌는지도 확인 — 사유만 싣고 값은 쓰는 상태면 모순이다.
    # ★R5 리뷰(F-9) — `methods` 가 비면 아래 `not any(...)` 는 **공허하게 참**이 된다.
    assert result.get("methods"), "산정방법이 비었다 — 아래 단언이 공허해진다"
    assert not any(
        "거래사례" in str(m.get("name") or m.get("method") or "")
        for m in (result.get("methods") or [])
    ), "사유를 실으면서 거래사례비교법을 그대로 썼다"


def test_user_inputs_do_not_suppress_comparable_lookup() -> None:
    """★★라이브 적발 — 공시지가·면적을 **둘 다 입력하면** 거래사례비교법이 통째로 사라졌다.

    PNU 는 `if op is None or not area or pnu:` 블록에서만 해석되는데, 아래 거래사례 블록은
    `pnu` 를 요구한다. 그래서 사용자가 두 값을 다 채우면 → PNU 미해석 → 주변 실거래
    **조회 자체를 안 함** → 사유도 없이 공시지가 단독.

    ★프로덕션 실측(강남 논현동 1-1, 2026-08-06):
        공시지가 비움 → pnu=1168010800100010001 · "286건 전부 마스킹" 사유 표시
        면적 비움     → 같음
        둘 다 입력    → pnu=None · comparable_skipped_reason=None  ← 완전 침묵

    ★**사용자가 정보를 더 줄수록 분석이 줄어드는** 역설이었다.

    이 테스트는 게이트 **조건식**을 직접 본다 — 실호출은 VWorld 네트워크에 의존해
    단위 테스트로 태울 수 없고, 조건이 바로 결함의 자리이기 때문이다.
    """
    import inspect

    from app.services.land_intelligence import desk_appraisal_service as mod

    src = inspect.getsource(mod.desk_appraisal)
    gate = [ln for ln in src.splitlines() if ln.strip().startswith("if op is None or not area")]
    assert gate, "PNU 해석 게이트를 찾지 못했다 — 조건이 바뀌었으면 이 테스트를 갱신하라"
    assert "comparable_avg_per_sqm is None" in gate[0], (
        "거래사례 단가를 아직 못 받았는데도 PNU 해석을 건너뛴다 — 사용자가 공시지가·면적을 "
        "입력했다는 이유로 주변 실거래를 조회조차 하지 않게 된다(라이브 실측 결함)"
    )
    # ★비공허 — 조건식이 실제로 네 갈래를 갖는지(하나로 뭉개지지 않았는지) 본다.
    assert gate[0].count(" or ") >= 3, f"게이트가 축소됐다: {gate[0].strip()}"


def test_cross_check_note_does_not_claim_unused_comparables() -> None:
    """★★라이브 적발 — 거래사례를 **하나도 안 썼는데** "실거래 가중 분포"라고 말했다.

    `cross_check` 는 `cmp_unit_price > 0` 일 때만 거래사례 가중을 섞고, 아니면 공시지가
    경로 단독이다. 그런데 `note` 와 신뢰도 `basis` 는 **무조건** 실거래를 언급했다.

    ★같은 함수의 `weight_note` 는 이미 조건부로 정확했다("실거래 확보 시 정밀도↑") —
    저자가 그 구분을 알고 있었는데 두 문구만 따라오지 않은 **한 곳만 고침** 패턴이다.

    ★프로덕션 자기모순 실측(강남 논현동, 2026-08-06): 한 응답 안에서
        weight_note = "…복수 시나리오 교차검증 평균 채택(**실거래 확보 시 정밀도↑**)"
        cross_check.note = "복수 시나리오(보정계수·**실거래 가중 분포**) 교차검증…"
    앞은 "아직 없다", 뒤는 "썼다"고 말한다.

    ★두 모집단을 가른다 — 거래사례 **있는** 호출과 **없는** 호출이 서로 다른 문구를
    내야 한다(둘이 같으면 이 검사는 아무것도 잠그지 못한다).
    """
    import asyncio

    from app.services.land_intelligence.desk_appraisal_service import desk_appraisal

    common = dict(pnu="1168010800100010001", address="", area_sqm=500.0,
                  official_price_per_sqm=15_000_000)
    without = asyncio.run(desk_appraisal(**common))
    with_cmp = asyncio.run(desk_appraisal(**common, comparable_avg_per_sqm=18_000_000))

    note_wo = (without.get("cross_check") or {}).get("note") or ""
    note_w = (with_cmp.get("cross_check") or {}).get("note") or ""
    assert note_wo and note_w, "교차검증 note 가 비었다 — 아래 검사가 공허해진다"
    assert note_wo != note_w, (
        "거래사례 유무와 무관하게 같은 문구를 낸다 — 안 쓴 방법을 썼다고 말하게 된다"
    )
    assert "실거래 가중" not in note_wo, f"거래사례를 안 썼는데 썼다고 말한다: {note_wo}"
    assert "실거래 가중" in note_w, f"거래사례를 썼는데 언급이 없다: {note_w}"

    # 신뢰도 근거도 같은 규율을 따른다.
    def _basis(res: dict) -> str:
        items = (res.get("evidence") or {}).get("evidence") or []
        for it in items:
            if "신뢰도" in str(it.get("label") or ""):
                return str(it.get("basis") or "")
        return ""

    b_wo, b_w = _basis(without), _basis(with_cmp)
    assert b_wo and b_w, "신뢰도 근거가 비었다 — 아래 검사가 공허해진다"
    # ★2026-08-25 계약 변경 — 신뢰도가 **주입 잡음의 CV** 에서 **두 독립 추정의 실제
    #   불일치**로 바뀌었다(`PLAN_appraisal_nondeterminism_2026-08-25.md`). 규율은 그대로다:
    #   안 쓴 방법을 썼다고 말하면 안 되고, 꼬리를 고정해 부분 변이를 막는다.
    assert "거래사례비교법" not in b_wo, f"근거 표기가 안 쓴 방법을 썼다고 말한다: {b_wo}"
    assert "거래사례비교법" in b_w, f"근거 표기가 쓴 방법을 빠뜨렸다: {b_w}"
    assert b_wo.endswith("주변 거래사례를 확보하면 두 방법의 불일치로 산출합니다."), b_wo
    assert b_w.endswith("→ 신뢰도 = 1 − 불일치(하한 0.4)"), b_w

    # ★같은 응답 안에서 두 문구가 서로 모순되지 않아야 한다(라이브에서 실제로 모순이었다).
    wn = without.get("weight_note") or ""
    assert "실거래 확보 시" in wn, f"weight_note 가 바뀌었다 — 이 대조를 갱신하라: {wn}"


def test_molit_parser_preserves_share_dealing_type() -> None:
    """★파서가 원천의 지분거래 구분을 **버리지 않는지** 실제 파서로 확인한다.

    ★왜 이 테스트가 따로 필요한가: 상위 배선 테스트는 `_StubMolit` 을 써서 **파서를
    우회**한다. 그래서 파서에서 이 필드를 지워도 전건 통과했다(변이 실증) —
    이 저장소가 반복해 겪은 "배선 층 미변이"다.

    ★원천 응답 형태는 라이브에서 확인했다(2026-08-06, 강남 202606):
        {"umdNm":"역삼동","jibun":"6**","jimok":"도로",
         "landUse":"제2종일반주거지역","dealAmount":"2,000","dealArea":3.31,
         "shareDealingType":"지분"}
    """
    from integrations.molit_client import MolitClient

    raw = {
        "response": {"body": {"items": {"item": [
            {"umdNm": "역삼동", "jibun": "6**", "jimok": "도로",
             "landUse": "제2종일반주거지역", "dealAmount": "2,000", "dealArea": "3.31",
             "dealYear": "2026", "dealMonth": "6", "dealDay": "10",
             "estateAgentSggNm": "강남구", "shareDealingType": "지분"},
            {"umdNm": "역삼동", "jibun": "7**", "jimok": "대",
             "landUse": "제3종일반주거지역", "dealAmount": "50,000", "dealArea": "100",
             "dealYear": "2026", "dealMonth": "6", "dealDay": "11",
             "estateAgentSggNm": "강남구", "shareDealingType": ""},
        ]}}}
    }
    client = MolitClient.__new__(MolitClient)
    rows = client._parse_trade_items(raw, "land")
    assert len(rows) == 2, f"파싱 건수가 다르다: {rows}"
    # ★두 모집단이 갈린다 — 지분 행과 일반 행이 **서로 다른 값**을 내야 한다.
    assert rows[0].get("share_dealing_type") == "지분", rows[0]
    assert rows[1].get("share_dealing_type") == "", rows[1]
    # 같은 응답에서 지목·용도지역도 살아 있어야 한다(층화의 재료).
    assert rows[0].get("jimok") == "도로" and rows[1].get("jimok") == "대"
    assert rows[0].get("land_use") == "제2종일반주거지역"


def test_desk_appraisal_carries_land_market_stats() -> None:
    """★토지 층화 통계가 **탁상감정 응답까지** 흐르는지.

    ★`scripts/mutate_changed.py` 가 이 구간이 **통째로 무잠금**임을 잡아냈다 —
    `land_market_stats` · `land_market_stats_note` · `target_land_use` 전달 · 통계 캡처를
    전부 지워도 95개 테스트가 통과했다. 내가 추가한 배선 락은 `NearbyMapService.build()`
    층만 봤고, 그 위(desk_appraisal)는 비어 있었다.

    ★두 모집단을 가른다 — 통계가 **있는** 경우와 **없는** 경우가 서로 다른 응답을 내야 한다.
    """
    from unittest.mock import patch


    fake_stats = {
        "unit_price_per_sqm": 1_190_476, "sample_count": 5, "layer": "dong_zone",
        "layer_label": "법정동 · 용도지역", "scope_label": "역삼동 · 제2종일반주거지역",
        "time_adjusted": False, "share_deal_count_excluded": 3,
        "avg_per_sqm": 1_190_476, "min_per_sqm": 1_000_000, "max_per_sqm": 1_300_000,
        "excluded_outliers": 0, "time_adjusted_count": 0, "masked_jibun_count": 5,
    }

    class _FakeNearby:
        def __init__(self, stats):
            self._stats = stats

        called: list = []

        async def build(self, **kwargs):
            _FakeNearby.called.append(kwargs)
            # ★★전달 **여부**만 보면 값이 틀려도 통과한다(변이 실증) — 실제 값을 본다.
            #   그리고 이 단언은 한 번 리팩토링 중 **유실됐다가** 도구가 다시 잡았다.
            assert kwargs.get("target_land_use") == "제2종일반주거지역", (
                f"용도지역이 그대로 전달되지 않는다: {kwargs.get('target_land_use')!r}"
            )
            # ★지목도 전달돼야 한다 — 안 넘기면 `대` 와 `도로` 가 한 통에 섞여
            #   단가가 자릿수로 틀린다(라이브 실측: 논현동 공시지가의 0.54배).
            assert kwargs.get("target_jimok") == "대", (
                f"지목이 그대로 전달되지 않는다: {kwargs.get('target_jimok')!r}"
            )
            # ★용도지역이 실제로 넘어오는지 — 안 넘기면 `dong_zone` 층까지 못 내려간다.
            assert "target_land_use" in kwargs, "용도지역이 전달되지 않는다"
            return {"categories": {"land_trade": {"groups": [], "sample_basis": {}}},
                    "land_dong_stats": self._stats}

    common = dict(pnu="1168010800100010001", address="", area_sqm=500.0,
                  official_price_per_sqm=15_000_000)

    # ★`NearbyMapService` 는 함수 안에서 지연 import 된다 — 원본 모듈을 패치해야 잡힌다.
    from app.services.external_api import vworld_service as vw_mod
    from app.services.land_intelligence import nearby_map_service as nm_mod

    # ★VWorld 도 스텁한다 — 안 하면 이 테스트가 **외부 네트워크에 의존**해
    #   CI(키 없음)와 로컬에서 다르게 동작한다. 용도지역은 여기서 결정론적으로 준다.
    class _FakeVWorld:
        async def geocode_address(self, *_a, **_k):
            return {}

        async def get_land_characteristics(self, *_a, **_k):
            return {"zone_type": "제2종일반주거지역", "land_category": "대"}

    stack = patch.object(vw_mod, "VWorldService", _FakeVWorld)
    stack.start()
    try:
        _run_land_stats_assertions(fake_stats, common, nm_mod, _FakeNearby)
    finally:
        stack.stop()
    return


def _run_land_stats_assertions(fake_stats, common, nm_mod, _FakeNearby) -> None:
    import asyncio
    from unittest.mock import patch

    from app.services.land_intelligence import desk_appraisal_service as mod

    with patch.object(nm_mod, "NearbyMapService", lambda: _FakeNearby(fake_stats)):
        with_stats = asyncio.run(mod.desk_appraisal(**common))
    with patch.object(nm_mod, "NearbyMapService", lambda: _FakeNearby(None)):
        without = asyncio.run(mod.desk_appraisal(**common))

    # ★★단언이 **실행되긴 했는지** — build 가 안 불리면 위 검증은 공허하다.
    assert _FakeNearby.called, "NearbyMapService.build 가 호출되지 않았다 — 검증이 공허하다"

    # ① 통계가 응답에 실린다
    assert with_stats.get("land_market_stats") == fake_stats, "통계가 응답에 없다"
    # ② 고지도 함께 — 값만 주면 "내 땅 시세"로 오독한다
    note = with_stats.get("land_market_stats_note") or ""
    assert "역삼동" in note and "개별 필지 위치는 반영되지 않았습니다" in note, note
    # ③ ★두 모집단이 갈린다 — 통계가 없으면 둘 다 None(없는 말을 지어내지 않는다)
    assert without.get("land_market_stats") is None
    assert without.get("land_market_stats_note") is None


def test_lookup_failure_path_says_why_and_is_actually_exercised() -> None:
    """★★전수 감사 적발 — **예외 경로가 어떤 테스트에도 안 걸려 있었다**.

    `except Exception` 안의 사유 문구·`comparable_basis = None` 을 전부 지워도 통과했다
    (`scripts/mutate_changed.py` 세션 전수 감사). MOLIT·지오코더 장애가 정확히 이 경로인데,
    그때 사용자가 무엇을 보는지 아무도 확인하지 않고 있었다.

    ★두 모집단을 가른다 — 조회가 **실패한** 경우와 **성공했지만 표본 0** 인 경우가 서로
    다른 문구를 내야 한다(둘이 같으면 사용자는 "거래가 없다"로 오독한다).
    """
    import asyncio
    from unittest.mock import patch

    from app.services.external_api import vworld_service as vw_mod
    from app.services.land_intelligence import desk_appraisal_service as mod
    from app.services.land_intelligence import nearby_map_service as nm_mod

    class _FakeVWorld:
        async def geocode_address(self, *_a, **_k):
            return {}

        async def get_land_characteristics(self, *_a, **_k):
            return {"zone_type": "제2종일반주거지역", "land_category": "대"}

    class _Boom:
        async def build(self, **_k):
            raise RuntimeError("MOLIT 장애 시뮬레이션")

    class _Empty:
        async def build(self, **_k):
            return {
                "categories": {"land_trade": {"groups": [], "sample_basis": {
                    "scope": "radius", "radius_applied": True, "radius_m": 1500,
                    "located_count": 0, "approximate_count": 0, "unlocated_count": 0,
                    "capped_count": 0,
                }}},
                "land_dong_stats": None,
            }

    common = dict(pnu="1168010800100010001", address="", area_sqm=500.0,
                  official_price_per_sqm=15_000_000)

    with patch.object(vw_mod, "VWorldService", _FakeVWorld):
        with patch.object(nm_mod, "NearbyMapService", _Boom):
            failed = asyncio.run(mod.desk_appraisal(**common))
        with patch.object(nm_mod, "NearbyMapService", _Empty):
            empty = asyncio.run(mod.desk_appraisal(**common))

    fail_note = failed.get("comparable_skipped_reason") or ""
    empty_note = empty.get("comparable_skipped_reason") or ""

    # ★★부분 문자열만 보면 나머지가 깨져도 통과한다(전수 감사에서 마지막 문장이 생존).
    #   사용자가 읽는 문장이므로 **전문을 리터럴로** 잠근다.
    assert fail_note == (
        "실거래 자료를 불러오지 못해 거래사례비교법을 쓰지 못했습니다 — "
        "이 지역에 거래가 없다는 뜻이 아니라 조회가 실패했다는 뜻입니다. "
        "공시지가기준법 단독으로 산정했습니다."
    ), fail_note
    # ★두 모집단이 실제로 갈린다 — 같으면 이 검사가 아무것도 잠그지 못한다.
    assert fail_note != empty_note, "실패와 표본 0 이 같은 문구를 낸다"
    # 실패 경로에서는 근거도 남기지 않는다(값이 없으면 근거도 없다).
    assert failed.get("comparable_basis") in (None, {}), failed.get("comparable_basis")


def test_cross_check_wording_is_locked_by_literal() -> None:
    """★★전수 감사 적발 — #568 에서 **조건만 잠그고 문구는 안 잠갔다**.

    그때 "변이 3/3 CAUGHT" 라고 보고했지만, 내가 고른 변이가 전부 **조건 분기**였다.
    문구 자체를 `"__MUTATED__"` 로 바꾸면 그대로 통과한다(전수 감사에서 생존).
    사용자가 읽는 문장이므로 **리터럴로 잠근다**.
    """
    import asyncio
    from unittest.mock import patch

    from app.services.external_api import vworld_service as vw_mod
    from app.services.land_intelligence import desk_appraisal_service as mod

    class _FakeVWorld:
        async def geocode_address(self, *_a, **_k):
            return {}

        async def get_land_characteristics(self, *_a, **_k):
            return {"zone_type": "제2종일반주거지역", "land_category": "대"}

    common = dict(pnu="1168010800100010001", address="", area_sqm=500.0,
                  official_price_per_sqm=15_000_000)

    with patch.object(vw_mod, "VWorldService", _FakeVWorld):
        without = asyncio.run(mod.desk_appraisal(**common))
        with_cmp = asyncio.run(mod.desk_appraisal(**common, comparable_avg_per_sqm=18_000_000))

    note_wo = (without.get("cross_check") or {}).get("note") or ""
    note_w = (with_cmp.get("cross_check") or {}).get("note") or ""

    # ★2026-08-25 문구 갱신 — 종전 문구는 난수 5회를 "교차검증"이라 불렀다. 이제 산출이
    #   **결정적 가정 격자**이므로 문장도 "가정 민감도"라고 말한다(`PLAN_appraisal_…` §3).
    assert note_wo == (
        "가정 민감도 — 그밖의요인 ±5% 를 편 결정적 범위입니다. 거래사례를 확보하지 못해 "
        "공시지가 기준 경로 하나만 계산했으며, 이는 **교차검증이 아닙니다**."
    ), note_wo
    assert note_w == (
        "가정 민감도 — 그밖의요인 ±5%·실거래 가중 0.3~0.5 를 편 결정적 범위입니다. "
        "독립된 평가 주체의 교차검증이 아니라 같은 산식의 가정 변동입니다."
    ), note_w


def test_every_skip_path_says_why() -> None:
    """★R6 리뷰(F-3) — "왜 거래사례비교를 안 썼는지"에 **침묵하는 갈래가 없어야** 한다.

    ★PNU 부재 갈래가 무테스트였다(변이 생존 실측) — 그 갈래는 조회를 **시도조차 못 한**
    경우인데, 사용자에게는 다른 갈래와 똑같이 "방법이 그냥 사라진" 것으로 보인다.

    ★문구는 **아는 만큼만** 말해야 한다: 조회가 실패한 것과 거래가 없는 것은 다르다.
    """
    import asyncio

    from app.services.land_intelligence.desk_appraisal_service import desk_appraisal

    # PNU 를 확정하지 못한 입력 — 위 블록 자체를 타지 않는 갈래.
    result = asyncio.run(
        desk_appraisal(
            pnu=None, address="", area_sqm=300.0, official_price_per_sqm=1_000_000,
        )
    )
    note = result.get("comparable_skipped_reason")
    assert note, "PNU 부재 갈래가 사유 없이 조용히 폴백한다"
    assert "거래가 없" not in note, (
        f"조회를 못 한 것을 '거래가 없다'로 말하면 안 된다: {note}"
    )
    # ★전수 감사 적발 — 존재·부정만 보면 문구가 깨져도 통과한다. 전문을 잠근다.
    assert note == (
        "대상지 필지번호(PNU)를 확정하지 못해 주변 실거래를 조회하지 못했습니다 — "
        "공시지가기준법 단독으로 산정했습니다."
    ), note


def test_report_model_carries_the_skip_reason() -> None:
    """★★R2 리뷰(H-2) — PDF/PPTX/DOCX 보고서 모델에 사유가 **실제로 실리는지** 실호출로 본다.

    ★변이 실증: 어댑터의 사유 블록을 지워도 73개 테스트가 전부 통과했다 — 그 락을
    vitest 파일에만 뒀기 때문이다. **백엔드 변경은 백엔드가 잠가야 한다.**
    그리고 소스 검사가 아니라 **실호출**이어야 한다(M-2 에서 배운 것: 소스 검사는
    텍스트를 볼 뿐 행위를 태우지 않는다).

    이건 은행 제출용 산출물이다. 화면에서는 "왜 안 썼는지" 말하면서 PDF 에서는 방법이
    그냥 사라지면, 읽는 사람은 "이 지역엔 거래가 없다"로 오독한다.
    """
    from app.services.report.render.appraisal_adapter import (
        build_report_model_from_appraisal,
    )

    reason = (
        "반경 1.5km 내에서 위치가 확인된 거래가 없습니다 — 위치 미확인 5건은 단가 산정에 "
        "쓰지 않습니다. 위치 미확인 중 5건은 공개 실거래 자료가 지번을 가려서 제공해"
        "(예: 5*, 1**) 위치를 확인할 수 없습니다."
    )
    result = {
        "ok": True,
        "appraised_price_per_sqm": 5_000_000,
        "appraised_total_won": 1_500_000_000,
        "area_sqm": 300.0,
        "confidence": 0.7,
        "range_per_sqm": {"low": 4_500_000, "high": 5_500_000},
        "methods": [
            {"method": "공시지가기준법", "unit_price": 5_000_000, "rationale": "공시지가 × 시점수정"}
        ],
        "weight_note": "공시지가기준법 단독",
        "comparable_skipped_reason": reason,
        "disclaimer": "참고용",
    }
    model = build_report_model_from_appraisal(result, address="서울특별시 강남구 논현동 1-1")

    # 모델 어딘가가 아니라 **산정방법 섹션**에 실려야 한다(방법이 빠진 자리에서 설명한다).
    method_sections = [
        sec for sec in model.sections if "산정방법" in (sec.title or "")
    ]
    assert method_sections, "산정방법 섹션이 없다 — 이 테스트가 공허해진다"
    rendered = "\n".join(
        str(getattr(b, "paragraphs", "")) for sec in method_sections for b in sec.blocks
    )
    assert "지번을 가려서" in rendered, (
        "보고서 모델에 거래사례비교법 제외 사유가 없다 — 은행 제출본에서 방법이 "
        "아무 설명 없이 사라진다"
    )


def test_legacy_payload_never_treats_masked_as_located() -> None:
    """레거시 페이로드(`location_status` 부재)에서 `coord_precision="masked"` 처리.

    ★R3 리뷰(F-9) — 4번째 enum 값을 추가하면서 양쪽 레거시 폴백을 손대지 않아
    **백엔드 `approximate` / 프론트 `located`** 로 두 미러가 갈려 있었다.
    마스킹은 좌표가 **없다**는 뜻이므로 정밀을 주장하지 않는다.

    ★정직 표기 두 가지:
    ① 이 조합(`location_status` 부재 + `lat` 존재 + `masked`)은 **현재 생산 경로에서
       도달 불가**다(마스킹 그룹은 질의를 안 만들어 `lat` 이 없다). 레거시/스큐 방어다.
    ② **백엔드 쪽은 이 테스트로 잠기지 않는다** — `masked` 분기를 지워도 `else` 가
       `approximate` 를 주고 둘 다 `located` 가 아니라 반환값이 같다(실측 확인).
       실제로 갈렸던 것은 **프론트**(`!== "dong"` → `located`)이고 아래 단언이 그것을 잡는다.
       "이 테스트가 두 곳을 다 잠근다"고 쓰면 거짓이 된다.
    """
    from app.services.market.comparable_sample import select_located_groups

    legacy = {
        "groups": [
            # location_status 가 없고 lat 은 있는 옛 형태 — 폴백 가지를 태운다.
            {"jibun": "5*", "lat": 36.0, "lon": 129.0, "coord_precision": "masked",
             "avg_price_10k": 50000, "avg_area_m2": 84.0, "count": 3},
            {"jibun": "736", "lat": 36.001, "lon": 129.001, "coord_precision": "parcel",
             "avg_price_10k": 53000, "avg_area_m2": 84.0, "count": 1},
        ],
    }
    located, _ = select_located_groups(legacy)
    assert [g["jibun"] for g in located] == ["736"], (
        "마스킹 그룹이 위치 확인분으로 취급됐다 — 좌표가 없다는 뜻인데 정밀을 주장했다"
    )
    # 프론트 미러도 같은 답을 내야 한다(소스로 계약 확인 — 실행은 vitest·CI).
    mirror = (
        _API_ROOT.parent.parent / "apps/web/lib/market/comparable-sample.ts"
    ).read_text(encoding="utf-8")
    assert re.search(r'coord_precision === "masked"\)\s*return "unlocated"', mirror), (
        "프론트 레거시 폴백이 masked 를 다루지 않는다 — 두 미러가 갈린다"
    )


def test_shared_golden_matches_backend_output_exactly() -> None:
    """★★R2 리뷰(M-3) — 백엔드와 프론트 미러가 **같은 값**을 내는지 값으로 잠근다.

    ★초판의 "문구 일치 불변식"은 TS 소스에 한국어 조각이 들어 있는지 **grep** 할 뿐이라
    값 대조가 아니었다. 실제로 반경 표기가 갈려 있었다 —
    1250m 에서 백엔드 `1.25km` / 미러 `1.3km`, 게다가 같은 TS 파일 안에서
    `sampleLabel` 은 `1.25km` 를 내 **한 파일에 세 표기**가 공존했다.
    현재 호출부가 전부 라운드 값이라 잠복해 있었을 뿐이다.

    → 두 구현이 **공유 골든 파일**을 본다. 이 테스트는 백엔드 출력이 그 파일과 같은지 보고,
      프론트 vitest 골든이 TS 출력이 같은 파일과 같은지 본다. 어느 쪽 문구를 바꾸든
      그쪽이 깨지므로 두 구현이 조용히 갈라질 수 없다.
    """
    import json

    from app.services.market.comparable_sample import SampleBasis, no_sample_reason

    golden_path = (
        _API_ROOT.parent.parent
        / "apps/web/lib/market/__tests__/fixtures/no-sample-reason.cases.json"
    )
    assert golden_path.exists(), f"공유 골든이 없다: {golden_path}"
    cases = json.loads(golden_path.read_text(encoding="utf-8"))
    assert cases, "공유 골든이 비었다 — 아래 대조가 공허해진다"
    # ★비공허성 — 케이스가 실제로 여러 갈래를 덮는지 확인한다(전부 같은 갈래면 무판별).
    #   ★R5(F-5) — 표본이 **있는** 케이스는 사유가 `None` 이므로(정상) 사유 중복 검사에서
    #   제외한다. 그 케이스들은 `label`/`exclusion` 축으로 판별한다.
    reasons = [c["expected"] for c in cases if c["expected"] is not None]
    assert len(set(reasons)) == len(reasons), "골든에 중복 사유가 있다"
    labels = {(c["expected_label"], c["expected_exclusion"]) for c in cases}
    assert len(labels) >= 5, f"label/exclusion 갈래가 {len(labels)}종뿐 — 판별력이 부족하다"
    assert any(c["masked"] > 0 and c["masked"] <= c["unlocated"] for c in cases), "포함 갈래 없음"
    assert any(c["masked"] > c["unlocated"] for c in cases), "스큐 갈래 없음"
    assert any(c["masked"] == 0 for c in cases), "마스킹 없는 갈래 없음"
    assert any(
        c["radius_m"] and c["radius_m"] % 500 != 0 for c in cases
    ), "비라운드 반경 케이스 없음(표기 갈림 미검증)"
    # ★R3 리뷰(F-6·F-2) — 축을 더 덮는다.
    #   ① 카운트 ≥ 1000: 천단위 구분자를 지우는 변이가 **생존**했다(전 케이스가 3자리 미만).
    #      게다가 미러의 `toLocaleString()` 은 로케일을 타서(de-DE `5.601`) 선언한 값 등가가
    #      비콤마 로케일에서 거짓이 됐다 — M-3 가 반경에서 잡은 것과 같은 클래스다.
    #   ② `scope` 3종: `sigungu`/`unknown` 가지가 **양쪽 다 무테스트**였다.
    assert any(c["unlocated"] >= 1000 or c["masked"] >= 1000 for c in cases), "천단위 케이스 없음"
    assert {c["scope"] for c in cases} >= {"radius", "sigungu", "unknown"}, "scope 갈래 미달"

    # ★R5 리뷰(F-5) — 골든이 `no_sample_reason` **만** 덮고 있었다. `label`/`exclusion_note`
    #   ↔ `sampleLabel`/`exclusionNote` 는 지금 일치하지만 **값 대조가 없어**, R4 C-1
    #   (한쪽만 고쳐서 갈림)과 같은 계열이 여기서 재발할 수 있었다.
    assert any(c.get("located", 0) > 0 for c in cases), "표본이 있는 갈래가 없다(label 미검증)"
    assert any(c.get("capped", 0) > 0 for c in cases), "상한 초과 갈래가 없다"

    for c in cases:
        basis = SampleBasis(
            scope=c["scope"], radius_applied=c["scope"] == "radius", radius_m=c["radius_m"],
            located_count=c.get("located", 0), approximate_count=c["approximate"],
            unlocated_count=c["unlocated"], capped_count=c.get("capped", 0),
            masked_jibun_count=c["masked"], masked_jibun_group_count=c["masked_groups"],
        )
        assert basis.label() == c["expected_label"], (
            f"label 이 공유 골든과 다르다(scope={c['scope']}) — 미러도 함께 맞춰라"
        )
        assert basis.exclusion_note() == c["expected_exclusion"], (
            f"exclusion_note 가 공유 골든과 다르다(scope={c['scope']}) — 미러도 함께 맞춰라"
        )
        if c["expected"] is None:
            continue
        assert no_sample_reason(basis) == c["expected"], (
            f"백엔드 출력이 공유 골든과 다르다(scope={c['scope']} r={c['radius_m']}) — "
            "문구를 바꿨으면 골든을 재생성하고 프론트 미러도 함께 맞춰라"
        )


def test_mirror_does_not_drift_from_backend_wording_or_locale() -> None:
    """미러에 **이미 폐기된** 문구·로케일 비고정 호출이 남았는지 본다(스냅샷 검사).

    ★R5 리뷰(F-6) 표기 강등 — 이 테스트는 "미러가 갈라졌는지 잡는다"는 **일반 주장을 할 수
    없다**. 목록에 없는 새 갈림은 못 잡는다(리뷰어 실측: 미러만 `why` 를 *새* 문구로 바꾸면
    전건 통과). **구조적 재발 방지는 공유 골든 JSON 이 한다** — 양측이 같은 파일과 대조하므로
    어느 쪽을 바꿔도 그쪽이 깨진다. 이 테스트는 그 위에 얹은 보조물이다.

    ★C-1 실측: R3 에서 F-5 문구를 **백엔드만** 고치고 미러를 놓쳐 공유 골든 13건 중
    3건이 어긋났다(vitest 확정 실패). 사용자가 실제로 읽는 화면에는 없애겠다고 선언한
    "그 밖에"(서로소 단정 → 이중계수 오독)가 **그대로 출하될 뻔했다**.
    → pytest 로 잡을 수 있었는데 안 잡았다. 전역 전파방지 미이행이다.

    ★M-4 실측: `toLocaleString()` 을 인자 없이 부르면 **브라우저 로케일**을 탄다
    (de-DE `5.601` vs 백엔드 `5,601`). CI 는 en-US 라 골든 케이스로는 **못 잡는다** —
    로케일 고정은 **소스로** 잠가야 한다.
    """
    mirror = (
        _API_ROOT.parent.parent / "apps/web/lib/market/comparable-sample.ts"
    ).read_text(encoding="utf-8")

    # ① 폐기된 문구가 미러에 남아 있으면 두 구현이 갈린 것이다.
    for dead in ("그 밖에", "를 찾지 못했습니다"):
        assert dead not in mirror, (
            f"미러에 폐기된 문구가 남아 있다: {dead!r} — 백엔드만 고치고 미러를 놓쳤다"
        )

    # ② 로케일 비고정 호출이 남아 있으면 값 등가 계약이 비콤마 로케일에서 거짓이 된다.
    #   ★R5 리뷰(F-7) — 스코프를 **탁상감정 표기 파일까지** 넓힌다. 종전엔 미러 한 파일만
    #   봐서, 같은 PR 이 고친 `desk-appraisal.ts` 의 `won()` 은 되돌려도 무검출이었고
    #   `eok()` 은 `toLocaleString(undefined, …)` 로 여전히 브라우저 로케일을 타고 있었다.
    web_root = _API_ROOT.parent.parent / "apps/web/lib"
    for rel in ("market/comparable-sample.ts", "land/desk-appraisal.ts"):
        src = (web_root / rel).read_text(encoding="utf-8")
        assert not re.search(r"toLocaleString\(\s*\)", src), (
            f"{rel} 에 로케일 비고정 `toLocaleString()` 이 남아 있다 — de-DE 에서 `5.601` 이 "
            "돼 '백엔드와 같은 값' 계약이 거짓이 된다(CI 는 en-US 라 골든으로 못 잡는다)"
        )
        assert not re.search(r"toLocaleString\(\s*undefined", src), (
            f"{rel} 에 `toLocaleString(undefined, …)` 가 남아 있다 — 명시적으로 보이지만 "
            "실제로는 브라우저 로케일이다(de-DE `1.234,56`)"
        )


def test_frontend_mirror_reads_the_shared_golden() -> None:
    """미러가 공유 골든을 소비하도록 **작성돼 있는지** 소스로 확인한다.

    ★R3 리뷰(F-4) 정직 표기 — 이 검사는 **소스 grep 이다**. `it.skip` 으로 바꾸거나
    루프를 죽은 분기에 넣으면 통과한다. 진짜 방벽은 이 테스트가 아니라
    **CI 가 vitest 전체를 돌린다는 사실**이다(`.github/workflows/ci.yml` — `propai-platform/**`
    변경 PR 에서 `pnpm test:run` 실행, 판별 실패 시 fail-safe 전체 실행. vitest include
    글롭이 `lib/**/*.test.ts` 라 신규 파일도 덮는다). 이 테스트의 역할은
    **골든 파일만 만들어 두고 미러 소비를 잊는 것**을 막는 얕은 그물이다.
    "반쪽 계약을 막는다"고 쓰면 과대 표기가 된다.
    """
    mirror_test = (
        _API_ROOT.parent.parent
        / "apps/web/lib/market/__tests__/comparable-sample.golden.test.ts"
    ).read_text(encoding="utf-8")
    assert "no-sample-reason.cases.json" in mirror_test, (
        "프론트 골든이 공유 케이스 파일을 읽지 않는다 — 값 대조가 백엔드 한쪽만 남는다"
    )
    # 읽기만 하고 대조를 안 하면 역시 공허다 — 기대값 필드를 쓰는지 본다.
    assert re.search(r"\.expected\b", mirror_test), "골든을 읽고도 expected 를 대조하지 않는다"


def test_sample_basis_method_and_module_function_agree() -> None:
    """★R1 리뷰(M-4) 락 — 메서드와 모듈 함수가 **같은 답**을 낸다(정의는 한 곳).

    ★변이 실증: 메서드의 위임을 걷어내고 옛 문장을 되돌려도 70개 테스트가 전부 통과했다.
    그게 M-4 가 지적한 실제 피해의 형태다 — 유일한 기존 소비처(`ai/assistant_agent`)가
    메서드를 쓰고 있어서, 모듈 함수만 고치면 **AI 비서는 마스킹 사유를 영영 말하지 않는다**.
    두 구현이 갈렸다는 사실 자체가 아무 데서도 잡히지 않았다.
    """
    from app.services.market.comparable_sample import SampleBasis, no_sample_reason

    cases = [
        # (unlocated, approximate, masked_deals, masked_groups)
        (5, 0, 5, 2),      # 마스킹이 지배 원인
        (50, 30, 1, 1),    # 마스킹은 소수 — 나머지가 사라지면 안 된다
        (0, 7, 0, 0),      # 마스킹 없음
        (0, 0, 0, 0),      # 진짜 무자료
        (2, 0, 9, 3),      # 스큐로 포함 관계가 깨진 경우
    ]
    for un, ap, md, mg in cases:
        b = SampleBasis(
            scope="radius", radius_applied=True, radius_m=1000,
            located_count=0, approximate_count=ap, unlocated_count=un,
            capped_count=0, masked_jibun_count=md, masked_jibun_group_count=mg,
        )
        assert b.no_sample_reason() == no_sample_reason(b), (
            f"메서드와 모듈 함수가 다른 답을 낸다(un={un} ap={ap} md={md}) — "
            "소비처가 어느 쪽을 부르냐에 따라 사용자가 다른 설명을 받는다"
        )


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
