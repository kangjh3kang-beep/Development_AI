"""★배포키 위생 — **키가 화면·저장소로 새지 않는가.**

개인키가 터미널에 한 번이라도 찍히면 **셸 히스토리·스크롤백·세션 기록**에 남는다.
AI 세션이나 CI 로그를 거치면 더 그렇다. ***찍힌 키는 그 순간 오염된 것으로 취급한다.***
그래서 생성 스크립트는 키를 **`.env` 로 바로 흘려보내고** 출력은 **주소만** 한다.

이 파일이 잠그는 것:
  ① 생성 스크립트가 개인키를 **stdout 으로 내보내지 않는다**
  ② `.env` 가 **git 무시**된다 · `.env.example` 에 **진짜 키가 없다**
  ③ 배포 스크립트가 **DrawRegistry 를 다룬다**(하드코딩된 이름이 남아 있지 않다)
  ④ 저장소 어디에도 **개인키 모양의 문자열**이 커밋돼 있지 않다
"""

from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

_ROOT = next(p for p in pathlib.Path(__file__).resolve().parents
             if (p / "contracts" / "src").is_dir())
_CONTRACTS = _ROOT / "contracts"
_KEYGEN = _CONTRACTS / "scripts" / "new-deployer-key.sh"
_DEPLOY = _CONTRACTS / "scripts" / "deploy.ts"

#: 개인키 모양 — `0x` + 64 hex. ★대조군으로 이 정규식이 **진짜 키를 잡는지** 먼저 확인한다.
_PRIV = re.compile(r"0x[0-9a-fA-F]{64}")


def test_the_scanner_itself_is_alive():
    """★대조군 먼저 — 이 정규식이 개인키 모양을 실제로 잡는가."""
    assert _PRIV.search("DEPLOYER_PRIVATE_KEY=0x" + "ab" * 32), "검사기 사망"
    assert not _PRIV.search("0x" + "ab" * 20), "주소(20바이트)를 키로 오인한다"


def test_keygen_script_never_prints_a_private_key():
    """★스크립트가 개인키를 **stdout 에 쓰지 않는다** — 소스에서 확인."""
    assert _KEYGEN.exists(), f"키 생성 스크립트가 없다: {_KEYGEN}"
    src = _KEYGEN.read_text(encoding="utf-8")
    assert "createRandom" in src, "대조군 실패 — 스크립트를 못 읽었다"
    # ★`privateKey` 가 나오는 줄은 **파일 쓰기**뿐이어야 한다(stdout 아님)
    for ln in src.splitlines():
        if "privateKey" in ln:
            assert "appendFileSync" in ln or "//" in ln.strip()[:2], (
                f"개인키가 파일 쓰기 밖에서 쓰인다: {ln.strip()}"
            )
    assert "process.stdout.write(w.address)" in src, "주소만 내보내는 경로가 사라졌다"


def test_keygen_run_emits_an_address_and_no_key(tmp_path):
    """★★**실제로 돌려서** 확인한다 — 소스 검사는 다른 경로로 새는 것을 못 본다."""
    if not (_CONTRACTS / "node_modules" / ".bin").exists():
        pytest.skip("contracts/node_modules 부재 — ★이 실행에서 키 위생이 검증되지 않았다")
    work = tmp_path / "w"
    (work / "scripts").mkdir(parents=True)
    (work / "scripts" / "new-deployer-key.sh").write_text(
        _KEYGEN.read_text(encoding="utf-8"), encoding="utf-8")
    (work / "node_modules").symlink_to(_CONTRACTS / "node_modules")
    out = subprocess.run(["bash", "scripts/new-deployer-key.sh"], cwd=work,
                         capture_output=True, text=True, check=False)
    combined = out.stdout + out.stderr
    assert out.returncode == 0, combined
    assert _PRIV.search(combined) is None, f"★개인키가 출력에 실렸다:\n{combined}"
    assert re.search(r"주소: 0x[0-9a-fA-F]{40}", combined), combined
    env = work / ".env"
    assert env.exists() and _PRIV.search(env.read_text(encoding="utf-8")), (
        "키가 .env 에 안 들어갔다 — 어디로 갔는지 모른다"
    )
    assert oct(env.stat().st_mode)[-3:] == "600", "`.env` 권한이 600 이 아니다"


def test_env_is_ignored_and_example_has_no_real_key():
    """`.env` 는 커밋되지 않고, `.env.example` 에는 **진짜 키가 없다**."""
    ignored = subprocess.run(["git", "check-ignore", "-q", "contracts/.env"],
                             cwd=_ROOT, check=False)
    assert ignored.returncode == 0, "`.env` 가 git 에 추적될 수 있다"
    ex = _CONTRACTS / ".env.example"
    assert ex.exists(), ".env.example 이 없다 — 운영자가 무엇을 채울지 모른다"
    body = ex.read_text(encoding="utf-8")
    assert "POLYGON_AMOY_RPC_URL" in body, "대조군 실패 — 예시 파일을 못 읽었다"
    assert _PRIV.search(body) is None, "예시 파일에 개인키 모양이 있다"


def test_deploy_script_handles_draw_registry_without_hardcoding():
    """★배포 스크립트가 `DrawRegistry` 를 다루고, **보고가 거짓이 아니다**.

    종전엔 마지막 출력이 `PropAIEscrow.json` 을 **하드코딩**해서 DrawRegistry 를 배포하고도
    다른 파일명을 찍었다 — ***배포 보고가 틀리면 다음 사람이 없는 파일을 찾으러 간다.***
    """
    src = _DEPLOY.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith(("//", "*", "/*")))
    assert "DEPLOY_CONTRACT" in code, "컨트랙트 이름을 바꿀 수 없다"
    assert "DrawRegistry" in code, "DrawRegistry 생성자 인자 분기가 없다"
    assert '"PropAIEscrow.json"' not in code, "산출물 경로에 하드코딩이 남아 있다"
    assert code.count('"PropAIEscrow"') <= 1, (
        "PropAIEscrow 가 기본값 말고 다른 곳에도 하드코딩돼 있다"
    )


def test_no_private_key_is_committed_anywhere_in_contracts():
    """★저장소에 **개인키가** 커밋돼 있지 않다.

    ★축을 정확히 잡는다: 「`0x`+64hex」만 보면 **트랜잭션 해시·블록 해시·바이트코드**가 전부
      걸린다(실측: `deployments/amoy/PropAIEscrow.json` 의 `deploymentTransactionHash`).
      ***락을 느슨하게 하는 대신 축을 고친다*** — 찾는 것은 「키 이름에 붙은 64자 hex」다.
    """
    pat = r"(PRIVATE_KEY|privateKey|SECRET_KEY|MNEMONIC)[\"' :=]+0x?[0-9a-fA-F]{64}"
    out = subprocess.run(["git", "grep", "-IlE", pat, "--", "contracts/"],
                         cwd=_ROOT, capture_output=True, text=True, check=False)
    hits = [f for f in out.stdout.split() if f]
    assert hits == [], f"★개인키가 커밋돼 있다: {hits}"

    # ★공허 방지 — 이 조회가 **진짜 키를 잡는지** 대조군으로 증명한다(조회기 생존).
    probe = subprocess.run(
        ["grep", "-IlE", pat, "-"], input='DEPLOYER_PRIVATE_KEY=0x' + 'ab' * 32,
        capture_output=True, text=True, check=False)
    assert probe.returncode == 0, (
        "★검사기 사망 — 이 정규식은 진짜 키도 못 잡는다(그러면 위 「0건」이 무의미하다)"
    )
