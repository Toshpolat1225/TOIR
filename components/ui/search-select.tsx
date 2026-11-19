"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { ChevronDown, X } from "@/components/ui/icons";

export type SearchOption = {
  value: string;
  label: string;
  /** small grey text under/next to the label (also searchable) */
  hint?: string;
  /** extra words that should match but are not shown */
  search?: string;
  /** text shown in the closed field after choosing (defaults to the label) */
  display?: string;
};

const MAX_VISIBLE = 60;

const baseInput =
  "w-full rounded-md border border-gray-300 bg-white px-3 py-2 pr-8 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-700 dark:bg-gray-800 dark:text-white";

function norm(text: string): string {
  return text.toLocaleLowerCase("ru").replace(/ё/g, "е");
}

/** Every typed word must be found somewhere in the option — updates on every key press. */
export function filterOptions(options: SearchOption[], query: string): SearchOption[] {
  const words = norm(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return options;
  return options.filter((option) => {
    const haystack = norm(`${option.label} ${option.hint ?? ""} ${option.search ?? ""}`);
    return words.every((word) => haystack.includes(word));
  });
}

type ListProps = {
  options: SearchOption[];
  active: number;
  selected: Set<string>;
  listId: string;
  emptyText: string;
  total: number;
  onPick: (option: SearchOption) => void;
  onHover: (index: number) => void;
};

function OptionList({ options, active, selected, listId, emptyText, total, onPick, onHover }: ListProps) {
  const activeRef = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [active]);
  return (
    <ul
      id={listId}
      role="listbox"
      className="absolute left-0 right-0 z-30 mt-1 max-h-60 overflow-auto rounded-md border border-gray-200 bg-white py-1 text-sm shadow-lg dark:border-gray-700 dark:bg-gray-800"
    >
      {options.length === 0 && <li className="px-3 py-2 text-gray-500">{emptyText}</li>}
      {options.map((option, index) => {
        const isSelected = selected.has(option.value);
        return (
          <li
            key={option.value}
            ref={index === active ? activeRef : null}
            role="option"
            aria-selected={isSelected}
            onMouseDown={(event) => {
              event.preventDefault();
              onPick(option);
            }}
            onMouseEnter={() => onHover(index)}
            className={`cursor-pointer px-3 py-1.5 ${
              index === active ? "bg-blue-50 dark:bg-blue-950" : ""
            } ${isSelected ? "font-medium text-blue-700 dark:text-blue-300" : "text-gray-900 dark:text-gray-100"}`}
          >
            <span>{option.label}</span>
            {option.hint && <span className="ml-2 text-xs text-gray-500">{option.hint}</span>}
          </li>
        );
      })}
      {total > options.length && (
        <li className="px-3 py-1.5 text-xs text-gray-500">
          Показано {options.length} из {total} — уточните запрос
        </li>
      )}
    </ul>
  );
}

type SingleProps = {
  options: SearchOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  emptyText?: string;
  disabled?: boolean;
  clearable?: boolean;
  testId?: string;
  ariaLabel?: string;
};

/** Searchable select: type to filter on every key, ↑↓ to move, Enter to choose, Esc to close. */
export function SearchSelect({
  options,
  value,
  onChange,
  placeholder = "Начните вводить...",
  emptyText = "Ничего не найдено",
  disabled,
  clearable = true,
  testId,
  ariaLabel,
}: SingleProps) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const selected = options.find((option) => option.value === value);
  const filtered = useMemo(() => filterOptions(options, query), [options, query]);
  const visible = filtered.slice(0, MAX_VISIBLE);

  function pick(option: SearchOption) {
    onChange(option.value);
    setOpen(false);
    setQuery("");
  }

  return (
    <div className="relative mt-1">
      <input
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-label={ariaLabel}
        data-testid={testId}
        autoComplete="off"
        disabled={disabled}
        className={baseInput}
        placeholder={selected ? (selected.display ?? selected.label) : placeholder}
        value={open ? query : selected ? (selected.display ?? selected.label) : ""}
        onFocus={() => {
          setOpen(true);
          setQuery("");
          setActive(0);
        }}
        onBlur={() => {
          setOpen(false);
          setQuery("");
        }}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
          setActive(0);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            setActive((current) => Math.min(current + 1, visible.length - 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((current) => Math.max(current - 1, 0));
          } else if (event.key === "Enter") {
            if (open && visible[active]) {
              event.preventDefault();
              pick(visible[active]);
            }
          } else if (event.key === "Escape" && open) {
            event.stopPropagation();
            setOpen(false);
          }
        }}
      />
      {clearable && value && !disabled ? (
        <button
          type="button"
          aria-label="Очистить"
          tabIndex={-1}
          onMouseDown={(event) => {
            event.preventDefault();
            onChange("");
            setQuery("");
          }}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700"
        >
          <X className="h-4 w-4" />
        </button>
      ) : (
        <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
      )}
      {open && (
        <OptionList
          options={visible}
          active={active}
          selected={new Set(value ? [value] : [])}
          listId={listId}
          emptyText={emptyText}
          total={filtered.length}
          onPick={pick}
          onHover={setActive}
        />
      )}
    </div>
  );
}

type MultiProps = {
  options: SearchOption[];
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  emptyText?: string;
  disabled?: boolean;
  testId?: string;
  ariaLabel?: string;
};

/** Multi-select with chips; chosen options stay in the list (click again to remove). */
export function SearchMultiSelect({
  options,
  values,
  onChange,
  placeholder = "Начните вводить...",
  emptyText = "Ничего не найдено",
  disabled,
  testId,
  ariaLabel,
}: MultiProps) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const filtered = useMemo(() => filterOptions(options, query), [options, query]);
  const visible = filtered.slice(0, MAX_VISIBLE);
  const chosen = values
    .map((value) => options.find((option) => option.value === value))
    .filter((option): option is SearchOption => Boolean(option));

  function toggle(option: SearchOption) {
    onChange(
      values.includes(option.value)
        ? values.filter((value) => value !== option.value)
        : [...values, option.value]
    );
    setQuery("");
  }

  return (
    <div className="relative mt-1">
      <div
        className={`flex flex-wrap items-center gap-1 rounded-md border border-gray-300 bg-white px-2 py-1.5 focus-within:border-blue-500 focus-within:ring-1 focus-within:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 ${
          disabled ? "opacity-60" : ""
        }`}
      >
        {chosen.map((option) => (
          <span
            key={option.value}
            data-testid="chip"
            className="inline-flex items-center gap-1 rounded bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-950 dark:text-blue-200"
          >
            {option.label}
            {!disabled && (
              <button
                type="button"
                aria-label={`Убрать ${option.label}`}
                onMouseDown={(event) => {
                  event.preventDefault();
                  onChange(values.filter((value) => value !== option.value));
                }}
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </span>
        ))}
        <input
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-label={ariaLabel}
          data-testid={testId}
          autoComplete="off"
          disabled={disabled}
          className="min-w-[8rem] flex-1 bg-transparent px-1 py-0.5 text-sm text-gray-900 outline-none placeholder:text-gray-400 dark:text-white"
          placeholder={chosen.length === 0 ? placeholder : "Добавить ещё..."}
          value={query}
          onFocus={() => {
            setOpen(true);
            setActive(0);
          }}
          onBlur={() => {
            setOpen(false);
            setQuery("");
          }}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
            setActive(0);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setOpen(true);
              setActive((current) => Math.min(current + 1, visible.length - 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((current) => Math.max(current - 1, 0));
            } else if (event.key === "Enter") {
              if (open && visible[active]) {
                event.preventDefault();
                toggle(visible[active]);
              }
            } else if (event.key === "Backspace" && !query && values.length > 0) {
              onChange(values.slice(0, -1));
            } else if (event.key === "Escape" && open) {
              event.stopPropagation();
              setOpen(false);
            }
          }}
        />
      </div>
      {open && (
        <OptionList
          options={visible}
          active={active}
          selected={new Set(values)}
          listId={listId}
          emptyText={emptyText}
          total={filtered.length}
          onPick={toggle}
          onHover={setActive}
        />
      )}
    </div>
  );
}
