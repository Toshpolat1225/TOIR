"use client";

import { Suspense, useCallback, useDeferredValue, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, Loader2 } from "@/components/ui/icons";
import {
  api,
  type Employee,
  type FixedAsset,
  type Nomenclature,
  type NomenclatureNorm,
  type Section,
  type WorkOrder,
  type WorkType,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useRealtime } from "@/lib/use-realtime";
import { CreateWorkOrderModal } from "./_components/CreateWorkOrderModal";
import { ViewEditOrderModal } from "./_components/ViewEditOrderModal";
import { WorkOrderList } from "./_components/WorkOrderList";
import type { WorkOrderTab } from "./_components/types";

const PAGE_SIZE = 50;

function WorkOrdersPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { profile } = useAuth();
  const [assets, setAssets] = useState<FixedAsset[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [workTypes, setWorkTypes] = useState<WorkType[]>([]);
  const [nomenclature, setNomenclature] = useState<Nomenclature[]>([]);
  const [norms, setNorms] = useState<NomenclatureNorm[]>([]);
  const [orders, setOrders] = useState<WorkOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [resourceLoading, setResourceLoading] = useState(true);
  const [ordersLoading, setOrdersLoading] = useState(true);
  const [referenceError, setReferenceError] = useState<string | null>(null);
  const [ordersError, setOrdersError] = useState<string | null>(null);
  const [tab, setTab] = useState<WorkOrderTab>("open");
  const [query, setQuery] = useState("");
  const [sectionId, setSectionId] = useState("");
  const [assetId, setAssetId] = useState("");
  const [executorId, setExecutorId] = useState("");
  const [workTypeId, setWorkTypeId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [materialQuery, setMaterialQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [initialAssetId, setInitialAssetId] = useState("");
  const [initialUnit, setInitialUnit] = useState("");
  const [initialSection, setInitialSection] = useState("");
  const [selectedOrder, setSelectedOrder] = useState<WorkOrder | null>(null);
  const deferredQuery = useDeferredValue(query.trim());

  const loadReferenceData = useCallback(async () => {
    setResourceLoading(true);
    try {
      const [
        assetsResult,
        employeesResult,
        sectionsResult,
        workTypesResult,
        nomenclatureResult,
        normsResult,
      ] = await Promise.all([
        api.fixedAssets.list({ limit: 1000, offset: 0 }),
        api.employees.list({ limit: 1000, offset: 0 }),
        api.sections.list({ limit: 1000, offset: 0 }),
        api.workTypes.list({ limit: 1000, offset: 0 }),
        api.nomenclature.list({ limit: 1000, offset: 0 }),
        api.nomenclatureNorms.list({ limit: 1000, offset: 0 }),
      ]);
      setAssets(assetsResult.items);
      setEmployees(employeesResult.items);
      setSections(sectionsResult.items.map((item) => ({
        ...item,
        name: item.localized_name ?? item.name,
      })));
      setWorkTypes(workTypesResult.items.map((item) => ({
        ...item,
        name: item.localized_name ?? item.name,
        subtasks: item.subtasks.map((subtask) => ({
          ...subtask,
          name: subtask.localized_name ?? subtask.name,
        })),
      })));
      setNomenclature(nomenclatureResult.items);
      setNorms(normsResult.items);
      setReferenceError(null);
    } catch (cause) {
      setReferenceError(cause instanceof Error ? cause.message : "Не удалось загрузить справочники");
    } finally {
      setResourceLoading(false);
    }
  }, []);

  const loadOrders = useCallback(async () => {
    setOrdersLoading(true);
    try {
      const params: Parameters<typeof api.workOrders.list>[0] = {
        limit: PAGE_SIZE,
        offset,
        sort_by: "created_at",
        sort_order: "desc",
        ...(tab === "open"
          ? { open: true }
          : { status: tab }),
        ...(sectionId ? { section_id: sectionId } : {}),
        ...(assetId ? { fixed_asset_id: assetId } : {}),
        ...(executorId ? { executor_id: executorId } : {}),
        ...(workTypeId ? { work_type_id: workTypeId } : {}),
        ...(materialQuery.trim() ? { material_q: materialQuery.trim() } : {}),
        ...(dateFrom ? { date_from: new Date(dateFrom).toISOString() } : {}),
        ...(dateTo ? { date_to: new Date(dateTo).toISOString() } : {}),
        ...(deferredQuery ? { q: deferredQuery } : {}),
      };
      const result = await api.workOrders.list(params);
      setOrders(result.items);
      setTotal(result.total);
      setOrdersError(null);
    } catch (cause) {
      setOrders([]);
      setTotal(0);
      setOrdersError(cause instanceof Error ? cause.message : "Не удалось загрузить наряды");
    } finally {
      setOrdersLoading(false);
    }
  }, [assetId, dateFrom, dateTo, deferredQuery, executorId, materialQuery, offset, refreshKey, sectionId, tab, workTypeId]);

  useEffect(() => {
    void loadReferenceData();
  }, [loadReferenceData]);

  useEffect(() => {
    void loadOrders();
  }, [loadOrders]);

  useRealtime(
    useCallback(
      (event) => {
        if (event.resource === "work_orders") void loadOrders();
      },
      [loadOrders]
    ),
    ["work_orders"]
  );

  useEffect(() => {
    if (resourceLoading || searchParams.get("create") !== "1") return;
    setInitialAssetId(searchParams.get("asset_id") ?? "");
    setInitialUnit(searchParams.get("unit") ?? "");
    setInitialSection(searchParams.get("section") ?? "");
    setShowCreate(true);
    router.replace("/dashboard/work-orders");
  }, [resourceLoading, router, searchParams]);

  const canCreate =
    profile?.role === "admin" ||
    profile?.role === "management" ||
    profile?.role === "operator";
  const canEdit =
    profile?.role === "admin" ||
    profile?.role === "management" ||
    profile?.role === "operator" ||
    profile?.role === "master";

  function resetOffsetAnd<T>(setter: (value: T) => void, value: T) {
    setOffset(0);
    setter(value);
  }

  const pageLoading = resourceLoading && assets.length === 0;
  const error = referenceError ?? ordersError;

  return (
    <main className="mx-auto max-w-7xl p-4 sm:p-6">
      {error && (
        <div role="alert" className="mb-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
          {!ordersLoading && (
            <button onClick={() => { void loadReferenceData(); void loadOrders(); }} className="ml-auto underline">
              Повторить
            </button>
          )}
        </div>
      )}
      {pageLoading ? (
        <div className="flex h-80 items-center justify-center gap-3 text-sm text-gray-500">
          <Loader2 className="h-5 w-5 animate-spin" /> Загрузка справочников...
        </div>
      ) : (
        <WorkOrderList
          items={orders}
          total={total}
          loading={ordersLoading}
          tab={tab}
          query={query}
          sectionId={sectionId}
          assetId={assetId}
          executorId={executorId}
          workTypeId={workTypeId}
          dateFrom={dateFrom}
          dateTo={dateTo}
          materialQuery={materialQuery}
          sections={sections}
          assets={assets}
          employees={employees}
          workTypes={workTypes}
          canCreate={canCreate}
          onTabChange={(value) => resetOffsetAnd(setTab, value)}
          onQueryChange={(value) => resetOffsetAnd(setQuery, value)}
          onSectionChange={(value) => resetOffsetAnd(setSectionId, value)}
          onAssetChange={(value) => resetOffsetAnd(setAssetId, value)}
          onExecutorChange={(value) => resetOffsetAnd(setExecutorId, value)}
          onWorkTypeChange={(value) => resetOffsetAnd(setWorkTypeId, value)}
          onDateFromChange={(value) => resetOffsetAnd(setDateFrom, value)}
          onDateToChange={(value) => resetOffsetAnd(setDateTo, value)}
          onMaterialQueryChange={(value) => resetOffsetAnd(setMaterialQuery, value)}
          onClearFilters={() => {
            setOffset(0); setQuery(""); setSectionId(""); setAssetId(""); setExecutorId("");
            setWorkTypeId(""); setDateFrom(""); setDateTo(""); setMaterialQuery("");
          }}
          onCreate={() => {
            setInitialAssetId("");
            setInitialUnit("");
            setInitialSection("");
            setShowCreate(true);
          }}
          onSelect={setSelectedOrder}
          onPageChange={setOffset}
          offset={offset}
          limit={PAGE_SIZE}
        />
      )}
      {showCreate && (
        <CreateWorkOrderModal
          initialAssetId={initialAssetId}
          initialUnit={initialUnit}
          initialSection={initialSection}
          assets={assets}
          employees={employees}
          sections={sections}
          workTypes={workTypes}
          nomenclature={nomenclature}
          norms={norms}
          onCreated={() => {
            setShowCreate(false);
            setOffset(0);
            setRefreshKey((current) => current + 1);
          }}
          onClose={() => setShowCreate(false)}
        />
      )}
      {selectedOrder && (
        <ViewEditOrderModal
          order={selectedOrder}
          canEdit={canEdit}
          assets={assets}
          employees={employees}
          sections={sections}
          workTypes={workTypes}
          nomenclature={nomenclature}
          norms={norms}
          onUpdated={() => {
            setSelectedOrder(null);
            void loadOrders();
          }}
          onClose={() => setSelectedOrder(null)}
        />
      )}
    </main>
  );
}

export default function WorkOrdersPageWrapper() {
  return (
    <Suspense
      fallback={
        <div className="flex h-96 items-center justify-center gap-3 text-sm text-gray-400">
          <Loader2 className="h-5 w-5 animate-spin" /> Загрузка...
        </div>
      }
    >
      <WorkOrdersPage />
    </Suspense>
  );
}
