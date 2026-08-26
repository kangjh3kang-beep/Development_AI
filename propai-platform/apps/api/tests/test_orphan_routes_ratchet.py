"""배선 안 된 라우트가 **늘어나지 않게** 잠근다(래칫).

【왜 래칫인가】현재 소비처 0 이 123 건이다. 전부 결함은 아니다 — 정당한 백엔드 내부용이 섞인다.
그래서 **0 을 요구하지 않는다**(요구하면 정당한 라우트를 지우게 만들거나, 테스트를 끄게 된다).
대신 **새로 생기는 것만** 막는다: 새 라우트를 만들면서 화면에 안 붙이면 여기서 드러난다.

【이 저장소가 이 결함으로 데인 이력】
  · P2 매입전략 — 백엔드 배포됐는데 프론트 소비처 0(2026-08-16 인계서가 미결로 남김)
  · 종합 부지분석 — 라우트 live 인데 생성허브·랜딩 어디에도 진입 카드 없음
  · AVM 항공영상 — Next 라우트가 백엔드에 가려져 404, 실패는 "생략됩니다"로 위장

【기준선을 줄이는 것이 목표다】
`orphan_routes_baseline.txt` 에서 항목을 **지우면** 그 라우트는 다시 고아가 될 수 없다.
배선하거나 삭제한 뒤 기준선에서 빼라 — 그게 이 부채를 갚는 방법이다.

【★2026-08-20 — 기준선이 **둘**로 갈렸다】
도구가 양방향으로 틀렸다(과대·과소). 자세한 것은 `scripts/orphan_routes.py` 독스트링.
  · `orphan_routes_baseline.txt`  = **확정 고아**(124)
  · `orphan_routes_undecided.txt` = **판정 불가**(13, 동적 세그먼트)
판정 불가를 고아로 세면 **없는 결함을 만들고**, 소비로 세면 **진짜 고아를 숨긴다**.
그래서 어느 쪽으로도 흡수하지 않고 **자기 파일에서 양방향 래칫**으로 잠근다 —
줄어도(=결론이 났는데 기록 안 함) 늘어도(=새 동적 자리) 여기서 드러난다.
"""
from __future__ import annotations

import os
import sys

# tests/ → apps/api/tests 기준으로 propai-platform/scripts 를 찾는다(3단계 상위).
_SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))
sys.path.insert(0, _SCRIPTS)

_BASELINE = os.path.join(os.path.dirname(__file__), "orphan_routes_baseline.txt")
_UNDECIDED = os.path.join(os.path.dirname(__file__), "orphan_routes_undecided.txt")


#: 종류 어휘는 **닫혀 있다.** 열어 두면 다음 사람이 새 낱말을 만들어 같은 것을 두 이름으로
#: 부르고, 그 순간 "몇 건이 진짜 부채인가"에 다시 답할 수 없게 된다.
_KINDS = {
    "admin-cron": "운영·배치 전용 — 프론트 소비처가 없는 것이 정상",
    "internal": "백엔드 내부/서버간 호출 전용",
    "legacy-suspect": "소비처 0 이고 구 트리·구 계약 — 삭제 후보이나 미확정",
    "debt": "배선해야 하는데 안 됐다 — 진짜 부채",
    "unclassified": "★아직 안 봤다(유추 금지)",
}
#: 아직 열어 보지 않은 것. **늘어날 수 없다**(줄이는 방향으로만 움직인다).
_UNCLASSIFIED = "unclassified"

#: `unclassified` 상한 — 형식 승격 시점(2026-08-26)의 실측값. 한 건을 열어 분류할 때마다
#: 내려간다. ★이 수를 **올리는 커밋은 새 미분류를 들여오는 것**이므로 실패한다.
_UNCLASSIFIED_CEILING = 130


def _rows(path: str) -> list[tuple[str, str, str]]:
    """`경로 <TAB> 종류 <TAB> 사유` 로 읽는다.

    ★탭이 없는 줄도 **조용히 통과시키지 않는다** — 종류를 빈 문자열로 돌려주고
      형식 검사가 잡는다. 여기서 관대하면 사유 없는 줄이 다시 스며든다.
    """
    out: list[tuple[str, str, str]] = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            if not ln.strip() or ln.lstrip().startswith("#"):
                continue
            parts = [c.strip() for c in ln.rstrip("\n").split("\t")]
            route = parts[0]
            kind = parts[1] if len(parts) > 1 else ""
            reason = parts[2] if len(parts) > 2 else ""
            out.append((route, kind, reason))
    return out


def _load(path: str) -> set[str]:
    """**경로만** 돌려준다(래칫의 집합 연산용). 종류·사유는 `_rows` 로 본다.

    `#` 주석줄은 무시한다 — 수치가 움직인 **사유를 파일 안에** 남기기 위한 것이다.
    """
    return {r for r, _k, _why in _rows(path)}


def _load_baseline() -> set[str]:
    return _load(_BASELINE)


def test_배선안된_라우트가_늘어나지_않는다():
    from orphan_routes import orphans  # type: ignore[import-not-found]

    current = {f for f, _m, _p in orphans()}
    baseline = _load_baseline()

    # ★공허한 초록 방지 — 조회기가 죽으면 current 가 비고 "새 고아 0"이 참이 된다.
    # ★이 하한은 **파일 파손·조회기 사망 탐지용**이다. 배선을 갚아 정당하게 내려가면
    #   막지 말고 이 숫자를 낮춰라(부채 상환을 벌하지 않는다).
    assert len(baseline) > 50, "기준선이 비정상적으로 작다 — 파일이 깨졌는지 확인하라"
    assert len(current) > 0, "소비처 0 이 한 건도 없다 — 조회기가 죽었을 가능성이 높다"

    added = sorted(current - baseline)
    assert not added, (
        "새 라우트를 만들고 화면에 붙이지 않았다 — 기능이 존재하지만 아무도 못 쓴다:\n"
        + "\n".join(f"  {r}" for r in added)
        + "\n→ 프론트에 배선하거나, 백엔드 내부용이면 기준선에 추가하고 **사유를 커밋에 남겨라**."
    )


def test_판정불가가_양방향으로_잠긴다():
    """★판정 불가를 고아·소비 어느 쪽으로도 조용히 흡수하지 못하게 한다."""
    from orphan_routes import undecided_routes  # type: ignore[import-not-found]

    current = {f for f, _m, _p in undecided_routes()}
    baseline = _load(_UNDECIDED)

    # ★공허한 초록 방지 — 분류기가 죽어 전부 빈 집합이면 두 차집합이 모두 참이 된다.
    # ★파손 탐지용 하한 — 정당하게 결론이 나 줄어들면 이 숫자를 낮춰라.
    # ★2026-08-21: 13 → 4. 메서드 게이트로 9건이 **정당하게 결론나** 내려갔으므로 하한을 낮춘다
    #   (이 하한은 파일 파손 탐지용이지 부채 목표가 아니다 — 위 주석의 지시를 그대로 따른 것).
    assert len(baseline) > 2, "판정 불가 기준선이 비었다 — 파일이 깨졌는지 확인하라"
    assert len(current) > 0, "판정 불가가 0건 — 동적 세그먼트 분류기가 죽었을 가능성이 높다"

    added = sorted(current - baseline)
    removed = sorted(baseline - current)
    assert not added, (
        "마지막 세그먼트를 동적으로 부르는 새 자리가 생겼다 — 이 라우트들이 실제로 불리는지"
        " **호출부를 열어** 확인하고 결론을 파일에 남겨라(고아면 기준선으로, 소비면 삭제):\n"
        + "\n".join(f"  {r}" for r in added)
    )
    assert not removed, (
        "판정 불가였던 라우트가 사라졌다 — 결론이 났으면 파일에서 지우고 **사유를 커밋에 남겨라**."
        " 조용히 사라지면 진짜 고아가 숨는다:\n" + "\n".join(f"  {r}" for r in removed)
    )


def test_두_기준선은_서로소다():
    """★같은 라우트가 양쪽에 있으면 한쪽 래칫이 반드시 거짓말을 한다."""
    both = _load_baseline() & _load(_UNDECIDED)
    assert not both, f"확정 고아와 판정 불가에 동시에 있다: {sorted(both)}"


def test_기준선이_줄면_알려준다():
    """★부채를 갚았는데 기준선을 안 줄이면 그 라우트가 다시 고아가 될 수 있다."""
    from orphan_routes import orphans  # type: ignore[import-not-found]

    current = {f for f, _m, _p in orphans()}
    removed = sorted(_load_baseline() - current)
    assert not removed, (
        "배선이 끝난 라우트가 기준선에 남아 있다 — 기준선에서 지워라(다시 고아가 되는 것을 막는다):\n"
        + "\n".join(f"  {r}" for r in removed)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 메서드 게이트 잠금 — 2026-08-21
#
# ★왜 두 모집단을 다 단언하나: "9건이 판정 불가에 **없다**"만 쓰면 분류기가 죽어 전부 빈
#   집합이 돼도 참이 된다(부재 단언은 그 자체로 잠금이 아니다). 그래서 같은 실행에서
#   **① 그것들이 확정 고아에 실제로 있다** 와 **② 메서드가 일치하는 것들은 여전히 판정
#   불가로 남는다** 를 함께 단언한다. 게이트가 통째로 빠지면 ①이, 게이트가 과하게 먹으면
#   ②가 깨진다 — 어느 방향으로 틀어져도 하나가 죽는다.
# ─────────────────────────────────────────────────────────────────────────────

# 메서드가 **어긋나** 확정 고아로 내려온 것들(라우트 메서드 ≠ 프론트 동적 호출 메서드).
_METHOD_MISMATCH_ORPHANS = (
    "/api/v1/blockchain/escrow/fund",         # POST 라우트 ↔ GET 호출
    "/api/v1/blockchain/escrow/release",
    "/api/v1/blockchain/escrow/dispute",
    "/api/v1/blockchain/escrow/resolve",
    "/api/v1/blockchain/escrow/refund",
    "/api/v1/blockchain/escrow/direct-pay",
    "/api/v1/design-references/from-design",  # POST 라우트 ↔ DELETE 호출
    "/api/v1/admin/secrets/image-health",     # GET 라우트  ↔ PUT/DELETE 호출
    "/api/v1/admin/secrets/llm-health",
)

# 메서드가 **일치**해 판정 불가로 남아야 하는 것(대조군). 게이트가 과하면 여기가 깨진다.
_METHOD_MATCH_UNDECIDED = (
    "/api/v1/market/report/pdf",   # POST 라우트 ↔ fetch(..., {method:"POST"})
    "/api/v1/market/report/docx",
    "/api/v1/market/report/pptx",
)


def test_메서드가_어긋나면_판정불가가_아니라_확정고아다():
    from orphan_routes import orphans, undecided_routes  # type: ignore[import-not-found]

    orphan_set = {f for f, _m, _p in orphans()}
    undecided_set = {f for f, _m, _p in undecided_routes()}

    # 공허 진리 가드 — 조회기가 살아 있는지 먼저 본다.
    assert len(orphan_set) > 50, "확정 고아가 비정상적으로 적다 — 조회기 확인"
    assert undecided_set, "판정 불가가 0건 — 동적 세그먼트 분류기가 죽었다"

    for route in _METHOD_MISMATCH_ORPHANS:
        # ①있어야 할 곳에 **있다**(양성) — 이것이 없으면 부재 단언이 공허해진다.
        assert route in orphan_set, f"{route} 가 확정 고아가 아니다 — 메서드 게이트가 빠졌나"
        # ②없어야 할 곳에 **없다**(음성)
        assert route not in undecided_set, f"{route} 가 아직 판정 불가다"


def test_메서드가_일치하면_판정불가로_남는다():
    """★대조군 — 게이트가 '전부 고아'로 쓸어버리지 않는지 본다.

    이 셋은 라우트도 POST 이고 호출부도 `method:"POST"` 라 **정말로 불릴 수 있다**.
    게이트가 메서드를 안 보고 무조건 배제하면 여기가 깨진다.
    """
    from orphan_routes import orphans, undecided_routes  # type: ignore[import-not-found]

    orphan_set = {f for f, _m, _p in orphans()}
    undecided_set = {f for f, _m, _p in undecided_routes()}

    for route in _METHOD_MATCH_UNDECIDED:
        assert route in undecided_set, f"{route} 가 판정 불가에서 사라졌다 — 게이트가 과하다"
        assert route not in orphan_set, f"{route} 를 고아로 셌다 — 없는 결함을 만든다"


def test_메서드를_못읽으면_판정불가로_남긴다():
    """★모르는 것을 안다고 하지 않는다 — 프롭으로 경로만 넘기는 호출은 메서드가 없다.

    `endpoint={`/underwriting/${projectId}`}` 에는 메서드가 그 자리에 없다. 도구가
    추정으로 GET/POST 를 고르면 **없는 결함을 만들거나 진짜 고아를 숨긴다**.
    """
    from orphan_routes import undecided_routes  # type: ignore[import-not-found]

    undecided_set = {f for f, _m, _p in undecided_routes()}
    assert "/api/v1/underwriting/history" in undecided_set, (
        "메서드를 읽을 수 없는 호출부인데 결론을 내 버렸다 — 게이트는 한 방향이어야 한다"
    )


def test_call_method_at_이_실제_호출부를_읽는다():
    """★게이트가 **실행되는 입력**인지 확인한다 — 판독기가 늘 None 이면 게이트는 죽은 코드다.

    (판독기가 항상 None 을 돌려줘도 위 두 래칫은 '판정 불가 유지'로 통과할 수 있다.
     그래서 판독기 자체를 직접 태운다.)
    """
    import orphan_routes as _o  # type: ignore[import-not-found]

    blob = "await apiClient.get<OnChainEscrowResponse>(\n  `/blockchain/escrow/${id}`,"
    start = blob.index("/blockchain/escrow/${id}")
    end = start + len("/blockchain/escrow/${id}")
    assert _o.call_method_at(blob, start, end) == "get"

    fetch_blob = 'fetch(`${base}/market/report/${fmt}`, {\n  method: "POST",\n})'
    s2 = fetch_blob.index("/market/report/${fmt}")
    e2 = s2 + len("/market/report/${fmt}")
    assert _o.call_method_at(fetch_blob, s2, e2) == "post"

    # 프롭 전달 — 메서드가 그 자리에 없다 → None(추정 금지)
    prop_blob = "endpoint={`/underwriting/${projectId}`}"
    s3 = prop_blob.index("/underwriting/${projectId}")
    e3 = s3 + len("/underwriting/${projectId}")
    assert _o.call_method_at(prop_blob, s3, e3) is None


# ─────────────────────────────────────────────────────────────────────────────
# 사유 컬럼 잠금 — 2026-08-26
#
# ★무엇이 있었나: 기준선이 **경로만** 담아서 `/api/v1/auction/sync`(라우트 자신이 summary 에
#   "(관리/cron)" 이라고 적어 둔 **정당한 운영용**)와 `/api/v1/auction/opportunities`
#   (소비처가 프론트·백엔드 양쪽 다 0인 **구 트리 잔재**)가 **나란히 서서 구별되지 않았다.**
#   132 건이 한 덩어리라 *"이 중 몇 건이 진짜 부채인가"* 에 아무도 답할 수 없었다.
#
# ★왜 대부분이 `unclassified` 인가: **유추로 채우지 않기 때문이다.** 기계 분류를 시도했다가
#   폐기했다 — *"핸들러가 정의 파일 밖에서 참조되는가"* 로 37건을 얻었는데 **표본 10건이
#   전부 위양성**이었다(로그 문자열·독스트링·`from urllib.parse import quote` 같은 임포트 4건 ·
#   **동명의 다른 함수 정의** 6건). 싼 신호는 없다. 연 사람만 사유를 적는다.
# ─────────────────────────────────────────────────────────────────────────────


def test_모든_행이_경로_종류_사유_셋을_갖는다():
    rows = _rows(_BASELINE)

    # ★공허 진리 가드 — 파서가 죽어 빈 목록이면 아래 전부가 참이 된다.
    assert len(rows) > 50, "기준선 행이 비정상적으로 적다 — 파서나 파일이 깨졌다"

    malformed = [r for r, k, _w in rows if not k]
    assert not malformed, (
        "종류 컬럼이 없는 행이다 — `경로 <TAB> 종류 <TAB> 사유` 로 적어라:\n"
        + "\n".join(f"  {r}" for r in malformed)
    )

    unknown = sorted({k for _r, k, _w in rows if k not in _KINDS})
    assert not unknown, (
        f"닫힌 어휘 밖의 종류다: {unknown}\n"
        f"→ 쓸 수 있는 것: {sorted(_KINDS)}. 새 낱말이 필요하면 _KINDS 에 **뜻과 함께** 추가하라."
    )


def test_분류했다면_무엇을_보고_그렇게_판단했는지_적혀_있다():
    """★`unclassified` 가 아닌 행은 **근거**를 지닌다 — 종류만 바꾸고 사유를 비우면 유추와 같다."""
    rows = _rows(_BASELINE)
    classified = [(r, k, w) for r, k, w in rows if k and k != _UNCLASSIFIED]

    # ★모집단 가드 — 분류된 행이 0 이면 이 검사는 아무것도 잠그지 않는다(공허한 참).
    assert classified, "분류된 행이 하나도 없다 — 이 검사가 공허해졌다"

    thin = [(r, k) for r, k, w in classified if len(w) < 20]
    assert not thin, (
        "종류는 바꿨는데 사유가 비었거나 너무 짧다 — **파일:줄** 로 근거를 적어라:\n"
        + "\n".join(f"  {r} [{k}]" for r, k in thin)
    )


def test_미분류는_늘어나지_않는다():
    """★`unclassified` 는 *"아직 안 봤다"* 이지 *"문제없다"* 가 아니다. 줄이는 방향으로만 간다."""
    rows = _rows(_BASELINE)
    n = sum(1 for _r, k, _w in rows if k == _UNCLASSIFIED)

    assert n <= _UNCLASSIFIED_CEILING, (
        f"미분류가 {n} 건으로 상한 {_UNCLASSIFIED_CEILING} 을 넘었다 — 새 라우트를 기준선에 넣으면서"
        " 사유를 안 적었을 가능성이 높다. 열어 보고 종류와 근거를 적어라."
    )
    # ★죽은 상한도 막는다 — 부채를 갚았는데 상한을 안 내리면 그만큼 다시 늘 수 있다.
    assert n >= _UNCLASSIFIED_CEILING - 25, (
        f"미분류가 {n} 건으로 상한 {_UNCLASSIFIED_CEILING} 보다 한참 낮다 — 부채를 갚았으면"
        " _UNCLASSIFIED_CEILING 을 그 수로 **내려서** 다시 늘 여지를 없애라."
    )
