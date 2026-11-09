"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api, type GtkCarriage, type GtkLocomotive, type WialonUnit } from "@/lib/api"
import { useDebouncedValue } from "@/lib/use-debounced-value"

type Source = "wialon" | "gtk"
type GtkKind = "locomotive" | "carriage"

type PickerItem = {
  id: string
  name: string
  description: string
  linkedAssetName: string | null
}

type SourceAssetPickerDialogProps = {
  source: Source
  open: boolean
  saving: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (selection: { externalId: string; externalName: string }) => void
}

const PAGE_SIZE = 50

function wialonPickerItem(unit: WialonUnit): PickerItem {
  return {
    id: unit.unit_id,
    name: unit.name || `Wialon ${unit.unit_id}`,
    description: `ID ${unit.unit_id}`,
    linkedAssetName: unit.linked_asset?.name ?? null,
  }
}

function gtkLocomotivePickerItem(item: GtkLocomotive): PickerItem {
  const details = [item.garage_number, item.inventory_number, item.model_name].filter(Boolean)
  return {
    id: String(item.gtk_id),
    name: item.name || `GTK ${item.gtk_id}`,
    description: [`ID ${item.gtk_id}`, ...details].join(" · "),
    linkedAssetName: item.linked_asset?.name ?? null,
  }
}

function gtkCarriagePickerItem(item: GtkCarriage): PickerItem {
  const details = [item.reg_number, item.inventory_number, item.model_name].filter(Boolean)
  return {
    id: String(item.gtk_id),
    name: item.name || `GTK ${item.gtk_id}`,
    description: [`ID ${item.gtk_id}`, ...details].join(" · "),
    linkedAssetName: item.linked_asset?.name ?? null,
  }
}

export function SourceAssetPickerDialog({
  source,
  open,
  saving,
  onOpenChange,
  onSelect,
}: SourceAssetPickerDialogProps) {
  const [gtkKind, setGtkKind] = useState<GtkKind>("locomotive")
  const [search, setSearch] = useState("")
  const debouncedSearch = useDebouncedValue(search, 300)
  const [page, setPage] = useState(0)
  const [items, setItems] = useState<PickerItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [retry, setRetry] = useState(0)
  const requestVersion = useRef(0)

  const loadItems = useCallback(async () => {
    const version = ++requestVersion.current
    setLoading(true)
    setError("")
    setItems([])
    try {
      const params = {
        q: debouncedSearch.trim() || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }

      if (source === "wialon") {
        const response = await api.wialon.listUnits({ ...params, sort_by: "name", sort_order: "asc" })
        if (version !== requestVersion.current) return
        setItems(response.items.map(wialonPickerItem))
        setTotal(response.total)
      } else if (gtkKind === "locomotive") {
        const response = await api.gtk.locomotives({ ...params, sort_by: "gtk_id", sort_order: "asc" })
        if (version !== requestVersion.current) return
        setItems(response.items.map(gtkLocomotivePickerItem))
        setTotal(response.total)
      } else {
        const response = await api.gtk.carriages({ ...params, sort_by: "gtk_id", sort_order: "asc" })
        if (version !== requestVersion.current) return
        setItems(response.items.map(gtkCarriagePickerItem))
        setTotal(response.total)
      }
    } catch (loadError) {
      if (version !== requestVersion.current) return
      setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить список объектов.")
      setTotal(0)
    } finally {
      if (version === requestVersion.current) setLoading(false)
    }
  }, [debouncedSearch, gtkKind, page, source])

  useEffect(() => {
    if (!open) return
    void loadItems()
    return () => {
      requestVersion.current += 1
    }
  }, [loadItems, open, retry])

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const firstItem = total === 0 ? 0 : page * PAGE_SIZE + 1
  const lastItem = Math.min((page + 1) * PAGE_SIZE, total)

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => {
      if (!saving) onOpenChange(nextOpen)
    }}>
      <DialogContent className="flex max-h-[85vh] max-w-3xl flex-col gap-4">
        <DialogHeader>
          <DialogTitle>Выбор объекта {source === "wialon" ? "Wialon" : "GTK"}</DialogTitle>
          <DialogDescription>
            Выберите объект, чтобы привязать его к этому основному средству.
          </DialogDescription>
        </DialogHeader>

        {source === "gtk" && (
          <label className="space-y-1 text-sm text-gray-600 dark:text-gray-300">
            Тип объекта
            <select
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              value={gtkKind}
              onChange={(event) => {
                setGtkKind(event.target.value as GtkKind)
                setPage(0)
              }}
            >
              <option value="locomotive">Локомотивы</option>
              <option value="carriage">Вагоны</option>
            </select>
          </label>
        )}

        <Input
          value={search}
          onChange={(event) => {
            setSearch(event.target.value)
            setPage(0)
          }}
          placeholder="Поиск по названию или ID"
          aria-label="Поиск по названию или ID"
        />

        <div className="min-h-40 flex-1 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700">
          {loading && <p className="p-4 text-sm text-gray-500">Загрузка списка...</p>}
          {!loading && error && (
            <div className="space-y-3 p-4">
              <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>
              <Button type="button" size="sm" variant="outline" onClick={() => setRetry((current) => current + 1)}>
                Повторить
              </Button>
            </div>
          )}
          {!loading && !error && items.length === 0 && (
            <p className="p-4 text-sm text-gray-500">Объекты не найдены.</p>
          )}
          {!loading && !error && items.map((item) => (
            <button
              key={item.id}
              type="button"
              disabled={saving || Boolean(item.linkedAssetName)}
              onClick={() => onSelect({ externalId: item.id, externalName: item.name })}
              className="flex w-full items-center justify-between gap-4 border-b border-gray-100 px-4 py-3 text-left last:border-b-0 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-800 dark:hover:bg-gray-800"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-gray-900 dark:text-white">{item.name}</span>
                <span className="block truncate text-xs text-gray-500">{item.description}</span>
              </span>
              <span className="shrink-0 text-xs text-gray-500">
                {item.linkedAssetName ? `Уже привязан: ${item.linkedAssetName}` : saving ? "Сохранение..." : "Выбрать"}
              </span>
            </button>
          ))}
        </div>

        <div className="flex items-center justify-between gap-3 text-sm text-gray-500">
          <span>{firstItem}–{lastItem} из {total}</span>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={loading || page === 0}
              onClick={() => setPage((current) => current - 1)}
            >
              Назад
            </Button>
            <span className="self-center">{page + 1} / {pageCount}</span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={loading || page + 1 >= pageCount}
              onClick={() => setPage((current) => current + 1)}
            >
              Далее
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
