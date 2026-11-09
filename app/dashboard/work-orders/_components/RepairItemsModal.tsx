"use client";

import { useState } from "react";
import { AlertCircle, Plus, Trash2, Wrench, X } from "@/components/ui/icons";
import {
  api,
  type Nomenclature,
  type NomenclatureNorm,
  type WorkOrderTemplateItem,
  type WorkType,
} from "@/lib/api";
import type { RepairDraft, TmcDraft } from "./types";
import { TmcModal } from "./TmcModal";

type Props = {
  departmentId: string | null;
  repairs: RepairDraft[];
  workTypes: WorkType[];
  nomenclature: Nomenclature[];
  norms: NomenclatureNorm[];
  onSave: (repairs: RepairDraft[]) => void;
  onClose: () => void;
};

function createTmcFromTemplate(
  item: WorkOrderTemplateItem,
  nomenclature: Nomenclature[]
): TmcDraft {
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

export function RepairItemsModal({
  departmentId,
  repairs,
  workTypes,
  nomenclature,
  norms,
  onSave,
  onClose,
}: Props) {
  const [localRepairs, setLocalRepairs] = useState(repairs);
  const [selectedRepairId, setSelectedRepairId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingWorkTypeId, setLoadingWorkTypeId] = useState<string | null>(null);

  async function addRepair(workTypeId: string) {
    const workType = workTypes.find((item) => item.id === workTypeId);
    if (!workType) return;
    setError(null);
    setLoadingWorkTypeId(workTypeId);
    try {
      const templates = departmentId
        ? await api.workOrders.templateItems({
            work_type_id: workType.id,
            department_id: departmentId,
          })
        : [];
      const repair: RepairDraft = {
        id: crypto.randomUUID(),
        workTypeId: workType.id,
        kind: workType.code,
        rows: templates.map((item) => createTmcFromTemplate(item, nomenclature)),
      };
      setLocalRepairs((current) => [...current, repair]);
      setSelectedRepairId(repair.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось загрузить шаблон");
    } finally {
      setLoadingWorkTypeId(null);
    }
  }

  function saveRows(repairId: string, rows: TmcDraft[]) {
    setLocalRepairs((current) =>
      current.map((repair) => (repair.id === repairId ? { ...repair, rows } : repair))
    );
    setSelectedRepairId(null);
  }

  const selectedRepair = localRepairs.find((repair) => repair.id === selectedRepairId);

  return (
    <>
      <div className="fixed inset-0 z-[70] flex items-center justify-center p-3">
        <button aria-label="Закрыть виды работ" className="absolute inset-0 bg-black/60" onClick={onClose} />
        <section className="relative flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-gray-900">
          <header className="flex items-center justify-between border-b p-4 dark:border-gray-700">
            <div>
              <h2 className="font-semibold text-gray-900 dark:text-white">Виды ремонта и ТМЦ</h2>
              <p className="text-xs text-gray-500">Добавьте один или несколько видов ремонта</p>
            </div>
            <button aria-label="Закрыть" onClick={onClose}><X className="h-5 w-5" /></button>
          </header>
          <div className="overflow-auto p-4">
            {error && (
              <p role="alert" className="mb-3 flex items-center gap-2 rounded bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
                <AlertCircle className="h-4 w-4" />{error}
              </p>
            )}
            <label className="mb-4 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Добавить вид ремонта
              <select
                className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800"
                value=""
                disabled={loadingWorkTypeId !== null}
                onChange={(event) => {
                  if (event.target.value) void addRepair(event.target.value);
                }}
              >
                <option value="">Выберите...</option>
                {workTypes.map((workType) => (
                  <option key={workType.id} value={workType.id}>
                    {workType.code} — {workType.name}
                  </option>
                ))}
              </select>
            </label>
            {localRepairs.length === 0 ? (
              <div className="rounded-lg border border-dashed p-8 text-center text-sm text-gray-500">
                <Wrench className="mx-auto mb-2 h-6 w-6" />
                Пока не добавлены виды ремонта
              </div>
            ) : (
              <ul className="space-y-2">
                {localRepairs.map((repair) => {
                  const workType = workTypes.find((item) => item.id === repair.workTypeId);
                  return (
                    <li key={repair.id} className="flex items-center gap-2 rounded-lg border p-3 dark:border-gray-700">
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-gray-900 dark:text-white">
                          {repair.kind} — {workType?.name ?? "Вид ремонта"}
                        </p>
                        <p className="text-xs text-gray-500">Позиций ТМЦ: {repair.rows.length}</p>
                      </div>
                      <button
                        onClick={() => setSelectedRepairId(repair.id)}
                        className="rounded-md border px-3 py-1.5 text-sm text-blue-700 dark:border-gray-600 dark:text-blue-300"
                      >
                        ТМЦ
                      </button>
                      <button
                        aria-label="Удалить вид ремонта"
                        onClick={() => setLocalRepairs((current) => current.filter((item) => item.id !== repair.id))}
                        className="rounded p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-950"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
          <footer className="flex justify-end gap-2 border-t p-4 dark:border-gray-700">
            <button onClick={onClose} className="rounded-md border px-4 py-2 text-sm">Отмена</button>
            <button
              onClick={() => onSave(localRepairs)}
              disabled={localRepairs.length === 0}
              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              <Plus className="h-4 w-4" /> Применить
            </button>
          </footer>
        </section>
      </div>
      {selectedRepair && (
        <TmcModal
          workTypeId={selectedRepair.workTypeId}
          workTypeName={selectedRepair.kind}
          departmentId={departmentId}
          rows={selectedRepair.rows}
          nomenclature={nomenclature}
          norms={norms}
          onSave={(rows) => saveRows(selectedRepair.id, rows)}
          onClose={() => setSelectedRepairId(null)}
        />
      )}
    </>
  );
}
