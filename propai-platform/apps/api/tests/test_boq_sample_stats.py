"""N1 — 실적 N건 누적 → 원단위 표본 통계(boq_sample_stats) 인프라 테스트.

검증 범위(§3 N1 명세 — 인프라만):
- unit_rate_stats: n·평균·표본표준편차(ddof=1)·CV(변동계수).
- aggregate_item_unit_rates: (name,spec,unit)별 프로젝트간 원단위(qty/driver) 누적.
- 일반화 게이트: n<3 보류(섣부른 일반화 금지) / n>=3 일반화 허용.
- 엔진 옵셔널 참조: sample_stats 미제공 → 현 동작(n=1) 그대로,
  합성 n=3 표본 제공 → 해당 항목만 평균 원단위·"실적 N건 기반·CV xx%" 배지로 전환.
- 단일 플랫 구조 하위호환: load_projects 가 기존 data/boq_master/*.json 을
  default 프로젝트 1건으로 인식(n=1 유지).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.cost import boq_sample_stats as stats  # noqa: E402
from app.services.cost.boq_parametric_engine import generate_draft  # noqa: E402


class TestUnitRateStats:
    def test_n1_단일표본(self):
        s = stats.unit_rate_stats([2.0])
        assert s["n"] == 1
        assert s["mean"] == 2.0
        assert s["cv"] == 0.0

    def test_n3_평균_표준편차_cv(self):
        s = stats.unit_rate_stats([2.0, 4.0, 6.0])
        assert s["n"] == 3
        assert s["mean"] == 4.0
        assert abs(s["std"] - 2.0) < 1e-9  # ddof=1: var=(4+0+4)/2=4 → std=2
        assert abs(s["cv"] - 0.5) < 1e-9

    def test_빈표본(self):
        s = stats.unit_rate_stats([])
        assert s["n"] == 0
        assert s["mean"] is None

    def test_일반화_게이트(self):
        assert stats.is_generalizable({"n": 3}) is True
        assert stats.is_generalizable({"n": 2}) is False
        assert stats.REF_MIN_N == 3


class TestAggregate:
    def test_원단위_누적_2건(self):
        projects = [
            {"params": {"gfa_sqm": 100.0},
             "items": [{"name": "레미콘", "spec": "25-24", "unit": "m3",
                        "qty_sample": 200.0, "driver": "gfa"}]},
            {"params": {"gfa_sqm": 100.0},
             "items": [{"name": "레미콘", "spec": "25-24", "unit": "m3",
                        "qty_sample": 400.0, "driver": "gfa"}]},
        ]
        agg = stats.aggregate_item_unit_rates(projects)
        key = ("레미콘", "25-24", "m3")
        assert key in agg
        assert agg[key]["n"] == 2
        # 원단위 = 200/100=2.0, 400/100=4.0 → 평균 3.0
        assert abs(agg[key]["mean"] - 3.0) < 1e-9


class TestEngineHook:
    def test_미제공시_현동작_n1(self):
        draft = generate_draft({"gfa_sqm": 52000.0}, disciplines=["건축"])
        items = draft["disciplines"]["건축"]["items"]
        # 표본 통계 미제공 → 전 항목 현행 신뢰도(n=1) 유지
        assert all(it["confidence"] == "낮음(n=1)" for it in items)

    def test_n3_표본_평균_및_배지_전환(self):
        key = ("가설용수시설", "연면적기준,인입비포함", "M2")
        sample_stats = {key: {"n": 3, "mean": 1.5, "std": 0.3, "cv": 0.2, "driver": "gfa"}}
        draft = generate_draft({"gfa_sqm": 52000.0}, disciplines=["건축"],
                               sample_stats=sample_stats)
        items = draft["disciplines"]["건축"]["items"]
        target = [it for it in items
                  if it["name"] == "가설용수시설" and it["spec"] == "연면적기준,인입비포함"]
        assert target, "대상 항목(가설용수시설) 미발견"
        t = target[0]
        # 평균 원단위 × gfa = 1.5 × 52000 = 78000
        assert t["qty"] == 78000
        assert "실적 3건" in t["confidence"]
        assert "CV" in t["confidence"]
        # 표본 없는 다른 항목들은 현행(n=1) 유지(섣부른 일반화 금지)
        assert any(it["confidence"] == "낮음(n=1)" for it in items)


class TestLoadProjectsBackwardCompat:
    def test_단일_플랫구조_default_프로젝트(self):
        projects = stats.load_projects()  # 기존 data/boq_master/*.json
        assert len(projects) == 1
        assert projects[0]["name"] == "default"
        assert projects[0]["items"], "default 프로젝트 항목이 비어 있음"

    def test_load_sample_stats_전부_n1(self):
        agg = stats.load_sample_stats()
        assert agg, "표본 통계가 비어 있음"
        # 단일 실적(n=1) → 일반화 가능한 항목 0건(현행 유지)
        assert all(not stats.is_generalizable(s) for s in agg.values())
