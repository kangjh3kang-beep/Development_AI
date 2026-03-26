import { CadEditor } from "@/components/cad/CadEditor";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { isValidLocale } from "@/i18n/config";

type CadPageProps = {
  params: Promise<{
    locale: string;
    id: string;
  }>;
};

export default async function CadPage({ params }: CadPageProps) {
  const { locale, id } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="grid gap-6">
      <ModulePlaceholder
        eyebrow="PROJECT / CAD"
        title="Project CAD editor route"
        description="Keep the parametric CAD editor available on this route, but treat it as editor-only until the current Three.js and dependency blockers are resolved."
        statusLabel="EDITOR"
        localeLabel={locale}
        items={[
          "react-konva based editor remains available for route-level design editing",
          "This route is not treated as a live backend-bound workspace yet",
          "Resolve current CAD dependency and type-check blockers before promoting it to live status",
        ]}
      />
      <CadEditor projectId={id} />
    </div>
  );
}
