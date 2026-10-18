/**
 * Centralized API client for the FastAPI backend.
 *
 * Features:
 * - Uses fetch for requests.
 * - Automatically manages and injects JWT for authorization.
 * - Provides typed methods for resources (e.g., auth, sections).
 * - Keeps access tokens in memory and sends refresh cookies with requests.
 * - Centralized error handling.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8010/api/v1";

let inMemoryAccessToken: string | null = null;
let accessTokenExpiresAt = 0;
let refreshRequest: Promise<AccessTokenResponse> | null = null;

type ApiRequestOptions = {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
  body?: unknown;
  params?: Record<string, string | number | boolean>;
  isPublic?: boolean;
  responseType?: "json" | "blob";
  suppress404Log?: boolean;
  suppressNetworkLog?: boolean;
};

export class ApiHttpError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiHttpError";
  }
}

async function request<T>(options: ApiRequestOptions): Promise<T> {
  const { method, path, body, params, isPublic = false, responseType = "json", suppress404Log = false, suppressNetworkLog = false } = options;

  const url = new URL(`${API_BASE_URL}${path}`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.append(key, String(value));
      }
    });
  }

  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };

  if (typeof document !== "undefined") {
    const localeCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("toir-locale="))
      ?.slice("toir-locale=".length);
    const locale = localeCookie ? decodeURIComponent(localeCookie) : "ru";
    headers["Accept-Language"] = ["uz-Latn", "uz-Cyrl", "ru"].includes(locale) ? locale : "ru";
  }

  if (!isPublic) {
    if (!inMemoryAccessToken) {
      // If no token, try to refresh it. This handles the initial load case.
      await api.auth.refresh();
    }
    if (!inMemoryAccessToken) throw new Error("No authentication token found.");
    headers["Authorization"] = `Bearer ${inMemoryAccessToken}`;
  }

  try {
    const response = await fetch(url.toString(), {
      method,
      headers,
      credentials: "include",
      body: body === undefined ? undefined : JSON.stringify(body),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: response.statusText }));
      
      // If 401 Unauthorized, try to refresh the token and retry the request once.
      if (
        response.status === 401 &&
        !["/auth/login", "/auth/refresh", "/auth/logout"].includes(options.path)
      ) {
        try {
          await api.auth.refresh();
          // Retry the original request with the new token
          headers["Authorization"] = `Bearer ${inMemoryAccessToken}`;
          const retryResponse = await fetch(url.toString(), {
            method,
            headers,
            credentials: "include",
            body: body === undefined ? undefined : JSON.stringify(body),
          });
          if (!retryResponse.ok) throw new Error(errorData.detail || `HTTP error! status: ${retryResponse.status}`);
          if (retryResponse.status === 204) return null as T;
          return (responseType === "blob" ? await retryResponse.blob() : await retryResponse.json()) as T;
        } catch (refreshError) {
          throw refreshError; // If refresh fails, propagate the error
        }
      }
      throw new ApiHttpError(errorData.detail || `HTTP error! status: ${response.status}`, response.status);
    }

    // Handle cases with no content in response body (e.g., 204 No Content)
    if (response.status === 204) {
      return null as T;
    }

    return (responseType === "blob" ? await response.blob() : await response.json()) as T;
  } catch (error) {
    const isSuppressed404 = suppress404Log && error instanceof ApiHttpError && error.status === 404;
    const isSuppressedNetworkError = suppressNetworkLog && error instanceof TypeError;
    if (!isSuppressed404 && !isSuppressedNetworkError) {
      console.error(`API request failed: ${method} ${path}`, error);
    }
    // Re-throw the error so it can be caught by the caller
    throw error;
  }
}

// --- Auth Module ---

type LoginRequest = { email: string; password: string };
type AccessTokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
};
type LoginResponse = AccessTokenResponse & { user: CurrentUser };
export type CurrentUser = {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "operator" | "master" | "management";
  is_active: boolean;
  section_id: string | null;
  section?: string | null;
};

const auth = {
  async login(credentials: LoginRequest): Promise<LoginResponse> {
    const response = await request<AccessTokenResponse>({
      method: "POST",
      path: "/auth/login",
      body: credentials,
      isPublic: true,
    });
    inMemoryAccessToken = response.access_token;
    accessTokenExpiresAt = Date.now() + response.expires_in * 1000;
    try {
      const user = await request<CurrentUser>({
        method: "GET",
        path: "/auth/me",
      });
      return { ...response, user };
    } catch (error) {
      inMemoryAccessToken = null;
      accessTokenExpiresAt = 0;
      try {
        await request<null>({
          method: "POST",
          path: "/auth/logout",
          isPublic: true,
        });
      } catch {
        throw new Error("Could not load the user profile or clear the login session.");
      }
      throw error;
    }
  },

  async logout(): Promise<void> {
    try {
      await request<null>({
        method: "POST",
        path: "/auth/logout",
        isPublic: true,
      });
    } finally {
      inMemoryAccessToken = null;
      accessTokenExpiresAt = 0;
    }
  },

  async me(): Promise<CurrentUser> {
    return request<CurrentUser>({
      method: "GET",
      path: "/auth/me",
    });
  },

  async getAccessToken(): Promise<string> {
    if (!inMemoryAccessToken || accessTokenExpiresAt <= Date.now() + 30_000) {
      await this.refresh();
    }
    if (!inMemoryAccessToken) throw new Error("No authentication token found.");
    return inMemoryAccessToken;
  },

  async refresh(): Promise<AccessTokenResponse> {
    if (!refreshRequest) {
      refreshRequest = request<AccessTokenResponse>({
        method: "POST",
        path: "/auth/refresh",
        isPublic: true,
      })
        .then((response) => {
          inMemoryAccessToken = response.access_token;
          accessTokenExpiresAt = Date.now() + response.expires_in * 1000;
          return response;
        })
        .catch((error: unknown) => {
          inMemoryAccessToken = null;
          accessTokenExpiresAt = 0;
          throw error;
        })
        .finally(() => {
          refreshRequest = null;
        });
    }
    return refreshRequest;
  },
};

type UserRole = CurrentUser["role"];
type UserListParams = ListParams & { q?: string; is_active?: boolean };
type UserCreate = {
  email: string;
  full_name: string;
  password: string;
  role: UserRole;
  section_id: string | null;
};
type UserUpdate = {
  full_name?: string;
  role?: UserRole;
  section_id?: string | null;
  is_active?: boolean;
};

const users = {
  async list(params: UserListParams = {}): Promise<Paginated<CurrentUser>> {
    return request<Paginated<CurrentUser>>({
      method: "GET",
      path: "/users",
      params,
    });
  },

  async create(data: UserCreate): Promise<CurrentUser> {
    return request<CurrentUser>({ method: "POST", path: "/users", body: data });
  },

  async update(id: string, data: UserUpdate): Promise<CurrentUser> {
    return request<CurrentUser>({
      method: "PATCH",
      path: `/users/${id}`,
      body: data,
    });
  },

  async resetPassword(id: string, password: string): Promise<void> {
    await request<null>({
      method: "POST",
      path: `/users/${id}/reset-password`,
      body: { password },
    });
  },
};

export type PermissionEntry = { code: string; module: string; action: string; label: string; granted: boolean };
export type RolePermissionMatrix = { role: "admin" | "operator" | "master" | "management"; permissions: PermissionEntry[]; changed: string[] };
const permissions = {
  async mine(): Promise<{ permissions: string[] }> {
    return request({ method: "GET", path: "/permissions/me" });
  },
  async getRole(role: RolePermissionMatrix["role"]): Promise<RolePermissionMatrix> {
    return request({ method: "GET", path: `/permissions/${role}` });
  },
  async setRole(role: Exclude<RolePermissionMatrix["role"], "admin">, granted: string[]): Promise<RolePermissionMatrix> {
    return request({ method: "PUT", path: `/permissions/${role}`, body: { granted } });
  },
};

// --- Sections Module ---

export type Section = {
  id: string;
  name: string;
  localized_name?: string;
  translation_missing?: boolean;
  department_id: string | null;
  created_at: string;
  updated_at: string;
};

export type Paginated<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

type ListParams = {
  limit?: number;
  offset?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
};

const sections = {
  async list(params: ListParams = { limit: 100, offset: 0 }): Promise<Paginated<Section>> {
    return request<Paginated<Section>>({
      method: "GET",
      path: "/sections",
      params,
    });
  },

  async create(data: { name: string; department_id?: string }): Promise<Section> {
    return request<Section>({
      method: "POST",
      path: "/sections",
      body: data,
    });
  },

  async update(id: string, data: { name?: string; department_id?: string }): Promise<Section> {
    return request<Section>({
      method: "PATCH",
      path: `/sections/${id}`,
      body: data,
    });
  },

  async remove(id: string): Promise<void> {
    await request<null>({
      method: "DELETE",
      path: `/sections/${id}`,
    });
  },
};

// --- Departments Module ---

export type Department = {
  id: string;
  name: string;
  localized_name?: string;
  translation_missing?: boolean;
  color: string;
  created_at: string;
  updated_at: string;
};

const departments = {
  async list(params: ListParams = { limit: 100, offset: 0 }): Promise<Paginated<Department>> {
    return request<Paginated<Department>>({
      method: "GET",
      path: "/departments",
      params,
    });
  },

  async create(data: { name: string; color?: string }): Promise<Department> {
    return request<Department>({
      method: "POST",
      path: "/departments",
      body: data,
    });
  },

  async update(id: string, data: { name?: string; color?: string }): Promise<Department> {
    return request<Department>({
      method: "PATCH",
      path: `/departments/${id}`,
      body: data,
    });
  },

  async remove(id: string): Promise<void> {
    await request<null>({
      method: "DELETE",
      path: `/departments/${id}`,
    });
  },
};

export type Employee = {
  id: string;
  tab_number: string;
  full_name: string;
  position: string | null;
  section_id: string | null;
  location_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type EmployeeListParams = ListParams & { section_id?: string; q?: string; is_active?: boolean };
type EmployeeCreate = Pick<Employee, "tab_number" | "full_name"> &
  Partial<Pick<Employee, "position" | "section_id" | "location_id" | "is_active">>;
type EmployeeUpdate = Partial<EmployeeCreate>;

const employees = {
  async list(params: EmployeeListParams = {}): Promise<Paginated<Employee>> {
    return request<Paginated<Employee>>({ method: "GET", path: "/employees", params });
  },
  async get(id: string): Promise<Employee> {
    return request<Employee>({ method: "GET", path: `/employees/${id}` });
  },
  async create(data: EmployeeCreate): Promise<Employee> {
    return request<Employee>({ method: "POST", path: "/employees", body: data });
  },
  async update(id: string, data: EmployeeUpdate): Promise<Employee> {
    return request<Employee>({ method: "PATCH", path: `/employees/${id}`, body: data });
  },
  async remove(id: string): Promise<void> {
    await request<null>({ method: "DELETE", path: `/employees/${id}` });
  },
};

// --- Nomenclature Module ---

export type Nomenclature = {
  id: string;
  department_id: string;
  department_name: string;
  localized_department_name?: string;
  department_translation_missing?: boolean;
  name: string;
  localized_name?: string;
  translation_missing?: boolean;
  code: string | null;
  unit: string;
  extra: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type NomenclatureListParams = ListParams & {
  q?: string;
  department_id?: string;
};

const nomenclature = {
  async list(params: NomenclatureListParams = { limit: 50, offset: 0 }): Promise<Paginated<Nomenclature>> {
    return request<Paginated<Nomenclature>>({
      method: "GET",
      path: "/nomenclature",
      params,
    });
  },

  async get(id: string): Promise<Nomenclature> {
    return request<Nomenclature>({ method: "GET", path: `/nomenclature/${id}` });
  },

  async create(data: {
    department_id: string;
    name: string;
    code?: string | null;
    unit?: string;
    extra?: Record<string, unknown>;
  }): Promise<Nomenclature> {
    return request<Nomenclature>({
      method: "POST",
      path: "/nomenclature",
      body: data,
    });
  },

  async update(
    id: string,
    data: Partial<{
      department_id: string;
      name: string;
      code: string | null;
      unit: string;
      extra: Record<string, unknown>;
    }>
  ): Promise<Nomenclature> {
    return request<Nomenclature>({
      method: "PATCH",
      path: `/nomenclature/${id}`,
      body: data,
    });
  },

  async remove(id: string): Promise<void> {
    await request<null>({
      method: "DELETE",
      path: `/nomenclature/${id}`,
    });
  },
};

// --- Fixed Assets Module ---

export type FixedAsset = {
  id: string;
  inv_number: string;
  name: string;
  asset_type_label?: string;
  asset_status_label?: string;
  asset_type_translation_missing?: boolean;
  asset_status_translation_missing?: boolean;
  asset_type: string;
  series: string | null;
  depot: string | null;
  section_id: string | null;
  status: string;
  comm_date: string | null;
  year_built: number | null;
  mileage: number | string;
  last_maint_date: string | null;
  next_maint_date: string | null;
  initial_cost: number | string | null;
  owner: string | null;
  wialon_id: string | null;
  wialon_last_sync: string | null;
  wialon_speed: number | string | null;
  wialon_online: boolean;
  failure_probability: number | string | null;
  health_score: number | string | null;
  predicted_failure_km: number | string | null;
  last_ml_update: string | null;
  created_at: string;
  updated_at: string;
};

export type FixedAssetListParams = ListParams & {
  q?: string;
  asset_type?: string;
  status?: string;
  status_behavior?: string;
  section_id?: string;
  depot?: string;
};

export type FixedAssetStats = {
  total: number;
  by_asset_type: Record<string, number>;
  by_status: Record<string, number>;
  by_status_behavior: Record<string, number>;
  by_section: Record<string, number>;
  depots: string[];
};

export type MileageHistory = {
  id: number;
  asset_id: string;
  mileage: number | string;
  source: "wialon" | "manual";
  recorded_at: string;
};

export type FixedAssetCreate = Pick<FixedAsset, "inv_number" | "name" | "asset_type"> &
  Partial<Omit<FixedAsset, "id" | "inv_number" | "name" | "asset_type" | "created_at" | "updated_at" |
    "wialon_last_sync" | "wialon_speed" | "wialon_online" | "failure_probability" |
    "health_score" | "predicted_failure_km" | "last_ml_update">>;

export type FixedAssetUpdate = Partial<Omit<FixedAsset, "id" | "created_at" | "updated_at" |
  "wialon_last_sync" | "wialon_speed" | "wialon_online" | "failure_probability" |
  "health_score" | "predicted_failure_km" | "last_ml_update">>;

const fixedAssets = {
  async list(params: FixedAssetListParams): Promise<Paginated<FixedAsset>> {
    return request<Paginated<FixedAsset>>({ method: "GET", path: "/fixed-assets", params });
  },
  async get(id: string): Promise<FixedAsset> {
    return request<FixedAsset>({ method: "GET", path: `/fixed-assets/${id}` });
  },
  async stats(params: Omit<FixedAssetListParams, "limit" | "offset" | "sort_by" | "sort_order"> = {}): Promise<FixedAssetStats> {
    return request<FixedAssetStats>({ method: "GET", path: "/fixed-assets/stats", params });
  },
  async mileageHistory(id: string, params: { days?: number; limit?: number } = {}): Promise<{
    items: MileageHistory[];
    total: number;
    days: number;
    limit: number;
  }> {
    return request({ method: "GET", path: `/fixed-assets/${id}/mileage-history`, params });
  },
  async setMileage(id: string, mileage: number): Promise<FixedAsset> {
    return request<FixedAsset>({
      method: "POST",
      path: `/fixed-assets/${id}/mileage`,
      body: { mileage },
    });
  },
  async create(data: FixedAssetCreate): Promise<FixedAsset> {
    return request<FixedAsset>({ method: "POST", path: "/fixed-assets", body: data });
  },
  async update(id: string, data: FixedAssetUpdate): Promise<FixedAsset> {
    return request<FixedAsset>({ method: "PATCH", path: `/fixed-assets/${id}`, body: data });
  },
  async remove(id: string): Promise<void> {
    await request<null>({ method: "DELETE", path: `/fixed-assets/${id}` });
  },
};

export type AssetCatalogKind = "types" | "statuses";
export type AssetCatalogColor = "blue" | "green" | "amber" | "orange" | "red" | "gray" | "purple";
export type AssetCatalogBehavior = "operational" | "maintenance" | "repair" | "out_of_service";
export type AssetCatalogItem = {
  code: string; name: string; names: Partial<Record<TranslationLocale, string>>;
  is_active: boolean; usage_count: number; behavior: AssetCatalogBehavior | null; color: AssetCatalogColor;
};
export type AssetCatalogWrite = {
  code?: string; names: Record<TranslationLocale, string>; is_active: boolean;
  behavior?: AssetCatalogBehavior; color: AssetCatalogColor;
};
const fixedAssetCatalogs = {
  async list(kind: AssetCatalogKind, params: ListParams & { q?: string; is_active?: boolean } = {}): Promise<Paginated<AssetCatalogItem>> {
    return request({ method: "GET", path: `/fixed-asset-catalogs/${kind}`, params });
  },
  async create(kind: AssetCatalogKind, payload: AssetCatalogWrite): Promise<AssetCatalogItem> {
    return request({ method: "POST", path: `/fixed-asset-catalogs/${kind}`, body: payload });
  },
  async update(kind: AssetCatalogKind, code: string, payload: AssetCatalogWrite): Promise<AssetCatalogItem> {
    return request({ method: "PUT", path: `/fixed-asset-catalogs/${kind}/${encodeURIComponent(code)}`, body: payload });
  },
  async remove(kind: AssetCatalogKind, code: string): Promise<void> {
    return request({ method: "DELETE", path: `/fixed-asset-catalogs/${kind}/${encodeURIComponent(code)}` });
  },
};

// --- Work Orders Module Types ---

export type WorkOrderItemInput = {
  nomenclature_id?: string | null;
  name: string;
  inv_no?: string | null;
  unit?: string | null;
  qty: number | string;
  note?: string | null;
};

export type WorkOrderRepairInput = {
  work_type_id: string;
  items: WorkOrderItemInput[];
};

export type WorkOrderItem = WorkOrderItemInput & {
  id: string;
  repair_id: string;
  nomenclature_id: string | null;
  localized_nomenclature_name?: string;
  nomenclature_translation_missing?: boolean;
  inv_no: string | null;
  unit: string | null;
  note: string | null;
  qty: number | string;
  sort_order: number;
};

export type WorkOrderRepair = {
  id: string;
  work_order_id: string;
  work_type_id: string;
  work_type_code: string;
  work_type_name: string;
  localized_work_type_name?: string;
  work_type_translation_missing?: boolean;
  sort_order: number;
  items: WorkOrderItem[];
};

export type WorkOrderStatus = "pending" | "in_progress" | "completed" | "cancelled";
export type WorkOrderKind = "planned" | "unplanned" | "repair" | "emergency";
export type WorkOrderPriority = "critical" | "high" | "normal" | "low";

export type WorkOrder = {
  id: string;
  number: string;
  fixed_asset_id: string;
  asset_name: string;
  asset_inv_number: string;
  section_id: string;
  section_name: string;
  localized_section_name?: string;
  section_translation_missing?: boolean;
  department_id: string | null;
  order_kind: WorkOrderKind;
  status: WorkOrderStatus;
  priority: WorkOrderPriority;
  executor_id: string | null;
  executor_name: string | null;
  chief_id: string | null;
  description: string;
  note: string | null;
  date_start: string | null;
  date_end: string | null;
  closed_at: string | null;
  mileage_at_creation: number | string | null;
  mileage_threshold: number | string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  is_overdue: boolean;
  repairs: WorkOrderRepair[];
};

export type WorkOrderCreatePayload = {
  fixed_asset_id: string;
  maintenance_plan_id?: string | null;
  maintenance_interval_id?: string | null;
  maintenance_trigger_mileage?: number | string | null;
  section_id?: string | null;
  department_id?: string | null;
  order_kind: WorkOrderKind;
  priority?: WorkOrderPriority;
  executor_id: string;
  chief_id?: string | null;
  description: string;
  note?: string | null;
  date_start?: string | null;
  date_end?: string | null;
  repairs: WorkOrderRepairInput[];
};

export type WorkOrderUpdatePayload = Partial<{
  fixed_asset_id: string;
  section_id: string;
  department_id: string | null;
  order_kind: WorkOrderKind;
  status: WorkOrderStatus;
  priority: WorkOrderPriority;
  executor_id: string;
  chief_id: string | null;
  description: string;
  note: string | null;
  date_start: string | null;
  date_end: string | null;
  repairs: WorkOrderRepairInput[];
}>;

export type WorkOrderListParams = ListParams & {
  status?: WorkOrderStatus | string;
  open?: boolean;
  section_id?: string;
  department_id?: string;
  fixed_asset_id?: string;
  executor_id?: string;
  work_type_id?: string;
  material_q?: string;
  date_from?: string;
  date_to?: string;
  q?: string;
};

export type WorkOrderNormCheckItem = {
  nomenclature_id: string;
  work_type_id: string;
  qty: number | string;
};

export type WorkOrderNormCheckResult = {
  nomenclature_id: string;
  work_type_id: string;
  qty: number | string;
  standard_quantity: number | string | null;
  deviation_percent: number | string | null;
  warning: boolean;
  estimated_cost: number | string | null;
};

export type WorkOrderTemplateItem = {
  id: string;
  work_type_id: string;
  work_type: string;
  department_id: string | null;
  nomenclature_id: string | null;
  nomenclature_name: string | null;
  name: string | null;
  inv_no: string | null;
  unit: string | null;
  default_quantity: number | string;
  is_required: boolean;
  note: string | null;
};

const workOrders = {
  async list(params: WorkOrderListParams = {}): Promise<Paginated<WorkOrder>> {
    return request<Paginated<WorkOrder>>({
      method: "GET",
      path: "/work-orders",
      params,
    });
  },
  async get(id: string): Promise<WorkOrder> {
    return request<WorkOrder>({ method: "GET", path: `/work-orders/${id}` });
  },
  async create(data: WorkOrderCreatePayload): Promise<WorkOrder> {
    return request<WorkOrder>({
      method: "POST",
      path: "/work-orders",
      body: data,
    });
  },
  async update(id: string, data: WorkOrderUpdatePayload): Promise<WorkOrder> {
    return request<WorkOrder>({
      method: "PATCH",
      path: `/work-orders/${id}`,
      body: data,
    });
  },
  async remove(id: string): Promise<void> {
    await request<null>({ method: "DELETE", path: `/work-orders/${id}` });
  },
  async normCheck(data: {
    department_id: string;
    items: WorkOrderNormCheckItem[];
  }): Promise<WorkOrderNormCheckResult[]> {
    return request<WorkOrderNormCheckResult[]>({
      method: "POST",
      path: "/work-orders/norm-check",
      body: data,
    });
  },
  async templateItems(params: {
    work_type_id: string;
    department_id: string;
  }): Promise<WorkOrderTemplateItem[]> {
    return request<WorkOrderTemplateItem[]>({
      method: "GET",
      path: "/work-orders/template-items",
      params,
    });
  },
};

// --- Maintenance Schedule Module ---

export type MaintenanceScheduleItem = {
  id: string;
  entity_type: "work_order" | "maintenance_plan" | "forecast";
  unit: string;
  type: string;
  startDate: string;
  durationH: number;
  depot: string;
  tech: string;
  status: "upcoming" | "in_progress" | "completed" | "overdue";
  note: string | null;
  mileage: number | string | null;
  remainingKm: number | string | null;
  nextThreshold: number | string | null;
  asset_id: string;
  section_id: string | null;
  interval_id: string | null;
  work_type_id: string | null;
  plan_id: string | null;
  work_order_id: string | null;
};

export type MaintenanceScheduleResponse = {
  schedule: MaintenanceScheduleItem[];
  daily_average_km: number | string | null;
};

export type MaintenanceSettings = {
  daily_average_km: number | string | null;
};

export type MaintenancePlan = {
  id: string;
  asset_id: string;
  asset_name: string;
  asset_inv_number: string;
  section_id: string | null;
  interval_id: string;
  interval_code: string;
  interval_name: string;
  work_type_id: string | null;
  status: "scheduled" | "in_progress" | "completed" | "cancelled";
  trigger_mileage: number | string | null;
  scheduled_date: string | null;
  completed_date: string | null;
  work_order_id: string | null;
};

export type MaintenancePlanUpdate = Partial<{
  status: MaintenancePlan["status"];
  completed_date: string | null;
  work_order_id: string | null;
}>;

const maintenanceSchedule = {
  async get(params: { month: string }): Promise<MaintenanceScheduleResponse> {
    return request<MaintenanceScheduleResponse>({ method: "GET", path: "/maintenance-schedule", params, suppressNetworkLog: true });
  },
};

const maintenancePlans = {
  async list(
    params: ListParams & {
      month?: string;
      asset_id?: string;
      status?: MaintenancePlan["status"];
    } = {}
  ): Promise<Paginated<MaintenancePlan>> {
    return request<Paginated<MaintenancePlan>>({
      method: "GET",
      path: "/maintenance-plan",
      params,
    });
  },
  async update(id: string, data: MaintenancePlanUpdate): Promise<MaintenancePlan> {
    return request<MaintenancePlan>({
      method: "PATCH",
      path: `/maintenance-plan/${id}`,
      body: data,
    });
  },
};

const maintenanceSettings = {
  async get(): Promise<MaintenanceSettings> {
    return request<MaintenanceSettings>({
      method: "GET",
      path: "/maintenance-settings",
    });
  },
  async update(data: { daily_average_km: number }): Promise<MaintenanceSettings> {
    return request<MaintenanceSettings>({
      method: "PATCH",
      path: "/maintenance-settings",
      body: data,
    });
  },
};

// --- Nomenclature Norms Module ---
export type NomenclatureNorm = {
  id: string;
  nomenclature_id: string;
  department_id: string;
  work_type_id: string;
  standard_quantity: number | string;
  avg_price: number | string;
  min_quantity: number | string | null;
  max_quantity: number | string | null;
  nomenclature_name: string;
  nomenclature_code: string | null;
  nomenclature_unit: string;
  work_type_code: string;
  created_at: string;
  updated_at: string;
};

export type NomenclatureNormListParams = ListParams & {
  department_id?: string;
  work_type_id?: string;
  nomenclature_id?: string;
};

export type NomenclatureNormCreate = {
  nomenclature_id: string;
  department_id: string;
  work_type_id: string;
  standard_quantity: number | string;
  avg_price?: number | string;
  min_quantity?: number | string | null;
  max_quantity?: number | string | null;
};

export type NomenclatureNormUpdate = Partial<NomenclatureNormCreate>;

const nomenclatureNorms = {
  async list(params: NomenclatureNormListParams = { limit: 50, offset: 0 }): Promise<Paginated<NomenclatureNorm>> {
    return request<Paginated<NomenclatureNorm>>({ method: "GET", path: "/nomenclature-norms", params });
  },

  async get(id: string): Promise<NomenclatureNorm> {
    return request<NomenclatureNorm>({ method: "GET", path: `/nomenclature-norms/${id}` });
  },

  async create(data: NomenclatureNormCreate): Promise<NomenclatureNorm> {
    return request<NomenclatureNorm>({ method: "POST", path: "/nomenclature-norms", body: data });
  },

  async update(id: string, data: NomenclatureNormUpdate): Promise<NomenclatureNorm> {
    return request<NomenclatureNorm>({
      method: "PATCH",
      path: `/nomenclature-norms/${id}`,
      body: data,
    });
  },

  async remove(id: string): Promise<void> {
    await request<null>({ method: "DELETE", path: `/nomenclature-norms/${id}` });
  },
};

// --- Work Type Templates Module ---
export type WorkTypeTemplate = {
  id: string;
  work_type_id: string;
  work_type: string;
  department_id: string | null;
  nomenclature_id: string | null;
  name: string | null;
  inv_no: string | null;
  unit: string | null;
  default_quantity: number | string;
  is_required: boolean;
  note: string | null;
  nomenclature?: {
    id: string;
    name: string;
    code: string | null;
    unit: string;
  } | null;
};

type WorkTypeTemplateCreate = Omit<WorkTypeTemplate, "id" | "work_type" | "nomenclature">;
type WorkTypeTemplateUpdate = Partial<Omit<WorkTypeTemplateCreate, "work_type_id">>;
type WorkTypeTemplateListParams = ListParams & {
  work_type?: string;
  localized_work_type?: string;
  localized_section_name?: string;
  work_type_id?: string;
  department_id?: string;
};

const workTypeTemplates = {
  async list(params: WorkTypeTemplateListParams = {}): Promise<Paginated<WorkTypeTemplate>> {
    return request<Paginated<WorkTypeTemplate>>({ method: "GET", path: "/work-type-templates", params });
  },
  async create(data: WorkTypeTemplateCreate): Promise<WorkTypeTemplate> {
    return request<WorkTypeTemplate>({ method: "POST", path: "/work-type-templates", body: data });
  },
  async update(id: string, data: WorkTypeTemplateUpdate): Promise<WorkTypeTemplate> {
    return request<WorkTypeTemplate>({ method: "PATCH", path: `/work-type-templates/${id}`, body: data });
  },
  async remove(id: string): Promise<void> {
    await request<null>({ method: "DELETE", path: `/work-type-templates/${id}` });
  },
};

export type WorkSubtask = {
  id: string;
  work_type_id: string;
  name: string;
  localized_name?: string;
  translation_missing?: boolean;
  sort_order: number;
};

export type WorkType = {
  id: string;
  code: string;
  name: string;
  localized_name?: string;
  translation_missing?: boolean;
  description: string | null;
  unit_type: "locomotive" | "wagon";
  sort_order: number;
  created_at: string;
  updated_at: string;
  subtasks: WorkSubtask[];
};

type WorkTypeListParams = ListParams & { unit_type?: WorkType["unit_type"]; q?: string };
type WorkTypeCreate = Pick<WorkType, "code" | "name" | "unit_type"> &
  Partial<Pick<WorkType, "description" | "sort_order">>;
type WorkTypeUpdate = Partial<WorkTypeCreate>;
type WorkSubtaskCreate = Pick<WorkSubtask, "name"> & Partial<Pick<WorkSubtask, "sort_order">>;
type WorkSubtaskUpdate = Partial<WorkSubtaskCreate>;

const workTypes = {
  async list(params: WorkTypeListParams = {}): Promise<Paginated<WorkType>> {
    return request<Paginated<WorkType>>({ method: "GET", path: "/work-types", params });
  },
  async get(id: string): Promise<WorkType> {
    return request<WorkType>({ method: "GET", path: `/work-types/${id}` });
  },
  async create(data: WorkTypeCreate): Promise<WorkType> {
    return request<WorkType>({ method: "POST", path: "/work-types", body: data });
  },
  async update(id: string, data: WorkTypeUpdate): Promise<WorkType> {
    return request<WorkType>({ method: "PATCH", path: `/work-types/${id}`, body: data });
  },
  async remove(id: string): Promise<void> {
    await request<null>({ method: "DELETE", path: `/work-types/${id}` });
  },
  async createSubtask(workTypeId: string, data: WorkSubtaskCreate): Promise<WorkSubtask> {
    return request<WorkSubtask>({
      method: "POST",
      path: `/work-types/${workTypeId}/subtasks`,
      body: data,
    });
  },
  async updateSubtask(
    workTypeId: string,
    subtaskId: string,
    data: WorkSubtaskUpdate
  ): Promise<WorkSubtask> {
    return request<WorkSubtask>({
      method: "PATCH",
      path: `/work-types/${workTypeId}/subtasks/${subtaskId}`,
      body: data,
    });
  },
  async removeSubtask(workTypeId: string, subtaskId: string): Promise<void> {
    await request<null>({
      method: "DELETE",
      path: `/work-types/${workTypeId}/subtasks/${subtaskId}`,
    });
  },
};

export type MaintenanceInterval = {
  id: string;
  work_type_id: string | null;
  code: string;
  name: string;
  interval_km: number | string | null;
  interval_days: number | null;
  asset_types: string[];
  warn_percent: number | string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type MaintenanceIntervalCreate = Omit<MaintenanceInterval, "id" | "created_at" | "updated_at">;
type MaintenanceIntervalUpdate = Partial<MaintenanceIntervalCreate>;
type MaintenanceIntervalListParams = ListParams & { is_active?: boolean };

const maintenanceIntervals = {
  async list(params: MaintenanceIntervalListParams = {}): Promise<Paginated<MaintenanceInterval>> {
    return request<Paginated<MaintenanceInterval>>({
      method: "GET",
      path: "/maintenance-intervals",
      params,
    });
  },
  async get(id: string): Promise<MaintenanceInterval> {
    return request<MaintenanceInterval>({ method: "GET", path: `/maintenance-intervals/${id}` });
  },
  async create(data: MaintenanceIntervalCreate): Promise<MaintenanceInterval> {
    return request<MaintenanceInterval>({ method: "POST", path: "/maintenance-intervals", body: data });
  },
  async update(id: string, data: MaintenanceIntervalUpdate): Promise<MaintenanceInterval> {
    return request<MaintenanceInterval>({
      method: "PATCH",
      path: `/maintenance-intervals/${id}`,
      body: data,
    });
  },
  async remove(id: string): Promise<void> {
    await request<null>({ method: "DELETE", path: `/maintenance-intervals/${id}` });
  },
};

// --- TMC Documents Module ---

type TmcItem = {
  id: string;
  nomenclature_id: string | null;
  localized_nomenclature_name?: string;
  nomenclature_translation_missing?: boolean;
  name: string;
  inv_no: string | null;
  unit: string | null;
  qty: number | string;
  price: number | string | null;
  note: string | null;
  sort_order: number;
};

export type TmcDocument = {
  id: string;
  doc_no: string;
  doc_date: string;
  work_order_id: string | null;
  work_order_number: string | null;
  section_id: string | null;
  work_type_id: string | null;
  created_at: string;
  status: "draft" | "issued" | "closed";
  items: TmcItem[] | null;
  // Joined fields from backend, matching the `TmcDoc` type in the component
  loco?: string;
  work_type?: string;
  depot?: string;
  warehouse?: string;
  issued_by?: string;
  accepted_by?: string;
  chief?: string;
};

type TmcDocumentListParams = ListParams & {
  status?: "draft" | "issued" | "closed";
  department_id?: string;
  work_order_id?: string;
  q?: string;
  date_from?: string;
  date_to?: string;
};

const tmcDocuments = {
  async list(params: TmcDocumentListParams): Promise<Paginated<TmcDocument>> {
    return request<Paginated<TmcDocument>>({ method: "GET", path: "/tmc-documents", params, suppress404Log: true });
  },
  async create(data: Partial<TmcDocument>): Promise<TmcDocument> {
    return request<TmcDocument>({ method: "POST", path: "/tmc-documents", body: data });
  },
  async update(id: string, data: Partial<TmcDocument>): Promise<TmcDocument> {
    return request<TmcDocument>({ method: "PATCH", path: `/tmc-documents/${id}`, body: data });
  },
  async remove(id: string): Promise<void> {
    await request<null>({ method: "DELETE", path: `/tmc-documents/${id}` });
  },
};

// --- Dashboard Module ---
export type DashboardSummary = {
  assets: Array<{
    id: string;
    name: string;
    asset_type: string;
    series: string | null;
    status: string;
    asset_type_label?: string;
    asset_status_label?: string;
    asset_type_translation_missing?: boolean;
    asset_status_translation_missing?: boolean;
    section_id?: string | null;
    localized_section?: string | null;
    section: string | null;
    depot: string | null;
    mileage: number | string;
  }>;
  orders: Array<{
    id: string;
    number: string;
    unit: string;
    section: string;
    section_id: string;
    status: string;
    priority: string;
    description: string;
    created_at: string;
    date_start: string | null;
    tech: string | null;
    repair_kind: string | null;
    localized_repair_kind?: string | null;
    repair_kind_translation_missing?: boolean;
  }>;
  availability: Array<{
    month: string;
    label: string;
    pct: number;
  }>;
};
const dashboard = {
  async getSummary(params: { section_id?: string }): Promise<DashboardSummary> {
    return request<DashboardSummary>({ method: "GET", path: "/dashboard/summary", params });
  },
};

export type AnalyticsBlock =
  | "executive-summary"
  | "section-efficiency"
  | "work-type-efficiency"
  | "monthly-efficiency"
  | "ai-insights-summary"
  | "fleet-health"
  | "work-order-tmc-details"
  | "maintenance-schedule";

const analytics = {
  async list(
    block: AnalyticsBlock,
    params: ListParams & { section_id?: string } = {}
  ): Promise<Paginated<Record<string, unknown>>> {
    return request({
      method: "GET",
      path: `/analytics/${block}`,
      params,
      suppress404Log: true,
    });
  },
};

export type ReportName = "work-orders" | "fixed-assets" | "tmc-documents";
export type ReportParams = ListParams & {
  section_id?: string;
  date_from?: string;
  date_to?: string;
  status?: string;
  asset_type?: string;
  q?: string;
  fixed_asset_id?: string;
  mileage_from?: number | string;
  mileage_to?: number | string;
};

const reports = {
  async list(
    report: ReportName,
    params: ReportParams = {}
  ): Promise<Paginated<Record<string, unknown>>> {
    return request({
      method: "GET",
      path: `/reports/${report}`,
      params,
    });
  },
  async downloadCsv(report: ReportName, params: ReportParams = {}): Promise<Blob> {
    return request<Blob>({
      method: "GET",
      path: `/reports/${report}`,
      params: { ...params, format: "csv" },
      responseType: "blob",
    });
  },
};

export type TranslationLocale = "uz-Latn" | "uz-Cyrl" | "ru";
export type TranslationEntity =
  | "department"
  | "section"
  | "work_type"
  | "work_subtask"
  | "nomenclature"
  | "asset_type"
  | "asset_status";
export type TranslationEntry = {
  id: string;
  source_name: string;
  name: string;
  locale: TranslationLocale;
  translation_missing: boolean;
  translations: Partial<Record<TranslationLocale, string>>;
  missing_locales: TranslationLocale[];
};
export type TranslationDetail = {
  id: string;
  source_name: string;
  translations: Partial<Record<TranslationLocale, string>>;
  missing_locales: TranslationLocale[];
};

const translations = {
  async list(entity: TranslationEntity, params: ListParams & { q?: string } = {}): Promise<Paginated<TranslationEntry>> {
    return request({ method: "GET", path: `/translations/${entity}`, params });
  },
  async get(entity: TranslationEntity, id: string): Promise<TranslationDetail> {
    return request({ method: "GET", path: `/translations/${entity}/${encodeURIComponent(id)}` });
  },
  async set(entity: TranslationEntity, id: string, locale: TranslationLocale, name: string): Promise<TranslationDetail> {
    return request({ method: "PUT", path: `/translations/${entity}/${encodeURIComponent(id)}/${locale}`, body: { name } });
  },
  async remove(entity: TranslationEntity, id: string, locale: TranslationLocale): Promise<void> {
    return request({ method: "DELETE", path: `/translations/${entity}/${encodeURIComponent(id)}/${locale}` });
  },
};

/**
 * Helper function to fetch all items from a paginated API endpoint.
 */
async function fetchAllPaginated<T>(
  listFunc: (params: ListParams & { section_id?: string }) => Promise<Paginated<T>>,
  baseParams: ListParams & { section_id?: string } = {},
  pageSize = 500
): Promise<T[]> {
  const firstPage = await listFunc({ ...baseParams, limit: pageSize, offset: 0 });
  const allItems = firstPage.items;
  const total = firstPage.total;

  if (total > pageSize) {
    const remainingPages = Math.ceil((total - pageSize) / pageSize);
    const pagePromises = [];
    for (let i = 1; i <= remainingPages; i++) {
      pagePromises.push(
        listFunc({ ...baseParams, limit: pageSize, offset: i * pageSize })
      );
    }
    const subsequentPages = await Promise.all(pagePromises);
    subsequentPages.forEach(page => {
      allItems.push(...page.items);
    });
  }

  return allItems;
}


// type WorkOrderListParams = ListParams & {
//   status?: string;
//   section_id?: string;
//   department_id?: string;
//   fixed_asset_id?: string;
//   date_from?: string;
//   date_to?: string;
//   q?: string;
// };



// const workOrders = {
//   async list(params: WorkOrderListParams): Promise<Paginated<WorkOrder>> {
//     return request<Paginated<WorkOrder>>({
//       method: "GET",
//       path: "/work-orders",
//       params,
//     });
//   },

//   async create(data: Partial<WorkOrder>): Promise<WorkOrder> {
//     return request<WorkOrder>({
//       method: "POST",
//       path: "/work-orders",
//       body: data,
//     });
//   },

//   async update(
//     id: string,
//     data: Partial<WorkOrder>
//   ): Promise<WorkOrder> {
//     return request<WorkOrder>({
//       method: "PATCH",
//       path: `/work-orders/${id}`,
//       body: data,
//     });
//   },
// };

// const employees = {
//   async list(params: ListParams): Promise<Paginated<any>> {
//     return request<Paginated<any>>({
//       method: "GET",
//       path: "/employees",
//       params,
//     });
//   },
// };

// const workTypes = {
//   async list(params: ListParams): Promise<Paginated<any>> {
//     return request<Paginated<any>>({
//       method: "GET",
//       path: "/work-types",
//       params,
//     });
//   },
// };

// --- Main API Export ---

export const api = {
  auth,
  users,
  permissions,
  sections,
  departments,
  nomenclature,
  fixedAssets,
  fixedAssetCatalogs,
  workOrders,
  tmcDocuments,
  nomenclatureNorms,
  workTypeTemplates,
  maintenanceSchedule,
  maintenancePlans,
  maintenanceSettings,
  dashboard,
  analytics,
  reports,
  translations,
  employees,
  workTypes,
  maintenanceIntervals,
  fetchAllPaginated,
};
