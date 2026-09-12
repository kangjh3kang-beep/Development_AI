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

★**종료코드 계약**(기계는 rc 만 본다 — 산문은 안 읽는다):
    0  판정된 변이가 **전부** 걸렸고 **감사되지 않은 변이가 0건**
    1  ★생존 있음
    2  아무것도 감사하지 못함(변경 없음 · 테스트 못 찾음 · 기준선 실패 …)
    3  ★생존은 없으나 **판정 불가/건너뜀이 있다** — 이 실행은 **전수가 아니다**
★기계 판독은 stdout 의 **`::AUDIT=` 줄**을 보라(안내문에 안 쓰이는 형태).
  `generated / judged / caught / survived / undecided / skipped` 를 싣는다.
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
import platform
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

# 프론트 테스트 러너 위치(저장소 루트 기준). vitest 는 여기서 돌아야 한다.
_WEB_ROOT = Path("propai-platform/apps/web")

_ASSIGN = re.compile(r'^\s*(?:"[\w_]+"|[\w_]+)\s*[:=]\s*.+[,;]?\s*$')
_IF = re.compile(r'^(\s*)(el)?if\s+(.+?):\s*$')
_STR = re.compile(r'^(.*?)(["\'])((?:(?!\2).){8,})\2(.*)$')
_CALL_ARG = re.compile(r'^(\s*\w+\s*=\s*)(\w+\([^)]*\))\s*,?\s*$')


# ★TS **타입 선언**은 런타임에 사라진다 — vitest 로는 **원리적으로** 잡을 수 없다.
#   (`export type X = ...` · 인터페이스 필드 `name: Type;`)
#   변이해 봐야 전부 "생존"으로 나와 **진짜 신호를 묻는다**. 타입은 CI 의 `tsc --noEmit`
#   (Frontend type-check 잡)이 검증한다 — 여기서 제외하는 것이 역할 분담이다.
_TS_TYPE_DECL = re.compile(
    r'^\s*(?:export\s+)?(?:type|interface)\s'
    r'|^\s*\w+\??\s*:\s*[A-Za-z_][\w.<>\[\]|\s]*;?\s*$'
)


# ── 셸(.sh) 규칙 ───────────────────────────────────────────────────────────
# ★이 저장소의 배포·롤백·감시·조율 스크립트가 전부 셸이고, 그중 **17개는 이미 pytest 락을
#   갖고 있다**(2026-09-12 파생 · ★**base `cd942c6ec` 의 트리에서** 잰 값 — 17/39).
#   ★수를 인용할 때 **기준 sha 를 같이** 적는다: 처음 이 줄에 «14/35» 라 적었는데, 그것은
#     **45커밋 뒤처진 공유 워크트리**에서 잰 값이었다(독립 리뷰 MAJOR-4). 파생식은 옳았고
#     **모집단이 틀렸다** — «파생으로 쟀다»는 트리가 맞을 때만 의미가 있다.
#   그런데 이 도구가 확장자로 걸러 온 탓에 그 락들은
#   **한 번도 기계 감사를 받지 못했다** — "도구를 돌렸다"가 그 축에서는 보증이 아니었다.
# ★줄 끝 앵커(`then\s*$`)로는 이 저장소의 **한 줄 가드**를 통째로 못 본다(실측: 조건 줄
#   272건 중 44건 · 16%). 그래서 `then` **뒤를 통째로 보존**하고 조건만 죽인다 —
#   꼬리를 버리면 `fi` 가 사라져 **구문이 깨진다**(그건 변이가 아니라 파손이다).
_SH_IF = re.compile(r'^(\s*)(el)?if\s+(?!false\b)(.+?);(\s*then\b.*)$')
# ★`exit N` 도 줄 단독일 때만 보면 **게이트 계약의 대부분을 놓친다** — 이 저장소의 배포
#   가드는 `if …; then …; exit 1; fi` 한 줄 관용구를 쓴다. **토큰 경계**로 바꾼다.
#   ★`exit 0` 은 첫 자리 `[1-9]` 때문에 원리적으로 안 걸린다(성공 경로 불가침).
_SH_EXIT = re.compile(r'\bexit\s+[1-9][0-9]*\b')
_SH_ASSIGN = re.compile(
    r'^(\s*)(?:export\s+|local\s+|declare\s+(?:-[A-Za-z]+\s+)?)?'
    r'[A-Za-z_][A-Za-z0-9_]*=.*$'
)


def _shell_mutations_for_line(path: Path, line: str, line_no: int) -> list[Mutation]:
    """`.sh` 전용 변이. 값을 바꾸기보다 **경로를 끊는** 쪽을 고른다.

    ★`.py` 규칙을 그대로 쓰면 안 되는 이유: 셸 조건은 `if …:` 가 아니라 `if …; then` 이고,
      대입은 `=` 좌우에 공백이 없다. 파이썬 규칙으로는 **거의 아무것도 안 잡힌다** —
      그러면 "변이 N건"이 작게 나와 **감사한 것처럼 보이는 무감사**가 된다.
    """
    out: list[Mutation] = []

    # ① 조건무력화 — 가드가 실제로 무엇을 막는지 드러난다.
    #    ★`if false` 를 다시 `if false` 로 바꾸는 **무변화 변이**는 만들지 않는다
    #      (정규식의 `(?!false\b)`). 그런 변이는 항상 생존해 신호를 더럽힌다.
    m = _SH_IF.match(line)
    if m:
        indent, el, _cond, tail = m.group(1), m.group(2) or "", m.group(3), m.group(4)
        out.append(Mutation("조건무력화", path, line, f"{indent}{el}if false;{tail}", line_no))

    # ② 종료코드무력화 — **게이트 스크립트의 핵심 계약**이다.
    #    ★이 저장소의 셸 락 상당수가 "위반이면 0 이 아닌 코드로 죽는다"를 계약으로 삼는다.
    #      rc 를 안 보는 테스트는 이 변이에서 **생존**하고, 그것이 정확히 구멍이다.
    #    ★`exit 0` 은 대상이 아니다(성공 경로를 실패로 만드는 것은 계약 위반이 아니라 파손).
    # ★★**토큰마다 하나씩** 만든다. `sub()` 로 한꺼번에 죽이면 **두 계약이 한 변이에 묶여**
    #   테스트가 둘 중 하나만 봐도 CAUGHT 가 나오고 나머지 한쪽의 무잠금이 **가려진다**.
    #   ★이 PR 이 `safe-deploy.sh` 에서 찾아낸 결함(`or` 가 두 생존자를 서로 덮음)과
    #     **같은 가림 기제**다 — 그것을 보고하면서 같은 자리를 내 도구 안에 만들고 있었다.
    #   실측: 한 줄에 `exit N` 이 둘인 곳이 **6군데**(`safe-deploy.sh:164,229` · 계기판 4줄).
    for mo in _SH_EXIT.finditer(line):
        out.append(Mutation(
            "종료코드무력화", path, line,
            line[: mo.start()] + "exit 0" + line[mo.end():], line_no,
        ))

    # ③ 줄삭제 — "정의만 하고 소비처 0" 이 여기서 드러난다.
    if _SH_ASSIGN.match(line):
        out.append(Mutation("줄삭제", path, line, "", line_no))

    # ④ 문자열변경 — 문구 계약·소스 검사가 실제로 그 문자열을 보는지.
    m = _STR.match(line)
    if m:
        head, q, _body, tail = m.groups()
        out.append(Mutation("문자열변경", path, line, f"{head}{q}__MUTATED__{q}{tail}", line_no))

    return out


def _mutations_for_line(path: Path, line: str, line_no: int) -> list[Mutation]:
    out: list[Mutation] = []
    stripped = line.strip()
    if not stripped:
        return out
    # ★★셸을 **주석 가드보다 먼저** 가른다. 그 가드는 `*` 로 시작하는 줄을
    #   주석(JSDoc 이어짐)으로 보는데, 셸에서 `*)` 는 주석이 아니라 **`case` 의 기본 분기**다 —
    #   이 저장소 배포 게이트의 **거부 경로**가 정확히 그 모양이다(실측 2건):
    #     safe-deploy.sh  `*) status "FAIL unknown-target:$TARGET"; exit 1 ;;`
    #     coord.sh        `*) echo "…판정 거부" >&2; exit 2 ;;`
    #   그래서 종전엔 그 두 줄의 변이가 **0건**이었다(대조군 `z) exit 1 ;;` 은 생성됨).
    #   ★**언어마다 주석 어휘가 다르다** — 한 목록으로 여러 언어를 판정하면 이렇게 왜다.
    if path.suffix == ".sh":
        if stripped.startswith("#"):
            return out                    # 셸 주석은 `#` 뿐이다
        return _shell_mutations_for_line(path, line, line_no)
    if stripped.startswith(("#", "//", "*", '"""', "'''")):
        return out
    if path.suffix in (".ts", ".tsx") and _TS_TYPE_DECL.match(line):
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


def _resolve_base(base: str) -> str:
    """`base` 를 **HEAD 와의 공통 조상**으로 낮춘다 — 남의 커밋을 대상에서 뺀다.

    ★왜 (2026-08-27 · SESSION-H 실측):
        아래 `_changed_files` 는 **두-점** diff 다(워킹트리를 봐야 해서 — 그 이유는 거기
        주석에 있다). 두-점은 **양방향** 차이라, `origin/main` 이 내 HEAD 보다 앞서면
        **남이 머지한 파일까지** 변이 대상이 된다. 이 도구가 없애려는 상태 — 진짜 신호가
        남의 코드에서 나온 소음에 묻히는 것 — 을 이 도구가 스스로 만든다.

        실측: 26변이·생존 9 중 **5건이 남이 머지한 파일**(`growth_stale_producer_probe.py`)
        이었다. 공통 조상으로 낮추니 21변이·생존 4.
        대조군(같은 저장소, `HEAD~5` 를 가상 HEAD 로): 두-점 **10파일** ↔ 공통조상 **0파일**.

    ★두-점을 세-점으로 바꿔서 고치지 **않는다.** 세-점은 커밋된 것만 보므로
      "커밋 전에 돌린다"는 이 도구의 정상 사용법이 조용히 무효가 된다. base 만 낮추면
      워킹트리는 그대로 보면서 남의 커밋만 빠진다.

    ★`--base HEAD~1` 처럼 **이미 조상인 ref** 에는 아무 영향이 없다
      (merge-base(HEAD~1, HEAD) == HEAD~1). 그래서 기존 사용법을 깨지 않는다.
    """
    mb = subprocess.run(
        ["git", "merge-base", base, "HEAD"], capture_output=True, text=True,
    )
    resolved = mb.stdout.strip()
    if mb.returncode != 0 or not resolved:
        # ★공통 조상이 없다(무관한 히스토리·없는 ref). **조용히 넘기지 않는다** —
        #   그대로 쓰되 남의 커밋이 섞일 수 있다는 사실을 알린다.
        print(f"★공통 조상을 찾지 못했다({base}) — base 를 그대로 쓴다. "
              f"남의 커밋이 대상에 섞일 수 있다.")
        return base
    return resolved


def _changed_files(base: str) -> list[Path]:
    # ★`A...B`(three-dot)는 **커밋된 것만** 본다. 커밋 전에 돌리는 것이 자연스러운
    # 사용법이라(실사용에서 발견) `A`(two-dot)로 워킹트리까지 포함한다.
    # ★단 그 두-점 때문에 base 가 앞서면 **남의 커밋이 들어온다** — 호출 전에
    #   `_resolve_base()` 로 공통 조상까지 낮춰서 준다(그 함수의 독스트링 참조).
    cmd = ["git", "diff", "--name-only", base]
    names = subprocess.run(cmd, capture_output=True, text=True).stdout.split()
    out = []
    for n in names:
        p = Path(n)
        if p.suffix not in (".py", ".ts", ".tsx", ".sh") or not p.exists():
            continue
        # 테스트 자체는 변이 대상이 아니다. ★프론트 관례(`__tests__/`, `*.test.ts(x)`)도
        #   함께 거른다 — 종전엔 py 관례(`tests/`, `test_*`)만 걸러 프론트 테스트 파일이
        #   변이 대상으로 들어왔다(자기 자신을 변이하는 셈).
        if "/tests/" in n or "/__tests__/" in n:
            continue
        if p.name.startswith("test_") or ".test." in p.name or ".spec." in p.name:
            continue
        if n.startswith("scripts/"):
            continue          # 도구 자신은 이 테스트들의 대상이 아니다(오탐)
        out.append(p)
    return out


def _docstring_line_nos(path: Path) -> set[int]:
    """파일의 **문자열/독스트링 내부** 줄 번호. 그 안의 문장은 코드가 아니라 설명이다.

    ★전수 감사에서 오탐이 여럿 나왔다 — 독스트링에 적어 둔 설명 문장을 "문자열 변경"
    변이로 잡아, 진짜 구멍이 소음에 묻혔다. `tokenize` 로 정확히 걸러 낸다.
    """
    import io
    import tokenize

    out: set[int] = set()
    try:
        src = path.read_text(encoding="utf-8")
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.STRING and tok.end[0] > tok.start[0]:
                out.update(range(tok.start[0], tok.end[0] + 1))
    except Exception:  # noqa: BLE001 — 걸러 내기 실패는 소음만 늘릴 뿐 결과를 왜곡하지 않는다
        return set()
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
    """변경 파일 → 짝 테스트 **추정**. 못 찾으면 호출부가 EXIT=2 로 시끄럽게 실패한다.

    ★`test_{stem}.py` 만 보던 규칙은 이 저장소의 **실제 명명규칙과 어긋났다**. 서비스 모듈은
      `_service` 접미를 달지만 테스트 파일명은 그 접미를 뗀다:
        `parcel_rights_survey_service.py` → `test_parcel_rights_survey.py`
      그래서 `app/services/**` 상당수가 **자동탐색 0건**이었고, 그 결과 변이 감사가
      "사람이 손수 고른 변이"로 대체됐다(CLAUDE.md §5 가 금지하는 바로 그것 — #588 R1 에서
      설명 불가 생존 3건을 놓친 원인). 접미 제거 폴백을 추가해 그 계열을 회복한다.

    ★★남은 한계(정직 표기 — 이걸 모르면 또 "전수 감사했다"고 착각한다):
      이 폴백으로도 **테스트명이 모듈명과 무관하면 여전히 못 찾는다**(실측: 폴백 적용 후에도
      `registry_analysis_service` · `registry` 는 MISS). 즉 이 함수는 완전 탐색이 아니라
      **휴리스틱**이다. 자동탐색이 비면 반드시 `--tests` 를 명시하라 — EXIT=2 를 "대상 없음"으로
      넘기면 그 변경은 **감사되지 않은 것**이다.
    """
    found: list[str] = []
    for p in paths:
        # ★`.sh` 는 **이름규칙으로 못 찾는다** — `safe-deploy.sh` 의 짝은
        #   `test_safe-deploy.py` 가 아니라 `test_deploy_lock_contract.py` 다.
        #   그래서 축을 **이름**이 아니라 **참조**로 바꾼다: "그 스크립트를 언급하는 테스트".
        #   ★목록을 손으로 적지 않는다(목록은 곧 상한이 된다) — 저장소에서 파생시킨다.
        if p.suffix == ".sh":
            found.extend(_tests_referencing(p))
            continue
        stems = [p.stem]
        # 서비스 모듈 명명규칙: `foo_service.py` ↔ `test_foo.py`
        if p.stem.endswith("_service"):
            stems.append(p.stem[: -len("_service")])
        for root in (Path("propai-platform/apps/api/tests"), Path("tests")):
            for stem in stems:
                cand = root / f"test_{stem}.py"
                if cand.exists():
                    found.append(str(cand))
    return sorted(set(found))


def _tests_referencing(script: Path) -> list[str]:
    """그 셸 스크립트를 **언급하는** 테스트 파일들(저장소에서 파생).

    ★고정문자열(`-F`)로 찾는다 — `basename` 에 `.`·`-` 가 들어 있어 정규식으로 읽히면
      `safe-deploy.sh` 가 `safeXdeployYsh` 를 집는다.
    ★경계가 필요하다: 종전 손조회에서 `[.]sh` 패턴이 **`.shadow`·`.shape`·`.sheet`** 를 집어
      40 파일 위양성을 냈다. basename 전체를 고정문자열로 쓰면 그 함정에 안 빠진다.
    """
    r = subprocess.run(
        ["git", "grep", "-l", "-F", script.name, "--", "*test*.py"],
        capture_output=True, text=True, check=False,
    )
    return sorted(set(r.stdout.split()))


def _is_front(test: str) -> bool:
    return test.endswith((".ts", ".tsx"))


def _audit_counts(
    generated: int, survived: int, undecided: int, skipped: int, truncated: int = 0,
) -> dict[str, int]:
    """이 실행의 **분모와 분자**. 순수 함수로 둔다 — 산수는 잠글 수 있어야 한다.

    ★`judged` 에서 **`undecided` 와 `skipped` 를 둘 다** 뺀다. 종전엔 `skipped` 를 안 빼서
      *"판정된 N건이 전부 걸렸다"* 가 **거짓 수**였다(독립 리뷰 MAJOR-2 — 실제로 돌아간 변이가
      0건인데 「판정된 2건」 + EXIT=0 이 나왔다).
    """
    judged = generated - undecided - skipped - truncated
    return {
        "generated": generated, "judged": judged, "caught": judged - survived,
        "survived": survived, "undecided": undecided, "skipped": skipped,
        "truncated": truncated,
    }


def _audit_exit(counts: dict[str, int]) -> int:
    """`::AUDIT=` 계수 → 종료코드. **기계는 rc 만 본다**(모듈 독스트링의 계약).

    ★`undecided`·`skipped`·**`truncated`** 가 있는데 0 을 주면 호출자에겐 「전수 CAUGHT」와
      **같은 신호**다.
    ★★`truncated`(`--max` 절단)를 빠뜨린 판이 실제로 있었다 — 기본 `--max 60` 인데 이 저장소
      `.sh` 전수 생성은 **2,441건**이라 **정상 사용 경로에서 97.5% 가 감사되지 않은 채 `rc=0`**
      이 나갔다. 도구는 «전수가 아니다» 를 **산문으로** 찍고 있었고 기계는 그것을 안 읽는다
      (독립 리뷰 R2 MAJOR-A).
    """
    if counts["survived"]:
        return 1
    if counts["undecided"] or counts["skipped"] or counts["truncated"]:
        return 3
    return 0


def _apply_at_line(original: str, m: "Mutation") -> str | None:
    """변이를 **그 줄 번호에** 적용한다. 줄이 기대와 다르면 `None`(건너뜀).

    ★`str.replace(old, new, 1)` 은 **첫 번째** 일치를 바꾸므로, 같은 줄이 파일에 여러 번
      나오면 **엉뚱한 자리**를 바꾼다. 종전 판은 그래서 «유일하지 않으면 버린다» 로 피했는데,
      그러면 셸에서 손실이 크다 — `exit 1` 은 배포 게이트의 **표준 실패코드**라 한 파일에
      여러 번 나온다(실측: 종료코드 규칙 생성 55건 중 **22건(40%)** 이 그렇게 버려졌다).
    """
    lines = original.splitlines(keepends=True)
    idx = m.line_no - 1
    if not (0 <= idx < len(lines)):
        return None
    raw = lines[idx]
    body = raw.rstrip("\n").rstrip("\r")
    if body != m.old:
        return None
    lines[idx] = m.new + raw[len(body):]
    return "".join(lines)


def _mutant_broke_syntax(path: Path) -> str:
    """변이가 **대상 파일의 구문을 깼는가**. 깼으면 사유, 아니면 빈 문자열.

    ★왜 필요한가 — **구문이 깨진 변이는 「잡힌 것」이 아니라 「못 돈 것」이다.**
      그런데 테스트는 실패하므로 이 도구는 그것을 `kill`(=CAUGHT)로 센다. 즉 **변이 점수가
      거짓으로 부풀고**, 진짜로 잠긴 자리와 구분되지 않는다.
      형제 도구 `scripts/mutate_manual.sh` 는 이 상태를 **`exit 16`(판정 불가)** 으로 이미
      가른다 — 이 도구에는 그 개념이 **없었다**(2026-09-12 원문 통독으로 확인).

    ★`.sh` 는 `bash -n` 이다 — **`sh -n` 이 아니다.**
      이 저장소의 `.sh` **39개 중 6개**가 bash 확장을 써서 `sh -n` 으로는 **변이가 없어도**
      실패한다(2026-09-12 전수 실측 · base `cd942c6ec` · 대조군 `bash -n` 실패 **0/39**).
      `sh -n` 으로 짰으면 그 6개의 모든 변이가 **거짓 「판정 불가」**가 됐을 것이다.

    ★★**이 축은 `.ts/.tsx` 에서 닫히지 않는다** — 값싼 구문검사가 없다(`tsc` 는 프로젝트
      전체를 태워야 해서 변이마다 돌릴 수 없다). 그 공백을 **여기 적어 둔다**:
      프론트 변이는 여전히 「구문 파손 = 거짓 CAUGHT」 가능성이 있다.
    """
    if path.suffix == ".sh":
        r = subprocess.run(
            ["bash", "-n", str(path)], capture_output=True, text=True, check=False,
        )
        if r.returncode != 0:
            return (r.stderr.strip().splitlines() or ["bash -n 실패"])[-1]
        return ""
    if path.suffix == ".py":
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as e:
            return f"SyntaxError: {e.msg} (line {e.lineno})"
        except Exception:  # noqa: BLE001 — 읽기 실패는 구문 판정이 아니다
            return ""
        return ""
    return ""


def _rel_test(t: str, cwd: Path) -> str:
    """테스트 경로를 **러너 cwd 에서 풀리는 형태**로.

    ★`.sh` 의 짝 테스트는 `propai-platform/tests/` 에도 산다(`integrator_dashboard.sh` ·
      `coord.sh` 계열). 그 경로는 기본 cwd(`propai-platform/apps/api`)에서 **안 풀린다** —
      그대로 주면 pytest 가 «file or directory not found» 로 죽고, 그것이 **기준선 실패**로
      보여 «코드가 깨졌다» 는 엉뚱한 진단을 부른다.
    ★**지금 풀리는 경로는 건드리지 않는다**(회귀 방지) — 안 풀리는 것만 절대경로로 승격한다.
    """
    if "apps/api/" in t:
        return t.split("apps/api/", 1)[-1]
    if Path(t).is_absolute() or (cwd / t).exists():
        return t
    resolved = Path(t).resolve()
    return str(resolved) if resolved.exists() else t


# 마지막 실패 실행의 출력(진단용). 기준선이 깨졌을 때 **왜인지** 보여 주기 위해 남긴다.
_LAST_FAILURE: str = ""


def _run(tests: list[str], cwd: Path) -> bool:
    """테스트가 **통과**하면 True(= 변이 생존).

    ★러너를 테스트 확장자로 고른다 — `.ts/.tsx` 는 vitest, 나머지는 pytest.
    종전엔 pytest 만 돌려 **프론트가 통째로 검증에서 빠졌다**(실제로 그 상태로
    "전수 감사·생존 0"을 선언했다).
    """
    global _LAST_FAILURE
    front = [t for t in tests if _is_front(t)]
    back = [t for t in tests if not _is_front(t)]

    if back:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", *back, "-q", "--no-header", "-x"],
            capture_output=True, text=True, cwd=cwd,
        )
        if r.returncode != 0:
            _LAST_FAILURE = (r.stdout or "") + (r.stderr or "")
            return False

    if front:
        web = _WEB_ROOT
        rel = [t.split("apps/web/", 1)[-1] if "apps/web/" in t else t for t in front]
        r = subprocess.run(
            ["pnpm", "exec", "vitest", "run", *rel, "--reporter=dot"],
            capture_output=True, text=True, cwd=web,
        )
        if r.returncode != 0:
            _LAST_FAILURE = (r.stdout or "") + (r.stderr or "")
            return False

    return True


def _diagnose_baseline() -> str:
    """기준선이 왜 깨졌는지 한 문단.

    ★이 함수가 있는 이유(2026-08-24 실측): 종전 메시지는 *"기준선이 이미 실패한다"* 뿐이라
      **코드가 깨진 것으로 오독**된다. 실제 원인은 **인터프리터**였다 —
      `python3 scripts/mutate_changed.py` 로 부르면 `sys.executable` 이 시스템 파이썬(3.10)이
      되고, 앱이 쓰는 `datetime.UTC`(3.11+)에서 임포트가 죽는다. 같은 함정으로 이 도구를
      **두 번 포기했다**. 진단 불가는 그 자체로 장애다.
    """
    tail = "\n".join([ln for ln in _LAST_FAILURE.splitlines() if ln.strip()][-12:])
    hint = ""
    low = _LAST_FAILURE
    if "ImportError" in low or "SyntaxError" in low or "ModuleNotFoundError" in low:
        need = _required_python()
        hint = (
            f"\n★인터프리터를 의심하라. 지금 이 도구는 **{platform.python_version()}** 로 테스트를 돌린다"
            f"{f'(프로젝트 요구: {need})' if need else ''}.\n"
            "  프로젝트 venv 로 다시 실행하라:\n"
            "    <venv>/bin/python scripts/mutate_changed.py --tests <경로>\n"
            "  (`python3 scripts/…` 로 부르면 시스템 파이썬이 잡혀 앱 임포트가 깨진다)"
        )
    return (tail + hint) if (tail or hint) else "(출력 없음)"


def _required_python() -> str:
    """`pyproject.toml` 의 requires-python — 없으면 빈 문자열."""
    for name in ("propai-platform/apps/api/pyproject.toml", "pyproject.toml"):
        f = Path(name)
        if not f.exists():
            continue
        m = re.search(r'requires-python\s*=\s*"([^"]+)"', f.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--tests", nargs="*", default=None)
    ap.add_argument("--max", type=int, default=60)
    # ★★`--only` — 지정한 테스트가 **실제로 덮는 파일**로 좁힌다.
    #   확장자만 맞추면(프론트 테스트 ↔ 모든 .tsx) 무관한 파일이 전부 "생존"으로 나와
    #   진짜 신호가 묻힌다.
    #   ★2026-08-27 정정 — 종전 이 자리에 *"멀티세션 저장소라 남의 변경까지 diff 에
    #     들어온다"* 고 적혀 있었다. **그건 이제 참이 아니다**: `_resolve_base()` 가
    #     base 를 공통 조상까지 낮춰 남의 커밋을 구조적으로 뺀다. 이 주석이 지목하던
    #     결함을 **목록형 필터(`--only`)로 우회하던 것**이 근본이었다.
    #     `--only` 는 이제 **의도적 좁히기 전용**이다(무관한 조합 소음 제거).
    ap.add_argument("--only", nargs="*", default=None,
                    help="경로에 이 문자열이 포함된 파일만 변이(부분 일치)")
    ap.add_argument("--cwd", default="propai-platform/apps/api")
    args = ap.parse_args()

    # ★★CWD 의존 제거 — 하위 디렉토리에서 돌리면 `git diff` 가 그 경로만 보여
    #   "변경 없음"으로 **조용히 무효**가 된다(실측). 저장소 루트로 고정한다.
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
    ).stdout.strip()
    if root:
        import os

        os.chdir(root)

    # ★base 를 **공통 조상까지 낮춘 뒤** 쓴다 — 두 소비처(`_changed_files`·`_added_lines`)가
    #   같은 값을 봐야 한다. 한쪽만 낮추면 파일 목록과 변이 줄이 어긋난다.
    base = _resolve_base(args.base)
    if base != args.base:
        print(f"  base: {args.base} → {base[:12]} (공통 조상 · 남의 커밋 제외)")
    files = _changed_files(base)
    if not files:
        # ★"변경 없음"은 성공이 아니라 **아무것도 검증하지 않음**이다. EXIT 0 으로 두면
        #   호출자가 초록으로 읽는다(테스트 미발견 경로가 이미 2 로 실패하는 것과 대칭).
        print("★감사할 소스 변경이 없다 — 이 실행은 **아무것도 검증하지 않았다**.")
        return 2

    tests = args.tests or _guess_tests(files)
    if not tests:
        print("★테스트를 찾지 못했다 — `--tests` 로 지정하라.")
        print(f"  변경 파일: {[str(f) for f in files]}")
        return 2

    cwd = Path(args.cwd)
    rel_tests = [_rel_test(t, cwd) for t in tests]

    # ★★지정한 테스트와 **짝이 맞는 파일만** 변이한다.
    #   종전엔 변경 파일 전체 × 지정 테스트로 돌려, 프론트 테스트를 줬을 때 백엔드 변이가
    #   전부 "생존"으로 나왔다(무관한 조합이라 당연하다). 그러면 **진짜 신호가 소음에
    #   묻힌다** — 이 도구가 없애려는 상태를 이 도구가 만드는 셈이다.
    want_front = any(_is_front(t) for t in rel_tests)
    want_back = any(not _is_front(t) for t in rel_tests)
    scoped = [
        f for f in files
        if (f.suffix in (".ts", ".tsx") and want_front)
        # ★`.sh` 는 pytest 쪽이다 — 이 저장소의 셸 락은 전부 파이썬 계약테스트다
        #   (`bash` 를 직접 태우거나 소스를 읽는다). vitest 대상이 될 수 없다.
        or (f.suffix in (".py", ".sh") and want_back)
    ]
    if args.only:
        scoped = [f for f in scoped if any(pat in str(f) for pat in args.only)]
    dropped = len(files) - len(scoped)
    if dropped:
        print(f"  (테스트와 짝이 맞지 않는 파일 {dropped}개는 대상에서 제외)")
    files = scoped

    muts: list[Mutation] = []
    for f in files:
        skip = _docstring_line_nos(f)
        for no, line in _added_lines(base, f):
            if no in skip:
                continue      # 여러 줄 문자열(독스트링) 내부 — 코드가 아니다
            muts.extend(_mutations_for_line(f, line, no))
    # ★★상한 절단은 **절대 조용히 하지 않는다.** 잘린 부분은 감사되지 않았는데, 그 사실을
    #   안 알리면 "생존 N건"이 전수 결과로 읽힌다 — 이 도구가 잡으려는 '공허한 초록'을
    #   이 도구가 저지르는 꼴이다.
    #   ★실증(2026-08-15): `--max 300` 을 준 실행이 **정확히 300건에서 소스 순서로 잘려**
    #     변경 파일 하나에 변이가 **0건** 배정됐고, 신규 로직에는 도달조차 못 했다. 그런데도
    #     출력은 평온해서 "34 생존"이 전수 감사로 보고될 뻔했다. 같은 함정에 두 사람이
    #     연달아 빠졌다 — 침묵이 원인이었다.
    total_generated = len(muts)
    dropped = 0
    if total_generated > args.max:
        dropped = total_generated - args.max
        muts = muts[: args.max]
        by_file: dict[str, int] = {}
        for m in muts:
            by_file[m.path.name] = by_file.get(m.path.name, 0) + 1
        print(
            f"⚠️  상한 절단 — 생성 {total_generated}건 중 **{dropped}건을 버렸다**"
            f"(--max {args.max}).\n"
            f"    절단은 **소스 순서**라 뒤쪽 파일·뒤쪽 함수가 통째로 빠진다. "
            f"이 실행은 **전수 감사가 아니다**.\n"
            f"    실제 배정: "
            + " · ".join(f"{k} {v}건" for k, v in by_file.items())
            + f"\n    전수로 돌리려면 `--max {total_generated}` 이상을 주거나 `--only` 로 좁혀라.\n"
        )

    print(f"대상 파일 {len(files)}개 · 테스트 {rel_tests} · 변이 {len(muts)}건\n")

    # ★★변이가 0건인데 "생존 0" 을 찍으면 **공허한 초록**이다 — 아무것도 검증하지 않고
    #   통과한 것을 통과로 보고하게 된다. 이 도구가 잡으려는 결함을 이 도구가 저지르면 안 된다.
    if not muts:
        print("★변이를 하나도 만들지 못했다 — 검증된 것이 **없다**(초록이 아니다).")
        print("  변경이 주석·공백뿐이거나, 대상 파일이 규칙에 안 걸렸을 수 있다.")
        return 2

    # ★★프론트(.ts/.tsx) 변경이 있는데 프론트 테스트를 못 돌리면 **그 사실을 알린다**.
    #   조용히 넘기면 "백엔드만 감사하고 전수라고 부르는" 실수를 반복한다(실제로 저질렀다).
    front_files = [f for f in files if f.suffix in (".ts", ".tsx")]
    front_tests = [t for t in rel_tests if t.endswith((".ts", ".tsx"))]
    if front_files and not front_tests:
        print(f"★★프론트 변경 {len(front_files)}개가 있는데 프론트 테스트가 지정되지 않았다.")
        print("  ★러너는 확장자로 고르지만(#586) **탐색은 pytest 전용**이다 —")
        print("    프론트는 `--tests <경로>` 로 직접 줘야 vitest 로 돈다.")
        for f in front_files[:8]:
            print(f"    미검증: {f}")
        print("  → vitest 로 따로 돌리거나, 최소한 이 공백을 기록하라(조용히 넘기지 말 것).")
        print()

    # ★★프론트 테스트를 지정했는데 `node_modules` 가 없으면 vitest 가 못 돈다.
    #   그대로 두면 "전부 kill" 로 보여 **거짓 초록**이 된다(변이가 안 죽은 게 아니라
    #   테스트가 아예 못 돈 것이다). 먼저 확인하고 명시적으로 실패한다.
    if any(_is_front(t) for t in rel_tests) and not (_WEB_ROOT / "node_modules").exists():
        print(f"★프론트 테스트를 지정했는데 {_WEB_ROOT}/node_modules 가 없다 — vitest 를 "
              "돌릴 수 없다. `pnpm install` 후 다시 실행하라(지금 결과는 신뢰할 수 없다).")
        return 2

    # ★기준선 먼저 — 변이 전에 통과하지 않으면 결과가 무의미하다.
    if not _run(rel_tests, cwd):
        print("★기준선이 이미 실패한다 — 변이 결과를 신뢰할 수 없다. 먼저 고쳐라.")
        print("── 왜 실패했나 ──────────────────────────────────────────────")
        print(_diagnose_baseline())
        return 2

    survived: list[Mutation] = []
    # ★「판정 불가」를 생존·사망과 **다른 통**에 담는다. 한 통에 섞으면 그 수가 두 사건을
    #   덮어(형제 도구가 `::VERDICT=UNDECIDED` 로 가르는 바로 그 자리) 사람을 틀린 곳으로 보낸다.
    undecided: list[tuple[Mutation, str]] = []
    # ★`skipped` 를 **세 번째 통**으로 둔다. 종전엔 건너뛴 변이가 어느 통에도 안 들어가
    #   "판정된 N건" 이 **거짓 수**였다(독립 리뷰 MAJOR-2).
    skipped: list[Mutation] = []
    for i, m in enumerate(muts, 1):
        original = m.path.read_text(encoding="utf-8")
        # ★★**줄 번호로 치환한다** — 종전의 `original.count(m.old) != 1` 은 **같은 줄이
        #   두 번 나오면 그 변이를 통째로 버렸다.** 셸에서 그 손실이 크다(실측: 종료코드
        #   규칙의 **40%** 가 `exit 1` 중복으로 버려졌다 — 배포 게이트의 표준 실패코드다).
        #   변이 줄 번호는 `_added_lines` 가 **원본 기준**으로 준 값이고, 우리는 매번
        #   `original` 에서 새로 쓰므로 밀릴 수 없다. 그래도 **일치를 확인**하고,
        #   안 맞으면 조용히 넘기지 않고 `skipped` 로 **따로 센다**.
        mutated = _apply_at_line(original, m)
        if mutated is None:
            skipped.append(m)
            print(f"  [{i:3}/{len(muts)}] skip(줄 불일치)  {m.label()}")
            continue
        # ★`try/finally` — 중간에 예외(KeyboardInterrupt 포함)가 나도 **변이가 남지 않는다**.
        #   종전엔 원복이 정상 경로에만 있어, 끊기면 오염된 소스가 그대로 남았다.
        broke, alive = "", False
        try:
            m.path.write_text(mutated, encoding="utf-8")
            # ★★구문 게이트 — **변이 자신이 원인**인 실패를 「잡혔다」로 세지 않는다.
            #   깨진 변이는 테스트를 실패시키지만 그것은 «락이 잡은 것»이 아니라
            #   «코드가 아예 안 돈 것»이다. 세면 변이 점수가 거짓으로 부푼다.
            broke = _mutant_broke_syntax(m.path)
            # ★★**구문이 깨져도 테스트는 돌린다.** 깨진 변이에서 테스트가 **통과**하면
            #   정보가 하나도 안 줄었다 — «그 파일을 아무도 태우지 않는다»는 뜻이라
            #   **「생존」이 옳은 판정**이다. 여기서 판정을 접으면 이 도구는 *거짓 CAUGHT* 만이
            #   아니라 **진짜 SURVIVED 신호까지** 같은 통에 넣어 초록으로 만든다
            #   (독립 리뷰 MAJOR-3 · base 판이 `★생존`+EXIT=1 로 내던 신호였다).
            #   ⇒ 「판정 불가」는 **깨졌고 그래서 실패한** 경우로 좁힌다.
            alive = _run(rel_tests, cwd)
        finally:
            m.path.write_text(original, encoding="utf-8")
        assert m.path.read_text(encoding="utf-8") == original, f"원복 실패: {m.path}"
        if broke and not alive:
            undecided.append((m, broke))
            print(f"  [{i:3}/{len(muts)}] 판정불가  {m.label()}\n"
                  f"{'':>21}← 변이가 구문을 깼다: {broke}")
            continue
        print(f"  [{i:3}/{len(muts)}] {'★생존' if alive else 'kill '}  {m.label()}")
        if alive:
            survived.append(m)

    print(f"\n{'=' * 70}")
    # ★분모는 **자르기 전 수**다. `len(muts)` 는 이미 잘린 리스트라 그것을 쓰면
    #   `::AUDIT=generated=` 가 **거짓 분모**를 말한다(실측: 생성 9 · 출력 2).
    counts = _audit_counts(
        total_generated, len(survived), len(undecided), len(skipped), dropped,
    )
    judged = counts["judged"]
    # ★★**기계 판독 줄** — 사람이 읽는 산문과 분리한다. 형제 `scripts/mutate_manual.sh` 가
    #   `::VERDICT=` 로 이미 그렇게 한다(안내문에 절대 안 쓰이는 형태).
    #   종전엔 이 도구의 판정이 **산문에만** 있어, 호출자는 rc 밖에 볼 것이 없었다.
    print("::AUDIT=" + " ".join(f"{k}={v}" for k, v in counts.items()))
    if undecided:
        # ★조용히 넘기지 않는다 — 「판정 불가」를 안 알리면 분모가 작아진 채
        #   "생존 0" 이 **전수 결과로** 읽힌다(이 도구가 잡으려는 공허한 초록).
        print(f"★판정 불가 {len(undecided)}건 — **CAUGHT 도 SURVIVED 도 아니다**"
              f"(변이가 구문을 깨 테스트가 못 돌았다). 이 수만큼 분모가 작다:")
        for m, why in undecided:
            print(f"  {m.label()}  ← {why}")
        print()
    if dropped:
        print(f"★`--max` 로 버린 변이 {dropped}건 — **감사되지 않았다**. "
              "절단은 소스 순서라 뒤쪽 파일이 통째로 빠진다(rc 에 실린다).")
    if skipped:
        print(f"★건너뛴 변이 {len(skipped)}건 — 줄이 기대와 달라 **주입하지 못했다**. "
              "이 수만큼도 분모가 작다(도구 결함일 수 있으니 조용히 넘기지 마라).")
    if not survived:
        if undecided or skipped:
            # ★★**rc 에 싣는다.** 「판정 불가」를 신설해 놓고 `EXIT=0` 으로 내보내면
            #   호출자·CI·`&&` 체인에는 **「전수 CAUGHT」와 완전히 같은 신호**가 간다
            #   (독립 리뷰 MAJOR-1 — *«기계는 rc 만 본다»*).
            print(f"★판정 {judged}건은 전부 걸렸으나 **감사되지 않은 변이가 "
                  f"{counts['undecided'] + counts['skipped']}건** 있다 — 전수가 아니다.")
            return _audit_exit(counts)
        print(f"생존 0 — 판정된 {judged}건이 전부 테스트에 걸린다.")
        return _audit_exit(counts)
    print(f"★생존 {len(survived)}건 — 각각 **설명하거나 락을 추가**하라:\n")
    for m in survived:
        print(f"  {m.label()}")
    print(
        "\n생존이 곧 결함은 아니다. 이중 가드·도달 불가 방어라면 **그 사실을 코드에 적어라**"
        "(변이 점수 부풀리기 방지). 설명할 수 없는 생존만 진짜 구멍이다."
    )
    # ★rc 는 **한 축에서만** 나온다 — 여기서 손으로 1 을 쓰면 계수와 rc 가 따로 놀 수 있다.
    return _audit_exit(counts)


if __name__ == "__main__":
    raise SystemExit(main())
