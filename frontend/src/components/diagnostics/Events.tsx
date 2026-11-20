import { useState } from "react";
import { Download, Search } from "lucide-react";
import type { Telemetry } from "../../types";
import { downloadCsv, formatTimestamp } from "../../utils/telemetry";
export function Events({ events }: { events: Telemetry["events"] }) {
  const [level, setLevel] = useState("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const filtered = events.filter(
    (event) =>
      (level === "all" || event.level === level) &&
      event.message.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
  );
  const exportLogs = async () => {
    setExporting(true);
    setError("");
    try {
      await downloadCsv(
        `/api/events?${new URLSearchParams({ level, q: query, format: "csv" })}`,
        "pbl4-events.csv",
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setExporting(false);
    }
  };
  return (
    <section className="panel advanced-events">
      <div className="panel-heading">
        <h2>Simulation event archive</h2>
        <span className="tag">LATEST 60 EVENTS</span>
      </div>
      <div className="event-toolbar">
        <label>
          Severity
          <select
            aria-label="Event severity"
            value={level}
            onChange={(e) => setLevel(e.target.value)}
          >
            <option value="all">All levels</option>
            <option value="info">INFO</option>
            <option value="warning">WARNING</option>
            <option value="error">ERROR</option>
          </select>
        </label>
        <label className="event-search">
          <span>
            <Search size={14} />
            Keyword
          </span>
          <input
            aria-label="Search events"
            value={query}
            maxLength={200}
            placeholder="Search messages…"
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <button
          className="export-button"
          disabled={exporting}
          onClick={exportLogs}
        >
          <Download size={16} />
          {exporting ? "Exporting…" : "Export filtered events CSV"}
        </button>
      </div>
      {error && (
        <p role="alert" className="export-error">
          {error}
        </p>
      )}
      <p className="diagnostic-footnote">
        {filtered.length} of {events.length} retained events · timestamps
        UTC+07; CSV uses UTC ISO 8601.
      </p>
      <div className="diagnostic-table-wrap">
        <table className="diagnostic-table events-table">
          <thead>
            <tr>
              <th>Timestamp (UTC+07)</th>
              <th>Level</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((event) => (
              <tr key={event.id}>
                <td>{formatTimestamp(event.time)}</td>
                <td>
                  <span className={`event-severity ${event.level}`}>
                    {event.level.toUpperCase()}
                  </span>
                </td>
                <td>{event.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!filtered.length && (
          <p className="empty-events">No events match these filters.</p>
        )}
      </div>
    </section>
  );
}
