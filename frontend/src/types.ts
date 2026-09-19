export interface AgentState {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  battery: number;
  state: string;
  task_id: number | null;
  color: string;
}

export interface TaskState {
  id: number;
  status: string;
  pickup: [number, number];
  dropoff: [number, number];
}

export interface MetricsSnapshot {
  collisions: number;
  avg_completion_seconds: number | null;
  throughput_tasks: number;
}

export interface SimSnapshot {
  mode: string;
  tick: number;
  agents: AgentState[];
  tasks: TaskState[];
  blocked_edges: [number, number][][];
  metrics: MetricsSnapshot;
  events: string[];
}

export interface FleetSnapshot {
  primary: SimSnapshot;
  comparison: {
    decentralized: MetricsSnapshot;
    stop_and_wait: MetricsSnapshot;
  };
}

export interface LayoutInfo {
  rows: number;
  cols: number;
  cell_size: number;
  racks: { row: number; col: number }[];
  pickup_stations: [number, number][];
  dropoff_stations: [number, number][];
  charging_stations: [number, number][];
}
