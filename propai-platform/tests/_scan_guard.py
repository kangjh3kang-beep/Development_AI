"""소스/산출물 스캔 가드 — **대조군 없이 "0건"을 주장할 수 없게** 만든다.

★왜 (2026-08-16~17 · 한 세션 실측 7건):
    "위반 0"이라는 **결과는 매번 같았다.** 갈라 준 것은 오직 대조군이었다.

    | # | 위양성 | 무엇이 갈랐나 |
    |---|---|---|
    | 1 | `grep -c` 가 0건일 때 exit 1 → `|| echo 0` 동시 실행 → 값이 `"0\\n0"` | 양성대조 |
    | 2 | 계획서 문장에서 기대값 추론(도시개발 잔여 `null`) | 코드 원문 |
    | 3 | `매도청구 가능` 이 **`매도청구 가능여부`** 를 집음(다른 기능의 정당 라벨) | 잔존 파일 문맥 |
    | 4 | **404 페이지** 청크를 긁어 대조군까지 0 → "하드코딩 0건"으로 읽을 뻔 | 음성대조 |
    | 5 | `propai-v` 가 **`propai-vitest`** 를 집음(로그 파일명) | 대조군 |
    | 6 | `cmd \\| head` 의 종료코드를 읽어 EXIT=0 오독(실제 1) | `PIPESTATUS` |
    | 7 | **주석의 예시값**을 상수 선언으로 착각 | 선언 직접 조회 |

    3·5·7 은 전부 **내가 만든 패턴이 내가 쓴 텍스트를 집은 것**이다. 사람의 주의로는 안 된다 —
    **도구가 구조적으로 막아야** 한다.

★설계 원칙: `positive_control` 을 **필수 키워드 인자**로 받는다. 그래서 대조군 없이
  `assert_absent` 를 호출하는 것이 **문법적으로 불가능**하다
  (`lib/source-invariant.ts` 의 `assertWiredThrough` 가 `minMatches` 를 필수로 받아
   공허진리를 막은 것과 같은 설계).

★이 모듈은 **판정하지 않는다. 판정을 가능하게만 한다.** 무엇이 위반인지는 호출자가 정한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


class ScannerDeadError(AssertionError):
    """검사기가 죽었다 — '위반 0'이 **부재의 증거가 아니다**."""


@dataclass(frozen=True)
class ScanResult:
    hits: list[str]
    positive_hits: int
    negative_hits: int


def _findall(text: str, pattern: str | re.Pattern[str]) -> list[str]:
    rx = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern)
    return [m.group(0) for m in rx.finditer(text)]


def scan(
    text: str,
    *,
    pattern: str | re.Pattern[str],
    positive_control: str | re.Pattern[str],
    negative_control: str | re.Pattern[str] = r"zzz-absent-sentinel-do-not-add",
    min_positive: int = 1,
    where: str = "",
) -> ScanResult:
    """`pattern` 을 세되, **대조군이 살아 있을 때만** 결과를 신뢰한다.

    Args:
        positive_control: **반드시 있어야 하는** 것. 0건이면 검사기가 죽은 것이다
            (경로가 틀렸거나·대상이 비었거나·정규식이 어긋났다). 필수 인자다.
        negative_control: **절대 없어야 하는** 것. >0 이면 패턴이 아무거나 집고 있다.
        min_positive: 양성대조 하한. 대상 규모를 아는 호출자가 올려 잡으면 더 강해진다.

    Raises:
        ScannerDeadError: 대조군이 무너졌을 때. **위반 0 과 구분해서** 던진다 —
            이 둘을 같은 실패로 뭉치면 "검사기가 죽었다"가 "깨끗하다"로 읽힌다.
    """
    pos = len(_findall(text, positive_control))
    if pos < min_positive:
        raise ScannerDeadError(
            f"양성대조 {pos}건 < 최소 {min_positive}건{f' ({where})' if where else ''} — "
            "**검사기가 죽었다.** 이 상태의 '위반 0'은 부재의 증거가 아니다. "
            f"경로·대상·정규식을 먼저 의심하라. control={positive_control!r}"
        )
    neg = len(_findall(text, negative_control))
    if neg:
        raise ScannerDeadError(
            f"음성대조가 {neg}건 잡혔다{f' ({where})' if where else ''} — "
            "패턴이 아무거나 집고 있다. 있어서는 안 될 것이 잡히면 '위반 0'도 못 믿는다."
        )
    return ScanResult(hits=_findall(text, pattern), positive_hits=pos, negative_hits=neg)


def assert_absent(
    text: str,
    *,
    pattern: str | re.Pattern[str],
    positive_control: str | re.Pattern[str],
    reason: str,
    negative_control: str | re.Pattern[str] = r"zzz-absent-sentinel-do-not-add",
    min_positive: int = 1,
    where: str = "",
) -> ScanResult:
    """"이 패턴은 없어야 한다"를 **대조군과 함께** 단언한다.

    `positive_control` 과 `reason` 이 **필수 키워드**다 — 대조군 없이, 또는 왜 위반인지
    적지 않고 호출할 수 없다. 실패 메시지는 다음 사람이 읽는다.
    """
    r = scan(
        text,
        pattern=pattern,
        positive_control=positive_control,
        negative_control=negative_control,
        min_positive=min_positive,
        where=where,
    )
    if r.hits:
        sample = "\n  ".join(sorted(set(r.hits))[:8])
        raise AssertionError(
            f"{reason}\n  발견 {len(r.hits)}건{f' ({where})' if where else ''} "
            f"(양성대조 {r.positive_hits}건 — 검사기는 살아 있다):\n  {sample}"
        )
    return r


def code_lines(text: str, *, comment_prefixes: tuple[str, ...] = ("#", "//")) -> str:
    """줄 단위 주석을 걷어낸 텍스트.

    ★위양성 3·5·7 이 전부 **내가 쓴 주석·문서 문자열을 내 패턴이 집은 것**이었다.
      주석은 실행되지 않으므로 "코드에 남아 있다"의 증거가 될 수 없다.
    ★한계(정직): 블록 주석·문자열 리터럴은 걸러내지 못한다. 그 수준이 필요하면
      프론트의 `lib/source-invariant.ts`(TS 파서 기반 간극 주사)처럼 파서를 써야 한다.
      여기서는 **줄 주석만** 처리한다고 명시한다.
    """
    out = []
    for ln in text.splitlines():
        s = ln.lstrip()
        if any(s.startswith(p) for p in comment_prefixes):
            continue
        out.append(ln)
    return "\n".join(out)


def read(path: Path, *, must_exist_reason: str) -> str:
    """파일을 읽되 **부재를 조용히 넘기지 않는다**.

    파일이 사라지면 그 위의 모든 스캔이 "위반 0"으로 통과한다 — 가장 조용한 실패다.
    """
    if not path.exists():
        raise ScannerDeadError(f"{path} 가 없다 — {must_exist_reason}")
    return path.read_text(encoding="utf-8")
