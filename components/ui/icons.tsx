"use client"

import type { SVGProps } from "react"

export type IconProps = Omit<SVGProps<SVGSVGElement>, "color" | "ref"> & {
  color?: string
  size?: number | string
  title?: string
}

const iconNames = {
  Activity: "activity",
  AlertCircle: "exclamation-circle",
  AlertTriangle: "exclamation-triangle",
  ArrowLeft: "arrow-left",
  ArrowRight: "arrow-right",
  ArrowUpRight: "arrow-up-right",
  BarChart3: "bar-chart-line",
  Bell: "bell",
  BookOpen: "book",
  Brain: "cpu",
  Briefcase: "briefcase",
  Building2: "building",
  Calendar: "calendar",
  CalendarDays: "calendar3",
  CheckCircle: "check-circle",
  CheckIcon: "check-lg",
  ChevronDown: "chevron-down",
  ChevronDownIcon: "chevron-down",
  ChevronLeft: "chevron-left",
  ChevronLeftIcon: "chevron-left",
  ChevronRight: "chevron-right",
  ChevronRightIcon: "chevron-right",
  ChevronUp: "chevron-up",
  ChevronUpIcon: "chevron-up",
  CircleIcon: "circle",
  ClipboardList: "clipboard",
  Clock: "clock",
  Container: "box-seam",
  Cpu: "cpu",
  DollarSign: "currency-dollar",
  Download: "download",
  Eye: "eye",
  EyeOff: "eye-slash",
  FileText: "file-earmark-text",
  Filter: "funnel",
  FolderOpen: "folder2-open",
  Gauge: "speedometer2",
  GripVerticalIcon: "grip-vertical",
  HardHat: "cone-striped",
  Hash: "hash",
  HeartPulse: "heart-pulse",
  Info: "info-circle",
  Landmark: "bank",
  LayoutDashboard: "grid-1x2",
  LineChartIcon: "graph-up",
  List: "list",
  ListTodo: "list-task",
  Loader2: "arrow-repeat",
  Loader2Icon: "arrow-repeat",
  Lock: "lock",
  LogOut: "box-arrow-right",
  MapPin: "geo-alt",
  MinusIcon: "dash",
  MoreHorizontal: "three-dots",
  MoreHorizontalIcon: "three-dots",
  Package: "box",
  PackagePlus: "box-seam",
  PanelLeftIcon: "layout-sidebar",
  Palette: "palette",
  Pencil: "pencil",
  PieChart: "pie-chart",
  PieChartIcon: "pie-chart",
  Plus: "plus",
  Printer: "printer",
  Radio: "broadcast",
  RefreshCw: "arrow-clockwise",
  RotateCcw: "arrow-counterclockwise",
  Save: "floppy",
  Search: "search",
  SearchIcon: "search",
  Settings: "gear",
  Shield: "shield",
  ShieldCheck: "shield-check",
  SlidersHorizontal: "sliders",
  Target: "bullseye",
  Train: "train-front",
  Trash2: "trash",
  TrendingDown: "graph-down-arrow",
  TrendingUp: "graph-up-arrow",
  Users: "people",
  Wifi: "wifi",
  WifiOff: "wifi-off",
  Wrench: "wrench",
  X: "x",
  XCircle: "x-circle",
  XIcon: "x",
  Zap: "lightning-charge",
} as const

function createIcon(name: string) {
  function Icon({
    className,
    color,
    size,
    style,
    role,
    title,
    id,
    tabIndex,
    "aria-label": ariaLabel,
    "aria-hidden": ariaHidden,
  }: IconProps) {
    return (
      <i
        aria-hidden={ariaLabel ? undefined : ariaHidden ?? true}
        aria-label={ariaLabel}
        id={id}
        role={role}
        tabIndex={tabIndex}
        title={title}
        className={["bi", `bi-${name}`, className].filter(Boolean).join(" ")}
        style={{
          ...style,
          ...(size !== undefined ? { fontSize: typeof size === "number" ? `${size}px` : size } : {}),
          ...(color ? { color } : {}),
        }}
      />
    )
  }
  Icon.displayName = `BootstrapIcon(${name})`
  return Icon
}

export const Activity = createIcon(iconNames.Activity)
export const AlertCircle = createIcon(iconNames.AlertCircle)
export const AlertTriangle = createIcon(iconNames.AlertTriangle)
export const ArrowLeft = createIcon(iconNames.ArrowLeft)
export const ArrowRight = createIcon(iconNames.ArrowRight)
export const ArrowUpRight = createIcon(iconNames.ArrowUpRight)
export const BarChart3 = createIcon(iconNames.BarChart3)
export const Bell = createIcon(iconNames.Bell)
export const BookOpen = createIcon(iconNames.BookOpen)
export const Brain = createIcon(iconNames.Brain)
export const Briefcase = createIcon(iconNames.Briefcase)
export const Building2 = createIcon(iconNames.Building2)
export const Calendar = createIcon(iconNames.Calendar)
export const CalendarDays = createIcon(iconNames.CalendarDays)
export const CheckCircle = createIcon(iconNames.CheckCircle)
export const CheckIcon = createIcon(iconNames.CheckIcon)
export const ChevronDown = createIcon(iconNames.ChevronDown)
export const ChevronDownIcon = createIcon(iconNames.ChevronDownIcon)
export const ChevronLeft = createIcon(iconNames.ChevronLeft)
export const ChevronLeftIcon = createIcon(iconNames.ChevronLeftIcon)
export const ChevronRight = createIcon(iconNames.ChevronRight)
export const ChevronRightIcon = createIcon(iconNames.ChevronRightIcon)
export const ChevronUp = createIcon(iconNames.ChevronUp)
export const ChevronUpIcon = createIcon(iconNames.ChevronUpIcon)
export const CircleIcon = createIcon(iconNames.CircleIcon)
export const ClipboardList = createIcon(iconNames.ClipboardList)
export const Clock = createIcon(iconNames.Clock)
export const Container = createIcon(iconNames.Container)
export const Cpu = createIcon(iconNames.Cpu)
export const DollarSign = createIcon(iconNames.DollarSign)
export const Download = createIcon(iconNames.Download)
export const Eye = createIcon(iconNames.Eye)
export const EyeOff = createIcon(iconNames.EyeOff)
export const FileText = createIcon(iconNames.FileText)
export const Filter = createIcon(iconNames.Filter)
export const FolderOpen = createIcon(iconNames.FolderOpen)
export const Gauge = createIcon(iconNames.Gauge)
export const GripVerticalIcon = createIcon(iconNames.GripVerticalIcon)
export const HardHat = createIcon(iconNames.HardHat)
export const Hash = createIcon(iconNames.Hash)
export const HeartPulse = createIcon(iconNames.HeartPulse)
export const Info = createIcon(iconNames.Info)
export const Landmark = createIcon(iconNames.Landmark)
export const LayoutDashboard = createIcon(iconNames.LayoutDashboard)
export const LineChartIcon = createIcon(iconNames.LineChartIcon)
export const List = createIcon(iconNames.List)
export const ListTodo = createIcon(iconNames.ListTodo)
export const Loader2 = createIcon(iconNames.Loader2)
export const Loader2Icon = createIcon(iconNames.Loader2Icon)
export const Lock = createIcon(iconNames.Lock)
export const LogOut = createIcon(iconNames.LogOut)
export const MapPin = createIcon(iconNames.MapPin)
export const MinusIcon = createIcon(iconNames.MinusIcon)
export const MoreHorizontal = createIcon(iconNames.MoreHorizontal)
export const MoreHorizontalIcon = createIcon(iconNames.MoreHorizontalIcon)
export const Package = createIcon(iconNames.Package)
export const PackagePlus = createIcon(iconNames.PackagePlus)
export const PanelLeftIcon = createIcon(iconNames.PanelLeftIcon)
export const Palette = createIcon(iconNames.Palette)
export const Pencil = createIcon(iconNames.Pencil)
export const PieChart = createIcon(iconNames.PieChart)
export const PieChartIcon = createIcon(iconNames.PieChartIcon)
export const Plus = createIcon(iconNames.Plus)
export const Printer = createIcon(iconNames.Printer)
export const Radio = createIcon(iconNames.Radio)
export const RefreshCw = createIcon(iconNames.RefreshCw)
export const RotateCcw = createIcon(iconNames.RotateCcw)
export const Save = createIcon(iconNames.Save)
export const Search = createIcon(iconNames.Search)
export const SearchIcon = createIcon(iconNames.SearchIcon)
export const Settings = createIcon(iconNames.Settings)
export const Shield = createIcon(iconNames.Shield)
export const ShieldCheck = createIcon(iconNames.ShieldCheck)
export const SlidersHorizontal = createIcon(iconNames.SlidersHorizontal)
export const Target = createIcon(iconNames.Target)
export const Train = createIcon(iconNames.Train)
export const Trash2 = createIcon(iconNames.Trash2)
export const TrendingDown = createIcon(iconNames.TrendingDown)
export const TrendingUp = createIcon(iconNames.TrendingUp)
export const Users = createIcon(iconNames.Users)
export const Wifi = createIcon(iconNames.Wifi)
export const WifiOff = createIcon(iconNames.WifiOff)
export const Wrench = createIcon(iconNames.Wrench)
export const X = createIcon(iconNames.X)
export const XCircle = createIcon(iconNames.XCircle)
export const XIcon = createIcon(iconNames.XIcon)
export const Zap = createIcon(iconNames.Zap)
