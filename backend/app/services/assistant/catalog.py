"""The command catalogue: every intent the assistant understands (Uzbek Latin, Russian, English), its permission and what it needs.

Matching (see parser.py): the sentence is normalised (lower case, Uzbek apostrophes and Cyrillic-Uzbek letters folded to plain Latin, Russian stays
Cyrillic). A keyword group matches when ANY of its words matches a token; a word of 5+ letters matches as a PREFIX of a token (suffixes: "qayerda",
"qayerdaligini"), a shorter word must equal the token. An intent applies when ALL its `groups` match and its `needs` slots are filled (a missing
asset is taken from the page context when `context_asset`). `boost` groups only add to the score. Keywords are written in the normalised form.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# page key -> (path, permission code, spoken names). Permissions mirror the sidebar (app/dashboard/layout.tsx).
PAGES: dict[str, tuple[str, str | None, tuple[str, ...]]] = {
    "dashboard": ("/dashboard", "dashboard.view", ("dashboard", "dashbord", "bosh sahifa", "главная", "дашборд", "панель")),
    "analytics": ("/dashboard/analytics", "analytics.view", ("analitika", "аналитика", "analytics", "tahlil")),
    "gps": ("/dashboard/gps", "analytics.view", ("gps", "гпс", "gps sahifa", "jps")),
    "map": ("/dashboard/map", "analytics.view", ("xarita", "karta", "карта", "карту", "карте", "map")),
    "gps_wagons": ("/dashboard/gps/wagons", "analytics.view", ("vagonlar", "вагоны", "wagons")),
    "gtk_data": ("/dashboard/os/gtk", "gtk.view", ("gtk", "гтк", "gtk malumot", "данные gtk")),
    "wialon_data": ("/dashboard/os/wialon", "assets.view", ("wialon", "виалон", "vialon", "данные wialon")),
    "scales": ("/dashboard/scales", "scales.view", ("vesovoy", "tarozi", "весовая", "весовую", "весовой", "весы", "tarozilar")),
    "maintenance": ("/dashboard/maintenance", "maintenance.view", ("texnik xizmat", "to", "то", "ремонт", "техобслуживание", "obslujivanie")),
    "work_orders": ("/dashboard/work-orders", "work_orders.view", ("naryad", "naryadlar", "наряд", "наряды", "наряды", "нарядам", "наряд заказ")),
    "tmc": ("/dashboard/tmc", "tmc.view", ("tmc", "тмц", "ombor", "склад")),
    "reports": ("/dashboard/reports", "reports.view", ("hisobot", "hisobotlar", "отчет", "отчеты", "отчетам", "reports")),
    "directories": ("/dashboard/directories", "organization.view", ("malumotnoma", "spravochnik", "справочники", "справочник", "directories")),
    "users": ("/dashboard/admin/users", "users.manage_users", ("foydalanuvchilar", "пользователи", "users")),
    "audit_logs": ("/dashboard/admin/audit-logs", "users.manage_users", ("audit", "jurnal", "журнал", "logs", "loglar")),
}


@dataclass(frozen=True)
class Intent:
    id: str
    module: str  # help group key
    title_ru: str
    title_uz: str
    permission: str | None  # None: any signed-in user (the data is scoped by the services)
    groups: tuple[tuple[str, ...], ...]  # AND of ORs
    needs: tuple[str, ...] = ()  # slot names that must be filled: asset | train_no | work_order | page | text
    boost: tuple[tuple[str, ...], ...] = ()
    context_asset: bool = False  # "bu lokomotiv" / the open page's asset fills a missing asset
    write: bool = False  # returns a confirmation first (never executes directly)
    pronoun_only: bool = False  # the context asset is used only when the sentence points back to it ("uni xaritada ko'rsat"), never silently
    no_asset: bool = False  # a fleet-level question: it does not apply when the sentence names a unit
    no_train: bool = False  # a fleet-level question: it does not apply when the sentence names a train ("sostav 439")
    priority: int = 0
    examples_uz: tuple[str, ...] = ()
    examples_ru: tuple[str, ...] = ()


_Q = ("qayerda", "qaerda", "qayerga", "joylash", "manzil", "lokatsiya", "где", "местоположени", "местонахожд", "location", "position", "nimadir")
_FIND = ("top", "topib", "izla", "qidir", "qidiruv", "find", "найди", "найти", "поиск", "искать", "покажи")
_OPEN = ("och", "ochib", "ko'rsat", "korsat", "otib", "o'tib", "otish", "открой", "открыть", "покажи", "перейди", "show", "open", "go", "откр*", "покаж*", "перейд*", "зайд*", "включ*")
_PERIOD_WORDS = ("bugun", "kecha", "hafta", "oy", "сегодня", "вчера", "неделя", "неделю", "месяц", "today", "yesterday")

CATALOG: tuple[Intent, ...] = (
    Intent("sys.help", "system", "Что я умею", "Nima qila olaman", None,
           (("yordam", "help", "помощь", "справка", "buyruqlar", "komandalar", "команды", "qila olasan", "qila olaman", "что умеешь", "умеешь", "nima deyish", "qanday buyruq", "привет", "здравствуй*", "здраст*", "добрый день", "добрый вечер", "доброе утро", "salom", "assalomu*"),), priority=5, no_asset=True,
           examples_uz=("yordam", "nima qila olasan", "qanday buyruqlar bor"), examples_ru=("помощь", "что ты умеешь", "какие есть команды")),
    Intent("sys.bye", "system", "До свидания", "Xayr", None,
           (("до свидания", "досвидания", "пока", "хорошего дня", "спасибо", "благодарю", "xayr", "rahmat", "sog' bo'ling", "sog boling"),), priority=5, no_asset=True,
           examples_uz=("xayr", "rahmat"), examples_ru=("до свидания", "спасибо")),
    Intent("nav.open", "navigation", "Открыть страницу", "Sahifani ochish", None,
           (), boost=(_OPEN,), needs=("page",), priority=8,
           examples_uz=("xaritani och", "naryadlarga o'tish", "GPS sahifasi", "vesovoyni och"), examples_ru=("открой карту", "перейди в наряды", "покажи весовую")),
    Intent("find.asset", "search", "Найти технику", "Texnikani topish", "assets.view",
           (_FIND,), needs=("asset",),
           examples_uz=("37919 ni top", "vagon 35656 ni izla", "lokomotiv 2313"), examples_ru=("найди 37919", "вагон 35656", "найди локомотив 2313")),
    Intent("fleet.count", "search", "Сколько техники", "Texnika soni", "assets.view",
           (("vagon", "вагон*", "lokomotiv", "локомотив*", "teplovoz", "тепловоз*", "texnika", "техник*", "park", "парк", "подвижн", "dumpkar*", "думпкар*", "думкар*"),
            ("nechta", "necha", "qancha", "soni", "jami", "mavjud", "сколько", "количество", "всего", "число", "есть", "bor")),
           priority=2, no_asset=True, no_train=True,
           examples_uz=("nechta vagon bor", "lokomotivlar soni"), examples_ru=("сколько вагонов есть", "сколько локомотивов")),
    Intent("asset.info", "search", "Паспорт техники", "Texnika pasporti", "assets.view",
           (("haqida", "malumot", "ma'lumot", "pasport", "паспорт", "информация", "инфо", "карточка", "tavsif", "что за"),), needs=("asset",), context_asset=True,
           examples_uz=("37919 haqida ma'lumot", "35656 pasporti"), examples_ru=("информация о 37919", "паспорт вагона 35656")),
    Intent("train.info", "gps", "Состав", "Sostav", "analytics.view",
           (("sostav", "состав", "poezd", "поезд", "sostavda", "sostavi"),), needs=("train_no",), boost=(("nechta", "сколько", "vagon", "вагон", "lokomotiv", "локомотив"),),
           examples_uz=("sostav 439", "439 sostavda nechta vagon bor", "sostav 439 lokomotivi"), examples_ru=("состав 439", "сколько вагонов в составе 439")),
    Intent("gps.where", "gps", "Где находится", "Qayerda", "analytics.view",
           (_Q,), needs=("asset",), context_asset=True, priority=2,
           examples_uz=("37919 qayerda", "bu lokomotiv qayerda", "vagon 35656 qayerda"), examples_ru=("где 37919", "где находится вагон 35656", "где этот локомотив")),
    Intent("gps.status", "gps", "Состояние GPS", "GPS holati", "analytics.view",
           (("gps", "гпс", "jps", "tracker", "treker", "трекер", "holati", "статус", "состояни", "status"),), needs=("asset",), context_asset=True, boost=(("wialon", "gtk", "виалон", "гтк"),),
           examples_uz=("37919 GPS holati", "bu lokomotivning trekeri"), examples_ru=("статус GPS 37919", "состояние трекера локомотива 37919")),
    Intent("gps.km", "gps", "Пробег за период", "Davr bo'yicha yurgan masofa", "analytics.view",
           (("km", "kilometr", "probeg", "пробег", "yurdi", "yurgan", "проехал", "проехала", "masofa", "расстояни", "километр"), _PERIOD_WORDS + ("yurdi", "yurgan", "yurish", "проехал", "проехала", "necha", "сколько")), needs=("asset",), context_asset=True, priority=2,
           examples_uz=("37919 bugun necha km yurdi", "kecha necha km yurgan", "bu hafta probegi"), examples_ru=("сколько проехал 37919 сегодня", "пробег за неделю 37919")),
    Intent("gps.why_diff", "gps", "Почему расходятся Wialon и GTK", "Nega Wialon va GTK farq qiladi", "analytics.view",
           (("nega", "nima uchun", "sabab", "почему", "отчего", "причин", "why"), ("farq", "razlik", "различ", "расхож*", "расход*", "mos kelm", "не совпад", "отлича", "kam", "меньше", "разн*", "farqli")),
           context_asset=True, priority=3,
           examples_uz=("37919 uchun Wialon va GTK nega farq qildi", "nega GTK kam yozdi"), examples_ru=("почему у 37919 разные пробеги", "почему Wialon и GTK расходятся")),
    Intent("gps.dead_trackers", "gps", "Мёртвые трекеры GTK", "O'lik GTK trekerlar", "analytics.view",
           (("treker", "trekerlar", "tracker", "трекер", "трекеры", "gtk", "гтк"), ("olik", "o'lik", "dead", "мертв", "мёртв", "ishlamay*", "не работ*", "молчит", "jim", "muammo", "проблем", "buzuq", "неисправ")),
           priority=3, no_asset=True, examples_uz=("o'lik GTK trekerlar", "qaysi trekerlar ishlamayapti"), examples_ru=("мёртвые трекеры GTK", "какие трекеры не работают")),
    Intent("gps.summary", "gps", "Сводка GPS", "GPS xulosasi", "analytics.view",
           (("gps", "гпс", "jps"), ("umumiy", "xulosa", "hisobot", "svodka", "сводка", "итог", "holat", "qancha", "сколько", "статистика", "как дела")),
           priority=1, no_asset=True, examples_uz=("GPS xulosasi", "GPS holati umumiy"), examples_ru=("сводка по GPS", "как дела с GPS")),
    Intent("map.show", "gps", "Показать на карте", "Xaritada ko'rsatish", "analytics.view",
           (("xarita", "xaritada", "karta", "kartada", "карте", "карту", "map", "gps"), _OPEN), needs=("asset",), context_asset=True, pronoun_only=True, priority=2,
           examples_uz=("37919 ni xaritada ko'rsat", "uni xaritada ko'rsat"), examples_ru=("покажи 37919 на карте", "покажи его на карте")),
    Intent("wagon.loco", "gps", "С каким локомотивом вагон", "Vagon qaysi lokomotiv bilan", "analytics.view",
           (("lokomotiv", "локомотив", "teplovoz", "тепловоз", "tortuv", "тягов", "tortay*", "tortya*", "тянет", "тянут"), ("qaysi", "kim", "bilan", "какой", "каким", "с каким", "ushlab", "tortay*", "tortya*", "кто", "ким", "кем")), needs=("asset",), context_asset=True, priority=3,
           examples_uz=("vagon 35656 qaysi lokomotiv bilan", "35656 ni kim tortyapti"), examples_ru=("с каким локомотивом вагон 35656", "кто тянет вагон 35656")),
    Intent("mileage.asset", "mileage", "Пробег техники", "Texnika probegi", "assets.view",
           (("probeg", "probegi", "пробег", "kilometraj", "километраж", "mileage"),), needs=("asset",), context_asset=True,
           examples_uz=("37919 probegi", "vagon 35656 probegi"), examples_ru=("пробег 37919", "пробег вагона 35656")),
    Intent("to.overdue", "maintenance", "Просроченные ТО", "Muddati o'tgan ТО", "maintenance.view",
           (("то", "to", "техобслуживание", "техобслуживания", "обслуживание", "texnik", "xizmat", "tex"), ("muddati", "otgan", "o'tgan", "kechikkan", "просроч", "overdue", "kechik*", "vaqti")),
           priority=2, no_asset=True, examples_uz=("muddati o'tgan ТО", "kechikkan texnik xizmatlar"), examples_ru=("просроченные ТО", "какие ТО просрочены")),
    Intent("to.schedule", "maintenance", "График ТО", "ТО jadvali", "maintenance.view",
           (("то", "to", "техобслуживание", "обслуживание", "texnik", "xizmat", "tex", "remont", "ремонт"), ("jadval*", "grafik", "график", "schedule", "reja*", "план", "oy", "месяц", "hafta", "неделя")),
           priority=1, no_asset=True, examples_uz=("bu oy ТО jadvali", "texnik xizmat rejasi"), examples_ru=("график ТО на месяц", "план ТО")),
    Intent("to.types", "maintenance", "Виды ТО и ремонта", "ТО va ta'mir turlari", "maintenance.view",
           (("tur", "turi", "turlari", "turlar", "hil", "vid*", "вид*", "тип*", "kategoriya", "категори*"),
            ("то", "to", "texnik", "xizmat", "remont", "ремонт*", "обслуживани*", "ta'mir", "tamir", "ish", "работ*")),
           priority=3, no_asset=True, examples_uz=("qanday ТО turlari bor", "ta'mir turlari"), examples_ru=("какие виды ТО есть", "какой тип ремонта есть")),
    Intent("to.next", "maintenance", "Следующее ТО", "Keyingi ТО", "maintenance.view",
           (("то", "to", "техобслуживание", "обслуживание", "texnik", "xizmat", "tex", "remont", "ремонт"), ("keyingi", "qachon", "следующ", "когда", "next", "navbatdagi")), needs=("asset",), context_asset=True, priority=2,
           examples_uz=("37919 keyingi ТО qachon", "bu lokomotivning keyingi texnik xizmati"), examples_ru=("когда следующее ТО у 37919", "следующее ТО")),
    Intent("wo.count", "work_orders", "Сколько нарядов", "Nechta naryad", "work_orders.view",
           (("naryad", "naryadlar", "наряд", "наряды", "нарядов"), ("nechta", "soni", "сколько", "количество", "count", "qancha", "necha")), priority=2, no_asset=True,
           examples_uz=("nechta naryad ochiq", "uchastkamda nechta naryad bor"), examples_ru=("сколько нарядов открыто", "количество нарядов")),
    Intent("wo.list", "work_orders", "Список нарядов", "Naryadlar ro'yxati", "work_orders.view",
           (("naryad", "naryadlar", "наряд", "наряды", "нарядов"), ("ochiq", "royxat", "ro'yxat", "список", "открыт", "bajarilmagan", "list", "kechikkan", "просроч", "jarayonda", "в работе", "kutilmoqda", "ожида")),
           priority=1, no_asset=True, examples_uz=("ochiq naryadlar", "kechikkan naryadlar"), examples_ru=("открытые наряды", "просроченные наряды")),
    Intent("wo.by_asset", "work_orders", "Наряды по технике", "Texnika naryadlari", "work_orders.view",
           (("naryad", "naryadlar", "naryadlari", "наряд", "наряды", "нарядов"),), needs=("asset",), context_asset=True, priority=1,
           examples_uz=("37919 naryadlari", "bu lokomotiv naryadlari"), examples_ru=("наряды по 37919", "наряды этого вагона")),
    Intent("wo.create", "work_orders", "Создать наряд", "Naryad ochish", "work_orders.create",
           (("naryad", "наряд"), ("och", "yarat", "tuz", "qo'sh", "qosh", "yangi", "создай", "создать", "оформи", "оформить", "открой", "открыть", "новый", "create")), needs=("asset",), context_asset=True, write=True, priority=4,
           examples_uz=("37919 uchun naryad och", "bu lokomotivga naryad yarat"), examples_ru=("создай наряд на 37919", "открой наряд для этого вагона")),
    Intent("wo.set_status", "work_orders", "Изменить статус наряда", "Naryad holatini o'zgartirish", "work_orders.update",
           (("naryad", "наряд"), ("bajarildi", "tugadi", "yakunla", "yakun", "завершен", "завершить", "выполнен", "выполнено", "закрой", "yop", "jarayonda", "в работе", "bekor", "отмени", "отмена", "boshla", "начни")),
           needs=("work_order",), write=True, priority=4,
           examples_uz=("naryad 1024 ni bajarildi qil", "naryad 1024 jarayonda", "naryad 1024 bekor"), examples_ru=("наряд 1024 выполнен", "закрой наряд 1024", "наряд 1024 в работе")),
    Intent("wo.comment", "work_orders", "Добавить комментарий", "Izoh qo'shish", "work_orders.update",
           (("naryad", "наряд"), ("izoh", "comment", "комментар", "примечан", "qayd", "eslatma", "заметк")), needs=("work_order", "text"), write=True, priority=5,
           examples_uz=("naryad 1024 ga izoh qo'sh ehtiyot qism kutilmoqda",), examples_ru=("добавь комментарий к наряду 1024 ждём запчасти",)),
    Intent("scales.today", "scales", "Взвешивания за период", "Tarozi: bugun", "scales.view",
           (("tarozi", "tarozida", "vesovoy", "весов", "весы", "вес", "tortil", "tortildi", "взвес*", "tonna", "тонн", "yuk", "груз*", "перевез*", "отправ*", "отгруз*", "отгруж*", "yuboril*"),), boost=(_PERIOD_WORDS + ("nechta", "сколько"),), priority=1, no_asset=True,
           examples_uz=("bugun nechta sostav tortildi", "bugun necha tonna yuk tashildi"), examples_ru=("сколько составов взвесили сегодня", "сколько тонн перевезли")),
    Intent("scales.wagon", "scales", "Грузы вагона", "Vagon yuk tarixi", "scales.view",
           (("yuk", "груз*", "tonna", "тонн", "tortil", "tortildi", "взвес*", "tarozi", "весов", "reys*", "рейс*"),), needs=("asset",), context_asset=True, boost=(("vagon", "вагон"),), priority=2,
           examples_uz=("vagon 35656 yuk tarixi", "35656 necha tonna tashidi"), examples_ru=("грузы вагона 35656", "сколько тонн перевёз вагон 35656")),
    Intent("sys.sync_status", "system", "Статус синхронизации", "Sinxron holati", "dashboard.view",
           (("sinxron", "sinxronizatsiya", "yangilan", "синхрон", "обнов*", "sync", "oxirgi"), ("wialon", "gtk", "виалон", "гтк", "vialon")), priority=1, no_asset=True,
           examples_uz=("Wialon oxirgi marta qachon yangilandi", "GTK sinxron holati"), examples_ru=("когда обновился Wialon", "статус синхронизации GTK")),
    Intent("admin.audit_recent", "admin", "Последние события аудита", "Oxirgi audit hodisalari", "users.manage_users",
           (("audit", "аудит*", "журнал", "jurnal", "loglar", "log"), ("oxirgi", "последн", "recent", "yangi", "свеж")), priority=1, no_asset=True,
           examples_uz=("oxirgi audit hodisalari",), examples_ru=("последние события аудита",)),
)

INTENTS: dict[str, Intent] = {i.id: i for i in CATALOG}

MODULE_TITLES = {
    "navigation": "Навигация / Navigatsiya",
    "search": "Поиск / Qidiruv",
    "gps": "GPS и вагоны / GPS va vagonlar",
    "mileage": "Пробег / Probeg",
    "maintenance": "ТО / Texnik xizmat",
    "work_orders": "Наряды / Naryadlar",
    "scales": "Весовая / Vesovoy",
    "system": "Система / Tizim",
    "admin": "Администрирование / Admin",
}

STATUS_WORDS: dict[str, tuple[str, ...]] = {
    "completed": ("bajarildi", "tugadi", "yakunla", "yakun", "завершен", "завершить", "выполнен", "выполнено", "закрой", "yop"),
    "in_progress": ("jarayonda", "в работе", "boshla", "начни", "ishga"),
    "cancelled": ("bekor", "отмени", "отмена", "cancel"),
    "pending": ("kutilmoqda", "ожида", "kutish"),
}
