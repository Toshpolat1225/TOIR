"use client";

import { useState } from "react";
import { AlertCircle, CheckCircle, Clock, Pencil, X } from "@/components/ui/icons";
import {
  api,
  type Employee,
  type FixedAsset,
  type Nomenclature,
  type NomenclatureNorm,
  type Section,
  type WorkOrder,
  type WorkOrderRepairInput,
  type WorkType,
} from "@/lib/api";
import type { RepairDraft, TmcDraft } from "./types";
import { RepairItemsModal } from "./RepairItemsModal";

type Props = {
  order: WorkOrder;
  canEdit: boolean;
  assets: FixedAsset[];
  employees: Employee[];
  sections: Section[];
  workTypes: WorkType[];
  nomenclature: Nomenclature[];
  norms: NomenclatureNorm[];
  onUpdated: () => void;
  onClose: () => void;
};

const statusLabel: Record<WorkOrder["status"], string> = {
  pending: "Запланировано",
  in_progress: "Выполняется",
  completed: "Выполнено",
  cancelled: "Отменено",
};

function localDateTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function toRepairDrafts(order: WorkOrder): RepairDraft[] {
  return order.repairs.map((repair) => ({
    id: repair.id,
    workTypeId: repair.work_type_id,
    kind: repair.work_type_code,
    rows: repair.items.map((item): TmcDraft => ({
      id: item.id,
      nomenclatureId: item.nomenclature_id,
      name: item.name,
      invNo: item.inv_no ?? "",
      unit: item.unit ?? "",
      qty: String(item.qty),
      note: item.note ?? "",
    })),
  }));
}

function toRepairInputs(repairs: RepairDraft[]): WorkOrderRepairInput[] {
  return repairs.map((repair) => ({
    work_type_id: repair.workTypeId,
    items: repair.rows
      .filter((item) => item.name.trim() && Number(item.qty) > 0)
      .map((item) => ({
        nomenclature_id: item.nomenclatureId,
        name: item.name.trim(),
        inv_no: item.invNo.trim() || null,
        unit: item.unit.trim() || null,
        qty: Number(item.qty),
        note: item.note.trim() || null,
      })),
  }));
}

export function ViewEditOrderModal({
  order,
  canEdit,
  assets,
  employees,
  sections,
  workTypes,
  nomenclature,
  norms,
  onUpdated,
  onClose,
}: Props) {
  const [description, setDescription] = useState(order.description);
  const [note, setNote] = useState(order.note ?? "");
  const [executorId, setExecutorId] = useState(order.executor_id ?? "");
  const [assetId, setAssetId] = useState(order.fixed_asset_id);
  const [sectionId, setSectionId] = useState(order.section_id);
  const [orderKind, setOrderKind] = useState(order.order_kind);
  const [priority, setPriority] = useState(order.priority);
  const [dateStart, setDateStart] = useState(localDateTime(order.date_start));
  const [dateEnd, setDateEnd] = useState(localDateTime(order.date_end));
  const [repairs, setRepairs] = useState(() => toRepairDrafts(order));
  const [repairsOpen, setRepairsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const readOnly =
    !canEdit || order.status === "completed" || order.status === "cancelled";
  const canTransition = !readOnly;

  async function update(patch: Parameters<typeof api.workOrders.update>[1]) {
    setSaving(true);
    setError(null);
    try {
      await api.workOrders.update(order.id, patch);
      onUpdated();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Не удалось обновить наряд. Проверьте допустимость перехода статуса."
      );
    } finally {
      setSaving(false);
    }
  }

  async function save() {
    if (!description.trim()) {
      setError("Описание не может быть пустым");
      return;
    }
    if (!executorId) {
      setError("Выберите исполнителя");
      return;
    }
    if (!sectionId) {
      setError("Выберите участок");
      return;
    }
    if (repairs.length === 0) {
      setError("Должен остаться хотя бы один вид ремонта");
      return;
    }
    await update({
      fixed_asset_id: assetId,
      section_id: sectionId,
      department_id:
        sections.find((section) => section.id === sectionId)?.department_id ?? null,
      order_kind: orderKind,
      priority,
      description: description.trim(),
      note: note.trim() || null,
      executor_id: executorId,
      date_start: dateStart ? new Date(dateStart).toISOString() : null,
      date_end: dateEnd ? new Date(dateEnd).toISOString() : null,
      repairs: toRepairInputs(repairs),
    });
  }

  const departmentId =
    sections.find((section) => section.id === sectionId)?.department_id ??
    order.department_id ??
    null;

  return (
    <>
      <div className="fixed inset-0 z-[60] flex items-center justify-center p-3">
        <button aria-label="Закрыть наряд" className="absolute inset-0 bg-black/60" onClick={onClose} />
        <section className="relative flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-gray-900">
          <header className="flex items-start justify-between border-b p-4 dark:border-gray-700">
            <div>
              <h2 className="font-semibold text-gray-900 dark:text-white">{order.number}</h2>
              <p className="mt-1 text-xs text-gray-500">
                {order.asset_name} · {order.asset_inv_number} · {order.section_name}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-blue-50 px-2 py-1 text-xs text-blue-700 dark:bg-blue-950 dark:text-blue-300">
                  {statusLabel[order.status]}
                </span>
                {order.is_overdue && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-1 text-xs text-red-700 dark:bg-red-950 dark:text-red-300">
                    <AlertCircle className="h-3.5 w-3.5" /> Просрочен
                  </span>
                )}
              </div>
            </div>
            <button aria-label="Закрыть" onClick={onClose}><X className="h-5 w-5" /></button>
          </header>
          <div className="overflow-auto p-4">
            {error && <p role="alert" className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>}
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="text-sm font-medium sm:col-span-2">Основное средство
                <select disabled={readOnly} className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800" value={assetId} onChange={(event) => {
                  const value = event.target.value;
                  setAssetId(value);
                  setSectionId(assets.find((asset) => asset.id === value)?.section_id ?? "");
                }}>
                  {assets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name} · {asset.inv_number}</option>)}
                </select>
              </label>
              <label className="text-sm font-medium">Участок
                <select disabled={readOnly} className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800" value={sectionId} onChange={(event) => setSectionId(event.target.value)}>
                  <option value="">Не назначен</option>
                  {sections.map((section) => <option key={section.id} value={section.id}>{section.name}</option>)}
                </select>
              </label>
              <label className="text-sm font-medium">Вид наряда
                <select disabled={readOnly} className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800" value={orderKind} onChange={(event) => setOrderKind(event.target.value as typeof orderKind)}>
                  <option value="planned">Плановый</option>
                  <option value="unplanned">Внеплановый</option>
                  <option value="repair">Ремонт</option>
                  <option value="emergency">Аварийный</option>
                </select>
              </label>
              <label className="text-sm font-medium sm:col-span-2">Описание
                <textarea disabled={readOnly} className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-sm disabled:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:disabled:bg-gray-800" rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
              </label>
              <label className="text-sm font-medium">Исполнитель
                <select disabled={readOnly} className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-sm disabled:bg-gray-100 dark:border-gray-700 dark:bg-gray-800" value={executorId} onChange={(event) => setExecutorId(event.target.value)}>
                  <option value="">Выберите...</option>
                  {employees.filter((employee) => employee.is_active).map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}
                </select>
              </label>
              <label className="text-sm font-medium">Приоритет
                <select disabled={readOnly} className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800" value={priority} onChange={(event) => setPriority(event.target.value as typeof priority)}>
                  <option value="critical">Критический</option>
                  <option value="high">Высокий</option>
                  <option value="normal">Обычный</option>
                  <option value="low">Низкий</option>
                </select>
              </label>
              <label className="text-sm font-medium">Плановое начало
                <input disabled={readOnly} type="datetime-local" className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800" value={dateStart} onChange={(event) => setDateStart(event.target.value)} />
              </label>
              <label className="text-sm font-medium">Плановое завершение
                <input disabled={readOnly} type="datetime-local" className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800" value={dateEnd} onChange={(event) => setDateEnd(event.target.value)} />
              </label>
              <label className="text-sm font-medium sm:col-span-2">Примечание
                <textarea disabled={readOnly} className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800" rows={2} value={note} onChange={(event) => setNote(event.target.value)} />
              </label>
            </div>
            <div className="mt-4 rounded-lg border p-3 dark:border-gray-700">
              <div className="mb-2 flex items-center justify-between">
                <div>
                  <p className="font-medium">Виды ремонта и ТМЦ</p>
                  <p className="text-xs text-gray-500">{repairs.length} видов ремонта · {repairs.reduce((sum, item) => sum + item.rows.length, 0)} позиций</p>
                </div>
                {!readOnly && (
                  <button onClick={() => setRepairsOpen(true)} className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
                    <Pencil className="h-4 w-4" /> Изменить
                  </button>
                )}
              </div>
              <ul className="space-y-1 text-sm text-gray-600 dark:text-gray-300">
                {repairs.map((repair) => (
                  <li key={repair.id}>
                    {repair.kind} — {workTypes.find((item) => item.id === repair.workTypeId)?.name ?? "Вид ремонта"}: {repair.rows.length} поз.
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <footer className="flex flex-wrap items-center justify-between gap-2 border-t p-4 dark:border-gray-700">
            <div className="flex flex-wrap gap-2">
              {canTransition && order.status === "pending" && (
                <button disabled={saving} onClick={() => void update({ status: "in_progress" })} className="inline-flex items-center gap-2 rounded-md border border-amber-300 px-3 py-2 text-sm text-amber-700">
                  <Clock className="h-4 w-4" /> Начать
                </button>
              )}
              {canTransition && order.status === "in_progress" && (
                <button disabled={saving} onClick={() => void update({ status: "completed" })} className="inline-flex items-center gap-2 rounded-md border border-green-300 px-3 py-2 text-sm text-green-700">
                  <CheckCircle className="h-4 w-4" /> Завершить
                </button>
              )}
              {canTransition && (order.status === "pending" || order.status === "in_progress") && (
                <button disabled={saving} onClick={() => void update({ status: "cancelled" })} className="rounded-md border border-red-300 px-3 py-2 text-sm text-red-700">
                  Отменить
                </button>
              )}
            </div>
            <div className="flex gap-2">
              <button onClick={onClose} className="rounded-md border px-4 py-2 text-sm">Закрыть</button>
              {!readOnly && <button disabled={saving} onClick={() => void save()} className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{saving ? "Сохранение..." : "Сохранить"}</button>}
            </div>
          </footer>
        </section>
      </div>
      {repairsOpen && (
        <RepairItemsModal
          departmentId={departmentId}
          repairs={repairs}
          workTypes={workTypes}
          nomenclature={nomenclature.filter((item) => !departmentId || item.department_id === departmentId)}
          norms={norms}
          onSave={(value) => { setRepairs(value); setRepairsOpen(false); }}
          onClose={() => setRepairsOpen(false)}
        />
      )}
    </>
  );
}
