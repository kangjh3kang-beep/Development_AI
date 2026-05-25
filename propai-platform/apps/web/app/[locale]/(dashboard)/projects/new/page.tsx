"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, Button } from "@propai/ui";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

const PROJECT_TYPES = [
  { value: "residential", label: "주거" },
  { value: "commercial", label: "상업" },
  { value: "mixed", label: "복합" },
  { value: "logistics", label: "물류" },
  { value: "industrial", label: "산업" },
];

const AVAILABLE_MODULES = [
  { key: "design", label: "설계 (Design)", defaultOn: true },
  { key: "bim", label: "BIM 3D", defaultOn: true },
  { key: "finance", label: "금융 분석", defaultOn: true },
  { key: "drone", label: "드론 점검", defaultOn: false },
  { key: "blockchain", label: "블록체인 에스크로", defaultOn: false },
  { key: "tax", label: "세금 시뮬레이션", defaultOn: false },
  { key: "inspection", label: "현장 점검", defaultOn: false },
  { key: "report", label: "보고서 생성", defaultOn: true },
];

export default function NewProjectPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [projectType, setProjectType] = useState("mixed");
  const [modules, setModules] = useState<Set<string>>(
    new Set(AVAILABLE_MODULES.filter(m => m.defaultOn).map(m => m.key))
  );
  const [isSubmitting, setIsSubmitting] = useState(false);

  const toggleModule = (key: string) => {
    setModules(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!name.trim() || !location.trim()) return;
    setIsSubmitting(true);

    // TODO: POST /projects API 연동
    const projectId = `proj-${Date.now()}`;

    // 임시: 생성 후 프로젝트 상세 페이지로 이동
    router.push(`projects/${projectId}`);
  };

  return (
    <div className="grid gap-6">
      <ModulePlaceholder
        eyebrow="PROJECTS / NEW"
        title="신규 프로젝트 생성"
        description="새로운 부동산 개발 프로젝트를 생성하고 AI 자동 분석을 시작합니다."
        statusLabel="Setup"
        localeLabel="ko"
        items={[
          "기본 정보 입력 (프로젝트명, 위치, 유형)",
          "분석 모듈 선택 (설계/BIM/금융/드론 등)",
          "POST /projects API로 프로젝트 생성",
        ]}
      />

      <Card className="rounded-[var(--radius-2xl)]">
        <CardContent className="p-8">
          <h3 className="text-xl font-bold text-[var(--text-primary)]">Step 1: 기본 정보</h3>
          <div className="mt-6 grid gap-4">
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)]">프로젝트명</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="예: 성수 복합개발 1차"
                className="mt-2 w-full rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-3 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)]">위치</label>
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="예: 서울 성동구 성수동"
                className="mt-2 w-full rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-3 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)]">프로젝트 유형</label>
              <div className="mt-2 flex flex-wrap gap-2">
                {PROJECT_TYPES.map((type) => (
                  <button
                    key={type.value}
                    type="button"
                    onClick={() => setProjectType(type.value)}
                    className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                      projectType === type.value
                        ? "bg-[var(--accent-strong)] text-white"
                        : "border border-[var(--line)] bg-[var(--surface)] text-[var(--text-secondary)] hover:bg-[var(--surface-soft)]"
                    }`}
                  >
                    {type.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-[var(--radius-2xl)]">
        <CardContent className="p-8">
          <h3 className="text-xl font-bold text-[var(--text-primary)]">Step 2: 분석 모듈 선택</h3>
          <div className="mt-6 grid gap-3 md:grid-cols-2">
            {AVAILABLE_MODULES.map((mod) => (
              <button
                key={mod.key}
                type="button"
                onClick={() => toggleModule(mod.key)}
                className={`flex items-center gap-3 rounded-2xl px-5 py-3 text-left transition ${
                  modules.has(mod.key)
                    ? "bg-[var(--accent-soft)] border border-[var(--accent-strong)] text-[var(--accent-strong)]"
                    : "bg-[var(--surface-soft)] border border-transparent text-[var(--text-tertiary)]"
                }`}
              >
                <span className={`flex h-5 w-5 items-center justify-center rounded-md border text-xs ${
                  modules.has(mod.key)
                    ? "border-[var(--accent-strong)] bg-[var(--accent-strong)] text-white"
                    : "border-[var(--line)] text-transparent"
                }`}>
                  {modules.has(mod.key) ? "✓" : ""}
                </span>
                <span className="text-sm font-medium">{mod.label}</span>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-[var(--radius-2xl)]">
        <CardContent className="p-8">
          <h3 className="text-xl font-bold text-[var(--text-primary)]">Step 3: 프로젝트 생성</h3>
          <p className="mt-2 text-sm text-[var(--text-tertiary)]">
            프로젝트를 생성하면 선택한 모듈에 대해 AI 자동 분석이 시작됩니다.
          </p>
          <div className="mt-6">
            <Button
              onClick={handleSubmit}
              disabled={!name.trim() || !location.trim() || isSubmitting}
              className="rounded-full bg-[var(--accent-strong)] px-8 py-3 text-sm font-semibold text-white disabled:opacity-40"
            >
              {isSubmitting ? "생성 중..." : "프로젝트 생성 & AI 분석 시작"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
