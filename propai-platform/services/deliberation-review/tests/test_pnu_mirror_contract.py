"""PNU 판정 — **미러 정합**과 **미검증 입구**를 잠근다.

## 왜 미러인가

이 서비스는 **독립 이미지**다(`Dockerfile` 의 `COPY . /app` 가 이 디렉토리만 담는다).
메인 api 의 `app/utils/pnu.py` 를 임포트할 수 없어 **의도적으로 복사**했다.

★`#944` 실증: 프론트·백엔드 두 미러가 **정규식 텍스트는 같은데 의미가 달랐다**
(`\\d` 의 유니코드 포함 여부). **텍스트가 같다고 같은 판정이 아니다 — 오직 실행이 갈랐다.**
그래서 이 락은 **텍스트를 비교하지 않고 행위를 비교**한다.

## 무엇이 실제 결함이었나 (2026-09-04 실측)

입력 계약 `AnalysisInput.pnu` 는 `Field(pattern=r"^([0-9]{19})?$")` 로 **이미 막혀 있다.**
그런데 어댑터에 실제로 가는 값은 `effective_pnu` 이고, 그것은
`vworld_geocoder.address_to_pnu()` 가 **외부 응답의 `properties.pnu` 를 그대로** 실어 준다.

> **「입력이 검증된다」와 「그 변수가 검증된다」는 다른 명제다.**
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.utils.pnu import is_valid_pnu

# 저장소 루트: tests/ → deliberation-review → services → propai-platform
_REPO = Path(__file__).resolve().parents[3]
_CANON = _REPO / "apps" / "api" / "app" / "utils" / "pnu.py"


def _load_canonical():
    """정본을 **파일 경로로** 읽는다(패키지 임포트 불가 — 다른 이미지다).

    ★없으면 **시끄럽게 실패**한다. `importorskip` 류로 조용히 건너뛰면
    미러 정합 락이 **통째로 무잠금**이 된다(이 저장소가 겪은 형태다).
    """
    assert _CANON.exists(), f"정본을 못 찾았다(경로가 바뀌었나): {_CANON}"
    spec = importlib.util.spec_from_file_location("_canonical_pnu", _CANON)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 두 모집단을 **명시적으로** 가른다 — 통과해야 할 것과 거부돼야 할 것.
_MUST_PASS = (
    "4137011000104670001",
    "1111010100100890025",
    "1168010100100010000",
)
_MUST_REJECT = (
    "",                                # 빈값
    None,                              # 미상
    "413701100010467000",              # 18자
    "41370110001046700012",            # ★20자 — 「길이 >= 19」 판정이 통과시키던 것
    " 4137011000104670001",            # 앞 공백 — 소비처는 원본을 슬라이싱한다
    "4137011000104670001 ",            # 뒤 공백
    "４１３７０１１０００１０４６７０００１",  # ★전각 19자 — `\\d` 가 통과시킨다
    "٤١٣٧٠١١٠٠٠١٠٤٦٧٠٠٠١",              # 아랍-인도 숫자 19자
    "413701100010467000A",             # 비숫자 혼입
    "store-rep-서울시상도동",             # 실측된 오염 형태(PNU 칸의 비-PNU)
)


class Test미러가같은답을낸다:
    """★**행위로 비교한다** — 텍스트가 같아도 의미가 다를 수 있다."""

    @pytest.mark.parametrize("value", _MUST_PASS + _MUST_REJECT)
    def test_두_구현이_모든_입력에서_일치한다(self, value):
        canon = _load_canonical()
        assert is_valid_pnu(value) == canon.is_valid_pnu(value), (
            f"미러가 갈렸다: {value!r} → 서브서비스 {is_valid_pnu(value)} / 정본 {canon.is_valid_pnu(value)}"
        )

    def test_대조군_정본이_실제로_판정을_한다(self):
        """★정본이 전부 True 나 전부 False 를 내면 위 비교는 공허하다."""
        canon = _load_canonical()
        assert any(canon.is_valid_pnu(v) for v in _MUST_PASS)
        assert not any(canon.is_valid_pnu(v) for v in _MUST_REJECT)


class Test두모집단이갈린다:
    @pytest.mark.parametrize("value", _MUST_PASS)
    def test_정상_PNU_는_통과한다(self, value):
        """★위양성 축 — 「전부 거부」가 만점이 되지 않게 한다."""
        assert is_valid_pnu(value)

    @pytest.mark.parametrize("value", _MUST_REJECT)
    def test_비규격은_거부된다(self, value):
        assert not is_valid_pnu(value)


class Test길이판정이남아있지않다:
    """★**파생형 래칫** — 손으로 센 목록은 곧 상한이 된다.

    실행 코드에서 `len(pnu) < 19` 류가 다시 생기면 여기서 빨개진다.
    2026-09-04 기준 **7벌**을 걷어냈다(어댑터 5 + 파이프라인 2).
    """

    @staticmethod
    def _exec_sources():
        import ast
        root = Path(__file__).resolve().parents[1] / "apps" / "api" / "app"
        return [p for p in root.rglob("*.py")], ast

    def test_대조군_수집이_살아있다(self):
        files, _ = self._exec_sources()
        assert len(files) >= 30, f"수집이 죽었다: {len(files)}건"

    def test_길이로_PNU_를_판정하는_곳이_없다(self):
        """★`ast` 로 본다 — 주석·독스트링에 뚫리지 않는다."""
        files, ast = self._exec_sources()
        bad: list[str] = []
        for f in files:
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                parts = [node.left, *node.comparators]
                has_len_pnu = any(
                    isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "len"
                    and n.args and "pnu" in ast.dump(n.args[0]).lower()
                    for n in parts
                )
                has_19 = any(isinstance(n, ast.Constant) and n.value == 19 for n in parts)
                if has_len_pnu and has_19:
                    bad.append(f"{f.relative_to(Path(__file__).resolve().parents[1])}:{node.lineno}")
        assert not bad, (
            "길이로 PNU 를 판정하는 곳이 남아 있다 — 20자·전각·공백이 통과한다:\n  " + "\n  ".join(bad)
        )

    def test_어댑터가_전부_정본을_경유한다(self):
        """★**존재 검사가 아니라 전수 대조** — 새 어댑터가 자동으로 감시망에 들어온다."""
        root = Path(__file__).resolve().parents[1] / "apps" / "api" / "app" / "adapters" / "regulation"
        adapters = [p for p in root.glob("*.py") if p.name != "__init__.py"]
        assert len(adapters) >= 5, f"어댑터 수집이 죽었다: {len(adapters)}"
        missing = [
            p.name for p in adapters
            if "pnu" in p.read_text(encoding="utf-8") and "is_valid_pnu" not in p.read_text(encoding="utf-8")
        ]
        assert not missing, f"PNU 를 다루면서 정본을 안 쓰는 어댑터: {missing}"


class Test지오코더입구가막힌다:
    """★이 서비스에서 PNU 가 들어오는 **유일한 미검증 입구**였다."""

    @staticmethod
    def _geocoder(pnu_value):
        from app.adapters.regulation import vworld_geocoder as g
        gc = g.VworldGeocoder.__new__(g.VworldGeocoder)
        gc.key = "k"
        gc._getcoord = lambda a, t: (127.0, 37.0)                      # type: ignore[attr-defined]
        gc._coord_to_parcel = lambda lon, lat: (pnu_value, {"type": "Polygon"})  # type: ignore[attr-defined]
        return gc.address_to_pnu("서울특별시 동작구 상도동 211-434")

    def test_비규격_PNU_는_싣지_않는다(self):
        out = self._geocoder("41370110001046700012")   # ★20자
        assert out is not None and out["pnu"] is None, f"비규격이 실렸다: {out}"

    def test_왜_버렸는지_사유를_남긴다(self):
        """★무언 실패 금지 — 「조회 결과 없음」과 「받았는데 버렸다」는 다른 사건이다."""
        out = self._geocoder("４１３７０１１０００１０４６７０００１")   # 전각
        assert out["pnu_reason"], "사유가 없으면 조사자가 외부 장애를 의심하며 시간을 쓴다"
        assert "비규격" in out["pnu_reason"]

    def test_음성대조군_정상_PNU_는_그대로_실린다(self):
        """★「전부 버리는」 구현과 구별한다."""
        out = self._geocoder("4137011000104670001")
        assert out["pnu"] == "4137011000104670001"
        assert out["pnu_reason"] is None
