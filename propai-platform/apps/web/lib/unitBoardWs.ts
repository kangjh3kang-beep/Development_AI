/**
 * Phase 1-C — 세대(동호수) 실시간 선점 보드 WebSocket 클라이언트.
 *
 * 백엔드 계약(_workspace/61 §3·§7):
 *   - 연결: WS {origin}/ws/sales/board:{site_id}  (채널형 ws_manager, 채널=board:{site_id})
 *           토큰은 백엔드 미검증이나 ?token={access_jwt} 로 첨부(향후 게이팅 대비).
 *   - 서버→클라: {type:"UNIT_STATUS", event:HOLD|RELEASE|RESERVE, unit_id, status, held_by, expires_at, ts}
 *   - 클라→서버: {type:"PING"}(heartbeat) — 서버 PONG 미보장(채널 broadcast 전용)이라 응답 의존 안 함.
 *
 * 설계(socialWs 패턴 차용):
 *   - 현장(site_id)별 채널 연결이라 모듈 싱글톤이 아닌 인스턴스 핸들로 관리(현장 전환 시 독립 소켓).
 *   - PING heartbeat(25s), 지수 백오프 자동재연결(1s→최대 30s).
 *   - close()로 명시 해제(언마운트 시 반드시 호출 — 유령소켓/메모리릭 방지).
 *   - 재연결 시 보드 재조회를 유도하도록 status open 전이를 상위에 통지.
 */
import { resolveApiOrigin } from "@/lib/api-client";

export type UnitBoardWsStatus = "connecting" | "open" | "closed";

export interface UnitStatusEvent {
  type: "UNIT_STATUS";
  event?: "HOLD" | "RELEASE" | "RESERVE" | string;
  unit_id: string;
  status: string;
  held_by?: string | null;
  expires_at?: string | null;
  ts?: string;
}

export type UnitBoardWsEvent = UnitStatusEvent | { type: string; [k: string]: unknown };

type MessageListener = (ev: UnitBoardWsEvent) => void;
type StatusListener = (s: UnitBoardWsStatus) => void;

const PING_INTERVAL_MS = 25_000;
const BACKOFF_MIN_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

export interface UnitBoardWsHandle {
  /** 리스너 해제 + 연결 정리. 언마운트 시 반드시 호출. */
  close: () => void;
  /** 현재 연결 상태 즉시 조회. */
  getStatus: () => UnitBoardWsStatus;
}

/**
 * 현장 보드 채널(board:{siteId})에 구독한다. 인스턴스별 단일 소켓.
 * @param siteId    현장 UUID. WS 채널 board:{siteId} 구독.
 * @param onMessage UNIT_STATUS 이벤트 수신 콜백.
 * @param onStatus  연결 상태(connecting/open/closed) 변화 콜백(재연결 시 보드 재조회 트리거용).
 */
export function connectUnitBoardWs(
  siteId: string,
  onMessage: MessageListener,
  onStatus?: StatusListener,
): UnitBoardWsHandle {
  let socket: WebSocket | null = null;
  let status: UnitBoardWsStatus = "closed";
  let backoff = BACKOFF_MIN_MS;
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let manualClose = false;

  const setStatus = (next: UnitBoardWsStatus) => {
    if (status === next) return;
    status = next;
    if (onStatus) {
      try {
        onStatus(next);
      } catch {
        /* noop */
      }
    }
  };

  const clearTimers = () => {
    if (pingTimer) {
      clearInterval(pingTimer);
      pingTimer = null;
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  const buildUrl = (): string | null => {
    if (typeof window === "undefined" || !siteId) return null;
    let token = "";
    try {
      token = window.localStorage.getItem("propai_access_token")?.trim() ?? "";
    } catch {
      token = "";
    }
    const origin = resolveApiOrigin();
    const wsOrigin = origin.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
    const q = token ? `?token=${encodeURIComponent(token)}` : "";
    // 채널 식별자 board:{siteId} 는 콜론을 포함하므로 path segment 로 인코딩 첨부.
    return `${wsOrigin}/ws/sales/${encodeURIComponent(`board:${siteId}`)}${q}`;
  };

  const scheduleReconnect = () => {
    if (manualClose) return;
    if (reconnectTimer) return;
    const delay = backoff;
    backoff = Math.min(BACKOFF_MAX_MS, Math.round(backoff * 1.8));
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      open();
    }, delay);
  };

  const sendRaw = (obj: Record<string, unknown>): boolean => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      try {
        socket.send(JSON.stringify(obj));
        return true;
      } catch {
        return false;
      }
    }
    return false;
  };

  const open = () => {
    if (typeof window === "undefined") return;
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;

    const url = buildUrl();
    if (!url) {
      setStatus("closed");
      return;
    }

    manualClose = false;
    setStatus("connecting");

    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      scheduleReconnect();
      return;
    }
    socket = ws;

    ws.onopen = () => {
      backoff = BACKOFF_MIN_MS;
      setStatus("open");
      clearTimers();
      pingTimer = setInterval(() => sendRaw({ type: "PING" }), PING_INTERVAL_MS);
    };

    ws.onmessage = (evt) => {
      let data: UnitBoardWsEvent;
      try {
        data = JSON.parse(typeof evt.data === "string" ? evt.data : "");
      } catch {
        return;
      }
      if (!data || typeof data.type !== "string") return;
      try {
        onMessage(data);
      } catch {
        /* noop */
      }
    };

    ws.onerror = () => {
      try {
        ws.close();
      } catch {
        /* noop */
      }
    };

    ws.onclose = () => {
      if (socket === ws) socket = null;
      clearTimers();
      setStatus("closed");
      scheduleReconnect();
    };
  };

  open();

  return {
    close: () => {
      manualClose = true;
      clearTimers();
      if (socket) {
        try {
          socket.close();
        } catch {
          /* noop */
        }
        socket = null;
      }
      setStatus("closed");
    },
    getStatus: () => status,
  };
}
