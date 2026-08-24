"""유료·비가역 산출물 취급 규율 — **실행 가능한 형태**.

## 왜 이 파일이 있나

2026-08-24 한 세션에서 같은 뿌리의 결함이 네 얼굴로 나왔다. 전부 **돈을 주고 얻은 산출물**을
다루는 방식의 문제였다:

| 얼굴 | 실제 사건 |
|---|---|
| **다시 샀다** | 해석이 실패한 필지가 재시도마다 재발급 → 민원캐시 재차감. `/registry/bulk` 도 동일 |
| **잃었다** | 필지별 권리분석 결과가 화면 상태에만 있어 새로고침에 소실(1,200원/필지) |
| **사유를 버렸다** | 폴백이 `ai.failure_reason` 를 실어 보내는데 화면 소비 0건 |
| **실패를 성공으로 셌다** | 폴백도 `ai` 를 dict 로 주므로 존재 검사가 실패를 성공 분자에 넣었다 |

산문 지침은 이미 충분히 있었고 **그런데도 났다.** 그래서 여기서는 **기계가 강제**한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
API = Path(__file__).resolve().parents[1]

# 유료 외부발급의 **실제 실행부**. 재사용 래퍼(`get_one`)만 이것을 불러야 한다.
_UNCACHED = "_issue_uncached"
_OWNER = "services/registry/registry_service.py"


def _callers_of(name: str) -> list[str]:
    """그 이름을 **실제로 쓰는**(주석·독스트링 제외) 모듈 목록 — AST 판정."""
    out: list[str] = []
    for f in APP.rglob("*.py"):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        used = {
            n.attr if isinstance(n, ast.Attribute) else n.id
            for n in ast.walk(tree)
            if isinstance(n, (ast.Attribute, ast.Name))
        }
        if name in used:
            out.append(str(f.relative_to(APP)))
    return out


class TestPaidCallGoesThroughReuseWrapper:
    """★유료 발급은 **재사용 래퍼를 경유**한다 — 우회하면 재과금이 되살아난다."""

    def test_전제_실행부가_실재한다(self):
        """공허한 초록 방지 — 이름이 바뀌면 '위반 0'이 저절로 참이 된다."""
        assert _UNCACHED in (APP / _OWNER).read_text(encoding="utf-8"), (
            f"{_UNCACHED} 가 사라졌다 — 이 검사는 아무것도 지키지 않는다"
        )

    def test_핵심_실행부를_직접_부르는_모듈이_없다(self):
        callers = [m for m in _callers_of(_UNCACHED) if m != _OWNER]
        assert not callers, (
            "유료 발급 실행부를 직접 부른다(재사용 캐시를 우회 → 민원캐시 재차감): "
            + ", ".join(sorted(callers))
        )

    def test_래퍼가_실제로_캐시를_본다(self):
        """배선 락 — 래퍼가 남아 있어도 캐시 조회가 빠지면 무잠금이다."""
        src = ast.parse((APP / _OWNER).read_text(encoding="utf-8"))
        used = {
            n.attr if isinstance(n, ast.Attribute) else n.id
            for n in ast.walk(src)
            if isinstance(n, (ast.Attribute, ast.Name))
        }
        assert "_issue_cache_get" in used, "재사용 캐시를 조회하지 않는다"
        assert "_issue_cache_put" in used, "발급 결과를 보관하지 않는다"


class TestFailureCarriesItsReason:
    """★실패는 **사유와 함께** 돌아온다 — 사유를 버리면 복구 시간이 통째로 추적에 잡아먹힌다."""

    def test_LLM_폴백은_failure_reason_을_채운다(self):
        src = (APP / "services/registry/registry_analysis_service.py").read_text(encoding="utf-8")
        assert "failure_reason" in src, "폴백이 사유를 싣지 않는다"

    def test_폴백은_generated_False_로_자기를_구별한다(self):
        """★실패 응답이 성공과 **같은 키만** 채우면 존재 검사가 실패를 성공으로 센다.

        실제로 그렇게 일어났다 — 폴백도 `ai` 를 dict 로 주고 `safety_grade:"주의"` 까지 담아,
        화면 집계가 '분석 불가' 건을 성공 분자에 넣었다. 전용 필드가 그 구분자다.
        """
        src = (APP / "services/registry/registry_analysis_service.py").read_text(encoding="utf-8")
        assert '"generated": False' in src or "'generated': False" in src
        # 성공 판정은 그 전용 필드로만 한다(존재 검사 금지).
        assert 'ai.get("generated")' in src, "성공 판정이 전용 필드를 쓰지 않는다"
