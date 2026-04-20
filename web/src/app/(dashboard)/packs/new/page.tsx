"use client";

import { useRouter } from "next/navigation";
import { createPack, type ScenarioPackUpsertRequest } from "@/lib/api";
import { AccessPanel } from "@/components/auth/access-panel";
import { useDashboardAccess } from "@/lib/current-user";
import {
  PackEditorForm,
  type PackEditorInitialValues,
} from "../_components/PackEditorForm";

const EMPTY_INITIAL_VALUES: PackEditorInitialValues = {
  name: "",
  description: "",
  tags: [],
  selectedItems: [],
};

export default function NewPackPage() {
  const router = useRouter();
  const { roleResolved, canManagePacks } = useDashboardAccess();

  if (!roleResolved) {
    return (
      <AccessPanel
        title="New Pack"
        message="Loading pack permissions…"
        backHref="/packs"
        backLabel="Back to packs"
      />
    );
  }

  if (!canManagePacks) {
    return (
      <AccessPanel
        title="New Pack"
        message="Pack creation is restricted to admin role or above."
        backHref="/packs"
        backLabel="Back to packs"
      />
    );
  }

  async function handleCreate(payload: ScenarioPackUpsertRequest) {
    const created = await createPack(payload);
    router.push(`/packs/${created.pack_id}/edit`);
    router.refresh();
  }

  return (
    <PackEditorForm
      title="New Pack"
      subtitle="Create a reusable regression suite from existing scenarios."
      submitLabel="Create Pack"
      initialValues={EMPTY_INITIAL_VALUES}
      onSubmit={handleCreate}
    />
  );
}
