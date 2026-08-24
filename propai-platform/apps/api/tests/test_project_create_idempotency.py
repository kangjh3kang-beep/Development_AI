"""`POST /projects` 재전송 안전 — **같은 시도를 두 번 만들지 않는다**.

## 무엇이 있었나(실물)

프로덕션에 이름·주소·필지집합이 **완전히 같은 중복 프로젝트가 2쌍** 있다. 그리고 클라이언트에
같은 프로젝트를 두 번 POST 할 수 있는 경로가 실측으로 둘 있었다:

- `#815` — 생성 `await` 창에 동기화가 끼어들어 "고아"로 오판 (같은 탭 안에서만 막았다)
- `#822` — 목록이 20건에서 잘려 **이미 있는 프로젝트를 "백엔드에 없다"고 오판**

둘 다 클라이언트 처방이라 **다른 탭·기기·재설치**에는 닿지 않는다. 서버가 키를 기억하면 닫힌다.

★이 저장소에는 **이미 범용 `Idempotency-Key` 통로가 있었다**(`app/core/idempotency.py` —
`schema_guard` 기반이라 alembic 신규 헤드가 필요 없다). 인계 문서는 *"스키마 변경 필요"* 라고
적어 두었는데 **실측으로 거짓**이었다. 새로 만들지 않고 그 표준 통로에 배선했다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_API_ROOT = Path(__file__).resolve().parents[1]  # apps/api


def _read(rel: str) -> str:
    return (_API_ROOT / rel).read_text(encoding="utf-8")


# ── 판단: 요청 지문 ──────────────────────────────────────────────────────────
class _Body:
    """`ProjectCreateRequest` 의 최소 대역 — 스키마 import 없이 지문 판단만 태운다."""

    def __init__(self, address=None, name=None, total_area_sqm=None):
        self.address = address
        self.name = name
        self.total_area_sqm = total_area_sqm


def _fingerprint(body):
    from apps.api.routers.projects import create_request_fingerprint

    return create_request_fingerprint(body)


def test_같은_프로젝트의_재전송은_같은_지문이다():
    """★핵심 — 최초 생성과 고아 재전송은 **이름·면적이 갈리는데** 같은 요청이어야 한다.

    실측 근거: 고아 마이그레이션은 `name || address` 로 이름을 만들고 면적은 로컬 레코드의
    `area` 문자열에서 파싱한다. 최초 생성은 `effectiveLandAreaSqm` 을 쓴다. 두 값이 갈린다.
    전체 본문을 지문에 넣으면 그 재전송이 422 로 거부돼 **영원히 서버에 도달하지 못한다.**
    """
    first = _Body(address="경기도 오산시 내삼미동", name="오산시 내삼미동 외 76필지", total_area_sqm=86755.0)
    resend = _Body(address="경기도 오산시 내삼미동", name="경기도 오산시 내삼미동", total_area_sqm=None)
    assert _fingerprint(first) == _fingerprint(resend)


def test_주소가_다르면_지문도_다르다_양성대조군():
    """[양성 대조군] 지문이 **항상 같은** 상수가 아니다 — 그러면 키 오사용 방어가 죽는다."""
    a = _Body(address="경기도 오산시 내삼미동")
    b = _Body(address="서울특별시 동작구 상도동 211-376")
    assert _fingerprint(a) != _fingerprint(b)


def test_주소_미상은_빈문자로_접힌다_None_날조_금지():
    assert _fingerprint(_Body(address=None)) == {"address": ""}


# ── 판단: 재생/충돌 ─────────────────────────────────────────────────────────
class _Stored:
    def __init__(self, body):
        self._body = body

    def to_response(self):
        return self._body  # 실제 Response 대신 대역(판단만 태운다)


class _Look:
    def __init__(self, state, stored=None):
        self.state = state
        self.stored = stored


def _replay(look):
    from apps.api.routers.projects import resolve_idempotent_replay

    return resolve_idempotent_replay(look)


def test_저장된_응답이_있으면_재생한다_중복생성_차단():
    """★이 분기가 중복 생성을 막는 자리다.

    이전 판(핸들러 안 `if` 두 줄)에서는 `if replay is not None:` 을 `if False:` 로 바꿔도
    **테스트가 전부 초록이었다** — 소스 검사가 `.to_response()` 라는 문자열만 봤기 때문이다.
    """
    from app.core import idempotency

    assert _replay(_Look(idempotency.STATE_REPLAY, _Stored("첫 응답"))) == "첫 응답"


def test_처음_보는_키는_정상_실행으로_떨어진다_양성대조군():
    """[양성 대조군] 항상 재생하는 함수가 아니다 — 그러면 프로젝트를 아예 못 만든다."""
    from app.core import idempotency

    assert _replay(_Look(idempotency.STATE_MISS)) is None


def test_본문이_없는_저장은_재생하지_않는다():
    """대형이라 본문을 저장하지 못한 경우 — 빈 응답을 재생하면 클라이언트가 id 를 못 받는다."""
    from app.core import idempotency

    assert _replay(_Look(idempotency.STATE_REPLAY, _Stored(None))) is None
    assert _replay(_Look(idempotency.STATE_REPLAY, None)) is None


def test_충돌_판정이_replay_와_갈린다():
    from app.core import idempotency
    from apps.api.routers.projects import is_idempotency_conflict

    assert is_idempotency_conflict(_Look(idempotency.STATE_CONFLICT)) is True
    assert is_idempotency_conflict(_Look(idempotency.STATE_REPLAY)) is False
    assert is_idempotency_conflict(_Look(idempotency.STATE_MISS)) is False


# ── 배선: 라우터가 표준 통로를 실제로 거치는가 ──────────────────────────────
@pytest.fixture(scope="module")
def _src() -> str:
    return _read("routers/projects.py")


def test_생성_엔드포인트가_멱등_헤더를_읽는다(_src):
    assert 'Header(default=None, alias="Idempotency-Key")' in _src


def test_생성_엔드포인트가_lookup_replay_conflict_save_를_모두_배선한다(_src):
    """★네 지점이 모두 있어야 계약이 성립한다 — 하나만 빠져도 조용히 중복이 생기거나 422 가 샌다."""
    for needle in (
        "idempotency.lookup(",
        # ★**호출부**를 본다 — 함수 이름만 찾으면 `def is_idempotency_conflict(look)` 라는
        #   **정의 줄**이 조건을 대신 충족시킨다. 실제로 그렇게 변이가 살아남았다
        #   (핸들러에서 `replay = None` 으로 배선을 끊었는데 초록이었다).
        "if is_idempotency_conflict(look):",
        "replay = resolve_idempotent_replay(look)",
        "idempotency.save(",
    ):
        assert needle in _src, f"멱등 배선 누락: {needle}"


def test_지문은_순수함수를_경유한다_핸들러_인라인_금지(_src):
    """판단을 핸들러 안 한 줄로 되돌리면 어떤 테스트도 그것을 태우지 못한다."""
    assert "create_request_fingerprint(body)" in _src
    assert "def create_request_fingerprint(" in _src


def test_실패는_저장하지_않는다(_src):
    """★save 는 성공 경로 뒤에만 있다 — 실패한 생성은 다시 시도돼야 한다.

    `db.commit()`(성공 확정) 뒤에 save 가 오는지를 **위치**로 본다.
    """
    commit_at = _src.index("await db.refresh(project)")
    save_at = _src.index("await idempotency.save(")
    assert save_at > commit_at, "실패해도 저장되는 자리에 save 가 있다"


def test_키가_없으면_종전동작_그대로(_src):
    """무회귀 — 헤더가 없으면 lookup·save 를 아예 타지 않는다(조건부 배선)."""
    assert "if key:" in _src


# ── 이 저장소가 표준 통로를 이미 갖고 있었다는 사실 자체를 잠근다 ──────────
def test_표준_멱등_통로는_alembic_신규헤드가_필요없다():
    """★인계 문서의 *'스키마 변경 필요'* 가 왜 거짓이었는지를 코드로 고정한다.

    다음 사람이 같은 판단을 물려받아 불필요한 마이그레이션을 만들지 않게 한다.
    """
    core = _read("app/core/idempotency.py")
    assert "CREATE TABLE IF NOT EXISTS idempotency_key" in core
    assert "alembic 신규 헤드 없음" in core
