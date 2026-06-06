"use client";

/**
 * Phase 1-H — 소셜 네트워크(친구·단톡·푸시·다중톡) UI.
 *
 * 백엔드 계약(_workspace/58 §7, prefix /api/v1/social): 전역 토큰(get_current_user) →
 * 일반 apiClient(Authorization Bearer)로 REST 호출(site_token 불필요).
 *
 * 구성(서브뷰):
 *   - 친구: 검색→요청, 받은 요청 수락/거절, 친구 목록, 차단. 연락처 비노출(이름만).
 *   - 단톡 목록: 내 방·마지막 메시지·안읽음 배지. 방 생성(친구 다중선택→direct/group).
 *   - 채팅방: 타임라인(과거 페이지네이션 before), 입력·전송(text/이미지 media_urls),
 *             WS 실시간 수신(READY/MESSAGE), 읽음처리(read last_message_id), 멤버초대.
 *   - 다중톡: 친구/방 다중선택 broadcast(consent·야간 force_night 가드 사유 표시).
 *
 * 실시간: lib/socialWs(단일 공유 연결, PING/SUBSCRIBE, 자동재연결, 언마운트 cleanup).
 * 미디어: ImageUpload(/uploads/image) public URL → messages.media_urls[].
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { ImageUpload } from "@/components/ui/ImageUpload";
import { connectSocialWs, type SocialWsEvent, type SocialWsStatus, type SocialWsHandle } from "@/lib/socialWs";
import { registerSocialPush } from "@/lib/socialPush";

// ── 타입(백엔드 §7 정합) ────────────────────────────────────────────
type FriendStatus = "pending" | "accepted" | "blocked";
type Relation = "friend" | "incoming" | "outgoing" | "none";

interface Friend {
  friendship_id: string;
  user_id: string;
  name: string;
  status: FriendStatus;
  direction: "incoming" | "outgoing";
  created_at?: string;
}
interface SearchResult {
  user_id: string;
  name: string;
  relation: Relation;
}
interface LastMessage {
  id?: string;
  body?: string | null;
  kind?: string;
  sender_user_id?: string | null;
  created_at?: string;
}
interface Room {
  room_id: string;
  kind: "direct" | "group";
  title?: string | null;
  site_id?: string | null;
  last_read_message_id?: string | null;
  last_message?: LastMessage | null;
  unread_count?: number;
  created_at?: string;
}
interface ChatMessage {
  id: string;
  room_id: string;
  sender_user_id?: string | null;
  body?: string | null;
  media_urls?: string[];
  kind?: string;
  created_at?: string;
}
interface CurrentUser {
  id: string;
  name?: string;
}

type View = "rooms" | "friends" | "chat" | "broadcast";

// ── 공통 클래스 ──
const INPUT_CLS =
  "w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none";
const TAB_BTN = (active: boolean) =>
  `rounded-lg px-3.5 py-1.5 text-sm font-bold transition ${
    active
      ? "bg-[var(--accent-strong)] text-white"
      : "border border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
  }`;

function fmtTime(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function SocialPanel() {
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [view, setView] = useState<View>("rooms");
  const [wsStatus, setWsStatus] = useState<SocialWsStatus>("closed");

  // 방 목록(전역 안읽음 합계 배지에도 사용)
  const [rooms, setRooms] = useState<Room[]>([]);
  const [roomsLoading, setRoomsLoading] = useState(true);
  const [activeRoom, setActiveRoom] = useState<Room | null>(null);

  // 실시간 수신 이벤트를 자식들이 구독할 수 있도록 공유.
  const wsRef = useRef<SocialWsHandle | null>(null);
  const [lastEvent, setLastEvent] = useState<SocialWsEvent | null>(null);

  useEffect(() => {
    apiClient
      .get<CurrentUser>("/auth/me")
      .then((u) => setMe(u))
      .catch(() => setMe(null));
  }, []);

  const loadRooms = useCallback(() => {
    apiClient
      .get<{ rooms: Room[] }>("/social/rooms")
      .then((r) => setRooms(r?.rooms ?? []))
      .catch(() => {
        /* 빈 목록 유지 */
      })
      .finally(() => setRoomsLoading(false));
  }, []);

  useEffect(() => {
    loadRooms();
  }, [loadRooms]);

  // 푸시 등록(앱 진입 시 1회·실패 무해).
  useEffect(() => {
    void registerSocialPush();
  }, []);

  // WS 단일 공유 연결 — 언마운트 시 close(cleanup).
  useEffect(() => {
    const handle = connectSocialWs(
      (ev) => {
        setLastEvent(ev);
        // 새 메시지 → 방 목록 갱신(마지막 메시지·안읽음수). 활성방이면 read는 ChatRoom이 처리.
        if (ev.type === "MESSAGE" || ev.type === "SYSTEM") {
          loadRooms();
        }
      },
      (s) => setWsStatus(s),
    );
    wsRef.current = handle;
    return () => {
      handle.close();
      wsRef.current = null;
    };
  }, [loadRooms]);

  const totalUnread = rooms.reduce((n, r) => n + (r.unread_count ?? 0), 0);

  const openRoom = (room: Room) => {
    setActiveRoom(room);
    wsRef.current?.subscribeRoom(room.room_id);
    setView("chat");
  };

  return (
    <div className="space-y-4">
      {/* 헤더: 뷰 탭 + WS 상태 */}
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={() => setView("rooms")} className={TAB_BTN(view === "rooms")}>
          단톡{totalUnread > 0 && <span className="ml-1 rounded-full bg-rose-500 px-1.5 text-[10px] font-black text-white">{totalUnread}</span>}
        </button>
        <button onClick={() => setView("friends")} className={TAB_BTN(view === "friends")}>
          친구
        </button>
        <button onClick={() => setView("broadcast")} className={TAB_BTN(view === "broadcast")}>
          다중톡
        </button>
        <span className="ml-auto flex items-center gap-1.5 text-[11px] font-bold">
          <span
            className={`h-2 w-2 rounded-full ${
              wsStatus === "open" ? "bg-emerald-400" : wsStatus === "connecting" ? "bg-amber-400 animate-pulse" : "bg-rose-400"
            }`}
          />
          <span className="text-[var(--text-tertiary)]">
            {wsStatus === "open" ? "실시간 연결됨" : wsStatus === "connecting" ? "연결 중..." : "연결 끊김(재연결 시도)"}
          </span>
        </span>
      </div>

      {view === "rooms" && (
        <RoomsView
          rooms={rooms}
          loading={roomsLoading}
          me={me}
          onOpen={openRoom}
          onReload={loadRooms}
        />
      )}

      {view === "friends" && <FriendsView />}

      {view === "broadcast" && <BroadcastView rooms={rooms} />}

      {view === "chat" && activeRoom && me && (
        <ChatRoom
          room={activeRoom}
          me={me}
          lastEvent={lastEvent}
          onBack={() => {
            setView("rooms");
            loadRooms();
          }}
          onActivity={loadRooms}
        />
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// 단톡 목록 + 방 생성
// ════════════════════════════════════════════════════════════════════
function RoomsView({
  rooms,
  loading,
  me,
  onOpen,
  onReload,
}: {
  rooms: Room[];
  loading: boolean;
  me: CurrentUser | null;
  onOpen: (r: Room) => void;
  onReload: () => void;
}) {
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-bold text-[var(--text-primary)]">내 채팅방</p>
        <button
          onClick={() => setCreateOpen((v) => !v)}
          className="rounded-lg border border-[var(--accent-strong)] px-3 py-1.5 text-xs font-black text-[var(--accent-strong)] transition hover:bg-[var(--accent-soft)]"
        >
          {createOpen ? "닫기" : "＋ 새 대화"}
        </button>
      </div>

      {createOpen && (
        <CreateRoomForm
          onCreated={(roomId) => {
            setCreateOpen(false);
            onReload();
            const r: Room = { room_id: roomId, kind: "group", title: null, unread_count: 0 };
            onOpen(r);
          }}
        />
      )}

      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]" />
          ))}
        </div>
      ) : rooms.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--line)] bg-[var(--surface-soft)] px-4 py-10 text-center text-sm text-[var(--text-secondary)]">
          대화방이 없습니다. &lsquo;새 대화&rsquo;로 친구와 단톡을 시작하세요.
        </div>
      ) : (
        <div className="space-y-2">
          {rooms.map((r) => {
            const last = r.last_message;
            const isMine = last?.sender_user_id && me && last.sender_user_id === me.id;
            return (
              <button
                key={r.room_id}
                onClick={() => onOpen(r)}
                className="block w-full rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-4 text-left transition hover:border-[var(--accent-strong)]"
              >
                <div className="flex items-center gap-2">
                  <span className="rounded-md bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">
                    {r.kind === "direct" ? "1:1" : "그룹"}
                  </span>
                  <span className="truncate text-sm font-black text-[var(--text-primary)]">{r.title || "제목 없는 대화"}</span>
                  {(r.unread_count ?? 0) > 0 && (
                    <span className="ml-auto rounded-full bg-rose-500 px-2 py-0.5 text-[10px] font-black text-white">{r.unread_count}</span>
                  )}
                </div>
                {last && (
                  <p className="mt-1.5 line-clamp-1 text-xs text-[var(--text-secondary)]">
                    {isMine && <span className="text-[var(--text-tertiary)]">나: </span>}
                    {last.kind === "image" ? "📷 사진" : last.kind === "system" ? `ⓘ ${last.body ?? ""}` : last.body || ""}
                    {last.created_at && <span className="ml-2 text-[10px] text-[var(--text-hint)]">{fmtTime(last.created_at)}</span>}
                  </p>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** 방 생성: 친구 다중선택 → direct(1명)/group. */
function CreateRoomForm({ onCreated }: { onCreated: (roomId: string) => void }) {
  const [friends, setFriends] = useState<Friend[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    apiClient
      .get<{ friends: Friend[] }>("/social/friends?status=accepted")
      .then((r) => setFriends(r?.friends ?? []))
      .catch(() => setFriends([]));
  }, []);

  const toggle = (uid: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(uid)) next.delete(uid);
      else next.add(uid);
      return next;
    });
  };

  const submit = () => {
    const ids = Array.from(selected);
    if (ids.length === 0) {
      setErr("친구를 1명 이상 선택하세요.");
      return;
    }
    setSaving(true);
    setErr("");
    const kind = ids.length === 1 ? "direct" : "group";
    apiClient
      .post<{ room_id: string }>("/social/rooms", {
        body: { kind, title: title.trim() || undefined, member_user_ids: ids },
      })
      .then((r) => onCreated(r.room_id))
      .catch((e) => setErr(e instanceof ApiClientError ? e.message : "대화방 생성에 실패했습니다."))
      .finally(() => setSaving(false));
  };

  return (
    <div className="space-y-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="대화방 제목(선택, 그룹 권장)" className={INPUT_CLS} />
      <p className="text-xs font-bold text-[var(--text-secondary)]">친구 선택 (1명=1:1, 2명↑=그룹)</p>
      {friends.length === 0 ? (
        <p className="text-xs text-[var(--text-tertiary)]">친구가 없습니다. &lsquo;친구&rsquo; 탭에서 친구를 추가하세요.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {friends.map((f) => (
            <button
              key={f.user_id}
              onClick={() => toggle(f.user_id)}
              className={`rounded-full px-3 py-1.5 text-xs font-bold transition ${
                selected.has(f.user_id)
                  ? "bg-[var(--accent-strong)] text-white"
                  : "border border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-secondary)]"
              }`}
            >
              {f.name}
            </button>
          ))}
        </div>
      )}
      {err && <p className="text-sm font-semibold text-rose-300">{err}</p>}
      <button
        onClick={submit}
        disabled={saving}
        className="w-full rounded-lg bg-[var(--accent-strong)] px-4 py-2.5 text-sm font-black text-white transition hover:opacity-90 disabled:opacity-50"
      >
        {saving ? "생성 중..." : "대화방 만들기"}
      </button>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// 친구: 검색→요청 / 받은 요청 / 친구목록 / 차단
// ════════════════════════════════════════════════════════════════════
function FriendsView() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchErr, setSearchErr] = useState("");

  const [friends, setFriends] = useState<Friend[]>([]);
  const [pending, setPending] = useState<Friend[]>([]);
  const [listErr, setListErr] = useState("");
  const [busyId, setBusyId] = useState("");

  const loadFriends = useCallback(() => {
    Promise.all([
      apiClient.get<{ friends: Friend[] }>("/social/friends?status=accepted").catch(() => ({ friends: [] })),
      apiClient.get<{ friends: Friend[] }>("/social/friends?status=pending").catch(() => ({ friends: [] })),
    ])
      .then(([acc, pend]) => {
        setFriends(acc?.friends ?? []);
        setPending(pend?.friends ?? []);
        setListErr("");
      })
      .catch(() => setListErr("친구 목록을 불러오지 못했습니다."));
  }, []);

  useEffect(() => {
    loadFriends();
  }, [loadFriends]);

  const search = () => {
    if (!q.trim()) return;
    setSearching(true);
    setSearchErr("");
    apiClient
      .get<{ results: SearchResult[] }>(`/social/friends/search?q=${encodeURIComponent(q.trim())}`)
      .then((r) => setResults(r?.results ?? []))
      .catch(() => setSearchErr("검색에 실패했습니다."))
      .finally(() => setSearching(false));
  };

  const sendRequest = (userId: string) => {
    setBusyId(userId);
    apiClient
      .post<{ id: string; status: string }>("/social/friends/request", { body: { addressee_user_id: userId } })
      .then(() => {
        setResults((prev) => prev.map((r) => (r.user_id === userId ? { ...r, relation: "outgoing" } : r)));
        loadFriends();
      })
      .catch(() => setSearchErr("친구 요청에 실패했습니다."))
      .finally(() => setBusyId(""));
  };

  const act = (friendshipId: string, action: "accept" | "reject" | "block") => {
    setBusyId(friendshipId);
    apiClient
      .post<{ id: string; status: string }>(`/social/friends/${friendshipId}/${action}`)
      .then(() => loadFriends())
      .catch(() => setListErr("처리에 실패했습니다."))
      .finally(() => setBusyId(""));
  };

  // 받은 요청만(incoming) 수락/거절 대상.
  const incoming = pending.filter((p) => p.direction === "incoming");
  const outgoing = pending.filter((p) => p.direction === "outgoing");

  return (
    <div className="space-y-5">
      {/* 검색 */}
      <div className="space-y-2">
        <div className="flex gap-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
            placeholder="이름으로 친구 검색"
            className={INPUT_CLS}
          />
          <button
            onClick={search}
            disabled={searching}
            className="shrink-0 rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white transition hover:opacity-90 disabled:opacity-50"
          >
            {searching ? "검색 중" : "검색"}
          </button>
        </div>
        {searchErr && <p className="text-sm font-semibold text-rose-300">{searchErr}</p>}
        {results.length > 0 && (
          <div className="space-y-1.5">
            {results.map((r) => (
              <div key={r.user_id} className="flex items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2">
                <span className="text-sm font-bold text-[var(--text-primary)]">{r.name}</span>
                <span className="ml-auto text-[11px]">
                  {r.relation === "friend" ? (
                    <span className="text-emerald-300">친구</span>
                  ) : r.relation === "outgoing" ? (
                    <span className="text-[var(--text-tertiary)]">요청됨</span>
                  ) : r.relation === "incoming" ? (
                    <span className="text-amber-300">요청 받음</span>
                  ) : (
                    <button
                      onClick={() => sendRequest(r.user_id)}
                      disabled={busyId === r.user_id}
                      className="rounded-lg bg-[var(--accent-strong)] px-2.5 py-1 text-[11px] font-black text-white disabled:opacity-50"
                    >
                      친구 요청
                    </button>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}
        <p className="text-[10px] text-[var(--text-hint)]">ⓘ 검색은 이름만 표시되며 연락처·이메일은 노출되지 않습니다.</p>
      </div>

      {listErr && <p className="text-sm font-semibold text-rose-300">{listErr}</p>}

      {/* 받은 요청 */}
      {incoming.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-bold text-[var(--text-primary)]">받은 친구 요청 ({incoming.length})</p>
          {incoming.map((f) => (
            <div key={f.friendship_id} className="flex items-center gap-2 rounded-xl border border-amber-400/30 bg-amber-500/5 px-3 py-2">
              <span className="text-sm font-bold text-[var(--text-primary)]">{f.name}</span>
              <div className="ml-auto flex gap-1.5">
                <button
                  onClick={() => act(f.friendship_id, "accept")}
                  disabled={busyId === f.friendship_id}
                  className="rounded-lg bg-[var(--accent-strong)] px-2.5 py-1 text-[11px] font-black text-white disabled:opacity-50"
                >
                  수락
                </button>
                <button
                  onClick={() => act(f.friendship_id, "reject")}
                  disabled={busyId === f.friendship_id}
                  className="rounded-lg border border-[var(--line)] px-2.5 py-1 text-[11px] font-bold text-[var(--text-secondary)] disabled:opacity-50"
                >
                  거절
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 보낸 요청(대기) */}
      {outgoing.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-bold text-[var(--text-primary)]">보낸 요청 (대기 중)</p>
          {outgoing.map((f) => (
            <div key={f.friendship_id} className="flex items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2">
              <span className="text-sm text-[var(--text-secondary)]">{f.name}</span>
              <span className="ml-auto text-[11px] text-[var(--text-tertiary)]">수락 대기</span>
            </div>
          ))}
        </div>
      )}

      {/* 친구 목록 */}
      <div className="space-y-2">
        <p className="text-sm font-bold text-[var(--text-primary)]">내 친구 ({friends.length})</p>
        {friends.length === 0 ? (
          <p className="text-xs text-[var(--text-tertiary)]">아직 친구가 없습니다.</p>
        ) : (
          friends.map((f) => (
            <div key={f.friendship_id} className="flex items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2">
              <span className="text-sm font-bold text-[var(--text-primary)]">{f.name}</span>
              <button
                onClick={() => act(f.friendship_id, "block")}
                disabled={busyId === f.friendship_id}
                className="ml-auto rounded-lg border border-rose-400/40 px-2.5 py-1 text-[11px] font-bold text-rose-300 transition hover:bg-rose-500/10 disabled:opacity-50"
              >
                차단
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// 채팅방: 타임라인·페이지네이션(before)·전송(text/이미지)·WS실시간·읽음·초대
// ════════════════════════════════════════════════════════════════════
function ChatRoom({
  room,
  me,
  lastEvent,
  onBack,
  onActivity,
}: {
  room: Room;
  me: CurrentUser;
  lastEvent: SocialWsEvent | null;
  onBack: () => void;
  onActivity: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState("");
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState("");

  const [mediaUrl, setMediaUrl] = useState("");
  const [mediaOpen, setMediaOpen] = useState(false);

  const [inviteOpen, setInviteOpen] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const lastReadSentRef = useRef<string>("");

  // 초기 로드(최신 페이지). 방 전환 시 스켈레톤(loading) 표시 후 조회.
  // setState는 effect 본문이 아닌 microtask/콜백에서 호출(cascading render 방지).
  useEffect(() => {
    let alive = true;
    Promise.resolve().then(() => {
      if (alive) setLoading(true);
    });
    apiClient
      .get<{ messages: ChatMessage[]; next_before: string | null }>(`/social/rooms/${room.room_id}/messages?limit=30`)
      .then((r) => {
        if (!alive) return;
        setMessages(r?.messages ?? []);
        setNextBefore(r?.next_before ?? null);
        setLoadErr("");
      })
      .catch(() => {
        if (alive) setLoadErr("메시지를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [room.room_id]);

  // 초기 로드 후 하단 스크롤.
  useEffect(() => {
    if (!loading && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [loading]);

  // 읽음 처리 — 가장 최신 메시지 ID로 read 호출(중복 송신 방지).
  const markRead = useCallback(
    (lastId: string) => {
      if (!lastId || lastReadSentRef.current === lastId) return;
      lastReadSentRef.current = lastId;
      apiClient
        .post<{ room_id: string; last_read_message_id: string }>(`/social/rooms/${room.room_id}/read`, {
          body: { last_message_id: lastId },
        })
        .then(() => onActivity())
        .catch(() => {
          /* 무해: 다음 메시지 수신 시 재시도 */
        });
    },
    [room.room_id, onActivity],
  );

  // 메시지 목록 변경 시 마지막 메시지 읽음 처리.
  useEffect(() => {
    if (messages.length === 0) return;
    const last = messages[messages.length - 1];
    if (last?.id) markRead(last.id);
  }, [messages, markRead]);

  // WS 실시간 수신 — 이 방 MESSAGE면 append + 하단 스크롤.
  // setState는 effect 본문이 아닌 microtask 콜백에서 호출(cascading render 방지).
  useEffect(() => {
    if (!lastEvent) return;
    if (lastEvent.type !== "MESSAGE" || (lastEvent as { room_id?: string }).room_id !== room.room_id) return;
    const m = (lastEvent as { message?: ChatMessage }).message;
    if (!m?.id) return;
    let alive = true;
    Promise.resolve().then(() => {
      if (!alive) return;
      setMessages((prev) => {
        if (prev.some((x) => x.id === m.id)) return prev;
        return [...prev, m];
      });
      requestAnimationFrame(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      });
    });
    return () => {
      alive = false;
    };
  }, [lastEvent, room.room_id]);

  const loadOlder = () => {
    if (!nextBefore || loadingMore) return;
    setLoadingMore(true);
    const el = scrollRef.current;
    const prevHeight = el?.scrollHeight ?? 0;
    apiClient
      .get<{ messages: ChatMessage[]; next_before: string | null }>(
        `/social/rooms/${room.room_id}/messages?limit=30&before=${encodeURIComponent(nextBefore)}`,
      )
      .then((r) => {
        const older = r?.messages ?? [];
        setMessages((prev) => {
          const ids = new Set(prev.map((m) => m.id));
          const merged = older.filter((m) => !ids.has(m.id));
          return [...merged, ...prev];
        });
        setNextBefore(r?.next_before ?? null);
        // 스크롤 위치 보존(상단 추가분만큼 보정).
        requestAnimationFrame(() => {
          if (el) el.scrollTop = el.scrollHeight - prevHeight;
        });
      })
      .catch(() => {
        /* 무해 */
      })
      .finally(() => setLoadingMore(false));
  };

  const doSend = (body: string, kind: "text" | "image", media?: string[]) => {
    setSending(true);
    setSendErr("");
    apiClient
      .post<{ message_id: string }>(`/social/rooms/${room.room_id}/messages`, {
        body: { body: body || undefined, media_urls: media, kind },
      })
      .then(() => {
        // 본인 메시지는 WS 에코 또는 다음 갱신으로 반영. 즉시성 위해 목록 재조회.
        return apiClient.get<{ messages: ChatMessage[]; next_before: string | null }>(
          `/social/rooms/${room.room_id}/messages?limit=30`,
        );
      })
      .then((r) => {
        setMessages(r?.messages ?? []);
        setNextBefore(r?.next_before ?? null);
        requestAnimationFrame(() => {
          if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        });
        onActivity();
      })
      .catch((e) => setSendErr(e instanceof ApiClientError ? e.message : "전송에 실패했습니다."))
      .finally(() => setSending(false));
  };

  const sendText = () => {
    if (!text.trim()) return;
    const body = text.trim();
    setText("");
    doSend(body, "text");
  };

  const sendImage = () => {
    if (!mediaUrl) return;
    const url = mediaUrl;
    setMediaUrl("");
    setMediaOpen(false);
    doSend("", "image", [url]);
  };

  return (
    <div className="flex h-[70vh] flex-col space-y-3">
      <div className="flex items-center gap-2">
        <button onClick={onBack} className="text-sm text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">
          ← 목록
        </button>
        <span className="truncate text-sm font-black text-[var(--text-primary)]">{room.title || (room.kind === "direct" ? "1:1 대화" : "그룹 대화")}</span>
        <button
          onClick={() => setInviteOpen((v) => !v)}
          className="ml-auto rounded-lg border border-[var(--line)] px-2.5 py-1 text-[11px] font-bold text-[var(--text-secondary)] transition hover:text-[var(--text-primary)]"
        >
          ＋ 초대
        </button>
      </div>

      {inviteOpen && (
        <InviteForm
          roomId={room.room_id}
          onDone={() => {
            setInviteOpen(false);
            onActivity();
          }}
        />
      )}

      {/* 타임라인 */}
      <div
        ref={scrollRef}
        className="flex-1 space-y-2 overflow-y-auto rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3"
      >
        {loading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded-xl bg-[var(--surface-strong)]" />
            ))}
          </div>
        ) : loadErr ? (
          <p className="text-sm font-semibold text-rose-300">{loadErr}</p>
        ) : messages.length === 0 ? (
          <p className="py-8 text-center text-sm text-[var(--text-tertiary)]">첫 메시지를 보내보세요.</p>
        ) : (
          <>
            {nextBefore && (
              <button
                onClick={loadOlder}
                disabled={loadingMore}
                className="mx-auto block rounded-full border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-1 text-[11px] font-bold text-[var(--text-secondary)] disabled:opacity-50"
              >
                {loadingMore ? "불러오는 중..." : "이전 메시지 더 보기"}
              </button>
            )}
            {messages.map((m) => {
              if (m.kind === "system") {
                return (
                  <p key={m.id} className="my-1 text-center text-[11px] text-[var(--text-hint)]">
                    ⓘ {m.body}
                  </p>
                );
              }
              const mine = m.sender_user_id === me.id;
              return (
                <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[78%] px-3 py-2 ${
                      mine
                        ? "sa-bubble-me rounded-2xl rounded-br-md bg-[var(--accent-strong)] text-white"
                        : "rounded-2xl rounded-bl-md border border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-primary)]"
                    }`}
                  >
                    {(m.media_urls?.length ?? 0) > 0 && (
                      <div className="mb-1 space-y-1">
                        {m.media_urls!.map((u) => (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img key={u} src={u} alt="첨부 이미지" className="max-h-60 rounded-lg object-cover" />
                        ))}
                      </div>
                    )}
                    {m.body && <p className="whitespace-pre-wrap break-words text-sm">{m.body}</p>}
                    <p className={`mt-0.5 text-[10px] ${mine ? "text-white/70" : "text-[var(--text-hint)]"}`}>{fmtTime(m.created_at)}</p>
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>

      {/* 미디어 업로드(토글) */}
      {mediaOpen && (
        <div className="space-y-2 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
          <ImageUpload value={mediaUrl} onChange={setMediaUrl} label="사진을 클릭하거나 드래그하여 업로드" />
          <div className="flex gap-2">
            <button
              onClick={sendImage}
              disabled={!mediaUrl || sending}
              className="flex-1 rounded-lg bg-[var(--accent-strong)] px-3 py-2 text-sm font-black text-white disabled:opacity-50"
            >
              {sending ? "전송 중..." : "사진 전송"}
            </button>
            <button
              onClick={() => {
                setMediaOpen(false);
                setMediaUrl("");
              }}
              className="rounded-lg border border-[var(--line)] px-3 py-2 text-sm font-bold text-[var(--text-secondary)]"
            >
              취소
            </button>
          </div>
        </div>
      )}

      {sendErr && <p className="text-sm font-semibold text-rose-300">{sendErr}</p>}

      {/* 입력 — 모바일 하단 고정(세이프에어리어)·터치타깃 ≥44px */}
      <div className="sa-chatbar flex items-center gap-2 pt-1">
        <button
          onClick={() => setMediaOpen((v) => !v)}
          className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-[var(--line)] text-lg text-[var(--text-secondary)] transition hover:border-[var(--accent-strong)] hover:text-[var(--text-primary)]"
          title="사진 첨부"
          aria-label="사진 첨부"
        >
          📷
        </button>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              sendText();
            }
          }}
          placeholder="메시지 입력"
          aria-label="메시지 입력"
          className={INPUT_CLS}
        />
        <button
          onClick={sendText}
          disabled={sending || !text.trim()}
          className="grid h-11 shrink-0 place-items-center rounded-xl bg-[var(--accent-strong)] px-4 text-sm font-black text-white transition hover:opacity-90 disabled:opacity-50"
        >
          전송
        </button>
      </div>
    </div>
  );
}

/** 멤버 초대: 친구 다중선택 → invite. */
function InviteForm({ roomId, onDone }: { roomId: string; onDone: () => void }) {
  const [friends, setFriends] = useState<Friend[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    apiClient
      .get<{ friends: Friend[] }>("/social/friends?status=accepted")
      .then((r) => setFriends(r?.friends ?? []))
      .catch(() => setFriends([]));
  }, []);

  const toggle = (uid: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(uid)) next.delete(uid);
      else next.add(uid);
      return next;
    });
  };

  const submit = () => {
    const ids = Array.from(selected);
    if (ids.length === 0) {
      setErr("초대할 친구를 선택하세요.");
      return;
    }
    setSaving(true);
    setErr("");
    apiClient
      .post<{ room_id: string; added_user_ids: string[] }>(`/social/rooms/${roomId}/invite`, { body: { user_ids: ids } })
      .then(() => onDone())
      .catch((e) => setErr(e instanceof ApiClientError ? e.message : "초대에 실패했습니다."))
      .finally(() => setSaving(false));
  };

  return (
    <div className="space-y-2 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
      {friends.length === 0 ? (
        <p className="text-xs text-[var(--text-tertiary)]">초대 가능한 친구가 없습니다.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {friends.map((f) => (
            <button
              key={f.user_id}
              onClick={() => toggle(f.user_id)}
              className={`rounded-full px-3 py-1.5 text-xs font-bold transition ${
                selected.has(f.user_id) ? "bg-[var(--accent-strong)] text-white" : "border border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-secondary)]"
              }`}
            >
              {f.name}
            </button>
          ))}
        </div>
      )}
      {err && <p className="text-sm font-semibold text-rose-300">{err}</p>}
      <button
        onClick={submit}
        disabled={saving}
        className="w-full rounded-lg bg-[var(--accent-strong)] px-3 py-2 text-sm font-black text-white disabled:opacity-50"
      >
        {saving ? "초대 중..." : "선택 친구 초대"}
      </button>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// 다중톡(broadcast): 친구/방 다중선택 + consent·야간 가드
// ════════════════════════════════════════════════════════════════════
function BroadcastView({ rooms }: { rooms: Room[] }) {
  const [mode, setMode] = useState<"friends" | "room">("friends");
  const [friends, setFriends] = useState<Friend[]>([]);
  const [selectedFriends, setSelectedFriends] = useState<Set<string>>(new Set());
  const [roomId, setRoomId] = useState("");
  const [body, setBody] = useState("");
  const [consent, setConsent] = useState(false);
  const [forceNight, setForceNight] = useState(false);
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState("");
  const [result, setResult] = useState<string>("");

  useEffect(() => {
    apiClient
      .get<{ friends: Friend[] }>("/social/friends?status=accepted")
      .then((r) => setFriends(r?.friends ?? []))
      .catch(() => setFriends([]));
  }, []);

  // 야간(21~08시 local) 안내.
  const hour = new Date().getHours();
  const isNight = hour >= 21 || hour < 8;

  const toggleFriend = (uid: string) => {
    setSelectedFriends((prev) => {
      const next = new Set(prev);
      if (next.has(uid)) next.delete(uid);
      else next.add(uid);
      return next;
    });
  };

  const submit = () => {
    if (!body.trim()) {
      setErr("보낼 내용을 입력하세요.");
      return;
    }
    if (!consent) {
      setErr("수신자 동의를 확인해야 발송할 수 있습니다.");
      return;
    }
    const payload: Record<string, unknown> = { body: body.trim(), consent: true };
    if (forceNight) payload.force_night = true;
    if (mode === "friends") {
      const ids = Array.from(selectedFriends);
      if (ids.length === 0) {
        setErr("발송할 친구를 선택하세요.");
        return;
      }
      payload.user_ids = ids;
    } else {
      if (!roomId) {
        setErr("발송할 대화방을 선택하세요.");
        return;
      }
      payload.room_id = roomId;
    }
    setSending(true);
    setErr("");
    setResult("");
    apiClient
      .post<{ targets: number; alimtalk_sent: number; alimtalk_skipped: number; push: { sent: number; skipped: number; failed: number } }>(
        "/social/broadcast",
        { body: payload },
      )
      .then((r) => {
        setResult(
          `대상 ${r.targets}명 · 알림톡 발송 ${r.alimtalk_sent}/스킵 ${r.alimtalk_skipped} · 푸시 발송 ${r.push?.sent ?? 0}/스킵 ${r.push?.skipped ?? 0}/실패 ${r.push?.failed ?? 0}`,
        );
        setBody("");
      })
      .catch((e) => {
        if (e instanceof ApiClientError) {
          if (e.status === 400) setErr("수신자 동의가 확인되지 않았습니다(consent).");
          else if (e.status === 403) setErr("야간(21~08시) 발송은 차단됩니다. '야간 강제 발송'에 동의 시 발송됩니다.");
          else setErr(e.message || "발송에 실패했습니다.");
        } else {
          setErr("발송에 실패했습니다.");
        }
      })
      .finally(() => setSending(false));
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <button onClick={() => setMode("friends")} className={TAB_BTN(mode === "friends")}>
          친구 다중선택
        </button>
        <button onClick={() => setMode("room")} className={TAB_BTN(mode === "room")}>
          대화방 전체
        </button>
      </div>

      {mode === "friends" ? (
        friends.length === 0 ? (
          <p className="text-xs text-[var(--text-tertiary)]">친구가 없습니다. 친구에게만 발송할 수 있습니다(무단발송 차단).</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {friends.map((f) => (
              <button
                key={f.user_id}
                onClick={() => toggleFriend(f.user_id)}
                className={`rounded-full px-3 py-1.5 text-xs font-bold transition ${
                  selectedFriends.has(f.user_id) ? "bg-[var(--accent-strong)] text-white" : "border border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-secondary)]"
                }`}
              >
                {f.name}
              </button>
            ))}
          </div>
        )
      ) : (
        <select value={roomId} onChange={(e) => setRoomId(e.target.value)} className={INPUT_CLS}>
          <option value="">대화방 선택</option>
          {rooms.map((r) => (
            <option key={r.room_id} value={r.room_id}>
              {r.title || (r.kind === "direct" ? "1:1 대화" : "그룹 대화")}
            </option>
          ))}
        </select>
      )}

      <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={4} placeholder="다중 발송할 내용" className={INPUT_CLS} />

      <label className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        수신자가 메시지 수신에 동의했음을 확인합니다(미동의 발송 시 차단).
      </label>

      {isNight && (
        <label className="flex items-center gap-2 rounded-lg border border-amber-400/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-300">
          <input type="checkbox" checked={forceNight} onChange={(e) => setForceNight(e.target.checked)} />
          현재 야간 시간(21~08시)입니다. 부득이한 경우에만 야간 강제 발송에 동의합니다.
        </label>
      )}

      {err && <p className="text-sm font-semibold text-rose-300">{err}</p>}
      {result && <p className="text-sm font-semibold text-emerald-300">{result}</p>}

      <button
        onClick={submit}
        disabled={sending}
        className="w-full rounded-lg bg-[var(--accent-strong)] px-4 py-2.5 text-sm font-black text-white transition hover:opacity-90 disabled:opacity-50"
      >
        {sending ? "발송 중..." : "다중 발송"}
      </button>
      <p className="text-[10px] text-[var(--text-hint)]">ⓘ 친구(수락된 관계)에게만 발송됩니다. 미동의·야간 발송은 정책상 차단될 수 있습니다.</p>
    </div>
  );
}
