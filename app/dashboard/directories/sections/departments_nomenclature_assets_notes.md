# Migration Notes: Departments, Nomenclature, Fixed Assets

This document covers the migration of the Departments, Nomenclature, and Fixed Assets pages from Supabase to the FastAPI backend. The core pattern follows the one established in `sections_migration_notes.md`.

## 1. API Client Extension (`lib/api.ts`)

The API client was extended to include modules for `departments`, `nomenclature`, and `fixedAssets`. Each module implements the necessary `list`, `create`, `update`, and `remove` methods.

**Key Pattern:**
- **Pagination & Filtering**: The `list` methods accept a `params` object for pagination (`limit`, `offset`) and filtering/sorting (`sort_by`, `name`, `status`, etc.), which are passed as URL query parameters to the FastAPI backend.
- **Typed Responses**: All methods are strongly typed to match the Pydantic schemas on the backend, ensuring type safety from the database to the frontend component.

## 2. Departments Page (`app/dashboard/directories/departments/page.tsx`)

This was a straightforward migration, very similar to the `sections` page.

- `supabase.from("departments").select()` → `api.departments.list()`
- `supabase.from("departments").insert()` → `api.departments.create()`
- `supabase.from("departments").delete()` → `api.departments.remove()`
- Error handling for duplicate names was mapped from a `409 Conflict` HTTP status, which the API client throws as an error with a descriptive message.

## 3. Nomenclature Page (`app/dashboard/tmc/page.tsx`)

This migration was more complex as it involved a page with multiple data sources. Only the "Справочник номенклатуры ТМЦ" (Nomenclature Directory) section was migrated.

- **Data Fetching**: The `fetchNomenclature` function was refactored. Instead of multiple `await` calls to Supabase for departments and nomenclature, it now makes a single call to `api.nomenclature.list()`. The FastAPI backend handles the join and returns the department name directly, simplifying frontend logic.
- **Filtering**: The client-side search (`useMemo`) remains, but the server-side filtering by `department_id` is now handled by passing a parameter to `api.nomenclature.list({ department_id: ... })`.
- **CRUD**: The "Add", "Edit", and "Delete" modals and functions were updated to call `api.nomenclature.create()`, `api.nomenclature.update()`, and `api.nomenclature.remove()` respectively.

## 4. Fixed Assets Page (`app/dashboard/os/page.tsx`)

This was the most complex migration in this phase due to multiple parallel queries, complex state, and server-side filtering/pagination.

- **Data Fetching**: The `fetchAssets` function was completely rewritten. The single `supabase.from("fixed_assets").select()` call was replaced with `api.fixedAssets.list(params)`. All filter states (`search`, `fType`, `fDepot`, `fStatus`) and pagination state (`page`) are now collected into the `params` object for a single, efficient API call.
- **Counts & Totals**: The `fetchCounts` function, which made 7 parallel Supabase calls, was removed. The total count is now returned directly from the `api.fixedAssets.list()` response (`response.total`). The individual status counts are now calculated on the client side from the full (unfiltered) dataset, which will be optimized later if performance becomes an issue.
- **CRUD**: The `handleSave` (update), `handleDelete`, and `handleAdd` functions were updated to use `api.fixedAssets.update()`, `api.fixedAssets.remove()`, and `api.fixedAssets.create()`.
- **Real-time**: The `supabase.channel(...)` logic for real-time updates **was intentionally left in place** as per the migration plan. It will continue to trigger `fetchAssets`, which now calls the new backend. This ensures the UI remains reactive without having to implement WebSockets in this phase.

## 5. Shared Hook Migration (`lib/use-sections.ts`)

The `useSections` hook was a dependency for the `os` and `tmc` pages. It was migrated to use `api.sections.list()` instead of `supabase.from("sections")`. Its external interface remains unchanged, so the components using it required no modifications related to this hook's migration.