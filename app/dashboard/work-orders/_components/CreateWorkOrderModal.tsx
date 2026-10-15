"use client";

import { useMemo, useState } from "react";
import { AlertCircle, Plus, X } from "@/components/ui/icons";
import {
  api,
  type Employee,
  type FixedAsset,
  type Nomenclature,
  type NomenclatureNorm,
  type Section,
  type WorkOrderCreatePayload,
  type WorkType,
} from "@/lib/api";
import type { RepairDraft } from "./types";
import { RepairItemsModal } from "./RepairItemsModal";

type Props = {
  initialAssetId?: string;
  initialUnit?: string;
  initialSection?: string;
  assets: FixedAsset[];
  employees: Employee[];
  sections: Section[];
  workTypes: WorkType[];
  nomenclature: Nomenclature[];
  norms: NomenclatureNorm[];
  onCreated: () => void;
  onClose: () => void;
};

const inputClass =
  "mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white";

function initialSectionId(sections: Section[], section?: string): string {
  if (!section) return "";
  const match =
    sections.find((item) => item.id === section) ??
    sections.find((item) => item.name.toLocaleLowerCase() === section.toLocaleLowerCase());
  return match?.id ?? "";
}

function inputRows(repairs: RepairDraft[]) {
  return repairs.map((repair) => ({
    work_type_id: repair.workTypeId,
    items: repair.rows
      .filter((row) => row.name.trim() && Number(row.qty) > 0)
      .map((row) => ({
        nomenclature_id: row.nomenclatureId,
        name: row.name.trim(),
        inv_no: row.invNo.trim() || null,
        unit: row.unit.trim() || null,
        qty: Number(row.qty),
        note: row.note.trim() || null,
      })),
  }));
}

export function CreateWorkOrderModal({
  initialAssetId,
  initialUnit,
  initialSection,
  assets,
  employees,
  sections,
  workTypes,
  nomenclature,
  norms,
  onCreated,
  onClose,
}: Props) {
  const preselectedAsset =
    assets.find((asset) => asset.id === initialAssetId) ??
    assets.find((asset) => asset.inv_number === initialUnit || asset.name === initialUnit);
  const [assetId, setAssetId] = useState(preselectedAsset?.id ?? "");
  const [sectionId, setSectionId] = useState(
    initialSectionId(sections, initialSection) || preselectedAsset?.section_id || ""
  );
  const [orderKind, setOrderKind] = useState("unplanned");
  const [priority, setPriority] = useState<"critical" | "high" | "normal" | "low">("normal");
  const [executorId, setExecutorId] = useState("");
  const [description, setDescription] = useState("");
  const [note, setNote] = useState("");
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");
  const [repairs, setRepairs] = useState<RepairDraft[]>([]);
  const [repairsOpen, setRepairsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const selectedAsset = assets.find((asset) => asset.id === assetId);
  const section = sections.find((item) => item.id === sectionId);
  const departmentId = section?.department_id ?? null;
  const employeesInSection = useMemo(
    () =>
      employees.filter(
        (employee) => employee.is_active && (!sectionId || employee.section_id === sectionId)
      ),
    [employees, sectionId]
  );
  const totalItems = repairs.reduce((count, repair) => count + repair.rows.length, 0);

  async function submit() {
    setError(null);
    if (!assetId || !selectedAsset) {
      setError("Выберите основное средство");
      return;
    }
    if (!executorId) {
      setError("Выберите исполнителя");
      return;
    }
    if (!description.trim()) {
      setError("Укажите описание неисправности или работ");
      return;
    }
    if (repairs.length === 0) {
      setError("Добавьте хотя бы один вид ремонта");
      return;
    }
    const payload: WorkOrderCreatePayload = {
      fixed_asset_id: assetId,
      section_id: sectionId || selectedAsset.section_id,
      department_id: departmentId,
      order_kind: orderKind as WorkOrderCreatePayload["order_kind"],
      priority,
      executor_id: executorId,
      description: description.trim(),
      note: note.trim() || null,
      date_start: dateStart ? new Date(dateStart).toISOString() : null,
      date_end: dateEnd ? new Date(dateEnd).toISOString() : null,
      repairs: inputRows(repairs),
    };
    setSaving(true);
    try {
      await api.workOrders.create(payload);
      onCreated();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось создать наряд");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-[60] flex items-center justify-center p-3">
        <button aria-label="Закрыть создание наряда" className="absolute inset-0 bg-black/60" onClick={onClose} />
        <section className="relative flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-gray-900">
          <header className="flex items-center justify-between border-b p-4 dark:border-gray-700">
            <div>
              <h2 className="font-semibold text-gray-900 dark:text-white">Создать наряд-заказ</h2>
              <p className="text-xs text-gray-500">Номер и идентификатор будут назначены сервером</p>
            </div>
            <button aria-label="Закрыть" onClick={onClose}><X className="h-5 w-5" /></button>
          </header>
          <div className="overflow-auto p-4">
            {error && (
              <p role="alert" className="mb-3 flex items-center gap-2 rounded bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
                <AlertCircle className="h-4 w-4" />{error}
              </p>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="text-sm font-medium">Основное средство *
                <select className={inputClass} value={assetId} onChange={(event) => {
                  const value = event.target.value;
                  setAssetId(value);
                  setSectionId(assets.find((asset) => asset.id === value)?.section_id ?? "");
                }}>
                  <option value="">Выберите ОС...</option>
                  {assets.map((asset) => (
                    <option key={asset.id} value={asset.id}>{asset.name} · {asset.inv_number}</option>
                  ))}
                </select>
              </label>
              <label className="text-sm font-medium">Участок
                <select className={inputClass} value={sectionId} onChange={(event) => setSectionId(event.target.value)}>
                  <option value="">По участку ОС</option>
                  {sections.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
              <label className="text-sm font-medium">Вид наряда *
                <select className={inputClass} value={orderKind} onChange={(event) => setOrderKind(event.target.value)}>
                  <option value="planned">Плановый</option>
                  <option value="unplanned">Внеплановый</option>
                  <option value="repair">Ремонт</option>
                  <option value="emergency">Аварийный</option>
                </select>
              </label>
              <label className="text-sm font-medium">Приоритет
                <select className={inputClass} value={priority} onChange={(event) => setPriority(event.target.value as typeof priority)}>
                  <option value="critical">Критический</option>
                  <option value="high">Высокий</option>
                  <option value="normal">Обычный</option>
                  <option value="low">Низкий</option>
                </select>
              </label>
              <label className="text-sm font-medium">Исполнитель *
                <select className={inputClass} value={executorId} onChange={(event) => setExecutorId(event.target.value)}>
                  <option value="">Выберите сотрудника...</option>
                  {employeesInSection.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}
                </select>
              </label>
              <label className="text-sm font-medium">Плановое начало
                <input className={inputClass} type="datetime-local" value={dateStart} onChange={(event) => setDateStart(event.target.value)} />
              </label>
              <label className="text-sm font-medium">Плановое завершение
                <input className={inputClass} type="datetime-local" value={dateEnd} onChange={(event) => setDateEnd(event.target.value)} />
              </label>
              <label className="text-sm font-medium sm:col-span-2">Описание неисправности / работ *
                <textarea className={inputClass} rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
              </label>
              <label className="text-sm font-medium sm:col-span-2">Примечание
                <textarea className={inputClass} rows={2} value={note} onChange={(event) => setNote(event.target.value)} />
              </label>
            </div>
            <div className="mt-4 flex items-center justify-between rounded-lg border p-3 dark:border-gray-700">
              <div>
                <p className="font-medium text-gray-900 dark:text-white">Виды ремонта и ТМЦ *</p>
                <p className="text-xs text-gray-500">Видов: {repairs.length} · позиций: {totalItems}</p>
              </div>
              <button onClick={() => setRepairsOpen(true)} className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm text-blue-700 dark:border-gray-600 dark:text-blue-300">
                <Plus className="h-4 w-4" /> Настроить
              </button>
            </div>
          </div>
          <footer className="flex justify-end gap-2 border-t p-4 dark:border-gray-700">
            <button disabled={saving} onClick={onClose} className="rounded-md border px-4 py-2 text-sm">Отмена</button>
            <button disabled={saving} onClick={() => void submit()} className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
              {saving ? "Сохранение..." : "Создать наряд"}
            </button>
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
