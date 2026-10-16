# Localization inventory

Scan date: 2026-10-16. This is a source inventory, not a claim that all listed text has been translated. The scan searched `app/` and `components/` TypeScript files for Cyrillic characters. It can miss English text and text assembled at runtime.

## Source files containing Cyrillic UI or route text

- `app/dashboard/admin/translations/page.tsx` — translation editor; main labels use `t()`, entity labels use the locale dictionary.
- `app/dashboard/admin/users/page.tsx` — user management; still needs full `t()` coverage.
- `app/dashboard/analytics/_components/useAnalyticsData.ts` — error and analytics labels; still needs locale-aware API/UI review.
- `app/dashboard/analytics/loading.tsx` — loading label; still needs translation.
- `app/dashboard/analytics/page.tsx` — charts, filters, tables, empty/error states; still needs full translation.
- `app/dashboard/directories/employees/page.tsx` — employee CRUD; still needs full translation.
- `app/dashboard/directories/maintenance-intervals/page.tsx` — interval CRUD; still needs full translation.
- `app/dashboard/directories/page.tsx` — directory navigation; still needs translation.
- `app/dashboard/directories/sections/page.tsx` — section CRUD; still needs full translation.
- `app/dashboard/directories/work-types/page.tsx` — work type, subtask and material UI; still needs full translation.
- `app/dashboard/layout.tsx` — navigation/current-page labels use `t()`; role, account and accessibility text are only partly translated.
- `app/dashboard/loading.tsx` — loading label; still needs translation.
- `app/dashboard/maintenance/page.tsx` — maintenance settings and schedule; still needs full translation.
- `app/dashboard/os/loading.tsx` — loading label; still needs translation.
- `app/dashboard/os/page.tsx` — type/status display receives localized API labels; most controls and messages remain Russian.
- `app/dashboard/page.tsx` — date, headings, chart labels and selected cards use `t()`; many visible strings remain Russian.
- `app/dashboard/reports/page.tsx` — dates and several report labels use locale-aware formatting/API labels; many controls remain Russian.
- `app/dashboard/tmc/page.tsx` — nomenclature and linked work type labels use localized API values; most UI remains Russian.
- `app/dashboard/work-orders/_components/CreateWorkOrderModal.tsx` — form and validation; still needs full translation.
- `app/dashboard/work-orders/_components/RepairItemsModal.tsx` — linked work type names use localized values; other labels remain Russian.
- `app/dashboard/work-orders/_components/TmcModal.tsx` — linked nomenclature names use localized values; other labels remain Russian.
- `app/dashboard/work-orders/_components/ViewEditOrderModal.tsx` — section label uses localized value; other labels remain Russian.
- `app/dashboard/work-orders/_components/WorkOrderList.tsx` — section label uses localized value; other labels remain Russian.
- `app/dashboard/work-orders/loading.tsx` — loading label; still needs translation.
- `app/dashboard/work-orders/page.tsx` — section/work type dropdowns use localized names; remaining page text needs translation.
- `app/input/route.ts` — route-side text; confirm whether any of it is user-facing.
- `app/layout.tsx` — metadata remains Russian and needs locale-aware values.
- `app/auth/login/page.tsx` — main login copy uses `t()`; validation/API error text still needs coverage.
- `components/theme-switcher.tsx` — theme menu labels; still needs translation.

## Dynamic business data

Translation tables and API translation management cover departments, sections, work types, subtasks, nomenclature, fixed asset types, and fixed asset statuses. Existing canonical names and IDs remain unchanged. If a translation is missing, API display fields fall back to the canonical value and expose a `translation_missing` flag. Existing free text is not machine translated.

The translation editor is available at `/dashboard/admin/translations` to admins. The fixed asset type/status catalog currently contains the existing codes and translations; creating new codes and managing active state are not implemented. User profile locale storage is not implemented; locale currently persists in a validated browser cookie.

## Remaining localization work

- Translate every remaining page, component, form, validation/error message, accessibility label, confirmation dialog, and loading/empty state in the list above.
- Localize all analytics and dashboard API labels, including repair-kind codes where they represent a work type.
- Make filtering and sorting use localized labels across the ordinary resource endpoints, not only the translation editor.
- Add locale-aware display/validation for backend errors and inspect all exports beyond report CSV.
- Review login, permission/user management, all CRUD flows, and all three locales in a browser.
- Add and run migration/API/UI/export/fallback tests in an authorized test environment.
