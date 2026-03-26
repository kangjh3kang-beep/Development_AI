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
