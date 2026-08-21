#!/usr/bin/env python3
"""pip-audit 결과를 **베이스라인과 대조**해 *새로 생긴* 취약점만 실패로 만든다.

## 왜 이 게이트가 필요한가 (2026-08-20 실측)

`Security Scan` 은 **최근 100회 전부 실패 · 성공 이력 0건**이었다. 이 저장소에서
한 번도 초록인 적이 없다. 원인은 취약점이 아니라 **스캔이 아예 돌지 못한 것**이었다 —
`gdal` 이 네이티브 빌드(`gdal-config`)를 요구해 pip-audit 의 의존성 해석 단계에서
죽었다. 그것 하나로 **CVE 감사가 10주+ 부재**했다.

되살리자 **163건 / 26개 패키지**가 나왔다. 그대로 `--strict` 를 두면 매 커밋이 빨갛고,
그 빨강은 다시 **경보가 아니라 배경**이 된다(이 저장소가 이미 겪은 실패 형태다).
그래서 지금 있는 것을 **베이스라인으로 인정**하고 그 이후 **새로 들어온 것만** 막는다.
베이스라인은 줄여 나가야 할 **부채 목록**이지 면죄부가 아니다.

## ★매니페스트가 하나가 아니다 (2026-08-20 정정)

첫 판은 `requirements.txt` 만 감사했다. 그런데 **`Dockerfile.oracle` 이 설치하는 것은
`requirements.oracle.txt`** 다. 즉 **감사 대상이 배포 대상이 아니었다.**

실측한 차이:
  · `txt` 에만 있음 13개 — `mlflow`·`torch`·`torchvision`·`geopandas`·`lxml` 등
    → 약 **60건이 프로덕션에 없는데 부채로 계상**되고 있었다
  · `oracle` 에만 있음 1개 — **`minio`** → **배포되는데 감사되지 않고 있었다**

그래서 이 게이트는 **여러 매니페스트를 함께** 받는다. 판정은 **합집합**으로 하되
(같은 취약점이면 어느 쪽이든 같은 부채다), **어느 매니페스트에서 나왔는지**를 찍어
프로덕션 우선순위가 보이게 한다.

## ★공허한 초록 방지

pip-audit 이 아무 의존성도 해석하지 못해도 결과는 **"취약점 0"처럼 보인다** —
지금까지 죽어 있던 그 스캔과 구분되지 않는다. 그래서 감사한 **의존성 개수의 하한**을
매니페스트마다 함께 검사한다.

사용법:
    pip_audit_gate.py <baseline.json> <라벨>=<audit.json> [<라벨>=<audit.json> ...]
"""
from __future__ import annotations

import json
import pathlib
import sys

# 매니페스트 하나가 이보다 적은 의존성을 해석했다면 스캔이 죽은 것으로 본다.
MIN_DEPS = 40

# ★반드시 감사돼야 하는 라벨. **배포되는 매니페스트**가 빠지면 이 게이트는 의미가 없다.
#   변이로 확인했다: 이 검사가 없으면 `prod=` 인자를 지우기만 해도 **초록이 된다**
#   — 즉 "감사 대상이 배포 대상이 아니다"라는 결함이 **조용히 되돌아온다**.
REQUIRED_LABELS = {"prod"}


def _key(pkg: str, vuln_id: str) -> str:
    return f"{pkg.lower()}::{vuln_id}"


def _load(path: pathlib.Path) -> tuple[set[str], int, dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    deps = data.get("dependencies", data if isinstance(data, list) else [])
    found: set[str] = set()
    label: dict[str, str] = {}
    for dep in deps:
        name, version = dep.get("name", "?"), dep.get("version", "?")
        for v in dep.get("vulns", []) or []:
            k = _key(name, v.get("id", "?"))
            found.add(k)
            fix = ",".join(v.get("fix_versions", []) or []) or "미상"
            label[k] = f"{name} {version} → 수정본 {fix}"
    return found, len(deps), label


def main() -> int:
    if len(sys.argv) < 3:
        print("사용법: pip_audit_gate.py <baseline.json> <라벨>=<audit.json> ...", file=sys.stderr)
        return 2

    baseline_path = pathlib.Path(sys.argv[1])
    specs = sys.argv[2:]

    all_found: set[str] = set()
    origin: dict[str, list[str]] = {}
    labels: dict[str, str] = {}

    for spec in specs:
        if "=" not in spec:
            print(f"::error::인자 형식이 틀렸다: {spec!r} (라벨=경로 여야 한다)")
            return 2
        name, _, raw = spec.partition("=")
        path = pathlib.Path(raw)
        if not path.exists():
            print(f"::error::[{name}] 감사 결과가 없다({path}) — 그 스캔이 죽었다는 뜻이다")
            return 1

        found, dep_count, label = _load(path)
        if dep_count < MIN_DEPS:
            print(
                f"::error::[{name}] 감사된 의존성이 {dep_count}개뿐이다(하한 {MIN_DEPS}). "
                "스캔이 의존성 해석에 실패했을 가능성이 높다 — "
                "이 결과의 '취약점 0'은 신뢰할 수 없다"
            )
            return 1

        print(f"[{name}] 의존성 {dep_count}개 · 취약점 {len(found)}건")
        all_found |= found
        labels.update(label)
        for k in found:
            origin.setdefault(k, []).append(name)

    # ★필수 라벨이 빠졌으면 판정 자체를 거부한다(위 REQUIRED_LABELS 주석 참조).
    seen = {s.partition("=")[0] for s in specs}
    missing = REQUIRED_LABELS - seen
    if missing:
        print(
            f"::error::필수 감사 대상이 빠졌다: {sorted(missing)}. "
            f"받은 것: {sorted(seen)}. **배포되는 매니페스트**를 감사하지 않으면 "
            "이 게이트는 아무것도 보증하지 않는다"
        )
        return 1

    baseline: set[str] = set()
    if baseline_path.exists():
        baseline = set(json.loads(baseline_path.read_text(encoding="utf-8")).get("acknowledged", []))

    new = sorted(all_found - baseline)
    gone = sorted(baseline - all_found)

    print(f"합계 취약점 {len(all_found)}건 · 베이스라인 {len(baseline)}건")

    if gone:
        print(f"::notice::베이스라인 {len(gone)}건이 더 이상 나오지 않는다 — 베이스라인을 줄여라:")
        for k in gone[:20]:
            print(f"  - {k}")

    if new:
        print(f"::error::**새 취약점 {len(new)}건** — 베이스라인에 없던 것이다:")
        for k in new:
            where = ",".join(origin.get(k, []))
            print(f"  ✗ [{where}] {k}  ({labels.get(k, '')})")
        print("  대응: 해당 패키지를 올리거나, 감수 사유를 적고 베이스라인에 추가하라")
        return 1

    print("::notice::새 취약점 없음. ★베이스라인은 **부채 목록**이다 — 줄여 나가라")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
