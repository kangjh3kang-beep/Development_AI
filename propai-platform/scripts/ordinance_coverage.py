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
  no_section    섹션을 못 찾음 — **파서 결함**(표기변형 미대응 등)
  not_applicable 그 조례가 애초에 그 항목을 정하지 않음 — **정상**(광역 위임구조 등)

★no_section 과 not_applicable 을 가르는 것이 이 하네스의 핵심이다. 뭉뚱그리면
  "고칠 것"과 "고칠 게 없는 것"이 같은 통에 들어가 진척이 왜곡된다.
  실측(경기도 조례 id 2023945): **'건폐율' 단어 자체가 0회**, '자연녹지지역' 0회, '위임' 8회 —
  파서가 못 찾은 게 아니라 **조례에 없다.** 판별자: 본문에 그 단어가 아예 없으면 not_applicable.

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

from app.services.legal.moleg_drf_envelope import moleg_oc_key
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
            params={"OC": moleg_oc_key(), "target": "ordin", "type": "XML",
                    "query": "도시계획 조례", "display": "100", "page": str(page)},
        )
        r.raise_for_status()
        names = re.findall(r"<자치법규명[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</자치법규명", r.text)
        ids = re.findall(r"<자치법규ID>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</자치법규ID>", r.text)
        if not names:
            break
        # ★strict=True — `names`·`ids` 는 **같은 XML 응답에 대한 별개 findall 2회**라
        #   레코드마다 1:1 이어야 정상이다. 한 레코드에서 한쪽 필드가 빠지면 길이가 어긋난 채
        #   `zip` 이 조용히 잘라 **ID↔이름이 통째로 밀린다**(= 엉뚱한 조례 ID 를 그 이름에 붙임).
        #   그 상태의 결과는 이미 틀렸으므로 **죽는 편이 옳다**.
        out += [(i, n) for i, n in zip(ids, names, strict=True)
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
        # ★파서 결함과 '애초에 없음'을 가른다. 조례 본문에 '건폐율'·'용적률'이 **한 번도**
        #   나오지 않으면 그 조례는 그것을 정하지 않는 것이다(광역 위임구조 실측 확인).
        #   못 찾은 게 아니라 없는 것을 실패로 세면 고칠 게 없는 것이 진척을 가린다.
        # ★판별자 교정(1차 시도 실패 기록): 처음엔 `"건폐율" not in full and "용적률" not in full`
        #   로 걸었는데 경기도 조례는 건폐율 0회지만 **용적률 3회**라 AND 가 성립하지 않아
        #   n/a 가 0건이었다. 원인은 판정이 (zone, kind) 인데 조건을 조례 전체로 본 것.
        #   더 정확한 신호는 **요청 용도지역명 자체의 부재**다 — 경기도 조례에 `자연녹지지역`
        #   은 **0회**(오산시는 9회). 그 조례가 그 용도지역을 아예 규율하지 않는다는 뜻이다.
        # ★검증 완료(2026-08-19 표본 5건) — 이 판정은 오분류가 아니다.
        #   n/a 로 분류된 것들의 **XML 원문**(CDATA 추출본이 아니라)에도 용도지역명이 0회다:
        #     강원특별자치도·경기도·경상남도·경상북도(광역, 위임 5~12회) · 대전광역시 동구(자치구)
        #   → ①CDATA 추출 손실 가설 **기각**(원문에도 없다) ②광역·자치구는 용도지역별 밀도를
        #     직접 정하지 않는다(자치구는 시 본청 조례를 따른다 — ordinance_service 도 동일 처리).
        #   ★n/a 를 성공률 분모에서 빼므로 **오분류는 성공률을 부풀리는 방향**이다.
        #     그래서 이 검증을 후속 작업보다 먼저 했다(부풀려진 기준 위에 쌓지 않기 위해).
        if zone not in full:
            return "not_applicable"
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

        # ★광역자치단체(도·특별자치도)는 시·군에 위임하는 구조라 조례에 직접 수치가 없을 수
        #   있다. 기초와 같은 통에 넣으면 **파서 결함이 아닌 것이 실패로 집계**되어 진척이
        #   왜곡된다(실측: 잔여 실패 12건이 전부 광역이었다). 분모를 갈라서 센다.
        def is_gwangyeok(name: str) -> bool:
            return bool(re.search(r"(?:^|\s)(\S*(?:도|특별자치도))\s*도시계획", name)) and \
                not re.search(r"(?:시|군|구)\s*도시계획", name)

        tally: dict[str, Counter] = {z: Counter() for z in zones}
        tally_gw: dict[str, Counter] = {z: Counter() for z in zones}
        failures: list[str] = []
        for idx, (oid, name) in enumerate(targets, 1):
            try:
                r = await client.get(
                    MOLEG_ORDIN_TEXT_URL,
                    params={"OC": moleg_oc_key(), "target": "ordin",
                            "type": "XML", "ID": oid},
                )
                r.raise_for_status()
                xml = r.text
            except Exception as e:  # noqa: BLE001
                for z in zones:
                    tally[z]["fetch_error"] += 1
                failures.append(f"{name}: fetch {type(e).__name__}")
                continue
            gw = is_gwangyeok(name)
            for z in zones:
                verdict = classify(svc, xml, z)
                (tally_gw if gw else tally)[z][verdict] += 1
                # 광역의 no_section 은 위임구조일 수 있어 파서 실패로 세지 않는다(별도 집계).
                if verdict == "rejected" or (verdict == "no_section" and not gw):
                    failures.append(f"{name} / {z}: {verdict}")
            if idx % 10 == 0:
                print(f"  … {idx}/{len(targets)}", flush=True)

    def _report(title: str, t: dict[str, Counter]) -> None:
        print(f"\n=== {title} ===")
        for z in zones:
            c = t[z]
            tot = sum(c.values())
            if not tot:
                print(f"[{z}] 대상 0 — 표본에 없음")
                continue
            # ★분모에서 n/a 를 뺀다 — "그 조례가 규율하지 않음"은 **파서가 못한 게 아니다.**
            #   전수(150곳)에서 이걸 안 뺐다가 자연녹지 67.4% 로 읽어 표본 30곳(96.2%)과
            #   어긋나 보였다. 실제 파서 성공률은 95.0% 로 표본과 일치한다 —
            #   **표본이 틀린 게 아니라 내 지표가 틀렸다.**
            den = tot - c["not_applicable"]
            rate = f"{c['ok'] / den * 100:.1f}%" if den else "n/a"
            print(f"[{z}] 대상 {tot} | 파서분모 {den} | ok {c['ok']} ({rate}) | "
                  f"rejected {c['rejected']} | no_value {c['no_value']} | "
                  f"no_section {c['no_section']} | n/a {c['not_applicable']}(분모제외) | "
                  f"fetch_error {c['fetch_error']}")

    _report("커버리지 — 기초자치단체(시·군·구)", tally)
    _report("커버리지 — 광역자치단체(도) ※위임구조라 no_section 이 정상일 수 있음", tally_gw)
    print("\n=== 실패 표본(앞 25) ===")
    for f in failures[:25]:
        print("  -", f)
    print(f"\n총 실패 {len(failures)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
