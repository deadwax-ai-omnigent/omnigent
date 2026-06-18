interface SkullSpinnerProps {
  className?: string;
}

/**
 * Deadwax skull mark with a gentle, record-like spin — the Deadwax mascot,
 * standing in for the upstream Otto eyes. The spin + reduced-motion handling
 * live in the `.deadwax-skull-spin` rule in index.css.
 */
export function SkullSpinner({ className }: SkullSpinnerProps) {
  return (
    <img
      src="/skull-mark.svg"
      alt="Deadwax"
      draggable={false}
      className={`deadwax-skull-spin select-none ${className ?? ""}`}
    />
  );
}
