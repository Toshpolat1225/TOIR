"use client";

import { AlertCircle, Calendar, Plus, Search, Wrench } from "@/components/ui/icons";
import type { Employee, FixedAsset, Section, WorkOrder } from "@/lib/api";
import type { WorkOrderTab } from "./types";

type Props = {
  items: WorkOrder[];
  total: number;
  loading: boolean;
  tab: WorkOrderTab;
  query: string;
  sectionId: string;
  assetId: string;
  sections: Section[];
  assets: FixedAsset[];
  employees: Employee[];
  canCreate: boolean;
  onTabChange: (tab: WorkOrderTab) => void;
  onQueryChange: (value: string) => void;
  onSectionChange: (value: string) => void;
  onAssetChange: (value: string) => void;
  onCreate: () => void;
  onSelect: (order: WorkOrder) => void;
  onPageChange: (offset: number) => void;
  offset: number;
  limit: number;
};

const tabs: Array<{ value: WorkOrderTab; label: string }> = [
  { value: "open", label: "Открытые" },
  { value: "pending", label: "Запланировано" },
  { value: "in_progress", label: "Выполняется" },
  { value: "completed", label: "Выполнено" },
];

const statusNames: Record<WorkOrder["status"], string> = {
  pending: "Запланировано",
  in_progress: "Выполняется",
  completed: "Выполнено",
  cancelled: "Отменено",
};

const statusStyles: Record<WorkOrder["status"], string> = {
  pending: "bg-sky-50 text-sky-700 dark:bg-sky-950 dark:text-sky-300",
  in_progress: "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  completed: "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300",
  cancelled: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString("ru-RU");
}

export function WorkOrderList({
  items,
  total,
  loading,
  tab,
  query,
  sectionId,
  assetId,
  sections,
  assets,
  employees,
  canCreate,
  onTabChange,
  onQueryChange,
  onSectionChange,
  onAssetChange,
  onCreate,
  onSelect,
  onPageChange,
  offset,
  limit,
}: Props) {
  const employeeName = (id: string | null) =>
    employees.find((employee) => employee.id === id)?.full_name ?? "Не назначен";
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + limit, total);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Наряды-заказы</h1>
          <p className="mt-1 text-sm text-gray-500">Управление ремонтными работами и исполнением</p>
        </div>
        {canCreate && (
          <button onClick={onCreate} className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700">
            <Plus className="h-4 w-4" /> Создать наряд
          </button>
        )}
      </div>
      <div className="flex gap-1 overflow-x-auto border-b border-gray-200 dark:border-gray-700">
        {tabs.map((item) => (
          <button
            key={item.value}
            onClick={() => onTabChange(item.value)}
            className={`whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium ${
              tab === item.value
                ? "border-blue-600 text-blue-700 dark:text-blue-300"
                : "border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-gray-200"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="relative sm:col-span-2">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Поиск по номеру, описанию или ОС..."
            className="w-full rounded-md border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm dark:border-gray-700 dark:bg-gray-800"
          />
        </label>
        <select value={sectionId} onChange={(event) => onSectionChange(event.target.value)} className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800">
          <option value="">Все участки</option>
          {sections.map((section) => <option key={section.id} value={section.id}>{section.name}</option>)}
        </select>
        <select value={assetId} onChange={(event) => onAssetChange(event.target.value)} className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800">
          <option value="">Все ОС</option>
          {assets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name} · {asset.inv_number}</option>)}
        </select>
      </div>
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
        {loading ? (
          <div className="p-12 text-center text-sm text-gray-500">Загрузка нарядов...</div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center">
            <Wrench className="mx-auto mb-3 h-8 w-8 text-gray-400" />
            <p className="font-medium text-gray-700 dark:text-gray-200">Наряды не найдены</p>
            <p className="mt-1 text-sm text-gray-500">Измените фильтры или создайте новый наряд</p>
          </div>
        ) : (
          <>
            <div className="divide-y divide-gray-100 dark:divide-gray-800">
              {items.map((order) => (
                <button key={order.id} onClick={() => onSelect(order)} className="block w-full p-4 text-left transition hover:bg-gray-50 dark:hover:bg-gray-800/60">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-blue-700 dark:text-blue-300">{order.number}</span>
                        <span className={`rounded-full px-2 py-0.5 text-xs ${statusStyles[order.status]}`}>{statusNames[order.status]}</span>
                        {order.is_overdue && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-xs text-red-700 dark:bg-red-950 dark:text-red-300">
                            <AlertCircle className="h-3 w-3" /> Просрочен
                          </span>
                        )}
                      </div>
                      <p className="mt-2 truncate font-medium text-gray-900 dark:text-white">{order.description}</p>
                      <p className="mt-1 text-sm text-gray-500">{order.asset_name} · {order.asset_inv_number} · {order.localized_section_name ?? order.section_name}</p>
                      <p className="mt-1 text-xs text-gray-500">
                        {order.repairs.map((repair) => repair.work_type_code).join(", ") || "Без типа ремонта"}
                        {" · "}{employeeName(order.executor_id)}
                      </p>
                    </div>
                    <div className="shrink-0 text-right text-xs text-gray-500">
                      <span className="inline-flex items-center gap-1"><Calendar className="h-3.5 w-3.5" />{formatDate(order.date_start)}</span>
                      {order.date_end && <p className="mt-1">до {formatDate(order.date_end)}</p>}
                    </div>
                  </div>
                </button>
              ))}
            </div>
            <footer className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm dark:border-gray-700">
              <span className="text-gray-500">{pageStart}–{pageEnd} из {total}</span>
              <div className="flex gap-2">
                <button disabled={offset === 0} onClick={() => onPageChange(Math.max(0, offset - limit))} className="rounded border px-3 py-1.5 disabled:opacity-40">Назад</button>
                <button disabled={offset + limit >= total} onClick={() => onPageChange(offset + limit)} className="rounded border px-3 py-1.5 disabled:opacity-40">Далее</button>
              </div>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}
