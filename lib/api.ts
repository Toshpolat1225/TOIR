const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"
const TOKEN_KEY = "toir_access_token"

type Scalar = string | number | boolean
type QueryParams = Record<string, Scalar | undefined>

type ApiRequestOptions = {
  method: "GET" | "POST" | "PATCH" | "DELETE"
  path: string
  body?: unknown
  params?: QueryParams
  isPublic?: boolean
}

async function request<T>({ method, path, body, params, isPublic = false }: ApiRequestOptions): Promise<T> {
  const url = new URL(`${API_BASE_URL}${path}`)
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value))
  }

  const headers: HeadersInit = { "Content-Type": "application/json" }
  if (!isPublic) {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) throw new Error("No authentication token found.")
    headers.Authorization = `Bearer ${token}`
  }

  const response = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText })) as { detail?: string }
    throw new Error(error.detail ?? `HTTP error: ${response.status}`)
  }
  return response.status === 204 ? null as T : response.json() as Promise<T>
}

export type Paginated<T> = { items: T[]; total: number; limit: number; offset: number }
export type ListParams = { limit?: number; offset?: number; sort_by?: string; sort_order?: "asc" | "desc" }

export async function fetchAllPaginated<T, P extends ListParams>(
  list: (params: P) => Promise<Paginated<T>>,
  baseParams: Omit<P, "limit" | "offset">,
): Promise<T[]> {
  const firstPage = await list({ ...baseParams, offset: 0 } as P)
  const items = [...firstPage.items]
  let offset = firstPage.offset + firstPage.items.length

  if (firstPage.total > 0 && firstPage.items.length === 0) {
    throw new Error("The API returned an empty first page for a non-empty result set.")
  }
  if (firstPage.limit <= 0) throw new Error("The API returned an invalid pagination limit.")

  while (offset < firstPage.total) {
    const page = await list({ ...baseParams, limit: firstPage.limit, offset } as P)
    if (page.items.length === 0) {
      throw new Error("The API returned an empty page before all records were fetched.")
    }
    items.push(...page.items)
    offset += page.items.length
  }
  return items
}

export type Section = { id: string; name: string; department_id: string | null; created_at: string; updated_at: string }
export type Department = { id: string; name: string; color: string | null; created_at: string; updated_at: string }
export type Nomenclature = { id: string; name: string; code: string | null; unit: string; department_id: string; department_name?: string }
export type FixedAsset = {
  id: string; name: string; asset_type: "locomotive" | "wagon" | "diesel" | null; depot: string | null
  status?: "operational" | "maintenance" | "repair" | "out_of_service"; series: string | null
  comm_date: string | null; year_built: string | null; mileage: number | null; last_maint_date: string | null
  inv_number: string | null; initial_cost: string | null; owner: string | null; wialon_last_sync: string | null; wialon_online: boolean | null
}

export type WorkOrderStatus = "pending" | "in_progress" | "completed" | "cancelled"
export type WorkOrderPriority = "low" | "normal" | "high" | "critical"
export type WorkOrderCreatePayload = {
  id: string
  fixed_asset_id?: string | null
  department_id?: string | null
  section_id?: string | null
  status?: WorkOrderStatus
  priority?: WorkOrderPriority
  repair_kind?: string | null
  description?: string | null
  date_start?: string | null
  date_end?: string | null
}
export type WorkOrderUpdatePayload = Partial<Omit<WorkOrderCreatePayload, "id">>
export type WorkOrderRead = WorkOrderCreatePayload & {
  created_at: string
  updated_at: string
  fixed_asset?: FixedAsset | null
  section?: Section | null
  department?: Department | null
}
export type WorkOrderListParams = ListParams & {
  status?: WorkOrderStatus
  section_id?: string
  department_id?: string
  fixed_asset_id?: string
  date_from?: string
  date_to?: string
  q?: string
}

type Employee = { id: string; full_name: string; position?: string | null }
type WorkType = { id: string; name: string; unit_type?: string | null }
type TmcItem = { no: number; name: string; invNo: string; unit: string; qty: number; price: number; note: string }
type TmcDocument = { id: string; doc_no: string; doc_date: string; work_order_id: string | null; department_id: string | null; status: "draft" | "issued" | "closed"; items: TmcItem[] | null }

const sections = {
  list: (params: ListParams = {}) => request<Paginated<Section>>({ method: "GET", path: "/sections", params }),
  create: (data: { name: string; department_id?: string }) => request<Section>({ method: "POST", path: "/sections", body: data }),
  update: (id: string, data: { name?: string; department_id?: string }) => request<Section>({ method: "PATCH", path: `/sections/${id}`, body: data }),
  remove: (id: string) => request<null>({ method: "DELETE", path: `/sections/${id}` }),
}
const departments = {
  list: (params: ListParams = {}) => request<Paginated<Department>>({ method: "GET", path: "/departments", params }),
}
const nomenclature = {
  list: (params: ListParams & { name?: string; department_id?: string } = {}) => request<Paginated<Nomenclature>>({ method: "GET", path: "/nomenclature", params }),
  create: (data: { name: string; code?: string; unit?: string; department_id: string }) => request<Nomenclature>({ method: "POST", path: "/nomenclature", body: data }),
  update: (id: string, data: Partial<{ name: string; code: string; unit: string; department_id: string }>) => request<Nomenclature>({ method: "PATCH", path: `/nomenclature/${id}`, body: data }),
  remove: (id: string) => request<null>({ method: "DELETE", path: `/nomenclature/${id}` }),
}
const fixedAssets = {
  list: (params: ListParams & { name?: string; asset_type?: string; depot?: string; status?: FixedAsset["status"] } = {}) => request<Paginated<FixedAsset>>({ method: "GET", path: "/fixed-assets", params }),
  create: (data: Partial<FixedAsset>) => request<FixedAsset>({ method: "POST", path: "/fixed-assets", body: data }),
  update: (id: string, data: Partial<FixedAsset>) => request<FixedAsset>({ method: "PATCH", path: `/fixed-assets/${id}`, body: data }),
  remove: (id: string) => request<null>({ method: "DELETE", path: `/fixed-assets/${id}` }),
}
const workOrders = {
  list: (params: WorkOrderListParams = {}) => request<Paginated<WorkOrderRead>>({ method: "GET", path: "/work-orders", params }),
  create: (data: WorkOrderCreatePayload) => request<WorkOrderRead>({ method: "POST", path: "/work-orders", body: data }),
  update: (id: string, data: WorkOrderUpdatePayload) => request<WorkOrderRead>({ method: "PATCH", path: `/work-orders/${id}`, body: data }),
}
const employees = { list: (params: ListParams = {}) => request<Paginated<Employee>>({ method: "GET", path: "/employees", params }) }
const workTypes = { list: (params: ListParams = {}) => request<Paginated<WorkType>>({ method: "GET", path: "/work-types", params }) }
const tmcDocuments = { list: (params: ListParams = {}) => request<Paginated<TmcDocument>>({ method: "GET", path: "/tmc-documents", params }) }

export const api = { sections, departments, nomenclature, fixedAssets, workOrders, employees, workTypes, tmcDocuments, fetchAllPaginated }
