const PREFIX = "minewatch:cache:v2:";
const META_KEY = "minewatch:cache-meta:v2";
const MAX_CHARS = 900000;
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

function readMeta() {
  try { return JSON.parse(localStorage.getItem(META_KEY) || "{}"); }
  catch { return {}; }
}

export function saveCached(path, data) {
  try {
    const raw = JSON.stringify(data);
    if (raw.length > MAX_CHARS) return false;
    localStorage.setItem(PREFIX + path, raw);
    const meta = readMeta();
    meta[path] = { savedAt: Date.now(), size: raw.length };
    localStorage.setItem(META_KEY, JSON.stringify(meta));
    return true;
  } catch (error) {
    console.warn("Offline cache write skipped:", error);
    return false;
  }
}

export function readCached(path, { allowStale = true } = {}) {
  try {
    const raw = localStorage.getItem(PREFIX + path);
    if (!raw) return null;
    const meta = readMeta()[path];
    if (!allowStale && meta?.savedAt && Date.now() - meta.savedAt > MAX_AGE_MS) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function cachedAt(path) {
  return readMeta()[path]?.savedAt || null;
}

export function dispatchConnectivity(online, cached = false) {
  window.dispatchEvent(new CustomEvent("minewatch:connectivity", {
    detail: { online, cached, at: Date.now() }
  }));
}

export function clearOfflineCache() {
  try {
    const meta = readMeta();
    Object.keys(meta).forEach((path) => localStorage.removeItem(PREFIX + path));
    localStorage.removeItem(META_KEY);
  } catch (error) {
    console.warn("Offline cache clear skipped:", error);
  }
}
