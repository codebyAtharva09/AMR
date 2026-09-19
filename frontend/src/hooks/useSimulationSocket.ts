import { useEffect, useRef } from "react";
import { useFleetStore } from "../store/useFleetStore";
import { WS_URL } from "../api";
import type { FleetSnapshot } from "../types";

export function useSimulationSocket() {
  const setSnapshot = useFleetStore((s) => s.setSnapshot);
  const setConnected = useFleetStore((s) => s.setConnected);
  const retryRef = useRef<number | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let cancelled = false;

    const connect = () => {
      ws = new WebSocket(WS_URL);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!cancelled) {
          retryRef.current = window.setTimeout(connect, 1500);
        }
      };
      ws.onerror = () => ws?.close();
      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data) as FleetSnapshot;
          setSnapshot(data);
        } catch {
          // ignore malformed frame
        }
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (retryRef.current) window.clearTimeout(retryRef.current);
      ws?.close();
    };
  }, [setSnapshot, setConnected]);
}
