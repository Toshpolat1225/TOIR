"use client"

import { useState, useRef, useEffect, createContext, useContext, useCallback, Suspense } from "react"
import { useSearchParams, useRouter } from "next/navigation"
import { supabase } from "@/lib/supabase"
import { useAuth } from "@/lib/auth-context"
import {
  ClipboardList, Plus, Search, CheckCircle, Clock, Wrench,
  AlertTriangle, X, Trash2, PackagePlus, ChevronDown,
  Save, ChevronUp, Package, Info, BookOpen, Filter, SlidersHorizontal, Lock
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useSections } from "@/lib/use-sections"

/* ════════════════════════════════════════
   КОНТЕКСТ (используется в дочерних модалах)
════════════════════════════════════════ */
// RoleCtx оставлен для обратной совместимости с вложенными компонентами
const RoleCtx = createContext<{ role: "operator"; mySection: string }>({ role: "operator", mySection: "" })

/* ════════════════════════════════════════
   СПРАВОЧНИК ТМЦ
════════════════════════════════════════ */
type CatalogItem = { name: string; invNo: string; unit: string; category: string }

const tmcCatalog: CatalogItem[] = [
  // Масла и смазки
  { name: "Масло дизельное М-14В2 (канистра 20 л)",         invNo: "МТР-00101", unit: "кан.",  category: "Масла и смазки" },
  { name: "Масло трансмиссионное ТАД-17и (канистра 20 л)",  invNo: "МТР-00145", unit: "кан.",  category: "Масла и смазки" },
  { name: "Масло моторное Shell Rimula R4X (20 л)",          invNo: "МТР-00148", unit: "кан.",  category: "Масла и смазки" },
  { name: "Смазка БУКСОЛ (картридж 800 г)",                  invNo: "МТР-00203", unit: "шт.",   category: "Масла и смазки" },
  { name: "Смазка ЖТ-79Л тугоплавкая (0,8 кг)",             invNo: "МТР-00207", unit: "шт.",   category: "Масла и смазки" },
  { name: "Герметик силиконовый высокотемп. ABRO (100 мл)", invNo: "МТР-00499", unit: "шт.",   category: "Масла и смазки" },
  // Фильтры
  { name: "Фильтр масляный (картридж)",                     invNo: "МТР-00102", unit: "шт.",   category: "Фильтры" },
  { name: "Фильтр топливный грубой очистки",                invNo: "МТР-00103", unit: "шт.",   category: "Фильтры" },
  { name: "Фильтр топливный тонкой очистки",                invNo: "МТР-00104", unit: "шт.",   category: "Фильтры" },
  { name: "Фильтр воздушный дизеля",                        invNo: "МТР-00105", unit: "шт.",   category: "Фильтры" },
  // Подшипники
  { name: "Подшипник роликовый 42228 ГОСТ 5721",            invNo: "МТР-00087", unit: "шт.",   category: "Подшипники" },
  { name: "Подшипник шариковый 6310 ГОСТ 8338",             invNo: "МТР-00088", unit: "шт.",   category: "Подшипники" },
  { name: "Подшипник конический 7518 ГОСТ 27365",           invNo: "МТР-00089", unit: "шт.",   category: "Подшипники" },
  { name: "Подшипник буксовый роликовый 30-42726 Л2М",      invNo: "МТР-00091", unit: "шт.",   category: "Подшипники" },
  // Тормозное оборудование
  { name: "Колодка тормозная чугунная ТМ-1 (тип А)",        invNo: "МТР-00033", unit: "шт.",   category: "Тормозное оборудование" },
  { name: "Колодка тормозная композиционная ТИИР-300",      invNo: "МТР-00035", unit: "шт.",   category: "Тормозное оборудование" },
  { name: "Чека тормозной колодки",                         invNo: "МТР-00034", unit: "шт.",   category: "Тормозное оборудование" },
  { name: "Воздухораспределитель № 483М (комплект)",        invNo: "МТР-00421", unit: "к-т",   category: "Тормозное оборудование" },
  { name: "Рукав тормозной Р17Б (760 мм)",                  invNo: "МТР-00430", unit: "шт.",   category: "Тормозное оборудование" },
  // Электрооборудование
  { name: "Щётка угольная ЭГ-74 (тяговый двигатель)",       invNo: "МТР-00412", unit: "шт.",   category: "Электрооборудование" },
  { name: "Щётка угольная МГС-7 (вспомогательный двигатель)",invNo:"МТР-00413", unit: "шт.",   category: "Электрооборудование" },
  { name: "Лакоткань ЛХМ-105 (рулон 10 м)",                 invNo: "МТР-00318", unit: "рул.",  category: "Электрооборудование" },
  { name: "Токоприёмник (к-т для замены)",                   invNo: "МТР-00820", unit: "к-т",   category: "Электрооборудование" },
  { name: "Трансформатор тяговый (ремкомплект)",             invNo: "МТР-00800", unit: "к-т",   category: "Электрооборудование" },
  { name: "Секция тягового двигателя (к-т запчастей)",       invNo: "МТР-00750", unit: "к-т",   category: "Электрооборудование" },
  { name: "Контактор электромагнитный КПД-110",              invNo: "МТР-00651", unit: "шт.",   category: "Электрооборудование" },
  { name: "Реле давления воздуха РДВ-1",                    invNo: "МТР-00652", unit: "шт.",   category: "Электрооборудование" },
  // Прокладки и уплотнители
  { name: "Прокладка маслосборника (к-т)",                   invNo: "МТР-00310", unit: "к-т",   category: "Прокладки и уплотнители" },
  { name: "Прокладка редуктора колёсной пары",               invNo: "МТР-00722", unit: "шт.",   category: "Прокладки и уплотнители" },
  { name: "Уплотнитель резиновый маслостойкий (м.п.)",       invNo: "МТР-00381", unit: "м.",    category: "Прокладки и уплотнители" },
  { name: "Набивка сальниковая асбестовая (кг)",             invNo: "МТР-00385", unit: "кг.",   category: "Прокладки и уплотнители" },
  // Крепёж
  { name: "Болт М12×40 нержавеющий (уп. 50 шт.)",           invNo: "МТР-00561", unit: "уп.",   category: "Крепёж" },
  { name: "Болт М16×60 класс прочности 8.8 (уп. 25 шт.)",   invNo: "МТР-00565", unit: "уп.",   category: "Крепёж" },
  { name: "Гайка М12 самоконтрящаяся (уп. 50 шт.)",         invNo: "МТР-00570", unit: "уп.",   category: "Крепёж" },
  { name: "Шайба пружинная Гровера М12 (уп. 100 шт.)",      invNo: "МТР-00575", unit: "уп.",   category: "Крепёж" },
  { name: "Шплинт 6×40 ГОСТ 397 (уп. 100 шт.)",             invNo: "МТР-00602", unit: "уп.",   category: "Крепёж" },
  // Расходные материалы
  { name: "Ветошь обтирочная",                               invNo: "МТР-00900", unit: "кг.",   category: "Расходные материалы" },
  { name: "Краска эмаль ПФ-115 (бочка 50 кг)",              invNo: "МТР-00850", unit: "шт.",   category: "Расходные материалы" },
  { name: "Растворитель 647 (канистра 10 л)",                invNo: "МТР-00855", unit: "кан.",  category: "Расходные материалы" },
  { name: "Антикоррозийное покрытие Мовиль (0,5 л)",        invNo: "МТР-00860", unit: "шт.",   category: "Расходные материалы" },
  { name: "Лента изоляционная ПВХ (рулон)",                  invNo: "МТР-00865", unit: "рул.",  category: "Расходные материалы" },
  { name: "Проволока стальная вязальная 1,2 мм (кг)",       invNo: "МТР-00870", unit: "кг.",   category: "Расходные материалы" },
]

const catalogCategories = [...new Set(tmcCatalog.map(i => i.category))]

/* ════════════════════════════════════════
   СПРАВОЧНИКИ ФОРМЫ
════════════════════════════════════════ */
const workTypes = ["Плановое","Внеплановое","Ремонтное","Аварийное"]

const repairKindsLoco = [
  { value:"",     label:"— Не выбрано —" },
  { value:"ТО-1", label:"ТО-1 — Техническое обслуживание №1" },
  { value:"ТО-2", label:"ТО-2 — Техническое обслуживание №2" },
  { value:"ТО-3", label:"ТО-3 — Техническое обслуживание №3" },
  { value:"ТР-1", label:"ТР-1 — Текущий ремонт №1" },
  { value:"ТР-2", label:"ТР-2 — Текущий ремонт №2" },
  { value:"ТР-3", label:"ТР-3 — Текущий ремонт №3" },
  { value:"СР",   label:"СР  — Средний ремонт" },
  { value:"КР",   label:"КР  — Капитальный ремонт" },
  { value:"ВНП",  label:"ВНП — Внеплановый ремонт" },
]

const repairKindsWagon = [
  { value:"",      label:"— Не выбрано —" },
  { value:"ТО-1В", label:"ТО-1В — Техническое обслуживание вагона №1" },
  { value:"ТО-2В", label:"ТО-2В — Техническое обслуживание вагона №2" },
  { value:"ТОР",   label:"ТОР — Текущий отцепочный ремонт" },
  { value:"ТОВ",   label:"ТОВ — Текущий отцепочный ремонт (внеплановый)" },
  { value:"ДР",    label:"ДР  — Деповской ремонт" },
  { value:"КРВ",   label:"КРВ — Капитальный ремонт вагона" },
  { value:"ВНВ",   label:"ВНВ — Внеплановый ремонт вагона" },
]

// Для обратной совместимости
const repairKinds = repairKindsLoco

/* ════════════════════════════════════════
   ШАБЛОНЫ ТМЦ
════════════════════════════════════════ */
type TmcTemplate = { name:string; invNo:string; unit:string; qty:string; note:string }
const tmcTemplates: Record<string, TmcTemplate[]> = {
  "ТО-1": [
    { name:"Масло дизельное М-14В2 (канистра 20 л)",       invNo:"МТР-00101", unit:"кан.", qty:"1", note:"Долив картера" },
    { name:"Фильтр масляный (картридж)",                   invNo:"МТР-00102", unit:"шт.",  qty:"1", note:"" },
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"2", note:"" },
  ],
  "ТО-2": [
    { name:"Масло дизельное М-14В2 (канистра 20 л)",       invNo:"МТР-00101", unit:"кан.", qty:"2", note:"" },
    { name:"Фильтр масляный (картридж)",                   invNo:"МТР-00102", unit:"шт.",  qty:"2", note:"" },
    { name:"Смазка БУКСОЛ (картридж 800 г)",               invNo:"МТР-00203", unit:"шт.",  qty:"4", note:"Смазка букс" },
    { name:"Щётка угольная ЭГ-74 (тяговый двигатель)",    invNo:"МТР-00412", unit:"шт.",  qty:"4", note:"Контроль износа" },
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"3", note:"" },
  ],
  "ТО-3": [
    { name:"Масло дизельное М-14В2 (канистра 20 л)",       invNo:"МТР-00101", unit:"кан.", qty:"4", note:"Замена полная" },
    { name:"Фильтр масляный (картридж)",                   invNo:"МТР-00102", unit:"шт.",  qty:"4", note:"" },
    { name:"Фильтр топливный грубой очистки",              invNo:"МТР-00103", unit:"шт.",  qty:"2", note:"" },
    { name:"Смазка БУКСОЛ (картридж 800 г)",               invNo:"МТР-00203", unit:"шт.",  qty:"6", note:"" },
    { name:"Щётка угольная ЭГ-74 (тяговый двигатель)",    invNo:"МТР-00412", unit:"шт.",  qty:"8", note:"" },
    { name:"Подшипник роликовый 42228 ГОСТ 5721",          invNo:"МТР-00087", unit:"шт.",  qty:"2", note:"При необходимости" },
    { name:"Прокладка маслосборника (к-т)",                invNo:"МТР-00310", unit:"к-т",  qty:"1", note:"" },
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"5", note:"" },
  ],
  "ТР-1": [
    { name:"Масло дизельное М-14В2 (канистра 20 л)",       invNo:"МТР-00101", unit:"кан.", qty:"4", note:"" },
    { name:"Фильтр масляный (картридж)",                   invNo:"МТР-00102", unit:"шт.",  qty:"4", note:"" },
    { name:"Фильтр топливный грубой очистки",              invNo:"МТР-00103", unit:"шт.",  qty:"2", note:"" },
    { name:"Подшипник роликовый 42228 ГОСТ 5721",          invNo:"МТР-00087", unit:"шт.",  qty:"4", note:"" },
    { name:"Колодка тормозная чугунная ТМ-1 (тип А)",     invNo:"МТР-00033", unit:"шт.",  qty:"8", note:"" },
    { name:"Чека тормозной колодки",                       invNo:"МТР-00034", unit:"шт.",  qty:"8", note:"" },
    { name:"Смазка БУКСОЛ (картридж 800 г)",               invNo:"МТР-00203", unit:"шт.",  qty:"6", note:"" },
    { name:"Щётка угольная ЭГ-74 (тяговый двигатель)",    invNo:"МТР-00412", unit:"шт.",  qty:"8", note:"" },
    { name:"Лакоткань ЛХМ-105 (рулон 10 м)",              invNo:"МТР-00318", unit:"рул.", qty:"1", note:"" },
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"5", note:"" },
  ],
  "ТР-2": [
    { name:"Масло дизельное М-14В2 (канистра 20 л)",       invNo:"МТР-00101", unit:"кан.", qty:"6", note:"" },
    { name:"Масло трансмиссионное ТАД-17и (канистра 20 л)",invNo:"МТР-00145", unit:"кан.", qty:"4", note:"" },
    { name:"Фильтр масляный (картридж)",                   invNo:"МТР-00102", unit:"шт.",  qty:"6", note:"" },
    { name:"Подшипник роликовый 42228 ГОСТ 5721",          invNo:"МТР-00087", unit:"шт.",  qty:"8", note:"" },
    { name:"Колодка тормозная чугунная ТМ-1 (тип А)",     invNo:"МТР-00033", unit:"шт.",  qty:"16",note:"" },
    { name:"Прокладка редуктора колёсной пары",            invNo:"МТР-00722", unit:"шт.",  qty:"4", note:"" },
    { name:"Щётка угольная ЭГ-74 (тяговый двигатель)",    invNo:"МТР-00412", unit:"шт.",  qty:"16",note:"" },
    { name:"Лакоткань ЛХМ-105 (рулон 10 м)",              invNo:"МТР-00318", unit:"рул.", qty:"2", note:"" },
    { name:"Уплотнитель резиновый маслостойкий (м.п.)",    invNo:"МТР-00381", unit:"м.",   qty:"3", note:"" },
    { name:"Герметик силиконовый высокотемп. ABRO (100 мл)",invNo:"МТР-00499",unit:"шт.",  qty:"4", note:"" },
    { name:"Болт М12×40 нержавеющий (уп. 50 шт.)",        invNo:"МТР-00561", unit:"уп.",  qty:"2", note:"" },
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"8", note:"" },
  ],
  "ТР-3": [
    { name:"Масло дизельное М-14В2 (канистра 20 л)",       invNo:"МТР-00101", unit:"кан.", qty:"8", note:"" },
    { name:"Масло трансмиссионное ТАД-17и (канистра 20 л)",invNo:"МТР-00145", unit:"кан.", qty:"6", note:"" },
    { name:"Подшипник роликовый 42228 ГОСТ 5721",          invNo:"МТР-00087", unit:"шт.",  qty:"12",note:"" },
    { name:"Колодка тормозная чугунная ТМ-1 (тип А)",     invNo:"МТР-00033", unit:"шт.",  qty:"16",note:"" },
    { name:"Щётка угольная ЭГ-74 (тяговый двигатель)",    invNo:"МТР-00412", unit:"шт.",  qty:"16",note:"" },
    { name:"Секция тягового двигателя (к-т запчастей)",    invNo:"МТР-00750", unit:"к-т",  qty:"1", note:"" },
    { name:"Прокладка редуктора колёсной пары",            invNo:"МТР-00722", unit:"шт.",  qty:"8", note:"" },
    { name:"Лакоткань ЛХМ-105 (рулон 10 м)",              invNo:"МТР-00318", unit:"рул.", qty:"4", note:"" },
    { name:"Уплотнитель резиновый маслостойкий (м.п.)",    invNo:"МТР-00381", unit:"м.",   qty:"6", note:"" },
    { name:"Болт М12×40 нержавеющий (уп. 50 шт.)",        invNo:"МТР-00561", unit:"уп.",  qty:"4", note:"" },
    { name:"Шплинт 6×40 ГОСТ 397 (уп. 100 шт.)",          invNo:"МТР-00602", unit:"уп.",  qty:"2", note:"" },
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"10",note:"" },
  ],
  "СР": [
    { name:"Масло дизельное М-14В2 (канистра 20 л)",       invNo:"МТР-00101", unit:"кан.", qty:"10",note:"" },
    { name:"Масло трансмиссионное ТАД-17и (канистра 20 л)",invNo:"МТР-00145", unit:"кан.", qty:"8", note:"" },
    { name:"Подшипник роликовый 42228 ГОСТ 5721",          invNo:"МТР-00087", unit:"шт.",  qty:"16",note:"" },
    { name:"Колодка тормозная чугунная ТМ-1 (тип А)",     invNo:"МТР-00033", unit:"шт.",  qty:"32",note:"" },
    { name:"Щётка угольная ЭГ-74 (тяговый двигатель)",    invNo:"МТР-00412", unit:"шт.",  qty:"32",note:"" },
    { name:"Секция тягового двигателя (к-т запчастей)",    invNo:"МТР-00750", unit:"к-т",  qty:"2", note:"" },
    { name:"Трансформатор тяговый (ремкомплект)",          invNo:"МТР-00800", unit:"к-т",  qty:"1", note:"" },
    { name:"Лакоткань ЛХМ-105 (рулон 10 м)",              invNo:"МТР-00318", unit:"рул.", qty:"6", note:"" },
    { name:"Краска эмаль ПФ-115 (бочка 50 кг)",           invNo:"МТР-00850", unit:"шт.",  qty:"2", note:"Окраска кузова" },
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"15",note:"" },
  ],
  "КР": [
    { name:"Масло дизельное М-14В2 (канистра 20 л)",       invNo:"МТР-00101", unit:"кан.", qty:"15",note:"" },
    { name:"Масло трансмиссионное ТАД-17и (канистра 20 л)",invNo:"МТР-00145", unit:"кан.", qty:"10",note:"" },
    { name:"Подшипник роликовый 42228 ГОСТ 5721",          invNo:"МТР-00087", unit:"шт.",  qty:"24",note:"" },
    { name:"Колодка тормозная чугунная ТМ-1 (тип А)",     invNo:"МТР-00033", unit:"шт.",  qty:"32",note:"" },
    { name:"Щётка угольная ЭГ-74 (тяговый двигатель)",    invNo:"МТР-00412", unit:"шт.",  qty:"32",note:"" },
    { name:"Секция тягового двигателя (к-т запчастей)",    invNo:"МТР-00750", unit:"к-т",  qty:"4", note:"" },
    { name:"Трансформатор тяговый (ремкомплект)",          invNo:"МТР-00800", unit:"к-т",  qty:"1", note:"" },
    { name:"Токоприёмник (к-т для замены)",                invNo:"МТР-00820", unit:"к-т",  qty:"2", note:"" },
    { name:"Лакоткань ЛХМ-105 (рулон 10 м)",              invNo:"МТР-00318", unit:"рул.", qty:"8", note:"" },
    { name:"Краска эмаль ПФ-115 (бочка 50 кг)",           invNo:"МТР-00850", unit:"шт.",  qty:"4", note:"" },
    { name:"Уплотнитель резиновый маслостойкий (м.п.)",    invNo:"МТР-00381", unit:"м.",   qty:"10",note:"" },
    { name:"Болт М12×40 нержавеющий (уп. 50 шт.)",        invNo:"МТР-00561", unit:"уп.",  qty:"6", note:"" },
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"20",note:"" },
  ],
  "ВНП": [
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"3", note:"" },
  ],
  // ── Вагонные виды ремонта ──
  "ТО-1В": [
    { name:"Смазка БУКСОЛ (картридж 800 г)",               invNo:"МТР-00203", unit:"шт.",  qty:"4",  note:"Смазка букс" },
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"2",  note:"" },
  ],
  "ТО-2В": [
    { name:"Смазка БУКСОЛ (картридж 800 г)",               invNo:"МТР-00203", unit:"шт.",  qty:"8",  note:"" },
    { name:"Колодка тормозная чугунная ТМ-1 (тип А)",     invNo:"МТР-00033", unit:"шт.",  qty:"8",  note:"" },
    { name:"Чека тормозной колодки",                       invNo:"МТР-00034", unit:"шт.",  qty:"8",  note:"" },
    { name:"Рукав тормозной Р17Б (760 мм)",                invNo:"МТР-00430", unit:"шт.",  qty:"2",  note:"Контроль" },
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"3",  note:"" },
  ],
  "ТОР": [
    { name:"Подшипник буксовый роликовый 30-42726 Л2М",    invNo:"МТР-00091", unit:"шт.",  qty:"4",  note:"" },
    { name:"Смазка БУКСОЛ (картридж 800 г)",               invNo:"МТР-00203", unit:"шт.",  qty:"8",  note:"" },
    { name:"Колодка тормозная чугунная ТМ-1 (тип А)",     invNo:"МТР-00033", unit:"шт.",  qty:"8",  note:"" },
    { name:"Чека тормозной колодки",                       invNo:"МТР-00034", unit:"шт.",  qty:"8",  note:"" },
    { name:"Воздухораспределитель № 483М (комплект)",      invNo:"МТР-00421", unit:"к-т",  qty:"1",  note:"При необходимости" },
    { name:"Рукав тормозной Р17Б (760 мм)",                invNo:"МТР-00430", unit:"шт.",  qty:"2",  note:"" },
    { name:"Уплотнитель резиновый маслостойкий (м.п.)",    invNo:"МТР-00381", unit:"м.",   qty:"2",  note:"" },
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"4",  note:"" },
  ],
  "ТОВ": [
    { name:"Подшипник буксовый роликовый 30-42726 Л2М",    invNo:"МТР-00091", unit:"шт.",  qty:"2",  note:"" },
    { name:"Смазка БУКСОЛ (картридж 800 г)",               invNo:"МТР-00203", unit:"шт.",  qty:"4",  note:"" },
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"3",  note:"" },
  ],
  "ДР": [
    { name:"Подшипник буксовый роликовый 30-42726 Л2М",    invNo:"МТР-00091", unit:"шт.",  qty:"8",  note:"" },
    { name:"Смазка БУКСОЛ (картридж 800 г)",               invNo:"МТР-00203", unit:"шт.",  qty:"12", note:"" },
    { name:"Колодка тормозная чугунная ТМ-1 (тип А)",     invNo:"МТР-00033", unit:"шт.",  qty:"16", note:"" },
    { name:"Колодка тормозная композиционная ТИИР-300",    invNo:"МТР-00035", unit:"шт.",  qty:"8",  note:"Пассажирские" },
    { name:"Чека тормозной колодки",                       invNo:"МТР-00034", unit:"шт.",  qty:"16", note:"" },
    { name:"Воздухораспределитель № 483М (комплект)",      invNo:"МТР-00421", unit:"к-т",  qty:"1",  note:"" },
    { name:"Рукав тормозной Р17Б (760 мм)",                invNo:"МТР-00430", unit:"шт.",  qty:"4",  note:"" },
    { name:"Прокладка редуктора колёсной пары",            invNo:"МТР-00722", unit:"шт.",  qty:"4",  note:"" },
    { name:"Уплотнитель резиновый маслостойкий (м.п.)",    invNo:"МТР-00381", unit:"м.",   qty:"4",  note:"" },
    { name:"Болт М12×40 нержавеющий (уп. 50 шт.)",        invNo:"МТР-00561", unit:"уп.",  qty:"2",  note:"" },
    { name:"Краска эмаль ПФ-115 (бочка 50 кг)",           invNo:"МТР-00850", unit:"шт.",  qty:"1",  note:"Подкраска" },
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"8",  note:"" },
  ],
  "КРВ": [
    { name:"Подшипник буксовый роликовый 30-42726 Л2М",    invNo:"МТР-00091", unit:"шт.",  qty:"16", note:"" },
    { name:"Смазка БУКСОЛ (картридж 800 г)",               invNo:"МТР-00203", unit:"шт.",  qty:"16", note:"" },
    { name:"Колодка тормозная чугунная ТМ-1 (тип А)",     invNo:"МТР-00033", unit:"шт.",  qty:"32", note:"" },
    { name:"Колодка тормозная композиционная ТИИР-300",    invNo:"МТР-00035", unit:"шт.",  qty:"16", note:"" },
    { name:"Чека тормозной колодки",                       invNo:"МТР-00034", unit:"шт.",  qty:"32", note:"" },
    { name:"Воздухораспределитель № 483М (комплект)",      invNo:"МТР-00421", unit:"к-т",  qty:"2",  note:"" },
    { name:"Рукав тормозной Р17Б (760 мм)",                invNo:"МТР-00430", unit:"шт.",  qty:"8",  note:"" },
    { name:"Прокладка редуктора колёсной пары",            invNo:"МТР-00722", unit:"шт.",  qty:"8",  note:"" },
    { name:"Уплотнитель резиновый маслостойкий (м.п.)",    invNo:"МТР-00381", unit:"м.",   qty:"8",  note:"" },
    { name:"Болт М12×40 нержавеющий (уп. 50 шт.)",        invNo:"МТР-00561", unit:"уп.",  qty:"4",  note:"" },
    { name:"Краска эмаль ПФ-115 (бочка 50 кг)",           invNo:"МТР-00850", unit:"шт.",  qty:"3",  note:"Полная окраска" },
    { name:"Антикоррозийное покрытие Мовиль (0,5 л)",     invNo:"МТР-00860", unit:"шт.",  qty:"6",  note:"" },
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"15", note:"" },
  ],
  "ВНВ": [
    { name:"Ветошь обтирочная",                            invNo:"МТР-00900", unit:"кг.",  qty:"3",  note:"" },
  ],
}

/* ════════════════════════════════════════
   ТИПЫ
════════════════════════════════════════ */
type TmcRow = { 
  id: number
  name: string
  invNo: string
  unit: string
  qty: string
  note: string
  // Новые поля для валидации и расчёта стоимости
  standardQty?: number      // Нормативное количество
  avgPrice?: number         // Средняя цена
  estimatedCost?: number    // Расчётная стоимость
  warning?: string          // Предупреждение о превышении
  nomenclatureId?: string   // ID из справочника
}
type RepairItem = { id:number; kind:string; rows:TmcRow[] }

// Тип для нормативов из БД
type NomenclatureNorm = {
  id: string
  nomenclature_id: string
  department_id: string
  work_type: string
  standard_quantity: number
  avg_price: number
  nomenclature?: {
    id: string
    name: string
    code: string
    unit: string
  }
}
type UnitType  = "locomotive" | "wagon" | "diesel"
type WorkOrder = {
  id:string; unitType:UnitType; unit:string; desc:string; type:string; repairKind:string
  priority:string; status:string; tech:string; created:string; closed:string
  section:string; equipment:string
  // расширенные поля (опционально, для Supabase и формы)
  note?:string; repairItems?:RepairItem[]; dateStart?:string; dateEnd?:string
  depot?:string; chief?:string
}


const statusConfig: Record<string,{label:string;icon:React.ElementType;class:string}> = {
  completed:   { label:"Выполнен",  icon:CheckCircle,   class:"bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400" },
  in_progress: { label:"В работе",  icon:Wrench,        class:"bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400" },
  pending:     { label:"Ожидание",  icon:Clock,         class:"bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400" },
  overdue:     { label:"Просрочен", icon:AlertTriangle, class:"bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400" },
}
const priorityConfig: Record<string,{label:string;class:string}> = {
  critical: { label:"Критический", class:"bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400" },
  high:     { label:"Высокий",     class:"bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-400" },
  normal:   { label:"Обычный",     class:"bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300" },
  low:      { label:"Низкий",      class:"bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400" },
}

/* ════════════════════════════════════════
   COMBOBOX — поиск по справочнику ТМЦ
════════════════════════════════════════ */
function TmcCombobox({ value, onChange, onSelect, filteredItems }: {
  value: string
  onChange: (v: string) => void
  onSelect: (item: CatalogItem) => void
  filteredItems?: CatalogItem[]  // Отфильтрованные по участку позиции
}) {
  const [open, setOpen]   = useState(false)
  const [query, setQuery] = useState(value)
  const ref = useRef<HTMLDivElement>(null)

  // Синхронизируем query с внешним value при сбросе
  useEffect(() => { setQuery(value) }, [value])

  // Закрытие по клику вне
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  // Используем отфильтрованные по участку или общий справочник
  const baseCatalog = filteredItems && filteredItems.length > 0 ? filteredItems : tmcCatalog
  
  const filtered = query.length === 0
    ? baseCatalog
    : baseCatalog.filter(i =>
        i.name.toLowerCase().includes(query.toLowerCase()) ||
        i.invNo.toLowerCase().includes(query.toLowerCase()) ||
        i.category.toLowerCase().includes(query.toLowerCase())
      )

  // Группировка по категории
  const allCategories = [...new Set(baseCatalog.map(i => i.category))]
  const grouped = allCategories
    .map(cat => ({ cat, items: filtered.filter(i => i.category === cat) }))
    .filter(g => g.items.length > 0)

  return (
    <div ref={ref} className="relative w-full">
      <div className="relative">
        <input
          value={query}
          onFocus={() => setOpen(true)}
          onChange={e => { setQuery(e.target.value); onChange(e.target.value); setOpen(true) }}
          placeholder="Введите название или выберите из справочника..."
          className="w-full border border-gray-200 dark:border-gray-700 rounded px-2 py-1 pr-7 text-xs bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="absolute right-1.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-blue-500"
        >
          <BookOpen className="w-3.5 h-3.5" />
        </button>
      </div>

      {open && (
        <div className="absolute z-50 mt-1 w-[420px] max-h-64 overflow-auto bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg shadow-xl">
          {/* Поиск внутри дропдауна */}
          <div className="sticky top-0 bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800 px-2 py-1.5">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400" />
              <input
                autoFocus
                value={query}
                onChange={e => { setQuery(e.target.value); onChange(e.target.value) }}
                placeholder="Поиск по справочнику..."
                className="w-full pl-6 pr-2 py-1 text-xs border border-gray-200 dark:border-gray-700 rounded bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            </div>
          </div>

          {grouped.length === 0 && (
            <div className="px-3 py-4 text-xs text-gray-400 text-center">
              Позиция не найдена в справочнике.<br />
              <span className="text-blue-500">Значение будет добавлено вручную.</span>
            </div>
          )}

          {grouped.map(({ cat, items }) => (
            <div key={cat}>
              <div className="px-3 py-1 text-[10px] font-bold text-gray-400 uppercase tracking-widest bg-gray-50 dark:bg-gray-800/60 border-b border-gray-100 dark:border-gray-800 sticky top-[34px]">
                {cat}
              </div>
              {items.map(item => (
                <button
                  key={item.invNo}
                  type="button"
                  onMouseDown={e => {
                    e.preventDefault()
                    onSelect(item)
                    setQuery(item.name)
                    setOpen(false)
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-blue-50 dark:hover:bg-blue-950 transition-colors flex items-start gap-2 group"
                >
                  <span className="flex-1 text-xs text-gray-900 dark:text-white leading-snug group-hover:text-blue-700 dark:group-hover:text-blue-300">
                    {item.name}
                  </span>
                  <div className="flex-shrink-0 text-right">
                    <span className="block text-[10px] font-mono text-gray-400">{item.invNo}</span>
                    <span className="block text-[10px] text-gray-400">{item.unit}</span>
                  </div>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ════════════════════════════════════════
   UI HELPERS
════════════════════════════════════════ */
type SelectOption = string | { value: string; label: string; id?: string }
function FieldSelect({ value, onChange, options, placeholder }: {
  value:string; onChange:(v:string)=>void; options:SelectOption[]; placeholder:string
}) {
  return (
    <div className="relative">
      <select value={value} onChange={e=>onChange(e.target.value)}
        className="w-full appearance-none border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 pr-8 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500">
        <option value="">{placeholder}</option>
        {options.map((o, idx) => {
          const val = typeof o === "string" ? o : o.value
          const lbl = typeof o === "string" ? o : o.label
          const key = typeof o === "string" ? `${o}-${idx}` : (o.id || `${val}-${idx}`)
          return <option key={key} value={val}>{lbl}</option>
        })}
      </select>
      <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
    </div>
  )
}

function FormField({ label, required, error, children }:{label:string;required?:boolean;error?:string;children:React.ReactNode}) {
  return (
    <div>
      <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wide">
        {label}{required&&<span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
      {error&&<p className="text-xs text-red-500 mt-1">{error}</p>}
    </div>
  )
}

/* ════════════════════════════════════════
   МОДАЛЬНОЕ ОКНО ТМЦ
════════════════════════════════════════ */
function TmcModal({ repairKind, rows, onSave, onClose, zClass = "z-[60]", departmentId, workType }: {
  repairKind: string
  rows: TmcRow[]
  onSave: (rows: TmcRow[]) => void
  onClose: () => void
  zClass?: string
  departmentId?: string    // ID участка мастера для фильтрации
  workType?: string        // Вид работ для автозаполнения шаблона
}) {
  const [localRows, setLocalRows] = useState<TmcRow[]>(rows)
  const [nextId, setNextId] = useState(rows.length + 1)
  const [norms, setNorms] = useState<NomenclatureNorm[]>([])
  const [filteredNomenclature, setFilteredNomenclature] = useState<CatalogItem[]>([])
  const [totalEstimatedCost, setTotalEstimatedCost] = useState(0)

  const newId = () => { const id = nextId; setNextId(n => n + 1); return id }

  // Загрузка нормативов по участку мастера
  useEffect(() => {
    async function loadNorms() {
      if (!departmentId) return
      
      const { data } = await supabase
        .from("nomenclature_norms")
        .select(`
          id, nomenclature_id, department_id, work_type, 
          standard_quantity, avg_price,
          nomenclature:nomenclature_id (id, name, code, unit)
        `)
        .eq("department_id", departmentId)
      
      if (data) {
        setNorms(data as NomenclatureNorm[])
        
        // Фильтруем справочник ТМЦ по нормативам участка
        const filtered = (data as NomenclatureNorm[])
          .filter(n => n.nomenclature)
          .map(n => ({
            name: n.nomenclature!.name,
            invNo: n.nomenclature!.code,
            unit: n.nomenclature!.unit,
            category: "Нормативы участка",
            standardQty: n.standard_quantity,
            avgPrice: n.avg_price,
            nomenclatureId: n.nomenclature_id,
          }))
        setFilteredNomenclature(filtered as CatalogItem[])
      }
    }
    loadNorms()
  }, [departmentId])

  // Автозаполнение шаблона при выборе ТО-2 или ПТОЛ ТО-2
  useEffect(() => {
    async function loadTemplate() {
      if (!workType || !departmentId) return
      
      // Проверяем, нужно ли загружать шаблон (ТО-2, ПТОЛ ТО-2)
      const isTO2 = workType.includes("ТО-2") || workType.includes("ПТОЛ")
      if (!isTO2 || localRows.length > 0) return
      
      const { data } = await supabase
        .from("work_type_templates")
        .select(`
          id, work_type, default_quantity, sort_order,
          nomenclature:nomenclature_id (id, name, code, unit)
        `)
        .eq("work_type", workType)
        .eq("department_id", departmentId)
        .order("sort_order")
      
      if (data && data.length > 0) {
        const templateRows: TmcRow[] = data
          .filter((t: { nomenclature?: { id: string; name: string; code: string; unit: string } }) => t.nomenclature)
          .map((t: { nomenclature?: { id: string; name: string; code: string; unit: string }; default_quantity: number }, i: number) => ({
            id: i + 1,
            name: t.nomenclature!.name,
            invNo: t.nomenclature!.code,
            unit: t.nomenclature!.unit,
            qty: String(t.default_quantity),
            note: "Из шаблона " + workType,
            nomenclatureId: t.nomenclature!.id,
          }))
        
        if (templateRows.length > 0) {
          setLocalRows(templateRows)
          setNextId(templateRows.length + 1)
        }
      }
    }
    loadTemplate()
  }, [workType, departmentId, localRows.length])

  // Валидация количества и расчёт стоимости
  const validateAndCalculate = useCallback((row: TmcRow): TmcRow => {
    const qty = parseFloat(row.qty) || 0
    const norm = norms.find(n => 
      n.nomenclature?.name === row.name || 
      n.nomenclature?.code === row.invNo ||
      n.nomenclature_id === row.nomenclatureId
    )
    
    let warning: string | undefined
    let estimatedCost = 0
    let standardQty = row.standardQty
    let avgPrice = row.avgPrice
    
    if (norm) {
      standardQty = norm.standard_quantity
      avgPrice = norm.avg_price
      
      // Проверка превышения норматива на 20%
      const threshold = standardQty * 1.2
      if (qty > threshold) {
        const overPercent = Math.round(((qty - standardQty) / standardQty) * 100)
        warning = `Превышение норматива на ${overPercent}% (норма: ${standardQty})`
      }
      
      // Расчёт стоимости
      estimatedCost = qty * avgPrice
    }
    
    return { ...row, warning, estimatedCost, standardQty, avgPrice }
  }, [norms])

  // Пересчёт при изменении строк
  useEffect(() => {
    const total = localRows.reduce((sum, row) => sum + (row.estimatedCost || 0), 0)
    setTotalEstimatedCost(total)
  }, [localRows])

  const addRow = () => setLocalRows(r => [...r, { 
    id: newId(), name: "", invNo: "", unit: "шт.", qty: "1", note: "" 
  }])
  
  const removeRow = (id: number) => setLocalRows(r => r.filter(x => x.id !== id))
  
  const updateRow = (id: number, field: keyof TmcRow, value: string) => {
    setLocalRows(r => r.map(x => {
      if (x.id !== id) return x
      const updated = { ...x, [field]: value }
      // Валидация при изменении количества
      if (field === "qty") {
        return validateAndCalculate(updated)
      }
      return updated
    }))
  }
  
  const selectFromCatalog = (id: number, item: CatalogItem) => {
    setLocalRows(r => r.map(x => {
      if (x.id !== id) return x
      const updated = { 
        ...x, 
        name: item.name, 
        invNo: item.invNo, 
        unit: item.unit,
        nomenclatureId: (item as CatalogItem & { nomenclatureId?: string }).nomenclatureId,
        standardQty: (item as CatalogItem & { standardQty?: number }).standardQty,
        avgPrice: (item as CatalogItem & { avgPrice?: number }).avgPrice,
      }
      return validateAndCalculate(updated)
    }))
  }

  return (
    <div className={`fixed inset-0 ${zClass} flex items-center justify-center`}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose}/>
      <div className="relative z-10 w-full max-w-5xl mx-4 bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 flex flex-col max-h-[90vh]">

        {/* Шапка */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center shadow-md">
              <Package className="w-4.5 h-4.5 text-white"/>
            </div>
            <div>
              <h2 className="text-base font-bold text-gray-900 dark:text-white">Потребность в ТМЦ</h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {repairKind
                  ? <>Материалы для <span className="font-semibold text-blue-600 dark:text-blue-400">{repairKind}</span> · выберите из справочника или введите вручную</>
                  : "Добавьте позиции из справочника или вручную"}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
            <X className="w-5 h-5 text-gray-500"/>
          </button>
        </div>

        {/* Тело */}
        <div className="flex-1 overflow-y-auto">
          {/* Тулбар */}
          <div className="flex items-center justify-between px-6 py-3 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 sticky top-0 z-10">
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <BookOpen className="w-3.5 h-3.5 text-blue-500"/>
              <span>Выберите позицию из справочника или введите вручную</span>
              {localRows.length > 0 && (
                <span className="ml-2 px-2 py-0.5 rounded-full bg-blue-600 text-white font-bold text-[10px]">{localRows.length}</span>
              )}
            </div>
            <button onClick={addRow}
              className="flex items-center gap-1.5 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:text-blue-800 transition-colors px-3 py-1.5 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-950">
              <PackagePlus className="w-3.5 h-3.5"/> Добавить строку
            </button>
          </div>

          <table className="w-full text-xs table-fixed">
            <colgroup>
              <col style={{width:"32px"}}/>
              <col/>
              <col style={{width:"100px"}}/>
              <col style={{width:"60px"}}/>
              <col style={{width:"65px"}}/>
              <col style={{width:"90px"}}/>
              <col style={{width:"120px"}}/>
              <col style={{width:"32px"}}/>
            </colgroup>
            <thead className="sticky top-[44px] z-10">
              <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                <th className="px-2 py-2.5 text-center text-gray-500 font-semibold">№</th>
                <th className="px-2 py-2.5 text-left text-gray-500 font-semibold">
                  Наименование ТМЦ
                  <span className="ml-1 text-[10px] font-normal text-blue-400 normal-case">(справочник)</span>
                </th>
                <th className="px-2 py-2.5 text-center text-gray-500 font-semibold">Инв. номер</th>
                <th className="px-2 py-2.5 text-center text-gray-500 font-semibold">Ед.</th>
                <th className="px-2 py-2.5 text-center text-gray-500 font-semibold">Кол-во</th>
                <th className="px-2 py-2.5 text-right text-gray-500 font-semibold">
                  Стоимость
                  <span className="ml-1 text-[9px] font-normal text-green-500 normal-case">(сум)</span>
                </th>
                <th className="px-2 py-2.5 text-left text-gray-500 font-semibold">Примечание</th>
                <th className="px-2 py-2.5"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {localRows.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center">
                    <div className="flex flex-col items-center gap-3 text-gray-400">
                      <Package className="w-10 h-10 opacity-30"/>
                      <p className="text-sm font-medium">Нет позиций</p>
                      <p className="text-xs">Нажмите «Добавить строку» или выберите вид ремонта в форме</p>
                    </div>
                  </td>
                </tr>
              )}
              {localRows.map((row, idx) => (
                <tr key={row.id} className={`bg-white dark:bg-gray-900 hover:bg-gray-50/50 dark:hover:bg-gray-800/30 ${
                  row.warning ? "bg-amber-50/50 dark:bg-amber-950/20" : ""
                }`}>
                  <td className="px-2 py-2 text-center text-gray-400 font-mono text-[11px]">{idx + 1}</td>
                  <td className="px-2 py-2">
                    <TmcCombobox
                      value={row.name}
                      onChange={v => updateRow(row.id, "name", v)}
                      onSelect={item => selectFromCatalog(row.id, item)}
                      filteredItems={filteredNomenclature}
                    />
                    {/* Предупреждение о превышении норматива */}
                    {row.warning && (
                      <div className="flex items-center gap-1 mt-1 text-[10px] text-amber-600 dark:text-amber-400">
                        <AlertTriangle className="w-3 h-3 flex-shrink-0"/>
                        <span>{row.warning}</span>
                      </div>
                    )}
                  </td>
                  <td className="px-2 py-2">
                    <input value={row.invNo} onChange={e => updateRow(row.id, "invNo", e.target.value)}
                      placeholder="МТР-00000"
                      className="w-full border border-gray-200 dark:border-gray-700 rounded px-1.5 py-1 text-xs bg-white dark:bg-gray-800 text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-400"/>
                  </td>
                  <td className="px-2 py-2">
                    <select value={row.unit} onChange={e => updateRow(row.id, "unit", e.target.value)}
                      className="w-full border border-gray-200 dark:border-gray-700 rounded px-1 py-1 text-xs bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-blue-400">
                      {["шт.","кг.","м.","л.","уп.","рул.","кан.","к-т"].map(u => <option key={u}>{u}</option>)}
                    </select>
                  </td>
                  <td className="px-2 py-2">
                    <input type="number" min="0" value={row.qty} onChange={e => updateRow(row.id, "qty", e.target.value)}
                      placeholder="0"
                      className={`w-full border rounded px-1.5 py-1 text-xs bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-1 ${
                        row.warning 
                          ? "border-amber-400 dark:border-amber-600 focus:ring-amber-400" 
                          : "border-gray-200 dark:border-gray-700 focus:ring-blue-400"
                      }`}/>
                    {/* Норматив под полем */}
                    {row.standardQty && (
                      <p className="text-[9px] text-gray-400 mt-0.5 text-center">
                        норма: {row.standardQty}
                      </p>
                    )}
                  </td>
                  <td className="px-2 py-2 text-right">
                    {/* Расчётная стоимость (estimated_cost) */}
                    {row.estimatedCost ? (
                      <div>
                        <span className="font-semibold text-green-600 dark:text-green-400">
                          {row.estimatedCost.toLocaleString("ru-RU")}
                        </span>
                        {row.avgPrice && (
                          <p className="text-[9px] text-gray-400 mt-0.5">
                            {row.avgPrice.toLocaleString("ru-RU")}/ед.
                          </p>
                        )}
                      </div>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-2 py-2">
                    <input value={row.note} onChange={e => updateRow(row.id, "note", e.target.value)}
                      placeholder="—"
                      className="w-full border border-gray-200 dark:border-gray-700 rounded px-1.5 py-1 text-xs bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-blue-400"/>
                  </td>
                  <td className="px-2 py-2 text-center">
                    <button onClick={() => removeRow(row.id)}
                      className="p-1 rounded hover:bg-red-50 dark:hover:bg-red-950 text-gray-300 hover:text-red-500 transition-colors">
                      <Trash2 className="w-3.5 h-3.5"/>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Подвал */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 flex-shrink-0">
          <div className="flex items-center gap-6">
            <p className="text-xs text-gray-500">
              Позиций: <span className="font-semibold text-gray-900 dark:text-white">{localRows.length}</span>
            </p>
            {totalEstimatedCost > 0 && (
              <p className="text-xs text-gray-500">
                Расчётная стоимость: 
                <span className="ml-1 font-bold text-green-600 dark:text-green-400">
                  {totalEstimatedCost.toLocaleString("ru-RU")} сум
                </span>
              </p>
            )}
            {localRows.some(r => r.warning) && (
              <p className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                <AlertTriangle className="w-3 h-3"/>
                Есть превышения норматива
              </p>
            )}
          </div>
          <div className="flex gap-3">
            <Button variant="outline" onClick={onClose}>Отмена</Button>
            <Button className="gap-2 bg-blue-600 hover:bg-blue-700" onClick={() => onSave(localRows)}>
              <Save className="w-4 h-4"/>Сохранить ТМЦ
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ════════════════════════════════════════
   МОДАЛ УПРАВЛЕНИЯ ВИДАМИ РАБОТ И ТМЦ
════════════════════════════════════════ */
function RepairItemsModal({ repairItems, repairKinds, onSave, onClose, tmcTemplatesData, departmentId }: {
  repairItems: RepairItem[]
  repairKinds: { value: string; label: string }[]
  onSave: (items: RepairItem[]) => void
  onClose: () => void
  tmcTemplatesData?: Record<string, TmcTemplate[]>
  departmentId?: string  // ID участка мастера для фильтрации ТМЦ
}) {
  const [localItems, setLocalItems] = useState<RepairItem[]>(repairItems)
  const [idCnt,      setIdCnt]      = useState(repairItems.length + 1)
  const [addingKind, setAddingKind] = useState("")
  const [tmcEditId,  setTmcEditId]  = useState<number|null>(null)

  // Используем шаблоны из БД или захардкоженные (fallback)
  const templates = tmcTemplatesData && Object.keys(tmcTemplatesData).length > 0
    ? tmcTemplatesData
    : tmcTemplates

  const addItem = () => {
    if (!addingKind) return
    if (localItems.some(r => r.kind === addingKind)) { setAddingKind(""); return }
    const id = idCnt
    setIdCnt(n => n + 1)
    const rows = (templates[addingKind] || []).map((t, i) => ({ id: i + 1, ...t }))
    setLocalItems(r => [...r, { id, kind: addingKind, rows }])
    setAddingKind("")
  }

  const removeItem = (id: number) => setLocalItems(r => r.filter(x => x.id !== id))

  const setItemRows = (id: number, rows: TmcRow[]) =>
    setLocalItems(r => r.map(x => x.id === id ? { ...x, rows } : x))

  const tmcItem = localItems.find(r => r.id === tmcEditId) ?? null
  const totalTmc = localItems.reduce((acc, r) => acc + r.rows.length, 0)

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose}/>
      <div className="relative z-10 w-full max-w-3xl mx-4 bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 flex flex-col max-h-[88vh]">

        {/* Шапка */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center shadow-md">
              <Wrench className="w-4.5 h-4.5 text-white"/>
            </div>
            <div>
              <h2 className="text-base font-bold text-gray-900 dark:text-white">Виды работ и ТМЦ</h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Добавьте виды работ и укажите материалы для каждого
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
            <X className="w-5 h-5 text-gray-500"/>
          </button>
        </div>

        {/* Тело */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-3">

          {/* Список видов работ */}
          {localItems.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 text-gray-400">
              <Wrench className="w-12 h-12 opacity-20 mb-3"/>
              <p className="text-sm font-medium">Виды работ не добавлены</p>
              <p className="text-xs mt-1">Выберите вид работы из списка ниже</p>
            </div>
          )}

          {localItems.map((item, idx) => {
            const kindLabel = repairKinds.find(r => r.value === item.kind)?.label ?? item.kind
            const tmcCount  = item.rows.length
            return (
              <div key={item.id}
                className="flex items-center gap-3 p-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 hover:border-blue-300 dark:hover:border-blue-700 transition-colors group">
                {/* Номер */}
                <span className="w-7 h-7 flex-shrink-0 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center">
                  {idx + 1}
                </span>
                {/* Инфо */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">{kindLabel}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    {tmcCount > 0 ? (
                      <>
                        <span className="text-blue-600 dark:text-blue-400 font-semibold">{tmcCount}</span> позиций ТМЦ
                        <span className="ml-2 text-gray-400">
                          {item.rows.filter(r=>r.name).slice(0,2).map(r=>r.name).join(", ")}
                          {tmcCount > 2 && ` +${tmcCount-2}`}
                        </span>
                      </>
                    ) : (
                      <span className="text-amber-500 font-medium">⚠ ТМЦ не указаны</span>
                    )}
                  </p>
                </div>
                {/* Кнопка ТМЦ */}
                <button type="button" onClick={() => setTmcEditId(item.id)}
                  className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border transition-colors
                    border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950
                    hover:bg-blue-600 hover:text-white hover:border-blue-600 whitespace-nowrap">
                  <Package className="w-3.5 h-3.5"/>
                  {tmcCount > 0 ? "Изменить ТМЦ" : "Добавить ТМЦ"}
                </button>
                {/* Удалить */}
                <button type="button" onClick={() => removeItem(item.id)}
                  className="p-1.5 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950 transition-colors">
                  <Trash2 className="w-4 h-4"/>
                </button>
              </div>
            )
          })}

          {/* Добавить вид */}
          <div className="flex gap-2 pt-2 border-t border-dashed border-gray-200 dark:border-gray-700">
            <div className="flex-1 relative">
              <select value={addingKind} onChange={e => setAddingKind(e.target.value)}
                className="w-full appearance-none border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 pr-8 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="">— Выберите вид работ для добавления —</option>
                {repairKinds.filter(r => r.value && !localItems.some(x => x.kind === r.value)).map(r => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
              <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"/>
            </div>
            <Button type="button" onClick={addItem} disabled={!addingKind}
              className="gap-1.5 bg-blue-600 hover:bg-blue-700 text-white flex-shrink-0">
              <Plus className="w-4 h-4"/> Добавить
            </Button>
          </div>

          {addingKind && templates[addingKind] && (
            <p className="text-xs text-blue-600 dark:text-blue-400 flex items-center gap-1">
              <Info className="w-3 h-3 flex-shrink-0"/>
              Шаблон ТМЦ для <b>{addingKind}</b> будет подгружен автоматически ({templates[addingKind].length} позиций)
            </p>
          )}
        </div>

        {/* Подвал */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 flex-shrink-0">
          <p className="text-xs text-gray-500">
            Видов работ: <span className="font-semibold text-gray-900 dark:text-white">{localItems.length}</span>
            {totalTmc > 0 && <> · ТМЦ позиций: <span className="font-semibold text-blue-600 dark:text-blue-400">{totalTmc}</span></>}
          </p>
          <div className="flex gap-3">
            <Button variant="outline" onClick={onClose}>Отмена</Button>
            <Button className="gap-2 bg-blue-600 hover:bg-blue-700" onClick={() => onSave(localItems)}>
              <Save className="w-4 h-4"/>Применить
            </Button>
          </div>
        </div>
      </div>

      {/* ТМЦ для конкретного вида — z-[70], поверх этого модала */}
      {tmcItem && (
        <TmcModal
          repairKind={tmcItem.kind}
          rows={tmcItem.rows}
          zClass="z-[70]"
          departmentId={departmentId}
          workType={tmcItem.kind}
          onSave={(rows) => { setItemRows(tmcItem.id, rows); setTmcEditId(null) }}
          onClose={() => setTmcEditId(null)}
        />
      )}
    </div>
  )
}

/* ════════════════════════════════════════
   ФОРМА СОЗДАНИЯ НАРЯДА
════════════════════════════════════════ */
type EmployeeOption = { id: string; tab_number: string; full_name: string; section_id: string | null }
type WorkTypeFromDb = { id: string; code: string; name: string; unit_type: "locomotive" | "wagon" | "diesel" }
type FixedAsset = { id: string; name: string; series: string; inv_number: string; asset_type: "locomotive" | "wagon" | "diesel" | string; initial_cost: string | null }

function CreateWorkOrderModal({ onClose, onSave, defaultUnit="", defaultSection="", sections, employees, onRefreshData, workTypesDb, tmcTemplatesDb, fixedAssets, getSectionId }:{
  onClose:()=>void
  onSave:(wo:WorkOrder)=>void
  defaultUnit?: string
  defaultSection?: string
  sections: string[]
  employees: EmployeeOption[]
  onRefreshData?: () => void
  workTypesDb?: WorkTypeFromDb[]
  tmcTemplatesDb?: Record<string, TmcTemplate[]>
  fixedAssets?: FixedAsset[]
  getSectionId?: (name: string) => string | undefined
}) {
  // Фактическая дата и время создания
  const now = new Date()
  const createdDate = now.toLocaleDateString("ru-RU")
  const createdTime = now.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
  const createdDateTime = `${createdDate} ${createdTime}`

  // Значения по умолчанию для плановых дат
  const defaultStartDate = now.toISOString().slice(0, 10)
  const defaultStartTime = now.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })

  const [unitType,      setUnitType]      = useState<UnitType>("locomotive")
  const [selectedSeries, setSelectedSeries] = useState("")
  const [unit,          setUnit]          = useState(defaultUnit)
  const [depot,         setDepot]         = useState(defaultSection)
  const [workType,      setWorkType]      = useState("")
  const [status,        setStatus]        = useState("pending")
  const [priority,      setPriority]      = useState("normal")
  const [tech,          setTech]          = useState("")
  const [chief,         setChief]         = useState("")
  const [dateStart,     setDateStart]     = useState(defaultStartDate)
  const [timeStart,     setTimeStart]     = useState(defaultStartTime)
  const [dateEnd,       setDateEnd]       = useState("")
  const [timeEnd,       setTimeEnd]       = useState("")
  const [desc,          setDesc]          = useState("")
  const [note,          setNote]          = useState("")
  const [errors,        setErrors]        = useState<Record<string,string>>({})

  const [repairItems,   setRepairItems]   = useState<RepairItem[]>([])
  const [repairModalOpen, setRepairModalOpen] = useState(false)

  const handleUnitTypeChange = (t: UnitType) => {
    setUnitType(t)
    setSelectedSeries("")
    setUnit("")
    setRepairItems([])
  }

  const handleSeriesChange = (s: string) => {
    setSelectedSeries(s)
    setUnit("")
  }

  // Виды работ из БД или захардкоженные (fallback)
  // Тепловозы используют виды работ локомотивов (unit_type = "locomotive" или "diesel")
  const workTypeFilter = unitType === "diesel" ? ["diesel", "locomotive"] : [unitType]
  const currentRepairKinds = workTypesDb && workTypesDb.length > 0
    ? [
        { value: "", label: "— Не выбрано —" },
        ...workTypesDb
          .filter(wt => workTypeFilter.includes(wt.unit_type))
          .map(wt => ({ value: wt.code, label: `${wt.code} — ${wt.name}` }))
      ]
    : (unitType === "wagon" ? repairKindsWagon : repairKindsLoco)
  
  // Шаблоны ТМЦ из БД или захардкоженные (fallback)
  const currentTmcTemplates = tmcTemplatesDb && Object.keys(tmcTemplatesDb).length > 0
    ? tmcTemplatesDb
    : tmcTemplates

  // Основные средства из БД (без fallback - только реальные данные из справочника ОС)
  const assetsFromDb = fixedAssets ?? []
  
  // Фильтрация по типу оборудования
  const getAssetsByType = (type: UnitType) => {
    if (type === "wagon") {
      return assetsFromDb.filter(a => a.asset_type === "wagon")
    } else if (type === "diesel") {
      return assetsFromDb.filter(a => a.asset_type === "diesel")
    } else {
      // Локомотивы: asset_type === "locomotive" ИЛИ не указан тип
      return assetsFromDb.filter(a => a.asset_type === "locomotive" || !a.asset_type || a.asset_type === "")
    }
  }
  
  const filteredAssets = getAssetsByType(unitType)
  
  // Уникальные серии для выбранного типа оборудования
  const availableSeries = [...new Set(filteredAssets.map(a => a.series).filter(Boolean))].sort()
  
  // Оборудование отфильтрованное по серии (если выбрана)
  const currentUnits = filteredAssets
    .filter(a => !selectedSeries || a.series === selectedSeries)
    .map(a => {
      const extra = a.initial_cost ? ` (${a.initial_cost})` : ""
      const displayName = `${a.name}${extra}`
      return { value: a.name, label: displayName, id: a.id, series: a.series }
    })
    .filter(a => a.value)
  const unitLabel = unitType === "wagon" ? "Вагон" : unitType === "diesel" ? "Тепловоз" : "Локомотив"

  const totalTmcCount = repairItems.reduce((acc, r) => acc + r.rows.length, 0)
  
  const technicians = employees.map(e => e.full_name)

  const validate = () => {
    const e:Record<string,string>={}
    if (!unit)                    e.unit       = `Выберите ${unitLabel.toLowerCase()}`
    if (!workType)                e.workType   = "Выберите тип работ"
    if (repairItems.length === 0) e.repairKind = "Добавьте хотя бы один вид работ"
    if (!desc.trim())             e.desc       = "Укажите описание работ"
    if (!tech)                    e.tech       = "Выберите исполнителя"
    return e
  }

  const handleSave = () => {
    const e=validate()
    if (Object.keys(e).length){setErrors(e);return}
    const id = genOrderId()
    const repairKind = repairItems.map(r => r.kind).join(", ")
    // equipment — серия из номера единицы (часть до первого дефиса-цифры или первые символы)
    const equipmentVal = unit.replace(/-\d+$/, "").replace(/-\d+-.*/, "")
    const closed = status === "completed" ? createdDateTime : "—"
    // Формируем даты с временем
    const dateStartFull = dateStart && timeStart ? `${dateStart} ${timeStart}` : dateStart
    const dateEndFull = dateEnd && timeEnd ? `${dateEnd} ${timeEnd}` : dateEnd
    onSave({id,unitType,unit,section:depot||"—",equipment:equipmentVal||unit,desc:desc.trim(),type:workType,repairKind,priority,status,tech,created:createdDateTime,closed,dateStart:dateStartFull,dateEnd:dateEndFull,note,chief,depot})
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/50" onClick={onClose}/>
      <div className="relative ml-auto w-full max-w-4xl h-full bg-white dark:bg-gray-900 shadow-2xl flex flex-col overflow-hidden">

        {/* Шапка */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
              <ClipboardList className="w-4 h-4 text-white"/>
            </div>
            <div>
              <h2 className="text-base font-bold text-gray-900 dark:text-white">Новый наряд-задание</h2>
              <p className="text-xs text-gray-500">Создан: {createdDateTime}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
            <X className="w-5 h-5 text-gray-500"/>
          </button>
        </div>

        {/* Тело */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">

          {/* 1. Основные сведения */}
          <section>
            <h3 className="text-xs font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest mb-3 pb-1 border-b border-blue-100 dark:border-blue-900">
              1. Основные сведения
            </h3>

            {/* Переключатель Локомотив / Тепловоз / Вагон */}
            <div className="flex gap-2 mb-4 p-1 bg-gray-100 dark:bg-gray-800 rounded-xl">
              {([
                { value: "locomotive", label: "Локомотив" },
                { value: "diesel",     label: "Тепловоз" },
                { value: "wagon",      label: "Вагон" },
              ] as {value:UnitType;label:string}[]).map(opt => (
                <button key={opt.value} type="button"
                  onClick={() => handleUnitTypeChange(opt.value)}
                  className={`flex-1 py-2 px-4 rounded-lg text-sm font-semibold transition-all ${
                    unitType === opt.value
                      ? "bg-white dark:bg-gray-900 text-blue-600 dark:text-blue-400 shadow-sm"
                      : "text-gray-500 dark:text-gray-400 hover:text-gray-700"
                  }`}>
                  {opt.label}
                </button>
              ))}
            </div>

            {/* Выбор серии (если есть серии для данного типа) */}
            {availableSeries.length > 0 && (
              <div className="mb-4">
                <FormField label="Серия оборудования">
                  <FieldSelect 
                    placeholder="Все серии" 
                    value={selectedSeries} 
                    onChange={handleSeriesChange} 
                    options={[
                      { value: "", label: "— Все серии —", id: "all" },
                      ...availableSeries.map(s => ({ value: s, label: s, id: s }))
                    ]}
                  />
                </FormField>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <FormField label={unitLabel} required error={errors.unit}>
                <FieldSelect placeholder={`Выберите ${unitLabel.toLowerCase()}`} value={unit} onChange={setUnit} options={currentUnits}/>
              </FormField>
              <FormField label="Депо / Подразделение">
                <FieldSelect placeholder="Выберите участок" value={depot} onChange={setDepot} options={sections}/>
              </FormField>
              <FormField label="Тип работ" required error={errors.workType}>
                <FieldSelect placeholder="Выберите тип" value={workType} onChange={setWorkType} options={workTypes}/>
              </FormField>
              <FormField label="Приоритет">
                <FieldSelect placeholder="Приоритет" value={priority} onChange={setPriority} options={["Низкий","Обычный","Высокий","Критический"]}/>
              </FormField>
              <div className="col-span-2">
                <FormField label="Статус наряда" required>
                  <div className="relative">
                    <select value={status} onChange={e => setStatus(e.target.value)}
                      className={`w-full appearance-none rounded-lg px-3 py-2 pr-10 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-blue-500 border ${
                        status === "pending"     ? "bg-blue-50 border-blue-300 text-blue-700 dark:bg-blue-950 dark:border-blue-700 dark:text-blue-300" :
                        status === "in_progress" ? "bg-amber-50 border-amber-300 text-amber-700 dark:bg-amber-950 dark:border-amber-700 dark:text-amber-300" :
                        "bg-green-50 border-green-300 text-green-700 dark:bg-green-950 dark:border-green-700 dark:text-green-300"
                      }`}>
                      <option value="pending">Запланировано</option>
                      <option value="in_progress">Выполняется</option>
                      <option value="completed">Выполнено</option>
                    </select>
                    <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 opacity-50 pointer-events-none"/>
                  </div>
                </FormField>
              </div>
            </div>
            <div className="mt-4">
              <FormField label="Описание работ" required error={errors.desc}>
                <textarea value={desc} onChange={e=>setDesc(e.target.value)} rows={3}
                  placeholder="Подробно опишите содержание работ..."
                  className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"/>
              </FormField>
            </div>
          </section>

          {/* 2. Виды работ и ТМЦ — карточка-триггер */}
          <section>
            <h3 className="text-xs font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest mb-3 pb-1 border-b border-blue-100 dark:border-blue-900">
              2. Виды работ и ТМЦ
              {errors.repairKind && <span className="ml-2 text-red-500 text-xs font-normal normal-case">{errors.repairKind}</span>}
            </h3>

            <div className={`flex items-center gap-4 p-4 rounded-xl border transition-colors ${
              errors.repairKind
                ? "border-red-300 bg-red-50/40 dark:border-red-800 dark:bg-red-950/20"
                : repairItems.length > 0
                  ? "border-blue-200 dark:border-blue-800 bg-blue-50/40 dark:bg-blue-950/20"
                  : "border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/40"
            }`}>
              {/* Иконка */}
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${
                repairItems.length > 0 ? "bg-blue-600" : "bg-gray-200 dark:bg-gray-700"
              }`}>
                <Wrench className={`w-5 h-5 ${repairItems.length > 0 ? "text-white" : "text-gray-400"}`}/>
              </div>

              {/* Текст */}
              <div className="flex-1 min-w-0">
                {repairItems.length > 0 ? (
                  <>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">
                      {repairItems.length} {repairItems.length === 1 ? "вид работ" : repairItems.length < 5 ? "вида работ" : "видов работ"}
                      {totalTmcCount > 0 && (
                        <span className="ml-2 text-xs font-normal text-blue-600 dark:text-blue-400">
                          · {totalTmcCount} поз. ТМЦ
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5 truncate">
                      {repairItems.map(r => r.kind).join(", ")}
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-sm font-semibold text-gray-500 dark:text-gray-400">Виды работ не выбраны</p>
                    <p className="text-xs text-gray-400 mt-0.5">Нажмите кнопку, чтобы добавить виды работ и ТМЦ</p>
                  </>
                )}
              </div>

              {/* Кнопка */}
              <Button
                type="button"
                variant={repairItems.length > 0 ? "outline" : "default"}
                className={`gap-2 flex-shrink-0 ${repairItems.length === 0 ? "bg-blue-600 hover:bg-blue-700 text-white" : ""}`}
                onClick={() => setRepairModalOpen(true)}
              >
                <Wrench className="w-4 h-4"/>
                {repairItems.length > 0 ? "Редактировать" : "Добавить виды работ"}
              </Button>
            </div>
          </section>

          {/* 3. Исполнение */}
          <section>
            <div className="flex items-center justify-between mb-3 pb-1 border-b border-blue-100 dark:border-blue-900">
              <h3 className="text-xs font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest">
                3. Исполнение
              </h3>
              {onRefreshData && (
                <button
                  type="button"
                  onClick={onRefreshData}
                  className="text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Обновить справочники
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Исполнитель" required error={errors.tech}>
                <FieldSelect placeholder="Выберите исполнителя" value={tech} onChange={setTech} options={technicians}/>
              </FormField>
              <FormField label="Руководитель работ">
                <FieldSelect placeholder="Выберите руководителя" value={chief} onChange={setChief} options={technicians}/>
              </FormField>
              <FormField label="Плановая дата начала">
                <div className="flex gap-2">
                  <Input type="date" value={dateStart} onChange={e=>setDateStart(e.target.value)} className="text-sm flex-1"/>
                  <Input type="time" value={timeStart} onChange={e=>setTimeStart(e.target.value)} className="text-sm w-24"/>
                </div>
              </FormField>
              <FormField label="Плановая дата окончания">
                <div className="flex gap-2">
                  <Input type="date" value={dateEnd} onChange={e=>setDateEnd(e.target.value)} className="text-sm flex-1"/>
                  <Input type="time" value={timeEnd} onChange={e=>setTimeEnd(e.target.value)} className="text-sm w-24"/>
                </div>
              </FormField>
            </div>

            {/* Фактическая дата и время создания */}
            <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-950/30 rounded-lg border border-blue-200 dark:border-blue-800">
              <div className="flex items-center gap-2 text-sm">
                <Clock className="w-4 h-4 text-blue-600 dark:text-blue-400"/>
                <span className="text-gray-600 dark:text-gray-400">Фактическая дата создания:</span>
                <span className="font-semibold text-blue-700 dark:text-blue-300">{createdDateTime}</span>
              </div>
            </div>

            <div className="mt-4">
              <FormField label="Примечание">
                <textarea value={note} onChange={e=>setNote(e.target.value)} rows={2}
                  placeholder="Дополнительные указания..."
                  className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"/>
              </FormField>
            </div>
          </section>

        </div>

        {/* Подвал */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 flex-shrink-0">
          <p className="text-xs text-gray-500">Поля со <span className="text-red-500">*</span> обязательны</p>
          <div className="flex gap-3">
            <Button variant="outline" onClick={onClose}>Отмена</Button>
            <Button className="gap-2 bg-blue-600 hover:bg-blue-700" onClick={handleSave}>
              <Save className="w-4 h-4"/>Сохранить наряд
            </Button>
          </div>
        </div>
      </div>

      {/* Модал «Виды работ и ТМЦ» */}
      {repairModalOpen && (
        <RepairItemsModal
          repairItems={repairItems}
          repairKinds={currentRepairKinds}
          tmcTemplatesData={currentTmcTemplates}
          departmentId={getSectionId?.(depot)}
          onSave={(items) => { setRepairItems(items); setRepairModalOpen(false) }}
          onClose={() => setRepairModalOpen(false)}
        />
      )}
    </div>
  )
}

/* ════════════════════════════════════════
   МОДАЛ ПРОСМОТРА / РЕДАКТИРОВАНИЯ НАРЯДА
════════════════════════════════════════ */
function ViewEditOrderModal({ order, onClose, onSave, isMasterView = false, employees = [] }: {
  order: WorkOrder
  onClose: () => void
  onSave: (updated: WorkOrder) => void
  isMasterView?: boolean
  employees?: EmployeeOption[]
}) {
  const technicians = employees.map(e => e.full_name)
  const isReadOnly = order.status === "completed"

  const [desc,     setDesc]     = useState(order.desc)
  const [priority, setPriority] = useState(order.priority)
  const [tech,     setTech]     = useState(order.tech)
  const [note,     setNote]     = useState("")
  const [status,   setStatus]   = useState(order.status)
  const [editing,  setEditing]  = useState(false)

  const isEditing = (editing || isMasterView) && !isReadOnly

  const handleSave = () => {
    const today = new Date().toLocaleDateString("ru-RU")
    onSave({
      ...order,
      desc:     isMasterView ? order.desc : desc.trim(),
      priority: isMasterView ? order.priority : priority,
      tech:     isMasterView ? order.tech : tech,
      status,
      closed: status === "completed" ? today : order.closed,
    })
    onClose()
  }

  const handleStatusChange = (newStatus: string) => {
    if (isReadOnly) return
    setStatus(newStatus)
    if (!editing) setEditing(true)
  }

  const st = statusConfig[status] ?? statusConfig.pending
  const pr = priorityConfig[priority] ?? priorityConfig.normal

  const fieldCls = (editable: boolean) =>
    editable
      ? "w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
      : "w-full px-3 py-2 text-sm text-gray-900 dark:text-white bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700 cursor-default select-text"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose}/>
      <div className="relative z-10 w-full max-w-3xl mx-4 bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 flex flex-col max-h-[92vh]">

        {/* Шапка */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${st.class}`}>
              <st.icon className="w-4 h-4"/>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-gray-900 dark:text-white font-mono">{order.id}</h2>
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${st.class}`}>{st.label}</span>
                {isReadOnly && (
                  <span className="flex items-center gap-1 text-xs text-gray-400 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded-full">
                    <Lock className="w-3 h-3 inline mr-1"/> Только просмотр
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-500 mt-0.5">
                {order.unitType === "wagon" ? "Вагон" : "Локомотив"} · {order.unit} · Создан: {order.created}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
            <X className="w-5 h-5 text-gray-500"/>
          </button>
        </div>

        {/* Тело */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">

          {/* Статус наряда — справочник с выпадающим меню */}
          {!isReadOnly && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Статус наряда</p>
              <div className="relative">
                <select
                  value={status}
                  onChange={e => handleStatusChange(e.target.value)}
                  className={`w-full appearance-none rounded-xl px-4 py-3 pr-10 text-sm font-semibold focus:outline-none focus:ring-2 border-2 transition-all ${
                    status === "pending"
                      ? "bg-blue-50 border-blue-300 text-blue-700 dark:bg-blue-950/50 dark:border-blue-700 dark:text-blue-300 focus:ring-blue-400"
                      : status === "in_progress"
                      ? "bg-amber-50 border-amber-300 text-amber-700 dark:bg-amber-950/50 dark:border-amber-700 dark:text-amber-300 focus:ring-amber-400"
                      : "bg-green-50 border-green-300 text-green-700 dark:bg-green-950/50 dark:border-green-700 dark:text-green-300 focus:ring-green-400"
                  }`}>
                  <option value="pending">Запланировано — наряд создан, ожидает выполнения</option>
                  <option value="in_progress">Выполняется — работы в процессе</option>
                  <option value="completed">Выполнено — работы завершены, наряд закрывается</option>
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 opacity-50 pointer-events-none"/>
              </div>
              {status === "completed" && status !== order.status && (
                <p className="text-xs text-green-600 dark:text-green-400 mt-1.5 flex items-center gap-1">
                  <CheckCircle className="w-3 h-3"/> После сохранения наряд будет закрыт и заблокирован для изменений
                </p>
              )}
            </div>
          )}

          {/* Основная информация */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Участок</p>
              <p className="px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300">{order.section}</p>
            </div>
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Оборудование</p>
              <p className="px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300">{order.equipment} · {order.unit}</p>
            </div>
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Тип работ</p>
              <p className="px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300">{order.type}</p>
            </div>
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Вид ремонта</p>
              <p className="px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300">
                {order.repairKind || <span className="text-gray-400">—</span>}
              </p>
            </div>
          </div>

          {/* Описание */}
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
              Описание работ {isEditing && <span className="text-blue-500 normal-case font-normal">(редактируется)</span>}
            </p>
            {isEditing ? (
              <textarea value={desc} onChange={e=>setDesc(e.target.value)} rows={3}
                className="w-full border border-blue-400 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            ) : (
              <p className="px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 leading-relaxed min-h-[64px]">{desc}</p>
            )}
          </div>

          {/* Исполнитель + приоритет */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Исполнитель</p>
              {isEditing ? (
                <div className="relative">
                  <select value={tech} onChange={e=>setTech(e.target.value)} className={fieldCls(true)}>
                    <option value="">— Не назначен —</option>
                    {technicians.map(t=><option key={t} value={t}>{t}</option>)}
                  </select>
                  <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"/>
                </div>
              ) : (
                <p className={fieldCls(false)}>{tech || "—"}</p>
              )}
            </div>
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Приоритет</p>
              {isEditing ? (
                <div className="relative">
                  <select value={priority} onChange={e=>setPriority(e.target.value)} className={fieldCls(true)}>
                    <option value="low">Низкий</option>
                    <option value="normal">Обычный</option>
                    <option value="high">Высокий</option>
                    <option value="critical">Критический</option>
                  </select>
                  <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"/>
                </div>
              ) : (
                <span className={`inline-block px-3 py-2 text-sm font-medium rounded-lg ${pr.class}`}>{pr.label}</span>
              )}
            </div>
          </div>

          {/* Даты */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Дата создания</p>
              <p className={fieldCls(false)}>{order.created}</p>
            </div>
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Дата закрытия</p>
              <p className={fieldCls(false)}>{order.closed === "—" && status === "completed" ? new Date().toLocaleDateString("ru-RU") : order.closed}</p>
            </div>
          </div>

          {/* Примечание */}
          {isEditing && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Примечание к изменениям
              </p>
              <textarea value={note} onChange={e=>setNote(e.target.value)} rows={2}
                placeholder="Укажите причину изменений..."
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            </div>
          )}
        </div>

        {/* Подвал */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 flex-shrink-0">
          {isReadOnly ? (
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <Lock className="w-4 h-4"/> <span>Наряд выполнен и закрыт — редактирование недоступно</span>
            </div>
          ) : !isEditing ? (
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <Info className="w-4 h-4"/>
              <span>Нажмите «Редактировать» для изменения данных</span>
            </div>
          ) : (
            <p className="text-xs text-blue-600 dark:text-blue-400">Данные изменены — не забудьте сохранить</p>
          )}

          <div className="flex gap-3">
            <Button variant="outline" onClick={onClose}>Закрыть</Button>
            {!isReadOnly && !isEditing && !isMasterView && (
              <Button className="gap-2 bg-blue-600 hover:bg-blue-700" onClick={() => setEditing(true)}>
                <Wrench className="w-4 h-4"/> Редактировать
              </Button>
            )}
            {(isEditing || isMasterView) && !isReadOnly && (
              <Button className="gap-2 bg-green-600 hover:bg-green-700" onClick={handleSave}>
                <Save className="w-4 h-4"/> Сохранить статус
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ════════════════════════════════════════
   СТРАНИЦА
════════════════════════════════════════ */

function genOrderId(): string {
  const now = new Date()
  const y  = now.getFullYear()
  const mo = String(now.getMonth() + 1).padStart(2, "0")
  const d  = String(now.getDate()).padStart(2, "0")
  const h  = String(now.getHours()).padStart(2, "0")
  const mi = String(now.getMinutes()).padStart(2, "0")
  const s  = String(now.getSeconds()).padStart(2, "0")
  return `НЗ-${y}${mo}${d}-${h}${mi}${s}`
}

// Конвертация WorkOrder → строка БД
function toRow(o: WorkOrder) {
  return {
    id:           o.id,
    unit_type:    o.unitType,
    unit:         o.unit,
    depot:        o.depot ?? o.section,
    section:      o.section,
    equipment:    o.equipment,
    work_type:    o.type,           // WorkOrder.type → work_type
    repair_kind:  o.repairKind,
    status:       o.status,
    priority:     o.priority,
    tech:         o.tech,
    chief:        o.chief ?? "",
    description:  o.desc,
    note:         o.note ?? "",
    created:      o.created,
    closed:       o.closed,
    repair_items: o.repairItems ?? [],
    date_start:   o.dateStart ?? "",
    date_end:     o.dateEnd ?? "",
  }
}

// Конвертация строки БД → WorkOrder
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function fromRow(r: any): WorkOrder {
  return {
    id:          r.id,
    unitType:    r.unit_type,
    unit:        r.unit,
    depot:       r.depot,
    section:     r.section,
    equipment:   r.equipment,
    type:        r.work_type,       // work_type → WorkOrder.type
    repairKind:  r.repair_kind,
    status:      r.status,
    priority:    r.priority,
    tech:        r.tech,
    chief:       r.chief,
    desc:        r.description,
    note:        r.note,
    created:     r.created,
    closed:      r.closed,
    repairItems: r.repair_items ?? [],
    dateStart:   r.date_start,
    dateEnd:     r.date_end,
  }
}

function WorkOrdersPage() {
  const searchParams = useSearchParams()
  const router       = useRouter()

  const { profile } = useAuth()
  const isMaster   = profile?.role === "master"

  const [orders,         setOrders]         = useState<WorkOrder[]>([])
  const [employees,      setEmployees]      = useState<EmployeeOption[]>([])
  const [workTypesDb,    setWorkTypesDb]    = useState<WorkTypeFromDb[]>([])
  const [tmcTemplatesDb, setTmcTemplatesDb] = useState<Record<string, TmcTemplate[]>>({})
  const [fixedAssets,    setFixedAssets]    = useState<FixedAsset[]>([])
  const [loading,        setLoading]        = useState(true)
  const [showForm,       setShowForm]        = useState(false)
  const [formDefUnit,    setFormDefUnit]     = useState("")
  const [formDefSection, setFormDefSection]  = useState("")
  const [selectedOrder,  setSelectedOrder]   = useState<WorkOrder|null>(null)
  const [search,         setSearch]          = useState("")
  const [tabStatus,      setTabStatus]       = useState<string>("open")
  const [fSection,       setFSection]        = useState("")
  const [fEquip,         setFEquip]          = useState("")
  const [fUnitType,      setFUnitType]       = useState("")

  // Справочник участков (перемещён выше для использования в realtime подписке)
  const { sections: sectionsFromDb, refresh: refreshSections, getSectionId } = useSections()

  // Загрузка работников из справочника
  const fetchEmployees = useCallback(async () => {
    const { data } = await supabase
      .from("employees")
      .select("id, tab_number, full_name, section_id")
      .order("full_name")
    setEmployees((data as EmployeeOption[]) ?? [])
  }, [])

  // Загрузка основных средств (все записи из справочника ОС)
  const fetchFixedAssets = useCallback(async () => {
    const { data } = await supabase
      .from("fixed_assets")
      .select("id, name, series, inv_number, asset_type, initial_cost")
      .order("name")
      .limit(1000)
    setFixedAssets((data as FixedAsset[]) ?? [])
  }, [])

  // Загрузка видов работ из справочника
  const fetchWorkTypes = useCallback(async () => {
    const { data: wtData } = await supabase
      .from("work_types")
      .select("id, code, name, unit_type")
      .order("sort_order")
      .order("code")
    
    const types = (wtData as WorkTypeFromDb[]) ?? []
    setWorkTypesDb(types)

    // Загрузка шаблонов ТМЦ для каждого вида работ
    if (types.length > 0) {
      const ids = types.map(t => t.id)
      const { data: tmcData } = await supabase
        .from("work_type_tmc")
        .select("work_type_id, name, inv_no, unit, qty, note")
        .in("work_type_id", ids)
        .order("sort_order")

      const templates: Record<string, TmcTemplate[]> = {}
      for (const t of tmcData ?? []) {
        const wt = types.find(w => w.id === t.work_type_id)
        if (wt) {
          if (!templates[wt.code]) templates[wt.code] = []
          templates[wt.code].push({
            name: t.name,
            invNo: t.inv_no,
            unit: t.unit,
            qty: String(t.qty),
            note: t.note,
          })
        }
      }
      setTmcTemplatesDb(templates)
    }
  }, [])

  // Загрузка нарядов из Supabase (лимит 500 — для списка и фильтров)
  const fetchOrders = useCallback(async () => {
    setLoading(true)
    const { data, error } = await supabase
      .from("work_orders")
      .select("id,unit_type,unit,depot,section,equipment,work_type,repair_kind,status,priority,tech,chief,description,note,created,closed,repair_items,date_start,date_end,created_at")
      .order("created_at", { ascending: false })
      .limit(500)
    if (!error && data) {
      setOrders(data.map(fromRow))
    } else {
      setOrders([])
    }
    setLoading(false)
  }, [])

  useEffect(() => { 
    fetchOrders()
    fetchEmployees()
    fetchWorkTypes()
    fetchFixedAssets()
  }, [fetchOrders, fetchEmployees, fetchWorkTypes, fetchFixedAssets])

  // Real-time подписки для синхронизации всех справочников
  useEffect(() => {
    const channel = supabase
      .channel("work_orders_sync")
      .on("postgres_changes", { event: "*", schema: "public", table: "fixed_assets" }, () => {
        fetchFixedAssets()
      })
      .on("postgres_changes", { event: "*", schema: "public", table: "employees" }, () => {
        fetchEmployees()
      })
      .on("postgres_changes", { event: "*", schema: "public", table: "work_types" }, () => {
        fetchWorkTypes()
      })
      .on("postgres_changes", { event: "*", schema: "public", table: "sections" }, () => {
        refreshSections()
      })
      .on("postgres_changes", { event: "*", schema: "public", table: "work_orders" }, () => {
        fetchOrders()
      })
      .subscribe()
    return () => { supabase.removeChannel(channel) }
  }, [fetchFixedAssets, fetchEmployees, fetchWorkTypes, refreshSections, fetchOrders])

  // Обработка URL-параметров из Ганта (create=1&unit=X&section=Y)
  useEffect(() => {
    if (searchParams.get("create") === "1") {
      setFormDefUnit(searchParams.get("unit") || "")
      setFormDefSection(searchParams.get("section") || "")
      setShowForm(true)
      router.replace("/dashboard/work-orders")
    }
  }, [searchParams, router])

  const sections  = [...new Set([...sectionsFromDb, ...orders.map(o => o.section)])].filter(Boolean).sort()
  const equipment = [...new Set(orders.map(o => o.equipment))].filter(Boolean).sort()

  const activeFilters = [fSection, fEquip, fUnitType].filter(Boolean).length
  const clearFilters  = () => { setFSection(""); setFEquip(""); setFUnitType("") }

  // Мастер видит только наряды своего участка
  const baseOrders = isMaster && profile?.section
    ? orders.filter(o => o.section === profile.section)
    : orders

  const counts = {
    total:       baseOrders.length,
    open:        baseOrders.filter(w => w.status === "pending" || w.status === "in_progress").length,
    pending:     baseOrders.filter(w => w.status === "pending").length,
    in_progress: baseOrders.filter(w => w.status === "in_progress").length,
    completed:   baseOrders.filter(w => w.status === "completed").length,
  }

  const filtered = baseOrders.filter(w => {
    const q = search.toLowerCase()
    const matchSearch = !q ||
      w.id.toLowerCase().includes(q) ||
      w.unit.toLowerCase().includes(q) ||
      w.desc.toLowerCase().includes(q) ||
      w.section.toLowerCase().includes(q) ||
      w.equipment.toLowerCase().includes(q)
    const matchTab =
      tabStatus === "open"        ? (w.status === "pending" || w.status === "in_progress") :
      tabStatus === "pending"     ? w.status === "pending" :
      tabStatus === "in_progress" ? w.status === "in_progress" :
      tabStatus === "completed"   ? w.status === "completed" : true
    return matchSearch && matchTab &&
      (!fSection  || w.section   === fSection) &&
      (!fEquip    || w.equipment === fEquip) &&
      (!fUnitType || w.unitType  === fUnitType)
  })

  const handleUpdateOrder = async (updated: WorkOrder) => {
    const { error } = await supabase
      .from("work_orders")
      .upsert(toRow(updated))
    if (!error) {
      setOrders(prev => prev.map(o => o.id === updated.id ? updated : o))
    }
  }

  const handleAddOrder = async (wo: WorkOrder) => {
    const { error } = await supabase
      .from("work_orders")
      .insert(toRow(wo))
    if (!error) {
      setOrders(prev => [wo, ...prev])
    }
  }

  const selCls = "appearance-none border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 pr-8 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"

  const tabs = [
    { key:"open",        label:"Открытые",      count: counts.open,        Icon: BookOpen,      activeCls:"border-blue-600 text-blue-600"   },
    { key:"pending",     label:"Запланировано", count: counts.pending,     Icon: Clock,         activeCls:"border-gray-600 text-gray-700 dark:text-gray-200"   },
    { key:"in_progress", label:"Выполняется",   count: counts.in_progress, Icon: Wrench,        activeCls:"border-amber-500 text-amber-600"  },
    { key:"completed",   label:"Выполнено",     count: counts.completed,   Icon: CheckCircle,   activeCls:"border-green-600 text-green-600"  },
  ]

  if (loading) return (
    <div className="flex items-center justify-center h-96 text-gray-400 text-sm gap-3">
      <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"/>
      Загрузка нарядов...
    </div>
  )

  return (
    <RoleCtx.Provider value={{ role: "operator", mySection: "" }}>
      <div className="p-8 space-y-6">
        {showForm && (
          <CreateWorkOrderModal
            onClose={()=>{ setShowForm(false); setFormDefUnit(""); setFormDefSection("") }}
            onSave={handleAddOrder}
            defaultUnit={formDefUnit}
            defaultSection={formDefSection}
            sections={sectionsFromDb}
            employees={employees}
            onRefreshData={() => { fetchEmployees(); refreshSections(); fetchWorkTypes(); fetchFixedAssets(); }}
            workTypesDb={workTypesDb}
            tmcTemplatesDb={tmcTemplatesDb}
            fixedAssets={fixedAssets}
            getSectionId={getSectionId}
          />
        )}
        {selectedOrder && (
          <ViewEditOrderModal
            order={selectedOrder}
            onClose={()=>setSelectedOrder(null)}
            onSave={(updated)=>{ handleUpdateOrder(updated); setSelectedOrder(null) }}
            isMasterView={isMaster}
            employees={employees}
          />
        )}

        {/* Заголовок */}
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Наряд-заказы</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Управление заданиями на техническое обслуживание</p>
          </div>
          {!isMaster && (
            <Button className="gap-2 bg-blue-600 hover:bg-blue-700" onClick={()=>setShowForm(true)}>
              <Plus className="w-4 h-4"/>Создать наряд
            </Button>
          )}
        </div>

        {/* Табы статусов */}
        <div className="flex border-b border-gray-200 dark:border-gray-800">
          {tabs.map(tab => (
            <button key={tab.key} onClick={() => setTabStatus(tab.key)}
              className={`flex items-center gap-2 px-5 py-3 text-sm font-semibold border-b-2 transition-all whitespace-nowrap ${
                tabStatus === tab.key
                  ? tab.activeCls + " bg-transparent"
                  : "border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              }`}>
              <tab.Icon className="w-4 h-4"/>
              {tab.label}
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                tabStatus === tab.key ? "bg-current/10" : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
              }`}>
                {tab.count}
              </span>
            </button>
          ))}
          <div className="flex-1"/>
          <div className="flex items-center px-4 text-xs text-gray-400">
            Всего: <span className="font-semibold text-gray-700 dark:text-gray-300 ml-1">{counts.total}</span>
          </div>
        </div>

        {/* Панель поиска + фильтры */}
        <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4 space-y-3">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"/>
              <Input placeholder="Поиск по №, единице, описанию..." className="pl-9"
                value={search} onChange={e=>setSearch(e.target.value)}/>
            </div>
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <SlidersHorizontal className="w-4 h-4"/>
              <span>Фильтры:</span>
            </div>

            {/* Участок */}
            <div className="relative">
              <select value={fSection} onChange={e=>setFSection(e.target.value)} className={selCls}>
                <option value="">Все участки</option>
                {sections.map(s=><option key={s} value={s}>{s}</option>)}
              </select>
              <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none"/>
              {fSection && <span className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-blue-600 rounded-full text-[9px] text-white flex items-center justify-center font-bold">✓</span>}
            </div>

            {/* Оборудование */}
            <div className="relative">
              <select value={fEquip} onChange={e=>setFEquip(e.target.value)} className={selCls}>
                <option value="">Всё оборудование</option>
                {equipment.map(e=><option key={e} value={e}>{e}</option>)}
              </select>
              <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none"/>
              {fEquip && <span className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-blue-600 rounded-full text-[9px] text-white flex items-center justify-center font-bold">✓</span>}
            </div>

            {/* Тип ТПС */}
            <div className="relative">
              <select value={fUnitType} onChange={e=>setFUnitType(e.target.value)} className={selCls}>
                <option value="">Все типы ТПС</option>
              <option value="locomotive">Локомотивы</option>
              <option value="wagon">Вагоны</option>
              </select>
              <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none"/>
              {fUnitType && <span className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-blue-600 rounded-full text-[9px] text-white flex items-center justify-center font-bold">✓</span>}
            </div>

            {activeFilters > 0 && (
              <button onClick={clearFilters}
                className="flex items-center gap-1 text-xs text-red-500 hover:text-red-700 font-medium px-2.5 py-1.5 rounded-lg hover:bg-red-50 transition-colors border border-red-200 dark:border-red-800">
                <X className="w-3.5 h-3.5"/> Сбросить ({activeFilters})
              </button>
            )}

            <div className="ml-auto text-xs text-gray-400 self-center">
              Показано: <span className="font-semibold text-gray-700 dark:text-gray-300">{filtered.length}</span>
            </div>
          </div>
        </div>

        {/* Таблица */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
                {["Номер НЗ","Участок","Оборудование","Единица","Описание работ","Вид ремонта","Приоритет","Исполнитель","Создан","Статус"].map(h=>(
                  <th key={h} className="text-left px-4 py-3.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {filtered.length===0 && (
                <tr><td colSpan={10} className="px-5 py-12 text-center text-sm text-gray-400">
                  <Filter className="w-8 h-8 mx-auto mb-2 opacity-30"/>
                  {isMaster && !profile?.section
                    ? "Выберите ваш участок, чтобы увидеть наряды"
                    : tabStatus === "completed" ? "Выполненных нарядов нет"
                    : tabStatus === "in_progress" ? "Нарядов в работе нет"
                    : tabStatus === "pending" ? "Запланированных нарядов нет"
                    : "Ничего не найдено — попробуйте изменить фильтры"}
                </td></tr>
              )}
              {filtered.map(wo => {
                const st = statusConfig[wo.status] ?? statusConfig.pending
                const pr = priorityConfig[wo.priority] ?? priorityConfig.normal
                const isLocked = wo.status === "completed"
                return (
                  <tr key={wo.id}
                    onClick={() => setSelectedOrder(wo)}
                    className={`transition-colors cursor-pointer ${
                      isLocked
                        ? "bg-gray-50/50 dark:bg-gray-800/20 hover:bg-gray-100/60 dark:hover:bg-gray-800/40"
                        : "hover:bg-blue-50/40 dark:hover:bg-blue-950/20"
                    }`}>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-1.5">
                        {isLocked && <Lock title="Закрыт" className="w-3 h-3 text-gray-400"/>}
                        <span className="text-xs font-mono text-gray-500 whitespace-nowrap">{wo.id}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-md bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 whitespace-nowrap">
                        {wo.section}
                      </span>
                    </td>
                    <td className="px-4 py-3.5">
                      <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-md whitespace-nowrap ${
                        wo.unitType === "wagon"
                          ? "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300"
                          : "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                      }`}>
                        {wo.equipment}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-sm font-medium text-blue-600 dark:text-blue-400 whitespace-nowrap">{wo.unit}</td>
                    <td className="px-4 py-3.5 text-sm text-gray-900 dark:text-white max-w-[180px]">
                      <span className="line-clamp-2">{wo.desc}</span>
                    </td>
                    <td className="px-4 py-3.5">
                      {wo.repairKind && (
                        <span className="text-xs font-bold px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 whitespace-nowrap">{wo.repairKind}</span>
                      )}
                    </td>
                    <td className="px-4 py-3.5">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap ${pr.class}`}>{pr.label}</span>
                    </td>
                    <td className="px-4 py-3.5 text-sm text-gray-600 dark:text-gray-300 whitespace-nowrap">{wo.tech}</td>
                    <td className="px-4 py-3.5 text-sm text-gray-600 dark:text-gray-300 whitespace-nowrap">{wo.created}</td>
                    <td className="px-4 py-3.5">
                      <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full whitespace-nowrap ${st.class}`}>
                        <st.icon className="w-3 h-3"/>{st.label}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </RoleCtx.Provider>
  )
}

export default function WorkOrdersPageWrapper() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center h-96 text-gray-400 text-sm gap-3">
        <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"/>
        Загрузка...
      </div>
    }>
      <WorkOrdersPage />
    </Suspense>
  )
}
