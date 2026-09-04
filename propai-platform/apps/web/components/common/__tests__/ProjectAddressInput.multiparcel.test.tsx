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

  it("★단일필지 프로젝트도 호출한다 — 호스트의 extra 를 비워 교차오염을 막는다", () => {
    // 호출을 건너뛰면 호스트 extra 가 '이전 프로젝트' 필지로 남는다(5필지 A → 1필지 B 전환 시
    // B 화면에 A 의 4필지 잔류 → "5개 필지 통합" 날조·A 필지로 유료 등기조회·분석 혼합).
    seedProject([FIVE[0]]);
    const onParcelsChange = vi.fn();
    render(
      <ProjectAddressInput value="" onChange={() => {}} onParcelsChange={onParcelsChange} multi />,
    );

    selectProject();

    expect(onParcelsChange).toHaveBeenCalledWith([PROJECT.address]); // → 호스트 extra = []
  });

  it("★스냅샷에 parcels 가 없어도 호출한다 (구 스냅샷 — extra 잔류 차단)", () => {
    seedProject(undefined);
    const onParcelsChange = vi.fn();
    render(
      <ProjectAddressInput value="" onChange={() => {}} onParcelsChange={onParcelsChange} multi />,
    );

    selectProject();

    expect(onParcelsChange).toHaveBeenCalledWith([PROJECT.address]);
  });

  it("대표주소는 항상 onChange 로 전달된다", () => {
    seedProject(FIVE);
    const onChange = vi.fn();
    render(<ProjectAddressInput value="" onChange={onChange} multi />);

    selectProject();

    expect(onChange).toHaveBeenCalledWith(PROJECT.address);
  });
});

describe("ProjectAddressInput — 면적 write-path 오염 가드", () => {
  // ★실측 상도동 재현: 분석으로 확보한 정확한 면적(landAreaSqm=3,059)이 이미 store 에 있는데,
  //   프로젝트 레코드 p.area 는 불량값(11,465 = 대지지분 미적용 원면적 합계)이다. 프로젝트를
  //   고를 때 레코드 값이 확보된 분석 면적을 덮으면 landAreaSqm ≠ landAreaSqmTotal 분기가 생겨
  //   같은 화면에서 두 면적이 표시된다. 빈 값일 때만 시드해야 한다.
  const PROJ_BAD_RECORD = {
    id: "p2",
    name: "역세권2",
    status: "active",
    address: "서울특별시 동작구 상도동 211-376",
    area: "11,465㎡", // 불량 레코드 값
  };

  beforeEach(() => {
    useProjectContextStore.getState().clearProject?.();
    vi.clearAllMocks();
  });

  it("이미 확보된 landAreaSqm 을 프로젝트 레코드 area 로 덮어쓰지 않는다", () => {
    useProjectStore.setState({ projects: [PROJ_BAD_RECORD] } as never);
    const ctx = useProjectContextStore.getState();
    ctx.setProject(PROJ_BAD_RECORD.id, PROJ_BAD_RECORD.name, PROJ_BAD_RECORD.status);
    // 분석으로 확보한 정확한 면적을 미리 store 에 둔다(3,059).
    ctx.updateSiteAnalysis({ address: PROJ_BAD_RECORD.address, landAreaSqm: 3059 } as never);

    render(<ProjectAddressInput value="" onChange={() => {}} multi />);
    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: PROJ_BAD_RECORD.id } });

    // 레코드 11,465 가 아니라 확보값 3,059 가 유지돼야 한다.
    expect(useProjectContextStore.getState().siteAnalysis?.landAreaSqm).toBe(3059);
  });

  it("면적이 비어 있으면 프로젝트 레코드 area 로 보강한다(기존 보강 동작 보존)", () => {
    // ★별도 프로젝트 id — clearProject 가 직전 프로젝트를 스냅샷에 보존하므로, 같은 id 를
    //   재사용하면 앞 테스트의 면적이 복원돼 격리가 깨진다(정상 store 동작).
    const FRESH = { id: "p3", name: "신규", status: "active", address: "서울특별시 동작구 상도동 211-999", area: "540㎡" };
    useProjectStore.setState({ projects: [FRESH] } as never);
    const ctx = useProjectContextStore.getState();
    ctx.setProject(FRESH.id, FRESH.name, FRESH.status);
    // 면적 미확보 상태(landAreaSqm 없음).
    ctx.updateSiteAnalysis({ address: FRESH.address } as never);

    render(<ProjectAddressInput value="" onChange={() => {}} multi />);
    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: FRESH.id } });

    // 빈 값이었으므로 레코드 값(540)으로 보강됨.
    expect(useProjectContextStore.getState().siteAnalysis?.landAreaSqm).toBe(540);
  });
});
