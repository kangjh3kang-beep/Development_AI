"""공종분류 SSOT(work_breakdown) 단위 테스트 — 4체계 왕복·unmapped 정직·전수 코드 커버리지.

검증 범위:
- WB_CATEGORIES 13종(대공종 12 + 간접비 1, 별도 축) 고정.
- A(numeric)/B(ifc) 체계 — 실코드 전수 왕복(resolve → codes_for 역참조 일치).
- D(display) 체계 — 조경/간접만 매핑, 지상/지하/직접비는 정직 unmapped.
- C(master) 체계 — boq_master 5공종·414섹션 전수 코드가 전부 resolve 되거나
  명시적 unmapped 목록(스냅샷)에 있는지 잠금(회귀 방지 — 신규 미분류 코드가 조용히
  늘어나면 이 테스트가 실패한다).
- unmapped 코드는 항상 {wb_code: None, wb_name: None, unmapped: True} 정직 반환.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from app.services.cost import work_breakdown as wb  # noqa: E402
from app.services.cost.ifc_work_map import IFC_WORK_MAP  # noqa: E402


class TestWbCategories:
    def test_대공종_13종_고정(self):
        assert set(wb.WB_CATEGORIES) == {f"WB{i:02d}" for i in range(1, 14)}

    def test_모든_대공종명_비어있지_않음(self):
        for name in wb.WB_CATEGORIES.values():
            assert isinstance(name, str) and name.strip()

    def test_간접비는_WB13_별도축(self):
        assert wb.WB_CATEGORIES["WB13"] == "간접비"


class TestResolveInvalidSystem:
    def test_알수없는_체계는_예외(self):
        with pytest.raises(ValueError):
            wb.resolve("아무코드", "unknown")  # type: ignore[arg-type]


class TestNumericSystem:
    """A(numeric) — standard_quantity_estimator 8개 원시코드 + 단가키 별칭 6개(실코드)."""

    RAW_CODES = [
        "01-콘크리트", "02-철근", "03-거푸집", "04-조적",
        "05-방수", "06-창호", "07-기계설비", "08-전기설비",
    ]
    ALIAS_CODES = ["concrete", "rebar", "formwork", "masonry", "waterproof", "window"]

    def test_원시코드_8개_전부_매핑됨(self):
        for code in self.RAW_CODES:
            r = wb.resolve(code, "numeric")
            assert r["unmapped"] is False
            assert r["wb_code"] in wb.WB_CATEGORIES

    def test_단가키_별칭_6개_전부_매핑됨(self):
        for code in self.ALIAS_CODES:
            r = wb.resolve(code, "numeric")
            assert r["unmapped"] is False

    def test_원시코드와_별칭은_동일_WB(self):
        pairs = [
            ("01-콘크리트", "concrete"), ("02-철근", "rebar"), ("03-거푸집", "formwork"),
            ("04-조적", "masonry"), ("05-방수", "waterproof"), ("06-창호", "window"),
        ]
        for raw, alias in pairs:
            assert wb.resolve(raw, "numeric")["wb_code"] == wb.resolve(alias, "numeric")["wb_code"]

    def test_왕복_codes_for(self):
        for code in self.RAW_CODES + self.ALIAS_CODES:
            wb_code = wb.resolve(code, "numeric")["wb_code"]
            assert code in wb.codes_for(wb_code, "numeric")

    def test_미지정_코드는_unmapped(self):
        r = wb.resolve("99-존재안함", "numeric")
        assert r == {"wb_code": None, "wb_name": None, "unmapped": True}


class TestIfcSystem:
    """B(ifc) — ifc_work_map.IFC_WORK_MAP 전체 19개 실코드(grep 전수 수집)."""

    @staticmethod
    def _all_ifc_codes() -> set[str]:
        return {code for pairs in IFC_WORK_MAP.values() for code, _name in pairs}

    def test_실코드_19개_고정(self):
        assert len(self._all_ifc_codes()) == 19

    def test_전수_코드_매핑됨_unmapped_없음(self):
        for code in self._all_ifc_codes():
            r = wb.resolve(code, "ifc")
            assert r["unmapped"] is False, f"ifc 코드 {code} 가 unmapped — 브리지 누락"
            assert r["wb_code"] in wb.WB_CATEGORIES

    def test_왕복_codes_for(self):
        for code in self._all_ifc_codes():
            wb_code = wb.resolve(code, "ifc")["wb_code"]
            assert code in wb.codes_for(wb_code, "ifc")

    def test_미지정_코드는_unmapped(self):
        assert wb.resolve("Z99", "ifc")["unmapped"] is True


class TestDisplaySystem:
    """D(display) — useProjectContextStore.ts CostData 필드명(실코드) 5개."""

    def test_조경은_WB12(self):
        assert wb.resolve("landscapeWon", "display") == {
            "wb_code": "WB12", "wb_name": "부대·조경공사", "unmapped": False,
        }

    def test_간접비는_WB13(self):
        assert wb.resolve("indirectWon", "display") == {
            "wb_code": "WB13", "wb_name": "간접비", "unmapped": False,
        }

    @pytest.mark.parametrize("code", ["abovegroundWon", "undergroundWon", "directWon"])
    def test_지상_지하_직접비는_정직_unmapped(self, code):
        r = wb.resolve(code, "display")
        assert r["unmapped"] is True, f"{code} 는 여러 WB에 걸친 집계 — 단일 WB 강제 매핑 금지"

    def test_codes_for_조경(self):
        assert wb.codes_for("WB12", "display") == ["landscapeWon"]


class TestMasterSystem:
    """C(master) — boq_master 5공종·414섹션 전수 코드 커버리지 잠금."""

    _DISCIPLINE_FILE_STEMS = {
        "건축": "architecture", "기계소방": "mechanical",
        "전기통신소방": "electrical", "조경": "landscape", "토목": "civil",
    }

    # 실제 클래시파이어 실행 결과 스냅샷(35개) — boq_master 데이터나 분류 규칙이 바뀌어
    # 신규 unmapped 코드가 조용히 늘어나면(또는 기존 unmapped가 사라지면) 이 테스트가
    # 깨진다(회귀 잠금). 값은 자재별 세부 라인·원가분류성 라인(골재비/운반비/기타공사
    # 등) — 단일 대공종으로 강제 분류하면 오분류이므로 정직하게 unmapped 유지.
    EXPECTED_UNMAPPED = {
        "architecture:010314", "architecture:011115", "architecture:011202",
        "architecture:011302", "architecture:0115", "architecture:0116",
        "architecture:0117", "architecture:0118", "architecture:0119",
        "civil:C01", "civil:C11", "civil:C21", "civil:C22", "civil:C23",
        "civil:C24", "civil:C25", "civil:C26", "civil:C27", "civil:C32",
        "civil:C36", "civil:C37", "civil:C58", "civil:C60", "civil:C61",
        "civil:C62", "civil:C63", "civil:C64", "civil:C68", "civil:C69",
        "electrical:010104",
        "landscape:L02",
        "mechanical:01120103", "mechanical:01130103", "mechanical:105", "mechanical:111",
    }

    @classmethod
    def _real_codes(cls) -> set[str]:
        """boq_master 실제 5공종 JSON에서 전수 섹션코드를 grep(로드) — 발명 없음."""
        import json
        from pathlib import Path

        data_dir = (
            Path(__file__).resolve().parent.parent
            / "app" / "services" / "cost" / "data" / "boq_master"
        )
        out: set[str] = set()
        for stem in cls._DISCIPLINE_FILE_STEMS.values():
            with (data_dir / f"{stem}.json").open(encoding="utf-8") as fh:
                doc = json.load(fh)
            for sec in doc.get("sections") or []:
                code = sec.get("code")
                if code:
                    out.add(f"{stem}:{code}")
        return out

    def test_실코드_414개_고정(self):
        assert len(self._real_codes()) == 414

    def test_전수_코드가_resolve되거나_명시적_unmapped_목록에_있음(self):
        real_codes = self._real_codes()
        actually_unmapped = set()
        for code in real_codes:
            r = wb.resolve(code, "master")
            if r["unmapped"]:
                actually_unmapped.add(code)
            else:
                assert r["wb_code"] in wb.WB_CATEGORIES

        # 전수 커버리지: 실코드 전부가 (매핑됨) 또는 (명시적 unmapped 목록)에 있어야 함.
        assert actually_unmapped == self.EXPECTED_UNMAPPED, (
            "unmapped 코드 집합이 스냅샷과 다릅니다 — boq_master 데이터 변경 또는 분류 "
            "규칙 변경. 의도된 변경이면 EXPECTED_UNMAPPED 를 갱신하세요.\n"
            f"신규 unmapped: {actually_unmapped - self.EXPECTED_UNMAPPED}\n"
            f"더 이상 unmapped 아님: {self.EXPECTED_UNMAPPED - actually_unmapped}"
        )

    def test_왕복_codes_for_표본(self):
        # 전수(414개) 왕복은 느리므로 대공종별 대표 코드 하나씩만 확인(결정론 샘플).
        samples = ["architecture:010202", "mechanical:0101", "electrical:010203",
                   "landscape:L01", "civil:C03"]
        for code in samples:
            r = wb.resolve(code, "master")
            if not r["unmapped"]:
                assert code in wb.codes_for(r["wb_code"], "master")

    def test_존재하지_않는_코드는_unmapped(self):
        assert wb.resolve("architecture:999999", "master")["unmapped"] is True
        assert wb.resolve("존재안함:XX", "master")["unmapped"] is True

    def test_클래시파이어_직접_확인_조적(self):
        assert wb._classify_master_name("철근콘크리트공사") == "WB04"
        assert wb._classify_master_name("전기공사") == "WB11"
        assert wb._classify_master_name("환기설비공사") == "WB10"
        assert wb._classify_master_name("골   재   비") is None

    def test_캐시_클리어_후_동일결과(self):
        before = wb.resolve("architecture:010202", "master")
        wb.clear_master_cache()
        after = wb.resolve("architecture:010202", "master")
        assert before == after
