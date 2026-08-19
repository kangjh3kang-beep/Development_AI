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
 * 【학습권리 문턱 — 2026-08-19 적대리뷰 HIGH】
 * 권리가 확인되지 않은 자료는 경고만 띄우고 승인은 그대로 되게 두었었다. 그건 틀렸다:
 * 프롬프트 주입 경로(base_interpreter._load_fewshot)는 status='active' 만 보고 권리를
 * 전혀 보지 않으므로, **승인만으로 권리 없는 자료가 AI 답변에 들어간다.**
 * 그래서 지금은 그런 행의 승인 버튼이 잠겨 있고, 사람이 '출처를 확인했다'를 명시적으로
 * 체크해야 열린다. 그 체크는 서버로도 함께 가고(acknowledge_unverified_rights),
 * 서버는 그 값 없이는 409 로 거부한다. 인수 사실은 감사기록에 남는다.
 * ★행 단위 문턱이다 — 한 행을 인수해도 다른 행은 잠긴 채로 남는다(일괄 승인 금지와 같은 뜻).
 *
 * 【절대 넣지 않는 것 — 일괄/자동 승인】
 * "전체 승인" 같은 버튼은 두지 않는다. 이 설계의 핵심 제약이 "자동 활성 절대 금지"이고,
 * 한 번에 다 켜는 버튼은 사람이 내용을 본다는 전제를 무너뜨려 자동 승인과 사실상 같아진다.
 * 승인/거부는 **항상 한 건씩**, 그 건의 내용을 화면에서 보면서 누른다.
 *
 * 무목업: 실제 API 만 쓴다. 데이터가 없으면 "아직 후보가 쌓이지 않았다"고 정직하게 적는다.
 *
 * 【변이 감사 재분류 — 2026-08-19, 도구 재실행 결과】
 * 처음엔 남은 생존을 **전부 표시층**이라고 적었다. 그 분류가 틀렸다. 적대리뷰가
 * fetch URL 뒤에 글자를 붙이는 변이(/candidates → /candidatesX)를 넣자 살아남았는데,
 * 문자열 변이지만 표시층이 아니라 **프로덕션 404** 를 내는 배선 구멍이었다.
 * 그래서 "문자열이면 표시층"으로 뭉뚱그리지 않고, 생존 문자열을 종류로 갈랐다
 * (mutate_changed.py 136변이 · 생존 65건 기준):
 *   ② **배선** — 아래 열거는 처음에 좁았고, 좁은 탓에 구멍을 놓쳤다(F3 실증). 배선이란
 *        "요청이 **어디로·무엇을 담고·몇 번** 나가는가"를 정하는 코드 전부다:
 *          · URL·경로 세그먼트·쿼리 키 · 요청 본문 키 · 상태값
 *          · ★**상태 가드**(in-flight 잠금·중복요청 방지·가드 해제 시점) ← 처음 빠뜨린 범주
 *        1차: 3건(STATUS_TABS 의 key "candidate"/"rejected" — 표시 문구가 아니라 서버로 가는
 *             값이라 바꾸면 그 탭에서 400 · statusClasses 의 case "rejected") → 전부 잠갔다.
 *        2차: 그러고 "② 0건"이라 선언했는데 **틀렸다.** 열거에 상태 가드가 없어서
 *             `setBusy(...add(id))` 를 지워도 51 테스트가 전부 초록이었다(POST 1회→3회).
 *             연타 가드와 **행 단위** 해제를 테스트로 잠갔다.
 *   ③ 런타임에 사라지는 것(use client 지시자·TS 유니온 타입·React key) …… 4건
 *        jsdom 테스트로는 **원리적으로** 못 잡는다. type-check 가 담당한다.
 *   ① 표시 문구·클래스명 …… 58건. 바꿔도 동작이 같다.
 * ★교훈 둘: (1) 문자열 변이를 한 덩어리로 분류하면 그 안에 배선 구멍이 숨는다.
 *   (2) **범주 열거 자체가 틀릴 수 있다** — "그 범주 안에서 0건"은 "구멍이 없다"가 아니다.
 *   내가 방금 바꾼 배선부터 의심하라(이번 둘 다 내가 직접 만든 코드에서 나왔다).
 * ※새 로직을 넣으면 도구를 다시 돌리고 **종류별로** 가려라 — "남은 건 다 표시층"으로 읽지 마라.
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

type PromoteResult = { example_id: string; status: string; rights_acknowledged?: boolean };

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
  // 처리 중인 항목 id들 — 같은 건을 두 번 누르는 것을 막는다(중복 승인 방지).
  // ★Set 인 이유: 단일 문자열이면 A 처리 중 B 를 누를 때 A 의 finally 가 가드를 일찍 풀어
  //   화면 전체에 **한 칸짜리** 가드가 된다(적대리뷰 구조 관찰). 행마다 독립으로 잠근다.
  const [busy, setBusy] = useState<ReadonlySet<string>>(() => new Set());
  // 학습권리가 확인되지 않은 항목을 "출처를 확인했다"고 사람이 명시적으로 인수한 목록.
  // ★이게 있어야만 승인 버튼이 열리고, 서버로도 그 사실을 함께 보낸다(백엔드가 기본 거부).
  const [acknowledged, setAcknowledged] = useState<ReadonlySet<string>>(() => new Set());

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
    async (id: string, next: "active" | "rejected", acknowledgeRights: boolean) => {
      setBusy((prev) => new Set(prev).add(id));
      setNotice(null);
      try {
        const res = await apiClient.post<PromoteResult>("/growth/learning/promote", {
          body: {
            example_id: id,
            status: next,
            // 권리 미확인 항목은 이 값이 true 여야 서버가 받아 준다(기본 거부).
            acknowledge_unverified_rights: acknowledgeRights,
          },
          useMock: false,
        });
        setNotice(
          res.status === "active"
            ? res.rights_acknowledged
              ? "승인했습니다(학습권리 미확인 — 확인 책임을 인수한 기록이 남았습니다)."
              : "승인했습니다. 이제 이 사례가 AI 답변에 참고됩니다."
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
        setBusy((prev) => {
          const next2 = new Set(prev);
          next2.delete(id);
          return next2;
        });
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
                    <div className="mt-3 rounded-lg border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 px-3 py-2 text-xs text-[var(--status-warning)]">
                      <p>
                        학습 사용 권리가 확인되지 않은 자료입니다(권리 {it.rights_scope ?? "미등록"}).
                        확인하지 않으면 승인할 수 없습니다.
                      </p>
                      {/* ★승인 문턱 — 서버가 기본 거부하므로 이 체크 없이는 활성화가 불가능하다. */}
                      <label className="mt-2 flex items-center gap-2 font-bold">
                        <input
                          type="checkbox"
                          checked={acknowledged.has(it.id)}
                          onChange={(e) =>
                            setAcknowledged((prev) => {
                              const nextSet = new Set(prev);
                              if (e.target.checked) nextSet.add(it.id);
                              else nextSet.delete(it.id);
                              return nextSet;
                            })
                          }
                        />
                        출처·이용 조건을 확인했으며 승인 책임을 집니다
                      </label>
                    </div>
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
                        disabled={busy.has(it.id) || (!it.train_allowed && !acknowledged.has(it.id))}
                        onClick={() =>
                          void decide(it.id, "active", acknowledged.has(it.id))
                        }
                        className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50"
                      >
                        {busy.has(it.id) ? "처리 중…" : "승인"}
                      </button>
                      {/* 거부는 안전한 방향이라 권리 확인과 무관하게 항상 누를 수 있다. */}
                      <button
                        type="button"
                        disabled={busy.has(it.id)}
                        onClick={() => void decide(it.id, "rejected", false)}
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
