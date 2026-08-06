#!/usr/bin/env python3
"""변경분에서 **기계적으로** 변이를 만들어 주입하고, 살아남은 것을 보고한다.

## 왜 이게 필요한가 — 사람이 고른 변이는 사람이 못 본 층을 비껴간다

이 저장소는 변이 검증을 이미 쓴다. 그런데 **변이를 작성자가 직접 고르기 때문에**,
작성자가 떠올리지 못한 층은 계속 뚫린다. 실제로 반복해서 같은 형태로 새어 나갔다:

- 상수·필드를 **정의만** 하고 소비처가 0인데 테스트는 통과("정의는 했는데 소비처 0")
- 테스트가 스텁을 써서 **파서·네트워크 층을 우회** → 그 층을 지워도 통과
- 픽스처가 두 모집단을 안 갈라 **차이가 0** → 배선을 끊어도 값이 같아 통과
- 단언이 스코프에 **함의**되어 위반이 원리적으로 불가능(공허한 참)
- 소스 검사가 **주석·문자열**에 뚫림

전부 한 가지다 — **검증이 실제 대상을 태우지 않는다**. 이 스크립트는 변이를 *고르지 않고*
diff 에서 **기계적으로 뽑아** 그 구멍을 드러낸다.

## 쓰는 법

    python3 scripts/mutate_changed.py                    # origin/main 대비 변경분
    python3 scripts/mutate_changed.py --base HEAD~1
    python3 scripts/mutate_changed.py --tests tests/test_foo.py tests/test_bar.py
    python3 scripts/mutate_changed.py --max 40           # 변이 개수 상한

기본 테스트 명령은 변경된 파일에서 추론한다(같은 이름의 `tests/test_*.py`).
찾지 못하면 `--tests` 로 직접 준다.

## 읽는 법 — 생존이 곧 결함은 아니다

생존한 변이는 **"이 줄을 망가뜨려도 아무 테스트가 알아채지 못한다"**는 사실이다.
그게 결함인지는 판단이 필요하다:

- 진짜 구멍 → 락을 추가한다
- 이중 가드라 한쪽만 죽어도 동작이 옳다 → **그 사실을 코드에 적는다**(변이 점수 부풀리기 방지)
- 도달 불가 방어 코드 → 역시 **도달 불가라고 적는다**

★생존을 0으로 만드는 것이 목표가 아니다. **설명할 수 없는 생존을 남기지 않는 것**이 목표다.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Mutation:
    kind: str
    path: Path
    old: str
    new: str
    line_no: int

    def label(self) -> str:
        return f"{self.kind:16} {self.path.name}:{self.line_no}  {self.old.strip()[:58]}"


# ── 변이 규칙 ──────────────────────────────────────────────────────────────
# 각 규칙은 "추가된 줄"을 보고 **의미를 죽이는** 최소 변형을 만든다.
# 값을 바꾸는 것보다 **경로를 끊는** 변이가 배선 구멍을 잘 드러낸다.

_ASSIGN = re.compile(r'^\s*(?:"[\w_]+"|[\w_]+)\s*[:=]\s*.+[,;]?\s*$')
_IF = re.compile(r'^(\s*)(el)?if\s+(.+?):\s*$')
_STR = re.compile(r'^(.*?)(["\'])((?:(?!\2).){8,})\2(.*)$')
_CALL_ARG = re.compile(r'^(\s*\w+\s*=\s*)(\w+\([^)]*\))\s*,?\s*$')


def _mutations_for_line(path: Path, line: str, line_no: int) -> list[Mutation]:
    out: list[Mutation] = []
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", "//", "*", '"""', "'''")):
        return out

    # ① 조건을 무력화한다 — 가드가 실제로 무엇을 막는지 드러난다.
    m = _IF.match(line)
    if m and "False" not in line:
        indent, el, _cond = m.group(1), m.group(2) or "", m.group(3)
        out.append(Mutation("조건무력화", path, line, f"{indent}{el}if False:", line_no))

    # ② 대입·필드를 지운다 — "정의만 하고 소비처 0" 이 여기서 드러난다.
    if _ASSIGN.match(line) and "def " not in line and "import " not in line:
        out.append(Mutation("줄삭제", path, line, "", line_no))

    # ③ 호출 인자를 상수로 — 배선(계산 결과 전달)이 끊긴다.
    m = _CALL_ARG.match(line)
    if m and "None" not in m.group(2):
        out.append(Mutation("배선상수화", path, line, f"{m.group(1)}0,", line_no))

    # ④ 문자열 리터럴을 바꾼다 — 문구 계약·소스 검사가 실제로 그 문자열을 보는지.
    m = _STR.match(line)
    # ★타입 어노테이션 문자열(`x: "A | None"`)은 런타임에 평가되지 않아 바꿔도 동작이
    #   같다 — 잡아 봐야 오탐이다(자기 자신에게 돌려 실측).
    _is_annotation = re.search(r'[:\)]\s*(?:->\s*)?["\']', line) and "def " in line
    if m and "import" not in line and not _is_annotation:
        head, q, body, tail = m.groups()
        out.append(Mutation("문자열변경", path, line, f"{head}{q}__MUTATED__{q}{tail}", line_no))

    return out


def _changed_files(base: str) -> list[Path]:
    # ★`A...B`(three-dot)는 **커밋된 것만** 본다. 커밋 전에 돌리는 것이 자연스러운
    # 사용법이라(실사용에서 발견) `A`(two-dot)로 워킹트리까지 포함한다.
    cmd = ["git", "diff", "--name-only", base]
    names = subprocess.run(cmd, capture_output=True, text=True).stdout.split()
    out = []
    for n in names:
        p = Path(n)
        if p.suffix != ".py" or not p.exists():
            continue
        if "/tests/" in n or p.name.startswith("test_"):
            continue          # 테스트 자체는 변이 대상이 아니다
        if n.startswith("scripts/"):
            continue          # 도구 자신은 이 테스트들의 대상이 아니다(오탐)
        out.append(p)
    return out


def _added_lines(base: str, path: Path) -> list[tuple[int, str]]:
    """`path` 에서 이 브랜치가 **추가한** 줄만. 기존 코드를 망가뜨려 소음을 내지 않는다."""
    diff = subprocess.run(
        ["git", "diff", "-U0", base, "--", str(path)],
        capture_output=True, text=True,
    ).stdout
    out: list[tuple[int, str]] = []
    lineno = 0
    for ln in diff.splitlines():
        h = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)", ln)
        if h:
            lineno = int(h.group(1))
            continue
        if ln.startswith("+") and not ln.startswith("+++"):
            out.append((lineno, ln[1:]))
            lineno += 1
        elif not ln.startswith("-"):
            lineno += 1
    return out


def _guess_tests(paths: list[Path]) -> list[str]:
    found: list[str] = []
    for p in paths:
        for root in (Path("propai-platform/apps/api/tests"), Path("tests")):
            cand = root / f"test_{p.stem}.py"
            if cand.exists():
                found.append(str(cand))
    return sorted(set(found))


def _run(tests: list[str], cwd: Path) -> bool:
    """테스트가 **통과**하면 True(= 변이 생존)."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", *tests, "-q", "--no-header", "-x"],
        capture_output=True, text=True, cwd=cwd,
    )
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--tests", nargs="*", default=None)
    ap.add_argument("--max", type=int, default=60)
    ap.add_argument("--cwd", default="propai-platform/apps/api")
    args = ap.parse_args()

    files = _changed_files(args.base)
    if not files:
        print("변경된 .py 파일이 없다.")
        return 0

    tests = args.tests or _guess_tests(files)
    if not tests:
        print("★테스트를 찾지 못했다 — `--tests` 로 지정하라.")
        print(f"  변경 파일: {[str(f) for f in files]}")
        return 2

    cwd = Path(args.cwd)
    rel_tests = [t.split("apps/api/", 1)[-1] if "apps/api/" in t else t for t in tests]

    muts: list[Mutation] = []
    for f in files:
        for no, line in _added_lines(args.base, f):
            muts.extend(_mutations_for_line(f, line, no))
    muts = muts[: args.max]

    print(f"대상 파일 {len(files)}개 · 테스트 {rel_tests} · 변이 {len(muts)}건\n")

    # ★기준선 먼저 — 변이 전에 통과하지 않으면 결과가 무의미하다.
    if not _run(rel_tests, cwd):
        print("★기준선이 이미 실패한다 — 변이 결과를 신뢰할 수 없다. 먼저 고쳐라.")
        return 2

    survived: list[Mutation] = []
    for i, m in enumerate(muts, 1):
        original = m.path.read_text(encoding="utf-8")
        if original.count(m.old) != 1:
            print(f"  [{i:3}/{len(muts)}] skip(유일하지 않음)  {m.label()}")
            continue
        m.path.write_text(original.replace(m.old, m.new, 1), encoding="utf-8")
        alive = _run(rel_tests, cwd)
        m.path.write_text(original, encoding="utf-8")
        assert m.path.read_text(encoding="utf-8") == original, f"원복 실패: {m.path}"
        print(f"  [{i:3}/{len(muts)}] {'★생존' if alive else 'kill '}  {m.label()}")
        if alive:
            survived.append(m)

    print(f"\n{'=' * 70}")
    if not survived:
        print("생존 0 — 추가한 줄이 전부 테스트에 걸린다.")
        return 0
    print(f"★생존 {len(survived)}건 — 각각 **설명하거나 락을 추가**하라:\n")
    for m in survived:
        print(f"  {m.label()}")
    print(
        "\n생존이 곧 결함은 아니다. 이중 가드·도달 불가 방어라면 **그 사실을 코드에 적어라**"
        "(변이 점수 부풀리기 방지). 설명할 수 없는 생존만 진짜 구멍이다."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
