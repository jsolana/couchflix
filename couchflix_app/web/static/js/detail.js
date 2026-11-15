// Detail view: info + icon actions + microinteractions + per-block update dates.
import { api } from "./api.js";
import { icon } from "./icons.js";
import { $, esc, fmtDate, h, toast } from "./ui.js";

const MODES = { subscription: "Suscripción", free: "Gratis", free_ads: "Gratis con anuncios", rental: "Alquiler", purchase: "Compra" };
const ACTIONS = [
  ["watched", "Marcar como vista", icon("eye")],
  ["like", "Me gusta", icon("up")],
  ["love", "Me encanta", icon("up") + icon("up"), "dbl"],
  ["dislike", "No me gusta", icon("down")],
  ["comment", "Añadir comentario", icon("chat")],
];
let onChange = () => {};
export const setOnChange = (fn) => (onChange = fn);

let escHandler;
export function close() {
  $("#overlay").replaceChildren(); document.body.style.overflow = "";
  document.removeEventListener("keydown", escHandler);
}

export async function open(id, closeTo) {
  const overlay = $("#overlay");
  const shell = h(`<div><div class="backdrop"></div>
    <aside class="detail" role="dialog" aria-modal="true" aria-label="Detalle" data-testid="detail">
      <button class="icon-btn close" aria-label="Cerrar" data-tip="Cerrar" data-testid="close">${icon("x")}</button>
      <div class="d-poster"><div class="sk-line" style="height:100%;border-radius:0"></div></div>
      <div class="d-body"><div class="sk-line" style="height:34px;width:70%"></div><div class="sk-line" style="width:45%"></div>
        <div class="sk-line" style="height:46px;width:60%"></div><div class="sk-line" style="height:90px"></div></div>
    </aside></div>`);
  overlay.replaceChildren(shell);
  document.body.style.overflow = "hidden";
  const quit = () => closeTo();
  document.removeEventListener("keydown", escHandler);
  escHandler = (e) => e.key === "Escape" && quit();
  document.addEventListener("keydown", escHandler);
  $(".backdrop", shell).onclick = quit; $(".close", shell).onclick = quit;
  $(".close", shell).focus();
  let data;
  try { data = await api.get(`/api/content/${id}`); } catch { return quit(); }
  if (!overlay.contains(shell)) return;
  render($(".detail", shell), data.content, quit);
  if (data.errors.length) toast("Mostrando datos guardados · alguna fuente no responde");
}

function render(el, c, quit) {
  const state = { ...c.interaction };
  const facts = [c.year, c.type === "tv" ? (c.seasons ? `${c.seasons} temporada${c.seasons > 1 ? "s" : ""}` : "Serie") : c.runtime && `${c.runtime} min`, c.genres.join(", ")].filter(Boolean).join(" · ");
  const scores = Object.entries(c.ratings).map(([k, v]) => `<span class="score" title="Puntuación ${k.toUpperCase()}">${k === "imdb" ? "IMDb" : k.toUpperCase()} ★ ${v.toFixed(1)}</span>`).join("");
  el.innerHTML = `
    <button class="icon-btn close" aria-label="Cerrar" data-tip="Cerrar" data-testid="close">${icon("x")}</button>
    <div class="d-poster">${c.poster ? `<img src="${esc(c.poster)}" alt="Carátula de ${esc(c.title)}">` : `<div class="sk-line" style="height:100%;border-radius:0;animation:none"></div>`}</div>
    <div class="d-body">
      <div><h2 data-testid="detail-title">${esc(c.title)}</h2><p class="sub" style="margin-top:6px">${esc(facts)}</p></div>
      ${scores ? `<div class="scores" data-testid="scores">${scores}</div>` : ""}
      <div class="actions" role="group" aria-label="Acciones">
        ${ACTIONS.map(([k, label, svg, cls]) => `<button class="act ${cls || ""}" data-act="${k}" data-tip="${label}" aria-label="${label}" aria-pressed="false" data-testid="act-${k}">${svg}</button>`).join("")}
        <span class="sep"></span>
        <button class="act" data-act="refresh" data-tip="Actualizar información" aria-label="Actualizar información" data-testid="act-refresh">${icon("refresh")}</button>
      </div>
      <div class="comment-pop" data-testid="comment-pop"><textarea aria-label="Tu comentario" placeholder="¿Qué te pareció?" data-testid="comment-text"></textarea>
        <div class="row-end"><button class="icon-btn" data-act="save-comment" aria-label="Guardar comentario" data-tip="Guardar" data-testid="save-comment">${icon("check")}</button></div></div>
      <p class="synopsis" data-testid="synopsis">${esc(c.synopsis || "Sin sinopsis disponible.")}</p>
      <div><h4>Dónde verla · ${esc(c.country)}</h4><ul class="offers" data-testid="offers"></ul></div>
      <footer class="updated" data-testid="updated"></footer>
    </div>`;
  $(".close", el).onclick = quit;
  paintOffers(el, c);
  paintUpdated(el, c);
  const paint = () => {
    el.querySelectorAll(".act[aria-pressed]").forEach((b) => {
      const k = b.dataset.act;
      b.setAttribute("aria-pressed", String(k === "comment" ? !!state.comment : k === "watched" ? state.watched : state.rating === k));
    });
  };
  paint();
  $("[data-testid=comment-text]", el).value = state.comment || "";

  const pop = (btn, cls) => { btn.classList.remove(cls); void btn.offsetWidth; btn.classList.add(cls); setTimeout(() => btn.classList.remove(cls), 1000); };
  const save = async (fields) => { Object.assign(state, fields); paint(); await api.put(`/api/content/${c.id}/interaction`, fields); onChange(c.id, state); };

  el.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const k = btn.dataset.act;
    if (k === "watched") { pop(btn, "pop-watch"); await save({ watched: !state.watched }); toast(state.watched ? "Marcada como vista" : "Ya no figura como vista"); }
    else if (["like", "love", "dislike"].includes(k)) {
      const on = state.rating !== k;
      if (on) pop(btn, k === "love" ? "pop-love" : k === "like" ? "pop-like" : "pop-dislike");
      await save({ rating: on ? k : null });
      toast(on ? { like: "Te gusta", love: "Te encanta", dislike: "No te gusta" }[k] : "Valoración quitada");
    } else if (k === "comment") { const p = $(".comment-pop", el); p.classList.toggle("open"); p.classList.contains("open") && $("textarea", p).focus(); }
    else if (k === "save-comment") { await save({ comment: $("textarea", el).value.trim() || null }); $(".comment-pop", el).classList.remove("open"); toast("Comentario guardado"); }
    else if (k === "refresh") await refresh(el, c, btn);
  });
}

async function refresh(el, c, btn) {
  btn.classList.add("spin"); btn.disabled = true;
  try {
    const r = await api.post(`/api/content/${c.id}/refresh`);
    paintOffers(el, r.content); paintUpdated(el, r.content);
    toast(r.status === "error" ? "No se pudo actualizar · mostrando datos guardados" : r.status === "unchanged" ? "Todo al día, sin cambios" : "Información actualizada", r.status === "error" ? "err" : "");
  } catch { /* api.js already informed; previous data stays on screen */ }
  btn.classList.remove("spin"); btn.disabled = false;
}

function paintOffers(el, c) {
  const list = $(".offers", el);
  list.innerHTML = c.offers.length ? c.offers.map((o) => {
    const inner = `${o.icon ? `<img src="${esc(o.icon)}" alt="">` : ""}<span>${esc(o.name)}</span>${o.mine ? `<span class="mine-tag">tuya</span>` : ""}<span class="mode">${MODES[o.mode] || o.mode}</span>${o.url ? icon("link") : ""}`;
    return `<li>${o.url ? `<a href="${esc(o.url)}" target="_blank" rel="noopener noreferrer">${inner}</a>` : `<span>${inner}</span>`}</li>`;
  }).join("") : `<li class="sub" data-testid="no-availability">${c.availability_known ? "No disponible en streaming en tu país." : "Disponibilidad desconocida por ahora."}</li>`;
}

function paintUpdated(el, c) {
  const line = (label, iso, extra = "") => iso ? `<div class="line">${label} el <time datetime="${iso}" data-testid="${extra}">${fmtDate(iso)}</time></div>` : "";
  $(".updated", el).innerHTML = (line("Información actualizada", c.metadata_updated_at, "meta-updated")
    + line("Disponibilidad actualizada", c.availability_updated_at, "avail-updated")) || `<div class="line">Sin información de actualización</div>`;
  if (c.sources.length) $(".updated", el).insertAdjacentHTML("beforeend", `<div class="line">Fuentes: ${c.sources.map(esc).join(", ")}</div>`);
}
