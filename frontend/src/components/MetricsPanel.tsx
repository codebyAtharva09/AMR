import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import { useFleetStore } from "../store/useFleetStore";
import { Panel } from "./Panel";

const GOOD = "#34d399";
const BAD = "#f87171";

export function MetricsPanel() {
  const snapshot = useFleetStore((s) => s.snapshot);
  const comparison = snapshot?.comparison;
  const agents = snapshot?.primary.agents ?? [];

  const dec = comparison?.decentralized;
  const saw = comparison?.stop_and_wait;

  const chartData = [
    { name: "Decentralized\nORCA", value: dec?.avg_completion_seconds ?? 0, fill: "#22d3ee" },
    { name: "Stop-and-\nWait", value: saw?.avg_completion_seconds ?? 0, fill: "#f59e0b" },
  ];

  // Time saved vs. the baseline (positive = decentralized is faster).
  let timeImprovement: number | null = null;
  if (dec?.avg_completion_seconds && saw?.avg_completion_seconds) {
    timeImprovement = ((saw.avg_completion_seconds - dec.avg_completion_seconds) / saw.avg_completion_seconds) * 100;
  }
  // Extra tasks completed vs. the baseline over the same window.
  let throughputGain: number | null = null;
  if (dec && saw && saw.throughput_tasks > 0) {
    throughputGain = ((dec.throughput_tasks - saw.throughput_tasks) / saw.throughput_tasks) * 100;
  }

  const working = agents.filter((a) => a.state !== "idle" && a.state !== "charging").length;
  const utilization = agents.length > 0 ? (working / agents.length) * 100 : null;
  const collisions = dec?.collisions ?? 0;

  return (
    <Panel title="Live Metrics">
      <div className="grid grid-cols-2 gap-2.5">
        <MetricCard
          label="Tasks Completed"
          value={(dec?.throughput_tasks ?? 0).toString()}
          delta={throughputGain !== null ? { text: `${Math.abs(throughputGain).toFixed(0)}%`, up: throughputGain >= 0, good: throughputGain >= 0 } : undefined}
          note="vs baseline"
        />
        <MetricCard
          label="Collisions"
          value={collisions.toString()}
          valueColor={collisions > 0 ? BAD : GOOD}
          note={collisions === 0 ? "Zero incidents" : "Incident logged"}
          noteColor={collisions === 0 ? GOOD : BAD}
        />
        <MetricCard
          label="Avg. Task Time"
          value={dec?.avg_completion_seconds != null ? `${dec.avg_completion_seconds.toFixed(0)} s` : "—"}
          delta={timeImprovement !== null ? { text: `${Math.abs(timeImprovement).toFixed(0)}%`, up: timeImprovement < 0, good: timeImprovement >= 0 } : undefined}
          note="vs baseline"
        />
        <MetricCard
          label="Fleet Utilization"
          value={utilization !== null ? `${utilization.toFixed(0)}%` : "—"}
          note={`${working} of ${agents.length} working`}
        />
      </div>

      <div className="mb-1 mt-4 text-[11px] font-medium text-[var(--text-dim)]">Avg. task time (s) · ORCA vs Stop-and-Wait</div>
      <div style={{ width: "100%", height: 120 }}>
        <ResponsiveContainer>
          <BarChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e2942" vertical={false} />
            <XAxis dataKey="name" tick={{ fill: "#8291ab", fontSize: 10 }} axisLine={{ stroke: "#1e2942" }} tickLine={false} />
            <YAxis tick={{ fill: "#8291ab", fontSize: 10 }} axisLine={{ stroke: "#1e2942" }} tickLine={false} />
            <Tooltip
              contentStyle={{ background: "#0d1220", border: "1px solid #1e2942", borderRadius: 8, fontSize: 12 }}
              formatter={(v) => [`${Number(v).toFixed(1)}s`, "avg completion"]}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {chartData.map((d, i) => (
                <Cell key={i} fill={d.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-2 flex justify-between text-[11px] text-[var(--text-dim)]">
        <span>Decentralized: <span className="font-semibold text-[var(--text-primary)]">{dec?.throughput_tasks ?? 0}</span> tasks</span>
        <span>Baseline: <span className="font-semibold text-[var(--text-primary)]">{saw?.throughput_tasks ?? 0}</span></span>
      </div>
    </Panel>
  );
}

function MetricCard({
  label,
  value,
  valueColor,
  delta,
  note,
  noteColor,
}: {
  label: string;
  value: string;
  valueColor?: string;
  delta?: { text: string; up: boolean; good: boolean };
  note?: string;
  noteColor?: string;
}) {
  return (
    <div className="rounded-xl border border-[var(--border-soft)] bg-white/[0.02] px-3.5 py-3">
      <div className="text-[11px] text-[var(--text-dim)]">{label}</div>
      <div className="mono mt-0.5 text-[26px] font-bold leading-tight" style={{ color: valueColor ?? "var(--text-primary)" }}>
        {value}
      </div>
      <div className="mt-0.5 flex items-center gap-1.5 text-[11px]">
        {delta && (
          <span className="mono font-semibold" style={{ color: delta.good ? GOOD : BAD }}>
            {delta.up ? "↑" : "↓"} {delta.text}
          </span>
        )}
        {note && (
          <span style={{ color: noteColor ?? "var(--text-dim)" }} className={noteColor ? "font-medium" : ""}>
            {note}
          </span>
        )}
      </div>
    </div>
  );
}
