"""프론트가 보내는 커스텀 헤더가 CORS 화이트리스트에 **실제로** 통과하는지 잠근다.

왜 이 파일이 있나(2026-08-16 라이브 결함):
    `apps/web` 은 설계 승인 버튼에서 `Idempotency-Key` 헤더를 보내는데(`CADEditor.tsx`),
    백엔드 `middleware.py` 의 `allow_headers` 화이트리스트에 그 이름이 없었다.
    브라우저는 프리플라이트(OPTIONS)에서 **400 "Disallowed CORS headers"** 를 받고
    본 요청을 아예 보내지 않는다 → 배포된 기능이 한 번도 동작한 적이 없었다.
    프로덕션 실측: `OPTIONS /api/v1/design-runs/{id}/approve` 에
    `Access-Control-Request-Headers: ...,idempotency-key` → 400 / 그 헤더만 빼면 200.

    ★백엔드 로그에는 아무것도 안 남는다(요청이 도달하지 못한다). 그래서 이 결함 클래스는
      **사용자 신고 아니면 발견되지 않는다** — 자동 락이 필요한 전형이다.
    ★같은 결함이 이미 한 번 있었다: 분양 현장앱 `X-Site-Code` 누락 → 진입 503.
      `middleware.py` 주석이 그 사고를 적어 두었는데도 재발했다. 주석은 락이 아니다.

이 파일의 잠금 방식(CLAUDE.md A4 — 목록형 금지, 파생형):
    기대 헤더 목록을 **사람이 적지 않는다.** `apps/web` 소스에서 "우리 API 로 나가는
    요청 헤더"를 긁어와, 그 전부가 실제 프리플라이트를 통과하는지 확인한다.
    프론트가 새 헤더를 추가하면 이 테스트가 **자동으로** 그 헤더를 감시하기 시작한다.

무엇을 태우는가(CLAUDE.md A3 — 소스 검사 대신 실행 결과):
    `allow_headers` 리스트를 grep 하지 않는다. `setup_middlewares()` 로 미들웨어를
    실제 등록한 앱에 **진짜 OPTIONS 프리플라이트**를 쏴서 상태코드를 본다.
    브라우저가 겪는 것과 같은 경로다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.middleware import setup_middlewares

# tests/ → apps/api → apps → apps/web
_WEB = Path(__file__).resolve().parents[2] / "web"

# 프리플라이트에 쓸 오리진 — Settings 기본 CORS_ORIGINS 에 포함된 값(test_security.py 와 동일 전제).
_ORIGIN = "http://localhost:3000"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
# `//` 앞이 `:` 나 단어면 URL(`https://`)이라 주석이 아니다.
_LINE_COMMENT = re.compile(r"(?<![:\w])//[^\n]*")

# `headers: {...}` / `headers = {...}` 블록 안의 따옴표 키.
_HEADERS_OBJ = re.compile(r"\bheaders\s*[:=]\s*\{")
_QUOTED_KEY = re.compile(r"""["']([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*)["']\s*:""")
# ★리터럴 블록 밖에서 조립되는 헤더도 있다(`salesApi.ts` 가 함수 반환으로 만든다).
#   그래서 `X-*` 어휘는 파일 전역 문자열에서도 긁는다.
_X_HEADER = re.compile(r"""["'](X-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)["']""")
# 우리 API 로 나가는 요청을 만드는 파일만 본다 — 3자 요청·응답 헤더 구성(예: VWorld 프록시가
# 돌려주는 `X-VWorld-Breaker`)을 위양성으로 신고하면 정상 코드를 막는다(CLAUDE.md A6).
_OUR_API_FUNNEL = re.compile(r"\bapiClient\b|\bsalesApi\b|\bgetRequestUrl\b|\bapiFetch\b")
# `resp.headers.get("X-…")` — 응답을 **읽는** 자리. 여기서만 보이면 요청 헤더가 아니다.
_HEADER_READ = re.compile(r"""\.headers\.get\(\s*["'](X-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)["']""")


def _sent_somewhere(src: str, key: str) -> bool:
    """그 키가 **읽기 이외의 자리**에도 등장하는가(= 실제로 보낼 가능성이 있는가)."""
    total = len(re.findall(rf"""["']{re.escape(key)}["']""", src))
    reads = len(re.findall(rf"""\.headers\.get\(\s*["']{re.escape(key)}["']""", src))
    return total > reads


def _strip_comments(src: str) -> str:
    """주석을 걷어낸다 — 주석 처리된 헤더를 '보낸다'고 오독하지 않기 위해(CLAUDE.md A3)."""
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", src))


def _balanced_block(src: str, open_idx: int) -> str:
    depth = 0
    for i in range(open_idx, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[open_idx : i + 1]
    return src[open_idx : open_idx + 400]


def _derive_frontend_request_headers() -> dict[str, set[str]]:
    """`apps/web` 이 **우리 API 로** 보내는 요청헤더를 소스에서 파생한다."""
    found: dict[str, set[str]] = {}
    for path in sorted(_WEB.rglob("*.ts")) + sorted(_WEB.rglob("*.tsx")):
        rel = path.relative_to(_WEB).as_posix()
        # node_modules: 남의 코드 / __tests__: 목 헤더 / app/api: Next 라우트 = **응답** 헤더.
        if "node_modules" in rel or "/__tests__/" in rel or rel.startswith("app/api/"):
            continue
        src = _strip_comments(path.read_text(encoding="utf-8", errors="ignore"))
        if not _OUR_API_FUNNEL.search(src):
            continue
        for m in _HEADERS_OBJ.finditer(src):
            for key in _QUOTED_KEY.findall(_balanced_block(src, m.end() - 1)):
                found.setdefault(key, set()).add(rel)
        # ★응답에서 **읽기만** 하는 헤더는 요청 헤더가 아니다 — 프리플라이트와 무관하다.
        #   이 추출기는 위 주석(54~56줄)에서 그 위양성 클래스를 이미 지목했지만
        #   메커니즘이 가르지 못했다: `resp.headers.get("X-…")` 도 문자열이라 잡혔다.
        #   실증 2026-08-18: `X-VWorld-Degraded`(타일 강등 사유)는 **동일 출처** 응답에서
        #   읽기만 하는데 "프리플라이트 400" 으로 신고돼 정상 코드를 막았다(CLAUDE.md A6).
        #   → `.headers.get("X-…")` 위치에서만 등장하는 키는 제외한다. 보내기도 하는 헤더는
        #     다른 자리(headers 객체 리터럴 등)에도 나타나므로 계속 잡힌다.
        read_only = set(_HEADER_READ.findall(src))
        for key in _X_HEADER.findall(src):
            if key in read_only and not _sent_somewhere(src, key):
                continue
            found.setdefault(key, set()).add(rel)
    return found


def _preflight_app() -> TestClient:
    app = FastAPI()

    @app.post("/__preflight_probe__")
    async def _probe() -> dict[str, bool]:
        return {"ok": True}

    setup_middlewares(app)
    return TestClient(app)


def _preflight(client: TestClient, header_name: str):
    return client.options(
        "/__preflight_probe__",
        headers={
            "Origin": _ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": f"content-type,{header_name.lower()}",
        },
    )


def test_파생이_비어_있지_않다():
    """공허 진리 가드 — 스캐너가 조용히 0건이 되면 아래 단언이 전부 무의미해진다.

    ★"위반 0"이 참인 이유가 "대상 0개"이면 잠금이 아니다(CLAUDE.md A2).
      실제로 보내는 것이 확인된 두 헤더를 하한으로 못 박는다.
    """
    derived = _derive_frontend_request_headers()
    assert derived, "프론트에서 요청 헤더를 한 개도 파생하지 못했다 — 스캐너가 깨졌다"
    for known in ("Idempotency-Key", "X-Site-Code", "X-Site-Token"):
        assert known in derived, (
            f"{known} 를 파생하지 못했다 — 프론트가 실제로 보내는 헤더인데 스캐너가 놓쳤다. "
            f"파생 결과={sorted(derived)}"
        )


def test_프리플라이트_통과_대조군이_실제로_거절된다():
    """양성 대조 — 화이트리스트가 실제로 **거절도** 하는지 먼저 확인한다.

    ★이게 없으면, 미들웨어가 모든 헤더를 허용하도록 망가져도 아래 테스트는 전부 초록이다
      (탐지기는 양성대조가 없으면 무성으로 죽는다 — 2026-08-12 교훈).
    """
    client = _preflight_app()
    resp = _preflight(client, "X-Definitely-Not-Allowed-Header")
    assert resp.status_code == 400, (
        "허용목록에 없는 헤더가 프리플라이트를 통과했다 — CORS 화이트리스트가 무력화됐다"
    )


@pytest.mark.parametrize("header_name", sorted(_derive_frontend_request_headers()))
def test_프론트가_보내는_헤더는_프리플라이트를_통과한다(header_name: str):
    """파생된 모든 헤더가 실제 OPTIONS 프리플라이트를 통과해야 한다.

    실패 = 그 헤더를 쓰는 화면이 **브라우저에서 통째로 죽어 있다**는 뜻이다.
    (백엔드 로그에는 안 남는다 — 본 요청이 도달하지 못한다.)
    """
    client = _preflight_app()
    resp = _preflight(client, header_name)
    senders = sorted(_derive_frontend_request_headers().get(header_name, ()))[:3]
    assert resp.status_code == 200, (
        f"'{header_name}' 가 CORS allow_headers 에 없다 → 브라우저 프리플라이트 400. "
        f"보내는 곳: {senders}. middleware.py 의 allow_headers 에 추가하라."
    )
