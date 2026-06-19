import { PaletteIcon } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useIsEmbedded } from "@/lib/embedded";
import {
  DEADWAX_THEMES,
  type DeadwaxThemeId,
  applyDeadwaxTheme,
  readDeadwaxTheme,
} from "./deadwaxThemes";

/**
 * Sidebar control for picking one of the 7 Deadwax brand themes. Replaces
 * upstream's light/dark/system cycle (Deadwax has no light mode). A palette
 * icon opens a radio menu; selecting a theme retints the whole app instantly
 * via `data-theme` on <html> and persists the choice.
 *
 * @returns Theme picker dropdown.
 */
export function DeadwaxThemeMenu() {
  // Embedded: the host owns the chrome, so a theme switcher would be a no-op.
  const isEmbedded = useIsEmbedded();
  const [theme, setTheme] = useState<DeadwaxThemeId>(() => readDeadwaxTheme());

  if (isEmbedded) return null;

  const onValueChange = (value: string) => {
    const id = value as DeadwaxThemeId;
    setTheme(id);
    applyDeadwaxTheme(id);
  };

  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Theme"
              title="Theme"
              className="rounded-full"
            >
              <PaletteIcon className="size-4" />
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="bottom">Theme</TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="end" className="w-44">
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup value={theme} onValueChange={onValueChange}>
          {DEADWAX_THEMES.map((t) => (
            <DropdownMenuRadioItem key={t.id} value={t.id}>
              {t.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
