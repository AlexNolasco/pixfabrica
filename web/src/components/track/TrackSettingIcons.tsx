/** Monochrome SVG thumbnails for track layout / transition pickers. */

const frameClass = 'h-full w-full text-foreground'

export function LayoutFillIcon() {
  return (
    <svg viewBox="0 0 48 32" className={frameClass} aria-hidden>
      <rect x="4" y="4" width="40" height="24" rx="2" fill="currentColor" fillOpacity="0.25" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

export function LayoutVerticalIcon() {
  return (
    <svg viewBox="0 0 48 32" className={frameClass} aria-hidden>
      <rect x="4" y="4" width="40" height="7" rx="1" fill="currentColor" fillOpacity="0.35" stroke="currentColor" strokeWidth="1" />
      <rect x="4" y="12.5" width="40" height="7" rx="1" fill="currentColor" fillOpacity="0.55" stroke="currentColor" strokeWidth="1" />
      <rect x="4" y="21" width="40" height="7" rx="1" fill="currentColor" fillOpacity="0.35" stroke="currentColor" strokeWidth="1" />
    </svg>
  )
}

export function LayoutHorizontalIcon() {
  return (
    <svg viewBox="0 0 48 32" className={frameClass} aria-hidden>
      <rect x="4" y="4" width="11" height="24" rx="1" fill="currentColor" fillOpacity="0.35" stroke="currentColor" strokeWidth="1" />
      <rect x="18.5" y="4" width="11" height="24" rx="1" fill="currentColor" fillOpacity="0.55" stroke="currentColor" strokeWidth="1" />
      <rect x="33" y="4" width="11" height="24" rx="1" fill="currentColor" fillOpacity="0.35" stroke="currentColor" strokeWidth="1" />
    </svg>
  )
}

export function TransitionNoneIcon() {
  return (
    <svg viewBox="0 0 48 32" className={frameClass} aria-hidden>
      <rect x="4" y="4" width="40" height="24" rx="2" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="4 3" opacity="0.5" />
      <path d="M14 16h20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.35" />
    </svg>
  )
}

export function TransitionFadeIcon() {
  return (
    <svg viewBox="0 0 48 32" className={`${frameClass} transition-opacity duration-300 group-hover:opacity-55`} aria-hidden>
      <rect x="4" y="4" width="40" height="24" rx="2" fill="currentColor" fillOpacity="0.2" stroke="currentColor" strokeWidth="1.5" />
      <rect x="4" y="4" width="40" height="24" rx="2" fill="currentColor" fillOpacity="0.65" className="transition-opacity duration-300 group-hover:fill-opacity-35" />
    </svg>
  )
}

export function TransitionSlideIcon() {
  return (
    <svg viewBox="0 0 48 32" className={frameClass} aria-hidden>
      <rect x="4" y="4" width="40" height="24" rx="2" fill="currentColor" fillOpacity="0.12" stroke="currentColor" strokeWidth="1.5" />
      <rect
        x="4"
        y="4"
        width="28"
        height="24"
        rx="2"
        fill="currentColor"
        fillOpacity="0.45"
        stroke="currentColor"
        strokeWidth="1.5"
        className="transition-transform duration-300 group-hover:translate-x-2"
      />
    </svg>
  )
}

export function TransitionScaleIcon() {
  return (
    <svg viewBox="0 0 48 32" className={frameClass} aria-hidden>
      <rect x="4" y="4" width="40" height="24" rx="2" fill="currentColor" fillOpacity="0.12" stroke="currentColor" strokeWidth="1.5" />
      <rect
        x="12"
        y="8"
        width="24"
        height="16"
        rx="2"
        fill="currentColor"
        fillOpacity="0.5"
        stroke="currentColor"
        strokeWidth="1.5"
        className="origin-center transition-transform duration-300 group-hover:scale-90"
      />
    </svg>
  )
}

export function TransitionBlurIcon() {
  return (
    <svg viewBox="0 0 48 32" className={frameClass} aria-hidden>
      <rect x="4" y="4" width="40" height="24" rx="2" fill="currentColor" fillOpacity="0.2" stroke="currentColor" strokeWidth="1.5" className="transition-[filter] duration-300 group-hover:blur-[1.5px]" />
      <rect x="10" y="10" width="28" height="12" rx="1" fill="currentColor" fillOpacity="0.55" />
    </svg>
  )
}

export function TransitionWipeIcon() {
  return (
    <svg viewBox="0 0 48 32" className={frameClass} aria-hidden>
      <rect x="4" y="4" width="40" height="24" rx="2" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.5" />
      <rect
        x="4"
        y="4"
        width="22"
        height="24"
        rx="2"
        fill="currentColor"
        fillOpacity="0.5"
        stroke="currentColor"
        strokeWidth="1.5"
        className="transition-[width] duration-300 group-hover:w-[30px]"
      />
    </svg>
  )
}
