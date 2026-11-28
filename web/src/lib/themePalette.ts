// Persisted, app-global color-palette preference.
//
// The web UI has two independent appearance axes:
//
//   1. MODE  — light / dark / system, owned by next-themes (toggles the
//      `.dark` class on <html>; see components/theme/ThemeProvider.tsx).
//   2. PALETTE — the color scheme (Deadwax Blue & Gold, Jimi, GitHub, …), owned here.
//
// A palette is applied as a `data-theme` attribute on <html>, so it composes
// with the mode class: `:root:not(.dark)[data-theme="github"]` is GitHub-light
// and `.dark[data-theme="github"]` is GitHub-dark. The default "omni" palette
// carries no data attribute, so selecting it restores the brand look. Everything
// is expressed through the existing CSS custom properties (--background,
// --primary, --sidebar, …), so a palette re-skins the whole app without any
// component knowing a theme changed.
//
// Mirrors lib/uiFontPreferences.ts: a read/write pair backed by localStorage
// plus a single `apply*` function that owns the DOM side-effect, called at boot
// (main.tsx) before first paint and on every change (Appearance settings).

// `.ts` extension (not extensionless like the app's other imports): this module
// is also loaded directly by the `generate-theme-palettes.mjs` node script,
// whose ESM resolver can't do extensionless resolution. tsconfig has
// `allowImportingTsExtensions`, and Vite resolves it the same either way.
import { getThemeRoots } from "./host.ts";

const STORAGE_KEY = "omnigent:ui-theme-palette";
// Where the original Deadwax theme menu stored its choice ("gold-blue" is now "omni").
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
  "solarized",
  "nord",
] as const;

export type ThemePalette = (typeof themePalettes)[number];

/** Built-in palettes plus the user's derived custom configuration. */
export const themeSelections = [...themePalettes, "custom"] as const;
export type ThemeSelection = (typeof themeSelections)[number];

/** Default palette: Deadwax Blue & Gold (kept under the "omni" id for stored preferences). */
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

export interface PaletteTokens {
  background: string;
  foreground: string;
  card: string;
  cardSolid: string;
  cardForeground: string;
  tray: string;
  popover: string;
  popoverForeground: string;
  primary: string;
  link: string;
  primaryForeground: string;
  selectionBackground: string;
  selectionForeground: string;
  codeSelection: string;
  secondary: string;
  secondaryForeground: string;
  muted: string;
  mutedForeground: string;
  codeBackground: string;
  accent: string;
  accentForeground: string;
  border: string;
  borderStrong: string;
  buttonBorder: string;
  input: string;
  ring: string;
  brandAccent: string;
  sidebar: string;
  sidebarForeground: string;
  sidebarPrimary: string;
  sidebarPrimaryForeground: string;
  sidebarAccent: string;
  sidebarAccentForeground: string;
  sidebarBorder: string;
  sidebarRing: string;
  sidebarActive: string;
  sidebarActiveForeground: string;
  sidebarBackground: string;
  shellBackground: string;
}

export const PALETTE_TOKEN_CSS_NAMES = {
  background: "background",
  foreground: "foreground",
  card: "card",
  cardSolid: "card-solid",
  cardForeground: "card-foreground",
  tray: "tray",
  popover: "popover",
  popoverForeground: "popover-foreground",
  primary: "primary",
  link: "link",
  primaryForeground: "primary-foreground",
  selectionBackground: "selection-background",
  selectionForeground: "selection-foreground",
  codeSelection: "code-selection",
  secondary: "secondary",
  secondaryForeground: "secondary-foreground",
  muted: "muted",
  mutedForeground: "muted-foreground",
  codeBackground: "code-bg",
  accent: "accent",
  accentForeground: "accent-foreground",
  border: "border",
  borderStrong: "border-strong",
  buttonBorder: "button-border",
  input: "input",
  ring: "ring",
  brandAccent: "brand-accent",
  sidebar: "sidebar",
  sidebarForeground: "sidebar-foreground",
  sidebarPrimary: "sidebar-primary",
  sidebarPrimaryForeground: "sidebar-primary-foreground",
  sidebarAccent: "sidebar-accent",
  sidebarAccentForeground: "sidebar-accent-foreground",
  sidebarBorder: "sidebar-border",
  sidebarRing: "sidebar-ring",
  sidebarActive: "sidebar-active",
  sidebarActiveForeground: "sidebar-active-foreground",
  sidebarBackground: "sidebar-background",
  shellBackground: "shell-background",
} as const satisfies Record<keyof PaletteTokens, string>;

type PaletteTokenInput = Pick<
  PaletteTokens,
  | "background"
  | "foreground"
  | "card"
  | "cardSolid"
  | "primary"
  | "primaryForeground"
  | "selectionBackground"
  | "secondary"
  | "muted"
  | "mutedForeground"
  | "codeBackground"
  | "accent"
  | "accentForeground"
  | "border"
  | "borderStrong"
  | "ring"
  | "sidebar"
  | "shellBackground"
> &
  Partial<PaletteTokens>;

function paletteTokens(tokens: PaletteTokenInput): PaletteTokens {
  return {
    // Selection is a translucent wash of the palette's accent under the page
    // foreground, never an opaque block. Dark alphas are tuned per accent: a
    // saturated one reads heavy at low alpha, a pastel needs more; light
    // variants use the lightest alpha that stays visible.
    selectionForeground: tokens.foreground,
    // The code viewer paints its selection under the text; palettes whose text wash
    // is too faint there, or too heavy over syntax colours, tune it for code.
    codeSelection: tokens.selectionBackground,
    cardForeground: tokens.foreground,
    tray: tokens.card,
    popover: tokens.cardSolid,
    popoverForeground: tokens.foreground,
    secondaryForeground: tokens.foreground,
    buttonBorder: tokens.border,
    input: tokens.border,
    brandAccent: tokens.ring,
    sidebarForeground: tokens.foreground,
    sidebarPrimary: tokens.ring,
    sidebarPrimaryForeground: tokens.primaryForeground,
    sidebarAccent: tokens.accent,
    sidebarAccentForeground: tokens.accentForeground,
    sidebarBorder: tokens.border,
    sidebarRing: tokens.ring,
    sidebarActive: "color-mix(in srgb, var(--primary) 12%, transparent)",
    sidebarActiveForeground: "var(--primary)",
    sidebarBackground: "var(--sidebar)",
    link: tokens.ring,
    ...tokens,
  };
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
  tokens: {
    light: PaletteTokens;
    dark: PaletteTokens;
  };
}

/** Source colors for the Deadwax presets; each one is a single dark look. */
interface DeadwaxPresetColors {
  bg: string;
  bgSecondary: string;
  surface: string;
  surfaceHover: string;
  card: string;
  text: string;
  textMuted: string;
  textInverse: string;
  accent: string;
  /** Link color, when the accent itself is too dim to read as text. */
  link?: string;
  border: string;
  borderStrong: string;
  /** Selection wash alphas, tuned so each accent stays visible but readable. */
  selectionAlpha?: number;
  codeSelectionAlpha?: number;
  /** Selected-text color, when the body text is too dim over the wash. */
  selectionForeground?: string;
}

function hexToRgba(hex: string, alpha: number): string {
  const [r, g, b] = [1, 3, 5].map((i) => Number.parseInt(hex.slice(i, i + 2), 16));
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// The presets are dark-only, so light mode reuses the dark tokens (with a
// gradient canvas, since only dark mode paints the shell from --background).
function deadwaxPreset(
  id: ThemePalette,
  label: string,
  blurb: string,
  c: DeadwaxPresetColors,
): PaletteMeta {
  const swatch: PaletteSwatch = {
    bg: c.bg,
    card: c.card,
    accent: c.accent,
    border: c.border,
    text: c.text,
  };
  const tokens = (shellBackground: string) =>
    paletteTokens({
      background: c.bg,
      foreground: c.text,
      card: c.card,
      cardSolid: c.card,
      tray: c.bgSecondary,
      popover: c.card,
      primary: c.accent,
      link: c.link ?? c.accent,
      primaryForeground: c.textInverse,
      selectionBackground: hexToRgba(c.accent, c.selectionAlpha ?? 0.3),
      codeSelection: hexToRgba(c.accent, c.codeSelectionAlpha ?? 0.24),
      selectionForeground: c.selectionForeground ?? c.text,
      secondary: c.surface,
      muted: c.surface,
      mutedForeground: c.textMuted,
      codeBackground: c.surface,
      accent: c.surfaceHover,
      accentForeground: c.text,
      border: c.border,
      borderStrong: c.borderStrong,
      ring: c.accent,
      sidebar: c.bgSecondary,
      shellBackground,
    });
  return {
    id,
    label,
    blurb,
    light: swatch,
    dark: swatch,
    tokens: {
      light: tokens(
        `radial-gradient(ellipse at 20% 50%, ${hexToRgba(c.accent, 0.1)} 0%, transparent 50%), linear-gradient(145deg, ${c.bgSecondary} 0%, ${c.bg} 50%, ${c.bgSecondary} 100%)`,
      ),
      dark: tokens("var(--background)"),
    },
  };
}

const DEADWAX_PRESETS: readonly PaletteMeta[] = [
  deadwaxPreset("purple", "Gurple Purple", "Deep violet with an electric-purple accent.", {
    bg: "#0e0914",
    bgSecondary: "#170c21",
    surface: "#221130",
    surfaceHover: "#2a153c",
    card: "#1a1025",
    text: "#f3eaff",
    textMuted: "#bca9d9",
    textInverse: "#ffffff",
    accent: "#8b2eff",
    link: "#b57bff",
    border: "#34184d",
    borderStrong: "#5f4280",
  }),
  deadwaxPreset("jimi", "Jimi", "Purple haze with a vivid magenta lead.", {
    bg: "#160c1c",
    bgSecondary: "#201228",
    surface: "#2f1a3a",
    surfaceHover: "#3a2048",
    card: "#24142d",
    text: "#f6eafc",
    textMuted: "#c4aad3",
    textInverse: "#ffffff",
    accent: "#c62cb8",
    link: "#e070d6",
    border: "#3a2048",
    borderStrong: "#643e7a",
  }),
  deadwaxPreset("record-store", "Record Store", "Warm black vinyl with a worn-gold accent.", {
    bg: "#0c0d0b",
    bgSecondary: "#171815",
    surface: "#22231e",
    surfaceHover: "#2a2b25",
    card: "#1b1b18",
    text: "#f3efe4",
    textMuted: "#b9b2a3",
    textInverse: "#0c0d0b",
    accent: "#d9a441",
    border: "#303126",
    borderStrong: "#505247",
  }),
  deadwaxPreset("red-black", "Kill 'Em", "Near-black surfaces cut with signal red.", {
    bg: "#090405",
    bgSecondary: "#160709",
    surface: "#231013",
    surfaceHover: "#301318",
    card: "#170a0c",
    text: "#f6edee",
    textMuted: "#c7a8ac",
    textInverse: "#090405",
    accent: "#d72638",
    link: "#ef5a68",
    border: "#3a0d11",
    borderStrong: "#573139",
  }),
  deadwaxPreset("hornet", "Nikki", "Black, red, and gold with hornet energy.", {
    bg: "#000000",
    bgSecondary: "#090909",
    surface: "#121212",
    surfaceHover: "#191919",
    card: "#0d0d0d",
    text: "#d6a84f",
    textMuted: "#d71920",
    textInverse: "#000000",
    accent: "#d71920",
    link: "#d6a84f",
    codeSelectionAlpha: 0.3,
    border: "#1b1b1b",
    borderStrong: "#3a3935",
  }),
  deadwaxPreset("billie", "Billie", "Midnight navy lit by acid green.", {
    bg: "#071426",
    bgSecondary: "#0b1d35",
    surface: "#102a4f",
    surfaceHover: "#143460",
    card: "#0b203c",
    text: "#eaf3ff",
    textMuted: "#a6bedc",
    textInverse: "#071426",
    accent: "#a6ff00",
    selectionAlpha: 0.22,
    codeSelectionAlpha: 0.16,
    border: "#153b70",
    borderStrong: "#2e4d73",
  }),
  deadwaxPreset("ye", "Ye", "Severe monochrome in near-black graphite.", {
    bg: "#000000",
    bgSecondary: "#050505",
    surface: "#0b0b0b",
    surfaceHover: "#101010",
    card: "#070707",
    text: "#6a6a6a",
    textMuted: "#4a4a4a",
    textInverse: "#000000",
    accent: "#5a5a5a",
    link: "#8a8a8a",
    selectionAlpha: 0.4,
    codeSelectionAlpha: 0.4,
    selectionForeground: "#b0b0b0",
    border: "#141414",
    borderStrong: "#3a3a3a",
  }),
];

// Swatch colors are a hand-picked summary used for mini-previews.
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
    tokens: {
      light: paletteTokens({
        background: "#ffffff",
        foreground: "#11171c",
        card: "#ffffff",
        cardSolid: "#ffffff",
        popoverForeground: "#11171c",
        // Amber Glow is too light for text and white labels on a light canvas,
        // so light mode leads with a deeper cut of the same gold.
        primary: "#8a5d1a",
        link: "#2a66a0",
        primaryForeground: "#ffffff",
        selectionBackground: "rgba(138, 93, 26, 0.14)",
        codeSelection: "rgba(138, 93, 26, 0.2)",
        selectionForeground: "#5c4520",
        secondary: "#eceef1",
        muted: "#0000000f",
        mutedForeground: "#71717a",
        codeBackground: "#0000000f",
        accent: "#f2f1f2",
        accentForeground: "#11171c",
        border: "#e8ecf0",
        borderStrong: "#a1a1aa",
        buttonBorder: "#d6d6d6",
        input: "#e8ecf0",
        ring: "#edb978",
        brandAccent: "#edb978",
        sidebar: "#fdfafa",
        sidebarPrimary: "#edb978",
        sidebarPrimaryForeground: "#11171c",
        sidebarBackground: "linear-gradient(to right, #fffefe, #fdfaf4)",
        shellBackground:
          "radial-gradient(ellipse at 20% 50%, rgb(237 185 120 / 8%) 0%, transparent 50%), linear-gradient(145deg, #fffdfa 0%, #fdfafa 52%, #f8f4ee 100%)",
      }),
      dark: paletteTokens({
        background: "#111318",
        foreground: "#ece8e1",
        card: "rgba(29, 32, 40, 0.72)",
        cardSolid: "#1d2028",
        tray: "rgba(26, 29, 36, 0.78)",
        popover: "rgba(29, 32, 40, 0.94)",
        primary: "#edb978",
        link: "#5b9bd5",
        primaryForeground: "#111318",
        selectionBackground: "rgba(237, 185, 120, 0.18)",
        codeSelection: "rgba(237, 185, 120, 0.2)",
        selectionForeground: "#f6dcb5",
        secondary: "#22262f",
        secondaryForeground: "#ece8e1",
        muted: "#22262f",
        mutedForeground: "#9ba3b2",
        codeBackground: "#22262f",
        accent: "#2a2f3a",
        accentForeground: "#ece8e1",
        border: "#2a2f3a",
        borderStrong: "#3d434d",
        buttonBorder: "#2a2f3a",
        input: "rgb(255 255 255 / 15%)",
        ring: "#edb978",
        brandAccent: "#edb978",
        sidebar: "#111318",
        sidebarPrimary: "#edb978",
        sidebarPrimaryForeground: "#11171c",
        sidebarAccent: "#2a2f3a",
        sidebarAccentForeground: "#ece8e1",
        sidebarBorder: "#2a2f3a",
        sidebarRing: "#edb978",
        sidebarBackground:
          "linear-gradient(transparent 35%, rgba(237, 185, 120, 0.08)), linear-gradient(135deg, rgba(255, 255, 255, 0.04), transparent 60%)",
        shellBackground: "var(--background)",
      }),
    },
  },
  ...DEADWAX_PRESETS,
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
    tokens: {
      light: paletteTokens({
        background: "#f7f5fd",
        selectionBackground: "rgba(124, 58, 237, 0.15)",
        foreground: "#1e1a2b",
        card: "#ffffff",
        cardSolid: "#ffffff",
        primary: "#7c3aed",
        primaryForeground: "#ffffff",
        secondary: "#efeaf9",
        muted: "#efeaf9",
        mutedForeground: "#6b6786",
        codeBackground: "#efeaf9",
        accent: "#f3e8ff",
        accentForeground: "#6b21a8",
        border: "#e6e0f2",
        borderStrong: "#b6abd6",
        ring: "#7c3aed",
        brandAccent: "#d6409f",
        sidebar: "#f3f0fa",
        shellBackground: "linear-gradient(160deg, #faf8ff 0%, #f5f1fd 50%, #f3eefb 100%)",
      }),
      dark: paletteTokens({
        background: "#282a36",
        selectionBackground: "rgba(189, 147, 249, 0.33)",
        codeSelection: "rgba(189, 147, 249, 0.26)",
        foreground: "#f8f8f2",
        card: "rgba(68, 71, 90, 0.5)",
        cardSolid: "#343746",
        popover: "rgba(33, 34, 44, 0.92)",
        primary: "#bd93f9",
        link: "#be95f9",
        primaryForeground: "#282a36",
        secondary: "#343746",
        muted: "#3b3d4d",
        mutedForeground: "#b3b8d4",
        codeBackground: "#21222c",
        accent: "#3b304f",
        accentForeground: "#ff79c6",
        border: "#44475a",
        borderStrong: "#5a5d75",
        ring: "#bd93f9",
        brandAccent: "#ff79c6",
        sidebar: "rgba(33, 34, 44, 0.8)",
        shellBackground: "var(--background)",
      }),
    },
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
    tokens: {
      light: paletteTokens({
        background: "#f6f8fa",
        selectionBackground: "rgba(9, 105, 218, 0.15)",
        foreground: "#1f2328",
        card: "#ffffff",
        cardSolid: "#ffffff",
        primary: "#0969da",
        link: "#0968d9",
        primaryForeground: "#ffffff",
        secondary: "#eaeef2",
        muted: "#eaeef2",
        mutedForeground: "#59636e",
        codeBackground: "#eff1f3",
        accent: "#ddf4ff",
        accentForeground: "#0550ae",
        border: "#d1d9e0",
        borderStrong: "#afb8c1",
        ring: "#0969da",
        sidebar: "#f6f8fa",
        shellBackground: "linear-gradient(180deg, #fbfcfd 0%, #f6f8fa 100%)",
      }),
      dark: paletteTokens({
        background: "#0d1117",
        selectionBackground: "rgba(88, 166, 255, 0.39)",
        codeSelection: "rgba(88, 166, 255, 0.24)",
        foreground: "#e6edf3",
        card: "rgba(22, 27, 34, 0.72)",
        cardSolid: "#161b22",
        popover: "rgba(22, 27, 34, 0.9)",
        primary: "#58a6ff",
        primaryForeground: "#0d1117",
        secondary: "#21262d",
        muted: "#21262d",
        mutedForeground: "#8b949e",
        codeBackground: "#1c2128",
        accent: "#121d2f",
        accentForeground: "#58a6ff",
        border: "#30363d",
        borderStrong: "#444c56",
        ring: "#58a6ff",
        sidebar: "rgba(13, 17, 23, 0.75)",
        sidebarPrimaryForeground: "#0d1117",
        shellBackground: "var(--background)",
      }),
    },
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
    tokens: {
      light: paletteTokens({
        background: "#eff1f5",
        selectionBackground: "rgba(136, 57, 239, 0.15)",
        foreground: "#4c4f69",
        card: "#ffffff",
        cardSolid: "#ffffff",
        primary: "#8839ef",
        link: "#8739ec",
        primaryForeground: "#ffffff",
        secondary: "#e6e9ef",
        muted: "#e6e9ef",
        mutedForeground: "#6c6f85",
        codeBackground: "#e6e9ef",
        accent: "#ccd0da",
        accentForeground: "#8839ef",
        border: "#ccd0da",
        borderStrong: "#acb0be",
        ring: "#8839ef",
        brandAccent: "#ea76cb",
        sidebar: "#e6e9ef",
        shellBackground: "linear-gradient(160deg, #f2f3f7 0%, #eff1f5 60%, #e9ecf2 100%)",
      }),
      dark: paletteTokens({
        background: "#1e1e2e",
        // The body text sits at the 4.5:1 edge over the wash; rosewater is the
        // lightest Catppuccin text.
        selectionBackground: "rgba(203, 166, 247, 0.26)",
        codeSelection: "rgba(203, 166, 247, 0.16)",
        selectionForeground: "#f5e0dc",
        foreground: "#cdd6f4",
        card: "rgba(49, 50, 68, 0.6)",
        cardSolid: "#282938",
        popover: "rgba(24, 24, 37, 0.92)",
        primary: "#cba6f7",
        primaryForeground: "#1e1e2e",
        secondary: "#313244",
        muted: "#313244",
        mutedForeground: "#a6adc8",
        codeBackground: "#181825",
        accent: "#45475a",
        accentForeground: "#cba6f7",
        border: "#45475a",
        borderStrong: "#585b70",
        ring: "#cba6f7",
        sidebar: "rgba(24, 24, 37, 0.8)",
        shellBackground: "var(--background)",
      }),
    },
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
    tokens: {
      light: paletteTokens({
        background: "#fbf1c7",
        selectionBackground: "rgba(214, 93, 14, 0.18)",
        foreground: "#3c3836",
        card: "#fffdf2",
        cardSolid: "#fffdf2",
        primary: "#d65d0e",
        link: "#9d360a",
        primaryForeground: "#ffffff",
        secondary: "#ebdbb2",
        muted: "#ebdbb2",
        mutedForeground: "#7c6f64",
        codeBackground: "#ebdbb2",
        accent: "#f2e5bc",
        accentForeground: "#af3a03",
        border: "#e6d5a8",
        borderStrong: "#bdae93",
        ring: "#d65d0e",
        sidebar: "#f4e8bc",
        shellBackground: "linear-gradient(160deg, #fbf3cd 0%, #fbf1c7 55%, #f7ecbb 100%)",
      }),
      dark: paletteTokens({
        background: "#282828",
        selectionBackground: "rgba(254, 128, 25, 0.34)",
        codeSelection: "rgba(254, 128, 25, 0.24)",
        foreground: "#ebdbb2",
        card: "rgba(60, 56, 54, 0.6)",
        cardSolid: "#32302f",
        popover: "rgba(29, 32, 33, 0.92)",
        primary: "#fe8019",
        primaryForeground: "#282828",
        secondary: "#3c3836",
        muted: "#3c3836",
        mutedForeground: "#a89984",
        codeBackground: "#1d2021",
        accent: "#504945",
        accentForeground: "#fe8019",
        border: "#504945",
        borderStrong: "#665c54",
        ring: "#fe8019",
        sidebar: "rgba(29, 32, 33, 0.8)",
        shellBackground: "var(--background)",
      }),
    },
  },
  {
    id: "solarized",
    label: "Solarized",
    blurb: "Precision colors in Solarized Light & Dark.",
    light: {
      bg: "#fdf6e3",
      card: "#eee8d5",
      accent: "#268bd2",
      border: "#c1c5bb",
      text: "#657b83",
    },
    dark: {
      bg: "#002b36",
      card: "#073642",
      accent: "#268bd2",
      border: "#304f5c",
      text: "#839496",
    },
    tokens: {
      light: paletteTokens({
        background: "#fdf6e3",
        selectionBackground: "rgba(38, 139, 210, 0.15)",
        codeSelection: "rgba(38, 139, 210, 0.16)",
        // base02: the body text (base00) is too light over the wash.
        selectionForeground: "#073642",
        foreground: "#657b83",
        card: "#eee8d5",
        cardSolid: "#eee8d5",
        primary: "#268bd2",
        link: "#026287",
        primaryForeground: "#fdf6e3",
        secondary: "#eee8d5",
        // Keep interactive rows visible over the base2 popover surface.
        muted: "#d6d4c6",
        mutedForeground: "#586e75",
        codeBackground: "#eee8d5",
        accent: "#eee8d5",
        accentForeground: "#268bd2",
        border: "#c1c5bb",
        borderStrong: "#aeb6af",
        ring: "#268bd2",
        brandAccent: "#6c71c4",
        sidebar: "#eee8d5",
        shellBackground: "#fdf6e3",
      }),
      dark: paletteTokens({
        background: "#002b36",
        selectionBackground: "rgba(38, 139, 210, 0.42)",
        codeSelection: "rgba(38, 139, 210, 0.26)",
        // base2, for the same reason as light mode.
        selectionForeground: "#eee8d5",
        foreground: "#839496",
        card: "#073642",
        cardSolid: "#073642",
        popover: "#073642",
        primary: "#268bd2",
        link: "#6ab8d0",
        primaryForeground: "#fdf6e3",
        secondary: "#073642",
        // Keep interactive rows visible over the base02 popover surface.
        muted: "#1d474f",
        mutedForeground: "#93a1a1",
        codeBackground: "#073642",
        accent: "#073642",
        accentForeground: "#2aa198",
        border: "#304f5c",
        borderStrong: "#3f5f69",
        ring: "#268bd2",
        brandAccent: "#6c71c4",
        sidebar: "#073642",
        sidebarPrimaryForeground: "#fdf6e3",
        shellBackground: "var(--background)",
      }),
    },
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
    tokens: {
      light: paletteTokens({
        background: "#eceff4",
        selectionBackground: "rgba(94, 129, 172, 0.25)",
        foreground: "#2e3440",
        card: "#e5e9f0",
        cardSolid: "#e5e9f0",
        primary: "#5e81ac",
        link: "#355e86",
        primaryForeground: "#eceff4",
        secondary: "#d8dee9",
        muted: "#d8dee9",
        mutedForeground: "#4c566a",
        codeBackground: "#d8dee9",
        accent: "#e5e9f0",
        accentForeground: "#5e81ac",
        border: "#d8dee9",
        borderStrong: "#81a1c1",
        ring: "#5e81ac",
        sidebar: "#e5e9f0",
        sidebarAccent: "#d8dee9",
        shellBackground: "linear-gradient(160deg, #eceff4 0%, #e5e9f0 55%, #d8dee9 100%)",
      }),
      dark: paletteTokens({
        background: "#2e3440",
        // The body text, already the lightest Nord colour, only stays at 4.5:1
        // over the muted surface up to here.
        selectionBackground: "rgba(136, 192, 208, 0.25)",
        codeSelection: "rgba(136, 192, 208, 0.19)",
        foreground: "#eceff4",
        card: "rgba(59, 66, 82, 0.6)",
        cardSolid: "#3b4252",
        popover: "rgba(46, 52, 64, 0.92)",
        primary: "#88c0d0",
        link: "#8fc4d3",
        primaryForeground: "#2e3440",
        secondary: "#3b4252",
        muted: "#434c5e",
        mutedForeground: "#d8dee9",
        codeBackground: "#3b4252",
        accent: "#434c5e",
        accentForeground: "#88c0d0",
        border: "#4c566a",
        borderStrong: "#81a1c1",
        ring: "#88c0d0",
        sidebar: "rgba(46, 52, 64, 0.8)",
        shellBackground: "var(--background)",
      }),
    },
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
 * Apply the palette to the DOM by setting `data-theme` on the theme roots.
 * The generated `[data-theme]` blocks re-point the color tokens; the default
 * "omni" palette removes the attribute. This composes with the `.dark` mode
 * class untouched.
 *
 * Embedded, `getThemeRoots()` returns both the scope root (matched by the light
 * `:root[data-theme]` selectors) and the inner `.dark` root (matched by the
 * dark `.dark[data-theme]` selectors); standalone it's just the document root,
 * so behavior is unchanged.
 */
export function applyThemePalette(palette: ThemeSelection): void {
  const roots = getThemeRoots();
  if (roots.length === 0) return;
  const next = isThemeSelection(palette) ? palette : DEFAULT_PALETTE;
  for (const root of roots) {
    if (next === DEFAULT_PALETTE) {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", next);
    }
  }
}
