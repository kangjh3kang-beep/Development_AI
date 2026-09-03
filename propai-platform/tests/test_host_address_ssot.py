"""호스트 주소 SSOT — **실행되는 매체**의 주소 리터럴을 잠근다.

## 왜 (실측 — 같은 형태가 최소 3회)

| 언제 | 무엇을 쟀나 | 결론 |
|---|---|---|
| 2026-08-26 | 저장소 0건인 주소로 tcp 22 timeout ×3 | **"배포 정지"** (정본은 저장소 52회) |
| 2026-09-03 | 저장소 0건인 두 주소 | **"배포 채널 전면 두절"** |
| 2026-09-03 | 저장소 0건인 또 다른 주소 | 위 오보를 **부분 확증** |

세 번 다 **호스트는 멀쩡했다.** 볼트에 *"주소는 저장소에서 파생"* 이 **산문으로** 있었고,
산문이라서 세 번 재발했다.
★틀린 주소는 `refused` 가 아니라 **timeout** 을 준다 — timeout 은 「방화벽·장애」로 읽혀
**그럴듯한 원인 가설**을 낳는다. 값이 이상한 게 아니라 **형태가 맞아서** 안 걸린다.

## ★빈도(다수결)로는 부족하다 — 이 락이 존재하는 이유

`git grep` 빈도로 정본을 정하면 3위가 `134.185.104.167`(**10회**)인데,
2026-09-04 실측으로 그 호스트는 **죽어 있다**(tcp 22 막힘 · 대조군 `168:22` 열림).
**다수결은 죽은 주소를 정본으로 받아들인다.** 그래서 상태를 **선언**한다.

## 범위 — 왜 `.md` 를 뺐나

문서에 남은 옛 주소는 **그때 무엇을 쟀는지의 기록(증거)** 이다. 기록을 위반으로 신고하면
**정상적인 사고 기록을 막는 위양성**이 된다. 이 락은 **실행되는 매체**만 본다.
즉석 Bash 명령은 다른 매체이고 `hooks/guard-unknown-host-literal.sh` 가 덮는다 —
★**두 매체는 서로를 대체하지 못한다.** 그 훅은 다수결을 **저장소 파일에서** 뽑으므로,
누군가 실행 매체에 오주소를 커밋하면 **그 훅이 그 순간부터 오주소를 정본으로 신뢰한다.**
이 락이 정확히 그 구멍을 막는다.
"""

from __future__ import annotations

import ipaddress
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# ── SSOT ───────────────────────────────────────────────────────────────────
# ★값만 적지 않는다 — **재측정 명령**을 함께 적는다. 값만 적으면 다음 사람이 재검증하지 않는다.
LIVE_HOSTS: dict[str, str] = {
    "168.110.125.89": "ssh -i ~/.oci.key ubuntu@168.110.125.89 hostname  # -> 4t8tpropai-backend-a1",
    "158.179.174.207": "ssh -i ~/.oci.key ubuntu@158.179.174.207 hostname  # -> 4t8t",
}
RETIRED_HOSTS: dict[str, str] = {
    # ★죽었다고 **선언**한다(삭제가 아니라). 되살아나면 LIVE 로 옮기면 된다.
    "134.185.104.167": (
        "2026-09-04 실측: tcp 22 막힘(대조군 168.110.125.89:22 열림). "
        "실행 매체에 남으면 「호스트 다운」 오진의 씨앗이 된다."
    ),
}

# ★배포·접속을 실제로 수행하는 매체만 본다.
#
#   `.ts`/`.tsx` 는 뺐다 — 실측 결과 그 매체의 「IP」는 **전부 SVG 좌표 위양성**이었다
#   (`m16.71 13.88.7.71-2.82` 의 `13.88.7.71`). 프론트는 호스트를 도메인으로 부르고
#   IP 리터럴로 접속하는 곳이 **0건**이다. 위양성 100% · 진양성 0% 인 매체는 넣지 않는다.
#   ★가드가 정상 코드를 막으면 그것도 결함이다.
EXEC_SUFFIXES = (".sh", ".py", ".yml", ".yaml", ".ps1")

# ★테스트 픽스처의 가짜 IP(`1.2.3.4` · `9.9.9.9` …)는 **정당하다** — 접속하지 않는다.
#   실측: 위반 후보 27건 중 **25건이 테스트 픽스처**였다. 넣으면 가드가 곧 꺼진다.
_TEST_MARKERS = ("/tests/", "/test/", "__tests__", ".test.", ".spec.", "conftest.py")

_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# RFC 5737 문서용 · RFC 6598 CGNAT — 픽스처에 정당하게 쓰인다.
_DOC_NETS = tuple(
    ipaddress.IPv4Network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
)
_CGNAT = ipaddress.IPv4Network("100.64.0.0/10")


def is_public_host_literal(addr: str) -> bool:
    """예약·사설·문서용 대역은 위반이 아니다.

    ★이 함수가 「전부 차단」을 막는다 — 없으면 loopback 도 위반이 된다.
    """
    try:
        ip = ipaddress.IPv4Address(addr)
    except ValueError:
        return False   # 오탐 문자열(버전 번호 등)
    if (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
        return False
    return not (any(ip in n for n in _DOC_NETS) or ip in _CGNAT)


def tracked_exec_files() -> list[Path]:
    """★파생형 수집 — 손으로 적은 목록은 곧 상한이 된다.

    `git ls-files` 전수를 받아 확장자로만 거른다. 새 스크립트가 자동으로 감시망에 들어온다.
    """
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout
    return [
        REPO / p for p in out.split("\0")
        if p and p.endswith(EXEC_SUFFIXES)
        and not any(m in f"/{p}" for m in _TEST_MARKERS)
    ]


def scan(sources: list[tuple[str, str]]) -> dict[str, list[str]]:
    """(이름, 본문) 목록에서 공개 IP 리터럴을 찾는다 — **순수 함수**.

    ★저장소와 분리해 둔다. 저장소 상태만 단언하면 위반을 고친 순간
    「위반 0」이 **공허한 참**이 되어 탐지기를 통째로 지워도 초록이다
    (적대 변이로 실증: `RETIRED 검사 제거`·`위반 판정 무력화` 둘 다 생존했다).
    """
    found: dict[str, list[str]] = {}
    for name, text in sources:
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in _IPV4.findall(line):
                if is_public_host_literal(m):
                    found.setdefault(m, []).append(f"{name}:{lineno}")
    return found


def _repo_sources() -> list[tuple[str, str]]:
    out = []
    for f in tracked_exec_files():
        try:
            out.append((str(f.relative_to(REPO)), f.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return out


def public_literals() -> dict[str, list[str]]:
    """{주소: [파일:줄, ...]} — 실행 매체의 공개 IP 리터럴 전수."""
    return scan(_repo_sources())


def classify(addr: str) -> str | None:
    """위반의 **종류**를 돌려준다(위반이 아니면 `None`).

    ★`retired` 와 `unknown` 을 가르는 이유: 운영자에게 **다른 행동**을 요구한다.
      · `retired` → *"그 호스트는 죽었다. 정본으로 바꿔라"* (근거가 SSOT 에 적혀 있다)
      · `unknown` → *"이 주소가 어디서 왔는지 모른다. 오타이거나 신규 호스트다"*
    둘을 한 칸에 뭉치면 **행동이 다른 것이 같은 메시지**를 받는다.
    ★그리고 이 구분이 없으면 `RETIRED` 분기는 `unknown` 폴백과 **같은 답**을 내서
      전용 락이 있어도 무잠금이 된다(적대 변이로 실증했다).
    """
    if addr in LIVE_HOSTS:
        return None
    return "retired" if addr in RETIRED_HOSTS else "unknown"


def violations_in(found: dict[str, list[str]]) -> dict[str, list[str]]:
    """SSOT(LIVE) 밖의 공개 주소 = 위반. RETIRED 도 실행 매체에서는 위반이다."""
    return {addr: locs for addr, locs in found.items() if classify(addr) is not None}


def violations() -> dict[str, list[str]]:
    return violations_in(public_literals())

# ── 락 ─────────────────────────────────────────────────────────────────────

class Test수집기가살아있다:
    """★「위반 0」이 「대상 0」이면 무의미하다 — 단언 **앞에** 생존을 증명한다."""

    def test_실행매체를_충분히_훑는다(self):
        files = tracked_exec_files()
        # 2026-09-04 실측 하한(당시 수천 개). 새 파일이 늘어도 안 깨지고,
        # 수집이 통째로 죽으면(cwd 오류·git 실패) 여기서 잡힌다.
        assert len(files) >= 100, f"실행 매체 수집이 죽었다: {len(files)}건"

    def test_정본_주소를_실제로_찾아낸다(self):
        """★양성 대조군 — 스캐너가 아무것도 못 찾는데 「위반 0」이면 그것은 사망이다."""
        found = public_literals()
        assert set(found) & set(LIVE_HOSTS), (
            f"정본 주소를 하나도 못 찾았다 = 스캐너 사망. 찾은 것: {sorted(found)}"
        )


class Test정본은위반이아니다:
    """★음성 대조군 — 없으면 「전부 차단」이 만점이 된다."""

    def test_정본_두_호스트는_통과한다(self):
        for addr in LIVE_HOSTS:
            assert is_public_host_literal(addr), f"{addr} 를 공개 주소로 못 읽었다"
        # 위반 판정에서 제외되는지까지 본다(판정 함수가 아니라 **계약**을 태운다).
        assert not violations(), f"정본만 있는 상태인데 위반이 났다: {violations()}"

    def test_사설_예약_문서용_대역은_위반이_아니다(self):
        for addr in ("127.0.0.1", "192.168.1.100", "172.17.0.1", "169.254.169.254",
                     "10.0.0.1", "198.51.100.7", "192.0.2.5", "203.0.113.9", "100.64.0.0"):
            assert not is_public_host_literal(addr), f"{addr} 를 위반으로 신고하면 위양성이다"


class Test실행매체의주소는SSOT에있어야한다:
    def test_미선언_공개주소가_없다(self):
        bad = violations()
        assert not bad, (
            "실행 매체에 SSOT 밖 공개 IP 가 있다 — 「기억에서 지어낸 주소」의 서식지다.\n"
            + "\n".join(f"  {a}: {', '.join(locs[:3])}" for a, locs in sorted(bad.items()))
            + "\n정본은 LIVE_HOSTS 에 **재측정 명령과 함께** 추가하라."
        )

    def test_은퇴한_주소가_실행매체에_남아있지_않다(self):
        """★빈도 기반 판정이 놓치는 축 — 죽은 주소가 10회 있으면 다수결은 그것을 정본으로 받는다."""
        found = public_literals()
        left = {a: locs for a, locs in found.items() if classify(a) == "retired"}
        assert not left, (
            "은퇴 선언된 주소가 실행 매체에 남아 있다(「호스트 다운」 오진의 씨앗):\n"
            + "\n".join(f"  {a}: {RETIRED_HOSTS[a]}\n    {', '.join(locs)}" for a, locs in left.items())
        )


class TestSSOT선언자체가건전하다:
    """★**변이는 「단언」이 아니라 「지켜지는 선언」에 넣어야 한다.**

    이 절의 단언들은 **자기가 유일한 감시자**라서, 단언 자체를 지우는 변이는
    원리적으로 생존한다(어떤 검사도 자기 삭제를 못 잡는다). 그것은 구멍이 아니다.
    실제로 잠기는지는 **선언 데이터를 변이시켜** 확인했고, 4종 전부 CAUGHT 다:
      · LIVE 명령을 **남의 호스트 것으로 복사**   → CAUGHT
      · RETIRED 선언에서 **날짜 제거**            → CAUGHT
      · RETIRED 선언에서 **대조군 제거**          → CAUGHT
      · LIVE 주소를 **저장소에 없는 것으로**      → CAUGHT
    """

    def test_LIVE_와_RETIRED_가_겹치지_않는다(self):
        assert not (set(LIVE_HOSTS) & set(RETIRED_HOSTS))

    def test_LIVE_선언은_그_주소를_실제로_찌르는_명령을_담는다(self):
        """★값만 적으면 다음 사람이 재검증하지 않는다 — 그게 이 사고의 근본이었다.

        ★「길이 ≥ 20」 같은 **대리 변수**로 잠그지 않는다. 그러면 아무 문장이나 통과하고,
        특히 **다른 호스트의 명령을 복사해 붙인 것**이 통과한다(그게 오주소의 발생 경로다).
        명령이 **그 주소 자체**를 담는지 본다.
        """
        for addr, note in LIVE_HOSTS.items():
            assert addr in note, (
                f"{addr} 의 재측정 명령이 그 주소를 안 담는다 — 다른 호스트 명령의 복사본일 수 있다"
            )
            assert "ssh" in note or "curl" in note, f"{addr} 선언에 실행 가능한 프로브가 없다"

    def test_RETIRED_선언은_판정_근거와_날짜를_담는다(self):
        """★「죽었다」는 관측이다 — **언제 어떻게 쟀는지** 없으면 승계할 수 없다."""
        for addr, note in RETIRED_HOSTS.items():
            assert re.search(r"20\d\d-\d\d-\d\d", note), f"{addr} 은퇴 선언에 측정 날짜가 없다"
            assert "대조군" in note, (
                f"{addr} 은퇴 선언에 대조군이 없다 — 「막힘」이 내 회선 문제일 수 있다"
            )

    def test_선언된_주소가_전부_공개주소다(self):
        for addr in {**LIVE_HOSTS, **RETIRED_HOSTS}:
            assert is_public_host_literal(addr), f"{addr} 는 공개 주소가 아니다 — SSOT 대상이 아니다"


class Test탐지기가실제로탐지한다:
    """★**탐지 축을 저장소 상태와 분리해 잠근다.**

    저장소 위반을 고치는 순간 「위반 0」은 **공허한 참**이 된다 — 그 상태에서는
    탐지기를 통째로 지워도 초록이다(적대 변이 실증: `RETIRED 검사 제거` ·
    `위반 판정 무력화` 둘 다 **생존**했다). 그래서 **합성 입력**으로 따로 태운다.
    """

    def test_은퇴주소를_담은_파일을_탐지한다(self):
        retired = next(iter(RETIRED_HOSTS))
        found = scan([("deploy.sh", f"ssh ubuntu@{retired} 'bash deploy.sh'")])
        assert retired in found, "은퇴 주소를 못 잡으면 이 락의 존재 이유가 없다"
        assert violations_in(found), "은퇴 주소는 위반이어야 한다"

    def test_미선언_공개주소를_탐지한다(self):
        """★오늘 3회 사고에서 실제로 쓰인 형태 — 저장소에 없는 그럴듯한 주소."""
        found = scan([("probe.sh", "ssh ubuntu@203.0.113.9 date  # 문서용은 통과\n"
                                   "ssh ubuntu@45.77.201.6 date  # ★미선언 공개주소")])
        bad = violations_in(found)
        assert "45.77.201.6" in bad, f"미선언 공개주소를 못 잡았다: {bad}"
        assert "203.0.113.9" not in bad, "문서용 대역을 위반으로 신고하면 위양성이다"

    def test_음성대조군_정본과_사설만_있으면_위반이_없다(self):
        live = next(iter(LIVE_HOSTS))
        found = scan([("ok.sh", f"ssh ubuntu@{live} hostname\ncurl http://127.0.0.1:8000/health\n"
                                "REDIS=172.17.0.1")])
        assert not violations_in(found), "정본·사설만 있는데 위반이 나면 정상 코드를 막는다"

    def test_SVG_좌표를_주소로_읽지_않는다(self):
        """★실측 위양성 — `m16.71 13.88.7.71-2.82` 의 `13.88.7.71`.

        이 매체(`.tsx`)를 범위에서 뺀 근거다. 범위 결정이 옳은지 여기서 고정한다.
        """
        assert not any(p.suffix in (".ts", ".tsx") for p in tracked_exec_files())

    def test_은퇴와_미상을_구분한다(self):
        """★**이 입력만이 RETIRED 분기를 가른다** — 없으면 폴백이 같은 답을 내서 무잠금이다.

        둘은 운영자에게 **다른 행동**을 요구한다: 은퇴는 「정본으로 교체」,
        미상은 「출처 확인(오타인가 신규 호스트인가)」.
        """
        retired = next(iter(RETIRED_HOSTS))
        live = next(iter(LIVE_HOSTS))
        assert classify(retired) == "retired"
        assert classify("45.77.201.6") == "unknown"
        assert classify(live) is None, "정본이 위반으로 분류되면 정상 코드를 막는다"
