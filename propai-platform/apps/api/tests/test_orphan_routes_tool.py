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

import orphan_routes  # type: ignore[import-not-found]  # noqa: E402
from orphan_routes import (  # type: ignore[import-not-found]  # noqa: E402
    _py_comment_string_spans,
    _strip_js_comments,
    backend_routes,
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


def test_템플릿_표현식_안의_주석도_지운다():
    """★변이 감사(2026-08-20)가 **생존**으로 짚은 구멍 — 템플릿 표현식 추적을 끊어도 초록이었다.

    `${...}` 안은 다시 **코드 문맥**이다. 그 추적을 끊으면 스캐너가 백틱 안에 갇혀
    표현식 속 주석을 못 지우고, 거기 적힌 경로가 "소비"로 세어진다(결함② 재발 경로).
    """
    src = 'const s = `${/* /api/v1/hidden-in-template */ ""}`;'
    kept = _strip_js_comments(src)
    assert "/api/v1/hidden-in-template" not in kept, "템플릿 표현식 안의 주석을 못 지웠다"
    # 대조군 — 표현식 밖의 진짜 경로는 살아 있어야 한다(다 지워서 통과하면 잠금이 아니다).
    assert "/api/v1/kept" in _strip_js_comments('const s = `${x}/api/v1/kept`;')


def test_파일이_줄주석으로_끝나도_지운다():
    """★변이 감사(2026-08-20) 생존 — 개행 없이 끝나는 줄 주석을 픽스처가 한 번도 안 만들었다.

    `src.find("\n", i)` 가 -1 을 돌려주는 경로다. 이 폴백이 없으면 주석이 안 지워진다
    (그리고 커서가 뒤로 가 무한루프가 된다 — 그래서 이 케이스는 변이 시 **행**으로 죽는다).
    """
    kept = _strip_js_comments('run(); // /api/v1/tail-comment-no-newline')
    assert "/api/v1/tail-comment-no-newline" not in kept, "개행 없이 끝나는 줄 주석을 못 지웠다"
    assert "run();" in kept, "주석 아닌 코드까지 삼켰다"


def test_파이썬_주석과_독스트링_속_라우트는_세지_않는다():
    """★적대리뷰 H-2 — 프론트 주석만 배제하고 **백엔드 주석은 세고 있었다**(미러 누락).

    `/admin-only` 는 `app/core/rbac.py:114` **독스트링의 사용 예**인데 라우트로 추출돼
    기준선에 "확정 고아"로 실려 있었다 — 실재하지 않는 결함이 후보로 공표된 것이다.
    전수 575건 중 정확히 3건이 주석/문자열 내부였다.
    """
    routes = backend_routes()

    # 공허 진리 가드 — 추출기가 죽으면 아래 `not in` 이 전부 공허하게 참이 된다.
    assert len(routes) > 400, f"백엔드 라우트가 비정상적으로 적다({len(routes)}) — 추출기 사망 의심"

    for ghost in ("/admin-only", "/from-project", "/projects"):
        assert ghost not in routes, f"주석/독스트링 속 유령 라우트가 다시 세어졌다: {ghost}"

    # 대조군 — 진짜 라우트는 여전히 잡혀야 한다(다 배제해서 통과하면 잠금이 아니다).
    assert "/api/v1/market/report/pdf" in routes, "실제 라우트까지 배제됐다 — 마스킹이 과하다"


def test_토큰화_실패시_None_을_돌려준다():
    """★변이 감사 생존 보강 — 폴백 **판단층**을 직접 잠근다.

    호출부의 `if spans is None:` 가지는 저장소 .py 가 전부 토큰화에 성공해(실패 0건)
    도달 불가라 변이가 살아남는다. 최소한 "None 을 돌려준다"는 계약은 여기서 잠근다.
    """
    assert _py_comment_string_spans("def f(:\n    pass\n") is None, "깨진 소스인데 None 이 아니다"
    # 대조군 — 정상 소스는 범위를 돌려줘야 한다(항상 None 이면 마스킹이 통째로 죽는다).
    spans = _py_comment_string_spans('# c\nx = "s"\n')
    assert spans and len(spans) >= 2, f"정상 소스에서 주석·문자열 범위를 못 찾았다: {spans}"


def test_호출자가_캐시를_오염시키지_못한다():
    """★`classify()` 는 lru_cache 다 — 캐시가 쥔 리스트를 그대로 돌려주면 호출자의
    `.append()`/`.sort()` 한 줄이 **전역 분류 결과를 조용히 바꾼다**(실증: 123 → 124).

    오늘 훼손하는 호출자는 없지만, 그래서 더더욱 잠가 둔다 — 미래의 한 줄이 기준선·래칫을
    통째로 거짓말하게 만든다.
    """
    first = orphan_routes.orphans()
    n = len(first)
    assert n > 50, "확정 고아가 비정상적으로 적다 — 아래 비교가 공허해진다"

    first.append(("/api/v1/__contamination__", "get", "fake.py"))
    assert len(orphan_routes.orphans()) == n, "호출자의 변경이 캐시로 새어 들어갔다(사본 반환 아님)"

    # 판정 불가 쪽도 같은 계약이어야 한다(한쪽만 막으면 반대쪽으로 샌다).
    und = orphan_routes.undecided_routes()
    m = len(und)
    und.append(("/api/v1/__contamination2__", "get", "fake.py"))
    assert len(orphan_routes.undecided_routes()) == m, "판정 불가가 사본이 아니다"


def test_세그먼트_경계는_숫자와_밑줄도_경계로_본다():
    """★적대리뷰가 **손수** 넣은 변이로 생존한 층 — `_SEG_CHAR` 는 오른쪽 경계 **계약**이다.

    `[A-Za-z-]` 로 좁히면 `/api/v1/user` 가 `/api/v1/user2` 에 걸려 "소비"로 세어진다
    (= 진짜 고아가 숨는 방향). 줄 단위 변이 도구는 문자클래스 멤버 제거를 만들지 못해
    57변이 안에서는 드러나지 않았다.
    """
    assert not is_consumed("/api/v1/user", 'apiClient.get("/api/v1/user2");'), "숫자가 경계에서 빠졌다"
    assert not is_consumed("/api/v1/user", 'apiClient.get("/api/v1/user_profile");'), "밑줄이 경계에서 빠졌다"
    # 대조군 — 진짜 경로는 여전히 잡아야 한다(전부 막아버리면 도구가 죽는다).
    assert is_consumed("/api/v1/user", 'apiClient.get("/api/v1/user");')


def test_동적_세그먼트_종료는_백틱만이_아니다():
    """★손수 변이 생존 층 — `_URL_END` 는 동적 세그먼트 종료 **계약**이다.

    백틱 하나로 줄이면 쿼리스트링이 붙은 호출을 못 봐서 **판정 불가가 확정 고아로** 새어
    나간다(= 없는 결함을 만드는 방향).
    """
    assert is_dynamically_reachable("/api/v1/thing/x", 'fetch(`/api/v1/thing/${id}?q=1`);'), (
        "`?`(쿼리 시작)로 끝나는 동적 세그먼트를 못 봤다"
    )
    # 대조군 — 뒤에 경로가 더 붙으면 여전히 인정하지 않는다.
    assert not is_dynamically_reachable("/api/v1/thing/x", 'fetch(`/api/v1/thing/${id}/more`);')


def test_조회기_사망_대조군이_실제로_발화한다():
    """★손수 변이 생존 층 — 이 도구가 **선언한 안전 대조군**이 진짜 도는지 태운다.

    ★캐시 때문에 두 번째 호출부터는 발화하지 않는다. 그래서 `cache_clear()` 를 부른다 —
      이 테스트 자체가 `classify()` 독스트링이 경고하는 캐시 함정의 **실증**이다.
    """
    orphan_routes.classify.cache_clear()
    original = orphan_routes.WEB_DIR
    try:
        orphan_routes.WEB_DIR = "/tmp/__orphan_routes_nonexistent__"
        with pytest.raises(SystemExit, match="조회기 사망"):
            orphan_routes.classify()
    finally:
        orphan_routes.WEB_DIR = original
        orphan_routes.classify.cache_clear()

    # 대조군 — 원복 후에는 정상 분류가 돌아와야 한다(테스트가 전역을 망가뜨리지 않았음).
    assert len(orphan_routes.classify()[0]) > 50


def test_블록주석이_닫히지_않고_끝나도_지운다():
    """★변이 감사 생존 — 줄주석 미러(`…줄주석으로_끝나도…`)는 있는데 **블록주석 미러가 없었다**.

    도달 경로가 실재한다: JSX·정규식의 가짜 `/*` 는 `*/` 가 없어 `close == -1` 이 되고,
    폴백이 없으면 파일 꼬리를 **통째로 삼켜** 진짜 호출줄이 사라진다(= 고아 과대).
    """
    src = '<p>면적 /* 가격</p>\napiClient.get("/api/v1/real-consumption");'
    kept = _strip_js_comments(src)
    # 폴백이 살아 있으면 `/*` 이후는 전부 공백 → 호출줄도 사라진다. 그것이 **현재 계약**이다.
    assert len(kept) == len(src), "길이 보존이 깨졌다"
    assert "real-consumption" not in kept, (
        "닫히지 않은 블록주석 폴백이 사라졌다 — 파일 꼬리 처리가 정의되지 않는다"
    )
    # 대조군 — 정상적으로 닫힌 블록주석은 그 뒤 코드를 살려야 한다.
    ok = _strip_js_comments('/* c */ apiClient.get("/api/v1/real-consumption");')
    assert "real-consumption" in ok, "닫힌 블록주석 뒤 코드까지 삼켰다"


def test_중첩_템플릿_표현식도_동적_세그먼트로_본다():
    """★변이 감사 생존 — `_DYN_EXPR` 의 중첩 허용 분기가 **한 번도 안 태워졌다**.

    오늘 분류에는 영향이 없지만(중첩 없이도 13건 동일) 프론트에 중첩 템플릿 표현식이
    **105건 실재**하므로 도달 가능한 분기다 → 지우지 않고 잠근다.
    """
    blob = 'fetch(`${base}/api/v1/thing/${flag ? `${a}` : b}`);'
    assert is_dynamically_reachable("/api/v1/thing/literal", blob), "중첩 표현식을 못 봤다"


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
        # 메서드 게이트(2026-08-21) 실증 — 같은 부모의 동적 호출이 있어도 메서드가 갈린다.
        ("/api/v1/blockchain/escrow/fund", "orphan"),      # POST 라우트 ↔ GET 호출
        ("/api/v1/underwriting/history", "undecided"),     # 메서드 판독 불가 → 남긴다
    ],
)
def test_실제_저장소에서도_세_칸으로_갈린다(route: str, expected: str):
    """★순수 함수만 잠그면 **실제 스캔 경로**는 우회된다 — 진짜 파이프라인을 태운다."""
    confirmed, undecided = classify()
    conf, und = {f for f, _m, _p in confirmed}, {f for f, _m, _p in undecided}

    # 공허 진리 가드 — 세 칸이 모두 유의미한 크기여야 아래 판정이 의미를 가진다.
    # ★스캐너 사망 탐지용 하한 — 부채를 갚아 정당하게 내려가면 이 숫자를 낮춰라.
    assert len(conf) > 50, "확정 고아가 비정상적으로 적다 — 스캐너가 죽었을 가능성"
    # ★2026-08-21: 13 → 4(메서드 게이트로 9건이 확정 고아로 결론남). 위 주석의 지시대로 낮춘다.
    assert len(und) > 2, "판정 불가가 비정상적으로 적다 — 동적 분류기가 죽었을 가능성"

    actual = "orphan" if route in conf else "undecided" if route in und else "consumed"
    assert actual == expected, (
        f"{route} 가 {expected} 가 아니라 {actual} 로 분류됐다.\n"
        "→ 이것이 **의도된 변화**라면(배선했거나 라우트를 지웠다면) 결함이 아니다. "
        "`orphan_routes_baseline.txt`·`orphan_routes_undecided.txt` 와 이 파라미터를 "
        "**함께 갱신하고 사유를 커밋에 남겨라**. 부채를 갚는 것은 벌할 일이 아니다."
    )
