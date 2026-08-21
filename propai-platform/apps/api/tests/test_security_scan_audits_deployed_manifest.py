"""**감사하는 매니페스트**가 **배포되는 매니페스트**를 포함하는지 잠근다.

## 왜 (2026-08-20 실측)

`#716` 이 CVE 감사를 되살렸다. 그런데 감사 대상이 `requirements.txt` 였고,
`Dockerfile.oracle` 이 실제로 설치하는 것은 **`requirements.oracle.txt`** 였다.
즉 **감사 대상이 배포 대상이 아니었다** — 이 저장소가 반복해 데인 그 결함
(*"검증이 실제 대상을 태우지 않는다"*)을, 검증을 되살리는 PR 이 스스로 저질렀다.

실측 차이: `txt` 에만 13개(mlflow·torch·torchvision·geopandas·lxml 등)라
**약 55건이 프로덕션에 없는데 부채로 계상**되고 있었고, 반대로 `oracle` 에만 있는
`minio` 는 **감사되지 않고 있었다**(현재 취약점 0이라 실질 누락은 없었지만 사각은 사각이다).

## 이 락의 모양 — 목록형이 아니라 **파생형**

배포 매니페스트 이름을 손으로 적지 않는다. **Dockerfile 에서 뽑아** 감사 설정과 대조한다.
그래야 파일명이 바뀌거나 매니페스트가 늘어나도 **자동으로 감시망에 들어온다**
(사람이 센 목록은 그 목록이 곧 상한이 된다).
"""

from __future__ import annotations

import pathlib
import re

_REPO = pathlib.Path(__file__).resolve().parents[4]
_WORKFLOW = _REPO / ".github" / "workflows" / "security.yml"
_DOCKERFILES = ("propai-platform/Dockerfile.oracle",)


def _strip_yaml_comments(text: str) -> str:
    """주석을 걷어낸다 — 주석에 적힌 파일명이 락을 통과시키면 안 된다."""
    out = []
    for line in text.splitlines():
        stripped = line.split("#", 1)[0] if not line.lstrip().startswith("#") else ""
        out.append(stripped)
    return "\n".join(out)


def _deployed_manifests() -> set[str]:
    """Dockerfile 이 **COPY 해서 설치하는** requirements 파일 이름을 뽑는다."""
    found: set[str] = set()
    for rel in _DOCKERFILES:
        p = _REPO / rel
        assert p.exists(), f"Dockerfile 이 없다: {rel} — 이 락은 아무것도 검증하지 않는다"
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#"):
                continue
            for m in re.finditer(r'([A-Za-z0-9_./\-]*requirements[A-Za-z0-9_.\-]*\.txt)', line):
                name = pathlib.PurePosixPath(m.group(1)).name
                # 컨테이너 안 목적지(./requirements.txt)가 아니라 **원본**만 센다.
                if line.lstrip().upper().startswith("COPY") and "apps/api/" in m.group(1):
                    found.add(name)
    return found


def test_배포되는_매니페스트를_실제로_뽑아낸다_전제확인() -> None:
    """★공허 진리 방지 — 아래 락이 '위반 0'인 이유가 *뽑은 게 0개*여서는 안 된다."""
    manifests = _deployed_manifests()
    assert manifests, (
        "Dockerfile 에서 배포 매니페스트를 하나도 뽑지 못했다 — 정규식이나 경로가 틀렸다. "
        "이 상태에서 아래 락이 초록인 것은 아무 의미가 없다"
    )
    # 현재 알려진 사실과 어긋나면 구조가 바뀐 것이니 사람이 봐야 한다.
    assert "requirements.oracle.txt" in manifests, (
        f"배포 매니페스트가 예상과 다르다: {sorted(manifests)}. "
        "Dockerfile 구조가 바뀌었다면 이 락과 security.yml 을 함께 갱신하라"
    )


def test_보안스캔이_배포되는_매니페스트를_감사한다() -> None:
    """★배포되는 매니페스트가 감사 설정에 **전부** 들어 있어야 한다."""
    assert _WORKFLOW.exists(), f"워크플로가 없다: {_WORKFLOW}"
    body = _strip_yaml_comments(_WORKFLOW.read_text(encoding="utf-8"))

    빠진 = [m for m in sorted(_deployed_manifests()) if m not in body]
    assert not 빠진, (
        "배포되는데 **감사되지 않는** 매니페스트가 있다 — 감사 대상이 배포 대상이 아니다: "
        f"{빠진!r}"
    )


def test_게이트가_필수_감사대상을_요구한다() -> None:
    """★워크플로에서 `prod=` 를 지우기만 해도 초록이 되면 위 락들이 무력해진다.

    ★★이 케이스의 첫 판은 소스에 `REQUIRED_LABELS` **글자가 있는지**만 봤다.
      변이(`REQUIRED_LABELS = set()`)가 **그대로 통과했다** — 존재만 보고 **내용을
      보지 않는** 락이었다. 이 저장소가 반복해 데인 *"소스 검사는 뚫린다"* 그대로다.
      → 그래서 **게이트를 진짜 실행**한다. `prod=` 없이 부르면 **0이 아닌 종료코드**가
        나와야 하고, 정상 호출은 **0**이어야 한다(대조군).
    """
    import json
    import subprocess
    import sys
    import tempfile

    gate = _REPO / ".github" / "scripts" / "pip_audit_gate.py"
    assert gate.exists(), f"게이트 스크립트가 없다: {gate}"

    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        # MIN_DEPS 하한을 넘기는 최소 픽스처(취약점은 0건).
        fake = {"dependencies": [{"name": f"pkg{i}", "version": "1.0.0", "vulns": []} for i in range(60)]}
        audit = tmp / "audit.json"
        audit.write_text(json.dumps(fake), encoding="utf-8")
        baseline = tmp / "baseline.json"
        baseline.write_text(json.dumps({"acknowledged": []}), encoding="utf-8")

        def run(*specs: str) -> int:
            return subprocess.run(
                [sys.executable, str(gate), str(baseline), *specs],
                capture_output=True, text=True,
            ).returncode

        # ★대조군 먼저 — 정상 호출이 0이 아니면 아래 단언은 아무것도 뜻하지 않는다.
        assert run(f"prod={audit}", f"dev={audit}") == 0, (
            "정상 호출(prod+dev)이 실패했다 — 이 케이스는 게이트를 검증하지 못한다"
        )
        assert run(f"dev={audit}") != 0, (
            "**prod 를 빼도 게이트가 통과했다** — 배포되는 매니페스트를 감사하지 않아도 "
            "초록이 된다는 뜻이다. 필수 라벨 강제가 사라졌다"
        )
