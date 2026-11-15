// Discreet configuration panel (not a main menu section).
import { api } from "./api.js";
import { icon } from "./icons.js";
import { $, esc, h, toast } from "./ui.js";

const COUNTRIES = { ES: "España", PT: "Portugal", FR: "Francia", IT: "Italia", DE: "Alemania", GB: "Reino Unido", US: "Estados Unidos", MX: "México", AR: "Argentina", CO: "Colombia" };
const CRED = { tmdb_api_key: "TMDB API key (o token v4)", anthropic_api_key: "Anthropic API key", openai_api_key: "OpenAI-compatible API key" };

export async function open(onChanged) {
  let dirty = false;
  const s = await api.get("/api/settings");
  const overlay = $("#overlay");
  const close = () => { document.removeEventListener("keydown", onKey); overlay.replaceChildren(); if (dirty) onChanged?.(); };
  const onKey = (e) => e.key === "Escape" && close();
  document.addEventListener("keydown", onKey);
  const put = async (patch, msg) => { dirty ||= ["platforms", "country", "providers", "tmdb_api_key"].some((k) => k in patch); Object.assign(s, await api.put("/api/settings", patch)); if (msg) toast(msg); };
  const el = h(`<div><div class="backdrop" data-testid="settings-backdrop"></div>
    <section class="panel" role="dialog" aria-modal="true" aria-label="Configuración" data-testid="settings">
      <div class="top"><h1 style="font-size:22px">Configuración</h1><button class="icon-btn" id="s-close" aria-label="Cerrar" data-tip="Cerrar">${icon("x")}</button></div>
      <div><h3>Mis plataformas</h3><div class="chips" id="s-platforms"></div>
        <p class="sub" id="s-noplat" style="margin-top:10px;font-size:13px" hidden>Sin plataformas activas: se mostrará todo el catálogo, sin filtrar por suscripción.</p></div>
      <div class="field-row">
        <div class="field"><label for="s-country">País</label><select id="s-country">${Object.entries(COUNTRIES).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div>
        <div class="field"><label for="s-interval">Refrescar Random Couch Sessions cada</label><select id="s-interval">${[1, 6, 12, 24, 72].map((n) => `<option value="${n}">${n} h</option>`).join("")}</select></div></div>
      <div><h3>Proveedores de catálogo</h3><div class="chips" id="s-providers"></div></div>
      <div><h3>Credenciales</h3><div class="field-row" id="s-cred"></div></div>
      <div><h3>Agente · modelo de lenguaje (opcional)</h3><div class="field-row">
        <div class="field"><label for="s-llm">Proveedor</label><select id="s-llm"><option value="none">Sin LLM (reglas)</option><option value="anthropic">Anthropic</option><option value="openai">OpenAI-compatible</option></select></div>
        <div class="field"><label for="s-model">Modelo</label><input id="s-model" placeholder="por defecto"></div>
        <div class="field"><label for="s-base">Base URL (OpenAI-compatible)</label><input id="s-base" placeholder="https://api.openai.com/v1"></div></div></div>
      <div class="chips"><button class="btn" id="s-recalc">${icon("refresh")} Recalcular perfil</button><a class="btn" href="/api/export" download>${icon("download")} Exportar mis datos</a></div>
    </section></div>`);
  overlay.replaceChildren(el);
  $(".backdrop", el).onclick = close; $("#s-close", el).onclick = close;

  const paintPlatforms = () => {
    $("#s-platforms", el).replaceChildren(...s.platforms.map((p) => {
      const b = h(`<button class="chip-btn" aria-pressed="${!!p.subscribed}" data-testid="platform-${esc(p.key.replace(/\s+/g, "-"))}">${p.icon ? `<img src="${esc(p.icon)}" alt="">` : `<span class="ph"></span>`}${esc(p.name)}</button>`);
      b.onclick = async () => { await put({ platforms: [{ id: p.id, subscribed: !p.subscribed }] }); paintPlatforms(); };
      return b;
    }));
    $("#s-noplat", el).hidden = s.platforms.some((p) => p.subscribed);
  };
  paintPlatforms();
  $("#s-country", el).value = s.country; $("#s-interval", el).value = String(s.discovery_interval_hours);
  $("#s-country", el).onchange = (e) => put({ country: e.target.value }, "País actualizado");
  $("#s-interval", el).onchange = (e) => put({ discovery_interval_hours: +e.target.value }, "Intervalo guardado");
  $("#s-providers", el).replaceChildren(...s.providers.map((p) => {
    const b = h(`<button class="chip-btn" aria-pressed="${p.enabled && p.available}" ${p.available ? "" : "disabled"} title="${p.available ? "" : "No disponible (faltan credenciales o acceso)"}">${esc(p.name)}${p.available ? "" : " · no disponible"}</button>`);
    b.onclick = async () => {
      const on = s.providers.filter((q) => (q.name === p.name ? !q.enabled : q.enabled)).map((q) => q.name);
      await put({ providers: on }, "Proveedores actualizados"); close(); open(onChanged);
    };
    return b;
  }));
  $("#s-cred", el).replaceChildren(...Object.entries(CRED).map(([k, label]) => {
    const f = h(`<div class="field"><label for="c-${k}">${label}</label><input id="c-${k}" type="password" autocomplete="off" value="${esc(s.credentials[k])}" placeholder="no configurada"></div>`);
    $("input", f).onchange = async (e) => { await put({ [k]: e.target.value }, "Credencial guardada"); close(); open(onChanged); };
    return f;
  }));
  $("#s-llm", el).value = s.llm.provider; $("#s-model", el).value = s.llm.model; $("#s-base", el).value = s.llm.base_url;
  $("#s-llm", el).onchange = (e) => put({ llm_provider: e.target.value }, "Agente actualizado");
  $("#s-model", el).onchange = (e) => put({ llm_model: e.target.value });
  $("#s-base", el).onchange = (e) => put({ llm_base_url: e.target.value });
  $("#s-recalc", el).onclick = async () => { await api.post("/api/profile/recalculate"); toast("Perfil recalculado"); };
}
