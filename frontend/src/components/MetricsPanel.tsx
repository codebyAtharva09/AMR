import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import { useFleetStore } from "../store/useFleetStore";
import { Panel } from "./Panel";

export function MetricsPanel() {
  const snapshot = useFleetStore((s) => s.snapshot);
  const comparison = snapshot?.comparison;

  const dec = comparison?.decentralized;
  const saw = comparison?.stop_and_wait;

  const chartData = [
    { name: "Decentralized\nORCA", value: dec?.avg_completion_seconds ?? 0, fill: "#22d3ee" },
    { name: "Stop-and-\nWait", value: saw?.avg_completion_seconds ?? 0, fill: "#f59e0b" },
  ];

  let improvement: number | null = null;
  if (dec?.avg_completion_seconds && saw?.avg_completion_seconds) {
    improvement = ((saw.avg_completion_seconds - dec.avg_completion_seconds) / saw.avg_completion_seconds) * 100;
  }

  return (
    <Panel title="Live Performance Metrics">
      <div className="mb-3 grid grid-cols-2 gap-2">
        <StatTile label="Collisions" value={(dec?.collisions ?? 0).toString()} accent={dec && dec.collisions > 0 ? "#f87171" : "#34d399"} />
        <StatTile
          label="Speed advantage"
          value={improvement !== null ? `${improvement >= 0 ? "+" : ""}${improvement.toFixed(0)}%` : "—"}
          accent={improvement !== null && improvement >= 0 ? "#34d399" : "#f87171"}
        />
      </div>

      <div className="mb-1 text-[10px] uppercase text-[var(--text-dim)]">Avg. task completion time (s)</div>
      <div style={{ width: "100%", height: 130 }}>
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

      <div className="mt-3 flex justify-between text-[11px] text-[var(--text-dim)]">
        <span>Throughput (decentralized): <span className="text-[var(--text-primary)] font-semibold">{dec?.throughput_tasks ?? 0}</span> tasks</span>
        <span>(baseline): <span className="text-[var(--text-primary)] font-semibold">{saw?.throughput_tasks ?? 0}</span></span>
      </div>
    </Panel>
  );
}

function StatTile({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="rounded-lg border border-[var(--border-soft)] bg-[#0a0f1c] px-3 py-2">
      <div className="text-[10px] uppercase text-[var(--text-dim)]">{label}</div>
      <div className="mono text-xl font-bold" style={{ color: accent }}>
        {value}
      </div>
    </div>
  );
}
