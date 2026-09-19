import { useEffect, useState } from "react";
import { TopBar } from "./components/TopBar";
import { WarehouseScene } from "./components/WarehouseScene";
import { ControlPanel } from "./components/ControlPanel";
import { FleetRoster } from "./components/FleetRoster";
import { MetricsPanel } from "./components/MetricsPanel";
import { EventFeed } from "./components/EventFeed";
import { useSimulationSocket } from "./hooks/useSimulationSocket";
import { useFleetStore } from "./store/useFleetStore";
import { api } from "./api";
import { RackConfiguratorApp } from "./rack-configurator/RackConfiguratorApp";

function App() {
  useSimulationSocket();
  const setLayout = useFleetStore((s) => s.setLayout);
  const [showRackStudio, setShowRackStudio] = useState(false);

  useEffect(() => {
    api.getLayout().then(setLayout).catch(() => {});
  }, [setLayout]);

  if (showRackStudio) {
    return <RackConfiguratorApp onClose={() => setShowRackStudio(false)} />;
  }

  return (
    <div className="flex h-screen w-screen flex-col">
      <TopBar onOpenRackStudio={() => setShowRackStudio(true)} />
      <div className="flex flex-1 overflow-hidden">
        <div className="relative flex-1">
          <WarehouseScene />
        </div>
        <div className="flex w-[380px] flex-shrink-0 flex-col gap-3 overflow-y-auto border-l border-[var(--border-soft)] bg-[var(--bg-void)] p-3">
          <ControlPanel />
          <FleetRoster />
          <MetricsPanel />
          <EventFeed />
        </div>
      </div>
    </div>
  );
}

export default App;
