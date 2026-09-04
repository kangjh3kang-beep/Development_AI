"""잔재 스택 판정을 **시간 겹침**으로 잠근다 — 표식 종류 수로 세지 않는다.

★왜 이 파일이 있는가 (2026-08-26 실측 회귀):
  계기판이 `표식 종류 > 1 → 잔재 스택` 으로 판정했다. 그런데 판정 창은 STOP(2일 전)
  이후 전체이고, 그 사이 배포를 8회 넘게 한다. **배포마다 표식이 바뀌므로 두 번째
  배포 이후로는 영원히 위반**이었다. 실측 형태:

      v002797  08-26 04:04~04:05
      v002799  08-26 08:05
      v002809  08-26 12:05~12:08     ← 완전한 순차 승계, 교차 기록 0건

  이것을 "잔재 스택 3종"으로 신고했다. 상시 빨간 계기판은 곧 무시되고,
  그때 **진짜 잔재가 묻힌다**. 위양성도 결함이다.

★이 테스트가 없어서 그 위양성이 배포됐다 — 계기판·프로브를 잠그는 테스트가 0건이었다.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_PROBE = (Path(__file__).resolve().parents[1]
          / "scripts" / "monitor" / "growth_stale_producer_probe.py")


def _load():
    """프로브를 **파일 경로로** 불러온다 — 임포트만으로 DB 에 붙으면 안 된다."""
    assert _PROBE.exists(), f"프로브 파일이 없다: {_PROBE}"
    spec = importlib.util.spec_from_file_location("growth_probe", _PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # ← DB 임포트가 모듈 레벨이면 여기서 터진다
    return mod


def _t(h: int, m: int = 0) -> datetime:
    return datetime(2026, 8, 26, h, m, tzinfo=timezone.utc)


class Test판정자:
    def test_임포트만으로_DB에_붙지_않는다(self):
        """★모듈 레벨 DB 임포트는 이 테스트를 통째로 못 돌게 만든다(무잠금)."""
        mod = _load()
        assert callable(mod.is_stale_stack)

    def test_순차_승계는_잔재가_아니다(self):
        """★실측 형태 — 배포마다 표식이 바뀐 정상 상태. 여기가 빨가면 계기판이 상시 빨갛다."""
        mod = _load()
        spans = [
            ("propai-v002797", _t(4, 4), _t(4, 5)),
            ("propai-v002799", _t(8, 5), _t(8, 5)),
            ("propai-v002809", _t(12, 5), _t(12, 8)),
        ]
        assert mod.is_stale_stack(spans) == []

    def test_동시_기록은_잔재다(self):
        """★대조 모집단 — 옛 빌드가 새 빌드와 **겹쳐서** 쓴다."""
        mod = _load()
        spans = [
            ("propai-vOLD", _t(4, 0), _t(9, 0)),   # 옛 빌드가 계속 쓰고 있다
            ("propai-vNEW", _t(8, 5), _t(8, 6)),   # 그 위로 새 빌드가 배포됨
        ]
        hits = mod.is_stale_stack(spans)
        assert hits, "겹치는데 잔재로 판정되지 않았다"
        assert {"propai-vOLD", "propai-vNEW"} == set(hits[0])

    def test_두_모집단이_실제로_다른_값을_낸다(self):
        """★픽스처가 두 모집단을 갈라야 배선 변이가 죽는다(차가 0이면 잠금이 아니다)."""
        mod = _load()
        seq = [("A", _t(1), _t(2)), ("B", _t(5), _t(6))]
        ovl = [("A", _t(1), _t(6)), ("B", _t(5), _t(6))]
        assert mod.is_stale_stack(seq) != mod.is_stale_stack(ovl)

    def test_무표식은_판정에서_제외된다(self):
        """`(표식없음)` 은 표식 배포 이전 생성분이라 겹침 판정 대상이 아니다."""
        mod = _load()
        spans = [
            ("(표식없음)", _t(0), _t(23)),          # 온종일 걸쳐 있다
            ("propai-vA", _t(4), _t(5)),
        ]
        assert mod.is_stale_stack(spans) == []

    def test_경계_창이_상수로_노출된다(self):
        """★대역(`> 0`)이 아니라 **상수에 결속**시킨다 — 상수가 장식이 되지 않게."""
        mod = _load()
        w = mod.OVERLAP_WINDOW_SEC
        assert isinstance(w, int) and w > 0
        # 창보다 **더 벌어진** 간격은 겹침이 아니다
        far = [("A", _t(1), _t(2)), ("B", _t(2) + timedelta(seconds=w + 1), _t(3))]
        assert mod.is_stale_stack(far) == []
        # 창 **안쪽**은 겹침이다
        near = [("A", _t(1), _t(2)), ("B", _t(2) + timedelta(seconds=w - 1), _t(3))]
        assert mod.is_stale_stack(near)


class Test계기판_배선:
    """판정 결과가 **계기판 종료코드로 이어지는지**를 잠근다(순수 함수만 맞아도 소용없다)."""

    _DASH = (Path(__file__).resolve().parents[1]
             / "scripts" / "monitor" / "integrator_dashboard.sh")

    def _src(self) -> str:
        assert self._DASH.exists(), f"계기판이 없다: {self._DASH}"
        return self._DASH.read_text(encoding="utf-8")

    def test_계기판이_overlap_필드를_읽는다(self):
        assert "overlap=" in self._src(), "계기판이 프로브의 overlap 을 안 읽는다"

    def test_종류_수로_위반을_내지_않는다(self):
        """★원래 결함을 되살리는 변이 — `NB > 1` 이 다시 VIOL 을 세우면 빨개야 한다."""
        src = self._src()
        for line in src.splitlines():
            code = line.split("#", 1)[0]          # 주석은 배제(설명은 남아 있어야 한다)
            if "NB" in code and "-gt 1" in code:
                assert "VIOL=1" not in code, (
                    "표식 종류 수로 위반을 낸다 — 배포마다 표식이 바뀌므로 상시 위반이 된다")

    def test_판정불가는_DEAD로_간다(self):
        """★VIOL=3 은 exit 2 조건에 안 걸려 **조용히 exit 0** 이 된다."""
        src = self._src()
        assert "VIOL=3" not in src, "VIOL=3 은 어떤 종료코드에도 안 걸린다 — DEAD=1 을 써라"
        assert "overlap 필드가 없다" in src and "DEAD=1" in src
