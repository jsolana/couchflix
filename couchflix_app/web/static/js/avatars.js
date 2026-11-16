// Built-in avatars: one family, same style (gradient tile + flat white glyph). Ids match the backend's AVATARS ("a1".."a12").
const D = "#0b0d15"; // dark detail colour
const GLYPHS = {
  a1: `<polygon points="14,28 16,8 31,21"/><polygon points="50,28 48,8 33,21"/><circle cx="32" cy="38" r="20"/><circle cx="24.5" cy="35" r="2.6" fill="${D}"/><circle cx="39.5" cy="35" r="2.6" fill="${D}"/><polygon points="29,42 35,42 32,46" fill="${D}"/>`,
  a2: `<polygon points="8,14 24,26 40,26 56,14 52,44 32,58 12,44"/><circle cx="24" cy="38" r="2.6" fill="${D}"/><circle cx="40" cy="38" r="2.6" fill="${D}"/><polygon points="28,48 36,48 32,54" fill="${D}"/>`,
  a3: `<polygon points="12,10 26,18 12,26"/><polygon points="52,10 38,18 52,26"/><ellipse cx="32" cy="36" rx="21" ry="22"/><circle cx="23" cy="32" r="8" fill="${D}"/><circle cx="41" cy="32" r="8" fill="${D}"/><circle cx="23" cy="32" r="3" fill="#fff"/><circle cx="41" cy="32" r="3" fill="#fff"/><polygon points="29,40 35,40 32,47" fill="#6ee7d8"/>`,
  a4: `<rect x="14" y="22" width="36" height="32" rx="8"/><rect x="30.5" y="10" width="3" height="12"/><circle cx="32" cy="9" r="4"/><rect x="21" y="31" width="7" height="7" rx="2" fill="${D}"/><rect x="36" y="31" width="7" height="7" rx="2" fill="${D}"/><rect x="23" y="44" width="18" height="3" rx="1.5" fill="${D}"/>`,
  a5: `<circle cx="32" cy="32" r="23"/><rect x="15" y="22" width="34" height="22" rx="11" fill="${D}"/><path d="M22 28q5-4 11-3" stroke="#6ee7d8" stroke-width="3" fill="none" stroke-linecap="round"/>`,
  a6: `<circle cx="16" cy="16" r="8" fill="${D}"/><circle cx="48" cy="16" r="8" fill="${D}"/><circle cx="32" cy="36" r="21"/><ellipse cx="23.5" cy="34" rx="5.5" ry="7.5" fill="${D}" transform="rotate(20 23.5 34)"/><ellipse cx="40.5" cy="34" rx="5.5" ry="7.5" fill="${D}" transform="rotate(-20 40.5 34)"/><circle cx="24" cy="33" r="2" /><circle cx="40" cy="33" r="2"/><ellipse cx="32" cy="43" rx="4" ry="3" fill="${D}"/>`,
  a7: `<circle cx="32" cy="27" r="19"/><path d="M13 40q-3 12 3 15 4-2 2-8M24 44q-2 12 3 14 3-3 1-12M40 44q2 12-3 14-3-3-1-12M51 40q3 12-3 15-4-2-2-8"/><circle cx="25" cy="26" r="3" fill="${D}"/><circle cx="39" cy="26" r="3" fill="${D}"/><path d="M27 34q5 4 10 0" stroke="${D}" stroke-width="2.4" fill="none" stroke-linecap="round"/>`,
  a8: `<ellipse cx="32" cy="40" rx="24" ry="17"/><circle cx="19" cy="24" r="9"/><circle cx="45" cy="24" r="9"/><circle cx="19" cy="24" r="4" fill="${D}"/><circle cx="45" cy="24" r="4" fill="${D}"/><path d="M17 42q15 12 30 0" stroke="${D}" stroke-width="3" fill="none" stroke-linecap="round"/>`,
  a9: `<polygon points="16,24 22,10 28,22 36,8 42,22 50,12 50,26"/><rect x="10" y="22" width="44" height="32" rx="14"/><circle cx="24" cy="35" r="3" fill="${D}"/><circle cx="42" cy="35" r="3" fill="${D}"/><path d="M22 46q10 7 22 0" stroke="${D}" stroke-width="3" fill="none" stroke-linecap="round"/>`,
  a10: `<path d="M32 6c10 8 14 20 12 34H20C18 26 22 14 32 6Z"/><polygon points="20,30 10,46 20,44"/><polygon points="44,30 54,46 44,44"/><circle cx="32" cy="26" r="6" fill="${D}"/><path d="M26 44h12l-6 14Z" fill="#6ee7d8"/>`,
  a11: `<path d="M12 56V30a20 20 0 0 1 40 0v26l-7-6-6.5 6-6.5-6-6.5 6-6.5-6Z"/><ellipse cx="25" cy="30" rx="3.2" ry="4.5" fill="${D}"/><ellipse cx="39" cy="30" rx="3.2" ry="4.5" fill="${D}"/><ellipse cx="32" cy="41" rx="4" ry="3" fill="${D}"/>`,
  a12: `<polygon points="8,48 12,18 24,32 32,12 40,32 52,18 56,48"/><rect x="8" y="48" width="48" height="7" rx="3"/><circle cx="12" cy="16" r="3.5"/><circle cx="32" cy="10" r="3.5"/><circle cx="52" cy="16" r="3.5"/><circle cx="32" cy="38" r="3.5" fill="#6ee7d8"/>`,
};
const HUES = { a1: 170, a2: 22, a3: 260, a4: 200, a5: 228, a6: 150, a7: 318, a8: 120, a9: 88, a10: 8, a11: 282, a12: 44 };

export const AVATAR_IDS = Object.keys(GLYPHS);
export const isImage = (avatar) => String(avatar).startsWith("data:image/");

/** HTML for an avatar: built-in SVG by id, or the user's own picture. Size comes from the CSS of the parent (.av). */
export function avatarHTML(avatar) {
  if (isImage(avatar)) return `<img src="${avatar}" alt="">`;
  const id = GLYPHS[avatar] ? avatar : "a1", h = HUES[id];
  return `<svg viewBox="0 0 64 64" aria-hidden="true" focusable="false"><defs><linearGradient id="g-${id}" x1="0" y1="0" x2="1" y2="1">` +
    `<stop offset="0" stop-color="hsl(${h},62%,42%)"/><stop offset="1" stop-color="hsl(${(h + 40) % 360},66%,22%)"/></linearGradient></defs>` +
    `<rect width="64" height="64" fill="url(#g-${id})"/><g fill="#fff" fill-opacity=".95">${GLYPHS[id]}</g></svg>`;
}
