import { describe, it, expect } from "vitest";
import { isHrefActive } from "@/components/layout/nav-config";
import {
  LIFECYCLE_STAGES,
  PIPELINE_STAGE_TO_LIFECYCLE,
  PROJECT_TOOLS,
  projectToolHref,
  STAGE_META,
} from "./lifecycle-stages";

describe("PROJECT_TOOLS — 프로젝트 도구 인덱스 SSOT", () => {
  it("고아 도구 8종 — route 유일 + 라벨/아이콘 비어있지 않음", () => {
    expect(PROJECT_TOOLS).toHaveLength(8);
    const routes = PROJECT_TOOLS.map((t) => t.route);
    expect(new Set(routes).size).toBe(routes.length); // 중복 없음
    for (const t of PROJECT_TOOLS) {
      expect(t.route).toMatch(/^[a-z-]+$/); // 라우트 세그먼트 형식
      expect(t.label.length).toBeGreaterThan(0);
      expect(t.icon).toMatch(/^tool_/); // StageIcon tool_* 키
    }
  });

  it("STAGE_META(11단계) 라우트와 겹치지 않음 — 진짜 고아·additive", () => {
    const stageRoutes = new Set(Object.values(STAGE_META).map((m) => m.route));
    for (const t of PROJECT_TOOLS) {
      expect(stageRoutes.has(t.route)).toBe(false);
    }
  });

  it("기대 라우트 집합(회귀 고정)", () => {
    expect(PROJECT_TOOLS.map((t) => t.route)).toEqual([
      "canvas",
      "cad",
      "collaboration",
      "cost",
      "boq",
      "multi-parcel",
      "blockchain",
      "agent",
    ]);
  });
});

describe("projectToolHref + 활성판정", () => {
  it("프로젝트 상세 하위 절대경로 빌더", () => {
    expect(projectToolHref("ko", "p1", "cad")).toBe("/ko/projects/p1/cad");
    expect(projectToolHref("en", "abc", "collaboration")).toBe("/en/projects/abc/collaboration");
  });

  it("isHrefActive 재사용 — 현재 도구만 활성(하위경로 포함)", () => {
    const href = projectToolHref("ko", "p1", "collaboration");
    expect(isHrefActive(href, "/ko/projects/p1/collaboration")).toBe(true);
    expect(isHrefActive(href, "/ko/projects/p1/collaboration/room-9")).toBe(true); // 하위경로 활성
    expect(isHrefActive(href, "/ko/projects/p1/cad")).toBe(false); // 다른 도구 비활성
    expect(isHrefActive(href, "/ko/projects/p1")).toBe(false); // 개요(루트) 비활성
  });
});

// (G9) PIPELINE_STAGE_TO_LIFECYCLE — 백엔드 project_pipeline.PipelineStage(8종) ↔ 프론트
// 라이프사이클 단계 매핑 계약. apps/api/tests/test_pipeline_stage_contract.py가 BE측을 핀한다.
describe("PIPELINE_STAGE_TO_LIFECYCLE — G9 계약(BE 8스텝 ↔ FE 라이프사이클)", () => {
  // ★BE 8스텝 리터럴 핀(G4 계약과 동일 방식 — node-body-builders.test.ts의
  //   SELLABLE_EFFICIENCY_BY_TYPE 핀 참고): 상수를 "import 재출력"하지 않고(교차언어라 애초에
  //   불가능하기도 함) app/services/pipeline/project_pipeline.py:22-32의 PipelineStage 값을
  //   그대로 문자열 리터럴로 옮겨 적는다. BE가 스텝을 추가/변경하면 이 배열과
  //   apps/api/tests/test_pipeline_stage_contract.py를 함께 갱신해야 한다(드리프트=CI 실패).
  const BE_PIPELINE_STAGES = [
    "site_analysis",
    "design",
    "design_review",
    "cost",
    "feasibility",
    "tax",
    "esg",
    "report",
  ] as const;

  it("BE 8스텝 리터럴 핀 — project_pipeline.PipelineStage와 동일(개수·중복 없음)", () => {
    expect(BE_PIPELINE_STAGES).toHaveLength(8);
    expect(new Set(BE_PIPELINE_STAGES).size).toBe(8);
  });

  it("매핑 키 = BE 8스텝 전수(빠짐·추가 없음)", () => {
    expect(Object.keys(PIPELINE_STAGE_TO_LIFECYCLE).sort()).toEqual(
      [...BE_PIPELINE_STAGES].sort(),
    );
  });

  it("매핑 값 = FE 단계 id(LIFECYCLE_STAGES 소속) 또는 null", () => {
    const feIds = new Set<string>(LIFECYCLE_STAGES);
    for (const feStage of Object.values(PIPELINE_STAGE_TO_LIFECYCLE)) {
      expect(feStage === null || feIds.has(feStage)).toBe(true);
    }
  });

  it("확정 매핑값(회귀 고정) — design_review→permit·cost→construction·tax→feasibility(수지 내 세금)", () => {
    expect(PIPELINE_STAGE_TO_LIFECYCLE).toEqual({
      site_analysis: "site-analysis",
      design: "design",
      design_review: "permit",
      cost: "construction",
      feasibility: "feasibility",
      tax: "feasibility",
      esg: "esg",
      report: "report",
    });
  });
});
