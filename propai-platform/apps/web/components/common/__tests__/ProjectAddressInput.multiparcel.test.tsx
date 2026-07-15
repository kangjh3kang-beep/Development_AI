import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

/**
 * 다필지 하이드레이션 회귀 테스트.
 *
 * ■ 무엇을 막는가
 *   사통맵에서 다필지로 등록한 프로젝트를 "분석 히스토리"에서 고르면, 호스트가
 *   전 필지를 받아야 한다. 이게 끊기면 화면(인테이크 목록·구획도·통합 종합분석)은
 *   대표필지 1개만 렌더하는데 ContextHeader 는 store 의 sa.parcelCount 를 직접 읽어
 *   "통합 N필지"를 표시해, 같은 화면에서 필지 수·면적이 갈린다.
 *
 * ■ 왜 심각한가 (디자인 이슈가 아니라 판정 오류)
 *   규모가 개발방식을 가른다. 대표필지 1,474㎡(446평)만 보면 "가로주택정비·소규모"로
 *   권고되지만, 통합 3,059㎡(925평)는 판정 자체가 달라진다.
 *
 * ■ 계약
 *   프로젝트 선택 시 onParcelsChange(all) 이 호출되고, all[0] 은 대표주소이며
 *   스냅샷의 전 필지가 중복 없이 포함된다. 단일필지면 호출하지 않는다(기존 동작 보존).
 */

// GlobalAddressSearch 는 지도/네트워크 의존이라 대체 — 본 테스트의 대상은 프로젝트 선택 경로다.
vi.mock("@/components/common/GlobalAddressSearch", () => ({
  GlobalAddressSearch: () => <div data-testid="address-search" />,
}));

const PROJECT = { id: "p1", name: "역세권", status: "active", address: "서울특별시 동작구 상도동 211-376" };

function seedProject(parcels: Array<{ pnu: string; address: string; areaSqm: number }> | undefined) {
  useProjectStore.setState({ projects: [PROJECT] } as never);
  const ctx = useProjectContextStore.getState();
  ctx.setProject(PROJECT.id, PROJECT.name, PROJECT.status);
  ctx.updateSiteAnalysis({
    address: PROJECT.address,
    ...(parcels
      ? {
          parcels: parcels.map((p) => ({
            ...p,
            landCategory: "대",
            ownerType: "미확인",
          })),
          parcelCount: parcels.length,
        }
      : {}),
  } as never);
}

const FIVE = [
  { pnu: "1159010200100000001", address: "서울특별시 동작구 상도동 211-376", areaSqm: 1474 },
  { pnu: "1159010200100000002", address: "서울특별시 동작구 상도동 211-377", areaSqm: 420 },
  { pnu: "1159010200100000003", address: "서울특별시 동작구 상도동 211-378", areaSqm: 385 },
  { pnu: "1159010200100000004", address: "서울특별시 동작구 상도동 211-379", areaSqm: 410 },
  { pnu: "1159010200100000005", address: "서울특별시 동작구 상도동 211-380", areaSqm: 370 },
];

function selectProject() {
  // 프로젝트 picker(select)에서 대상 프로젝트를 고른다.
  const select = screen.getByRole("combobox");
  fireEvent.change(select, { target: { value: PROJECT.id } });
}

describe("ProjectAddressInput — 프로젝트 선택 시 다필지 하이드레이션", () => {
  beforeEach(() => {
    useProjectContextStore.getState().clearProject?.();
    vi.clearAllMocks();
  });

  it("다필지 프로젝트를 고르면 전 필지가 호스트로 전달된다 (대표주소 선두)", () => {
    seedProject(FIVE);
    const onParcelsChange = vi.fn();
    render(
      <ProjectAddressInput value="" onChange={() => {}} onParcelsChange={onParcelsChange} multi />,
    );

    selectProject();

    expect(onParcelsChange).toHaveBeenCalledTimes(1);
    const all = onParcelsChange.mock.calls[0][0] as string[];
    expect(all).toHaveLength(5);           // ← 1필지로 줄면 실패(회귀 검출)
    expect(all[0]).toBe(PROJECT.address);  // 대표주소가 선두(호스트 계약)
    expect(new Set(all).size).toBe(5);     // 중복 없음
    for (const p of FIVE) expect(all).toContain(p.address);
  });

  it("단일필지 프로젝트는 onParcelsChange 를 호출하지 않는다 (기존 동작 보존)", () => {
    seedProject([FIVE[0]]);
    const onParcelsChange = vi.fn();
    render(
      <ProjectAddressInput value="" onChange={() => {}} onParcelsChange={onParcelsChange} multi />,
    );

    selectProject();

    expect(onParcelsChange).not.toHaveBeenCalled();
  });

  it("스냅샷에 parcels 가 없으면 호출하지 않는다 (구 스냅샷 하위호환)", () => {
    seedProject(undefined);
    const onParcelsChange = vi.fn();
    render(
      <ProjectAddressInput value="" onChange={() => {}} onParcelsChange={onParcelsChange} multi />,
    );

    selectProject();

    expect(onParcelsChange).not.toHaveBeenCalled();
  });

  it("대표주소는 항상 onChange 로 전달된다", () => {
    seedProject(FIVE);
    const onChange = vi.fn();
    render(<ProjectAddressInput value="" onChange={onChange} multi />);

    selectProject();

    expect(onChange).toHaveBeenCalledWith(PROJECT.address);
  });
});
