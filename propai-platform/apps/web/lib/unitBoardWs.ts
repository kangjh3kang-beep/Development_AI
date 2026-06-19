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
// 인증/인가 거부(영구) 사유 통지 — 상위가 재진입(토큰갱신/현장 비밀번호 재입력)을 안내할 수 있게.
export type AuthErrorReason = "unauthenticated" | "forbidden";
type AuthErrorListener = (reason: AuthErrorReason, code: number) => void;

const PING_INTERVAL_MS = 25_000;
const BACKOFF_MIN_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

// 백엔드 거부 close 코드(ws_routes 계약):
//   4401 = 인증 실패(토큰 없음/위조/만료) — 토큰을 갱신/재발급하기 전엔 재연결해도 동일 거부.
//   4403 = 인가 실패(그 현장 비멤버) — 멤버십이 바뀌기 전엔 재연결해도 동일 거부.
//   4429 = 연결/메시지 throttle 초과 — 일시적이라 지수 백오프로 재시도해야 한다.
const WS_CLOSE_UNAUTHENTICATED = 4401;
const WS_CLOSE_FORBIDDEN = 4403;

export interface UnitBoardWsHandle {
  /** 리스너 해제 + 연결 정리. 언마운트 시 반드시 호출. */
  close: () => void;
  /** 현재 연결 상태 즉시 조회. */
  getStatus: () => UnitBoardWsStatus;
}

/**
 * 현장 보드 채널(board:{siteId})에 구독한다. 인스턴스별 단일 소켓.
 * @param siteId      현장 UUID. WS 채널 board:{siteId} 구독.
 * @param onMessage   UNIT_STATUS 이벤트 수신 콜백.
 * @param onStatus    연결 상태(connecting/open/closed) 변화 콜백(재연결 시 보드 재조회 트리거용).
 * @param onAuthError (선택) 인증(4401)/인가(4403) 영구 거부 시 1회 통지. 이 경우 자동재연결을 멈추므로
 *                    상위는 토큰 갱신/현장 재진입을 안내해야 한다(무한 재연결 폭주 차단).
 */
export function connectUnitBoardWs(
  siteId: string,
  onMessage: MessageListener,
  onStatus?: StatusListener,
  onAuthError?: AuthErrorListener,
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

    ws.onclose = (ev) => {
      if (socket === ws) socket = null;
      clearTimers();
      setStatus("closed");
      // 인증(4401)/인가(4403) 거부는 '영구 사유'다 — 토큰/멤버십이 바뀌기 전엔 재연결해도 똑같이
      // 거부되며, 30s마다 무한 재연결하면 인증·인가 재평가만 폭주(연결 throttle 가치 상쇄)한다.
      // 따라서 재연결을 멈추고 상위에 1회 통지(토큰 갱신/현장 재진입 안내)한다.
      const code = ev?.code;
      if (code === WS_CLOSE_UNAUTHENTICATED || code === WS_CLOSE_FORBIDDEN) {
        manualClose = true; // scheduleReconnect 차단(이후 자동재연결 안 함).
        if (onAuthError) {
          try {
            onAuthError(code === WS_CLOSE_UNAUTHENTICATED ? "unauthenticated" : "forbidden", code);
          } catch {
            /* noop */
          }
        }
        return;
      }
      // 그 외(4429 throttle·1000/1001 정상종료·네트워크 단절 등)는 지수 백오프로 재연결한다.
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
