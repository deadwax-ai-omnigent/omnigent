import deadwaxSkullMark from "@/assets/deadwax-skull-mark.svg";
import { cn } from "@/lib/utils";

/**
 * The Deadwax skull mascot on a slow, record-like spin. The spin and its
 * reduced-motion gate live in the `.deadwax-skull-spin` rule in index.css.
 */
export function SkullSpinner({
  className,
  decorative = false,
}: {
  className?: string;
  /** Hide from assistive tech when nearby text already names the state. */
  decorative?: boolean;
}) {
  return (
    <img
      src={deadwaxSkullMark}
      alt={decorative ? "" : "Deadwax"}
      aria-hidden={decorative || undefined}
      draggable={false}
      data-testid="skull-spinner"
      className={cn("deadwax-skull-spin select-none", className)}
    />
  );
}
