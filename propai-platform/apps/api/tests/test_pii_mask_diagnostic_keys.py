"""**적재 마스킹이 진단 필드를 지우지 않는가** — 그리고 **면제가 PII 를 새게 하지 않는가**.

## 왜 (2026-08-27 실측 · 원본 함수를 그대로 실행해 확인)

`capture_service.mask_pii` 는 `_PII_KEYS` 를 **부분일치**로 본다(`p in key_l`). `_PII_KEYS` 에
`"name"` 이 있어 **`"name" in "filename"` 이 참**이고, 그래서 조기 오류 포착이 애써 싣는
`filename` 이 **적재 시점에 `[redacted]`** 되어 왔다.

## ★독립 적대 리뷰가 초판 락 3개를 뚫었다 — 그 자리가 이 파일의 설계다

1. **기각한 처방을 「손으로 고른 5개 키」로 잠갔었다** → 그 5개만 비켜 가는 토큰경계 리팩토링이
   **SURVIVED**(새로 누출되는 정당 PII 키 14건). **목록은 곧 상한이 된다.**
   → 이제 `_PII_KEYS` **전수 × 변형**으로 **부분일치라는 성질 자체**를 잠근다.
2. **(정)방향은 파생형인데 (역)방향이 목록형**이었다 → `_DIAGNOSTIC_SAFE_KEYS` 에
   `contact_name`·`home_addr1` 을 넣어도 **락 17개 전부 초록**이었다.
   → 이제 면제 집합이 **프론트 실제 payload 키에서 파생된 것의 부분집합**임을 강제한다.
3. **수집기가 간접 전달을 못 봤다** — `payload` 를 변수로 넘기는 호출
   (`buildSelectionContaminationProps`)의 4키가 파생 집합에 없었는데 **분모는 채워** 생존 단언이
   공허했다. → 축을 `TrackEventProps` 반환 함수까지 넓히고 **그 키를 양성 대조군으로** 못 박는다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.growth.capture_service import (
    _DIAGNOSTIC_SAFE_KEYS,
    _PII_KEYS,
    mask_pii,
)

WEB = Path(__file__).resolve().parents[2] / "web"

_JS_LITERALS = frozenset({"null", "true", "false", "undefined"})
# ★초판 정규식은 `r"\\."` 로 써서 **리터럴 역슬래시**를 요구했다 — POSIX 경로엔 없으므로
#   `.next/`·`*.test.ts` 를 **하나도 배제하지 못했다**(독립 리뷰 실측). 위양성도 결함이다.
_EXCLUDE = re.compile(r"(^|/)(node_modules|\.next|__tests__)(/|$)|\.(test|spec)\.tsx?$")


def _balanced(src: str, open_at: int, opener: str, closer: str) -> str:
    """`open_at` 의 여는 괄호부터 **균형이 맞는 지점**까지. 고정 창은 옆 블록을 침범한다."""
    depth = 0
    for j in range(open_at, len(src)):
        if src[j] == opener:
            depth += 1
        elif src[j] == closer:
            depth -= 1
            if depth == 0:
                return src[open_at + 1 : j]
    raise AssertionError("괄호 균형 실패 — 파서가 죽었다(조용히 넘어가지 않는다)")


def _keys_in_payload_blocks(text: str) -> set[str]:
    keys: set[str] = set()
    for m in re.finditer(r"payload:\s*\{", text):
        block = _balanced(text, m.end() - 1, "{", "}")
        keys |= set(re.findall(r"(?:^|[\s{,])([A-Za-z_][A-Za-z0-9_]*)\s*:", block))
        # 축약 속성(`scope,`)도 키다. `digest: null` 의 **값**은 리터럴 집합으로 걷어낸다.
        keys |= set(re.findall(r"(?:^|[\s{,])([A-Za-z_][A-Za-z0-9_]*)\s*(?=[,}])", block))
    return keys - _JS_LITERALS


def _extract(path: Path) -> tuple[set[str], int, int]:
    """성장루프 이벤트의 payload 키를 뽑고, **해석 못 한 호출 수**를 함께 돌려준다.

    반환: (키, **간접 호출 수**, **축② 생산자 수**). ★셋을 그대로 돌려주고 판정은 테스트가 한다.

    ★파일 전체의 `payload:` 를 훑으면 **경매 화면의 TypeScript 타입 선언**까지 집는다(실측 —
    그대로 갔으면 `name` 을 안전키로 면제하라는 **정반대 처방**을 유도했을 것이다).
    그래서 축은 ①`trackEvent(` 호출 인자 ②`TrackEventProps` 를 반환하는 함수 **둘뿐**이다.
    """
    src = path.read_text(encoding="utf-8")
    keys: set[str] = set()
    indirect = 0
    for call in re.finditer(r"\btrackEvent\s*\(", src):
        args = _balanced(src, call.end() - 1, "(", ")")
        if "payload:" in args:
            keys |= _keys_in_payload_blocks(args)
        elif not re.search(r"\{", args):
            indirect += 1  # payload 를 **변수로** 넘긴 호출 — 축 ②가 덮어야 한다
    axis2 = 0
    for fn in re.finditer(r":\s*TrackEventProps(?:\s*\|\s*null)?\s*\{", src):
        keys |= _keys_in_payload_blocks(_balanced(src, fn.end() - 1, "{", "}"))
        axis2 += 1
    # ★**판정을 여기서 하지 않는다.** 초판은 `if axis2: unresolved = 0` 으로 여기서 뭉갰는데,
    #   그 한 줄을 `if True:` 로 바꾸면 미해석 가드가 **통째로 공허**해졌다(변이 SURVIVED 실측).
    #   경고·보정은 산문이고 **판정은 테스트가 한다** — 두 수를 **그대로** 돌려준다.
    return keys, indirect, axis2


def _sources() -> list[Path]:
    out: list[Path] = []
    for p in WEB.rglob("*.ts*"):
        if _EXCLUDE.search(p.relative_to(WEB).as_posix()):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover
            continue
        if re.search(r"\btrackEvent\s*\(|:\s*TrackEventProps", text):
            out.append(p)
    return out


SOURCES = _sources()
_EXTRACTED = {p: _extract(p) for p in SOURCES}
FRONTEND_PAYLOAD_KEYS: set[str] = set().union(set(), *(k for k, _, _ in _EXTRACTED.values()))


# ── 수집기·파서 생존 ────────────────────────────────────────────────────────
def test_deriver_is_alive() -> None:
    """전제: 수집기와 파서가 살아 있다(공허한 초록 방지)."""
    assert len(SOURCES) >= 3, f"소스를 거의 못 찾았다 — 수집기가 죽었다: {SOURCES}"
    assert len(FRONTEND_PAYLOAD_KEYS) >= 5, f"키를 거의 못 뽑았다: {sorted(FRONTEND_PAYLOAD_KEYS)}"
    # ★양성 대조군 ①: 결함이 살던 그 키(직접 전달 축)
    assert "filename" in FRONTEND_PAYLOAD_KEYS, "직접 전달 축이 죽었다"
    # ★양성 대조군 ②: **간접 전달**(payload 를 변수로 넘기는 경로 — 초판이 통째로 놓친 축)
    assert "verdict" in FRONTEND_PAYLOAD_KEYS, (
        "간접 전달 축이 죽었다 — `buildSelectionContaminationProps` 의 키가 안 보인다.\n"
        "이 단언이 없으면 그 4키가 빠진 채로도 위 개수 단언이 **공허하게** 만족된다."
    )


def test_every_indirect_call_has_a_resolver() -> None:
    """★payload 를 **변수로** 넘기는 호출이 있으면, 같은 파일에 축② 생산자가 **있어야** 한다.

    없으면 그 키들은 이 락의 감시 밖이다 — **조용한 위음성**이다.
    ★판정을 수집기 안에서 하지 않는다: 초판은 `if axis2: unresolved = 0` 으로 뭉갰고, 그 한 줄을
    `if True:` 로 바꾸면 가드가 통째로 공허해졌다(변이 SURVIVED 실측).
    """
    orphan = sorted(
        str(p.relative_to(WEB))
        for p, (_, indirect, axis2) in _EXTRACTED.items()
        if indirect > 0 and axis2 == 0
    )
    assert orphan == [], (
        f"payload 를 해석할 수 없는 `trackEvent` 호출이 있는 파일: {orphan}\n"
        "축(`trackEvent(` 인자 · `TrackEventProps` 반환 함수)을 넓혀라."
    )
    # ★**설명되는 생존**(변이 점수 부풀리기 방지 · 실측 기록): 위 조건절을 `if False` 로 바꾸면
    #   이 단언은 생존한다. 그러나 그것은 **단언 자신의 술어를 죽인 것**이고, 그렇게 하면 어떤
    #   테스트든 죽는다 — 제품이 아니라 락을 지운 것이다. 앞선 `if axis2: unresolved = 0` 생존과
    #   **다른 층**이다: 그건 **수집기 안**의 보정이라 "정리"처럼 보였고 그래서 진짜 구멍이었다.
    # ★공허 진리 가드 — 간접 호출이 **실재**해야 위 단언이 무엇이라도 잰다.
    total_indirect = sum(i for _, i, _ in _EXTRACTED.values())
    assert total_indirect > 0, (
        "간접 호출을 한 건도 못 찾았다 — 수집기가 죽었으면 위 단언은 공허하게 참이다"
    )


# ── (정) 진단 필드는 살아남는다 ──────────────────────────────────────────────
def test_frontend_diagnostic_keys_survive_masking() -> None:
    wiped = sorted(k for k in FRONTEND_PAYLOAD_KEYS if mask_pii({k: "SENTINEL"})[k] == "[redacted]")
    assert wiped == [], (
        f"적재 마스킹이 진단 필드를 지운다 — 어디에도 도착하지 않는다.\n지워지는 키: {wiped}\n"
        "처방: `_DIAGNOSTIC_SAFE_KEYS` 에 **정확일치**로 추가하라. 매처를 약화시키지 마라."
    )


# ── ★기각한 처방을 **성질**로 잠근다(목록이 아니라) ──────────────────────────
@pytest.mark.parametrize("pii", _PII_KEYS)
def test_matcher_stays_substring_not_token(pii: str) -> None:
    """★부분일치 **성질 자체**를 `_PII_KEYS` 전수 × 변형으로 잠근다.

    초판은 `username` 등 **손으로 고른 5개**만 잠갔다 → 그 5개를 특례로 비켜 가는 토큰경계
    리팩토링이 SURVIVED 했고, 새로 누출되는 정당 PII 키가 **14건**이었다(독립 리뷰 실측).
    ★목록을 잠그면 그 목록이 곧 상한이 된다 — **성질**을 잠근다.
    """
    for key in (f"x{pii}", f"{pii}x", f"a{pii}b", f"user_{pii}", f"{pii}_id", f"{pii}s"):
        if key in _DIAGNOSTIC_SAFE_KEYS:
            continue  # 명시적으로 면제된 것만 예외(면제 자체는 아래에서 따로 잠근다)
        assert mask_pii({key: "PII"})[key] == "[redacted]", (
            f"`{key}` 가 마스킹되지 않는다 — 매처가 **토큰경계로 약화**됐을 가능성이 높다.\n"
            "부분일치를 유지하고, 진단 키만 `_DIAGNOSTIC_SAFE_KEYS` 로 면제하라."
        )


# ── (역) 면제가 발명되지 않았는가 ────────────────────────────────────────────
def test_exemptions_are_derived_not_invented() -> None:
    """★면제는 **프론트가 실제로 보내는 키** 중에서만 나와야 한다.

    초판의 역방향 락은 `k in _PII_KEYS`(튜플 정확일치)와 **손으로 쓴 7개 목록**이라,
    `contact_name`·`home_addr1` 을 면제에 넣어도 **락 17개가 전부 초록**이었다(독립 리뷰 실측).
    """
    invented = sorted(_DIAGNOSTIC_SAFE_KEYS - FRONTEND_PAYLOAD_KEYS)
    assert invented == [], (
        f"프론트가 보내지도 않는 키가 면제돼 있다: {invented}\n"
        "면제는 **실측된 위양성**만이다 — 발명하지 마라(PII 키를 슬쩍 넣는 경로가 된다)."
    )
    # 죽은 면제도 결함이다 — 실제로 부분일치에 걸리지 않는 키를 면제하는 것은 무의미하고,
    # 그 자리가 나중에 **의미 있는 면제로 오해**된다.
    dead = sorted(k for k in _DIAGNOSTIC_SAFE_KEYS if not any(p in k for p in _PII_KEYS))
    assert dead == [], f"부분일치에 걸리지도 않는 면제(죽은 면제): {dead}"


def test_exemption_is_exact_match_not_substring() -> None:
    """면제가 부분일치로 새면 `owner_filename` 같은 변형이 통째로 통과한다."""
    for key in ("owner_filename", "filename_owner", "user_filename"):
        assert mask_pii({key: "X"})[key] == "[redacted]", f"`{key}` 가 통과했다 — 면제가 샌다"


@pytest.mark.parametrize(
    "key", ["owner_name", "user_email", "contact_phone", "jumin", "resident_id", "addr", "address"]
)
def test_genuine_pii_keys_still_redacted(key: str) -> None:
    assert mask_pii({key: "X"})[key] == "[redacted]", f"`{key}` 가 더 이상 마스킹되지 않는다"


# ── ★C1: 면제된 값 자체가 PII 운반체다 ──────────────────────────────────────
def test_exempted_url_value_drops_query_and_fragment() -> None:
    """★`filename` 은 **인라인 스크립트 오류에서 문서 URL 전체**가 된다(실브라우저 실측).

    이 앱은 **지번을 쿼리에** 싣는다(`registry-analysis?addr=…`). 면제를 그냥 통과시키면
    지번이 평문 적재된다. 진단에는 **경로만으로 충분**하므로 쿼리·프래그먼트를 버린다.
    """
    out = mask_pii({"filename": "https://4t8t.net/ko/registry-analysis?addr=서울 강남구 테헤란로 152#f"})
    # 두 모집단이 같은 실행에서 갈린다: 경로는 **남고** 쿼리는 **사라진다**.
    assert "registry-analysis" in out["filename"], f"경로까지 지웠다 — 진단 불가: {out['filename']}"
    assert "테헤란로" not in out["filename"], f"쿼리의 지번이 살아남았다: {out['filename']}"
    assert "#f" not in out["filename"], out["filename"]


def test_exempted_percent_encoded_pii_is_redacted() -> None:
    """★퍼센트 인코딩은 `_mask_str` 의 정규식을 **전부 비켜 간다**(독립 리뷰 실측).

    `hong%40corp.co.kr` 는 이메일 정규식에 안 걸린다 → 디코드해서 검사하고, 걸리면 통째로 버린다.
    """
    enc = mask_pii({"filename": "app.js#u=hong%40corp.co.kr"})["filename"]
    assert "corp.co.kr" not in enc, f"인코딩된 이메일이 살아남았다: {enc}"
    # 음성 대조군 — PII 가 없는 평범한 경로는 **그대로 남아야** 한다(위양성도 결함이다).
    plain = mask_pii({"filename": "/_next/static/chunks/main-abc123.js"})["filename"]
    assert plain == "/_next/static/chunks/main-abc123.js", plain


def test_masking_still_scrubs_value_patterns_in_exempted_key() -> None:
    out = mask_pii({"filename": "leak@example.com 010-1234-5678"})["filename"]
    assert "example.com" not in out and "1234-5678" not in out, out


def test_exemption_applies_at_any_depth_but_pii_parent_still_wins() -> None:
    """면제는 깊이와 무관하되, **PII 부모 아래**에서는 부모가 이긴다(양방향 명시)."""
    assert mask_pii({"a": {"filename": "x.js"}})["a"]["filename"] == "x.js"
    assert mask_pii({"owner_name": {"filename": "x.js"}})["owner_name"] == "[redacted]"


@pytest.mark.xfail(
    reason=(
        "★부채(초록 안에 보이게 남김) — 백엔드 `_mask_str` 에 **주소 정규식이 없다**. "
        "프론트 `maskString` 은 `ADDRESS_RE` 로 지우지만 `growth.py` 피드백 payload 와 "
        "`learning_loop._summarize_payload` 는 프론트를 거치지 않는다. "
        "★처방 방향은 **결정 필요**: 그 경로가 태우는 것은 `analysis_ledger` 부동산 분석 payload 이고 "
        "**주소가 곧 분석 대상**이라, 지우면 학습 신호를 파괴할 수 있다(단독 판단하지 않았다). "
        "고쳐지면 XPASS 로 시끄럽게 알린다."
    ),
    strict=True,
)
def test_address_in_value_is_masked_debt() -> None:
    out = mask_pii({"note": "서울특별시 강남구 테헤란로 152 3동 401호"})["note"]
    assert "테헤란로 152" not in out
