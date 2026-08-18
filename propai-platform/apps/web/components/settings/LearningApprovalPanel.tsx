"use client";

/**
 * 자가학습 few-shot 후보 승인 화면(관리자 전용).
 *
 * GET  /growth/learning/candidates → { items, total, ... }  후보 목록(id 포함)
 * POST /growth/learning/promote    → { example_id, status } 사람 승인/거부
 * GET  /growth/learning/dataset    → JSONL 다운로드(활성 학습셋)
 *
 * 【이 화면이 없으면 무슨 일이 벌어졌나 — 2026-08-19 실측】
 * 백엔드는 좋은 분석 사례를 모아 `learning_examples` 에 **status='candidate'** 로만 쌓는다
 * (자동 활성 금지 = 사람 승인 게이트). 그런데 AI 프롬프트에 실제로 들어가는 건
 * **status='active'** 뿐이다. candidate → active 로 바꾸는 방법은 관리자 API 하나뿐인데
 * 그 API 를 부르는 화면이 **하나도 없었다**. 즉 "사람이 승인해야 도는 장치인데 사람에게
 * 문이 없어서" 자가학습이 구조적으로 영원히 비어 있었다. 이 화면이 그 문이다.
 *
 * 【절대 넣지 않는 것 — 일괄/자동 승인】
 * "전체 승인" 같은 버튼은 두지 않는다. 이 설계의 핵심 제약이 "자동 활성 절대 금지"이고,
 * 한 번에 다 켜는 버튼은 사람이 내용을 본다는 전제를 무너뜨려 자동 승인과 사실상 같아진다.
 * 승인/거부는 **항상 한 건씩**, 그 건의 내용을 화면에서 보면서 누른다.
 *
 * 무목업: 실제 API 만 쓴다. 데이터가 없으면 "아직 후보가 쌓이지 않았다"고 정직하게 적는다.
 *
 * 【변이 감사에서 살아남은 것 — 설명해 둔다(2026-08-19)】
 * scripts/mutate_changed.py 로 이 파일을 감사했다. 배선(요청 경로·요청 본문·버튼 핸들러·
 * 페이지 이동·탭 전환·필터)은 전부 죽었다. 남은 생존은 아래 세 갈래이고 전부 표시층이다:
 *   · 클래스명(디자인 토큰)·placeholder·안내 문구 — 바꿔도 동작은 같다.
 *   · use client 지시자·TS 타입 주석·React key — 런타임에 없거나 jsdom 으로 못 잡는다.
 *   · 거부됨 탭의 배지·빈 상태 문구 — 그 탭의 목록 렌더는 아직 회귀망 밖이다(부채).
 * 즉 설명할 수 없는 생존은 없다. 새 로직을 넣으면 이 감사를 다시 돌려라.
 * 문자열·색: 형제 화면(`settings/lists`·`settings/users`)과 같은 관례 —
 * 한국어 원문 + 디자인 토큰(var(--...)) 만 쓰고 색상 리터럴을 직접 박지 않는다.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, CardContent } from "@propai/ui";
import { apiClient, ApiClientError } from "@/lib/api-client";

/* ------------------------------------------------------------------ */
/*  백엔드 계약 (growth.py LearningCandidateOut 과 1:1)                 */
/* ------------------------------------------------------------------ */

type LearningStatus = "candidate" | "active" | "rejected";

export type LearningCandidate = {
  id: string;
  service: string | null;
  analysis_type: string | null;
  status: string;
  tenant_id: string | null;
  content_hash: string | null;
  input_summary: string;
  input_summary_truncated: boolean;
  good_output: string;
  good_output_truncated: boolean;
  created_at: string | null;
  train_allowed: boolean;
  rights_scope: string | null;
};

type CandidateList = {
  items: LearningCandidate[];
  total: number;
  statuses: string[];
  service: string | null;
  tenant_id: string | null;
  limit: number;
  offset: number;
};

type PromoteResult = { example_id: string; status: string };

/* ------------------------------------------------------------------ */
/*  표시 라벨 (디자인 토큰만 사용 — 색상 리터럴 금지)                    */
/* ------------------------------------------------------------------ */

const PAGE_SIZE = 20;

const STATUS_TABS: { key: LearningStatus; label: string; hint: string }[] = [
  { key: "candidate", label: "승인 대기", hint: "사람이 확인해야 AI 프롬프트에 들어갑니다." },
  { key: "active", label: "사용 중", hint: "승인되어 실제 AI 답변에 참고되고 있습니다." },
  { key: "rejected", label: "거부됨", hint: "쓰지 않기로 한 사례입니다." },
];

const STATUS_LABELS: Record<string, string> = {
  candidate: "승인 대기",
  active: "사용 중",
  rejected: "거부됨",
};

function statusClasses(status: string): string {
  switch (status) {
    case "active":
      return "border-[var(--status-success)]/30 bg-[var(--status-success)]/10 text-[var(--status-success)]";
    case "rejected":
      return "border-[var(--status-error)]/30 bg-[var(--status-error)]/10 text-[var(--status-error)]";
    default:
      return "border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] text-[var(--accent-strong)]";
  }
}

function fmtDate(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "-"
    : d.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

/* ------------------------------------------------------------------ */
/*  본체                                                               */
/* ------------------------------------------------------------------ */

export default function LearningApprovalPanel() {
  const [status, setStatus] = useState<LearningStatus>("candidate");
  const [serviceFilter, setServiceFilter] = useState("");
  const [page, setPage] = useState(0);

  const [data, setData] = useState<CandidateList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // 처리 중인 항목 id — 같은 건을 두 번 누르는 것을 막는다(중복 승인 방지).
  const [busyId, setBusyId] = useState<string | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams({
      status,
      limit: String(PAGE_SIZE),
      offset: String(page * PAGE_SIZE),
    });
    if (serviceFilter.trim()) params.set("service", serviceFilter.trim());
    return params.toString();
  }, [status, serviceFilter, page]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.get<CandidateList>(
        `/growth/learning/candidates?${query}`,
        { useMock: false },
      );
      setData(res);
    } catch (e) {
      setData(null);
      setError(
        e instanceof ApiClientError
          ? `후보 목록을 불러오지 못했습니다 (${e.status}). 총괄관리자 권한이 필요합니다.`
          : "후보 목록을 불러오지 못했습니다.",
      );
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * 한 건 승인/거부. ★한 번에 한 건만 — 목록 전체를 한 번에 처리하는 경로는 만들지 않는다
   * (자동 활성 금지 원칙. 위 파일 주석 참고).
   */
  const decide = useCallback(
    async (id: string, next: "active" | "rejected") => {
      setBusyId(id);
      setNotice(null);
      try {
        const res = await apiClient.post<PromoteResult>("/growth/learning/promote", {
          body: { example_id: id, status: next },
          useMock: false,
        });
        setNotice(
          res.status === "active"
            ? "승인했습니다. 이제 이 사례가 AI 답변에 참고됩니다."
            : "거부했습니다. 이 사례는 쓰이지 않습니다.",
        );
        await load();
      } catch (e) {
        setNotice(
          e instanceof ApiClientError
            ? `처리하지 못했습니다 (${e.status}).`
            : "처리하지 못했습니다.",
        );
      } finally {
        setBusyId(null);
      }
    },
    [load],
  );

  /** 활성 학습셋(JSONL) 내려받기 — 생성/다운로드까지만, 학습 실행은 사람이 따로 한다. */
  const downloadDataset = useCallback(async () => {
    setNotice(null);
    try {
      const res = await apiClient.get<{ message?: string }>(
        "/growth/learning/dataset?status=active",
        { useMock: false },
      );
      const body = typeof res?.message === "string" ? res.message : "";
      const url = URL.createObjectURL(new Blob([body], { type: "application/x-ndjson" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "learning_dataset_active.jsonl";
      a.click();
      URL.revokeObjectURL(url);
      setNotice(body ? "학습셋을 내려받았습니다." : "승인된 사례가 아직 없어 파일이 비어 있습니다.");
    } catch (e) {
      setNotice(
        e instanceof ApiClientError
          ? `학습셋을 내려받지 못했습니다 (${e.status}).`
          : "학습셋을 내려받지 못했습니다.",
      );
    }
  }, []);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const activeTab = STATUS_TABS.find((t) => t.key === status);

  return (
    <div className="space-y-6">
      {/* ── 필터 · 다운로드 ────────────────────────────────────── */}
      <Card className="rounded-2xl">
        <CardContent className="p-5">
          <div className="flex flex-wrap items-center gap-2">
            {STATUS_TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => {
                  setStatus(tab.key);
                  setPage(0);
                }}
                aria-pressed={status === tab.key}
                className={`rounded-xl border px-3 py-1.5 text-xs font-black transition-colors ${
                  status === tab.key
                    ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                    : "border-[var(--line)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)]"
                }`}
              >
                {tab.label}
              </button>
            ))}
            <input
              value={serviceFilter}
              onChange={(e) => {
                setServiceFilter(e.target.value);
                setPage(0);
              }}
              placeholder="서비스로 좁히기 (예: avm)"
              aria-label="서비스 필터"
              className="ml-auto w-52 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
            />
            <button
              type="button"
              onClick={downloadDataset}
              className="rounded-xl border border-[var(--line-strong)] px-3 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)]"
            >
              승인된 학습셋 내려받기
            </button>
          </div>
          <p className="mt-2 text-xs text-[var(--text-hint)]">{activeTab?.hint}</p>
        </CardContent>
      </Card>

      {error && (
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-[var(--status-error)]">{error}</p>
          </CardContent>
        </Card>
      )}
      {notice && (
        <p className="text-xs font-semibold text-[var(--accent-strong)]" role="status">
          {notice}
        </p>
      )}

      {/* ── 후보 목록 ─────────────────────────────────────────── */}
      {loading ? (
        <p className="text-sm text-[var(--text-hint)]">불러오는 중…</p>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="p-6">
            <p className="text-sm text-[var(--text-secondary)]">
              {status === "candidate"
                ? "승인을 기다리는 사례가 아직 없습니다. 사용자가 분석 결과에 좋아요를 남기면 여기에 쌓입니다."
                : "해당하는 사례가 없습니다."}
            </p>
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-4" aria-label="학습 사례 목록">
          {items.map((it) => (
            <li key={it.id}>
              <Card className="rounded-2xl">
                <CardContent className="p-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-full border px-2 py-0.5 text-xs font-bold ${statusClasses(it.status)}`}>
                      {STATUS_LABELS[it.status] ?? it.status}
                    </span>
                    <span className="cc-meta">{it.service ?? "서비스 미상"}</span>
                    {it.analysis_type && (
                      <span className="text-xs text-[var(--text-hint)]">{it.analysis_type}</span>
                    )}
                    {/* 승인하면 이 테넌트의 AI 프롬프트에만 들어간다(테넌트별 격리) — 보이게 둔다. */}
                    <span className="text-xs text-[var(--text-hint)]">
                      테넌트 {it.tenant_id ?? "미지정"}
                    </span>
                    <span className="cc-num ml-auto text-xs text-[var(--text-hint)]">
                      {fmtDate(it.created_at)}
                    </span>
                  </div>

                  {/* 자산권리 표시 — 숨기지 않고 알린다(숨기면 "후보 없음"으로 오독된다). */}
                  {!it.train_allowed && (
                    <p className="mt-3 rounded-lg border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 px-3 py-2 text-xs text-[var(--status-warning)]">
                      학습 사용 권리가 확인되지 않은 자료입니다(권리 {it.rights_scope ?? "미등록"}).
                      승인 전에 출처·이용 조건을 확인하세요.
                    </p>
                  )}

                  <dl className="mt-3 space-y-2">
                    <div>
                      <dt className="cc-label">입력 요약</dt>
                      <dd className="mt-0.5 whitespace-pre-wrap break-keep text-xs text-[var(--text-secondary)]">
                        {it.input_summary || "(비어 있음)"}
                        {it.input_summary_truncated && (
                          <span className="text-[var(--text-hint)]"> … (일부만 표시)</span>
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt className="cc-label">우수 출력</dt>
                      <dd className="mt-0.5 whitespace-pre-wrap break-keep text-xs text-[var(--text-primary)]">
                        {it.good_output || "(비어 있음)"}
                        {it.good_output_truncated && (
                          <span className="text-[var(--text-hint)]"> … (일부만 표시)</span>
                        )}
                      </dd>
                    </div>
                  </dl>

                  {/* ★한 건씩만 처리한다 — 목록 전체를 한 번에 켜는 버튼은 두지 않는다. */}
                  {it.status === "candidate" && (
                    <div className="mt-4 flex gap-2">
                      <button
                        type="button"
                        disabled={busyId === it.id}
                        onClick={() => void decide(it.id, "active")}
                        className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50"
                      >
                        {busyId === it.id ? "처리 중…" : "승인"}
                      </button>
                      <button
                        type="button"
                        disabled={busyId === it.id}
                        onClick={() => void decide(it.id, "rejected")}
                        className="rounded-xl border border-[var(--status-error)]/40 px-4 py-2 text-xs font-black text-[var(--status-error)] hover:bg-[var(--status-error)]/10 disabled:opacity-50"
                      >
                        거부
                      </button>
                    </div>
                  )}
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}

      {/* ── 페이지 이동 ───────────────────────────────────────── */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <button
            type="button"
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            className="rounded-xl border border-[var(--line)] px-3 py-2 text-xs font-bold text-[var(--text-secondary)] disabled:opacity-40"
          >
            이전
          </button>
          <span className="cc-num text-xs text-[var(--text-hint)]">
            {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} / {total}
          </span>
          <button
            type="button"
            disabled={(page + 1) * PAGE_SIZE >= total}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-xl border border-[var(--line)] px-3 py-2 text-xs font-bold text-[var(--text-secondary)] disabled:opacity-40"
          >
            다음
          </button>
        </div>
      )}
    </div>
  );
}
