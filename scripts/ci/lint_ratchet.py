#!/usr/bin/env python3
"""eslint 경고 **비성장 래칫** — 파일별 카운트를 고정한다.

왜(실측 2026-08-26 · `origin/main` a7838464):
`npx eslint . --no-cache` 전수 = 파일 1,060 · **경고 189 · 에러 0** · 경고 보유 파일 **95개**.
그런데 `ci.yml` 의 Lint 스텝은 `--max-warnings` 를 안 걸어 **경고가 몇이든 초록**이다.
그 파일 자신이 이렇게 적어 두었다 — *"경고 정리 후 0 게이트화 예정."* 그 예정이 오지 않았다.

★그 사이 무엇이 쌓였나: `@typescript-eslint/no-unused-vars` **74건**, 그중 *"정의됐으나
미사용"*(대개 **미사용 import**)이 **55건**. 이건 단순 노이즈가 아니다 —
**`import` 를 소비처로 착각하게 만드는 재료**다. 실제로 2026-08-26 에 그 함정에 걸려
`LandScheduleClient` 를 소비처로 세고 *"10페이지"* 라는 틀린 수치를 PR 에 적었다
(실제 9). **린트는 이미 보고 있었고 게이트가 없어서 쌓였다.**

★왜 전면 `--max-warnings 0` 이 아닌가: 그러면 **다른 세션의 무관한 PR 이 즉시 빨개진다.**
래칫은 *"늘지 않게"* 만 하므로, 기존 경고가 있는 파일을 건드리지 않는 PR 은 영향이 없다.
전면 게이트화는 **팀 결정 사안**으로 남긴다.

★왜 단일 카운트가 아니라 **파일별**인가(형제 `render-clock-ratchet.test.ts` 의 형태):
  · 단일 카운트는 **어디서 늘었는지 말하지 않는다**
  · 파일별이면 **줄었을 때도 알려 준다** → 래칫을 낮추라는 신호가 되어 정리를 유도한다
    (§36 "죽은 면제도 실패시켜라" 의 같은 정신 — 낡은 관용은 실패해야 걷힌다)

★eslint 를 **두 번 돌리지 않는다**: CI 의 기존 Lint 스텝이 낸 JSON 을 그대로 먹는다.

사용:  lint_ratchet.py <eslint-json> <ratchet-json> [--update]
종료:  0 통과 · 1 위반 · 3 입력 이상(측정 무효 — 통과로 세지 말 것)
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

WEB_MARKER = "/apps/web/"


def load_counts(eslint_json: Path) -> tuple[Counter, int]:
    """파일별 경고 수와 에러 총계. 경로는 저장소 상대(apps/web 기준)로 정규화한다."""
    data = json.loads(eslint_json.read_text(encoding="utf-8"))
    counts: Counter = Counter()
    errors = 0
    for rec in data:
        path = str(rec.get("filePath", ""))
        rel = path.split(WEB_MARKER, 1)[1] if WEB_MARKER in path else path
        for msg in rec.get("messages", []):
            if msg.get("severity") == 2:
                errors += 1
            else:
                counts[rel] += 1
    return counts, errors


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 3
    eslint_json, ratchet_json = Path(sys.argv[1]), Path(sys.argv[2])
    update = "--update" in sys.argv[3:]

    if not eslint_json.is_file() or eslint_json.stat().st_size == 0:
        # ★"경고 0" 과 "리포트를 못 읽음" 은 같은 0 으로 보인다 — 시끄럽게 죽는다.
        print(f"★eslint 리포트를 읽지 못했다: {eslint_json} — 측정 무효(통과 아님)")
        return 3

    counts, errors = load_counts(eslint_json)

    # ★조회기 생존: 파일이 한 건도 안 잡히면 포맷/경로가 바뀐 것이지 "깨끗한" 게 아니다.
    if not counts and errors == 0:
        raw = json.loads(eslint_json.read_text(encoding="utf-8"))
        if not raw:
            print("★eslint 리포트가 비었다 — 린트가 아무 파일도 안 봤다. 측정 무효")
            return 3

    if update:
        ratchet_json.write_text(
            json.dumps(dict(sorted(counts.items())), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"래칫 갱신: {len(counts)}파일 · 경고 {sum(counts.values())}건 → {ratchet_json}")
        return 0

    if not ratchet_json.is_file():
        print(f"★래칫 파일이 없다: {ratchet_json} — `--update` 로 먼저 만들 것")
        return 3
    ratchet: dict[str, int] = json.loads(ratchet_json.read_text(encoding="utf-8"))

    grew = [(f, ratchet.get(f, 0), n) for f, n in sorted(counts.items()) if n > ratchet.get(f, 0)]
    shrank = [(f, ratchet[f], counts.get(f, 0)) for f in sorted(ratchet) if counts.get(f, 0) < ratchet[f]]

    total_now, total_was = sum(counts.values()), sum(ratchet.values())
    print(f"eslint 경고 {total_now}건 / 래칫 {total_was}건 · 에러 {errors}건")

    if grew:
        print("\n★경고가 늘었다 — 이 PR 이 새로 만든 것이다:")
        for f, was, now in grew:
            tag = "  (신규 파일)" if was == 0 else ""
            print(f"  {was} → {now}   {f}{tag}")
        print(
            "\n고치거나, 정말 불가피하면 lint-ratchet.json 을 **사유와 함께** 올려라.\n"
            "  갱신: python3 scripts/ci/lint_ratchet.py <리포트> "
            "propai-platform/apps/web/lint-ratchet.json --update"
        )
        return 1

    if shrank:
        # ★줄어든 것도 알려 준다 — 낡은 래칫은 그만큼의 재발 여지를 남긴다(§36 죽은 면제).
        #   단 **실패시키지는 않는다**: 남의 PR 이 곁가지로 하나 고쳤다고 빨개지면 정리를 벌주는 꼴이다.
        print("\n래칫을 낮출 수 있다(권장 · 실패 아님):")
        for f, was, now in shrank[:12]:
            print(f"  {was} → {now}   {f}")
        if len(shrank) > 12:
            print(f"  … 외 {len(shrank) - 12}개")

    print("\n통과 — 경고가 늘지 않았다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
