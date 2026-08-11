import { Loader2, BarChart3, Brain, Bell } from "lucide-react"

export default function AnalyticsLoading() {
  return (
    <div className="p-8 space-y-6 bg-gray-50 dark:bg-gray-950 min-h-screen">
      {/* Header - показывается сразу */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Экономическая эффективность
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Загрузка аналитики...
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Loader2 className="w-4 h-4 animate-spin" />
          Загрузка данных
        </div>
      </div>

      {/* KPI Cards skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6 gap-4">
        {[1, 2, 3, 4, 5, 6].map(i => (
          <div key={i} className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5 animate-pulse">
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

      {/* AI Section skeleton */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Health */}
        <div className="bg-gradient-to-br from-blue-600 to-indigo-700 rounded-xl p-6 shadow-lg text-white animate-pulse">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 bg-white/20 rounded-lg" />
            <div className="space-y-1">
              <div className="h-4 w-24 bg-white/30 rounded" />
              <div className="h-3 w-32 bg-white/20 rounded" />
            </div>
          </div>
          <div className="h-12 bg-white/20 rounded mb-4" />
          <div className="h-3 bg-white/20 rounded-full" />
        </div>

        {/* AI Predictions */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 animate-pulse">
          <div className="flex items-center gap-2 mb-4">
            <div className="p-2 bg-purple-100 dark:bg-purple-900/50 rounded-lg">
              <Brain className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            </div>
            <div className="space-y-1">
              <div className="h-4 w-24 bg-gray-200 dark:bg-gray-700 rounded" />
              <div className="h-2 w-32 bg-gray-200 dark:bg-gray-700 rounded" />
            </div>
          </div>
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-16 bg-gray-200 dark:bg-gray-700 rounded-lg" />
            ))}
          </div>
        </div>

        {/* AI Notifications */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 animate-pulse">
          <div className="flex items-center gap-2 mb-4">
            <div className="p-2 bg-amber-100 dark:bg-amber-900/50 rounded-lg">
              <Bell className="w-4 h-4 text-amber-600 dark:text-amber-400" />
            </div>
            <div className="space-y-1">
              <div className="h-4 w-24 bg-gray-200 dark:bg-gray-700 rounded" />
              <div className="h-2 w-32 bg-gray-200 dark:bg-gray-700 rounded" />
            </div>
          </div>
          <div className="space-y-2">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="h-14 bg-gray-200 dark:bg-gray-700 rounded-lg" />
            ))}
          </div>
        </div>
      </div>

      {/* Charts skeleton */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {[1, 2].map(i => (
          <div key={i} className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 animate-pulse">
            <div className="flex items-center justify-between mb-6">
              <div className="space-y-2">
                <div className="h-4 w-32 bg-gray-200 dark:bg-gray-700 rounded" />
                <div className="h-3 w-24 bg-gray-200 dark:bg-gray-700 rounded" />
              </div>
              <BarChart3 className="w-5 h-5 text-gray-300 dark:text-gray-600" />
            </div>
            <div className="flex items-end gap-2 h-[250px]">
              {[40, 65, 45, 80, 55, 70, 50].map((h, j) => (
                <div key={j} className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-t transition-all" style={{ height: `${h}%` }} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
