"use client";

import { useState } from "react";
import { FloorPlanGenerator } from "@/components/design/FloorPlanGenerator";
import { FloorPlanViewer } from "@/components/design/FloorPlanViewer";
import { CollaborationCursors } from "@/components/collaboration/CollaborationCursors";
import type {
  CollaborationMember,
  FloorPlanDraft,
  FloorPlanStatus,
} from "@/mocks/module-data";

type DesignWorkspaceClientProps = {
  plans: FloorPlanDraft[];
  members: CollaborationMember[];
  labels: {
    workspaceTitle: string;
    workspaceDescription: string;
    previewTitle: string;
    generatorTitle: string;
    generatorDescription: string;
    promptLabel: string;
    uploadLabel: string;
    generateLabel: string;
    referenceIdle: string;
    referenceReady: string;
    optionsTitle: string;
    statusLabels: Record<FloorPlanStatus, string>;
    statusTitle: string;
    areaLabel: string;
    roomsLabel: string;
    collaborationTitle: string;
    collaborationDescription: string;
  };
};

export function DesignWorkspaceClient({
  plans,
  members,
  labels,
}: DesignWorkspaceClientProps) {
  const [selectedPlanId, setSelectedPlanId] = useState(plans[0]?.id ?? "");
  const selectedPlan =
    plans.find((plan) => plan.id === selectedPlanId) ?? plans[0];

  if (!selectedPlan) {
    return null;
  }

  return (
    <section className="grid gap-6">
      <div className="rounded-[1.75rem] border border-[var(--line)] bg-white/72 px-6 py-5">
        <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.48)]">
          Workspace
        </p>
        <h3 className="mt-3 text-2xl font-semibold text-[var(--foreground)]">
          {labels.workspaceTitle}
        </h3>
        <p className="mt-3 text-sm leading-7 text-[rgba(19,33,47,0.74)]">
          {labels.workspaceDescription}
        </p>
      </div>
      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <FloorPlanGenerator
          plans={plans}
          selectedPlanId={selectedPlan.id}
          onSelectPlan={setSelectedPlanId}
          labels={{
            title: labels.generatorTitle,
            description: labels.generatorDescription,
            promptLabel: labels.promptLabel,
            uploadLabel: labels.uploadLabel,
            generateLabel: labels.generateLabel,
            referenceIdle: labels.referenceIdle,
            referenceReady: labels.referenceReady,
            optionsTitle: labels.optionsTitle,
            statusLabels: labels.statusLabels,
          }}
        />
        <div className="grid gap-6">
          <FloorPlanViewer
            plan={selectedPlan}
            labels={{
              title: labels.previewTitle,
              areaLabel: labels.areaLabel,
              roomsLabel: labels.roomsLabel,
              statusTitle: labels.statusTitle,
              statusValue: labels.statusLabels[selectedPlan.status],
            }}
          />
          <CollaborationCursors
            members={members}
            labels={{
              title: labels.collaborationTitle,
              description: labels.collaborationDescription,
            }}
          />
        </div>
      </div>
    </section>
  );
}
