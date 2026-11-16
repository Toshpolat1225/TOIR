"""Standard HELD reason codes: Uzbek text and what to do about each."""

REASONS: dict[str, tuple[str, str]] = {
    "gtk_link_missing": (
        "Vagon GTK obyekti bilan bog'lanmagan",
        "Aktivni GTK vagoniga bog'lang (aktivlar kartochkasi / bog'lash ekrani).",
    ),
    "no_gtk_membership": (
        "GTK sostavida bu vagon hali ko'rilmagan",
        "GTK sinxronlashini kuting; vagon sostavga kiritilganda a'zolik paydo bo'ladi.",
    ),
    "approved_opening_balance_missing": (
        "Boshlang'ich probeg tasdiqlanmagan",
        "Boshlang'ich probegni kiriting va boshqa admin tasdiqlasin (wagon-opening-propose / approve).",
    ),
    "no_calculated_period_yet": (
        "Tasdiqlangan boshlang'ichdan keyin hisoblangan davr yo'q",
        "Keyingi run'ni kuting; GTK a'zolik va Wialon o'qishlari yangilanishi kerak.",
    ),
    "no_linked_locomotive": (
        "Sostavdagi lokomotiv aktivga bog'lanmagan",
        "GTK lokomotivini TOIR lokomotiv aktiviga bog'lang.",
    ),
    "locomotive_has_no_wialon_readings": (
        "Lokomotivda Wialon o'qishlari yo'q (mapping yo'q yoki birlik jim)",
        "Lokomotivga wialon_id bog'langanini va Wialon sinxronlash ishlashini tekshiring.",
    ),
    "no_eligible_locomotive_odometer": (
        "Lokomotivning hisobga olinadigan odometr o'qishi yo'q",
        "Wialon o'qishlari sifat darvozasidan o'tayotganini tekshiring (xabar vaqti, sakrashlar).",
    ),
    "locomotive_handoff_time_unknown": (
        "Lokomotiv almashgan vaqti GTK dan aniq emas (D4)",
        "GTK vaqtini kuting; qo'lda taxmin qilinmaydi.",
    ),
    "missing_odometer_sample_bracket": (
        "Davrni qoplaydigan odometr nuqtalari yetarli emas",
        "Wialon ma'lumoti paydo bo'lishini kuting; orqaga to'ldirish qilinmaydi.",
    ),
    "odometer_sample_gap_exceeded": (
        "Odometr nuqtalari orasi 30 daqiqadan katta va harakat bor",
        "Wialon aloqa uzilishi; bu davr hisoblanmaydi.",
    ),
    "reading_not_calculation_eligible": (
        "O'qish sifat darvozasidan o'tmagan",
        "wialon_odometer_readings.rejection_reason ni ko'ring. 'counter_state_blocked_by_unresolved_conflict' bo'lsa, lokomotiv hisoblagichi bir vaqtdagi ziddiyat sababli bloklangan: operator qayta baseline qilishi kerak.",
    ),
    "invalid_or_decreasing_odometer_sample": (
        "Odometr kamaygan yoki vaqt tartibi noto'g'ri",
        "Wialon hisoblagichini tekshiring (reset/almashtirish).",
    ),
    "locomotive_bracket_mismatch": (
        "Odometr nuqtalari turli lokomotivlarga tegishli",
        "Ma'lumot manbasini tekshiring.",
    ),
    "locomotive_distance_conflict": (
        "Ikki lokomotiv masofasi farqi max(2 km, 5%) dan katta (D6)",
        "Lokomotivlar odometrini solishtiring; km qo'shilmaydi yoki o'rtachalanmaydi.",
    ),
    "candidate_periods_disagree": (
        "Lokomotiv nomzodlari davrlari mos emas",
        "Ma'lumotni tekshiring.",
    ),
    "same_locomotive_readings_disagree": (
        "Bir lokomotivning o'qishlari bir-biriga zid",
        "Wialon o'qishlarini tekshiring (bir vaqtda turli odometr).",
    ),
    "no_valid_odometer_interval": (
        "Yaroqli odometr oralig'i yo'q",
        "Wialon o'qishlarini tekshiring.",
    ),
    "invalid_half_open_period": (
        "Davr noto'g'ri (oxiri boshidan oldin)",
        "GTK a'zolik vaqtlarini tekshiring.",
    ),
    "wagon_membership_overlap": (
        "Vagon bir vaqtda bir necha sostavda ko'rinadi",
        "GTK ma'lumotini tekshiring; hal qilinmaguncha hisoblanmaydi.",
    ),
}


def describe(code: str | None) -> dict[str, str]:
    if not code:
        return {"code": "", "text": "", "action": ""}
    text, action = REASONS.get(
        code, ("Noma'lum sabab kodi", "Kod standart ro'yxatda yo'q: dasturchiga xabar bering.")
    )
    return {"code": code, "text": text, "action": action}
