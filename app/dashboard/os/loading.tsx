import { Loader2, Train, Container } from "lucide-react"

export default function FixedAssetsLoading() {
  return (
    <div className="p-6 space-y-6 bg-gray-50 dark:bg-gray-950 min-h-screen">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-8 w-56 bg-gray-200 dark:bg-gray-800 rounded-lg animate-pulse" />
          <div className="h-4 w-72 bg-gray-200 dark:bg-gray-800 rounded animate-pulse" />
        </div>
        <div className="h-10 w-44 bg-blue-200 dark:bg-blue-900 rounded-lg animate-pulse" />
      </div>

      {/* Stats cards skeleton */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { icon: Train, color: "blue" },
          { icon: Train, color: "orange" },
          { icon: Container, color: "purple" },
          { icon: Container, color: "green" },
        ].map((item, i) => (
          <div key={i} className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 animate-pulse">
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg bg-${item.color}-100 dark:bg-${item.color}-900/30`}>
                <item.icon className={`w-5 h-5 text-${item.color}-600 dark:text-${item.color}-400`} />
              </div>
              <div className="space-y-1">
                <div className="h-6 w-12 bg-gray-200 dark:bg-gray-700 rounded" />
                <div className="h-3 w-20 bg-gray-200 dark:bg-gray-700 rounded" />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="h-10 flex-1 max-w-xs bg-gray-200 dark:bg-gray-800 rounded-lg animate-pulse" />
        {[1, 2, 3].map(i => (
          <div key={i} className="h-10 w-32 bg-gray-200 dark:bg-gray-800 rounded-lg animate-pulse" />
        ))}
      </div>

      {/* Table skeleton */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        <div className="bg-gray-50 dark:bg-gray-800 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <div className="flex gap-4">
            {[60, 150, 100, 80, 100, 80].map((w, i) => (
              <div key={i} className="h-4 bg-gray-300 dark:bg-gray-600 rounded animate-pulse" style={{ width: w }} />
            ))}
          </div>
        </div>
        
        {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(i => (
          <div key={i} className="px-4 py-4 border-b border-gray-100 dark:border-gray-800">
            <div className="flex gap-4 items-center">
              <div className="h-6 w-20 bg-blue-100 dark:bg-blue-900/30 rounded-md animate-pulse" />
              <div className="h-4 w-40 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
              <div className="h-4 w-24 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
              <div className="h-4 w-20 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
              <div className="h-6 w-24 bg-green-100 dark:bg-green-900/30 rounded-full animate-pulse" />
              <div className="h-4 w-20 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
            </div>
          </div>
        ))}
      </div>

      {/* Loading indicator */}
      <div className="flex items-center justify-center gap-2 text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin" />
        <span>Загрузка основных средств...</span>
      </div>
    </div>
  )
}
