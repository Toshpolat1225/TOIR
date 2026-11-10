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

export type GtkSuggestion = {
  level: "high" | "ambiguous" | "none";
  candidate_count: number;
  asset: Pick<FixedAsset, "id" | "name" | "inv_number" | "asset_type"> | null;
  signals: string[];
};

export type GtkLocomotive = {
  gtk_id: number;
  name: string | null;
  garage_number: string | null;
  inventory_number: string | null;
  model_name: string | null;
  vehicle_type_name: string | null;
  division_name: string | null;
  start_expl_date: string | null;
  end_expl_date: string | null;
  is_active: boolean;
  first_seen_at: string;
  last_synced_at: string;
  in_train: boolean;
  linked_asset: GtkSuggestion["asset"];
  suggestion: GtkSuggestion;
};

export type GtkCarriage = {
  gtk_id: number;
  name: string | null;
  reg_number: string | null;
  inventory_number: string | null;
  model_name: string | null;
  start_expl_date: string | null;
  end_expl_date: string | null;
  is_active: boolean;
  is_loaded: boolean | null;
  is_not_serviceable: boolean | null;
  lat: number | string | null;
  lon: number | string | null;
  state_duration_s: number | null;
  first_seen_at: string;
  last_synced_at: string;
  in_train: boolean;
  duplicate: boolean;
  linked_asset: GtkSuggestion["asset"];
  suggestion: GtkSuggestion;
};

export type GtkTrainMember = GtkLocomotive & {
  is_main: boolean;
  ord: number;
};

export type GtkTrainCarriageMember = GtkCarriage & { ord: number };

export type GtkTrain = {
  gtk_id: number;
  number: string | null;
  title: string | null;
  begin_time: string | null;
  end_time: string | null;
  is_open: boolean;
  last_synced_at: string;
};

export type GtkTrainDetail = GtkTrain & {
  locomotives: GtkTrainMember[];
  carriages: GtkTrainCarriageMember[];
};

export type GtkSyncRun = {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: "ok" | "error" | "parse_error" | "suspicious" | "login_failed";
  counts: Record<string, number> | null;
  quality: Record<string, unknown> | null;
  error: string | null;
};

export type GtkStatus = {
  enabled: boolean;
  interval_minutes: number;
  auto_sync_stopped: boolean;
  last_run: GtkSyncRun | null;
};

export type GtkMatchReportItem = {
  gtk_id: number;
  kind: "locomotive" | "carriage";
  level: "high" | "ambiguous" | "none" | "duplicate";
  candidate_count: number;
  suggestion: GtkSuggestion["asset"];
  signals: string[];
  linked_asset: GtkSuggestion["asset"];
  duplicate: boolean;
};

export type GtkMatchReport = {
  kind: "locomotive" | "carriage";
  totals: Record<string, number>;
  items: GtkMatchReportItem[];
};

export type GtkWagonMileageLog = {
  id: number;
  wagon_asset_id: string;
  loco_asset_id: string;
  train_gtk_id: number;
  period_from: string;
  period_to: string;
  km: number | string;
  created_at: string;
};

export type GtkWagonMileageList = {
  items: GtkWagonMileageLog[];
  total: number;
  limit: number;
};

export type GtkCreateAssetItem = {
  gtk_id: number;
  status: "created" | "would_create" | "skipped";
  reason: string | null;
  asset: {
    name: string;
    asset_type: "wagon";
    series: string | null;
    inv_number: string;
    mileage: number | string;
    gtk_id: string;
  } | null;
};

export type GtkCreateAssetsResponse = {
  dry_run: boolean;
  created: number;
  would_create: number;
  skipped: number;
  items: GtkCreateAssetItem[];
};

export type GtkFixedAssetDetail = {
  asset_id: string;
  gtk_id: number;
  kind: "locomotive" | "carriage";
  gtk_object: GtkLocomotive | GtkCarriage;
  current_trains: GtkTrainDetail[];
  recent_mileage_logs: GtkWagonMileageLog[];
};

export type GtkLinkRequest = {
  links: Array<{
    asset_id: string;
    gtk_id: number;
    kind: "locomotive" | "carriage";
  }>;
};

const gtk = {
  async status(): Promise<GtkStatus> {
    return request({ method: "GET", path: "/gtk/status" });
  },
  async locomotives(params: ListParams & {
    q?: string;
    is_active?: boolean;
    in_train?: boolean;
  } = {}): Promise<Paginated<GtkLocomotive>> {
    return request({ method: "GET", path: "/gtk/locomotives", params });
  },
  async carriages(params: ListParams & {
    q?: string;
    is_active?: boolean;
    in_train?: boolean;
    duplicate?: boolean;
  } = {}): Promise<Paginated<GtkCarriage>> {
    return request({ method: "GET", path: "/gtk/carriages", params });
  },
  async trains(params: ListParams & { q?: string; is_open?: boolean } = {}): Promise<Paginated<GtkTrain>> {
    return request({ method: "GET", path: "/gtk/trains", params });
  },
  async train(id: number): Promise<GtkTrainDetail> {
    return request({ method: "GET", path: `/gtk/trains/${id}` });
  },
  async matchReport(kind: "locomotive" | "carriage"): Promise<GtkMatchReport> {
    return request({ method: "GET", path: "/gtk/match-report", params: { kind } });
  },
  async downloadMatchReport(kind: "locomotive" | "carriage"): Promise<Blob> {
    return request({
      method: "GET",
      path: "/gtk/match-report",
      params: { kind, format: "csv" },
      responseType: "blob",
    });
  },
  async link(data: GtkLinkRequest): Promise<{ updated: number }> {
    return request({ method: "POST", path: "/gtk/links", body: data });
  },
  async unlink(assetId: string): Promise<void> {
    return request({ method: "DELETE", path: `/gtk/links/${assetId}` });
  },
  async createCarriageAssets(dry_run = true): Promise<GtkCreateAssetsResponse> {
    return request({
      method: "POST",
      path: "/gtk/carriages/create-assets",
      body: { dry_run },
    });
  },
  async createCarriageAsset(gtkId: number, dry_run = true): Promise<GtkCreateAssetsResponse> {
    return request({
      method: "POST",
      path: `/gtk/carriages/${gtkId}/create-asset`,
      body: { dry_run },
    });
  },
  async wagonMileage(params: { asset_id?: string; limit?: number } = {}): Promise<GtkWagonMileageList> {
    return request({ method: "GET", path: "/gtk/wagon-mileage", params });
  },
  async fixedAssetDetail(assetId: string): Promise<GtkFixedAssetDetail> {
    return request({ method: "GET", path: `/fixed-assets/${assetId}/gtk` });
  },
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
    "Accept-Language": "ru",
  };

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
  org_unit_id: string | null;
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

export type AuditAction = "create" | "update" | "delete" | "login" | "logout" | "other";
export type AuditLogEntry = {
  id: string;
  action: AuditAction;
  actor_type: "user" | "system" | "anonymous";
  actor_user_id: string | null;
  actor_name: string | null;
  module: string;
  route: string;
  object_type: string | null;
  object_id: string | null;
  object_label: string | null;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  details: Record<string, unknown> | null;
  created_at: string;
};
export type AuditLogFilters = {
  action?: AuditAction;
  actor_id?: string;
  module?: string;
  object_q?: string;
  q?: string;
  date_from?: string;
  date_to?: string;
};
export type AuditLogFacets = {
  users: Array<{ id: string; name: string }>;
  modules: string[];
};

const auditLogs = {
  async list(params: AuditLogFilters & { limit?: number; offset?: number } = {}): Promise<Paginated<AuditLogEntry>> {
    const query: Record<string, string | number | boolean> = {};
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") query[key] = value;
    }
    return request({ method: "GET", path: "/audit-logs", params: query });
  },
  async filters(): Promise<AuditLogFacets> {
    return request({ method: "GET", path: "/audit-logs/filters" });
  },
  async get(id: string): Promise<AuditLogEntry> {
    return request({ method: "GET", path: `/audit-logs/${id}` });
  },
  async exportCsv(params: AuditLogFilters = {}): Promise<Blob> {
    const query: Record<string, string | number | boolean> = {};
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") query[key] = value;
    }
    return request({
      method: "GET",
      path: "/audit-logs/export.csv",
      params: query,
      responseType: "blob",
    });
  },
};

// --- Sections Module ---

export type Section = {
  id: string;
  name: string;
  department_id: string | null;
  parent_id?: string | null;
  unit_type?: string;
  code?: string | null;
  translations: Partial<Record<"ru", string>>;
  is_active?: boolean;
  is_archived?: boolean;
  sort_order?: number;
  created_at: string;
  updated_at: string;
};

export type SectionTreeNode = Section & { children: SectionTreeNode[] };

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
  async list(params: ListParams & { q?: string; parent_id?: string; include_archived?: boolean; unit_type?: string; is_active?: boolean; department_id?: string } = { limit: 100, offset: 0 }): Promise<Paginated<Section>> {
    return request<Paginated<Section>>({
      method: "GET",
      path: "/sections",
      params,
    });
  },

  async tree(params: { parent_id?: string; include_archived?: boolean; q?: string; unit_type?: string; is_active?: boolean } = {}): Promise<SectionTreeNode[]> {
    return request<SectionTreeNode[]>({
      method: "GET",
      path: "/sections/tree",
      params,
    });
  },

  async create(data: { name: string; department_id?: string; parent_id?: string | null; unit_type?: string; code?: string | null; translations?: Record<"ru", string>; is_active?: boolean; is_archived?: boolean; sort_order?: number }): Promise<Section> {
    return request<Section>({
      method: "POST",
      path: "/sections",
      body: data,
    });
  },

  async update(id: string, data: { name?: string; department_id?: string; parent_id?: string | null; unit_type?: string; code?: string | null; translations?: Record<"ru", string>; is_active?: boolean; is_archived?: boolean; sort_order?: number }): Promise<Section> {
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
  name: string;
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
  asset_type_label?: string | null
  asset_status_label?: string | null
  id: string;
  inv_number: string;
  name: string;
  asset_type: string;
  series: string | null;
  depot: string | null;
  section_id: string | null;
  number: string | null;
  number_normalized: string | null;
  serial_number: string | null;
  model_id: string | null;
  accounting_inv_number: string | null;
  org_unit_id: string | null;
  commissioned_at: string | null;
  decommissioned_at: string | null;
  inv_number_is_provisional: boolean | null;
  status: string;
  comm_date: string | null;
  year_built: number | null;
  mileage: number | string;
  last_maint_date: string | null;
  next_maint_date: string | null;
  initial_cost: number | string | null;
  owner: string | null;
  wialon_id: string | null;
  gtk_id: string | null;
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

export type AssetModel = {
  id: string;
  name: string;
  name_normalized: string;
  asset_type: string;
  series: string | null;
};

export type AssetSource = "wialon" | "gtk" | "vesavoy" | "onec";

export type AssetSourceLink = {
  id: string;
  asset_id: string;
  source: AssetSource;
  external_id: string;
  external_name: string | null;
  status: "active" | "ended";
  link_method: "manual" | "migrated" | "import";
  linked_by: string | null;
  linked_at: string;
  unlinked_at: string | null;
  note: string | null;
};

export type AssetFieldChange = {
  id: number;
  asset_id: string;
  field: string;
  old_value: unknown;
  new_value: unknown;
  source: string;
  kind: "auto_fill" | "conflict" | "manual";
  status: "applied" | "pending" | "accepted" | "rejected";
  created_at: string;
  resolved_by: string | null;
  resolved_at: string | null;
};

export type FixedAssetBulkOrgUnitUpdate = {
  asset_ids: string[];
  org_unit_id: string | null;
};

export type FixedAssetBulkOrgUnitUpdateResponse = {
  updated: number;
};

export type FixedAssetInventoryImportRequest = {
  csv_text?: string;
  rows?: Array<{
    asset_id?: string | null;
    name?: string | null;
    inv_number?: string | null;
    accounting_inv_number?: string | null;
  }>;
};

export type FixedAssetInventoryImportPreviewItem = {
  row_number: number;
  status: "ok" | "not_found" | "ambiguous" | "duplicate" | "empty";
  asset_id: string | null;
  asset_name: string | null;
  inv_number: string | null;
  accounting_inv_number: string | null;
  message: string;
};

export type FixedAssetInventoryImportApplyRow = {
  asset_id: string;
  inv_number: string;
  accounting_inv_number?: string | null;
};

export type FixedAssetInventoryImportApplyResponse = {
  updated: number;
};

export type FixedAssetsPassportImportRequest = {
  json_text: string;
};

export type FixedAssetPassportImportPreviewRow = {
  row_number: number;
  status: "ready" | "duplicate" | "invalid";
  asset_type: string | null;
  name: string | null;
  model: string | null;
  serial_number: string | null;
  inv_number: string | null;
  commissioned_at: string | null;
  decommissioned_at: string | null;
  year_built: number | null;
  section: string | null;
  wialon_id: string | null;
  gtk_id: string | null;
  issue: string | null;
};

export type FixedAssetsPassportImportPreview = {
  source_hash: string;
  total: number;
  current_assets: number;
  ready: number;
  blocked: number;
  duplicate_inventory_groups: number;
  duplicate_number_groups: number;
  type_counts: Record<string, number>;
  section_counts: Record<string, number>;
  items: FixedAssetPassportImportPreviewRow[];
};

export type FixedAssetsPassportImportApplyResponse = {
  deleted_count: number;
  imported_count: number;
};

export type FixedAssetListParams = ListParams & {
  q?: string;
  asset_type?: string;
  status?: string;
  status_behavior?: string;
  section_id?: string;
  depot?: string;
};

export type UnifiedAsset = {
  source: "toir" | "wialon" | "both";
  asset_id: string | null;
  unit_id: string | null;
  name: string;
  asset_type: string | null;
  series: string | null;
  inv_number: string | null;
  status: string | null;
  section: string | null;
  section_id: string | null;
  org_unit_id: string | null;
  mileage: number | string | null;
  wialon_cnm: number | string | null;
  wialon_cneh: number | string | null;
  speed: number | string | null;
  last_message_at: string | null;
  is_online: boolean;
  suspect_absolute: boolean;
};

export type WialonUnitListParams = ListParams & {
  linked?: boolean;
  q?: string;
  online?: boolean;
  suspect?: boolean;
  stale?: boolean;
};

export type WialonCounterSummary = {
  last_status: string | null;
  last_reason: string | null;
};

export type WialonRejectedReading = {
  id: number;
  counter: string;
  value: number | string | null;
  previous_value: number | string | null;
  reading_at: string | null;
  reason: string;
  created_at: string;
};

export type WialonUnit = {
  unit_id: string;
  name: string;
  cnm: number | string | null;
  cneh: number | string | null;
  speed: number | string | null;
  last_message_at: string | null;
  is_online: boolean;
  suspect_absolute: boolean;
  linked_asset: { id: string; name: string; inv_number: string } | null;
  counter_state: WialonCounterSummary | null;
  rejected_count: number;
};

export type WialonUnitDetail = WialonUnit & {
  rejected_readings: WialonRejectedReading[];
};

export type WialonAssetSuggestion = {
  asset_id: string;
  name: string;
  inv_number: string;
  asset_type: string;
  series: string | null;
  section_id: string | null;
  matched_series: boolean;
  matched_numbers: number[];
};

export type WialonCreateAssetRequest = {
  inv_number: string;
  name?: string | null;
  asset_type: "locomotive" | "diesel" | "wagon";
  series?: string | null;
  model_id?: string | null;
  number?: string | null;
  section_id?: string | null;
};

export type WialonCreateAssetResponse = {
  asset: FixedAsset;
  warning: string | null;
};

const wialon = {
  async listUnits(params: WialonUnitListParams = {}): Promise<Paginated<WialonUnit>> {
    return request<Paginated<WialonUnit>>({
      method: "GET",
      path: "/wialon/units",
      params,
    });
  },
  async getUnit(unitId: string): Promise<WialonUnitDetail> {
    return request<WialonUnitDetail>({
      method: "GET",
      path: `/wialon/units/${encodeURIComponent(unitId)}`,
    });
  },
  async suggestions(unitId: string): Promise<{ items: WialonAssetSuggestion[] }> {
    return request<{ items: WialonAssetSuggestion[] }>({
      method: "GET",
      path: `/wialon/units/${encodeURIComponent(unitId)}/suggestions`,
    });
  },
  async createAsset(unitId: string, data: WialonCreateAssetRequest): Promise<WialonCreateAssetResponse> {
    return request<WialonCreateAssetResponse>({
      method: "POST",
      path: `/wialon/units/${encodeURIComponent(unitId)}/create-asset`,
      body: data,
    });
  },
};

export type UnifiedAssetListParams = ListParams & {
  source?: UnifiedAsset["source"];
  asset_type?: string;
  status?: string;
  section_id?: string;
  without_org_unit?: boolean;
  q?: string;
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
  source: "wialon" | "manual" | "gtk";
  recorded_at: string;
};

export type FixedAssetCreate = Pick<FixedAsset, "inv_number" | "asset_type"> &
  Partial<Omit<FixedAsset, "id" | "inv_number" | "name" | "asset_type" | "mileage" | "created_at" | "updated_at" |
    "wialon_last_sync" | "wialon_speed" | "wialon_online" | "failure_probability" |
    "health_score" | "predicted_failure_km" | "last_ml_update">> & {
      name?: string | null;
    };

export type FixedAssetUpdate = Partial<Omit<FixedAsset, "id" | "created_at" | "updated_at" |
  "mileage" |
  "wialon_last_sync" | "wialon_speed" | "wialon_online" | "failure_probability" |
  "health_score" | "predicted_failure_km" | "last_ml_update">>;

export type WagonMileageOpening = {
  id: string;
  asset_id: string;
  mileage_km: number | string;
  effective_at: string;
  created_by: string | null;
  approved_by: string | null;
  supersedes_id: string | null;
  note: string | null;
  status: "pending" | "approved" | "rejected" | "superseded";
  approved_at: string | null;
  created_at: string;
};

export type FixedAssetPassportReport = {
  depot_matches: Array<{
    asset_id: string;
    inv_number: string;
    depot: string;
    candidate_sections: Array<{ id: string; name: string }>;
    org_unit_id: string | null;
  }>;
  depot_unmatched: Array<{
    asset_id: string;
    inv_number: string;
    depot: string;
    candidate_sections: Array<{ id: string; name: string }>;
    org_unit_id: string | null;
    status: "no_match" | "ambiguous";
  }>;
  duplicate_numbers: Array<{
    asset_type: string;
    model_id: string;
    number_normalized: string;
    assets: Array<{ asset_id: string; inv_number: string }>;
  }>;
  invalid_values: Array<{
    asset_id: string;
    inv_number: string;
    issues: string[];
  }>;
};

const fixedAssets = {
  async list(params: FixedAssetListParams): Promise<Paginated<FixedAsset>> {
    return request<Paginated<FixedAsset>>({ method: "GET", path: "/fixed-assets", params });
  },
  async unified(params: UnifiedAssetListParams = {}): Promise<Paginated<UnifiedAsset>> {
    return request<Paginated<UnifiedAsset>>({ method: "GET", path: "/fixed-assets/unified", params });
  },
  async get(id: string): Promise<FixedAsset> {
    return request<FixedAsset>({ method: "GET", path: `/fixed-assets/${id}` });
  },
  async models(params: ListParams & { asset_type?: string; q?: string } = {}): Promise<Paginated<AssetModel>> {
    return request<Paginated<AssetModel>>({ method: "GET", path: "/fixed-assets/models", params });
  },
  async links(id: string, include_ended = true): Promise<{ asset_id: string; items: AssetSourceLink[] }> {
    return request<{ asset_id: string; items: AssetSourceLink[] }>({ method: "GET", path: `/fixed-assets/${id}/links`, params: { include_ended } });
  },
  async linkSource(
    id: string,
    data: { source: AssetSource; external_id: string; external_name?: string | null },
  ): Promise<AssetSourceLink> {
    return request<AssetSourceLink>({ method: "POST", path: `/fixed-assets/${id}/links`, body: data });
  },
  async unlinkSource(id: string, source: AssetSource): Promise<AssetSourceLink> {
    return request<AssetSourceLink>({ method: "DELETE", path: `/fixed-assets/${id}/links/${source}` });
  },
  async stats(params: Omit<FixedAssetListParams, "limit" | "offset" | "sort_by" | "sort_order"> = {}): Promise<FixedAssetStats> {
    return request<FixedAssetStats>({ method: "GET", path: "/fixed-assets/stats", params });
  },
  async passportReport(): Promise<FixedAssetPassportReport> {
    return request<FixedAssetPassportReport>({
      method: "GET",
      path: "/fixed-assets/passport-report",
    });
  },
  async mileageHistory(id: string, params: { days?: number; limit?: number } = {}): Promise<{
    items: MileageHistory[];
    total: number;
    days: number;
    limit: number;
  }> {
    return request({ method: "GET", path: `/fixed-assets/${id}/mileage-history`, params });
  },
  async create(data: FixedAssetCreate): Promise<FixedAsset> {
    return request<FixedAsset>({ method: "POST", path: "/fixed-assets", body: data });
  },
  async update(id: string, data: FixedAssetUpdate): Promise<FixedAsset> {
    return request<FixedAsset>({ method: "PATCH", path: `/fixed-assets/${id}`, body: data });
  },
  async bulkUpdateOrgUnit(
    data: FixedAssetBulkOrgUnitUpdate,
  ): Promise<FixedAssetBulkOrgUnitUpdateResponse> {
    return request<FixedAssetBulkOrgUnitUpdateResponse>({
      method: "POST",
      path: "/fixed-assets/bulk-org-unit",
      body: data,
    });
  },
  async previewInventoryImport(data: FixedAssetInventoryImportRequest): Promise<{
    items: FixedAssetInventoryImportPreviewItem[];
  }> {
    return request<{ items: FixedAssetInventoryImportPreviewItem[] }>({
      method: "POST",
      path: "/fixed-assets/inv-import/preview",
      body: data,
    });
  },
  async applyInventoryImport(rows: FixedAssetInventoryImportApplyRow[]): Promise<FixedAssetInventoryImportApplyResponse> {
    return request<FixedAssetInventoryImportApplyResponse>({
      method: "POST",
      path: "/fixed-assets/inv-import/apply",
      body: { rows },
    });
  },
  async previewPassportJsonImport(
    data: FixedAssetsPassportImportRequest,
  ): Promise<FixedAssetsPassportImportPreview> {
    return request<FixedAssetsPassportImportPreview>({
      method: "POST",
      path: "/fixed-assets/passport-import/preview",
      body: data,
    });
  },
  async applyPassportJsonImport(
    data: FixedAssetsPassportImportRequest & { source_hash: string },
  ): Promise<FixedAssetsPassportImportApplyResponse> {
    return request<FixedAssetsPassportImportApplyResponse>({
      method: "POST",
      path: "/fixed-assets/passport-import/apply",
      body: data,
    });
  },
  async remove(id: string): Promise<void> {
    await request<null>({ method: "DELETE", path: `/fixed-assets/${id}` });
  },
};

const wagonMileage = {
  async openings(params: { asset_id?: string; status?: WagonMileageOpening["status"]; limit?: number; offset?: number } = {}): Promise<{
    items: WagonMileageOpening[];
    total: number;
    limit: number;
    offset: number;
  }> {
    return request({
      method: "GET",
      path: "/wagon-mileage/openings",
      params,
    });
  },
  async submitOpening(data: {
    asset_id: string;
    mileage_km: string | number;
    effective_at: string;
    note?: string;
  }): Promise<WagonMileageOpening> {
    return request({
      method: "POST",
      path: "/wagon-mileage/openings",
      body: data,
    });
  },
  async approveOpening(id: string): Promise<WagonMileageOpening> {
    return request({
      method: "POST",
      path: `/wagon-mileage/openings/${id}/approve`,
    });
  },
};

const assetConflicts = {
  async list(params: ListParams & {
    status?: AssetFieldChange["status"];
  } = {}): Promise<Paginated<AssetFieldChange>> {
    return request<Paginated<AssetFieldChange>>({ method: "GET", path: "/asset-conflicts", params });
  },
  async accept(id: number): Promise<AssetFieldChange> {
    return request<AssetFieldChange>({ method: "POST", path: `/asset-conflicts/${id}/accept` });
  },
  async reject(id: number): Promise<AssetFieldChange> {
    return request<AssetFieldChange>({ method: "POST", path: `/asset-conflicts/${id}/reject` });
  },
};

export type AssetCatalogKind = "types" | "statuses";
export type AssetCatalogColor = "blue" | "green" | "amber" | "orange" | "red" | "gray" | "purple";
export type AssetCatalogBehavior = "operational" | "maintenance" | "repair" | "out_of_service";
export type TranslationLocale = "ru";
export type AssetCatalogItem = {
  code: string; name: string; names: Record<TranslationLocale, string>;
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
  urgency: "high" | "medium" | "low" | null;
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
  urgency: "high" | "medium" | "low" | null;
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
      urgency?: NonNullable<MaintenancePlan["urgency"]>;
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
  sort_order: number;
};

export type WorkType = {
  id: string;
  code: string;
  name: string;
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
    section_id?: string | null;
    section: string | null;
    depot: string | null;
    mileage: number | string;
  }>;
  orders: Array<{
    id: string;
    number: string;
    fixed_asset_id: string;
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
  auditLogs,
  sections,
  departments,
  nomenclature,
  fixedAssets,
  wagonMileage,
  assetConflicts,
  wialon,
  gtk,
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
  employees,
  workTypes,
  maintenanceIntervals,
  fetchAllPaginated,
};
