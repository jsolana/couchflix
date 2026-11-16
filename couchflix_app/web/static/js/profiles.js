// Session-profile picker ("¿Quién está viendo?"): choose, manage, create and delete family profiles.
// Not to be confused with the taste profile (profile.js), which belongs to each of these.
import { api, profileId } from "./api.js";
import { AVATAR_IDS, avatarHTML } from "./avatars.js";
import { icon } from "./icons.js";
import { $, esc, h, toast } from "./ui.js";

const MAX_IMAGE_CHARS = 150_000;

/** Resolves with the active profile. Always shows the picker unless this tab already chose one. */
export async function ensureProfile() {
  const { profiles, max } = await api.get("/api/profiles");
  const current = profiles.find((p) => String(p.id) === profileId.get());
  if (current) return current;
  profileId.clear();
  return new Promise((resolve) => picker(profiles, max, resolve));
}

export const switchProfile = () => { profileId.clear(); location.hash = "#/suggestions"; location.reload(); };

function picker(profiles, max, done) {
  let managing = false;
  const screen = h(`<div class="picker" id="picker" data-testid="picker">
    <div class="picker-brand">${icon("sofa")}<span>COUCHFLIX</span></div>
    <h1 id="picker-title">¿Quién está viendo?</h1>
    <div class="picker-grid" id="picker-grid" role="list"></div>
    <button class="btn" id="picker-manage" data-testid="manage-profiles">Administrar perfiles</button>
  </div>`);
  document.body.append(screen);
  $("#app").hidden = true;

  const reload = async () => { ({ profiles, max } = await api.get("/api/profiles")); paint(); };
  const choose = (p) => { profileId.set(p.id); screen.remove(); $("#app").hidden = false; done(p); };

  function paint() {
    $("#picker-title", screen).textContent = managing ? "Administrar perfiles" : "¿Quién está viendo?";
    $("#picker-manage", screen).textContent = managing ? "Listo" : "Administrar perfiles";
    screen.classList.toggle("managing", managing);
    const cards = profiles.map((p) => {
      const b = h(`<button class="pf-card" role="listitem" data-testid="profile-${p.id}" aria-label="${managing ? "Editar perfil " : ""}${esc(p.name)}">
        <span class="av">${avatarHTML(p.avatar)}${managing ? `<span class="pf-edit">${icon("pencil")}</span>` : ""}</span><span class="pf-name">${esc(p.name)}</span></button>`);
      b.onclick = () => (managing ? editor(p) : choose(p));
      return b;
    });
    if (profiles.length < max) {
      const add = h(`<button class="pf-card add" role="listitem" data-testid="add-profile" aria-label="Añadir perfil"><span class="av">${icon("plus")}</span><span class="pf-name">Añadir perfil</span></button>`);
      add.onclick = () => editor(null);
      cards.push(add);
    }
    $("#picker-grid", screen).replaceChildren(...cards);
  }

  $("#picker-manage", screen).onclick = () => { managing = !managing; paint(); };

  // ---- create / edit panel (same overlay pattern as settings)
  function editor(profile) {
    let avatar = profile?.avatar || AVATAR_IDS[Math.floor(Math.random() * AVATAR_IDS.length)];
    const overlay = $("#overlay");
    const close = () => { document.removeEventListener("keydown", onKey); overlay.replaceChildren(); };
    const onKey = (e) => e.key === "Escape" && close();
    document.addEventListener("keydown", onKey);
    const el = h(`<div><div class="backdrop"></div>
      <section class="panel" role="dialog" aria-modal="true" aria-label="${profile ? "Editar perfil" : "Nuevo perfil"}" data-testid="profile-editor">
        <div class="top"><h1 style="font-size:22px">${profile ? "Editar perfil" : "Nuevo perfil"}</h1><button class="icon-btn" id="pe-close" aria-label="Cerrar">${icon("x")}</button></div>
        <div class="pe-head"><span class="av lg" id="pe-preview"></span>
          <div class="field" style="flex:1"><label for="pe-name">Nombre</label><input id="pe-name" maxlength="24" autocomplete="off" value="${esc(profile?.name || "")}" data-testid="profile-name"></div></div>
        <div><h3>Avatar</h3><div class="av-grid" id="pe-avatars"></div>
          <div class="chips" style="margin-top:12px"><button class="btn" id="pe-upload" type="button">${icon("image")} Usar una imagen del dispositivo</button>
          <input id="pe-file" type="file" accept="image/*" hidden></div></div>
        <div class="pe-confirm" id="pe-confirm" hidden><p>Se eliminará <strong>${esc(profile?.name || "")}</strong> y todo lo suyo: gustos, historial, valoraciones, búsquedas y sugerencias. No se puede deshacer.</p>
          <div class="chips"><button class="btn danger" id="pe-yes" data-testid="confirm-delete">Sí, eliminar</button><button class="btn" id="pe-no">Cancelar</button></div></div>
        <div class="chips" id="pe-actions"><button class="btn primary" id="pe-save" data-testid="save-profile">${profile ? "Guardar" : "Crear perfil"}</button>
          <button class="btn" id="pe-cancel">Cancelar</button>
          ${profile && profiles.length > 1 ? `<button class="btn danger" id="pe-delete" style="margin-left:auto" data-testid="delete-profile">${icon("trash")} Eliminar perfil</button>` : ""}</div>
      </section></div>`);
    overlay.replaceChildren(el);
    $(".backdrop", el).onclick = close; $("#pe-close", el).onclick = close; $("#pe-cancel", el).onclick = close;

    const paintAvatars = () => {
      $("#pe-preview", el).innerHTML = avatarHTML(avatar);
      const options = [...(AVATAR_IDS.includes(avatar) ? [] : [avatar]), ...AVATAR_IDS];
      $("#pe-avatars", el).replaceChildren(...options.map((id) => {
        const b = h(`<button type="button" class="av-opt" aria-pressed="${id === avatar}" aria-label="Avatar" data-testid="avatar-${AVATAR_IDS.includes(id) ? id : "custom"}"><span class="av">${avatarHTML(id)}</span></button>`);
        b.onclick = () => { avatar = id; paintAvatars(); };
        return b;
      }));
    };
    paintAvatars();

    $("#pe-upload", el).onclick = () => $("#pe-file", el).click();
    $("#pe-file", el).onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try { avatar = await shrink(file); paintAvatars(); } catch { toast("No se pudo usar esa imagen", "err"); }
    };

    $("#pe-save", el).onclick = async () => {
      const name = $("#pe-name", el).value.trim();
      if (!name) { toast("Escribe un nombre", "err"); $("#pe-name", el).focus(); return; }
      if (profile) await api.put(`/api/profiles/${profile.id}`, { name, avatar });
      else await api.post("/api/profiles", { name, avatar });
      close(); await reload();
    };
    $("#pe-name", el).onkeydown = (e) => { if (e.key === "Enter") $("#pe-save", el).click(); };  // never return false: it cancels typing
    if ($("#pe-delete", el)) {
      $("#pe-delete", el).onclick = () => { $("#pe-actions", el).hidden = true; $("#pe-confirm", el).hidden = false; };
      $("#pe-no", el).onclick = () => { $("#pe-confirm", el).hidden = true; $("#pe-actions", el).hidden = false; };
      $("#pe-yes", el).onclick = async () => {
        await api.del(`/api/profiles/${profile.id}`);
        if (String(profile.id) === profileId.get()) profileId.clear();
        close(); await reload(); toast("Perfil eliminado");
      };
    }
    $("#pe-name", el).focus();
  }

  paint();
}

/** Square-crops and shrinks a picture to a 256px JPEG data-URL (small enough to live in the database). */
function shrink(file) {
  return new Promise((resolve, reject) => {
    const img = new Image(), url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      const side = Math.min(img.width, img.height), c = document.createElement("canvas");
      c.width = c.height = 256;
      c.getContext("2d").drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, 256, 256);
      for (const q of [0.85, 0.7, 0.5, 0.35]) {
        const data = c.toDataURL("image/jpeg", q);
        if (data.length <= MAX_IMAGE_CHARS) return resolve(data);
      }
      reject(new Error("too big"));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("bad image")); };
    img.src = url;
  });
}
