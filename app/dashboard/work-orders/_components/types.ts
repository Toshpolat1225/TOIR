export type TmcDraft = {
  id: string;
  nomenclatureId: string | null;
  name: string;
  invNo: string;
  unit: string;
  qty: string;
  note: string;
  standardQty?: number;
  deviationPercent?: number;
  estimatedCost?: number;
  avgPrice?: number;
  warning?: string;
};

export type RepairDraft = {
  id: string;
  workTypeId: string;
  kind: string;
  rows: TmcDraft[];
};

export type WorkOrderTab = "open" | "pending" | "in_progress" | "completed";

export type WorkOrderListFilters = {
  tab: WorkOrderTab;
  q: string;
  section_id?: string;
  fixed_asset_id?: string;
  department_id?: string;
};
