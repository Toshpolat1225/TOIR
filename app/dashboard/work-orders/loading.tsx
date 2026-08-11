import { Loader2 } from "lucide-react"

export default function WorkOrdersLoading() {
  return (
    <div className="p-6 space-y-6 bg-gray-50 dark:bg-gray-950 min-h-screen">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-8 w-48 bg-gray-200 dark:bg-gray-800 rounded-lg animate-pulse" />
          <div className="h-4 w-64 bg-gray-200 dark:bg-gray-800 rounded animate-pulse" />
        </div>
        <div className="flex gap-2">
          <div className="h-10 w-32 bg-gray-200 dark:bg-gray-800 rounded-lg animate-pulse" />
          <div className="h-10 w-40 bg-blue-200 dark:bg-blue-900 rounded-lg animate-pulse" />
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="h-10 w-32 bg-gray-200 dark:bg-gray-800 rounded-lg animate-pulse" />
        ))}
      </div>

      {/* Table skeleton */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        {/* Table header */}
        <div className="bg-gray-50 dark:bg-gray-800 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <div className="flex gap-4">
            {[80, 120, 100, 80, 100, 80, 60].map((w, i) => (
              <div key={i} className="h-4 bg-gray-300 dark:bg-gray-600 rounded animate-pulse" style={{ width: w }} />
            ))}
          </div>
        </div>
        
        {/* Table rows */}
        {[1, 2, 3, 4, 5, 6, 7, 8].map(i => (
          <div key={i} className="px-4 py-4 border-b border-gray-100 dark:border-gray-800">
            <div className="flex gap-4 items-center">
              {[80, 120, 100, 80, 100, 80, 60].map((w, j) => (
                <div key={j} className="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" style={{ width: w }} />
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Loading indicator */}
      <div className="flex items-center justify-center gap-2 text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin" />
        <span>Загрузка наряд-заданий...</span>
      </div>
    </div>
  )
}
