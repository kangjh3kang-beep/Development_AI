"use client";

import { useState, useEffect } from "react";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { Card, CardContent } from "@propai/ui";

type User = {
  id: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  created_at: string;
};

export default function AdminUsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadUsers() {
      try {
        const data = await apiClient.get<{ users: User[] }>("/auth/admin/users", { useMock: false });
        setUsers(data.users || []);
      } catch (e) {
        setError(e instanceof ApiClientError ? `${e.status}: ${e.message}` : "사용자 목록 로딩 실패");
      } finally {
        setLoading(false);
      }
    }
    loadUsers();
  }, []);

  if (loading) return <div className="flex justify-center py-20"><div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--accent-strong)] border-t-transparent" /></div>;

  return (
    <div className="space-y-8 p-4 sm:p-8">
      <div className="cc-bracketed relative overflow-hidden rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6 shadow-[var(--shadow-lg)]">
        <div className="cc-grid-bg opacity-50" />
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <div className="relative z-10 flex flex-wrap items-end justify-between gap-3">
          <div className="space-y-1.5">
            <span className="cc-meta">ACCESS · ROSTER</span>
            <h1 className="text-2xl sm:text-3xl font-black text-[var(--text-primary)]">사용자 관리</h1>
            <p className="text-sm text-[var(--text-secondary)]">등록된 사용자를 관리합니다 (관리자 전용)</p>
          </div>
          <span className="cc-chip-data">{users.length} REGISTERED</span>
        </div>
      </div>

      {error && (
        <Card><CardContent className="p-4">
          <p className="text-sm text-[var(--status-error)]">{error}</p>
          <p className="text-xs text-[var(--text-hint)] mt-1">관리자 권한이 필요합니다.</p>
        </CardContent></Card>
      )}

      <div className="overflow-x-auto rounded-2xl border border-[var(--line)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--line)] bg-[var(--surface-muted)]">
              <th className="cc-label px-4 py-3 text-left">이름</th>
              <th className="cc-label px-4 py-3 text-left">이메일</th>
              <th className="cc-label px-4 py-3 text-left">역할</th>
              <th className="cc-label px-4 py-3 text-left">상태</th>
              <th className="cc-label px-4 py-3 text-left">가입일</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className="border-b border-[var(--line)] hover:bg-[var(--surface-muted)] transition-colors">
                <td className="px-4 py-3 font-medium text-[var(--text-primary)]">{u.name}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{u.email}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${u.role === "admin" ? "bg-[var(--status-warning)]/10 text-[var(--status-warning)]" : "bg-[var(--status-info)]/10 text-[var(--status-info)]"}`}>
                    {u.role === "admin" ? "관리자" : "사용자"}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`flex items-center gap-1.5 text-xs ${u.is_active ? "text-[var(--status-success)]" : "text-[var(--status-error)]"}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${u.is_active ? "bg-[var(--status-success)]" : "bg-[var(--status-error)]"}`} />
                    {u.is_active ? "활성" : "비활성"}
                  </span>
                </td>
                <td className="cc-num px-4 py-3 text-[var(--text-hint)] text-xs">{new Date(u.created_at).toLocaleDateString("ko-KR")}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && !error && (
          <p className="text-center py-8 text-sm text-[var(--text-hint)]">등록된 사용자가 없습니다.</p>
        )}
      </div>
    </div>
  );
}
