export function SkeletonCard() {
  return (
    <div className="rounded-xl border border-border bg-surface-1 overflow-hidden">
      <div className="h-40 bg-surface-2 animate-pulse" />
      <div className="p-4 space-y-3">
        <div className="h-4 bg-surface-2 animate-pulse rounded w-3/4" />
        <div className="h-3 bg-surface-2 animate-pulse rounded w-full" />
        <div className="h-3 bg-surface-2 animate-pulse rounded w-1/2" />
      </div>
      <div className="px-4 pb-4 flex items-center gap-2">
        <div className="h-6 bg-surface-2 animate-pulse rounded w-16" />
        <div className="h-6 bg-surface-2 animate-pulse rounded w-20" />
      </div>
    </div>
  );
}

export function SkeletonCardGrid({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {Array.from({ length: count }, (_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
