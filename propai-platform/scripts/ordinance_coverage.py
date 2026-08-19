#!/usr/bin/env python3
"""조례 파서 **전국 커버리지 측정** — 특정 지자체가 아니라 전 지자체가 대상이다.

【왜 필요한가 — 2026-08-19】
파서를 고칠 때마다 "오산시가 된다/안 된다"만 알았다. **몇 곳이 되는지는 몰랐다.**
정적캐시 26곳이 답을 내는 바람에 Tier-1(법제처 실시간)이 **전면 고장**인 것도 8개월 가려졌다.
표기변형은 지자체마다 다르므로(오산시 "용도지역에서의" vs 시행령 "용도지역안에서의"),
픽스처 한 개는 그 지자체만 보증한다. **분모가 있어야 진척을 말할 수 있다.**

【분모를 하드코딩하지 않는다】
지자체 목록을 손으로 적으면 그 목록이 곧 상한이 된다. 법제처 자치법규 검색에서
`○○ 도시계획 조례` 를 **파생**해 분모를 만든다 — 새 지자체·개명이 자동 반영된다.

【판정 4종】
  ok            파서가 값을 냈고 법정범위 안
  rejected      법정초과로 S계층 가드가 기각(= 파서 오독이 잡힌 것 — 화면엔 안 나간다)
  no_value      섹션은 찾았으나 해당 용도지역 값 없음
  no_section    섹션 자체를 못 찾음(표기변형 미대응 가능성)

사용: python3 scripts/ordinance_coverage.py [--limit N] [--zone 용도지역]
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import Counter

import httpx

sys.path.insert(0, "/app")

from app.core.config import settings  # noqa: E402
from app.services.land_intelligence.ordinance_service import (  # noqa: E402
    MOLEG_ORDIN_LIST_URL,
    MOLEG_ORDIN_TEXT_URL,
    OrdinanceService,
)

H = {"User-Agent": "PropAI/1.0 (https://4t8t.net)"}
# 대표 용도지역 — 성격이 다른 것을 섞는다(녹지/주거/상업). 하나만 보면 그 하나의 표기만 검증된다.
DEFAULT_ZONES = ["자연녹지지역", "제2종일반주거지역", "일반상업지역"]


async def list_ordinances(client: httpx.AsyncClient, max_pages: int = 5) -> list[tuple[str, str]]:
    """법제처에서 `○○ 도시계획 조례` 를 파생. (id, name) 목록."""
    out: list[tuple[str, str]] = []
    for page in range(1, max_pages + 1):
        r = await client.get(
            MOLEG_ORDIN_LIST_URL,
            params={"OC": settings.MOLEG_API_KEY, "target": "ordin", "type": "XML",
                    "query": "도시계획 조례", "display": "100", "page": str(page)},
        )
        r.raise_for_status()
        names = re.findall(r"<자치법규명[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</자치법규명", r.text)
        ids = re.findall(r"<자치법규ID>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</자치법규ID>", r.text)
        if not names:
            break
        out += [(i, n) for i, n in zip(ids, names)
                if re.fullmatch(r".+\s?도시계획\s?조례", n)]
    # 중복 제거(개정 이력으로 같은 이름이 여러 번 나올 수 있다) — 이름 기준 첫 항목만.
    seen: set[str] = set()
    uniq: list[tuple[str, str]] = []
    for i, n in out:
        if n in seen:
            continue
        seen.add(n)
        uniq.append((i, n))
    return uniq


def classify(svc: OrdinanceService, xml: str, zone: str) -> str:
    res = svc._parse_bcr_far_from_text(xml, zone, "coverage")
    if res is None:
        import re as _re
        full = " ".join(_re.findall(r"CDATA\[(.*?)\]\]>", xml, _re.DOTALL))
        st = svc._extract_zone_limits_structured(full)
        return "no_section" if not st["zones"] else "no_value"
    missing = res.get("missing_sections") or []
    if any("법정상한" in m for m in missing):
        return "rejected"
    if res.get("bcr") is None and res.get("far") is None:
        return "no_value"
    return "ok"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="대상 지자체 수 상한(0=전체)")
    ap.add_argument("--zone", action="append", default=None)
    args = ap.parse_args()
    zones = args.zone or DEFAULT_ZONES

    svc = OrdinanceService()
    async with httpx.AsyncClient(timeout=30.0, headers=H) as client:
        targets = await list_ordinances(client)
        print(f"분모(법제처 파생 도시계획조례): {len(targets)}곳")
        if args.limit:
            targets = targets[: args.limit]
            print(f"※ 표본 {len(targets)}곳으로 제한 — **전수 아님**(보고 시 명시할 것)")

        tally: dict[str, Counter] = {z: Counter() for z in zones}
        failures: list[str] = []
        for idx, (oid, name) in enumerate(targets, 1):
            try:
                r = await client.get(
                    MOLEG_ORDIN_TEXT_URL,
                    params={"OC": settings.MOLEG_API_KEY, "target": "ordin",
                            "type": "XML", "ID": oid},
                )
                r.raise_for_status()
                xml = r.text
            except Exception as e:  # noqa: BLE001
                for z in zones:
                    tally[z]["fetch_error"] += 1
                failures.append(f"{name}: fetch {type(e).__name__}")
                continue
            for z in zones:
                verdict = classify(svc, xml, z)
                tally[z][verdict] += 1
                if verdict in ("no_section", "rejected"):
                    failures.append(f"{name} / {z}: {verdict}")
            if idx % 10 == 0:
                print(f"  … {idx}/{len(targets)}", flush=True)

    print("\n=== 커버리지 ===")
    for z in zones:
        c = tally[z]
        tot = sum(c.values())
        ok = c["ok"]
        print(f"[{z}] 대상 {tot} | ok {ok} ({ok / tot * 100:.1f}%) | "
              f"rejected {c['rejected']} | no_value {c['no_value']} | "
              f"no_section {c['no_section']} | fetch_error {c['fetch_error']}")
    print("\n=== 실패 표본(앞 25) ===")
    for f in failures[:25]:
        print("  -", f)
    print(f"\n총 실패 {len(failures)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
