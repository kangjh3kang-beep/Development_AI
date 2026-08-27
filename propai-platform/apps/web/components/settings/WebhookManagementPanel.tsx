"use client";

import { useEffect, useState, type FormEvent } from "react";

import { apiClient, ApiClientError } from "@/lib/api-client";
import { Button, Card, CardContent, Input } from "@propai/ui";

/**
 * 백엔드 계약(`packages/schemas/models.WebhookResponse`)을 **그대로** 옮긴다.
 *
 * ★2026-08-27 — 이 패널은 `MOCK_WEBHOOKS` 를 렌더하고 있었다. 등록/토글/삭제가 전부
 *   **로컬 state 조작**이라, 사용자가 웹훅을 만들면 화면은 성공했다고 말하고
 *   **서버에는 아무 일도 일어나지 않았다.** 미배선보다 나쁘다 — 거짓말이다.
 *
 * ★그리고 목업은 **없는 필드를 지어냈다**: `last_delivery_status`·`last_delivered_at`·`active`.
 *   실제 계약은 `is_active` 이고 전송 이력은 `/webhooks/{id}/deliveries` 로 **따로** 조회한다.
 *   지어낸 두 필드는 **지웠다** — 모르는 것을 화면에 만들어 내지 않는다.
 */
type Webhook = {
  id: string;
  tenant_id: string;
  url: string;
  events: string[] | null;
  is_active: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
};

const EVENT_OPTIONS = [
  { value: "project.created", label: "프로젝트 생성" },
  { value: "project.updated", label: "프로젝트 업데이트" },
  { value: "report.generated", label: "보고서 생성" },
  { value: "avm.completed", label: "AVM 감정 완료" },
  { value: "compliance.checked", label: "법규검토 완료" },
  { value: "design.generated", label: "AI 설계 완료" },
  { value: "risk.analyzed", label: "리스크 분석 완료" },
];

/** 서버 오류를 사람 말로 — ★상태코드를 삼키지 않는다(무엇이 막혔는지 알아야 고친다). */
function describe(e: unknown, fallback: string): string {
  if (e instanceof ApiClientError) {
    if (e.status === 401 || e.status === 403) return "권한이 없습니다. 다시 로그인해 주세요.";
    const detail =
      typeof e.payload === "object" && e.payload !== null && "detail" in e.payload
        ? String((e.payload as { detail: unknown }).detail)
        : "";
    return detail || `${fallback} (HTTP ${e.status})`;
  }
  return fallback;
}

export function WebhookManagementPanel() {
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newUrl, setNewUrl] = useState("");
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState("");

  // ★GET /webhooks 는 **배열을 직접** 준다(목업이 가정한 `{webhooks: []}` 래퍼가 아니다).
  async function reload() {
    try {
      const rows = await apiClient.get<Webhook[]>("/webhooks");
      setWebhooks(Array.isArray(rows) ? rows : []);
      setError("");
    } catch (e) {
      setWebhooks([]);
      setError(describe(e, "웹훅 목록을 불러오지 못했습니다."));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  function toggleEvent(event: string) {
    setSelectedEvents((prev) =>
      prev.includes(event)
        ? prev.filter((e) => e !== event)
        : [...prev, event],
    );
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError("");

    const url = newUrl.trim();
    if (!url) {
      setError("웹훅 URL을 입력해 주세요.");
      return;
    }

    if (!url.startsWith("https://")) {
      setError("보안을 위해 https:// 로 시작하는 URL만 허용됩니다.");
      return;
    }

    try {
      new URL(url);
    } catch {
      setError("유효한 URL 형식이 아닙니다.");
      return;
    }

    if (!selectedEvents.length) {
      setError("최소 하나의 이벤트를 선택해 주세요.");
      return;
    }

    setIsCreating(true);
    try {
      // ★서버가 만든 행을 그대로 쓴다 — 화면이 id·시각을 지어내지 않는다.
      const created = await apiClient.post<Webhook>("/webhooks", {
        body: { url, events: selectedEvents },
      });
      setWebhooks((prev) => [...prev, created]);
      setShowCreateForm(false);
      setNewUrl("");
      setSelectedEvents([]);
    } catch (e) {
      setError(describe(e, "웹훅 등록에 실패했습니다."));
    } finally {
      setIsCreating(false);
    }
  }

  async function toggleActive(webhookId: string) {
    const target = webhooks.find((wh) => wh.id === webhookId);
    if (!target) return;
    const next = !target.is_active;
    try {
      const saved = await apiClient.put<Webhook>(`/webhooks/${webhookId}`, {
        body: { is_active: next },
      });
      setWebhooks((prev) => prev.map((wh) => (wh.id === webhookId ? saved : wh)));
      setError("");
    } catch (e) {
      // ★서버가 거부하면 화면도 바뀌면 안 된다 — 낙관적 갱신을 하지 않는다.
      setError(describe(e, "활성 상태를 바꾸지 못했습니다."));
    }
  }

  async function handleDelete(webhookId: string) {
    try {
      await apiClient.delete(`/webhooks/${webhookId}`);
      setWebhooks((prev) => prev.filter((wh) => wh.id !== webhookId));
      setError("");
    } catch (e) {
      setError(describe(e, "웹훅을 삭제하지 못했습니다."));
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2].map((n) => (
          <div
            key={n}
            className="h-24 animate-pulse rounded-2xl bg-[var(--surface-soft)]"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ★목록 로딩·토글·삭제 실패는 **생성 폼 밖**에서도 보여야 한다.
          종전엔 오류 표시가 `showCreateForm` 블록 안에만 있어, 목록을 못 불러와도
          화면은 "등록된 웹훅: 0개" 만 말했다 — 정상과 장애가 구별되지 않는다.
          (이 파일을 실 API 로 배선하면서 내가 만든 결함이고, 락이 잡았다.) */}
      {!showCreateForm && error && (
        <p
          role="alert"
          className="rounded-xl bg-[var(--status-error)]/10 px-3 py-2 text-xs text-[var(--status-error)]"
        >
          {error}
        </p>
      )}

      {/* Header + Create Button */}
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-[var(--text-secondary)]">
          등록된 웹훅: <span className="cc-num text-[var(--text-primary)] font-bold">{webhooks.length}</span>개
        </p>
        <Button
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="gap-2"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 5v14" />
            <path d="M5 12h14" />
          </svg>
          새 웹훅 추가
        </Button>
      </div>

      {/* Create form */}
      {showCreateForm && (
        <Card className="border-[var(--accent-strong)]/30">
          <CardContent className="p-6">
            <p className="cc-label">
              새 웹훅 등록
            </p>
            <form className="mt-4 space-y-4" onSubmit={handleCreate}>
              <Input
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                placeholder="https://example.com/webhook"
              />

              <div className="space-y-2">
                <p className="cc-label">
                  이벤트 선택
                </p>
                <div className="flex flex-wrap gap-2">
                  {EVENT_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => toggleEvent(opt.value)}
                      className={`rounded-xl px-3 py-1.5 text-xs font-medium border transition-all ${
                        selectedEvents.includes(opt.value)
                          ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                          : "border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-secondary)] hover:border-[var(--text-tertiary)]"
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {error && (
                <p className="text-xs text-[var(--status-error)]">{error}</p>
              )}

              <div className="flex gap-3">
                <Button type="submit" disabled={isCreating}>
                  {isCreating ? "등록 중..." : "웹훅 등록"}
                </Button>
                <Button
                  type="button"
                  onClick={() => {
                    setShowCreateForm(false);
                    setError("");
                  }}
                  className="bg-[var(--surface-soft)] text-[var(--text-secondary)]"
                >
                  취소
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Webhook list */}
      {webhooks.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-sm text-[var(--text-secondary)]">
              등록된 웹훅이 없습니다. 새 웹훅을 추가해 보세요.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {webhooks.map((wh) => (
            <Card key={wh.id}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1 space-y-2">
                    {/* URL and status */}
                    <div className="flex items-center gap-3">
                      <div
                        className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                          wh.is_active
                            ? "bg-[var(--status-success)] animate-pulse"
                            : "bg-[var(--text-hint)]"
                        }`}
                      />
                      <p className="cc-num truncate text-sm font-semibold text-[var(--text-primary)]">
                        {wh.url}
                      </p>
                    </div>

                    {/* Events */}
                    <div className="flex flex-wrap gap-1.5">
                      {(wh.events ?? []).map((evt) => {
                        const label =
                          EVENT_OPTIONS.find((o) => o.value === evt)?.label ??
                          evt;
                        return (
                          <span
                            key={evt}
                            className="rounded-lg bg-[var(--surface-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]"
                          >
                            {label}
                          </span>
                        );
                      })}
                    </div>

                    {/* ★「마지막 전송」 두 줄은 지웠다 — 목업이 지어낸 필드였고 목록
                        엔드포인트는 그 값을 주지 않는다. 전송 이력은 별도 경로
                        (`/webhooks/{id}/deliveries`)이므로, 없는 것을 화면에 만들지 않는다.
                        ★대신 서버가 실제로 주는 것을 적는다. */}
                    <div className="flex items-center gap-4 text-xs text-[var(--text-hint)]">
                      {wh.description && <span>{wh.description}</span>}
                      <span>
                        등록{" "}
                        {new Intl.DateTimeFormat("ko-KR", {
                          dateStyle: "short",
                        }).format(new Date(wh.created_at))}
                      </span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      onClick={() => toggleActive(wh.id)}
                      className={`rounded-xl px-3 py-1.5 text-xs font-bold transition-all ${
                        wh.is_active
                          ? "bg-[var(--status-success)]/10 text-[var(--status-success)]"
                          : "bg-[var(--surface-soft)] text-[var(--text-hint)]"
                      }`}
                    >
                      {wh.is_active ? "활성" : "비활성"}
                    </button>
                    <button
                      onClick={() => handleDelete(wh.id)}
                      className="rounded-xl px-3 py-1.5 text-xs font-bold text-[var(--status-error)] transition-all hover:bg-[var(--status-error)]/10"
                    >
                      삭제
                    </button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
