"""sw 캐시명 파생 계약 — **사람이 올리지 않는다. 빌드가 만든다.**

★왜 (2026-08-16):
    종전에는 배포마다 사람이 `sw.js` 의 `CACHE_NAME` 문자열을 올렸다. 그 결과
      ① **범프 전용 PR 이 85개** 쌓였다(각각 CI 약 16분 + 채번 조율. 세 세션이 1분 안에
         같은 번호를 채번한 사고도 났다)
      ② **순서 결함(CLAUDE.md E-22)** 이 상시 존재했다 — 범프가 기능 PR 보다 먼저 머지되면
         그 기능이 앱셸 캐시에 가려진다. `#644` 가 실제로 그렇게 새어 나갔다
      ③ 그래서 **자동배포를 켤 수 없었다**(머지마다 배포되면 ②가 상시화된다)
    빌드가 만들면 **순서라는 것이 존재하지 않게 되어** ②가 원리적으로 사라진다.

★이 테스트가 지키는 것은 문구가 아니라 **배선**이다. 네 자리가 다 살아 있어야 값이 흐른다:
    safe-deploy.sh(산출·export) → docker-compose.yml(build arg) → Dockerfile.web(ARG/ENV·치환) → sw.js(앵커)
  한 곳만 끊겨도 조용히 옛 캐시명이 나가거나 치환이 안 된 채 배포된다.

★그리고 **치환 실패가 조용하면 지금보다 나쁘다** — 모든 배포가 같은 캐시명을 쓰게 되어
  앱셸 캐시가 **영원히 무효화되지 않는다**. 그래서 Dockerfile 이 3중으로 막고(fail closed),
  이 테스트가 그 가드들이 **실재하는지**를 잠근다.
"""
from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

# ★대조군 강제 통로(2026-08-17 신설). 이 파일의 스캔은 종전에 손수 grep 이었고,
#   그 방식이 이 세션에서 **위양성 7건**을 냈다(전부 "위반 0"이라는 결과는 같았고
#   대조군만이 검사기 사망과 진짜 부재를 갈랐다). 이제 통로를 거친다.
from tests._scan_guard import assert_absent, code_lines

_REPO = Path(__file__).resolve().parents[4]
_PLATFORM = _REPO / "propai-platform"
_SW = _PLATFORM / "apps" / "web" / "public" / "sw.js"
_DOCKERFILE = _PLATFORM / "Dockerfile.web"
_COMPOSE = _PLATFORM / "docker-compose.yml"
_DEPLOY = _PLATFORM / "scripts" / "safe-deploy.sh"

_DEV_PLACEHOLDER = 'const CACHE_NAME = "propai-vdev-local";'


def _read(p: Path) -> str:
    assert p.exists(), f"{p} 가 없다 — 배선의 한 자리가 사라졌다."
    return p.read_text(encoding="utf-8")


def test_sw_상수는_손으로_올린_버전이_아니라_치환_앵커다() -> None:
    """`propai-v<숫자>-<설명>` 같은 **손 채번 형태**가 남아 있으면 실패한다."""
    src = _read(_SW)
    assert _DEV_PLACEHOLDER in src, (
        f"sw.js 에 치환 앵커가 없다. Dockerfile.web 이 이 문자열을 찾아 바꾸므로, "
        f"형식을 바꾸려면 Dockerfile 도 함께 바꿔야 한다. 기대: {_DEV_PLACEHOLDER!r}"
    )
    # ★주석을 걷어낸 뒤 본다 — 이 파일과 sw.js 주석에 `propai-v002612-e527b6e8` 같은
    #   **예시**가 일부러 들어 있다. 실제로 그 예시를 상수로 착각한 적이 있다(위양성 #7).
    code = code_lines(src)
    decls = [ln for ln in code.splitlines() if re.match(r"\s*const\s+CACHE_NAME\s*=", ln)]
    assert len(decls) == 1, f"CACHE_NAME 선언이 {len(decls)}건 — 정확히 하나여야 한다: {decls}"
    # ★대조군을 강제하는 통로로 단언한다. `positive_control` 이 필수 인자라
    #   "대조군 없이 위반 0" 을 주장하는 것이 **문법적으로 불가능**하다.
    assert_absent(
        code,
        pattern=r'const CACHE_NAME = "propai-v\d+-\w',
        positive_control=r"const CACHE_NAME",
        reason=(
            "손으로 채번한 캐시명이 남아 있다. 이 상수는 빌드가 만든다 — "
            "범프 PR 을 다시 만들지 마라(그 방식이 E-22 순서 결함의 원인이었다)."
        ),
        where="sw.js",
    )


def test_배선_네_자리가_모두_살아_있다() -> None:
    """한 곳만 끊겨도 값이 안 흐른다 — **네 자리를 각각** 단언한다."""
    deploy = _read(_DEPLOY)
    assert "APP_BUILD_ID=" in deploy and "export APP_BUILD_ID" in deploy, (
        "safe-deploy.sh 가 APP_BUILD_ID 를 만들지·export 하지 않는다 — 빌드에 값이 도달하지 못한다."
    )
    assert "rev-list --count" in deploy and "rev-parse --short" in deploy, (
        "APP_BUILD_ID 가 커밋에서 파생되지 않는다(seq·shortsha 둘 다 필요)."
    )

    compose = _read(_COMPOSE)
    assert re.search(r"APP_BUILD_ID:\s*\$\{APP_BUILD_ID", compose), (
        "docker-compose.yml 의 web build args 에 APP_BUILD_ID 통로가 없다 — "
        "safe-deploy 가 export 해도 Dockerfile 까지 가지 못한다."
    )

    dockerfile = _read(_DOCKERFILE)
    assert "ARG APP_BUILD_ID" in dockerfile, "Dockerfile.web 에 ARG APP_BUILD_ID 가 없다."
    assert "ENV NEXT_PUBLIC_APP_VERSION=${APP_BUILD_ID}" in dockerfile, (
        "NEXT_PUBLIC_APP_VERSION 을 같은 값에서 파생하지 않는다 — 텔레메트리가 캐시키 폴백으로 "
        "되돌아간다(그게 종전 상태였고, 그래서 캐시명 형식 변경이 텔레메트리에 샜다)."
    )


def test_치환이_조용히_실패할_수_없다() -> None:
    """3중 가드가 **실재**하는지. 조용한 미치환은 캐시를 영원히 고정시킨다(지금보다 나쁘다)."""
    d = _read(_DOCKERFILE)
    guards = {
        "인자 비었음 감지": 'if [ -z "${APP_BUILD_ID}" ]',
        "치환 앵커 존재 확인": "grep -q 'const CACHE_NAME = \"propai-vdev-local\";'",
        "치환 결과 검증": 'grep -q "const CACHE_NAME = \\"${APP_BUILD_ID}\\";"',
    }
    missing = [name for name, needle in guards.items() if needle not in d]
    assert not missing, (
        f"Dockerfile.web 의 치환 가드가 빠졌다: {missing}\n"
        "가드가 없으면 치환 실패가 **조용히** 통과하고, 모든 배포가 같은 캐시명을 써서 "
        "앱셸 캐시가 영원히 무효화되지 않는다."
    )
    assert "set -eu" in d, "치환 RUN 에 `set -eu` 가 없다 — 중간 실패가 무시된다."


def test_소비처_계약이_유지된다() -> None:
    """캐시명 형식을 바꿔도 **읽는 쪽**이 살아 있어야 한다(소비처를 실제로 열어 확인했다)."""
    collector = _PLATFORM / "apps" / "web" / "lib" / "growth" / "event-collector.ts"
    src = _read(collector)
    # 접두사만 보는 형태여야 한다 — 숫자·설명 형식에 의존하면 파생값에서 깨진다.
    assert 'startsWith("propai-")' in src, (
        "event-collector 가 접두사가 아닌 형식에 의존한다 — 파생 캐시명에서 앱버전 조회가 깨진다."
    )
    # 1차 소스가 주입되면 캐시키 폴백은 애초에 안 탄다(이 PR 이 그 주입을 추가했다).
    assert "NEXT_PUBLIC_APP_VERSION" in src, "1차 소스 참조가 사라졌다."

    rollback = _PLATFORM / "scripts" / "rollback-web.sh"
    r = _read(rollback)
    assert "cut -d" in r and "CACHE_NAME" in r, (
        "rollback-web.sh 가 상수를 따옴표로 뽑지 않는다 — 형식 의존 정규식은 파생값에서 잘린다."
    )


# ── 문서가 적은 프로브 명령 (2026-08-17 추가) ────────────────────────────────
#
# 왜 있나 (실사고):
#     인계서·CLAUDE.md 가 "배포 상태는 값으로 적지 말고 **이 명령으로 재라**" 며
#     `curl -s .../sw.js | grep -m1 CACHE_NAME` 를 실었다. 그 명령은 **틀렸다.**
#     `sw.js` 에는 `propai-v` 문자열이 셋 있고 **둘이 주석**이다(형식 설명의 예시값 ·
#     레거시 이름 안내). 앵커가 없으면 그 **주석**을 집는다.
#
#     그대로 잰 세션이 *"라이브 sw 가 뒤로 갔다 — 롤백인가 CDN 편차인가"* 라는 유령을
#     만들었다. 롤백도 편차도 아니었다(CDN 6회 md5 동일·오리진 직접과 바이트 동일).
#     **조회기가 주석을 집은 것**이다.
#
# ★이 테스트는 **소스를 검사하지 않고 실행한다.** 문서에서 파이프 프로브를 뽑아
#   **실제 `sw.js` 에 흘려** 그 출력이 진짜 상수를 담는지 본다. 그래야
#   "문서에 좋은 말이 적혀 있다"가 아니라 "그 명령이 실제로 값을 준다"를 잠근다.
#   (소스 grep 락은 표현을 조금만 바꿔도 뚫린다 — CLAUDE.md §회귀망 A.3)

# 파이프 뒤에서 실행을 허용하는 명령. 문서에서 뽑은 문자열을 셸에 넘기므로
# **allowlist 를 통과하지 못하면 실행하지 않고 실패**시킨다(검증 불가 = 통과 아님).
_ALLOWED_FILTERS = {"grep", "sed", "awk", "cut", "head", "tail", "tr"}
_SHELL_METACHARS = (";", "&", "`", "$(", ">", "<", "\n")

_DOC_ROOTS = [
    _REPO / "CLAUDE.md",
    _PLATFORM / "_workspace",
    _PLATFORM / "docs",
]


def _doc_files() -> list[Path]:
    out: list[Path] = []
    for root in _DOC_ROOTS:
        if root.is_file():
            out.append(root)
        elif root.is_dir():
            out.extend(sorted(root.rglob("*.md")))
    return out


def _probe_pipelines() -> list[tuple[Path, int, str]]:
    """문서에서 ``… sw.js | <필터>`` 형태를 뽑는다. (파일, 줄번호, 파이프 뒤 세그먼트)

    ★알려진 잠재 위양성(아직 발생 안 함 · 다음 사람을 위해 적는다):
        문서가 **틀린 형태를 반례로 보여줄 때** 그 줄에 ``sw.js`` 와 파이프가 함께 있으면
        이 추출기가 그것을 "문서가 권하는 프로브"로 오인한다.
        현재 ``CLAUDE.md`` §G-28 의 반례 표는 줄에 ``sw.js`` 가 없어 걸리지 않는다.
        반례를 적을 때는 **같은 줄에 ``sw.js`` 를 쓰지 마라**(또는 이 함수에 제외 표식을 넣어라).
        검사기가 반례를 위반으로 신고하기 시작하면 그건 가드의 결함이다(§회귀망 A.6).
    """
    found: list[tuple[Path, int, str]] = []
    for path in _doc_files():
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # 마크다운 겉치레를 벗긴다: 인용부호 · 표 안의 이스케이프 파이프 · 인라인 코드 백틱
            line = raw.lstrip().lstrip("> ").replace(r"\|", "|").replace("`", "")
            if "sw.js" not in line or "|" not in line:
                continue
            head, _, tail = line.partition("|")
            if "sw.js" not in head:
                continue  # sw.js 를 읽는 파이프가 아니다
            seg = tail.strip().rstrip("|").strip()
            # ★`LIVE=$(curl … | grep …)` 처럼 **명령 치환 안**에 든 프로브는 닫는 괄호가
            #   파이프라인 끝에 붙어 온다. 그대로 실행하면 문법 오류로 빈 출력이 나고
            #   "프로브가 값을 못 뽑는다"는 **위양성**이 된다(2026-08-18 실측 — 이 검사가
            #   같은 날 작성한 인계서를 그렇게 신고했다).
            #   여는 괄호가 앞머리에 있을 때만 짝지어 떼어 낸다(무조건 떼면 정상 문법을 망친다).
            if seg.endswith(")") and "$(" in head:
                seg = seg[:-1].rstrip()
            if not seg:
                continue
            if "CACHE_NAME" not in seg and "propai-v" not in seg:
                continue
            found.append((path, lineno, seg))
    return found


def _run_probe(segment: str, sw_text: str) -> str:
    """프로브를 **실제 sw.js 본문에** 실행한다. 안전하지 않으면 실행 대신 실패."""
    for meta in _SHELL_METACHARS:
        assert meta not in segment, (
            f"문서의 프로브에 셸 메타문자 {meta!r} 가 있다 — 이 테스트는 그것을 실행하지 않는다. "
            f"검증 불가는 통과가 아니다. 프로브를 단순한 필터 파이프로 적을 것: {segment!r}"
        )
    # 인라인 주석(`  # …`)은 셸이 알아서 자르지만, allowlist 검사 전에 먼저 떼어 낸다.
    body = segment.split("#", 1)[0].strip() if " #" in f" {segment}" else segment
    for stage in body.split("|"):
        try:
            tokens = shlex.split(stage)
        except ValueError as exc:  # 따옴표가 안 닫힌 문서 조각
            raise AssertionError(f"프로브를 파싱할 수 없다({exc}): {stage!r}") from exc
        assert tokens, f"빈 파이프 단계가 있다: {segment!r}"
        assert tokens[0] in _ALLOWED_FILTERS, (
            f"허용되지 않은 명령 {tokens[0]!r} — 문서 프로브는 읽기 전용 필터여야 한다: {segment!r}"
        )
    proc = subprocess.run(
        body, shell=True, input=sw_text, capture_output=True, text=True, timeout=20
    )
    return proc.stdout


# 줄 시작 앵커. 이게 없으면 주석을 집는다 — 이 파일이 잠그는 결함의 본질이다.
#
# ★허용 표기를 **전부** 열거한다(CLAUDE.md §회귀망 A.6 — "하한을 넘는 등가 표기를 위반으로
#   신고하면 정상 코드를 막는다"). 실측으로 잡은 위양성:
#       ^const        ← 최소 형태
#       ^ *const      ← 들여쓰기 허용(더 넓지만 여전히 줄 시작 고정)
#       ^\s*const     ← 같은 것을 정규식 원자로
#   셋 다 **주석 줄을 집지 않는다**는 목적을 똑같이 달성한다. 한 표기만 인정하면
#   나머지 둘을 쓴 정당한 문서가 막힌다 — 이 파일이 방금 그 실수를 했다.
_ANCHOR_RX = re.compile(r"\^(?:\\s|[ *+])*const")


def _has_anchor(segment: str) -> bool:
    """줄 시작 앵커가 **어떤 등가 표기로든** 있는가."""
    return bool(_ANCHOR_RX.search(segment))


def _classify(segment: str, sw_text: str) -> tuple[str, str]:
    """프로브를 (판정, 근거) 로 분류한다.

    ★2026-08-17 위양성 봉합. 종전에는 **실행할 수 없는 세그먼트를 곧바로 실패**시켰다.
      그런데 실측해 보니 차단된 것 중 둘이 **앵커를 올바르게 쓴 정당한 문서**였다:

          docker exec web sh -c '… | grep -m1 "^const CACHE_NAME"'   ← 따옴표가 안 닫혀 파싱 실패
          … | grep -m1 '^const CACHE_NAME' > /tmp/x                  ← 리다이렉트 메타문자

      정상 표기를 위반으로 신고하는 것은 **가드의 결함**이다(CLAUDE.md §회귀망 A.6 — 2회 재발).
      ★이 규율이 적힌 파일을 고치는 PR 에서 내가 그 규율을 어겼다(§D.16).

    그래서 2단으로 나눈다 — **약한 판정으로 강등하되, 놓치지는 않는다**:
        실행 가능  → 실제 sw.js 에 흘려 **출력**으로 판정(가장 강함)
        실행 불가  → **앵커 유무만** 정적으로 본다(위양성 없음 · 핵심 결함은 여전히 잡힘)

    앵커 없는 프로브는 실행 가능하든 아니든 **양쪽 경로에서 다 걸린다** — 그게 요점이다.
    """
    try:
        out = _run_probe(segment, sw_text)
    except AssertionError as why:
        # 실행 불가 — 여기서 막지 않는다. 대신 앵커를 본다.
        if _has_anchor(segment):
            return "skipped", f"실행 불가라 앵커만 확인했다({str(why)[:60]}…)"
        return "broken", (
            f"실행할 수 없고 줄 시작 앵커(^const · ^ *const · ^\\s*const 중 아무거나)도 없다: "
            f"{str(why)[:80]}"
        )
    expected = _DEV_PLACEHOLDER.split('"')[1]
    if expected in out:
        return "executed", out.strip()[:60]
    return "broken", f"출력에 {expected!r} 가 없다 — 출력={out.strip()[:80]!r}"


def test_문서가_적은_프로브가_실제_sw_js_에서_상수를_뽑는다() -> None:
    """★**소스가 아니라 실행을 본다.** 문서의 명령을 진짜 `sw.js` 에 흘려 결과를 판정한다."""
    sw_text = _read(_SW)
    probes = _probe_pipelines()

    # 공허 진리 가드 — 단언 **앞에** 둔다. 문서가 옮겨지거나 표현이 바뀌어 0건이 되면
    # "위반 0"이 참이 되는 이유가 "대상이 0개"가 된다.
    assert len(probes) >= 3, (
        f"문서에서 sw.js 프로브를 {len(probes)}건만 찾았다 — **검사기가 죽었을 수 있다.** "
        f"CLAUDE.md 와 _workspace 인계서들이 이 명령을 싣고 있어야 한다. "
        f"문서를 옮겼다면 _DOC_ROOTS 를 고칠 것. 찾은 것: {[str(p) for p, _, _ in probes]}"
    )

    broken: list[str] = []
    executed = 0
    for path, lineno, seg in probes:
        verdict, why = _classify(seg, sw_text)
        if verdict == "executed":
            executed += 1
        elif verdict == "broken":
            broken.append(f"{path.relative_to(_REPO)}:{lineno}  프로브={seg!r}  {why}")

    # ★두 번째 공허 진리 가드 — **하한을 "찾은 수"가 아니라 "실행한 수"에 건다.**
    #   위양성 봉합으로 실행 불가 프로브를 통과시키게 됐는데, 그 완화가 지나치면
    #   "전부 skipped 라 위반 0" 이라는 새 공허함이 생긴다. 그 문을 여기서 닫는다.
    assert executed >= 3, (
        f"실제로 **실행된** 프로브가 {executed}건뿐이다(찾은 것 {len(probes)}건) — "
        "이 상태의 '위반 0'은 근거가 약하다. 문서의 프로브가 전부 실행 불가 형태로 바뀌었는지, "
        "아니면 allowlist·메타문자 규칙이 지나치게 좁아졌는지 보라."
    )

    expected = _DEV_PLACEHOLDER.split('"')[1]  # propai-vdev-local (저장소 소스의 값)
    assert not broken, (
        "문서의 프로브가 **실제 sw.js 에서 상수를 뽑지 못한다**:\n  "
        + "\n  ".join(broken)
        + f"\n\n기대값 {expected!r} 이 출력에 없다. 줄 시작 앵커를 줘라: "
        "grep -m1 '^const CACHE_NAME'. 앵커가 없으면 **주석의 예시값**이나 "
        "엉뚱한 주석 줄을 집는다(2026-08-17 실사고)."
    )


def test_실행할_수_없는_프로브도_앵커가_없으면_걸린다() -> None:
    """★위양성 봉합이 **구멍이 되지 않았는지** 확인한다(완화의 대조군).

    실행 불가 세그먼트를 통과시키기로 했으니, "따옴표로 감싸면 앵커 없이도 통과한다"는
    새 우회로가 생겼는지 물어야 한다. 생기지 않았음을 여기서 잠근다.
    """
    sw_text = _read(_SW)
    cases = [
        # (세그먼트, 기대 판정, 왜)
        ("""grep -m1 "^const CACHE_NAME"'""", "skipped", "실행 불가·앵커 O → 통과(위양성 방지)"),
        ("""grep -m1 '^const CACHE_NAME' > /tmp/x""", "skipped", "리다이렉트·앵커 O → 통과"),
        # ★등가 앵커 표기 — 한 표기만 인정하면 이 둘을 쓴 정당한 문서가 막힌다(§A.6).
        ("""sh -c 'grep -m1 "^ *const CACHE_NAME"'""", "skipped", "들여쓰기 허용 앵커도 앵커다"),
        ("""sh -c 'grep -mE "^\\s*const CACHE_NAME"'""", "skipped", "정규식 원자 앵커도 앵커다"),
        ("""grep -m1 "CACHE_NAME"'""", "broken", "실행 불가·앵커 X → 걸려야 한다"),
        ("""grep -m1 CACHE_NAME > /tmp/x""", "broken", "리다이렉트·앵커 X → 걸려야 한다"),
        ("""grep -m1 '^const CACHE_NAME'""", "executed", "정상 → 실행되어 값을 준다"),
        ("""grep -m1 CACHE_NAME""", "broken", "실행되지만 주석을 집는다"),
    ]
    wrong = []
    for seg, want, why in cases:
        got, detail = _classify(seg, sw_text)
        if got != want:
            wrong.append(f"{seg!r}: 기대 {want} · 실제 {got} ({why}) — {detail}")
    assert not wrong, "완화가 우회로를 만들었다:\n  " + "\n  ".join(wrong)


def test_앵커_없는_프로브는_이_테스트에_반드시_걸린다() -> None:
    """★**대조군 — 실패도 이 필터에 걸리는가.**

    위 테스트가 초록인 이유가 "판별력이 없어서"일 수 있다. 종전에 실제로 쓰이던
    **고장난 두 형태**를 같은 sw.js 에 흘려, 그것들이 **기대값을 주지 못함**을 확인한다.
    이게 무너지면(=고장난 형태도 통과하면) 위 테스트는 아무것도 잠그지 않는 것이다.
    """
    sw_text = _read(_SW)
    expected = _DEV_PLACEHOLDER.split('"')[1]

    # 양성대조 — 올바른 형태는 값을 준다(조회기 생존).
    good = _run_probe("grep -m1 '^const CACHE_NAME'", sw_text)
    assert expected in good, (
        f"앵커를 준 프로브조차 {expected!r} 를 못 뽑았다 — **테스트 하네스가 죽었다.** "
        f"sw.js 의 상수 형식이 바뀌었는지 먼저 볼 것. 출력={good.strip()[:120]!r}"
    )

    # 음성대조 — 실사고를 낸 두 형태는 반드시 실패해야 한다.
    for label, seg in (
        ("앵커 없는 grep(주석 줄을 집는다)", "grep -m1 CACHE_NAME"),
        ("패턴 매칭(주석의 예시값을 집는다)", "grep -oE propai-v[0-9a-z-]+ | head -1"),
    ):
        out = _run_probe(seg, sw_text)
        assert expected not in out, (
            f"고장난 형태({label})가 기대값을 뽑았다 — **이 대조군이 무너졌다.** "
            f"sw.js 의 주석 예시가 사라졌거나 형식이 바뀌었을 수 있다. 그렇다면 위 테스트는 "
            f"더 이상 앵커 유무를 가르지 못하므로 대조군을 다시 설계할 것. 출력={out.strip()[:120]!r}"
        )
