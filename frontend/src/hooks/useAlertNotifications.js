import { useEffect, useRef } from "react";
import { api } from "../services/api";

const KEY = "minewatch.last-notified-alert";
const INTERVAL = 5000;
const ACTIVE = new Set(["WARNING", "CRITICAL", "OFFLINE"]);

function browserNotificationsEnabled() {
  try {
    const settings = JSON.parse(localStorage.getItem("minewatch.settings") || "{}");
    return settings.browserNotifications === true && typeof Notification !== "undefined" && Notification.permission === "granted";
  } catch {
    return false;
  }
}

export function useAlertNotifications() {
  const initialized = useRef(false);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      if (cancelled || !navigator.onLine || !browserNotificationsEnabled()) return;
      try {
        const alert = await api.getLatestAlert();
        if (!alert?.id) return;
        const previous = Number(localStorage.getItem(KEY) || 0);
        localStorage.setItem(KEY, String(alert.id));
        if (!initialized.current) {
          initialized.current = true;
          return;
        }
        if (alert.id <= previous || !ACTIVE.has(String(alert.severity).toUpperCase())) return;
        new Notification(`MineWatch ${alert.severity}`, {
          body: `${alert.node_id}: ${alert.message}`,
          tag: `minewatch-alert-${alert.id}`,
          requireInteraction: alert.severity === "CRITICAL",
        });
      } catch {
        // The dashboard itself handles offline/cache state; notification polling is best-effort.
      }
    }
    poll();
    const timer = window.setInterval(poll, INTERVAL);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);
}
