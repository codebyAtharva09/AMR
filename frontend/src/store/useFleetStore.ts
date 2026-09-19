import { create } from "zustand";
import type { FleetSnapshot, LayoutInfo } from "../types";

interface FleetStore {
  connected: boolean;
  snapshot: FleetSnapshot | null;
  layout: LayoutInfo | null;
  selectedAgentId: string | null;
  lastMessageAt: number | null;
  setConnected: (v: boolean) => void;
  setSnapshot: (s: FleetSnapshot) => void;
  setLayout: (l: LayoutInfo) => void;
  setSelectedAgentId: (id: string | null) => void;
}

export const useFleetStore = create<FleetStore>((set) => ({
  connected: false,
  snapshot: null,
  layout: null,
  selectedAgentId: null,
  lastMessageAt: null,
  setConnected: (v) => set({ connected: v }),
  setSnapshot: (s) => set({ snapshot: s, lastMessageAt: Date.now() }),
  setLayout: (l) => set({ layout: l }),
  setSelectedAgentId: (id) => set({ selectedAgentId: id }),
}));
