import { toast } from "./ui.js";

// Active session profile: per tab (sessionStorage), sent on every call so the server keeps no "current profile".
const KEY = "couchflix.profile";
export const profileId = {
  get: () => { try { return sessionStorage.getItem(KEY); } catch { return null; } },
  set: (id) => { try { sessionStorage.setItem(KEY, String(id)); } catch {} },
  clear: () => { try { sessionStorage.removeItem(KEY); } catch {} },
};
export const authHeaders = () => (profileId.get() ? { "X-Profile": profileId.get() } : {});

async function call(method, url, body) {
  try {
    const res = await fetch(url, {
      method, headers: { ...authHeaders(), ...(body ? { "Content-Type": "application/json" } : {}) }, body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 401) { profileId.clear(); location.hash = "#/suggestions"; location.reload(); return new Promise(() => {}); }
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Error ${res.status}`);
    return await res.json();
  } catch (err) {
    toast(navigator.onLine ? "Algo no ha salido bien. Tus datos están a salvo." : "Sin conexión", "err");
    throw err;
  }
}

export const api = {
  get: (url) => call("GET", url),
  post: (url, body) => call("POST", url, body ?? {}),
  put: (url, body) => call("PUT", url, body),
  del: (url) => call("DELETE", url),
};
