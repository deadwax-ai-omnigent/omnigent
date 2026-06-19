import type { ReactNode } from "react";
import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * App-wide theme provider. Deadwax has no light mode — the user picks one of
 * the brand themes via {@link DeadwaxThemeMenu} (applied through
 * `<html data-theme="…">`). next-themes is kept and forced to `dark` only so
 * the `.dark` class is always present: the handful of semantic tokens the
 * Deadwax palette map leaves alone (destructive/status/chart) keep their
 * dark-mode values consistently under every theme.
 *
 * @param children React tree that should inherit theme context.
 * @returns React provider wrapping the app.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      forcedTheme="dark"
      disableTransitionOnChange
      storageKey="ap-web-theme"
    >
      {children}
    </NextThemesProvider>
  );
}
