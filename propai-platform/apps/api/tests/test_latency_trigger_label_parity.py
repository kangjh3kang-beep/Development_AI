"""★계약 락 — 지연 **발화 축** 이름이 생산자·백엔드 라벨표·프론트 라벨표에서 1:1 인가.

## 왜 이 파일이 파이썬에 있나 (2026-08-28 · 자기 감사로 발견)

같은 계약을 벌써 한 번 잠갔었다(`apps/web/.../GrowthDashboard.trigger-parity.test.ts`).
그 락은 **정규식으로** `_LATENCY_TRIGGER_LABELS` 를 긁었는데, 그 정규식이 **표기법을
재구현**한 것이라 다음이 **조용히 통과**했다(실측):

    _LATENCY_TRIGGER_LABELS = {"ratio": …, "absolute": …, 'trend': "추세"}
                                                          ↑ 세 번째만 작은따옴표

키 두 개는 여전히 추출되므로 **생존 가드(>=2)를 통과**하고, 세 번째만 조용히 사라져
**전수 일치가 참**이 된다 — 화면에는 `trend` 가 **영문 raw** 로 뜬다.

★동료 세션이 같은 날 남긴 교훈과 같은 형태다:
  ***"내 락이 태우는 것이 프로덕션 코드인가, 복제본인가?"***
  정규식은 «파이썬 dict 표기법» 을 **내가 다시 구현한 것**이고, 다시 구현한 것은 틀린다.

→ **판정은 파서로.** 파이썬 쪽은 `ast` 로 진짜 파싱한다(따옴표 종류·줄바꿈·주석 무관).
   프론트 `.tsx` 는 파이썬에 파서가 없으므로 **세 표기를 모두 받는** 정규식 + 생존 가드로 본다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parents[1]
_ANALYZER = _API / "app" / "services" / "growth" / "analyzer.py"
_DASHBOARD = _API.parent / "web" / "components" / "settings" / "GrowthDashboard.tsx"


def _module() -> ast.Module:
    return ast.parse(_ANALYZER.read_text(encoding="utf-8"))


def backend_label_keys() -> list[str]:
    """`_LATENCY_TRIGGER_LABELS` 의 키 — **ast 로** 뽑는다(표기법 무관)."""
    for node in ast.walk(_module()):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "_LATENCY_TRIGGER_LABELS":
                    assert isinstance(node.value, ast.Dict), "라벨표가 dict 리터럴이 아니다"
                    keys = [k.value for k in node.value.keys
                            if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                    assert len(keys) == len(node.value.keys), (
                        "라벨표에 문자열이 아닌 키가 있다 — 이 락이 그것을 못 본다")
                    return keys
    raise AssertionError("★_LATENCY_TRIGGER_LABELS 를 못 찾았다 — 조회기 사망(이름이 바뀌었나?)")


def backend_produced_axes() -> list[str]:
    """**실제로 생산되는** 축 이름 — 라벨표가 아니라 `triggers = [...]` 에서 ast 로 뽑는다.

    ★라벨표끼리만 맞추면 **둘 다 틀린 경우**를 못 잡는다. 생산자가 세 번째 모집단이다.
    """
    for node in ast.walk(_module()):
        if not (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "triggers" for t in node.targets)):
            continue
        comp = node.value
        if not isinstance(comp, ast.ListComp) or not comp.generators:
            continue
        it = comp.generators[0].iter
        if not isinstance(it, ast.Tuple):
            continue
        out = []
        for pair in it.elts:
            assert isinstance(pair, ast.Tuple) and pair.elts, "생산자 항목이 (이름, 값) 튜플이 아니다"
            head = pair.elts[0]
            assert isinstance(head, ast.Constant) and isinstance(head.value, str), (
                "생산자 축 이름이 문자열 리터럴이 아니다 — 동적 이름은 이 락이 못 본다")
            out.append(head.value)
        return out
    raise AssertionError("★`triggers = [...]` 생산자를 못 찾았다 — 조회기 사망")


#: `.tsx` 객체 리터럴의 키 — **세 표기를 모두** 받는다(`"k":` · `'k':` · `k:`).
#: ★한 표기만 받으면 나머지 표기가 조용히 누락돼 **전수 일치가 거짓으로 참**이 된다.
_TS_KEY = re.compile(r"""^\s*(?:"([^"]+)"|'([^']+)'|([A-Za-z_$][\w$]*))\s*:""", re.M)


def frontend_label_keys() -> list[str]:
    src = _DASHBOARD.read_text(encoding="utf-8")
    m = re.search(r"const LATENCY_TRIGGER_LABELS:\s*Record<string, string>\s*=\s*\{(.*?)\};",
                  src, re.S)
    assert m, "★프론트 LATENCY_TRIGGER_LABELS 를 못 찾았다 — 조회기 사망"
    return [a or b or c for a, b, c in _TS_KEY.findall(m.group(1))]


def test_extractors_are_alive_before_any_comparison():
    """★생존 단언을 **비교 앞에** 둔다 — 추출이 비면 «0 == 0» 으로 공허하게 초록이 된다."""
    assert _ANALYZER.is_file() and _DASHBOARD.is_file(), "대상 파일이 없다(경로가 바뀌었나?)"
    assert len(backend_label_keys()) >= 2
    assert len(frontend_label_keys()) >= 2
    assert len(backend_produced_axes()) >= 2


def test_backend_and_frontend_label_tables_match_exactly():
    """라벨표 ↔ 라벨표 **전수 일치**. 어긋나면 화면에 영문 raw 가 샌다."""
    assert sorted(frontend_label_keys()) == sorted(backend_label_keys())


def test_every_produced_axis_has_a_frontend_label():
    """★**생산되는 축**이 전부 프론트 라벨을 갖는다.

    전수 일치는 **「둘 다 없음」과 구별하지 못한다** — 생산자를 세 번째 모집단으로 태운다.
    """
    fe = set(frontend_label_keys())
    missing = [a for a in backend_produced_axes() if a not in fe]
    assert not missing, f"생산되는데 프론트 라벨이 없는 축(영문 raw 로 샌다): {missing}"


@pytest.mark.parametrize("notation", ['"trend"', "'trend'"])
def test_lock_sees_a_new_axis_in_either_quote_style(notation: str, tmp_path):
    """★**이 락이 표기법에 뚫리지 않는지**를 락 자신이 증명한다.

    종전 정규식 락은 세 번째 키만 작은따옴표로 써도 **조용히 통과**했다(실측).
    여기서는 두 표기 **모두**에서 새 축이 보여야 한다 — 안 보이면 추출기가 표기법을
    재구현하고 있다는 뜻이다.
    """
    src = _ANALYZER.read_text(encoding="utf-8")
    patched = src.replace(
        '_LATENCY_TRIGGER_LABELS = {"ratio"',
        f"_LATENCY_TRIGGER_LABELS = {{{notation}: '추세', \"ratio\"", 1)
    assert patched != src, "패치 앵커를 못 찾았다 — 이 대조군이 죽었다"
    f = tmp_path / "a.py"
    f.write_text(patched, encoding="utf-8")

    keys = []
    for node in ast.walk(ast.parse(patched)):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_LATENCY_TRIGGER_LABELS" for t in node.targets):
            keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
    assert "trend" in keys, f"{notation} 표기의 새 축을 추출기가 못 봤다 — 표기법에 뚫린다"
