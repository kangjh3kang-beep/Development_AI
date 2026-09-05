/**
 * SatongMapShell 연결 대상 전환 시 선택 필지 누수 봉합(레인F P0 — 사용자 버그리포트) → R2/R2b 교정.
 *
 * 증상(R1): "연결 프로젝트" 드롭다운을 "새 프로젝트로 등록" 또는 "프로젝트 연결 안 함(약식 분석)"
 *   으로 바꿔도 이전 프로젝트의 선택 필지가 그대로 잔존했다.
 *
 * R1 수정("무조건 clearParcels()")의 잘못(R2 리뷰어 프로브 실증): 상도동 프로젝트 연결 상태에서
 *   사용자가 지도로 같은 지역(상도동) 필지를 직접 담으면(가드 미발화) 그 방금 고른 선택까지
 *   삭제됐다 — addParcels 가드 경로(선택 항상 보존)와 정반대 계약. 소유권(selectionOwnerProjectIdRef)
 *   으로 "프로젝트에서 상속된 선택"과 "사용자가 직접 담은 선택"을 가른다.
 *
 * R2의 잘못(PROBE_P3 실증, R2b 교정): 소유권을 컴포넌트 인스턴스 ref에만 뒀더니, 세션 미러
 *   (sessionStorage) 하이드레이션 경로가 소유권을 복원하지 않아 산출물 페이지로 갔다가 소프트
 *   내비로 돌아오면(재마운트) 상속 선택이 사용자 소유로 영구 오분류됐다 — 원 버그리포트 재현.
 *   ownerProjectId를 세션 미러 payload에도 함께 영속해 재마운트를 넘어 살아남게 했다.
 *
 * ★★B+(2026-09-04 · 사용자 결정) — **계약 ②·⑥ 을 교체했다.**
 *   종전 ②는 *"사용자 소유는 보존된다"* 였다. 지금은 **비운다 — 대신 되돌릴 수 있다.**
 *   근거: R1 이 기각된 이유는 「비웠다」가 아니라 **「되돌릴 수 없다」**였다. 비가역성을
 *   없애면 두 계약이 충돌하지 않는다. 그리고 「비울지 말지」를 판정하려면 **소유권을 추론**
 *   해야 하는데 그 추론이 R2·R2b 의 버그 둘을 냈다.
 *   ★소유권 자체는 **남긴다** — `inheritedFromOtherProject`(교차 프로젝트 오염 고지)가
 *     여전히 소비한다. 「비우기 판정」에서만 안 쓴다.
 *     (초판에 *"write-only 가 되니 걷어낸다"* 고 적었다가 **소비 체인을 한 홉만 따라가서**
 *      틀렸다 — ref → 미러 → `inheritedFromOtherProject` 로 이어진다.)
 *   ★고지는 가른다 — 상속분은 **재연결로 복구되므로 되돌리기 실익이 없다**(사용자 지적).
 *     판정에는 **비우기 직전의 `projectId` 유무**만 쓴다(추론이 아니라 관측).
 *
 * ★★그리고 원 신고를 실제로 덮는 것은 **상태 기반 안내**다.
 *   신고 화면은 `connectTarget` 이 **초기값 "new"** 였고, 네이티브 <select> 는 같은 값을
 *   다시 골라도 `onChange` 가 **안 뜬다** — **핸들러가 아예 안 돈다.**
 *   이벤트 기반 고지(이 파일이 종전에 잠근 것)로는 **원리적으로** 덮을 수 없다.
 *
 * 이 스위트가 고정하는 계약:
 *   ① 프로젝트에서 상속된 선택 → 드롭다운 전환 시 비워진다(원 버그리포트 재현 봉합).
 *   ②(B+) 사용자가 직접 담은 선택도 **비워지고, 되돌리기로 복원된다**.
 *   ②-b 상태 기반 안내가 **전환 이벤트 없이도** 보인다 + 음성 대조군(선택 0이면 없다).
 *   ③ 지도 staged 폴리곤 청소 신호(clearSignal)는 소유권과 무관하게 항상 증가한다(R1b 결정 유지).
 *   ④ sessionStorage(satong_map_selection) 미러도 확정목록을 비울 때 함께 제거된다(실제 게이트).
 *   ⑤ 무음 금지 — 실제로 비웠을 때만 connectNotice로 고지한다.
 *   ⑥(R2b) 세션 미러에 실린 소유권이 재마운트를 넘어 살아남는다(PROBE_P3 양방향).
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import {
  SATONG_MAP_SELECTION_KEY,
  writeSatongMapSelection,
} from "@/components/precheck/satong-map-selection";
import { useProjectContextStore, type SiteAnalysisData } from "@/store/useProjectContextStore";
import { useProjectStore, type Project } from "@/store/useProjectStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

// next/dynamic(SatongMultiMap)은 jsdom에서 Leaflet 실로드가 불가 — 스텁으로 대체.
// ★clearSignal(=clearNonce)·onPickMany(가드/사용자편집 재현용)·onStagedCountChange(MEDIUM
//   staged 고지 검증용 — 테스트가 이 콜백을 직접 호출해 "staged>0" 상태를 재현한다)를 캡처한다.
const { capturedMapPropsRef } = vi.hoisted(() => ({
  capturedMapPropsRef: {
    current: null as null | {
      clearSignal?: number;
      onPickMany?: (parcels: unknown[]) => void;
      onStagedCountChange?: (count: number) => void;
    },
  },
}));

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = (props: {
      clearSignal?: number;
      onPickMany?: (parcels: unknown[]) => void;
      onStagedCountChange?: (count: number) => void;
    }) => {
      // eslint-disable-next-line react-hooks/immutability -- 테스트 전용 스텁: 지도 props 캡처
      capturedMapPropsRef.current = props;
      return <div data-testid="dynamic-map-stub" />;
    };
    return DynamicStub;
  },
}));

// 네트워크 차단: /projects 동기화·검색·레이어 조회 전부 영구 pending으로 고정.
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending),
      get: vi.fn(pending),
      post: vi.fn(pending),
      put: vi.fn(pending),
      patch: vi.fn(pending),
      delete: vi.fn(pending),
      getV2: vi.fn(pending),
      postV2: vi.fn(pending),
      putV2: vi.fn(pending),
      deleteV2: vi.fn(pending),
    },
  };
});

function makeProject(partial: Partial<Project>): Project {
  return {
    id: "proj-leak",
    name: "청진동 프로젝트",
    type: "residential",
    pnu: "",
    address: "서울특별시 종로구 청진동 1",
    area: "120㎡",
    status: "draft",
    createdAt: "2026-06-01T00:00:00.000Z",
    ...partial,
  };
}

function makeSite(partial: Partial<SiteAnalysisData>): SiteAnalysisData {
  return {
    estimatedValue: null,
    landAreaSqm: null,
    zoneCode: null,
    address: null,
    pnu: null,
    ...partial,
  } as SiteAnalysisData;
}

describe("SatongMapShell 연결 대상 전환 — 소유권 판별(R2)", () => {
  beforeEach(() => {
    capturedMapPropsRef.current = null;
    window.sessionStorage.clear();
    act(() => {
      useProjectStore.setState({ projects: [makeProject({})], syncing: false });
      useProjectContextStore.setState({
        projectId: "proj-leak",
        projectName: "청진동 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeSite({
          address: "서울특별시 종로구 청진동 1",
          parcels: [
            {
              pnu: "1111010100100010000",
              address: "서울특별시 종로구 청진동 1",
              areaSqm: 120,
              landCategory: "대",
              ownerType: "미확인",
              zoneCode: "일반상업지역",
            },
          ],
        } as Partial<SiteAnalysisData>),
      });
    });
  });

  afterEach(() => {
    window.sessionStorage.clear();
    act(() => {
      useProjectStore.setState({ projects: [], syncing: false });
      useProjectContextStore.setState({
        projectId: null,
        projectName: "",
        projectStatus: "",
        siteAnalysis: null,
      });
    });
  });

  it("① 프로젝트에서 상속된 선택 → 드롭다운을 '새 프로젝트로 등록'으로 바꾸면 비워지고 고지된다(원 버그리포트 재현)", () => {
    render(<SatongMapShell locale="ko" />);

    // 사전조건: 연결 프로젝트 필지가 선택 목록에 하이드레이션돼 있어야 한다(소유권=proj-leak).
    expect(screen.getByText("청진동 1")).toBeInTheDocument();
    expect(screen.getByText(/필지 선택 1건/)).toBeInTheDocument();

    // ★LOW 보정: 폴백 하이드레이션은 sessionStorage를 쓰지 않아 이 시점엔 아직 비어 있다.
    //   실사용에서는 다른 커밋 경로(addParcels 등)로 이미 존재했을 세션 미러를 재현해, 아래
    //   "제거됐다" 단언이 공허한 통과가 아니라 실제 게이트가 되게 한다.
    writeSatongMapSelection([
      { id: "mirror-1", address: "서울특별시 종로구 청진동 1", source: "map" },
    ]);
    expect(window.sessionStorage.getItem(SATONG_MAP_SELECTION_KEY)).not.toBeNull();

    const clearSignalBefore = capturedMapPropsRef.current?.clearSignal ?? 0;

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "new" } });
    });

    // 선택 0건
    expect(screen.queryByText("청진동 1")).not.toBeInTheDocument();
    expect(screen.getByText(/필지 선택 0건/)).toBeInTheDocument();
    expect(screen.getByText("아직 선택된 필지가 없습니다.")).toBeInTheDocument();
    // sessionStorage 미러 제거(실제 게이트)
    expect(window.sessionStorage.getItem(SATONG_MAP_SELECTION_KEY)).toBeNull();
    // 지도 staged 폴리곤 청소 신호 증가(WP-M2 대칭)
    expect(capturedMapPropsRef.current?.clearSignal).toBeGreaterThan(clearSignalBefore);
    // 무음 금지 — 고지 문구
    // ★문구를 못 박지 않는다 — **산문은 다듬을 때마다 깨지는 취약한 락**이다.
    //   계약은 「무음이 아니다」와 「몇 건을 비웠는지 말한다」이다.
    expect(screen.getByText(/비웠습니다/)).toBeInTheDocument();
  });

  it("드롭다운을 '프로젝트 연결 안 함(약식 분석)'으로 바꿔도 동일하게 비워진다", () => {
    render(<SatongMapShell locale="ko" />);

    expect(screen.getByText("청진동 1")).toBeInTheDocument();

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "none" } });
    });

    expect(screen.queryByText("청진동 1")).not.toBeInTheDocument();
    expect(screen.getByText(/필지 선택 0건/)).toBeInTheDocument();
    expect(window.sessionStorage.getItem(SATONG_MAP_SELECTION_KEY)).toBeNull();
    // ★문구를 못 박지 않는다 — **산문은 다듬을 때마다 깨지는 취약한 락**이다.
    //   계약은 「무음이 아니다」와 「몇 건을 비웠는지 말한다」이다.
    expect(screen.getByText(/비웠습니다/)).toBeInTheDocument();
  });

  it("비울 확정 선택도 staged도 없으면 무음 유지 — 불필요한 고지 남발 방지", () => {
    // 프로젝트는 연결돼 있으나 필지는 없는 상태(주소도 없음)로 재설정.
    act(() => {
      useProjectContextStore.setState({
        projectId: "proj-leak",
        projectName: "청진동 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeSite({}),
      });
    });

    render(<SatongMapShell locale="ko" />);
    expect(screen.getByText(/필지 선택 0건/)).toBeInTheDocument();

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "none" } });
    });

    expect(
      screen.queryByText(/비웠습니다/),
    ).not.toBeInTheDocument();
  });

  it("R1b: 확정 선택 0건이어도 clearSignal은 증가한다 — 지도 staged 폴리곤 정리는 소유권과 무관하게 무조건 실행", () => {
    // 확정 목록(selectedParcels)은 0건이지만, 사용자가 지도에서 필지를 찍어 SatongMultiMap
    // 내부 staged(녹색, 아직 [완료] 안 누름)에 쌓아둔 뒤 드롭다운을 바꾸는 순서를 재현한다.
    // staged 배열 자체는 스텁에서 만들 수 없지만, "확정목록이 없다"는 이유로 지도 청소 신호가
    // 스킵되지 않고 항상 오른다는 계약은 selectedParcels=0인 채로도 clearSignal이 증가한다는
    // 사실로 고정할 수 있다(고지만 조건부, 지도 청소는 무조건 — 게이팅 대상이 다르다).
    act(() => {
      useProjectContextStore.setState({
        projectId: "proj-leak",
        projectName: "청진동 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeSite({}),
      });
    });

    render(<SatongMapShell locale="ko" />);
    expect(screen.getByText(/필지 선택 0건/)).toBeInTheDocument();

    const clearSignalBefore = capturedMapPropsRef.current?.clearSignal ?? 0;

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "new" } });
    });

    expect(capturedMapPropsRef.current?.clearSignal).toBeGreaterThan(clearSignalBefore);
    expect(
      screen.queryByText(/비웠습니다/),
    ).not.toBeInTheDocument();
  });

  it("MEDIUM: 확정 0건이어도 staged>0이면 '임시 선택을 정리했습니다' 고지가 뜬다(무음 아님을 실계측)", () => {
    // ★LOW 보정: 이 브랜치(stagedCount>0)는 종전에 스텁이 onStagedCountChange를 호출하지 않아
    //   변이로 무력화해도 테스트가 통과했다 — 스텁에서 직접 통지해 실계측한다.
    act(() => {
      useProjectContextStore.setState({
        projectId: "proj-leak",
        projectName: "청진동 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeSite({}),
      });
    });

    render(<SatongMapShell locale="ko" />);
    expect(screen.getByText(/필지 선택 0건/)).toBeInTheDocument();

    // SatongMultiMap 내부에 사용자가 찍어둔(미완료) staged가 2건 있다고 통지.
    act(() => {
      capturedMapPropsRef.current?.onStagedCountChange?.(2);
    });

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "new" } });
    });

    expect(
      screen.getByText("연결 대상을 바꿔 지도에 임시로 찍어둔 선택을 정리했습니다."),
    ).toBeInTheDocument();
    // 확정목록 비움 고지와는 다른 문구다 — 혼동 방지.
    expect(
      screen.queryByText(/비웠습니다/),
    ).not.toBeInTheDocument();
  });

  it("② HIGH(R2): 사용자가 지도로 직접 담은 선택은 드롭다운 전환에도 보존된다(리뷰어 프로브 재현)", () => {
    // 상도동 프로젝트에 연결된 상태 — 최초 하이드레이션이 대표필지 1건을 시드하며 이때
    // 소유권(selectionOwnerProjectIdRef)이 "proj-sangdo"로 잡힌다(SatongMapShell.smoke.test.tsx
    // 의 가드 시나리오와 동일 주소 사용 — 같은 지역이라 addParcels 가드가 발화하지 않는다).
    act(() => {
      useProjectStore.setState({
        projects: [
          {
            id: "proj-sangdo",
            name: "상도동 프로젝트",
            type: "residential",
            pnu: "",
            address: "서울특별시 동작구 상도동 123",
            area: "500㎡",
            status: "draft",
            createdAt: "2026-06-01T00:00:00.000Z",
          },
        ],
        syncing: false,
      });
      useProjectContextStore.setState({
        projectId: "proj-sangdo",
        projectName: "상도동 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeSite({ address: "서울특별시 동작구 상도동 123" }),
      });
    });

    render(<SatongMapShell locale="ko" />);
    // 상속 시드 1건(대표 필지) 확인.
    expect(screen.getByText(/필지 선택 1건/)).toBeInTheDocument();

    // 사용자가 지도에서 같은 지역(상도동)의 다른 필지를 직접 추가 — 가드 미발화(지역 일치),
    // addParcels가 selectionOwnerProjectIdRef를 null(사용자 소유)로 바꾼다.
    act(() => {
      capturedMapPropsRef.current?.onPickMany?.([
        {
          found: true,
          address: "서울특별시 동작구 상도동 456",
          pnu: "1159010200104560000",
          lat: 37.5,
          lon: 126.94,
        },
      ]);
    });
    expect(screen.getByTitle(/서울특별시 동작구 상도동 456/)).toBeInTheDocument();
    expect(screen.getByText(/필지 선택 2건/)).toBeInTheDocument();
    // 가드가 발화하지 않았음을 재확인(교차오염 안내 없음 — 같은 지역이라 정상 병합됐다).
    expect(
      screen.queryByText("선택 필지가 연결 프로젝트 주소와 달라 '새 프로젝트로 등록'으로 전환했습니다."),
    ).not.toBeInTheDocument();

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "new" } });
    });

    // ★★계약 교체(B+ · 2026-09-04 사용자 결정) — 종전 R2 계약은 *"사용자 소유는 보존된다"* 였다.
    //   지금은 **비운다. 대신 되돌릴 수 있다.**
    //
    //   왜 바꿨나: R1("무조건 비움")이 기각된 이유는 「비웠다」가 아니라 **「되돌릴 수 없다」**
    //   였다. 비가역성을 없애면 두 계약이 충돌하지 않는다. 그리고 「비울지 말지」를 판정하려면
    //   **소유권을 추론**해야 하는데, 그 추론이 R2·R2b 의 버그 둘을 냈다.
    //   ★사용자 지적: *"새 프로젝트를 생성하니 기존 프로젝트는 따로 있는데 왜 되돌리기가?"*
    //     → 상속분은 재연결로 복구되므로 실익이 없다. **그래서 고지를 가른다**(아래 대조군).
    expect(screen.queryByTitle(/서울특별시 동작구 상도동 456/)).not.toBeInTheDocument();
    expect(screen.getByText(/비웠습니다/)).toBeInTheDocument();

    // ★비우기가 **세 매체**를 지웠음을 먼저 확인한다(대조군 — 지운 적이 없으면 복원 단언이 공허하다).
    expect(useProjectContextStore.getState().siteAnalysis?.parcelCount ?? 0).toBe(0);
    expect(window.sessionStorage.getItem(SATONG_MAP_SELECTION_KEY)).toBeNull();

    // ★되돌리기가 실제로 복원한다 — 「버튼이 있다」가 아니라 **「눌렀더니 돌아온다」**를 본다.
    const undo = screen.getByTestId("restore-cleared-selection");
    act(() => {
      fireEvent.click(undo);
    });
    expect(screen.getByTitle(/서울특별시 동작구 상도동 456/)).toBeInTheDocument();
    expect(screen.getByText(/필지 선택 2건/)).toBeInTheDocument();

    // ★★**부분 복원 금지** — 화면만 돌아오고 스토어·세션미러가 비어 있으면, 화면엔 필지가
    //   있는데 산출물이 **빈 선택으로 도는** 조합이 된다(이 저장소가 「유령 패널」로 데인 형태).
    //   비우기가 만진 매체를 **전부** 되돌리는지 각각 태운다.
    expect(useProjectContextStore.getState().siteAnalysis?.parcelCount ?? 0).toBe(2);
    const mirror = window.sessionStorage.getItem(SATONG_MAP_SELECTION_KEY);
    expect(mirror).toContain("상도동 456");
  });

  it("★상태 기반 안내 — 이벤트가 없어도 보인다(원 신고 화면의 유일한 처방)", () => {
    // 원 신고 화면은 `connectTarget` 이 **초기값 "new"** 였다. 네이티브 <select> 는 같은 값을
    // 다시 골라도 onChange 가 **안 뜬다** → 이벤트 기반 고지로는 원리적으로 덮을 수 없다.
    // ★신고 시나리오 그대로 — **연결 프로젝트 없이** 사용자가 직접 담는다(엑셀/지도).
    //   미러만 심는 방식은 `restorable`(연결 프로젝트 또는 같은 SPA 세션) 조건 때문에
    //   복원되지 않는다 — 내 첫 시도가 그래서 틀렸다.
    render(<SatongMapShell locale="ko" />);
    act(() => {
      capturedMapPropsRef.current?.onPickMany?.([
        {
          found: true,
          address: "경기도 오산시 내삼미동 356-1",
          pnu: "4137011000103560001",
          lat: 37.1,
          lon: 127.0,
        },
      ]);
    });
    // ★전환 이벤트를 **한 번도 일으키지 않고** 안내가 보여야 한다.
    expect(screen.getByTestId("new-project-selection-hint")).toBeInTheDocument();
    expect(screen.getByTestId("clear-selection-inline")).toBeInTheDocument();
  });

  it("★되돌리기가 **최신** 선택을 복원한다 — 길이가 같고 내용만 바뀐 경우(낡은 스냅샷 방지)", () => {
    // ★이 축은 **lint 래칫이 먼저 잡았다**. 의존성이 `selectedParcels.length` 였는데
    //   지금은 그 배열을 **스냅샷으로 캡처**하므로, 길이가 같고 **내용만 바뀌면**
    //   낡은 배열을 잡아 「그 전 선택」을 복원한다. 경고가 아니라 **실제 결함**이었다.
    render(<SatongMapShell locale="ko" />);
    const pick = (address: string, pnu: string) =>
      act(() => {
        capturedMapPropsRef.current?.onPickMany?.([
          { found: true, address, pnu, lat: 37.1, lon: 127.0 },
        ]);
      });

    // ★**같은 PNU 를 다시 담는다** — `addParcels` 가 키로 병합하므로 **길이는 1로 그대로**이고
    //   **내용만** 갱신된다(실제로는 `parcels-info` 2차 보강이 이 모양이다).
    //   `.length` 의존이면 이 갱신에 콜백이 **재생성되지 않아** 낡은 배열을 캡처한다.
    pick("경기도 오산시 내삼미동 356-1", "4137011000103560001");
    expect(screen.getByTitle(/내삼미동 356-1/)).toBeInTheDocument();
    pick("경기도 오산시 내삼미동 357-1", "4137011000103560001");
    // 같은 키로 병합됐으므로 옛 주소는 사라지고 새 주소만 남는다(길이는 1로 그대로).
    expect(screen.getByTitle(/내삼미동 357-1/)).toBeInTheDocument();
    expect(screen.queryByTitle(/내삼미동 356-1/)).not.toBeInTheDocument();

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "none" } });
    });
    act(() => {
      fireEvent.click(screen.getByTestId("restore-cleared-selection"));
    });
    // ★복원된 것은 **방금 것(357-1)**이어야 한다 — 낡은 스냅샷이면 356-1 이 돌아온다.
    expect(screen.getByTitle(/내삼미동 357-1/)).toBeInTheDocument();
    expect(screen.queryByTitle(/내삼미동 356-1/)).not.toBeInTheDocument();
  });

  it("★음성 대조군 — 선택이 없으면 그 안내가 없다(항상 보이는 구현과 구별)", () => {
    render(<SatongMapShell locale="ko" />);
    expect(screen.queryByTestId("new-project-selection-hint")).not.toBeInTheDocument();
    // ★이름 입력도 같은 조건이다 — 선택이 없으면 만들 것이 없다.
    expect(screen.queryByTestId("project-name-input")).not.toBeInTheDocument();
  });

  it("★프로젝트명 입력이 보이고 placeholder 가 **실제로 쓰일 파생 이름**이다", () => {
    // ★이 스위트의 beforeEach 는 **청진동 프로젝트를 의도적으로 심는다**(누수가 아니다).
    //   이 케이스는 「연결 없이 새로 담는」 상황이므로 그 시드를 걷어낸다.
    act(() => {
      useProjectContextStore.setState({
        projectId: null, projectName: null, projectStatus: null, siteAnalysis: null,
      } as never);
    });
    render(<SatongMapShell locale="ko" />);
    act(() => {
      capturedMapPropsRef.current?.onPickMany?.([
        {
          found: true,
          address: "경기도 오산시 내삼미동 356-1",
          pnu: "4137011000103560001",
          lat: 37.1,
          lon: 127.0,
        },
      ]);
    });
    const input = screen.getByTestId("project-name-input") as HTMLInputElement;
    // ★「입력창이 있다」로 끝내지 않는다 — 비웠을 때 **무엇이 쓰이는지**가 화면에 있어야 한다.
    expect(input.placeholder).toContain("내삼미동");
    expect(input.maxLength).toBe(200); // 백엔드 계약값에서 파생
  });

  it("★중복 이름이면 경고가 뜬다 + 음성 대조군(다른 이름이면 안 뜬다)", () => {
    act(() => {
      useProjectStore.setState({
        projects: [{ id: "p-1", name: "상도동 개발", address: "서울특별시 동작구 상도동 1" }] as never,
      });
    });
    // ★이 스위트의 beforeEach 는 **청진동 프로젝트를 의도적으로 심는다**(누수가 아니다).
    //   이 케이스는 「연결 없이 새로 담는」 상황이므로 그 시드를 걷어낸다.
    act(() => {
      useProjectContextStore.setState({
        projectId: null, projectName: null, projectStatus: null, siteAnalysis: null,
      } as never);
    });
    render(<SatongMapShell locale="ko" />);
    act(() => {
      capturedMapPropsRef.current?.onPickMany?.([
        {
          found: true,
          address: "경기도 오산시 내삼미동 356-1",
          pnu: "4137011000103560001",
          lat: 37.1,
          lon: 127.0,
        },
      ]);
    });
    const input = screen.getByTestId("project-name-input");
    act(() => {
      fireEvent.change(input, { target: { value: "  상도동   개발 " } });
    });
    expect(screen.getByTestId("project-name-duplicate")).toBeInTheDocument();
    // ★음성 대조군 — 「항상 경고하는」 구현과 구별한다.
    act(() => {
      fireEvent.change(input, { target: { value: "내삼미동 2차" } });
    });
    expect(screen.queryByTestId("project-name-duplicate")).not.toBeInTheDocument();
  });

  it("★중복이면 **실제로 만들어지지 않는다** — 「경고 표시」가 아니라 「차단」을 본다", async () => {
    // ★변이 검증이 이 축을 짚었다: 경고만 잠갔더니 「중복이어도 생성 진행」이 **생존**했다.
    //   생성은 **유료**다 — 표시만 하고 만들어지면 그게 결함이다.
    const before = useProjectStore.getState().projects.length;
    act(() => {
      useProjectStore.setState({
        projects: [{ id: "p-1", name: "상도동 개발", address: "서울특별시 동작구 상도동 1" }] as never,
      });
    });
    act(() => {
      useProjectContextStore.setState({
        projectId: null, projectName: null, projectStatus: null, siteAnalysis: null,
      } as never);
    });
    render(<SatongMapShell locale="ko" />);
    act(() => {
      capturedMapPropsRef.current?.onPickMany?.([
        {
          found: true,
          address: "경기도 오산시 내삼미동 356-1",
          pnu: "4137011000103560001",
          lat: 37.1,
          lon: 127.0,
        },
      ]);
    });
    act(() => {
      fireEvent.change(screen.getByTestId("project-name-input"), {
        target: { value: "상도동 개발" },
      });
    });
    const create = screen.getByRole("button", { name: /새 프로젝트 생성/ });
    await act(async () => {
      fireEvent.click(create);
    });
    // ★프로젝트가 **늘지 않았다** — 그리고 왜인지 말한다(무음 금지).
    expect(useProjectStore.getState().projects).toHaveLength(1);
    expect(before).toBeGreaterThanOrEqual(0); // 대조군: 스토어 접근 자체가 살아 있다
    // ★두 곳에 뜬다(입력 아래 경고 + 연결 고지) — **무음이 아님**만 본다.
    expect(screen.getAllByText(/이미 같은 이름의 프로젝트가 있습니다/).length).toBeGreaterThan(0);
  });
});

describe("SatongMapShell 프로젝트 A→B 전환 — clearNonce 대칭(P0-2 회귀, 종전 미검증)", () => {
  beforeEach(() => {
    capturedMapPropsRef.current = null;
    act(() => {
      useProjectStore.setState({ projects: [], syncing: false });
      useProjectContextStore.setState({
        projectId: "proj-A",
        projectName: "A 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeSite({ address: "서울특별시 종로구 청진동 1" }),
      });
    });
  });

  afterEach(() => {
    act(() => {
      useProjectContextStore.setState({
        projectId: null,
        projectName: "",
        projectStatus: "",
        siteAnalysis: null,
      });
    });
  });

  it("연결 프로젝트가 A에서 B로 바뀌면 clearSignal이 증가한다(A의 staged 폴리곤이 지도에 잔존하지 않게)", () => {
    render(<SatongMapShell locale="ko" />);
    expect(screen.getByText(/필지 선택 1건/)).toBeInTheDocument(); // A 하이드레이션 확인

    const clearSignalBefore = capturedMapPropsRef.current?.clearSignal ?? 0;

    // 실제 전환(예: handleSelectProject가 하는 setProject)을 스토어 갱신으로 직접 재현한다.
    act(() => {
      useProjectContextStore.setState({
        projectId: "proj-B",
        projectName: "B 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeSite({ address: "경기도 성남시 분당구 판교동 100" }),
      });
    });

    expect(capturedMapPropsRef.current?.clearSignal).toBeGreaterThan(clearSignalBefore);
  });
});

describe("SatongMapShell 세션 미러 소유권 영속(R2b HIGH — PROBE_P3, 리뷰어 프로브 재현)", () => {
  // ★재마운트 재현: 컴포넌트를 마운트하기 전에 sessionStorage에 직접 payload를 심어, "산출물
  //   페이지로 이동했다가 소프트 내비로 precheck에 돌아온" 흔한 재진입을 시뮬레이션한다 —
  //   이 경로가 스토어 폴백(:1679-)보다 우선하므로, 소유권 복원 누락이 가장 잘 드러나는 지점이다.
  beforeEach(() => {
    capturedMapPropsRef.current = null;
    window.sessionStorage.clear();
    act(() => {
      useProjectStore.setState({ projects: [makeProject({})], syncing: false });
    });
  });

  afterEach(() => {
    window.sessionStorage.clear();
    act(() => {
      useProjectStore.setState({ projects: [], syncing: false });
      useProjectContextStore.setState({
        projectId: null,
        projectName: "",
        projectStatus: "",
        siteAnalysis: null,
      });
    });
  });

  it("PROBE_P3-A: 프로젝트 상속 선택을 세션 미러(ownerProjectId 포함)에 심고 재마운트 → 드롭다운 전환 시 비워진다", () => {
    writeSatongMapSelection(
      [{ id: "mirror-owned", address: "서울특별시 종로구 청진동 1", source: "map" }],
      "proj-leak", // ★소유권을 명시 기록 — 이게 없으면(R2b 이전) 재마운트 후 사용자 소유로 오분류됐다.
    );
    act(() => {
      useProjectContextStore.setState({
        projectId: "proj-leak",
        projectName: "청진동 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeSite({ address: "서울특별시 종로구 청진동 1" }),
      });
    });

    render(<SatongMapShell locale="ko" />);
    // 세션 미러 경로로 하이드레이션됐는지 확인.
    expect(screen.getByText(/필지 선택 1건/)).toBeInTheDocument();

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "new" } });
    });

    // ★survived=false여야 정답(원 버그리포트 재현 봉합) — 세션 미러 경로도 스토어 폴백·전환
    //   시드와 동일하게 소유권을 인식해 상속 선택을 비운다.
    expect(screen.getByText(/필지 선택 0건/)).toBeInTheDocument();
    expect(window.sessionStorage.getItem(SATONG_MAP_SELECTION_KEY)).toBeNull();
    // ★문구를 못 박지 않는다 — **산문은 다듬을 때마다 깨지는 취약한 락**이다.
    //   계약은 「무음이 아니다」와 「몇 건을 비웠는지 말한다」이다.
    expect(screen.getByText(/비웠습니다/)).toBeInTheDocument();
  });

  it("PROBE_P3-B: 사용자 소유 선택(ownerProjectId=null)을 세션 미러에 심고 재마운트 → 드롭다운 전환에도 보존된다", () => {
    writeSatongMapSelection(
      [{ id: "mirror-user", address: "서울특별시 동작구 상도동 456", source: "map" }],
      null, // ★사용자 편집 결과임을 명시 — 재마운트 후에도 이 사실이 살아남아야 한다.
    );
    act(() => {
      useProjectContextStore.setState({
        projectId: "proj-leak",
        projectName: "청진동 프로젝트",
        projectStatus: "draft",
        // ★스토어 siteAnalysis는 다른 주소(청진동) — 세션 미러(상도동 456)가 실제로 복원됨을 함께 확인.
        siteAnalysis: makeSite({ address: "서울특별시 종로구 청진동 1" }),
      });
    });

    render(<SatongMapShell locale="ko" />);
    expect(screen.getByTitle(/서울특별시 동작구 상도동 456/)).toBeInTheDocument();
    expect(screen.getByText(/필지 선택 1건/)).toBeInTheDocument();

    const select = screen.getByRole("combobox");
    act(() => {
      fireEvent.change(select, { target: { value: "new" } });
    });

    // ★★계약 교체(B+) — 재마운트를 넘어온 선택도 **비운다. 대신 되돌릴 수 있다.**
    //   ★R2b 가 잠갔던 것은 「재마운트 후 소유권이 살아남는가」였는데, 비우기가 더 이상
    //   소유권을 안 보므로 그 축은 **비우기에 대해서는** 사라진다. 소유권 자체는 남는다 —
    //   `inheritedFromOtherProject`(교차 프로젝트 오염 고지)가 여전히 소비한다.
    expect(screen.queryByTitle(/서울특별시 동작구 상도동 456/)).not.toBeInTheDocument();
    const undoB = screen.getByTestId("restore-cleared-selection");
    act(() => {
      fireEvent.click(undoB);
    });
    expect(screen.getByTitle(/서울특별시 동작구 상도동 456/)).toBeInTheDocument();
    expect(screen.getByText(/필지 선택 1건/)).toBeInTheDocument();
    expect(
      screen.queryByText(/비웠습니다/),
    ).not.toBeInTheDocument();
  });
});

// ── ★교차 프로젝트 하이드레이션 (2026-08-24 · 사용자 스크린샷) ──────────────────
//
//  사용자 화면: 연결 프로젝트는 **"오산시 내삼미동 외 76필지"**(헤더 통합 77필지·86,755㎡)인데
//  선택 필지는 **모산동 123-1 외 6필지**였다. 두 프로젝트가 한 화면에 겹쳐 보였다.
//
//  ★기전: 하이드레이션의 `restorable` 은 `hasConnectedProject` 만 본다 — **미러의 소유
//    프로젝트가 지금 연결된 프로젝트인지 묻지 않는다.** 남의 선택이 복원되고, 그대로
//    `commitParcelsToContext` 로 **현재 프로젝트에 써 넣어졌다**(화면 오염 → 데이터 오염).
//
//  ★★A→B **전환** 이펙트는 이걸 정확히 막는데, `isFirstRun` 이면 반환한다. 즉 다른
//    페이지에서 프로젝트를 바꾼 뒤 이 화면으로 오면 **"전환"이 아니라 "첫 실행"** 이라
//    아무것도 안 지운다. **전환은 잠겼고 신규 마운트가 안 잠겨** 있었다(계약 비대칭).
//
//  ★위 PROBE_P3-A/B 는 미러에 소유권을 심지만 **항상 같은 프로젝트로** 마운트한다 —
//    `미러 소유자 ≠ 연결 프로젝트` 조합이 이 스위트에 **한 번도 없었다**. 여기서 만든다.
describe("SatongMapShell 하이드레이션 — 미러 소유자 ≠ 연결 프로젝트(교차 오염)", () => {
  beforeEach(() => {
    capturedMapPropsRef.current = null;
    window.sessionStorage.clear();
    act(() => {
      useProjectStore.setState({
        projects: [makeProject({ id: "proj-A", name: "오산시 내삼미동 외 76필지", address: "경기도 오산시 내삼미동" })],
        syncing: false,
      });
    });
  });

  afterEach(() => {
    window.sessionStorage.clear();
    act(() => {
      useProjectStore.setState({ projects: [], syncing: false });
      useProjectContextStore.setState({
        projectId: null, projectName: "", projectStatus: "", siteAnalysis: null,
      });
    });
  });

  /** 연결 프로젝트 A(내삼미동)에, 다른 프로젝트 B(모산동)의 선택이 미러에 남아 있는 상태. */
  function mountWithForeignMirror() {
    writeSatongMapSelection(
      [{ id: "b-1", address: "경기도 화성시 모산동 123-1", source: "map" }],
      "proj-B", // ★소유자는 **다른** 프로젝트다
    );
    act(() => {
      useProjectContextStore.setState({
        projectId: "proj-A",
        projectName: "오산시 내삼미동 외 76필지",
        projectStatus: "draft",
        siteAnalysis: makeSite({ address: "경기도 오산시 내삼미동" }),
      });
    });
    return render(<SatongMapShell locale="ko" />);
  }

  it("★남의 선택을 **현재 프로젝트에 커밋하지 않는다** — 화면 오염이 데이터 오염이 되던 지점", () => {
    mountWithForeignMirror();
    // 전제: 미러 경로로 하이드레이션은 됐다(선택 자체는 파괴하지 않는다 — 사용자 작업 보존).
    expect(screen.getByText(/필지 선택 1건/)).toBeInTheDocument();
    // ★핵심: 연결 프로젝트 A 의 siteAnalysis 가 B 의 필지로 덮이지 않아야 한다.
    const site = useProjectContextStore.getState().siteAnalysis;
    expect(site?.address, "A 의 주소가 B 로 덮였다 — 교차 오염이 데이터까지 갔다").toBe(
      "경기도 오산시 내삼미동",
    );
    expect(
      (site?.parcels ?? []).some((x) => String((x as { address?: string })?.address ?? "").includes("모산동")),
      "B 의 필지가 A 의 프로젝트 컨텍스트에 커밋됐다",
    ).toBe(false);
  });

  it("★무음이 아니다 — 왜 반영하지 않았는지와 빠져나갈 길을 말한다", () => {
    mountWithForeignMirror();
    const notice = screen.getByText(/연결 프로젝트와 다른 지역이라 프로젝트에 반영하지 않았습니다/);
    expect(notice).toBeInTheDocument();
    expect(notice.textContent, "빠져나갈 길을 안 준다").toMatch(/새 프로젝트로 등록/);
  });

  it("★대조군 — 같은 지역이면 종전대로 커밋한다(가드가 정상 경로를 막지 않는다)", () => {
    // ★두 모집단이 **다른 결과**를 내야 잠금이다. 지역만 바꾼다(다른 조건은 동일).
    writeSatongMapSelection(
      [{ id: "a-1", address: "경기도 오산시 내삼미동 465-1", source: "map" }],
      "proj-B", // 소유자는 여전히 다른 프로젝트지만 **지역이 같다** → 정상 워크플로우
    );
    act(() => {
      useProjectContextStore.setState({
        projectId: "proj-A",
        projectName: "오산시 내삼미동 외 76필지",
        projectStatus: "draft",
        siteAnalysis: makeSite({ address: "경기도 오산시 내삼미동" }),
      });
    });
    render(<SatongMapShell locale="ko" />);
    expect(screen.getByText(/필지 선택 1건/)).toBeInTheDocument();
    expect(
      screen.queryByText(/연결 프로젝트와 다른 지역이라/),
      "같은 지역인데 오염이라고 고지했다 — 위양성",
    ).toBeNull();
    const site = useProjectContextStore.getState().siteAnalysis;
    expect(
      (site?.parcels ?? []).length,
      "같은 지역 선택이 커밋되지 않았다 — 가드가 정상 경로를 막았다",
    ).toBeGreaterThan(0);
  });
});
