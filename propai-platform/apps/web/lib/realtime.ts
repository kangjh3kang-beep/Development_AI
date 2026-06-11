export type SseSubscriptionOptions<T> = {
  parse?: (raw: string) => T;
  onOpen?: () => void;
  onMessage: (payload: T, event: MessageEvent<string>) => void;
  onError?: (event: Event) => void;
  withCredentials?: boolean;
};

export function createSseSubscription<T>(
  url: string,
  options: SseSubscriptionOptions<T>,
) {
  const eventSource = new EventSource(url, {
    withCredentials: options.withCredentials ?? false,
  });

  eventSource.onopen = () => {
    options.onOpen?.();
  };

  eventSource.onmessage = (event) => {
    const payload = options.parse
      ? options.parse(event.data)
      : (JSON.parse(event.data) as T);

    options.onMessage(payload, event);
  };

  eventSource.onerror = (event) => {
    options.onError?.(event);
  };

  return () => {
    eventSource.close();
  };
}

/* ── fetch 기반 SSE 리더 ──
   EventSource는 GET 전용이라 POST 본문·Authorization 헤더를 보낼 수 없다.
   text/event-stream 응답을 fetch ReadableStream으로 직접 파싱해 data 프레임 단위로
   onMessage를 호출한다. 비-2xx·비-스트림 응답과 파싱 오류는 throw — 호출측이
   단발(non-stream) 폴백 경로로 전환할 수 있게 한다. */

export type SseStreamRequestOptions<T> = {
  method?: string;
  headers?: Record<string, string>;
  body?: BodyInit | null;
  signal?: AbortSignal;
  parse?: (raw: string) => T;
  onOpen?: () => void;
  onMessage: (payload: T, raw: string) => void;
};

export async function readSseStream<T = unknown>(
  url: string,
  options: SseStreamRequestOptions<T>,
): Promise<void> {
  const response = await fetch(url, {
    method: options.method ?? "POST",
    headers: { Accept: "text/event-stream", ...options.headers },
    body: options.body ?? null,
    signal: options.signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`SSE 스트림 연결 실패 (HTTP ${response.status})`);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("text/event-stream")) {
    throw new Error(`SSE가 아닌 응답입니다 (content-type: ${contentType || "없음"})`);
  }

  options.onOpen?.();

  const dispatch = (block: string) => {
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).replace(/^ /, ""))
      .join("\n");
    if (!data) return;
    const payload = options.parse ? options.parse(data) : (JSON.parse(data) as T);
    options.onMessage(payload, data);
  };

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      // CRLF 정규화 — 청크 경계에서 \r/\n이 갈라져도 누적 버퍼 치환으로 복원된다.
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, "\n");

      let sep = buffer.indexOf("\n\n");
      while (sep !== -1) {
        dispatch(buffer.slice(0, sep));
        buffer = buffer.slice(sep + 2);
        sep = buffer.indexOf("\n\n");
      }
    }
    // 종결 빈 줄 없이 닫힌 서버 대응 — 잔여 버퍼의 data 프레임도 플러시.
    buffer += decoder.decode();
    if (buffer.trim()) dispatch(buffer);
  } finally {
    try {
      await reader.cancel();
    } catch {
      /* noop: 이미 닫힌 스트림 */
    }
  }
}
