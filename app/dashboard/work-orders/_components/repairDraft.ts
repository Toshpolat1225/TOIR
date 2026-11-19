import { api, type Nomenclature, type WorkOrderTemplateItem, type WorkType } from "@/lib/api";
import type { RepairDraft, TmcDraft } from "./types";

function tmcFromTemplate(item: WorkOrderTemplateItem, nomenclature: Nomenclature[]): TmcDraft {
  const match = item.nomenclature_id
    ? nomenclature.find((row) => row.id === item.nomenclature_id)
    : undefined;
  return {
    id: crypto.randomUUID(),
    nomenclatureId: item.nomenclature_id ?? null,
    name: match?.name ?? item.nomenclature_name ?? item.name ?? "",
    invNo: item.inv_no ?? match?.code ?? "",
    unit: item.unit ?? match?.unit ?? "шт.",
    qty: String(item.default_quantity),
    note: item.note ?? "",
  };
}

/** One repair type with its default TMC rows taken from the department's template. */
export async function buildRepairDraft(
  workType: WorkType,
  departmentId: string | null,
  nomenclature: Nomenclature[]
): Promise<RepairDraft> {
  const templates = departmentId
    ? await api.workOrders.templateItems({ work_type_id: workType.id, department_id: departmentId })
    : [];
  return {
    id: crypto.randomUUID(),
    workTypeId: workType.id,
    kind: workType.code,
    rows: templates.map((item) => tmcFromTemplate(item, nomenclature)),
  };
}
