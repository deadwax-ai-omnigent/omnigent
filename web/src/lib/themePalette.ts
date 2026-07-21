// Persisted, app-global color-palette preference.
//
// The web UI has two independent appearance axes:
//
//   1. MODE  — light / dark / system, owned by next-themes (toggles the
//      `.dark` class on <html>; see components/theme/ThemeProvider.tsx).
//   2. PALETTE — the color scheme (Deadwax, GitHub, Dracula, …), owned here.
//
// A palette is applied as a `data-theme` attribute on <html>, so it composes
// with the mode class: `:root:not(.dark)[data-theme="github"]` is GitHub-light
// and `.dark[data-theme="github"]` is GitHub-dark (see the palette blocks in
// index.css). The default "omni" id is retained for storage compatibility but
// now represents Deadwax Blue & Gold. It carries no CSS overrides and falls
// through to the branded base `:root` / `.dark` tokens. Everything uses CSS custom
// properties (--background, --primary, --sidebar, …), so a palette re-skins the
// whole app without any component knowing a theme changed.
//
// Mirrors lib/uiFontPreferences.ts: a read/write pair backed by localStorage
// plus a single `apply*` function that owns the DOM side-effect, called at boot
// (main.tsx) before first paint and on every change (Appearance settings).

const STORAGE_KEY = "omnigent:ui-theme-palette";
const LEGACY_DEADWAX_STORAGE_KEY = "deadwax_theme_preference_v1";

/** Selectable color palettes. The first entry is the default (brand) look. */
export const themePalettes = [
  "omni",
  "purple",
  "jimi",
  "record-store",
  "red-black",
  "hornet",
  "billie",
  "ye",
  "dracula",
  "github",
  "catppuccin",
  "gruvbox",
  "nord",
] as const;

export type ThemePalette = (typeof themePalettes)[number];

/** Built-in palettes plus the user's derived custom configuration. */
export const themeSelections = [...themePalettes, "custom"] as const;
export type ThemeSelection = (typeof themeSelections)[number];

/** Default palette: Deadwax Blue & Gold tokens defined in `:root` / `.dark`. */
export const DEFAULT_PALETTE: ThemePalette = "omni";

/** A few representative colors used to render a palette's preview swatch. */
export interface PaletteSwatch {
  /** Page canvas (behind the cards). */
  bg: string;
  /** Card / panel surface floating on the canvas. */
  card: string;
  /** Primary action / brand accent for this palette. */
  accent: string;
  /** Card border / divider. */
  border: string;
  /** Body text on the card. */
  text: string;
}

export interface PaletteMeta {
  id: ThemePalette;
  /** Display name shown under the swatch. */
  label: string;
  /** One-line description of the palette's character. */
  blurb: string;
  /** Swatch colors for the light rendering of this palette. */
  light: PaletteSwatch;
  /** Swatch colors for the dark rendering of this palette. */
  dark: PaletteSwatch;
}

// Swatch colors are a hand-picked summary of each palette's CSS block — enough
// to render a faithful mini-preview without parsing the stylesheet. Keep these
// in sync with the matching `[data-theme]` block in index.css.
export const PALETTES: readonly PaletteMeta[] = [
  {
    id: "omni",
    label: "Blue & Gold",
    blurb: "The signature Deadwax gold on midnight blue.",
    light: {
      bg: "#fdfafa",
      card: "#ffffff",
      accent: "#edb978",
      border: "#e8ecf0",
      text: "#11171c",
    },
    dark: { bg: "#111318", card: "#1d2028", accent: "#edb978", border: "#2a2f3a", text: "#ece8e1" },
  },
  {
    id: "purple",
    label: "Gurple Purple",
    blurb: "Deep violet with an electric-purple accent.",
    light: {
      bg: "#0e0914",
      card: "#1a1025",
      accent: "#8b2eff",
      border: "#34184d",
      text: "#f3eaff",
    },
    dark: { bg: "#0e0914", card: "#1a1025", accent: "#8b2eff", border: "#34184d", text: "#f3eaff" },
  },
  {
    id: "jimi",
    label: "Jimi",
    blurb: "Purple haze with a vivid magenta lead.",
    light: {
      bg: "#160c1c",
      card: "#24142d",
      accent: "#c62cb8",
      border: "#3a2048",
      text: "#f6eafc",
    },
    dark: { bg: "#160c1c", card: "#24142d", accent: "#c62cb8", border: "#3a2048", text: "#f6eafc" },
  },
  {
    id: "record-store",
    label: "Record Store",
    blurb: "Warm black vinyl with a worn-gold accent.",
    light: {
      bg: "#0c0d0b",
      card: "#1b1b18",
      accent: "#d9a441",
      border: "#303126",
      text: "#f3efe4",
    },
    dark: { bg: "#0c0d0b", card: "#1b1b18", accent: "#d9a441", border: "#303126", text: "#f3efe4" },
  },
  {
    id: "red-black",
    label: "Kill 'Em",
    blurb: "Near-black surfaces cut with signal red.",
    light: {
      bg: "#090405",
      card: "#170a0c",
      accent: "#d72638",
      border: "#3a0d11",
      text: "#f6edee",
    },
    dark: { bg: "#090405", card: "#170a0c", accent: "#d72638", border: "#3a0d11", text: "#f6edee" },
  },
  {
    id: "hornet",
    label: "Nikki",
    blurb: "Black, red, and gold with hornet energy.",
    light: {
      bg: "#000000",
      card: "#0d0d0d",
      accent: "#d71920",
      border: "#1b1b1b",
      text: "#d6a84f",
    },
    dark: { bg: "#000000", card: "#0d0d0d", accent: "#d71920", border: "#1b1b1b", text: "#d6a84f" },
  },
  {
    id: "billie",
    label: "Billie",
    blurb: "Midnight navy lit by acid green.",
    light: {
      bg: "#071426",
      card: "#0b203c",
      accent: "#a6ff00",
      border: "#153b70",
      text: "#eaf3ff",
    },
    dark: { bg: "#071426", card: "#0b203c", accent: "#a6ff00", border: "#153b70", text: "#eaf3ff" },
  },
  {
    id: "ye",
    label: "Ye",
    blurb: "Severe monochrome in near-black graphite.",
    light: {
      bg: "#000000",
      card: "#070707",
      accent: "#5a5a5a",
      border: "#141414",
      text: "#6a6a6a",
    },
    dark: { bg: "#000000", card: "#070707", accent: "#5a5a5a", border: "#141414", text: "#6a6a6a" },
  },
  {
    id: "dracula",
    label: "Dracula",
    blurb: "Moody purple with a pink pop.",
    light: {
      bg: "#f7f5fd",
      card: "#ffffff",
      accent: "#7c3aed",
      border: "#e6e0f2",
      text: "#1e1a2b",
    },
    dark: { bg: "#282a36", card: "#343746", accent: "#bd93f9", border: "#44475a", text: "#f8f8f2" },
  },
  {
    id: "github",
    label: "GitHub",
    blurb: "Clean neutrals with a signal blue.",
    light: {
      bg: "#f6f8fa",
      card: "#ffffff",
      accent: "#0969da",
      border: "#d1d9e0",
      text: "#1f2328",
    },
    dark: { bg: "#0d1117", card: "#161b22", accent: "#58a6ff", border: "#30363d", text: "#e6edf3" },
  },
  {
    id: "catppuccin",
    label: "Catppuccin",
    blurb: "Soft pastels — Latte & Mocha.",
    light: {
      bg: "#eff1f5",
      card: "#ffffff",
      accent: "#8839ef",
      border: "#ccd0da",
      text: "#4c4f69",
    },
    dark: { bg: "#1e1e2e", card: "#313244", accent: "#cba6f7", border: "#45475a", text: "#cdd6f4" },
  },
  {
    id: "gruvbox",
    label: "Gruvbox",
    blurb: "Warm retro earth tones.",
    light: {
      bg: "#fbf1c7",
      card: "#fffdf2",
      accent: "#d65d0e",
      border: "#e6d5a8",
      text: "#3c3836",
    },
    dark: { bg: "#282828", card: "#3c3836", accent: "#fe8019", border: "#504945", text: "#ebdbb2" },
  },
  {
    id: "nord",
    label: "Nord",
    blurb: "Arctic frost blues over polar-night neutrals.",
    light: {
      bg: "#eceff4",
      card: "#e5e9f0",
      accent: "#5e81ac",
      border: "#d8dee9",
      text: "#2e3440",
    },
    dark: { bg: "#2e3440", card: "#3b4252", accent: "#88c0d0", border: "#4c566a", text: "#eceff4" },
  },
] as const;

/**
 * Return whether a string is a supported palette id.
 *
 * localStorage can hold any stale or hand-edited value, so this type guard
 * lets call sites reject unknown ids before handing them to the UI or the DOM.
 *
 * @param value Palette string to validate, e.g. `"github"`.
 * @returns Whether the value is a supported palette id.
 */
export function isThemePalette(value: unknown): value is ThemePalette {
  return typeof value === "string" && (themePalettes as readonly string[]).includes(value);
}

export function isThemeSelection(value: unknown): value is ThemeSelection {
  return typeof value === "string" && (themeSelections as readonly string[]).includes(value);
}

/**
 * Read the persisted palette.
 *
 * Returns the default when nothing is stored, on a server render (no `window`),
 * or when the stored value is missing/malformed — never throws, so a corrupt
 * entry can't break app boot.
 */
export function readThemePalette(): ThemeSelection {
  if (typeof window === "undefined") return DEFAULT_PALETTE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      const legacy = window.localStorage.getItem(LEGACY_DEADWAX_STORAGE_KEY);
      if (legacy === "gold-blue") return DEFAULT_PALETTE;
      return isThemeSelection(legacy) ? legacy : DEFAULT_PALETTE;
    }
    const parsed: unknown = JSON.parse(raw);
    return isThemeSelection(parsed) ? parsed : DEFAULT_PALETTE;
  } catch {
    return DEFAULT_PALETTE;
  }
}

/**
 * Persist the palette. An unknown id clears the preference (reverting to the
 * default) rather than storing garbage. Swallows quota/access errors so a
 * failed write can't break the app.
 */
export function writeThemePalette(palette: ThemeSelection): void {
  if (typeof window === "undefined") return;
  try {
    if (!isThemeSelection(palette) || palette === DEFAULT_PALETTE) {
      window.localStorage.removeItem(STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(palette));
  } catch {
    // localStorage quota or access errors shouldn't break the app.
  }
}

/**
 * Apply the palette to the DOM by setting `data-theme` on the document root.
 * The `[data-theme]` blocks in index.css re-point the color tokens; the default
 * "omni" palette has no block, so it removes the attribute and the base
 * `:root` / `.dark` tokens take over. This is the single source of the DOM
 * side-effect and composes with next-themes' `.dark` class untouched.
 */
export function applyThemePalette(palette: ThemeSelection): void {
  if (typeof document === "undefined") return;
  const next = isThemeSelection(palette) ? palette : DEFAULT_PALETTE;
  if (next === DEFAULT_PALETTE) {
    document.documentElement.removeAttribute("data-theme");
    return;
  }
  document.documentElement.setAttribute("data-theme", next);
}
