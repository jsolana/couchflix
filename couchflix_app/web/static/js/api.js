import { toast } from "./ui.js";

async function call(method, url, body) {
  try {
    const res = await fetch(url, {
      method, headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined,
    });
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
};
