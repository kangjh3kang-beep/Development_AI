import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ThreeScene from "@/components/cad/ThreeScene";

function createCanvasContextMock() {
  return {
    beginPath: vi.fn(),
    roundRect: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    clearRect: vi.fn(),
    fillRect: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    fillText: vi.fn(),
    arc: vi.fn(),
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 1,
    font: "",
  } as unknown as CanvasRenderingContext2D;
}

function stubAnimationFrame(invokeLimit = 1) {
  let frameId = 0;
  let invoked = 0;

  const cancelAnimationFrameMock = vi.fn();
  const requestAnimationFrameMock = vi.fn((callback: FrameRequestCallback) => {
    frameId += 1;
    const currentId = frameId;

    if (invoked < invokeLimit) {
      invoked += 1;
      setTimeout(() => callback(0), 0);
    }

    return currentId;
  });

  vi.stubGlobal("requestAnimationFrame", requestAnimationFrameMock);
  vi.stubGlobal("cancelAnimationFrame", cancelAnimationFrameMock);

  return {
    requestAnimationFrameMock,
    cancelAnimationFrameMock,
  };
}

describe("ThreeScene", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("boots the dependency-light CAD canvas preview and cleans up animation listeners", async () => {
    const context = createCanvasContextMock();
    const getContextSpy = vi
      .spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockReturnValue(context);
    const addEventListenerSpy = vi.spyOn(window, "addEventListener");
    const removeEventListenerSpy = vi.spyOn(window, "removeEventListener");
    const { cancelAnimationFrameMock } = stubAnimationFrame(1);

    const { container, unmount } = render(<ThreeScene />);

    expect(screen.getByText("Loading 3D scene...")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.queryByText("Loading 3D scene...")).not.toBeInTheDocument();
    });

    expect(getContextSpy).toHaveBeenCalledWith("2d");
    expect(container.querySelector("canvas")).toBeInTheDocument();
    expect(context.clearRect).toHaveBeenCalled();
    expect(addEventListenerSpy).toHaveBeenCalledWith(
      "resize",
      expect.any(Function),
    );

    unmount();

    expect(cancelAnimationFrameMock).toHaveBeenCalled();
    expect(removeEventListenerSpy).toHaveBeenCalledWith(
      "resize",
      expect.any(Function),
    );
  });

  it("renders an error state when the browser cannot provide a canvas context", async () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    stubAnimationFrame(1);

    render(<ThreeScene />);

    expect(
      await screen.findByText("Canvas rendering is not available in this browser."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Loading 3D scene...")).not.toBeInTheDocument();
  });
});
