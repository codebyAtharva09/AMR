export function Panel({
  title,
  right,
  children,
  className = "",
}: {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-panel)] shadow-lg shadow-black/20 ${className}`}>
      <div className="flex items-center justify-between px-4 pt-3.5 pb-1">
        <div className="text-[15px] font-semibold tracking-tight text-[var(--text-primary)]">{title}</div>
        {right}
      </div>
      <div className="px-4 pb-4 pt-2">{children}</div>
    </div>
  );
}
