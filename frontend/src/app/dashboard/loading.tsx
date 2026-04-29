export default function DashboardLoading() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Header skeleton */}
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <div className="h-8 w-64 bg-surface-border rounded-lg" />
          <div className="h-4 w-48 bg-surface-border rounded" />
        </div>
        <div className="h-10 w-28 bg-surface-border rounded-lg" />
      </div>

      {/* Stats grid skeleton */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="glass-card p-5">
            <div className="h-10 w-10 bg-surface-border rounded-lg mb-3" />
            <div className="h-7 w-16 bg-surface-border rounded mb-1" />
            <div className="h-4 w-24 bg-surface-border rounded" />
          </div>
        ))}
      </div>

      {/* Content skeleton */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-card p-5">
          <div className="h-5 w-32 bg-surface-border rounded mb-4" />
          <div className="space-y-3">
            {[1,2,3,4,5].map(i => (
              <div key={i} className="h-12 bg-surface-border rounded" />
            ))}
          </div>
        </div>
        <div className="glass-card p-5">
          <div className="h-5 w-32 bg-surface-border rounded mb-4" />
          <div className="h-48 bg-surface-border rounded" />
        </div>
      </div>
    </div>
  );
}
