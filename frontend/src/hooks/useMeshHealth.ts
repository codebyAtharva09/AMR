import { useEffect, useState } from "react";
import { useFleetStore } from "../store/useFleetStore";

const DEGRADED_AFTER_MS = 1200;

export type MeshHealth = "online" | "degraded" | "offline";

/** Derives fleet-mesh health purely from the existing WebSocket state already
 * in the store - no backend changes. "Degraded" means the socket says it's
 * connected but no snapshot has arrived recently (a stalled/lagging stream);
 * "offline" means the socket itself is closed. */
export function useMeshHealth(): MeshHealth {
  const connected = useFleetStore((s) => s.connected);
  const lastMessageAt = useFleetStore((s) => s.lastMessageAt);
  const [, forceTick] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => forceTick((n) => n + 1), 500);
    return () => window.clearInterval(id);
  }, []);

  if (!connected) return "offline";
  if (lastMessageAt !== null && Date.now() - lastMessageAt > DEGRADED_AFTER_MS) return "degraded";
  return "online";
}
