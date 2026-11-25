import { useId } from "react"

/** The assistant's emblem: a glowing "neural orb" - a core with a spark, three linked nodes that orbit it, a soft pulse. No lettering. */
export function AssistantMark({ className = "h-8 w-8", animated = true }: { className?: string; animated?: boolean }) {
  const id = useId().replace(/:/g, "")
  const spin = animated ? "motion-safe:animate-[spin_14s_linear_infinite]" : ""
  const spinBack = animated ? "motion-safe:animate-[spin_9s_linear_infinite_reverse]" : ""
  const pulse = animated ? "motion-safe:animate-pulse" : ""
  const box = "origin-center [transform-box:fill-box]"
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id={`${id}-core`} cx="38%" cy="32%" r="75%">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="0.35" stopColor="#c4b5fd" />
          <stop offset="1" stopColor="#6366f1" />
        </radialGradient>
        <radialGradient id={`${id}-glow`} cx="50%" cy="50%" r="50%">
          <stop offset="0.55" stopColor="#a78bfa" stopOpacity="0.55" />
          <stop offset="1" stopColor="#a78bfa" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="24" cy="24" r="23" fill={`url(#${id}-glow)`} className={`${pulse} ${box}`} />
      <g className={`${spin} ${box}`}>
        <ellipse cx="24" cy="24" rx="18" ry="7" fill="none" stroke="#e0e7ff" strokeOpacity="0.55" strokeWidth="0.8" transform="rotate(-28 24 24)" />
        <circle cx="40.6" cy="31" r="2.3" fill="#67e8f9" />
        <circle cx="7.4" cy="17" r="1.9" fill="#f0abfc" />
      </g>
      <g className={`${spinBack} ${box}`}>
        <ellipse cx="24" cy="24" rx="15" ry="5.5" fill="none" stroke="#fbcfe8" strokeOpacity="0.5" strokeWidth="0.8" transform="rotate(38 24 24)" />
        <circle cx="35.5" cy="12.5" r="1.7" fill="#fde68a" />
      </g>
      <circle cx="24" cy="24" r="9.5" fill={`url(#${id}-core)`} />
      <path d="M24 16.6 L25.9 22.1 L31.4 24 L25.9 25.9 L24 31.4 L22.1 25.9 L16.6 24 L22.1 22.1 Z" fill="#4f46e5" fillOpacity="0.9" />
      <circle cx="21" cy="20.5" r="1.4" fill="#ffffff" fillOpacity="0.8" />
    </svg>
  )
}
