"use client";

import { ProjectLifecyclePipeline } from "@/components/projects/ProjectLifecyclePipeline";

export function ProjectLifecyclePipelineWrapper({
  locale,
  projectId,
}: {
  locale: string;
  projectId: string;
}) {
  return <ProjectLifecyclePipeline locale={locale} projectId={projectId} compact />;
}
