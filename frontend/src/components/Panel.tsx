export function Panel({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-[var(--border-soft)] bg-[var(--bg-panel)] shadow-lg shadow-black/20 ${className}`}>
      <div className="border-b border-[var(--border-soft)] px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-dim)]">
        {title}
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}
