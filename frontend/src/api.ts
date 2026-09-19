export const API_BASE = "http://127.0.0.1:8000";
export const WS_URL = "ws://127.0.0.1:8000/ws";

async function post(path: string, body?: object) {
  await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
}

export const api = {
  blockAisle: (row: number, col: number) => post("/api/block_aisle", { row, col }),
  unblockAisle: (row: number, col: number) => post("/api/unblock_aisle", { row, col }),
  unblockAll: () => post("/api/unblock_all"),
  addAgent: () => post("/api/add_agent"),
  removeAgent: () => post("/api/remove_agent"),
  reset: () => post("/api/reset"),
  setMode: (mode: "decentralized" | "stop_and_wait") => post("/api/set_mode", { mode }),
  getLayout: () => fetch(`${API_BASE}/api/layout`).then((r) => r.json()),
};
