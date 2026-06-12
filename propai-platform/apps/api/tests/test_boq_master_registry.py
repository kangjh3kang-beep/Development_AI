"""BOQ 마스터 레지스트리(boq_master_registry) 단위 테스트.

실적 5공종 공내역서 마스터(의정부동 424 주상복합, n=1)의 lazy-load 조회 API를 검증:
- 5공종 로드·카운트(건축 961 · 기계소방 1741 · 전기통신소방 1029 · 조경 58 · 토목 208)
- 섹션 트리(level 포함) · 검색(name/spec 부분일치) · 페이지네이션 · 결정론 정렬
- 미존재 공종 정직 응답(예외 금지) · provenance 항상 동봉 · 캐시 불변(사본 반환)
"""

import os
import sys

# apps/api 루트를 Python path에 추가 (conftest 와 동일 규약 — 단독 실행 대비)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.cost import boq_master_registry as reg  # noqa: E402

# _meta.json 과 일치해야 하는 기대값(실적 추출 산출물 고정값).
EXPECTED = {
    "건축": {"file": "architecture.json", "sections": 126, "unique_items": 961},
    "기계소방": {"file": "mechanical.json", "sections": 99, "unique_items": 1741},
    "전기통신소방": {"file": "electrical.json", "sections": 114, "unique_items": 1029},
    "조경": {"file": "landscape.json", "sections": 4, "unique_items": 58},
    "토목": {"file": "civil.json", "sections": 71, "unique_items": 208},
}


# ──────────────────────────────────────────────
# list_disciplines — 5공종 로드·카운트
# ──────────────────────────────────────────────


class TestListDisciplines:
    def test_5공종_고정순서_로드(self):
        rows = reg.list_disciplines()
        assert [r["discipline"] for r in rows] == list(EXPECTED)

    def test_파일명_섹션_항목수_일치(self):
        for row in reg.list_disciplines():
            exp = EXPECTED[row["discipline"]]
            assert row["file"] == exp["file"]
            assert row["sections"] == exp["sections"]
            assert row["unique_items"] == exp["unique_items"]

    def test_provenance_항상_동봉(self):
        for row in reg.list_disciplines():
            prov = row["provenance"]
            assert prov["sample_count"] == 1
            assert "의정부동 424" in prov["name"]


# ──────────────────────────────────────────────
# get_sections — 섹션 트리(level 포함)
# ──────────────────────────────────────────────


def _count_tree_nodes(nodes):
    return sum(1 + _count_tree_nodes(n["children"]) for n in nodes)


class TestGetSections:
    def test_전공종_섹션수_일치(self):
        for discipline, exp in EXPECTED.items():
            res = reg.get_sections(discipline)
            assert res["found"] is True
            assert res["total"] == exp["sections"]
            assert len(res["sections"]) == exp["sections"]

    def test_level_포함(self):
        res = reg.get_sections("건축")
        assert all(isinstance(s["level"], int) for s in res["sections"])

    def test_트리_노드수_보존(self):
        """트리 중첩 후에도 노드 총수 = 평탄 섹션 수(유실·중복 없음)."""
        for discipline, exp in EXPECTED.items():
            res = reg.get_sections(discipline)
            assert _count_tree_nodes(res["tree"]) == exp["sections"]

    def test_조경_전부_루트(self):
        """조경(L01~L04, level 1)은 prefix 부모가 없어 모두 루트."""
        res = reg.get_sections("조경")
        assert len(res["tree"]) == 4
        assert all(node["children"] == [] for node in res["tree"])

    def test_전기_상위코드_하위중첩(self):
        """전기 '01'(전기공사) 하위에 '01' prefix 섹션들이 중첩된다."""
        res = reg.get_sections("전기통신소방")
        roots = {n["code"]: n for n in res["tree"]}
        assert "01" in roots
        assert len(roots["01"]["children"]) > 0

    def test_조경_item_count_합계(self):
        res = reg.get_sections("조경")
        assert sum(s["item_count"] for s in res["sections"]) == 58


# ──────────────────────────────────────────────
# get_items — 카운트·검색·페이지네이션·결정론
# ──────────────────────────────────────────────


class TestGetItems:
    def test_전공종_total_일치(self):
        for discipline, exp in EXPECTED.items():
            res = reg.get_items(discipline)
            assert res["found"] is True
            assert res["total"] == exp["unique_items"]
            assert len(res["items"]) == min(100, exp["unique_items"])

    def test_정렬_id_오름차순_결정론(self):
        r1 = reg.get_items("건축", query="콘크리트")
        r2 = reg.get_items("건축", query="콘크리트")
        assert r1 == r2  # 동일 입력 → 동일 출력
        ids = [it["id"] for it in r1["items"]]
        assert ids == sorted(ids)
        assert r1["total"] > 0

    def test_섹션_필터(self):
        res = reg.get_items("조경", section_code="L01")
        assert res["total"] == 29
        assert all(it["section_code"] == "L01" for it in res["items"])

    def test_검색_name_부분일치(self):
        res = reg.get_items("조경", query="대왕참나무")
        assert res["total"] >= 1
        assert any("대왕참나무" in it["name"] for it in res["items"])

    def test_검색_spec_부분일치_대소문자무시(self):
        res = reg.get_items("조경", query="h4.0")  # spec "H4.0xR12" — casefold 일치
        assert res["total"] >= 1
        assert all(
            "h4.0" in (it.get("name") or "").casefold()
            or "h4.0" in (it.get("spec") or "").casefold()
            for it in res["items"]
        )

    def test_검색_무결과_정직(self):
        res = reg.get_items("조경", query="존재하지않는항목XYZ987")
        assert res["found"] is True
        assert res["total"] == 0
        assert res["items"] == []

    def test_페이지네이션(self):
        page1 = reg.get_items("조경", limit=10, offset=0)
        page2 = reg.get_items("조경", limit=10, offset=10)
        tail = reg.get_items("조경", limit=10, offset=50)
        beyond = reg.get_items("조경", limit=10, offset=100)
        assert page1["total"] == page2["total"] == tail["total"] == 58
        assert len(page1["items"]) == 10
        assert len(tail["items"]) == 8  # 58 - 50
        assert beyond["items"] == []
        ids1 = {it["id"] for it in page1["items"]}
        ids2 = {it["id"] for it in page2["items"]}
        assert ids1.isdisjoint(ids2)

    def test_음수_입력_클램프(self):
        res = reg.get_items("조경", limit=-5, offset=-3)
        assert res["found"] is True
        assert res["items"] == []  # limit<0 → 0 클램프
        assert res["total"] == 58  # total 은 페이지와 무관

    def test_전기만_ref_mat_price_보유(self):
        elec = reg.get_items("전기통신소방", limit=200)
        assert any("ref_mat_price" in it for it in elec["items"])
        land = reg.get_items("조경", limit=100)
        assert all("ref_mat_price" not in it for it in land["items"])

    def test_영문_별칭_수용(self):
        res = reg.get_items("landscape")
        assert res["found"] is True
        assert res["discipline"] == "조경"
        assert res["total"] == 58


# ──────────────────────────────────────────────
# 미존재 공종 — 정직 응답(예외 금지)
# ──────────────────────────────────────────────


class TestUnknownDiscipline:
    def test_get_items_미존재_빈결과_사유(self):
        res = reg.get_items("플랜트")
        assert res["found"] is False
        assert res["total"] == 0
        assert res["items"] == []
        assert "플랜트" in res["reason"]
        assert res["provenance"]["sample_count"] == 1  # 출처는 여전히 동봉

    def test_get_sections_미존재_빈결과_사유(self):
        res = reg.get_sections("플랜트")
        assert res["found"] is False
        assert res["sections"] == []
        assert res["tree"] == []
        assert res["reason"]

    def test_None_입력_예외없음(self):
        res = reg.get_items(None)
        assert res["found"] is False
        assert res["items"] == []


# ──────────────────────────────────────────────
# provenance — 출처 정직성 · 캐시 불변
# ──────────────────────────────────────────────


class TestProvenance:
    def test_프로젝트_출처(self):
        prov = reg.get_provenance()
        assert "의정부동 424" in prov["name"]
        assert prov["gfa_sqm"] == 238504.0
        assert prov["sample_count"] == 1
        assert "n=1" in prov["provenance"]

    def test_사본_반환_캐시_불변(self):
        p1 = reg.get_provenance()
        p1["name"] = "변조시도"
        p2 = reg.get_provenance()
        assert "의정부동 424" in p2["name"]

    def test_items_사본_반환_캐시_불변(self):
        first = reg.get_items("조경", limit=1)["items"][0]
        original_name = first["name"]
        first["name"] = "변조시도"
        again = reg.get_items("조경", limit=1)["items"][0]
        assert again["name"] == original_name
