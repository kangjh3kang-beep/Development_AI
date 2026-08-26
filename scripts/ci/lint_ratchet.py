#!/usr/bin/env python3
"""eslint 경고 **비성장 래칫** — 파일별 카운트를 고정한다.

왜(실측 2026-08-26 · `origin/main` a7838464):
`npx eslint . --no-cache` 전수 = 파일 1,060 · **경고 189 · 에러 0** · 경고 보유 파일 **95개**.
그런데 `ci.yml` 의 Lint 스텝은 `--max-warnings` 를 안 걸어 **경고가 몇이든 초록**이다.
그 파일 자신이 이렇게 적어 두었다 — *"경고 정리 후 0 게이트화 예정."* 그 예정이 오지 않았다.

★그 사이 무엇이 쌓였나: `@typescript-eslint/no-unused-vars` **74건**, 그중 *"정의됐으나
미사용"*(대개 **미사용 import**)이 **55건**. 이건 단순 노이즈가 아니다 —
**`import` 를 소비처로 착각하게 만드는 재료**다. 실제로 2026-08-26 에 그 함정에 걸려
`LandScheduleClient` 를 소비처로 세고 *"10페이지"* 라는 틀린 수치를 PR 에 적었다(실제 9).
**린트는 이미 보고 있었고 게이트가 없어서 쌓였다.**

★왜 전면 `--max-warnings 0` 이 아닌가: 그러면 **다른 세션의 무관한 PR 이 즉시 빨개진다.**
래칫은 *"늘지 않게"* 만 하므로, 기존 경고가 있는 파일을 건드리지 않는 PR 은 영향이 없다.
전면 게이트화는 **팀 결정 사안**으로 남긴다.

★왜 단일 카운트가 아니라 **파일별**인가(형제 `render-clock-ratchet.test.ts` 의 형태):
  · 단일 카운트는 **어디서 늘었는지 말하지 않는다**
  · 파일별이면 **줄었을 때도 알려 준다** → 래칫을 낮추라는 신호가 되어 정리를 유도한다

★eslint 를 **두 번 돌리지 않는다**: CI 의 기존 Lint 스텝이 낸 JSON 을 그대로 먹는다.

──────────────────────────────────────────────────────────────────────────────
★독립 리뷰가 초판에서 찾아낸 것(2026-08-26 · 전부 실측 재현으로 확인하고 고쳤다):

 F1 **공허 진리 가드가 `[]` 하나만 막았다.** 깨끗한 레코드 **1개**만 든 리포트에 exit 0.
    린트가 1,060개 중 1개만 봐도 초록이었다. 현실적 트리거는 `[]` 가 아니라
    `globalIgnores` 오설정·config 범프로 **모집단이 줄어드는 것**인데 그게 전부 통과했다.
    → 래칫에 **린트된 파일 수 하한**(`_meta.lintedFileFloor`)을 기록하고 그 아래면 exit 3.
    (CLAUDE.md §A-2 — *"개수 하한·대상 존재를 먼저 단언한다"*.)
 F6 **문서화한 exit 계약이 실제와 어긋났다.** 손상 JSON·비-dict 래칫·문자열 값이
    exit 3 이 아니라 **exit 1(=위반)** 로 나갔다. *"측정 무효"가 "경고가 늘었다"로 읽힌다.*
 F5 **순수 rename 이 위양성으로 빨개지고 원인을 단정했다.** 경고 8건 파일을 이름만 바꿔도
    *"이 PR 이 새로 만든 것이다"* 라고 말했다. → 총량 상쇄면 **이동 가능성**을 먼저 말한다.
 F3 **고수위 헤드룸이 조용히 재소비된다.** 남이 9건 고쳐도 래칫은 안 내려가고,
    다음 PR 이 그만큼을 무료로 쓴다. → 실패시키진 않되 **부채 총량을 매번 출력**한다.
★이 결함들이 나온 근본은 **테스트가 없었다는 것**이다(§A-1 *"분기를 만들면 테스트는 같은
  커밋에"*). 그래서 `tests/test_lint_ratchet.py` 를 같은 커밋에 넣었다.
──────────────────────────────────────────────────────────────────────────────

사용:  lint_ratchet.py <eslint-json> <ratchet-json> [--update]
종료:  0 통과 · 1 위반 · 3 입력 이상(측정 무효 — **통과로 세지 말 것**)
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

WEB_MARKER = "/apps/web/"
META_KEY = "_meta"
#: 모집단이 이 비율 아래로 떨어지면 "린트가 대상을 잃었다"로 본다(설정 사고·ignore 오설정).
#: 1.0 이면 파일 하나만 지워도 빨개져 위양성이 된다 — 0.9 는 그 사이의 실용값이다.
FLOOR_RATIO = 0.9


class InputError(Exception):
    """입력이 이상하다 — 통과도 위반도 아니다(exit 3)."""


def _read_json(path: Path, what: str):
    if not path.is_file() or path.stat().st_size == 0:
        raise InputError(f"{what} 를 읽지 못했다: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        # ★F6 — 손상 입력이 예외로 터지면 exit 1 이 되어 "위반"으로 읽힌다.
        raise InputError(f"{what} 파싱 실패: {path} — {type(e).__name__}: {e}") from e


def load_counts(data) -> tuple[Counter, int, int]:
    """(파일별 경고 수, 에러 총계, **린트된 파일 수**). 경로는 apps/web 상대로 정규화."""
    if not isinstance(data, list):
        raise InputError(f"eslint 리포트가 리스트가 아니다: {type(data).__name__}")
    counts: Counter = Counter()
    errors = 0
    for rec in data:
        if not isinstance(rec, dict):
            raise InputError("eslint 리포트 레코드가 dict 가 아니다")
        path = str(rec.get("filePath", ""))
        rel = path.split(WEB_MARKER, 1)[1] if WEB_MARKER in path else path
        for msg in rec.get("messages", []) or []:
            if msg.get("severity") == 2:
                errors += 1
            else:
                counts[rel] += 1
    return counts, errors, len(data)


def load_ratchet(data) -> tuple[dict[str, int], int]:
    """(파일별 상한, 린트 파일 수 하한). `_meta` 는 비교 대상에서 제외한다."""
    if not isinstance(data, dict):
        raise InputError(f"래칫이 dict 가 아니다: {type(data).__name__}")
    meta = data.get(META_KEY) or {}
    if not isinstance(meta, dict):
        raise InputError("래칫의 _meta 가 dict 가 아니다")
    floor = meta.get("lintedFileFloor", 0)
    if not isinstance(floor, int):
        raise InputError("래칫의 _meta.lintedFileFloor 가 정수가 아니다")
    out: dict[str, int] = {}
    for k, v in data.items():
        if k == META_KEY:
            continue
        if not isinstance(v, int):
            raise InputError(f"래칫 값이 정수가 아니다: {k} = {v!r}")
        out[k] = v
    return out, floor


def run(eslint_json: Path, ratchet_json: Path, update: bool) -> int:
    counts, errors, linted = load_counts(_read_json(eslint_json, "eslint 리포트"))

    if update:
        payload: dict = {
            META_KEY: {
                "lintedFileFloor": int(linted * FLOOR_RATIO),
                "lintedFilesAtCapture": linted,
                "note": (
                    "린트가 대상을 잃으면(ignore 오설정·config 범프) 경고가 0 이 되어 "
                    "'깨끗함'처럼 보인다. 그 0 을 통과로 세지 않기 위한 하한이다."
                ),
            }
        }
        payload.update(sorted(counts.items()))
        ratchet_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"래칫 갱신: {len(counts)}파일 · 경고 {sum(counts.values())}건 · "
              f"린트 파일 {linted}(하한 {payload[META_KEY]['lintedFileFloor']}) → {ratchet_json}")
        return 0

    ratchet, floor = load_ratchet(_read_json(ratchet_json, "래칫"))

    # ★F1 — 공허 진리 가드. "경고 0" 과 "린트가 대상을 잃음" 은 같은 0 으로 보인다.
    if linted < floor:
        print(
            f"★린트가 본 파일이 {linted}개다(하한 {floor}). 대상을 잃었을 가능성이 크다 —\n"
            "  ignore 설정·config 범프·경로 변경을 의심하라. **측정 무효(통과 아님).**"
        )
        return 3

    grew = [(f, ratchet.get(f, 0), n) for f, n in sorted(counts.items()) if n > ratchet.get(f, 0)]
    shrank = [(f, ratchet[f], counts.get(f, 0)) for f in sorted(ratchet) if counts.get(f, 0) < ratchet[f]]

    total_now, total_was = sum(counts.values()), sum(ratchet.values())
    debt = sum(was - now for _, was, now in shrank)  # ★F3 — 조용히 재소비되는 헤드룸
    print(f"eslint 경고 {total_now}건 / 래칫 {total_was}건 · 에러 {errors}건 · 린트 파일 {linted}")

    if grew:
        added = sum(now - was for _, was, now in grew)
        # ★F5 — 총량이 상쇄되면 rename/이동일 수 있다. 원인을 단정하지 않는다.
        moved = debt == added and debt > 0
        head = ("★파일별 경고가 늘었다 — **총량은 그대로**라 이동/이름변경일 수 있다:"
                if moved else "★경고가 늘었다 — 이 PR 이 새로 만든 것이다:")
        print(f"\n{head}")
        for f, was, now in grew:
            print(f"  {was} → {now}   {f}{'  (신규 파일)' if was == 0 else ''}")
        if moved:
            print("  줄어든 쪽:")
            for f, was, now in shrank[:6]:
                print(f"  {was} → {now}   {f}")
            print("\n이동이 맞다면 `--update` 로 래칫을 다시 뜨면 된다(총량이 늘지 않았으므로).")
        else:
            print(
                "\n고치거나, 정말 불가피하면 lint-ratchet.json 을 **사유와 함께** 올려라.\n"
                "  갱신: python3 scripts/ci/lint_ratchet.py <리포트> "
                "propai-platform/apps/web/lint-ratchet.json --update"
            )
        return 1

    if shrank:
        # ★F3 — 실패시키지 않는다(곁가지로 하나 고친 PR 을 벌주면 정리를 벌주는 꼴이다).
        #   대신 **부채 총량**을 매번 말한다. 안 그러면 남이 청소한 만큼이 다음 사람의 무료 예산이 된다.
        print(f"\n★래칫 헤드룸 {debt}건 — 이만큼은 지금 **아무 검사 없이 다시 채워질 수 있다**.")
        print("  낮출 수 있는 곳(권장 · 실패 아님):")
        for f, was, now in shrank[:12]:
            print(f"  {was} → {now}   {f}")
        if len(shrank) > 12:
            print(f"  … 외 {len(shrank) - 12}개")

    print("\n통과 — 경고가 늘지 않았다.")
    return 0


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 3
    try:
        return run(Path(sys.argv[1]), Path(sys.argv[2]), "--update" in sys.argv[3:])
    except InputError as e:
        print(f"★{e} — 측정 무효(통과 아님)")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
