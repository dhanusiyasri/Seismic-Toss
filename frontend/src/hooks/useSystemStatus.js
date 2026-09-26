import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../services/api";

const HEALTH_INTERVAL = 5000;

export function useSystemStatus() {
  const [connected, setConnected] = useState(false);
  const [checking, setChecking] = useState(true);
  const [cachedMode, setCachedMode] = useState(false);
  const [lastChecked, setLastChecked] = useState(null);
  const [error, setError] = useState("");
  const inFlight = useRef(false);

  useEffect(() => {
    const onConnectivity = (event) => {
      setCachedMode(Boolean(event.detail?.cached));
      if (event.detail?.cached) setConnected(false);
    };
    window.addEventListener("minewatch:connectivity", onConnectivity);
    const onBrowserOnline = () => setCachedMode(false);
    const onBrowserOffline = () => { setConnected(false); setCachedMode(true); };
    window.addEventListener("online", onBrowserOnline);
    window.addEventListener("offline", onBrowserOffline);
    return () => {
      window.removeEventListener("minewatch:connectivity", onConnectivity);
      window.removeEventListener("online", onBrowserOnline);
      window.removeEventListener("offline", onBrowserOffline);
    };
  }, []);

  const check = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      if (!navigator.onLine) throw new Error("Browser is offline");
      const result = await fetch(`${api.baseUrl}/api/health`, { cache: "no-store" });
      if (!result.ok) throw new Error(`Health endpoint returned ${result.status}`);
      setConnected(true);
      setCachedMode(false);
      setError("");
      setLastChecked(new Date());
    } catch (err) {
      setConnected(false);
      setCachedMode(true);
      setError(err?.message || "Monitoring backend is unreachable");
      setLastChecked(new Date());
    } finally {
      setChecking(false);
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    check();
    const timer = window.setInterval(check, HEALTH_INTERVAL);
    return () => window.clearInterval(timer);
  }, [check]);

  return { connected, checking, cachedMode, lastChecked, error, refresh: check };
}
