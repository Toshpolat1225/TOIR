"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Plus, Trash2, X } from "@/components/ui/icons";
import {
  api,
  type Nomenclature,
  type NomenclatureNorm,
  type WorkOrderNormCheckResult,
} from "@/lib/api";
import type { TmcDraft } from "./types";

type Props = {
  workTypeId: string;
  workTypeName: string;
  departmentId: string | null;
  rows: TmcDraft[];
  nomenclature: Nomenclature[];
  norms: NomenclatureNorm[];
  onSave: (rows: TmcDraft[]) => void;
  onClose: () => void;
};

const inputClass =
  "w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white";

function formatNumber(value: number | undefined): string {
  return value === undefined || !Number.isFinite(value)
    ? ""
    : value.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

export function TmcModal({
  workTypeId,
  workTypeName,
  departmentId,
  rows,
  nomenclature,
  norms,
  onSave,
  onClose,
}: Props) {
  const [localRows, setLocalRows] = useState(rows);
  const [checkError, setCheckError] = useState<string | null>(null);
  const requestRows = useMemo(
    () =>
      localRows
        .filter((row) => row.nomenclatureId && Number(row.qty) >= 0)
        .map((row) => ({
          id: row.id,
          nomenclature_id: row.nomenclatureId as string,
          work_type_id: workTypeId,
          qty: row.qty,
        })),
    [localRows, workTypeId]
  );
  const requestKey = JSON.stringify(requestRows);
  const requestRowsRef = useRef(requestRows);
  requestRowsRef.current = requestRows;

  useEffect(() => {
    if (!departmentId || requestRows.length === 0) {
      setCheckError(null);
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      void api.workOrders
        .normCheck({
          department_id: departmentId,
          items: requestRowsRef.current.map(({ nomenclature_id, work_type_id, qty }) => ({
            nomenclature_id,
            work_type_id,
            qty: Number(qty) || 0,
          })),
        })
        .then((results: WorkOrderNormCheckResult[]) => {
          if (!active) return;
          setCheckError(null);
          const resultByNomenclature = new Map(
            results.map((result) => [result.nomenclature_id, result])
          );
          setLocalRows((current) =>
            current.map((row) => {
              if (!row.nomenclatureId) return row;
              const result = resultByNomenclature.get(row.nomenclatureId);
              if (!result) return row;
              const deviation = result.deviation_percent === null
                ? undefined
                : Number(result.deviation_percent);
              const warning =
                result.warning && deviation !== undefined
                  ? `Превышение норматива на ${formatNumber(deviation)}%`
                  : undefined;
              const standardQty = result.standard_quantity === null
                ? undefined
                : Number(result.standard_quantity);
              const estimatedCost = result.estimated_cost === null
                ? undefined
                : Number(result.estimated_cost);
              if (
                row.warning === warning &&
                row.standardQty === standardQty &&
                row.deviationPercent === deviation &&
                row.estimatedCost === estimatedCost
              ) {
                return row;
              }
              return {
                ...row,
                standardQty,
                deviationPercent: deviation,
                estimatedCost,
                warning,
              };
            })
          );
        })
        .catch((error: unknown) => {
          if (active) {
            setCheckError(
              error instanceof Error ? error.message : "Не удалось проверить норматив"
            );
          }
        });
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [departmentId, requestKey]);

  function updateRow(id: string, patch: Partial<TmcDraft>) {
    setLocalRows((current) =>
      current.map((row) => (row.id === id ? { ...row, ...patch } : row))
    );
  }

  function addRow() {
    setLocalRows((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        nomenclatureId: null,
        name: "",
        invNo: "",
        unit: "шт.",
        qty: "1",
        note: "",
      },
    ]);
  }

  function selectNomenclature(rowId: string, nomenclatureId: string) {
    const selected = nomenclature.find((item) => item.id === nomenclatureId);
    if (!selected) {
      updateRow(rowId, { nomenclatureId: null });
      return;
    }
    const norm = norms.find(
      (item) =>
        item.nomenclature_id === selected.id &&
        item.work_type_id === workTypeId &&
        item.department_id === departmentId
    );
    updateRow(rowId, {
      nomenclatureId: selected.id,
      name: selected.name,
      invNo: selected.code ?? "",
      unit: selected.unit,
      standardQty: norm ? Number(norm.standard_quantity) : undefined,
      avgPrice: norm ? Number(norm.avg_price) : undefined,
      estimatedCost: undefined,
      deviationPercent: undefined,
      warning: undefined,
    });
  }

  const total = localRows.reduce(
    (sum, row) => sum + (Number(row.estimatedCost) || 0),
    0
  );

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-3">
      <button
        aria-label="Закрыть окно ТМЦ"
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
      />
      <section className="relative flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-gray-900">
        <header className="flex items-center justify-between border-b border-gray-200 p-4 dark:border-gray-700">
          <div>
            <h2 className="font-semibold text-gray-900 dark:text-white">
              ТМЦ — {workTypeName}
            </h2>
            <p className="text-xs text-gray-500">Нормативная проверка не блокирует сохранение</p>
          </div>
          <button aria-label="Закрыть" onClick={onClose} className="rounded p-1 hover:bg-gray-100 dark:hover:bg-gray-800">
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="overflow-auto p-4">
          {checkError && (
            <p role="alert" className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
              {checkError}
            </p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead>
                <tr className="border-b text-xs text-gray-500">
                  <th className="p-2">Номенклатура / наименование</th>
                  <th className="w-28 p-2">Инв. номер</th>
                  <th className="w-24 p-2">Ед.</th>
                  <th className="w-24 p-2">Кол-во</th>
                  <th className="w-32 p-2 text-right">Стоимость</th>
                  <th className="w-10 p-2" />
                </tr>
              </thead>
              <tbody>
                {localRows.map((row) => (
                  <tr key={row.id} className="border-b align-top">
                    <td className="p-2">
                      <select
                        className={`${inputClass} mb-1`}
                        value={row.nomenclatureId ?? ""}
                        onChange={(event) =>
                          selectNomenclature(row.id, event.target.value)
                        }
                      >
                        <option value="">— вручную —</option>
                        {nomenclature.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name}{item.code ? ` (${item.code})` : ""}
                          </option>
                        ))}
                      </select>
                      <input
                        aria-label="Наименование ТМЦ"
                        className={inputClass}
                        value={row.name}
                        onChange={(event) =>
                          updateRow(row.id, {
                            name: event.target.value,
                            nomenclatureId: null,
                            warning: undefined,
                          })
                        }
                        placeholder="Наименование"
                      />
                      {row.warning && (
                        <p className="mt-1 flex items-center gap-1 text-xs text-amber-700 dark:text-amber-300">
                          <AlertTriangle className="h-3.5 w-3.5" />
                          {row.warning}
                        </p>
                      )}
                      {row.standardQty !== undefined && (
                        <p className="mt-1 text-xs text-gray-500">
                          Норма: {formatNumber(row.standardQty)}
                          {row.deviationPercent !== undefined && ` · отклонение ${formatNumber(row.deviationPercent)}%`}
                        </p>
                      )}
                    </td>
                    <td className="p-2">
                      <input
                        aria-label="Инвентарный номер"
                        className={inputClass}
                        value={row.invNo}
                        onChange={(event) => updateRow(row.id, { invNo: event.target.value })}
                      />
                    </td>
                    <td className="p-2">
                      <input
                        aria-label="Единица измерения"
                        className={inputClass}
                        value={row.unit}
                        onChange={(event) => updateRow(row.id, { unit: event.target.value })}
                      />
                    </td>
                    <td className="p-2">
                      <input
                        aria-label="Количество"
                        type="number"
                        min="0"
                        step="0.001"
                        className={inputClass}
                        value={row.qty}
                        onChange={(event) =>
                          updateRow(row.id, { qty: event.target.value })
                        }
                      />
                    </td>
                    <td className="p-2 text-right">
                      <span className="font-medium text-emerald-700 dark:text-emerald-300">
                        {row.estimatedCost === undefined ? "—" : formatNumber(row.estimatedCost)}
                      </span>
                      {row.avgPrice !== undefined && (
                        <p className="text-xs text-gray-500">
                          {formatNumber(row.avgPrice)} / ед.
                        </p>
                      )}
                      <input
                        aria-label="Примечание"
                        className={`${inputClass} mt-1`}
                        value={row.note}
                        onChange={(event) => updateRow(row.id, { note: event.target.value })}
                        placeholder="Примечание"
                      />
                    </td>
                    <td className="p-2">
                      <button
                        aria-label="Удалить строку"
                        onClick={() =>
                          setLocalRows((current) => current.filter((item) => item.id !== row.id))
                        }
                        className="rounded p-1 text-red-600 hover:bg-red-50 dark:hover:bg-red-950"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
                {localRows.length === 0 && (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-sm text-gray-500">
                      Нет позиций. Добавьте строку или выберите позицию из справочника.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <button
            onClick={addRow}
            className="mt-3 inline-flex items-center gap-2 rounded-md border border-blue-300 px-3 py-2 text-sm text-blue-700 hover:bg-blue-50 dark:border-blue-800 dark:text-blue-300 dark:hover:bg-blue-950"
          >
            <Plus className="h-4 w-4" /> Добавить строку
          </button>
        </div>

        <footer className="flex items-center justify-between border-t border-gray-200 p-4 dark:border-gray-700">
          <span className="text-sm text-gray-600 dark:text-gray-300">
            Расчётная стоимость: <b>{formatNumber(total)} сум</b>
          </span>
          <div className="flex gap-2">
            <button onClick={onClose} className="rounded-md border px-4 py-2 text-sm">Отмена</button>
            <button
              onClick={() => onSave(localRows)}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              Применить
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
