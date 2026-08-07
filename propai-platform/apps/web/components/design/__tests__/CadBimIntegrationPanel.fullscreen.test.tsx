/**
 * CAD·BIM 전체화면 **조건 배선** 계약.
 *
 * ★왜 따로 필요한가 — 층위 사다리 계약(`__tests__/layer-ladder.contract.test.tsx`)은
 *   이 파일 텍스트에 `z-[9990]` 이 **존재하는지**만 본다(소스 grep). 그래서 독립 변이
 *   검증에서 `fullscreen ?` → `!fullscreen ?` **조건 반전이 생존**했다 — 문자열은 엉뚱한
 *   분기에 그대로 남아 검사를 통과하기 때문이다.
 *
 *   결과는 사용자가 바로 겪는 버그다: 전체화면 버튼을 누르면 오히려 줄어들고, 평상시에
 *   전체화면 상태가 된다. **그걸 잡는 테스트가 하나도 없었다.**
 *
 * ★소스 검사로는 원리적으로 못 잡는다(조건을 뒤집어도 토큰 구성은 같다).
 *   그래서 실제로 **렌더하고 토글해서** 클래스가 붙고 떨어지는지를 본다.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// ── 3D 스택은 jsdom에서 못 돈다. 층위 판정에 필요한 DOM만 남기고 걷어낸다. ──
vi.mock("@react-three/fiber", () => ({
  Canvas: ({ children }: { children?: React.ReactNode }) => <div data-testid="r3f-canvas">{children}</div>,
  useThree: () => ({ camera: {}, gl: {}, scene: {}, size: { width: 800, height: 600 } }),
}));
vi.mock("@react-three/drei", () => ({
  CameraControls: () => null,
  Grid: () => null,
  Line: () => null,
  Html: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Sphere: () => null,
  TransformControls: () => null,
}));
vi.mock("three/examples/jsm/loaders/GLTFLoader.js", () => ({ GLTFLoader: class {} }));
vi.mock("./ProceduralBuilding", () => ({ ProceduralBuilding: () => null }));
vi.mock("@/components/design/CADEditor", () => ({ default: () => <div data-testid="cad-editor" /> }));

import { CadBimIntegrationPanel } from "@/components/design/CadBimIntegrationPanel";

const FULLSCREEN_Z = "z-[9990]";

/** 화면에 전체화면 오버레이(계약값 z)가 몇 개나 있는가. DOM 순회보다 계약을 직접 말한다. */
function fullscreenOverlayCount(): number {
  return document.querySelectorAll(`[class*="${FULLSCREEN_Z}"]`).length;
}

describe("CAD·BIM 전체화면 — 조건 배선", () => {
  it("★평상시에는 전체화면 오버레이가 없고, 토글하면 생긴다(조건 반전 감지)", () => {
    render(<CadBimIntegrationPanel projectId="test-project" dictionary={{}} />);

    const button = screen.getByTestId("cadbim-fullscreen");
    // ★공허 진리 방지 — 버튼이 실제로 있고 초기 상태가 '꺼짐'이어야 이 검사가 의미를 갖는다.
    expect(button).toHaveAttribute("aria-pressed", "false");
    expect(fullscreenOverlayCount()).toBe(0);

    fireEvent.click(button);

    expect(screen.getByTestId("cadbim-fullscreen")).toHaveAttribute("aria-pressed", "true");
    expect(fullscreenOverlayCount()).toBe(1);

    // 되돌리면 사라져야 한다 — 한 방향만 보면 "항상 켜짐" 변이를 놓친다.
    fireEvent.click(screen.getByTestId("cadbim-fullscreen"));
    expect(fullscreenOverlayCount()).toBe(0);
  });
});
