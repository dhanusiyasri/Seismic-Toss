import { useEffect, useState } from "react";

export default function ConnectionBanner({ connected, checking = false, error = "" }) {
  const [cachedMode, setCachedMode] = useState(false);

  useEffect(() => {
    const onConnectivity = (event) => setCachedMode(Boolean(event.detail?.cached));
    window.addEventListener("minewatch:connectivity", onConnectivity);
    return () => window.removeEventListener("minewatch:connectivity", onConnectivity);
  }, []);

  if (connected && !cachedMode) return null;

  return (
    <div className={`global-connection-banner ${cachedMode ? "cached-mode" : ""}`} role="status" aria-live="polite">
      <span className="connection-banner-icon">{cachedMode ? "↻" : "!"}</span>
      <div>
        <strong>{checking ? "Checking monitoring backend…" : cachedMode ? "Offline mode — showing last known data" : "Monitoring backend offline"}</strong>
        <p>
          {cachedMode
            ? "Live sensor updates and alert actions are paused. Cached dashboard data remains available."
            : (error || "Live data may be unavailable. The application will retry automatically.")}
        </p>
      </div>
    </div>
  );
}
