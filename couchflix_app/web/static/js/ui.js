// Shared UI pieces: DOM helpers, toasts, cards, skeletons and the carousel.
import { icon } from "./icons.js";

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };
export const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function toast(message, kind = "") {
  const el = h(`<div class="toast ${kind}">${esc(message)}</div>`);
  $("#toasts").append(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 320); }, 2400);
}

export function fmtDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  const day = d.toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "numeric" }).replace(/\./g, "");
  return `${day} · ${d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })}`;
}

const hue = (s) => [...String(s)].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 7);

// ---- cards
export function skeletonCard() {
  return h(`<div class="card sk" aria-hidden="true" data-testid="skeleton"><div class="meta"><i></i><i></i></div></div>`);
}

export function cardEl(item, lazy = false) {
  const plats = item.platforms.map((p) => p.icon ? `<img class="${p.mine ? "mine" : ""}" src="${esc(p.icon)}" alt="${esc(p.name)}" title="${esc(p.name)}" loading="lazy">` : "").join("");
  const info = [item.year, item.genres[0]].filter(Boolean).join(" · ");
  const el = h(`<article class="card sk ${item.watched ? "watched" : ""}" tabindex="0" role="button" data-id="${item.id}" data-testid="card" ${item.reason ? `title="${esc(item.reason)}"` : ""}
      aria-label="${esc(item.title)}${item.year ? ", " + item.year : ""}. Abrir detalle">
      <div class="poster"></div>
      ${item.rating ? `<span class="chip rating">★ ${item.rating.toFixed(1)}</span>` : ""}
      ${item.affinity != null ? `<span class="chip aff" title="Afinidad con tu perfil">${item.affinity}%</span>` : ""}
      <div class="meta"><h3>${esc(item.title)}</h3><p class="info">${esc(info)}</p>${plats ? `<div class="plats">${plats}</div>` : ""}</div>
      <span class="seen">${icon("eye")}</span>
    </article>`);
  const poster = $(".poster", el);
  const fallback = () => { poster.innerHTML = `<div class="fallback" style="background:linear-gradient(135deg,hsl(${hue(item.title)} 40% 22%),hsl(${(hue(item.title) + 70) % 360} 45% 12%))">${esc(item.title)}</div>`; };
  el.ready = new Promise((resolve) => {
    if (!item.poster) { fallback(); return resolve(); }
    const img = new Image();
    img.className = "cover"; img.alt = ""; img.decoding = "async";
    if (lazy) img.loading = "lazy"; // only cards below the fold; visible ones load eagerly before being revealed
    img.onload = () => { img.classList.add("loaded"); resolve(); };
    img.onerror = () => { fallback(); resolve(); };
    img.src = item.poster;
    poster.append(img);
    setTimeout(resolve, 4000); // never leave a card in placeholder state because of one slow image
  });
  el.ready.then(() => { el.classList.remove("sk"); el.classList.add("in"); });
  return el;
}

export function openOnActivate(root) {
  root.addEventListener("click", (e) => { const c = e.target.closest(".card[data-id]"); if (c && !root.suppressClick) location.hash = `#/c/${c.dataset.id}`; });
  root.addEventListener("keydown", (e) => {
    const c = e.target.closest(".card[data-id]");
    if (c && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); location.hash = `#/c/${c.dataset.id}`; }
  });
}

/** Real cards take the place of the skeletons right away, still looking like placeholders (`.sk`) until their own
 *  image is ready — so each carátula is revealed individually, never waiting for the others. */
export async function revealInto(container, items, { eager = 8 } = {}) {
  const slots = $$(".card.sk:not([data-id])", container);
  const cards = items.map((item, i) => cardEl(item, i >= eager));  // beyond the first screen: lazy-loaded
  cards.forEach((card, i) => (slots[i] ? slots[i].replaceWith(card) : container.append(card)));
  slots.slice(items.length).forEach((s) => s.remove());
  container.dispatchEvent(new Event("scroll"));
  await Promise.all(cards.slice(0, eager).map((c) => c.ready));
}

export function skeletonRow(n = 9) {
  return Array.from({ length: n }, () => skeletonCard());
}

// ---- carousel
export function createCarousel({ skeletons = 9, label = "Carrusel" } = {}) {
  const el = h(`<div class="carousel at-start" role="region" aria-roledescription="carrusel" aria-label="${esc(label)}">
      <button class="car-arrow l" aria-label="Anterior" hidden>${icon("left")}</button>
      <div class="track" tabindex="0" data-testid="track"></div>
      <button class="car-arrow r" aria-label="Siguiente">${icon("right")}</button></div>`);
  const track = $(".track", el), [left, right] = $$(".car-arrow", el);
  const sync = () => {
    const max = track.scrollWidth - track.clientWidth - 4;
    el.classList.toggle("at-start", track.scrollLeft < 8);
    el.classList.toggle("at-end", track.scrollLeft >= max);
    left.hidden = track.scrollLeft < 8; right.hidden = track.scrollLeft >= max;
  };
  const page = (dir) => track.scrollBy({ left: dir * track.clientWidth * 0.8, behavior: reduceMotion() ? "auto" : "smooth" });
  left.onclick = () => page(-1); right.onclick = () => page(1);
  track.addEventListener("scroll", sync, { passive: true });
  addEventListener("resize", sync);

  // mouse drag (touch and trackpads scroll natively with snap)
  let down = null;
  track.addEventListener("pointerdown", (e) => { if (e.pointerType === "mouse" && e.button === 0) down = { x: e.clientX, left: track.scrollLeft, moved: false }; });
  addEventListener("pointermove", (e) => {
    if (!down) return;
    const dx = e.clientX - down.x;
    if (Math.abs(dx) > 5 && !down.moved) { down.moved = true; track.classList.add("dragging"); }
    if (down.moved) track.scrollLeft = down.left - dx;
  });
  addEventListener("pointerup", () => {
    if (!down) return;
    if (down.moved) { track.suppressClick = true; setTimeout(() => (track.suppressClick = false), 0); }
    track.classList.remove("dragging"); down = null;
  });

  // keyboard: arrows move focus between cards and keep it in view
  track.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const cards = $$(".card:not(.sk)", track), i = cards.indexOf(document.activeElement);
    const next = cards[i === -1 ? 0 : Math.max(0, Math.min(cards.length - 1, i + (e.key === "ArrowRight" ? 1 : -1)))];
    next?.focus({ preventScroll: true });
    next?.scrollIntoView({ inline: "center", block: "nearest", behavior: reduceMotion() ? "auto" : "smooth" });
  });
  openOnActivate(track);

  const api = {
    el, track,
    skeleton(n = skeletons) { track.replaceChildren(...skeletonRow(n)); track.scrollLeft = 0; sync(); el.dataset.state = "loading"; },
    async show(items) { await revealInto(track, items); el.dataset.state = "ready"; requestAnimationFrame(sync); },
    message(node) { track.replaceChildren(node); el.dataset.state = "empty"; },
  };
  api.skeleton();
  return api;
}

export function emptyState(iconName, title, text, action) {
  const el = h(`<div class="empty" data-testid="empty">${icon(iconName)}<strong>${esc(title)}</strong><span>${esc(text || "")}</span></div>`);
  if (action) { const b = h(`<button class="btn primary">${esc(action.label)}</button>`); b.onclick = action.onClick; el.append(b); }
  return el;
}
