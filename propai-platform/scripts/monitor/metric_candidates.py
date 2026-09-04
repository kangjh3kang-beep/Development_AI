"""배포 지표 후보를 **주석을 걷어낸 실행 라인에서만** 뽑는다.

## 왜 (2026-08-25 실측 — 이 도구가 존재하는 이유)

35주기 배포에서 지표 2개(`정밀도 미표기` · `막다른 길`)가 `0 → 0` 이라
**미배포로 오보할 뻔했다.** 원문을 열어 보니 **모든 출현이 주석**이었다
(`//` · `/* */` · JSDoc). 후보를 `git diff` 의 `+` 라인에서 기계적으로 뽑았고
거기엔 주석이 섞인다. **인계서가 경고한 함정을 알면서 밟았다.**

두 번째 오류도 같은 주기에 났다: `precision` 이 0 이라 또 미배포를 의심했는데
**`/ko/projects/<id>` 상세 라우트에만 있는 청크 3개**를 안 봤을 뿐이었다.
그래서 이 도구는 후보마다 **"지금 번들에 몇 개 있나"** 를 함께 찍는다 —
0 이어야 판별력이 있고, 0 이 아니면 그 후보는 버려야 한다.

## 재구현하지 않는다

주석 제거는 저장소에 **이미 있는** `tests/_scan_guard.py` 의 `code_lines()` 를 쓴다.
(프론트 쪽 대응물은 `apps/web/lib/source-invariant.ts` 의 `__stripCommentsForScan` 이다.
 네 번 뚫리고 고친 이력이 그 파일 상단에 있다.)
★같은 규율을 두 곳에 따로 구현하면 한쪽만 고쳐지고, 그게 바로 이 저장소가
  반복해서 데인 형태다.

## 사용

    python3 propai-platform/scripts/monitor/metric_candidates.py <배포된-sha> [경로...]

출력은 후보마다: 종류 · 값 · 실행라인 출현수 · (선택) 현재 번들 출현수.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]          # propai-platform/
sys.path.insert(0, str(_ROOT))
from tests._scan_guard import code_lines             # noqa: E402  ★재구현 금지

# 최소화되지 않는 것만 후보로 삼는다.
#  · 한글/영문 **문자열 리터럴**  → 번들에 남는다
#  · **속성명**(`foo:`)          → 번들에 남는다
#  · 지역 식별자·함수명           → **최소화된다** → 후보 아님(프론트 한정)
_STR = re.compile(r'"([^"\\\n]{4,60})"|\'([^\'\\\n]{4,60})\'')
_PROP = re.compile(r'\b([a-z][a-zA-Z0-9]{5,28})\??:')
# ★`re.M` 이 **필수**다 — 이 패턴은 `^` 앵커를 쓰는데 MULTILINE 이 없으면 `^` 가
#   **문자열 맨 앞에서만** 맞는다. 즉 추가된 실행 라인의 **첫 줄이 def/class 일 때만** 잡히고
#   나머지는 전부 놓친다. 실측(2026-08-26): `#849` 의 `def max_area_sqm_for` 를 못 찾아
#   **후보 0개 + exit 0** 을 냈다(이 도구가 막으려던 바로 그 "조용한 빈 목록"이다).
#   ★더 나쁜 것은 **가끔 맞았다**는 점이다 — `#843` 은 우연히 `def` 가 첫 줄이라 1개를 냈고,
#     그래서 도구가 도는 것처럼 보였다. 틀리기만 하면 금방 드러나는데 섞이면 신뢰가 쌓인 뒤 배신한다.
_PYDEF = re.compile(r'^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]{4,40})|^\s*class\s+([A-Za-z_][A-Za-z0-9_]{3,40})', re.M)


def added_lines(base: str, paths: list[str]) -> tuple[str, str]:
    """diff 의 추가 라인을 (파이썬, 그 외) 로 나눠 돌려준다."""
    out = subprocess.run(
        ["git", "diff", f"{base}..origin/main", "--", *paths],
        capture_output=True, text=True, cwd=_ROOT.parent,
    ).stdout
    py, other, cur = [], [], None
    for ln in out.splitlines():
        if ln.startswith("+++ b/"):
            cur = ln[6:]
            continue
        if not ln.startswith("+") or ln.startswith("+++"):
            continue
        if cur and ("/tests/" in cur or "__tests__" in cur
                    or ".test." in cur or ".spec." in cur):
            continue                                  # ★테스트는 런타임이 아니다
        (py if (cur or "").endswith(".py") else other).append(ln[1:])
    return "\n".join(py), "\n".join(other)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip().splitlines()[-3].strip())
        return 2
    argv = [a for a in sys.argv[1:] if a != "--all"]
    show_all = "--all" in sys.argv
    base, paths = argv[0], (argv[1:] or ["propai-platform/"])

    py_raw, other_raw = added_lines(base, paths)
    # ★주석·문자열 위생: 저장소의 기존 도구를 경유한다(재구현 금지).
    py_code = code_lines(py_raw, comment_prefixes=("#",))
    other_code = code_lines(other_raw, comment_prefixes=("//",))
    # 블록 주석(/* */ · JSDoc)은 code_lines 가 줄 단위라 못 걷으므로 한 겹 더.
    other_code = re.sub(r"/\*.*?\*/", " ", other_code, flags=re.S)
    other_code = "\n".join(l for l in other_code.splitlines()
                           if not l.lstrip().startswith("*"))

    if not (py_code.strip() or other_code.strip()):
        print("★추가된 실행 라인이 0 이다 — 후보를 뽑을 수 없다(범위/베이스 확인).")
        return 3                                      # ★조용히 빈 목록을 내지 않는다

    cands: dict[tuple[str, str], int] = {}
    for m in _PYDEF.finditer(py_code):
        name = m.group(1) or m.group(2)
        cands[("py-def", name)] = cands.get(("py-def", name), 0) + 1
    for m in _STR.finditer(other_code):
        v = m.group(1) or m.group(2)
        if v and not v.startswith(("/", "@", "http", "use ")):
            cands[("문자열", v)] = cands.get(("문자열", v), 0) + 1
    for m in _PROP.finditer(other_code):
        cands[("속성명", m.group(1))] = cands.get(("속성명", m.group(1)), 0) + 1

    print(f"실행 라인에서 뽑은 후보 {len(cands)}개 "
          f"(★주석은 code_lines 로 걷어냄 · 테스트 파일 제외)")
    print(f"{'종류':<8} {'출현':>4}  값")
    ordered = sorted(cands.items(), key=lambda kv: -kv[1])
    LIMIT = 10**9 if show_all else 40
    for (kind, val), n in ordered[:LIMIT]:
        print(f"{kind:<8} {n:>4}  {val[:70]}")
    if len(ordered) > LIMIT:
        # ★조용히 자르지 않는다 — 내가 이 절단 때문에 "listComplete 누락"으로
        #   **도구를 오진**했다(도구는 옳았고 내 조회가 틀렸다).
        print(f"... ★{len(ordered) - LIMIT}개 더 있음(상위 {LIMIT}개만 표시). "
              f"전체는 --all 로 보라 — **절단을 부재로 읽지 마라**.")
    print("\n★다음 단계: 각 후보의 **현재 번들 출현수가 0** 인지 확인하라(0 이어야 판별력).")
    print("   bundle_collect.sh 로 수집 후 grep -oF / grep -ow 로 센다.")
    print("★그리고 후보가 사는 **라우트**를 적어 둬라 — 상세 라우트 청크를 안 모으면 0 이 나온다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
