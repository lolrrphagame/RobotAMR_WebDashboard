import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import type { Sample, Telemetry } from "../types";
import { downloadCsv, formatTimestamp } from "../utils/telemetry";
import { MotorDiagnostics } from "./diagnostics/MotorDiagnostics";
import { MotionAnalysis } from "./diagnostics/MotionAnalysis";
import { SystemHealth } from "./diagnostics/SystemHealth";
import { Communication } from "./diagnostics/Communication";
import { Events } from "./diagnostics/Events";
export function DiagnosticsPage({
  data,
  history,
  lastTimestamp,
  historyError,
  events,
}: {
  data: Telemetry | null;
  history: Sample[];
  lastTimestamp?: string;
  historyError: string;
  events: Telemetry["events"];
}) {
  const [tab, setTab] = useState("Motors");
  const [now, setNow] = useState(Date.now());
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, []);
  const age = lastTimestamp
    ? Math.max(0, now - Date.parse(lastTimestamp))
    : null;
  const exportHistory = async () => {
    setError("");
    setExporting(true);
    try {
      await downloadCsv(
        "/api/diagnostics/history?format=csv",
        "pbl4-telemetry.csv",
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setExporting(false);
    }
  };
  return (
    <div className="diagnostics-page">
      <div className="diagnostics-top">
        <div>
          <span className="eyebrow">SIMULATION OBSERVABILITY</span>
          <p className="freshness" role="status">
            {data && age !== null && age < 2000
              ? "Live simulated stream"
              : "Disconnected or stale stream"}{" "}
            ·{" "}
            {age === null
              ? "No samples"
              : `sample age ${(age / 1000).toFixed(1)} s`}{" "}
            · {history.length} / 600 samples
          </p>
          <p className="diagnostic-timestamp">
            Latest sample:{" "}
            {lastTimestamp ? formatTimestamp(lastTimestamp) : "Unavailable"}
          </p>
        </div>
        <button
          className="export-button"
          disabled={exporting}
          onClick={exportHistory}
        >
          <Download size={16} />
          {exporting ? "Exporting…" : "Export telemetry CSV"}
        </button>
      </div>
      {(error || historyError) && (
        <p className="export-error" role="alert">
          {error || historyError}
        </p>
      )}
      <div
        className="diagnostics-tabs"
        role="tablist"
        aria-label="Diagnostics sections"
      >
        {["Motors", "Motion Analysis", "System Health", "Communication", "Events"].map((name) => (
          <button
            role="tab"
            aria-selected={tab === name}
            aria-controls="diagnostics-content"
            id={`diagnostics-${name.replaceAll(" ", "-")}`}
            key={name}
            onClick={() => setTab(name)}
          >
            {name}
          </button>
        ))}
      </div>
      <div
        className="diagnostics-content"
        id="diagnostics-content"
        role="tabpanel"
        aria-labelledby={`diagnostics-${tab.replaceAll(" ", "-")}`}
      >
        {tab === "Motors" && <MotorDiagnostics data={data} history={history} />}
        {tab === "Motion Analysis" && <MotionAnalysis history={history} />}
        {tab === "System Health" && <SystemHealth history={history} />}
        {tab === "Communication" && <Communication data={data} />}
        {tab === "Events" && <Events events={events} />}
      </div>
    </div>
  );
}
