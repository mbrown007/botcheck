"use client";

import { useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { usePack, updatePack, type ScenarioPackUpsertRequest } from "@/lib/api";
import { AccessPanel } from "@/components/auth/access-panel";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { TableState } from "@/components/ui/table-state";
import { useDashboardAccess } from "@/lib/current-user";
import {
  PackEditorForm,
  type PackEditorInitialValues,
} from "../../_components/PackEditorForm";

export default function EditPackPage() {
  const params = useParams<{ packId: string }>();
  const packId = params?.packId ?? "";
  const router = useRouter();
  const { roleResolved, canManagePacks } = useDashboardAccess();
  const { data: pack, error, mutate } = usePack(packId || null);

  if (!roleResolved) {
    return (
      <AccessPanel
        title="Edit Pack"
        message="Loading pack permissions…"
        backHref="/packs"
        backLabel="Back to packs"
      />
    );
  }

  if (!canManagePacks) {
    return (
      <AccessPanel
        title="Edit Pack"
        message="Pack editing is restricted to admin role or above."
        backHref="/packs"
        backLabel="Back to packs"
      />
    );
  }

  const initialValues = useMemo<PackEditorInitialValues>(
    () => ({
      name: pack?.name ?? "",
      description: pack?.description ?? "",
      tags: pack?.tags ?? [],
      selectedItems: pack?.items
        ?.slice()
        .sort((left, right) => left.order_index - right.order_index)
        .map((item) => ({
          scenarioId: item.scenario_id,
          aiScenarioId: item.ai_scenario_id ?? null,
        })) ?? [],
    }),
    [pack]
  );

  async function handleSave(payload: ScenarioPackUpsertRequest) {
    if (!packId) {
      throw new Error("Pack id is missing");
    }
    await updatePack(packId, payload);
    await mutate();
    router.push("/packs");
    router.refresh();
  }

  if (error) {
    return (
      <div className="space-y-4">
        <Card>
          <CardBody className="p-0">
            <TableState kind="error" title="Failed to load pack" message={error.message} />
          </CardBody>
        </Card>
        <Button variant="secondary" onClick={() => router.push("/packs")}>
          Back to Packs
        </Button>
      </div>
    );
  }

  if (!pack) {
    return (
      <Card>
        <CardBody className="p-0">
          <TableState kind="loading" message="Loading pack…" columns={4} rows={4} />
        </CardBody>
      </Card>
    );
  }

  return (
    <PackEditorForm
      title={`Edit Pack ${pack.pack_id}`}
      subtitle="Update metadata and scenario membership for this pack."
      submitLabel="Save Pack"
      initialValues={initialValues}
      onSubmit={handleSave}
    />
  );
}
