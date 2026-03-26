import { useEffect, useEffectEvent, useRef } from "react";

export function useRealtime<T>(
  channelId: string,
  onMessage: (message: T) => void,
) {
  const socketRef = useRef<WebSocket | null>(null);
  const handleMessage = useEffectEvent(onMessage);

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/${channelId}`);

    ws.onmessage = (event) => {
      handleMessage(JSON.parse(event.data) as T);
    };

    socketRef.current = ws;

    return () => {
      if (
        ws.readyState === WebSocket.OPEN ||
        ws.readyState === WebSocket.CONNECTING
      ) {
        ws.close();
      }
      socketRef.current = null;
    };
  }, [channelId]);
}
