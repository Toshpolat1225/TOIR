import { Loader2 } from "lucide-react"

export default function DashboardLoading() {
  return (
    <div className="p-8 space-y-6 bg-gray-50 dark:bg-gray-950 min-h-screen animate-pulse">
      {/* Header skeleton */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-8 w-48 bg-gray-200 dark:bg-gray-800 rounded-lg" />
          <div className="h-4 w-64 bg-gray-200 dark:bg-gray-800 rounded" />
        </div>
        <div className="h-10 w-32 bg-gray-200 dark:bg-gray-800 rounded-lg" />
      </div>

      {/* KPI Cards skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
            <div className="flex items-start justify-between">
              <div className="space-y-3 flex-1">
                <div className="h-3 w-20 bg-gray-200 dark:bg-gray-700 rounded" />
                <div className="h-7 w-24 bg-gray-200 dark:bg-gray-700 rounded" />
                <div className="h-2 w-16 bg-gray-200 dark:bg-gray-700 rounded" />
              </div>
              <div className="w-11 h-11 bg-gray-200 dark:bg-gray-700 rounded-xl" />
            </div>
          </div>
        ))}
      </div>

      {/* Charts skeleton */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {[1, 2].map(i => (
          <div key={i} className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
            <div className="space-y-4">
              <div className="h-5 w-32 bg-gray-200 dark:bg-gray-700 rounded" />
              <div className="flex items-end gap-2 h-[200px]">
                {[40, 65, 45, 80, 55, 70, 50, 60].map((h, j) => (
                  <div key={j} className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-t" style={{ height: `${h}%` }} />
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Loading indicator */}
      <div className="fixed bottom-4 right-4 flex items-center gap-2 bg-white dark:bg-gray-900 px-4 py-2 rounded-full shadow-lg border border-gray-200 dark:border-gray-800">
        <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
        <span className="text-sm text-gray-600 dark:text-gray-400">Загрузка...</span>
      </div>
    </div>
  )
}
