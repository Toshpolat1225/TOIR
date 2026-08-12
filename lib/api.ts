/**
 * Centralized API client for the FastAPI backend.
 *
 * Features:
 * - Uses fetch for requests.
 * - Automatically manages and injects JWT for authorization.
 * - Provides typed methods for resources (e.g., auth, sections).
 * - Handles token persistence in localStorage.
 * - Centralized error handling.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "toir_access_token";

// In-memory token storage
let inMemoryAccessToken: string | null = null;
let isRefreshing = false;

type ApiRequestOptions = {
  method: "GET" | "POST" | "PATCH" | "DELETE";
  path: string;
  body?: unknown;
  params?: Record<string, string | number | boolean>;
  isPublic?: boolean;
};

async function request<T>(options: ApiRequestOptions): Promise<T> {
  const { method, path, body, params, isPublic = false } = options;

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
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: response.statusText }));
      
      // If 401 Unauthorized, try to refresh the token and retry the request once.
      if (response.status === 401 && !options.path.includes("/auth/")) {
        try {
          await api.auth.refresh();
          // Retry the original request with the new token
          headers["Authorization"] = `Bearer ${inMemoryAccessToken}`;
          const retryResponse = await fetch(url.toString(), { method, headers, body: body ? JSON.stringify(body) : undefined });
          if (!retryResponse.ok) throw new Error(errorData.detail || `HTTP error! status: ${retryResponse.status}`);
          return retryResponse.status === 204 ? (null as T) : await retryResponse.json();
        } catch (refreshError) {
          throw refreshError; // If refresh fails, propagate the error
        }
      }
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }

    // Handle cases with no content in response body (e.g., 204 No Content)
    if (response.status === 204) {
      return null as T;
    }

    return await response.json();
  } catch (error) {
    console.error(`API request failed: ${method} ${path}`, error);
    // Re-throw the error so it can be caught by the caller
    throw error;
  }
}

// --- Auth Module ---

type LoginRequest = { email: string; password: string };
type TokenResponse = {
  access_token: string; // The only thing the client needs from login
  user: CurrentUser;
};
export type CurrentUser = {
  id: string;
  email: string;
  full_name: string | null;
  role: "admin" | "operator" | "master" | "management";
  is_active: boolean;
};

const auth = {
  async login(credentials: LoginRequest): Promise<TokenResponse> {
    const response = await request<TokenResponse>({
      method: "POST",
      path: "/auth/login",
      body: credentials,
      isPublic: true,
    });
    if (response.access_token) {
      inMemoryAccessToken = response.access_token;
    }
    return response;
  },

  async logout(): Promise<void> {
    inMemoryAccessToken = null;
    await request<null>({
      method: "POST",
      path: "/auth/logout",
    });
  },

  async me(): Promise<CurrentUser> {
    return request<CurrentUser>({
      method: "GET",
      path: "/auth/me",
    });
  },

  async refresh(): Promise<TokenResponse> {
    if (isRefreshing) return Promise.reject("Token refresh already in progress.");
    isRefreshing = true;
    try {
      const response = await request<TokenResponse>({
        method: "POST",
        path: "/auth/refresh",
      });
      inMemoryAccessToken = response.access_token;
      return response;
    } finally {
      isRefreshing = false;
    }
  },
};

// --- Sections Module ---

type Section = {
  id: string;
  name: string;
  department_id: string | null;
  created_at: string;
  updated_at: string;
};

type Paginated<T> = {
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

type Department = {
  id: string;
  name: string;
  color: string | null;
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

// --- Nomenclature Module ---

type Nomenclature = {
  id: string;
  name: string;
  code: string | null;
  unit: string;
  department_id: string;
  department_name?: string; // Joined in backend
};

type NomenclatureListParams = ListParams & {
  name?: string;
  department_id?: string;
};

const nomenclature = {
  async list(params: NomenclatureListParams = { limit: 100, offset: 0 }): Promise<Paginated<Nomenclature>> {
    return request<Paginated<Nomenclature>>({
      method: "GET",
      path: "/nomenclature",
      params,
    });
  },

  async create(data: { name: string; code?: string; unit?: string; department_id: string }): Promise<Nomenclature> {
    return request<Nomenclature>({
      method: "POST",
      path: "/nomenclature",
      body: data,
    });
  },

  async update(id: string, data: Partial<{ name: string; code: string; unit: string; department_id: string }>): Promise<Nomenclature> {
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

type FixedAsset = {
  id: string;
  name: string;
  asset_type: "locomotive" | "wagon" | "diesel" | null;
  depot: string | null;
  status?: "operational" | "maintenance" | "repair" | "out_of_service";
  series: string | null;
  comm_date: string | null;
  year_built: string | null;
  mileage: number | null;
  last_maint_date: string | null;
  inv_number: string | null;
  initial_cost: string | null;
  owner: string | null;
  wialon_last_sync: string | null;
  wialon_online: boolean | null;
};

type FixedAssetListParams = ListParams & {
  name?: string;
  asset_type?: string;
  depot?: string;
  status?: "operational" | "maintenance" | "repair" | "out_of_service";
};

const fixedAssets = {
  async list(params: FixedAssetListParams): Promise<Paginated<FixedAsset>> {
    return request<Paginated<FixedAsset>>({ method: "GET", path: "/fixed-assets", params });
  },
  async create(data: Partial<FixedAsset>): Promise<FixedAsset> {
    return request<FixedAsset>({ method: "POST", path: "/fixed-assets", body: data });
  },
  async update(id: string, data: Partial<FixedAsset>): Promise<FixedAsset> {
    return request<FixedAsset>({ method: "PATCH", path: `/fixed-assets/${id}`, body: data });
  },
  async remove(id: string): Promise<void> {
    await request<null>({ method: "DELETE", path: `/fixed-assets/${id}` });
  },
};

// --- Work Orders Module Types ---

type WorkOrderListItem = {
  id: string;
  unit_type: "locomotive" | "wagon" | "diesel";
  unit: string;
  description: string;
  work_type: string;
  repair_kind: string;
  priority: string;
  status: string;
  tech: string;
  created: string;
  closed: string;
  section: string;
  equipment: string;
  note?: string;
  repair_items?: any[];
  date_start?: string;
  date_end?: string;
  depot?: string;
  chief?: string;
};

type WorkOrderCreatePayload = Omit<WorkOrderListItem, "id" | "created" | "closed">;
type WorkOrderUpdatePayload = Partial<Omit<WorkOrderListItem, "id" | "created">>;

type WorkOrderListParams = ListParams & {
  status?: string;
  section_id?: string;
  department_id?: string;
  fixed_asset_id?: string;
  date_from?: string;
  date_to?: string;
  q?: string;
};

const workOrders = {
  async list(params: WorkOrderListParams): Promise<Paginated<WorkOrderListItem>> {
    return request<Paginated<WorkOrderListItem>>({
      method: "GET",
      path: "/work-orders",
      params,
    });
  },
  async create(data: WorkOrderCreatePayload): Promise<WorkOrderListItem> {
    return request<WorkOrderListItem>({
      method: "POST",
      path: "/work-orders",
      body: data,
    });
  },
  async update(id: string, data: WorkOrderUpdatePayload): Promise<WorkOrderListItem> {
    return request<WorkOrderListItem>({
      method: "PATCH",
      path: `/work-orders/${id}`,
      body: data,
    });
  },
};

// --- Maintenance Schedule Module ---

type ScheduleItem = { id: string; unit: string; type: string; startDate: string; durationH: number; depot: string; tech: string; status: string; note?: string; mileage?: number; remainingKm?: number; nextThreshold?: number; };
type MaintenanceScheduleResponse = { schedule: ScheduleItem[]; };

const maintenanceSchedule = {
  async get(params: { month?: string }): Promise<MaintenanceScheduleResponse> {
    return request<MaintenanceScheduleResponse>({ method: "GET", path: "/maintenance-schedule", params });
  },
};

// --- Nomenclature Norms Module ---
type NomenclatureNorm = {
  id: string;
  nomenclature_id: string;
  department_id: string;
  work_type: string;
  standard_quantity: number;
  avg_price: number;
  nomenclature?: {
    id: string;
    name: string;
    code: string;
    unit: string;
  };
};
const nomenclatureNorms = {
  async list(params: { department_id: string }): Promise<Paginated<NomenclatureNorm>> {
    return request<Paginated<NomenclatureNorm>>({ method: "GET", path: "/nomenclature-norms", params });
  },
};

// --- Work Type Templates Module ---
type WorkTypeTemplate = {
  id: string;
  work_type: string;
  default_quantity: number;
  nomenclature?: {
    id: string;
    name: string;
    code: string;
    unit: string;
  };
};
const workTypeTemplates = {
  async list(params: { work_type: string; department_id: string }): Promise<Paginated<WorkTypeTemplate>> {
    return request<Paginated<WorkTypeTemplate>>({ method: "GET", path: "/work-type-templates", params });
  },
};

// --- TMC Documents Module ---

type TmcItem = {
  no: number;
  name: string;
  invNo: string;
  unit: string;
  qty: number;
  price: number;
  note: string;
};

type TmcDocument = {
  id: string;
  doc_no: string;
  doc_date: string;
  work_order_id: string | null;
  department_id: string | null;
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
};

const tmcDocuments = {
  async list(params: TmcDocumentListParams): Promise<Paginated<TmcDocument>> {
    return request<Paginated<TmcDocument>>({ method: "GET", path: "/tmc-documents", params });
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
type DashboardSummary = {
  kpi: any;
  fleetStatus: any[];
  seriesStats: any[];
  workOrdersTrend: any[];
  availability: any[];
  repairKindStats: any[];
  upcomingOrders: any[];
  recentWorkOrders: any[];
};
const dashboard = {
  async getSummary(params: { section?: string }): Promise<DashboardSummary> {
    return request<DashboardSummary>({ method: "GET", path: "/dashboard/summary", params });
  },
};

// Re-exporting directory APIs for clarity, though they already exist
const employees = {
  async list(params: ListParams): Promise<Paginated<any>> {
    return request<Paginated<any>>({ method: "GET", path: "/employees", params });
  },
};

const workTypes = {
  async list(params: ListParams): Promise<Paginated<any>> {
    return request<Paginated<any>>({ method: "GET", path: "/work-types", params });
  },
};

/**
 * Helper function to fetch all items from a paginated API endpoint.
 */
async function fetchAllPaginated<T>(
  listFunc: (params: any) => Promise<Paginated<T>>,
  baseParams: Record<string, any> = {},
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


// --- Main API Export ---

type WorkOrder = {
  id?: string;
  type: string;
  repairKind: string;
  priority: string;
  status: string;
  tech: string;
  created: string;
  closed: string;
  section: string;
  equipment: string;
  note?: string;
  repairItems?: any[];
  dateStart?: string;
  dateEnd?: string;
  depot?: string;
  chief?: string;
};



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
  sections,
  departments,
  nomenclature,
  fixedAssets,
  workOrders,
  tmcDocuments,
  nomenclatureNorms,
  workTypeTemplates,
  maintenanceSchedule,
  dashboard,
  employees,
  workTypes,
  fetchAllPaginated,
};