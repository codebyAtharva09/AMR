export function GlassPanel({ title, children, className = "" }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-2xl shadow-black/40 ${className}`}>
      {title && <div className="border-b border-white/10 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-white/60">{title}</div>}
      <div className="p-4">{children}</div>
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="mb-3.5">
      <div className="mb-1.5 flex items-baseline justify-between text-[11px] text-white/50">
        <span>{label}</span>
        {hint && <span className="mono text-white/70">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

export function SegButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition ${
        active ? "bg-cyan-500 text-slate-900 shadow shadow-cyan-500/30" : "bg-white/5 text-white/60 hover:bg-white/10 hover:text-white"
      }`}
    >
      {children}
    </button>
  );
}
