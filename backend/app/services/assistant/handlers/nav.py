"""nav.open: open a page by name. The page's own permission is checked here (the sidebar rule), not only the intent's."""
from __future__ import annotations

from app.core.permissions import user_has_permission
from app.schemas.assistant import Card, CardItem
from app.services.assistant.catalog import PAGES
from app.services.assistant.handlers._common import clarify, denied, t
from app.services.assistant.registry import handler
from app.services.assistant.types import Ctx, Result, Slots

PAGE_TITLES = {
    "dashboard": ("Dashbord", "Дашборд"), "analytics": ("Analitika", "Аналитика"), "gps": ("GPS: Wialon ↔ GTK", "GPS: Wialon ↔ GTK"), "map": ("Xarita", "Карта"),
    "gps_wagons": ("Vagonlar (sostav bo'yicha)", "Вагоны (по составу)"), "gtk_data": ("GTK ma'lumotlari", "Данные GTK"), "wialon_data": ("Wialon ma'lumotlari", "Данные Wialon"),
    "scales": ("Vesovoy", "Весовая"), "maintenance": ("Texnik xizmat va ta'mirlash", "ТО и ремонты"), "work_orders": ("Naryadlar", "Наряды"), "tmc": ("TMC", "ТМЦ"),
    "reports": ("Hisobotlar", "Отчёты"), "directories": ("Ma'lumotnomalar", "Справочники"), "users": ("Foydalanuvchilar", "Пользователи"), "audit_logs": ("Audit jurnali", "Журнал логов"),
}


@handler("nav.open")
async def open_page(ctx: Ctx, slots: Slots) -> Result:
    if not slots.page or slots.page not in PAGES:
        names = [t(ctx, PAGE_TITLES[k][0], PAGE_TITLES[k][1]) for k in ("map", "gps", "work_orders", "maintenance", "scales")]
        return clarify(ctx, "Qaysi sahifani ochay?", "Какую страницу открыть?", names)
    href, permission, _names = PAGES[slots.page]
    if permission and not await user_has_permission(ctx.db, ctx.user, permission):
        return denied(ctx)
    title = t(ctx, *PAGE_TITLES[slots.page])
    card = Card(kind="text", title=title, tone="info", href=href, items=[CardItem(label=title, href=href)])
    return Result(cards=[card], speak=t(ctx, f"{title} ochilmoqda.", f"Открываю: {title}."), navigate=href)
