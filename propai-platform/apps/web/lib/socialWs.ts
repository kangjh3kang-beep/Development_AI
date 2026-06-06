/**
 * Phase 1-H — 소셜 실시간 WebSocket 클라이언트(단일 공유 연결).
 *
 * 백엔드 계약(_workspace/58 §WebSocket):
 *   - 연결: WS /api/v1/social/ws?token={access_jwt} (실패 시 close 4401)
 *   - 서버→클라: {type:"READY",rooms:[...]} / {type:"MESSAGE",room_id,message{...}}
 *                / {type:"SYSTEM",...} / {type:"PONG"}
 *   - 클라→서버: {type:"PING"} / {type:"SUBSCRIBE",room_id}
 *
 * 설계:
 *   - 모듈 싱글톤. 여러 컴포넌트가 connect()로 공유 연결을 사용(중복 소켓 방지).
 *   - 토큰=localStorage propai_access_token, URL=resolveApiOrigin()(http→ws/https→wss).
 *   - PING heartbeat(25s), 지수 백오프 자동재연결(1s→최대 30s).
 *   - 구독자(리스너) 0이 되면 연결 해제(메모리릭/유령소켓 방지).
 *   - subscribeRoom(roomId)로 새 방 즉시 구독(서버 SUBSCRIBE 송신).
 */
import { resolveApiOrigin } from "@/lib/api-client";

export type SocialWsStatus = "connecting" | "open" | "closed";

interface ReadyEvent {
  type: "READY";
  rooms?: string[];
}
interface MessagePayload {
  id: string;
  room_id: string;
  sender_user_id?: string | null;
  body?: string | null;
  media_urls?: string[];
  kind?: string;
  created_at?: string;
}
interface MessageEvent_ {
  type: "MESSAGE";
  room_id: string;
  message: MessagePayload;
}
interface SystemEvent {
  type: "SYSTEM";
  room_id?: string;
  [k: string]: unknown;
}
interface PongEvent {
  type: "PONG";
}

export type SocialWsEvent = ReadyEvent | MessageEvent_ | SystemEvent | PongEvent | { type: string; [k: string]: unknown };

type MessageListener = (ev: SocialWsEvent) => void;
type StatusListener = (s: SocialWsStatus) => void;

const PING_INTERVAL_MS = 25_000;
const BACKOFF_MIN_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

let socket: WebSocket | null = null;
let status: SocialWsStatus = "closed";
let backoff = BACKOFF_MIN_MS;
let pingTimer: ReturnType<typeof setInterval> | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let manualClose = false;
// 재연결 시 다시 구독해야 하는 방(클라가 명시 SUBSCRIBE 한 방). 서버 READY가 기본 내 방을 줌.
const pendingRooms = new Set<string>();

const messageListeners = new Set<MessageListener>();
const statusListeners = new Set<StatusListener>();

function buildWsUrl(): string | null {
  if (typeof window === "undefined") return null;
  let token = "";
  try {
    token = window.localStorage.getItem("propai_access_token")?.trim() ?? "";
  } catch {
    token = "";
  }
  if (!token) return null;
  const origin = resolveApiOrigin();
  const wsOrigin = origin.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
  return `${wsOrigin}/api/v1/social/ws?token=${encodeURIComponent(token)}`;
}

function setStatus(next: SocialWsStatus) {
  if (status === next) return;
  status = next;
  statusListeners.forEach((l) => {
    try {
      l(next);
    } catch {
      /* noop */
    }
  });
}

function clearTimers() {
  if (pingTimer) {
    clearInterval(pingTimer);
    pingTimer = null;
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

function sendRaw(obj: Record<string, unknown>): boolean {
  if (socket && socket.readyState === WebSocket.OPEN) {
    try {
      socket.send(JSON.stringify(obj));
      return true;
    } catch {
      return false;
    }
  }
  return false;
}

function scheduleReconnect() {
  if (manualClose) return;
  if (messageListeners.size === 0 && statusListeners.size === 0) return;
  if (reconnectTimer) return;
  const delay = backoff;
  backoff = Math.min(BACKOFF_MAX_MS, Math.round(backoff * 1.8));
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    openSocket();
  }, delay);
}

function openSocket() {
  if (typeof window === "undefined") return;
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;

  const url = buildWsUrl();
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
    // 명시 구독 방 재구독(재연결 복원).
    pendingRooms.forEach((rid) => sendRaw({ type: "SUBSCRIBE", room_id: rid }));
    clearTimers();
    pingTimer = setInterval(() => sendRaw({ type: "PING" }), PING_INTERVAL_MS);
  };

  ws.onmessage = (evt) => {
    let data: SocialWsEvent;
    try {
      data = JSON.parse(typeof evt.data === "string" ? evt.data : "");
    } catch {
      return;
    }
    if (!data || typeof data.type !== "string") return;
    messageListeners.forEach((l) => {
      try {
        l(data);
      } catch {
        /* noop */
      }
    });
  };

  ws.onerror = () => {
    // onclose가 후속 처리. 여기선 별도 동작 없음(소켓 닫힘 유도).
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
}

function maybeTeardown() {
  if (messageListeners.size > 0 || statusListeners.size > 0) return;
  manualClose = true;
  clearTimers();
  backoff = BACKOFF_MIN_MS;
  pendingRooms.clear();
  if (socket) {
    try {
      socket.close();
    } catch {
      /* noop */
    }
    socket = null;
  }
  setStatus("closed");
}

export interface SocialWsHandle {
  /** 리스너 해제 + (구독자 0이면) 연결 정리. 언마운트 시 반드시 호출. */
  close: () => void;
  /** 현재 상태 즉시 조회. */
  getStatus: () => SocialWsStatus;
  /** 새 방 즉시 구독(서버 SUBSCRIBE). 재연결 시 자동 재구독. */
  subscribeRoom: (roomId: string) => void;
  /** 명시 구독 해제(재연결 재구독 목록에서 제거). 서버는 READY 기본 방 유지. */
  unsubscribeRoom: (roomId: string) => void;
}

/**
 * 공유 WS 연결에 리스너를 붙인다. 첫 구독자가 연결을 연다.
 * @param onMessage 서버 이벤트(READY/MESSAGE/SYSTEM/PONG) 수신 콜백.
 * @param onStatus  연결 상태(connecting/open/closed) 변화 콜백.
 */
export function connectSocialWs(onMessage: MessageListener, onStatus?: StatusListener): SocialWsHandle {
  messageListeners.add(onMessage);
  if (onStatus) {
    statusListeners.add(onStatus);
    // 현재 상태 즉시 통지.
    try {
      onStatus(status);
    } catch {
      /* noop */
    }
  }

  // 첫 연결 트리거(또는 이미 열려있으면 재사용).
  if (!socket) {
    openSocket();
  }

  return {
    close: () => {
      messageListeners.delete(onMessage);
      if (onStatus) statusListeners.delete(onStatus);
      maybeTeardown();
    },
    getStatus: () => status,
    subscribeRoom: (roomId: string) => {
      if (!roomId) return;
      pendingRooms.add(roomId);
      sendRaw({ type: "SUBSCRIBE", room_id: roomId });
    },
    unsubscribeRoom: (roomId: string) => {
      pendingRooms.delete(roomId);
    },
  };
}
