import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRealtime } from "@/hooks/useRealtime";

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];

  readyState = MockWebSocket.CONNECTING;
  onmessage: ((event: MessageEvent) => void) | null = null;
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED;
  });

  constructor(public readonly url: string) {
    MockWebSocket.instances.push(this);
  }
}

describe("useRealtime", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    MockWebSocket.instances = [];
  });

  it("keeps the current message callback without reopening the socket and closes sockets on channel changes", () => {
    const firstOnMessage = vi.fn();
    const secondOnMessage = vi.fn();

    const { rerender, unmount } = renderHook(
      ({
        channelId,
        onMessage,
      }: {
        channelId: string;
        onMessage: (message: { event: string }) => void;
      }) => useRealtime(channelId, onMessage),
      {
        initialProps: {
          channelId: "alpha",
          onMessage: firstOnMessage,
        },
      },
    );

    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0]?.url).toBe("ws://localhost:8000/ws/alpha");

    rerender({
      channelId: "alpha",
      onMessage: secondOnMessage,
    });

    expect(MockWebSocket.instances).toHaveLength(1);

    act(() => {
      MockWebSocket.instances[0]?.onmessage?.({
        data: JSON.stringify({ event: "ready" }),
      } as MessageEvent);
    });

    expect(firstOnMessage).not.toHaveBeenCalled();
    expect(secondOnMessage).toHaveBeenCalledWith({ event: "ready" });

    rerender({
      channelId: "beta",
      onMessage: secondOnMessage,
    });

    expect(MockWebSocket.instances).toHaveLength(2);
    expect(MockWebSocket.instances[0]?.close).toHaveBeenCalledTimes(1);
    expect(MockWebSocket.instances[1]?.url).toBe("ws://localhost:8000/ws/beta");

    unmount();

    expect(MockWebSocket.instances[1]?.close).toHaveBeenCalledTimes(1);
  });
});
