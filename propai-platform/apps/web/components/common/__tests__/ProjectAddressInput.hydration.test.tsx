import { renderToString } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

/**
 * 하이드레이션 불변식 — **서버 렌더는 persisted 스토어 내용에 의존하면 안 된다.**
 *
 * ■ 왜(라이브 관측 + 로컬 변이로 확정)
 *   `pickerProjects` 는 `useProjectStore.projects`(zustand persist = localStorage)에서 파생된다.
 *   **서버에는 localStorage 가 없으므로 서버는 항상 빈 배열**을 본다. 그 값을 조건부 렌더에
 *   그대로 쓰면 서버는 노드를 안 그리고 브라우저는 그려 **React #418**(하이드레이션 불일치)이 난다.
 *   React 는 그 서브트리를 통째로 버리고 uncaught error 를 던진다.
 *   로컬 프로덕션 빌드에서 이 조건을 무력화하니 `/ko/regulations` 의 #418 이 **1→0** 이 됐고,
 *   같은 배치의 다른 라우트(양성 대조군)는 **1 을 유지**했다.
 *
 * ■ 왜 문자열 검사를 쓰지 않는가
 *   이 저장소는 소스 문자열 락이 **주석 처리 + 임포트 유지** 변이에 여러 번 뚫렸다.
 *   그래서 `hydrated &&` 가 코드에 있는지 보지 않고 **불변식 자체를 직접 태운다** —
 *   빈 스토어 렌더와 채운 스토어 렌더가 **바이트 동일**해야 한다.
 *   ★파생형이라 이 컴포넌트에 **새 persisted-파생 조건부가 생겨도 자동으로** 감시망에 든다.
 */

// 지도·네트워크 의존이라 대체(이 테스트의 대상은 서버 렌더 안정성이다).
vi.mock("@/components/common/GlobalAddressSearch", () => ({
  GlobalAddressSearch: () => <div data-testid="address-search" />,
}));

const PROJECT = {
  id: "p1",
  name: "역세권",
  status: "active",
  address: "서울특별시 동작구 상도동 211-376",
};

function clearStores() {
  useProjectStore.setState({ projects: [] } as never);
  useProjectContextStore.setState({ snapshots: {} } as never);
}

function seedStores() {
  useProjectStore.setState({ projects: [PROJECT] } as never);
  const ctx = useProjectContextStore.getState();
  ctx.setProject(PROJECT.id, PROJECT.name, PROJECT.status);
  ctx.updateSiteAnalysis({ address: PROJECT.address } as never);
}

describe("ProjectAddressInput — 서버 렌더 하이드레이션 안정성", () => {
  beforeEach(() => {
    clearStores();
  });

  it("★서버 렌더가 persisted 스토어 내용에 의존하지 않는다", () => {
    const empty = renderToString(<ProjectAddressInput value="" onChange={() => {}} />);
    seedStores();
    const seeded = renderToString(<ProjectAddressInput value="" onChange={() => {}} />);

    // 대조군 ①: 렌더가 실제로 무언가를 냈는가(빈 문자열이면 이 단언은 공허하다).
    expect(empty.length, "서버 렌더가 비었다 — 이 테스트는 아무것도 잠그지 않는다").toBeGreaterThan(50);
    // 대조군 ②: 스토어 시딩이 실제로 먹었는가(안 먹었으면 두 렌더가 같은 게 당연하다).
    expect(useProjectStore.getState().projects.length, "시딩 실패 — 대조가 무의미하다").toBe(1);

    expect(
      seeded,
      "서버 렌더가 저장소 내용에 따라 달라진다 → 브라우저 첫 렌더와 어긋나 React #418 이 난다",
    ).toBe(empty);
  });

  it("서버 렌더에 프로젝트 선택 드롭다운이 없다(스토어가 차 있어도)", () => {
    seedStores();
    const html = renderToString(<ProjectAddressInput value="" onChange={() => {}} />);
    expect(html).not.toContain("<select");
    // 대조군: 이 조회기가 살아 있는가 — 반드시 있어야 할 형제 노드.
    expect(html, "조회기 사망 — 컴포넌트가 렌더되지 않았다").toContain("address-search");
  });

  it("서버 렌더는 라벨 등 저장소와 무관한 것은 그대로 그린다", () => {
    // ★게이트가 컴포넌트를 통째로 죽이면 안 된다 — 첫 페인트에 주소 입력이 사라지면 더 나쁘다.
    const html = renderToString(<ProjectAddressInput value="" onChange={() => {}} label="대지 주소" />);
    expect(html).toContain("대지 주소");
  });
});
