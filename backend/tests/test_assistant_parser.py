"""The command centre's pure parts: normalisation, spoken numbers, and the GOLDEN phrase set (intent selection without a database).

Every phrase a user once said and we got wrong is added here. A slot is simulated: a number of 3+ digits means "an asset was found".
"""
from uuid import uuid4

import pytest

from app.services.assistant import catalog, entities
from app.services.assistant.normalize import detect_locale, normalize
from app.services.assistant.numbers import canonical, join_digit_groups, words_to_digits
from app.services.assistant.parser import rank
from app.services.assistant.repair import repair_text
from app.services.assistant.types import AssetRef, Slots


# ---- normalisation and numbers -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("O'TGAN  ТО!", "otgan то"), ("ko‘rsat", "korsat"), ("Қаерда 37919?", "qaerda 37919"), ("мёртвые", "мертвые"), ("37-919", "37919"),
        ("o`n bir", "on bir"), ("  GPS,  holati ", "gps holati"),
    ],
)
def test_normalisation(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    "spoken,digits",
    [
        ("o'ttiz yetti to'qqiz yuz o'n to'qqiz", "37919"),  # 37 | 919 (the thousand is dropped when said)
        ("o'ttiz yetti ming to'qqiz yuz o'n to'qqiz", "37919"),  # the same with "ming"
        ("тридцать семь девятьсот девятнадцать", "37919"),
        ("тридцать семь тысяч девятьсот девятнадцать", "37919"),
        ("uch yetti to'qqiz bir to'qqiz", "37919"),  # digit by digit
        ("ikki uch bir uch", "2313"), ("yigirma uch o'n uch", "2313"), ("двадцать три тринадцать", "2313"),
        ("sakkiz yuz o'n besh", "815"), ("сто двадцать пять", "125"), ("bir ming besh yuz", "1500"), ("nol bir", "01"),
        ("sostav to'rt yuz o'ttiz to'qqiz", "sostav 439"), ("наряд тысяча двадцать четыре", "наряд 1024"),
    ],
)
def test_spoken_numbers(spoken, digits):
    assert words_to_digits(normalize(spoken)) == digits


@pytest.mark.parametrize("raw,expected", [("37 919", "37919"), ("3 7 9 1 9", "37919"), ("sostav 439 vagon 12", "sostav 439 vagon 12"), ("12 345 678", "12345678"), ("5 vagon 3", "5 vagon 3")])
def test_digit_groups_are_joined_only_when_they_look_like_one_number(raw, expected):
    assert join_digit_groups(raw) == expected


def test_canonical_is_what_the_parser_reads():
    assert canonical("O'ttiz yetti to'qqiz yuz o'n to'qqiz QAYERDA?") == "37919 qayerda"
    assert detect_locale("где 37919") == "ru" and detect_locale("37919 qayerda") == "uz" and detect_locale("қаерда") == "uz"


# ---- the golden phrases --------------------------------------------------------------------------------------
def _simulate_canon(canon: str, context_asset: bool = False):
    """Intent chosen for a canonical sentence without a database: slots from the pure extractors, an asset when a 3+ digit number is present."""
    tokens = canon.split()
    slots = Slots(raw_numbers=entities.numbers_in(tokens))
    slots.period = entities.detect_period(tokens)
    slots.status = entities.detect_status(tokens)
    slots.page = entities.detect_page(canon)
    slots.train_no = entities.after_keyword_number(tokens, entities._TRAIN_WORDS)
    slots.work_order = entities.after_keyword_number(tokens, entities._WO_WORDS, reach=1)
    slots.text = entities.comment_text(tokens, slots.raw_numbers)
    ids = [n for n in slots.raw_numbers if n not in {slots.train_no, slots.work_order}]
    if ids and len(ids[0]) >= 3:
        slots.asset = AssetRef(id=uuid4(), inv_number=ids[0], name="x", asset_type="locomotive")
    elif context_asset:  # the page / last answer supplies it
        slots.asset = AssetRef(id=uuid4(), inv_number="0", name="x", asset_type="locomotive")
        slots.asset_from_context = True
    slots.pronoun = entities._has(tokens, entities.PRONOUNS)
    matches = rank(tokens, slots)
    if matches:
        return matches[0].intent.id, matches[0].missing, slots
    if slots.asset is not None:
        return "find.asset", [], slots
    if slots.page:
        return "nav.open", [], slots
    return None, [], slots


def simulate(text: str, context_asset: bool = False):
    """What `parser.parse` does without a database: the strict sentence first, then the speech-repaired sentence when no keyword intent was found."""
    canon = canonical(text)
    got, missing, slots = _simulate_canon(canon, context_asset)
    if got is not None and not missing and got != "nav.open" and (_has_keyword(canon) or got != "find.asset"):
        return got, missing, slots
    repaired = repair_text(canon)
    if repaired != canon:
        got2, missing2, slots2 = _simulate_canon(repaired, context_asset)
        if got2 is not None and not missing2 and got2 != got and (_has_keyword(repaired) or got is None):
            return got2, missing2, slots2
    return got, missing, slots


def _has_keyword(canon: str) -> bool:
    """True when a catalogue intent WITH keywords matches (not the asset-only / page-only fallbacks)."""
    from app.services.assistant.parser import keyword_score

    tokens = canon.split()
    return any(i.groups and keyword_score(i.id, tokens) is not None for i in catalog.CATALOG)


GOLDEN = [
    # (phrase, intent)
    ("yordam", "sys.help"), ("nima qila olasan", "sys.help"), ("помощь", "sys.help"), ("что ты умеешь", "sys.help"), ("qanday buyruqlar bor", "sys.help"),
    ("xaritani och", "nav.open"), ("naryadlarga o'tish", "nav.open"), ("GPS sahifasi", "nav.open"), ("vesovoyni och", "nav.open"), ("открой карту", "nav.open"),
    ("перейди в наряды", "nav.open"), ("покажи весовую", "nav.open"), ("xarita", "nav.open"), ("vagonlar sahifasini och", "nav.open"), ("hisobotlarni och", "nav.open"),
    ("37919 ni top", "find.asset"), ("vagon 35656 ni izla", "find.asset"), ("найди 37919", "find.asset"), ("37919", "find.asset"), ("2313", "find.asset"), ("lokomotiv 2313", "find.asset"),
    ("37919 haqida ma'lumot", "asset.info"), ("информация о 37919", "asset.info"), ("паспорт вагона 35656", "asset.info"),
    ("sostav 439", "train.info"), ("439 sostavda nechta vagon bor", "train.info"), ("состав 439", "train.info"), ("сколько вагонов в составе 439", "train.info"),
    ("37919 qayerda", "gps.where"), ("vagon 35656 qayerda", "gps.where"), ("где 37919", "gps.where"), ("где находится вагон 35656", "gps.where"), ("o'ttiz yetti to'qqiz yuz o'n to'qqiz qayerda", "gps.where"),
    ("37919 GPS holati", "gps.status"), ("статус GPS 37919", "gps.status"), ("37919 trekeri", "gps.status"),
    ("37919 bugun necha km yurdi", "gps.km"), ("kecha necha km yurgan 37919", "gps.km"), ("сколько проехал 37919 сегодня", "gps.km"), ("пробег за неделю 37919", "gps.km"),
    ("37919 uchun Wialon va GTK nega farq qildi", "gps.why_diff"), ("почему у 37919 разные пробеги", "gps.why_diff"), ("nega GTK kam yozdi 37919", "gps.why_diff"),
    ("o'lik GTK trekerlar", "gps.dead_trackers"), ("qaysi trekerlar ishlamayapti", "gps.dead_trackers"), ("мёртвые трекеры GTK", "gps.dead_trackers"), ("какие трекеры не работают", "gps.dead_trackers"),
    ("GPS xulosasi", "gps.summary"), ("сводка по GPS", "gps.summary"),
    ("37919 ni xaritada ko'rsat", "map.show"), ("покажи 37919 на карте", "map.show"),
    ("vagon 35656 qaysi lokomotiv bilan", "wagon.loco"), ("с каким локомотивом вагон 35656", "wagon.loco"), ("кто тянет вагон 35656", "wagon.loco"),
    ("37919 probegi", "mileage.asset"), ("пробег 37919", "mileage.asset"), ("vagon 35656 probegi", "mileage.asset"),
    ("muddati o'tgan ТО", "to.overdue"), ("просроченные ТО", "to.overdue"), ("kechikkan texnik xizmatlar", "to.overdue"),
    ("bu oy ТО jadvali", "to.schedule"), ("график ТО на месяц", "to.schedule"), ("texnik xizmat rejasi", "to.schedule"),
    ("37919 keyingi ТО qachon", "to.next"), ("когда следующее ТО у 37919", "to.next"),
    ("nechta naryad ochiq", "wo.count"), ("сколько нарядов открыто", "wo.count"), ("uchastkamda nechta naryad bor", "wo.count"),
    ("ochiq naryadlar", "wo.list"), ("открытые наряды", "wo.list"), ("kechikkan naryadlar", "wo.list"), ("наряды по 37919", "wo.by_asset"),
    ("37919 uchun naryad och", "wo.create"), ("создай наряд на 37919", "wo.create"), ("37919 ga yangi naryad yarat", "wo.create"),
    ("naryad 1024 ni bajarildi qil", "wo.set_status"), ("наряд 1024 выполнен", "wo.set_status"), ("naryad 1024 jarayonda", "wo.set_status"), ("закрой наряд 1024", "wo.set_status"), ("naryad 1024 bekor", "wo.set_status"),
    ("naryad 1024 ga izoh qo'sh ehtiyot qism kutilmoqda", "wo.comment"), ("добавь комментарий к наряду 1024 ждём запчасти", "wo.comment"),
    ("bugun nechta sostav tortildi", "scales.today"), ("сколько тонн перевезли сегодня", "scales.today"), ("bugun necha tonna yuk tashildi", "scales.today"),
    ("vagon 35656 yuk tarixi", "scales.wagon"), ("грузы вагона 35656", "scales.wagon"),
    ("Wialon oxirgi marta qachon yangilandi", "sys.sync_status"), ("GTK sinxron holati", "sys.sync_status"), ("когда обновился Wialon", "sys.sync_status"),
    ("oxirgi audit hodisalari", "admin.audit_recent"), ("последние события аудита", "admin.audit_recent"),
    # what the speech recogniser really wrote (measured with the local Whisper on Russian recordings)
    ("Найди тридцать семь девятьсот девятнадцать.", "find.asset"), ("Где локомотив, 37919?", "gps.where"), ("Какие-то просрочены?", "to.overdue"),
    ("Почему Виалон и ГТК расходятся?", "gps.why_diff"), ("Сколько тон перевезли сегодня?", "scales.today"), ("Пробег локомотива 2313.", "mileage.asset"),
    ("Создай наряд на 37919.", "wo.create"),
    # phrases the user really said into the microphone (live log 2026-11-18)
    ("сколько вагонов есть", "fleet.count"), ("nechta vagon bor", "fleet.count"), ("какой тип ремонта есть", "to.types"), ("какие виды ТО есть", "to.types"),
    ("дай отчет сегодня сколько вес отправили", "scales.today"), ("сколько тонн отправили", "scales.today"), ("qanday ТО turlari bor", "to.types"), ("Состав 439.", "train.info"), ("Сколько нарядов открыто?", "wo.count"),
]


@pytest.mark.parametrize("phrase,intent", GOLDEN)
def test_golden_phrases(phrase, intent):
    got, missing, _ = simulate(phrase)
    assert got == intent, f"{phrase!r}: expected {intent}, got {got} (missing {missing})"
    assert not missing, f"{phrase!r}: {intent} still lacks {missing}"


def test_unrelated_text_matches_nothing():
    for phrase in ("salom", "bugun havo yaxshi", "qalaysan", "hello", "asdf qwer", "привет"):
        assert simulate(phrase)[0] is None, phrase


def test_the_context_fills_a_missing_asset_for_pronoun_commands():
    got, missing, _ = simulate("bu lokomotiv qayerda", context_asset=True)
    assert got == "gps.where" and not missing
    got, missing, _ = simulate("где этот локомотив", context_asset=True)
    assert got == "gps.where" and not missing
    got, missing, _ = simulate("qayerda")  # no number, no context
    assert got == "gps.where" and missing == ["asset"]


def test_a_context_unit_is_not_silently_taken_for_a_page_command():
    """After talking about a unit, "xaritani och" still opens the MAP page; only "uni xaritada ko'rsat" points back at the unit."""
    got, _, _ = simulate("xaritani och", context_asset=True)
    assert got == "nav.open"
    got, missing, _ = simulate("uni xaritada ko'rsat", context_asset=True)
    assert got == "map.show" and not missing
    got, _, _ = simulate("покажи его на карте", context_asset=True)
    assert got == "map.show"
    got, _, _ = simulate("открой карту", context_asset=True)
    assert got == "nav.open"


def test_slots_from_a_sentence():
    _, _, s = simulate("naryad 1024 ga izoh qo'sh ehtiyot qism kutilmoqda")
    assert s.work_order == "1024" and s.text == "ehtiyot qism kutilmoqda"
    _, _, s = simulate("naryad 1024 ni bajarildi qil")
    assert s.status == "completed" and s.work_order == "1024"
    _, _, s = simulate("kecha necha km yurgan 37919")
    assert s.period == "yesterday"
    _, _, s = simulate("37919 bu hafta necha km yurdi")
    assert s.period == "week"
    _, _, s = simulate("sostav 439 lokomotivi")
    assert s.train_no == "439"


def test_every_catalogue_example_resolves_to_its_own_intent():
    """The catalogue's own examples are tests too (they are what the help shows)."""
    bad = []
    for intent in catalog.CATALOG:
        for example in (*intent.examples_uz, *intent.examples_ru):
            got, _, _ = simulate(example, context_asset=intent.context_asset and not any(ch.isdigit() for ch in example))
            if got != intent.id:
                bad.append((example, intent.id, got))
    assert not bad, bad


def test_the_catalogue_is_consistent():
    assert len(catalog.INTENTS) == len(catalog.CATALOG)
    assert all(i.id.count(".") == 1 for i in catalog.CATALOG)
    assert {i.module for i in catalog.CATALOG} <= set(catalog.MODULE_TITLES)
    assert all(i.permission is None or i.permission.count(".") == 1 for i in catalog.CATALOG)
    for _key, (path, perm, names) in catalog.PAGES.items():
        assert path.startswith("/dashboard") and names


# ---- speech-recogniser near-misses (real log lines first, then the usual Uzbek mistakes of a small Whisper) -------------------
GARBLED = [
    ("харитana otz", "nav.open"), ("харитana oggi", "nav.open"), ("харита очиш", "nav.open"), ("vaqonlar", "nav.open"), ("naryadlir", "nav.open"),
    ("37919 каерда", "gps.where"), ("37919 қаерда", "gps.where"), ("37919 qayirda", "gps.where"), ("37919 каердa", "gps.where"),
    ("очик нарядлар", "wo.list"), ("ochik naryadlar", "wo.list"), ("очиқ нарядлар", "wo.list"),
    ("нечта наряд очиқ", "wo.count"), ("nechta naryat ochik", "wo.count"),
    ("муддати ўтган то", "to.overdue"), ("muddati utgan texnik hizmat", "to.overdue"), ("кечикган техник хизмат", "to.overdue"),
    ("37919 probigi", "mileage.asset"), ("37919 bugun necha kilometr yurdi", "gps.km"),
    ("ёрдам", "sys.help"), ("yordom", "sys.help"), ("нима қила оласан", "sys.help"),
    ("bugun nechta sostov tortildi", "scales.today"), ("виалон охирги янгиланиш", "sys.sync_status"),
    ("o'lik trekerlar", "gps.dead_trackers"), ("улик трекерлар", "gps.dead_trackers"),
]


@pytest.mark.parametrize("phrase,intent", GARBLED)
def test_garbled_speech_is_repaired(phrase, intent):
    got, missing, _ = simulate(phrase)
    assert got == intent and not missing, f"{phrase!r}: expected {intent}, got {got} (missing {missing})"


def test_repair_leaves_correct_and_unrelated_sentences_alone():
    from app.services.assistant.repair import repair_text

    for text in ("xaritani och", "37919 qayerda", "ochiq naryadlar", "sostav 439", "hello", "salom qalaysan", "bugun havo yaxshi", "asdf qwer"):
        assert repair_text(canonical(text)) == canonical(text), text


def test_repair_does_not_turn_short_words_into_commands():
    from app.services.assistant.repair import repair_token

    assert repair_token("hello") == "hello" and repair_token("yeti") == "yeti" and repair_token("12345") == "12345"


def test_a_standard_or_a_year_is_not_a_unit_number():
    for text, expected in (
        ("37919 GOST 33421-2015 qayerda", ["37919"]), ("naryad 1024 ga izoh qo'sh GOST 33421 bo'yicha", ["1024"]),
        ("sostav 439 2015 yil", ["439"]), ("37919 25 mart necha km yurdi", ["37919", "25"]), ("vagon 35656 4-marta yuk tashidi", ["35656"]),
        ("37919 2026", ["37919", "2026"]),  # a bare 4-digit number stays a number (it may be an inventory number)
    ):
        assert entities.numbers_in(canonical(text).split()) == expected, text


def test_a_create_verb_without_a_unit_asks_for_the_unit_and_a_bare_open_still_opens_the_page():
    assert simulate("yangi naryad yarat")[:2] == ("wo.create", ["asset"])
    assert simulate("создай наряд")[:2] == ("wo.create", ["asset"])
    assert simulate("naryad och")[0] == "nav.open" and simulate("открой наряды")[0] == "nav.open"
