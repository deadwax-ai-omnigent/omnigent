/**
 * Deadwax theme registry — the 7 brand themes that replace upstream's
 * light/dark/system modes. The selected theme id lives on
 * `<html data-theme="…">`; the matching `:root[data-theme="…"]` palette in
 * index.css does the actual recoloring. Persisted under a Deadwax-specific
 * localStorage key so it never collides with upstream's `ap-web-theme`.
 */
export const DEADWAX_THEME_STORAGE_KEY = "deadwax_theme_preference_v1";

export const DEADWAX_THEMES = [
  { id: "gold-blue", label: "Blue & Gold" },
  { id: "purple", label: "Gurple Purple" },
  { id: "jimi", label: "Jimi" },
  { id: "record-store", label: "Record Store" },
  { id: "red-black", label: "Kill 'Em" },
  { id: "hornet", label: "Nikki" },
  { id: "billie", label: "Billie" },
  { id: "ye", label: "Ye" },
] as const;

export type DeadwaxThemeId = (typeof DEADWAX_THEMES)[number]["id"];

export const DEFAULT_DEADWAX_THEME: DeadwaxThemeId = "gold-blue";

const THEME_IDS: readonly string[] = DEADWAX_THEMES.map((t) => t.id);

/** Type guard: is `value` one of the known Deadwax theme ids? */
export function isDeadwaxThemeId(
  value: string | null | undefined,
): value is DeadwaxThemeId {
  return value != null && THEME_IDS.includes(value);
}

/** Read the persisted theme, falling back to the Blue & Gold default. */
export function readDeadwaxTheme(): DeadwaxThemeId {
  try {
    const stored = localStorage.getItem(DEADWAX_THEME_STORAGE_KEY);
    if (isDeadwaxThemeId(stored)) return stored;
  } catch {
    // localStorage can throw in private mode / sandboxed embeds — ignore.
  }
  return DEFAULT_DEADWAX_THEME;
}

/** Apply a theme to <html> and persist the choice. */
export function applyDeadwaxTheme(id: DeadwaxThemeId): void {
  document.documentElement.dataset.theme = id;
  try {
    localStorage.setItem(DEADWAX_THEME_STORAGE_KEY, id);
  } catch {
    // Non-fatal: the theme still applies for this session.
  }
}
