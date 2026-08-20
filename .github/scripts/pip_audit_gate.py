#!/usr/bin/env python3
"""pip-audit 결과를 **베이스라인과 대조**해 *새로 생긴* 취약점만 실패로 만든다.

★왜 이 게이트가 필요한가 (2026-08-20 실측)
`Security Scan` 워크플로는 **최근 100건 전부 실패**했고 **성공 이력이 0건**이었다.
즉 이 저장소에서 한 번도 초록인 적이 없다. 원인은 취약점이 아니라 **스캔이 아예
돌지 못한 것**이었다 — `gdal` 이 네이티브 빌드(`gdal-config`)를 요구해 pip-audit 의
의존성 해석 단계에서 죽었다. 그것 하나 때문에 **CVE 감사가 10주+ 부재**했다.

스캔을 되살리자 **158건 / 26개 패키지**가 한꺼번에 나왔다. 그대로 `--strict` 를 두면
매 커밋이 빨갛고, 그 빨강은 다시 **경보가 아니라 배경**이 된다(이 저장소가 이미 겪은
실패 형태다). 그래서 지금 있는 것을 **베이스라인으로 인정**하고, 그 이후 **새로 들어온
것만** 막는다. 베이스라인은 줄여 나가야 할 **부채 목록**이지 면죄부가 아니다.

★공허한 초록 방지: 결과가 0건이면 **스캔이 실제로 돌았는지 의심**한다. pip-audit 이
  아무 의존성도 해석하지 못해도 "취약점 0"처럼 보이기 때문이다. 그래서 감사한
  **의존성 개수 하한**을 함께 검사한다.
"""
from __future__ import annotations

import json
import pathlib
import sys


def _key(pkg: str, vuln_id: str) -> str:
    return f"{pkg.lower()}::{vuln_id}"


def _load_findings(path: pathlib.Path) -> tuple[set[str], int, dict[str, str]]:
    """pip-audit JSON 에서 (취약점 키 집합, 감사된 의존성 수, 키→설명) 을 뽑는다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    deps = data.get("dependencies", data if isinstance(data, list) else [])
    found: set[str] = set()
    label: dict[str, str] = {}
    for dep in deps:
        name = dep.get("name", "?")
        version = dep.get("version", "?")
        for v in dep.get("vulns", []) or []:
            k = _key(name, v.get("id", "?"))
            found.add(k)
            fix = ",".join(v.get("fix_versions", []) or []) or "미상"
            label[k] = f"{name} {version} → 수정본 {fix}"
    return found, len(deps), label


def main() -> int:
    if len(sys.argv) != 3:
        print("사용법: pip_audit_gate.py <audit.json> <baseline.json>", file=sys.stderr)
        return 2

    audit_path, baseline_path = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    if not audit_path.exists():
        print(f"::error::감사 결과가 없다({audit_path}) — 스캔이 죽었다는 뜻이다")
        return 1

    found, dep_count, label = _load_findings(audit_path)

    # ★공허한 초록 방지 — 아무것도 해석 못 한 스캔은 "취약점 0"과 구분되지 않는다.
    MIN_DEPS = 40
    if dep_count < MIN_DEPS:
        print(
            f"::error::감사된 의존성이 {dep_count}개뿐이다(하한 {MIN_DEPS}). "
            "스캔이 의존성 해석에 실패했을 가능성이 높다 — 이 결과의 '취약점 0'은 신뢰할 수 없다"
        )
        return 1

    baseline: set[str] = set()
    if baseline_path.exists():
        baseline = set(json.loads(baseline_path.read_text(encoding="utf-8")).get("acknowledged", []))

    new = sorted(found - baseline)
    gone = sorted(baseline - found)

    print(f"감사된 의존성 {dep_count}개 · 취약점 {len(found)}건 · 베이스라인 {len(baseline)}건")

    if gone:
        print(f"::notice::베이스라인 {len(gone)}건이 해소됐다 — 베이스라인을 줄여라:")
        for k in gone[:20]:
            print(f"  - {k}")

    if new:
        print(f"::error::**새 취약점 {len(new)}건** — 베이스라인에 없던 것이다:")
        for k in new:
            print(f"  ✗ {k}  ({label.get(k, '')})")
        print("  대응: 해당 패키지를 올리거나, 감수 사유를 적고 베이스라인에 추가하라")
        return 1

    print("::notice::새 취약점 없음. ★베이스라인은 **부채 목록**이다 — 줄여 나가라")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
