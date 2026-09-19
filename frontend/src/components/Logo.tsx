// An original mark for this app: a stylised receipt whose torn edge doubles as a
// memory trace. Not RELEX's logo -- their mark is their trademark; only their
// public palette, type and shape language are followed.
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="logo-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#80c5ef" />
          <stop offset="1" stopColor="#177abf" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="28" height="28" rx="9" fill="url(#logo-g)" />
      <path
        d="M10 9.5h12M10 14h12M10 18.5h7"
        stroke="#fff"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
      <path d="m19 20.5 2.2 2.2 4-4.4" stroke="#0a3256" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
