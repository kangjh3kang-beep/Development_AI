"use client";

/**
 * Phase 1-E — 공통 구인구직 마켓 패널(PUBLIC, 현장 무관·전역 토큰).
 *
 * - 목록·검색·필터: kind 탭(구인/구직/현장홍보/대행모집)·지역·전문분야·키워드(q).
 * - 공고 작성(kind별 폼) + 프로필 원클릭 불러오기(저장된 profile_id 참조).
 * - 공고 상세 + 신청(apply: 프로필 불러오기 + 메시지).
 * - (작성자) 신청자 목록 + 수락/거절(decide).
 *
 * 일반 apiClient(Authorization Bearer만)로 /market/posts* 호출(salesApi 아님, X-Site-Token 불필요).
 * 백엔드 계약(_workspace/54 §7)과 필드명 정합.
 */
import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiClientError } from "@/lib/api-client";

type Kind = "hire" | "seek" | "promote_site" | "recruit_agency";

const KIND_LABEL: Record<Kind, string> = {
  hire: "구인",
  seek: "구직",
  promote_site: "현장 홍보",
  recruit_agency: "대행 모집",
};

interface Post {
  id: string;
  author_user_id: string;
  kind: Kind;
  title: string;
  body?: string;
  region?: string;
  specialty?: string[];
  site_id?: string;
  contact_method?: string;
  status?: string;
  created_at?: string;
}

interface Application {
  id: string;
  applicant_user_id: string;
  profile_personal_id?: string;
  profile_company_id?: string;
  message?: string;
  status?: string;
  created_at?: string;
  applicant_name?: string;
  applicant_email?: string;
}

interface CurrentUser {
  id: string;
  name?: string;
}

export default function JobMarketPanel() {
  const [me, setMe] = useState<CurrentUser | null>(null);

  // 목록/필터
  const [kind, setKind] = useState<Kind>("hire");
  const [region, setRegion] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [q, setQ] = useState("");
  const [items, setItems] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [listErr, setListErr] = useState("");

  // 상세
  const [selected, setSelected] = useState<Post | null>(null);

  // 작성 폼
  const [composeOpen, setComposeOpen] = useState(false);

  useEffect(() => {
    apiClient
      .get<CurrentUser>("/auth/me")
      .then((u) => setMe(u))
      .catch(() => setMe(null));
  }, []);

  const loadList = useCallback(() => {
    const params = new URLSearchParams({ kind, status: "open", limit: "50" });
    if (region.trim()) params.set("region", region.trim());
    if (specialty.trim()) params.set("specialty", specialty.trim());
    if (q.trim()) params.set("q", q.trim());
    apiClient
      .get<{ items: Post[]; count: number }>(`/market/posts?${params.toString()}`)
      .then((r) => {
        setItems(r?.items ?? []);
        setListErr("");
      })
      .catch(() => setListErr("공고 목록을 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, [kind, region, specialty, q]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  if (selected) {
    return (
      <PostDetail
        post={selected}
        me={me}
        onBack={() => {
          setSelected(null);
          loadList();
        }}
      />
    );
  }

  return (
    <div className="space-y-4">
      {/* kind 탭 */}
      <div className="flex flex-wrap gap-2">
        {(Object.keys(KIND_LABEL) as Kind[]).map((k) => (
          <button
            key={k}
            onClick={() => setKind(k)}
            className={`rounded-lg px-3.5 py-1.5 text-sm font-bold transition ${
              kind === k
                ? "bg-[var(--accent-strong)] text-white"
                : "border border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {KIND_LABEL[k]}
          </button>
        ))}
        <button
          onClick={() => setComposeOpen((v) => !v)}
          className="ml-auto rounded-lg border border-[var(--accent-strong)] px-3 py-1.5 text-xs font-black text-[var(--accent-strong)] transition hover:bg-[var(--accent-soft)]"
        >
          {composeOpen ? "작성 닫기" : "＋ 공고 작성"}
        </button>
      </div>

      {composeOpen && (
        <ComposeForm
          defaultKind={kind}
          onCreated={() => {
            setComposeOpen(false);
            loadList();
          }}
        />
      )}

      {/* 필터 */}
      <div className="grid gap-2 sm:grid-cols-3">
        <input
          value={region}
          onChange={(e) => setRegion(e.target.value)}
          placeholder="지역"
          className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none"
        />
        <input
          value={specialty}
          onChange={(e) => setSpecialty(e.target.value)}
          placeholder="전문 분야"
          className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none"
        />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="키워드 검색"
          className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none"
        />
      </div>

      {listErr && <p className="text-sm font-semibold text-rose-300">{listErr}</p>}

      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--line)] bg-[var(--surface-soft)] px-4 py-10 text-center text-sm text-[var(--text-secondary)]">
          등록된 {KIND_LABEL[kind]} 공고가 없습니다.
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((p) => (
            <button
              key={p.id}
              onClick={() => setSelected(p)}
              className="block w-full rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-4 text-left transition hover:border-[var(--accent-strong)]"
            >
              <div className="flex items-center gap-2">
                <span className="rounded-md bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">
                  {KIND_LABEL[p.kind]}
                </span>
                {p.region && <span className="text-[11px] text-[var(--text-tertiary)]">{p.region}</span>}
                {p.author_user_id === me?.id && (
                  <span className="rounded-md bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-300">내 공고</span>
                )}
              </div>
              <p className="mt-1.5 text-sm font-black text-[var(--text-primary)]">{p.title}</p>
              {p.body && <p className="mt-1 line-clamp-2 text-xs text-[var(--text-secondary)]">{p.body}</p>}
              {(p.specialty?.length ?? 0) > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {p.specialty!.map((s) => (
                    <span key={s} className="rounded bg-[var(--surface-soft)] px-1.5 py-0.5 text-[10px] text-[var(--text-tertiary)]">
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** 공고 작성 폼 — kind별 라벨 + 프로필 원클릭 불러오기. */
function ComposeForm({ defaultKind, onCreated }: { defaultKind: Kind; onCreated: () => void }) {
  const [kind, setKind] = useState<Kind>(defaultKind);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [region, setRegion] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [contactMethod, setContactMethod] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [loadingProfile, setLoadingProfile] = useState(false);

  // 저장된 개인 프로필로 구직 공고 자동 채움(원클릭 불러오기).
  const fillFromProfile = () => {
    setLoadingProfile(true);
    setErr("");
    apiClient
      .get<{ exists: boolean; profile?: { region?: string; specialties?: string[]; achievement_summary?: string; desired_conditions?: string; contact?: string } }>(
        "/market/profile/personal",
      )
      .then((r) => {
        if (!r?.exists || !r.profile) {
          setErr("저장된 개인 프로필이 없습니다. 먼저 '내 프로필'에서 작성하세요.");
          return;
        }
        const p = r.profile;
        if (p.region) setRegion(p.region);
        if (p.specialties?.length) setSpecialty(p.specialties.join(", "));
        if (p.contact) setContactMethod(p.contact);
        const parts = [p.achievement_summary, p.desired_conditions].filter(Boolean);
        if (parts.length) setBody((prev) => (prev ? prev : parts.join("\n\n")));
      })
      .catch(() => setErr("프로필을 불러오지 못했습니다."))
      .finally(() => setLoadingProfile(false));
  };

  const submit = () => {
    if (!title.trim()) {
      setErr("제목을 입력하세요.");
      return;
    }
    setSaving(true);
    setErr("");
    apiClient
      .post<{ post: Post }>("/market/posts", {
        body: {
          kind,
          title: title.trim(),
          body: body.trim(),
          region: region.trim(),
          specialty: specialty.split(",").map((s) => s.trim()).filter(Boolean),
          contact_method: contactMethod.trim(),
        },
      })
      .then(() => onCreated())
      .catch((e) => setErr(e instanceof ApiClientError ? e.message : "공고 등록에 실패했습니다."))
      .finally(() => setSaving(false));
  };

  return (
    <div className="space-y-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as Kind)}
          className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-sm text-[var(--text-primary)] focus:border-[var(--accent-strong)] focus:outline-none"
        >
          {(Object.keys(KIND_LABEL) as Kind[]).map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL[k]}
            </option>
          ))}
        </select>
        {(kind === "seek" || kind === "recruit_agency") && (
          <button
            type="button"
            onClick={fillFromProfile}
            disabled={loadingProfile}
            className="rounded-lg border border-[var(--accent-strong)] px-2.5 py-1.5 text-xs font-bold text-[var(--accent-strong)] transition hover:bg-[var(--accent-soft)] disabled:opacity-50"
          >
            {loadingProfile ? "불러오는 중..." : "내 프로필 불러오기"}
          </button>
        )}
      </div>

      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder={
          kind === "hire" ? "구인 제목(예: 강남 현장 분양상담 모집)" : kind === "seek" ? "구직 제목(예: 분양영업 경력 5년)" : kind === "promote_site" ? "현장 홍보 제목" : "대행 모집 제목"
        }
        className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none"
      />
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={4}
        placeholder="상세 내용"
        className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none"
      />
      <div className="grid gap-2 sm:grid-cols-3">
        <input value={region} onChange={(e) => setRegion(e.target.value)} placeholder="지역" className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none" />
        <input value={specialty} onChange={(e) => setSpecialty(e.target.value)} placeholder="전문 분야(쉼표 구분)" className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none" />
        <input value={contactMethod} onChange={(e) => setContactMethod(e.target.value)} placeholder="연락 방법" className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none" />
      </div>

      {err && <p className="text-sm font-semibold text-rose-300">{err}</p>}

      <button
        onClick={submit}
        disabled={saving}
        className="w-full rounded-lg bg-[var(--accent-strong)] px-4 py-2.5 text-sm font-black text-white transition hover:opacity-90 disabled:opacity-50"
      >
        {saving ? "등록 중..." : "공고 등록"}
      </button>
    </div>
  );
}

/** 공고 상세 + 신청 + (작성자)신청자 관리. */
function PostDetail({ post, me, onBack }: { post: Post; me: CurrentUser | null; onBack: () => void }) {
  const isAuthor = !!me && post.author_user_id === me.id;

  // 신청(비작성자)
  const [message, setMessage] = useState("");
  const [profileId, setProfileId] = useState("");
  const [applying, setApplying] = useState(false);
  const [applyMsg, setApplyMsg] = useState("");
  const [applyErr, setApplyErr] = useState("");

  // 작성자: 신청자 목록
  const [apps, setApps] = useState<Application[]>([]);
  const [appsLoading, setAppsLoading] = useState(isAuthor);
  const [appsErr, setAppsErr] = useState("");
  const [decidingId, setDecidingId] = useState("");

  const loadApps = useCallback(() => {
    if (!isAuthor) return;
    apiClient
      .get<{ items: Application[]; count: number }>(`/market/posts/${post.id}/applications`)
      .then((r) => {
        setApps(r?.items ?? []);
        setAppsErr("");
      })
      .catch(() => setAppsErr("신청자 목록을 불러오지 못했습니다."))
      .finally(() => setAppsLoading(false));
  }, [isAuthor, post.id]);

  useEffect(() => {
    loadApps();
  }, [loadApps]);

  // 신청 시 본인 프로필 id 자동 채움(원클릭 불러오기).
  const loadMyProfileId = () => {
    setApplyErr("");
    apiClient
      .get<{ exists: boolean; profile?: { id?: string } }>("/market/profile/personal")
      .then((r) => {
        if (r?.exists && r.profile?.id) {
          setProfileId(r.profile.id);
          setApplyMsg("프로필을 첨부했습니다.");
        } else {
          setApplyErr("저장된 개인 프로필이 없습니다. '내 프로필'에서 먼저 작성하세요.");
        }
      })
      .catch(() => setApplyErr("프로필을 불러오지 못했습니다."));
  };

  const submitApply = () => {
    setApplying(true);
    setApplyMsg("");
    setApplyErr("");
    apiClient
      .post<{ id: string; status: string }>(`/market/posts/${post.id}/apply`, {
        body: { profile_id: profileId || undefined, message: message.trim() || undefined },
      })
      .then(() => {
        setApplyMsg("신청이 완료되었습니다.");
        setMessage("");
      })
      .catch((e) => setApplyErr(e instanceof ApiClientError ? e.message : "신청에 실패했습니다."))
      .finally(() => setApplying(false));
  };

  const decide = (appId: string, accept: boolean) => {
    setDecidingId(appId);
    apiClient
      .post<{ id: string; status: string; membership_linked?: boolean }>(`/market/applications/${appId}/decide`, {
        body: { accept },
      })
      .then(() => loadApps())
      .catch(() => setAppsErr("처리에 실패했습니다."))
      .finally(() => setDecidingId(""));
  };

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-sm text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">
        ← 목록으로
      </button>

      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-4">
        <div className="flex items-center gap-2">
          <span className="rounded-md bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">
            {KIND_LABEL[post.kind]}
          </span>
          {post.region && <span className="text-[11px] text-[var(--text-tertiary)]">{post.region}</span>}
        </div>
        <h2 className="mt-2 text-base font-black text-[var(--text-primary)]">{post.title}</h2>
        {post.body && <p className="mt-2 whitespace-pre-wrap text-sm text-[var(--text-secondary)]">{post.body}</p>}
        {(post.specialty?.length ?? 0) > 0 && (
          <div className="mt-3 flex flex-wrap gap-1">
            {post.specialty!.map((s) => (
              <span key={s} className="rounded bg-[var(--surface-soft)] px-1.5 py-0.5 text-[10px] text-[var(--text-tertiary)]">
                {s}
              </span>
            ))}
          </div>
        )}
        {post.contact_method && (
          <p className="mt-3 text-xs text-[var(--text-tertiary)]">연락 방법: {post.contact_method}</p>
        )}
        <p className="mt-2 text-[10px] text-[var(--text-hint)]">
          ⓘ 게재 내용은 작성자가 직접 기재한 정보입니다(자기기재).
        </p>
      </div>

      {/* 비작성자: 신청 폼 */}
      {!isAuthor && (
        <div className="space-y-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <p className="text-sm font-bold text-[var(--text-primary)]">신청하기</p>
          <button
            type="button"
            onClick={loadMyProfileId}
            className="rounded-lg border border-[var(--accent-strong)] px-3 py-1.5 text-xs font-bold text-[var(--accent-strong)] transition hover:bg-[var(--accent-soft)]"
          >
            내 프로필 첨부
          </button>
          {profileId && <p className="text-[11px] text-emerald-300">프로필 첨부됨</p>}
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={3}
            placeholder="지원 메시지(선택)"
            className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none"
          />
          {applyErr && <p className="text-sm font-semibold text-rose-300">{applyErr}</p>}
          {applyMsg && <p className="text-sm font-semibold text-emerald-300">{applyMsg}</p>}
          <button
            onClick={submitApply}
            disabled={applying}
            className="w-full rounded-lg bg-[var(--accent-strong)] px-4 py-2.5 text-sm font-black text-white transition hover:opacity-90 disabled:opacity-50"
          >
            {applying ? "신청 중..." : "신청"}
          </button>
        </div>
      )}

      {/* 작성자: 신청자 목록 */}
      {isAuthor && (
        <div className="space-y-3">
          <p className="text-sm font-bold text-[var(--text-primary)]">신청자 ({apps.length})</p>
          {appsErr && <p className="text-sm font-semibold text-rose-300">{appsErr}</p>}
          {appsLoading ? (
            <div className="h-20 animate-pulse rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]" />
          ) : apps.length === 0 ? (
            <p className="text-sm text-[var(--text-secondary)]">아직 신청자가 없습니다.</p>
          ) : (
            <div className="space-y-2">
              {apps.map((a) => (
                <div key={a.id} className="rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-bold text-[var(--text-primary)]">{a.applicant_name || a.applicant_email || "지원자"}</span>
                    {a.applicant_email && <span className="text-[11px] text-[var(--text-tertiary)]">{a.applicant_email}</span>}
                    {a.status && a.status !== "applied" && (
                      <span
                        className={`rounded-md px-2 py-0.5 text-[10px] font-bold ${
                          a.status === "accepted" ? "bg-emerald-500/15 text-emerald-300" : "bg-rose-500/15 text-rose-300"
                        }`}
                      >
                        {a.status === "accepted" ? "수락됨" : "거절됨"}
                      </span>
                    )}
                  </div>
                  {a.message && <p className="mt-1.5 whitespace-pre-wrap text-xs text-[var(--text-secondary)]">{a.message}</p>}
                  {a.status === "applied" && (
                    <div className="mt-3 flex gap-2">
                      <button
                        onClick={() => decide(a.id, true)}
                        disabled={decidingId === a.id}
                        className="rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-xs font-black text-white transition hover:opacity-90 disabled:opacity-50"
                      >
                        수락
                      </button>
                      <button
                        onClick={() => decide(a.id, false)}
                        disabled={decidingId === a.id}
                        className="rounded-lg border border-[var(--line)] px-3 py-1.5 text-xs font-bold text-[var(--text-secondary)] transition hover:text-[var(--text-primary)] disabled:opacity-50"
                      >
                        거절
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
