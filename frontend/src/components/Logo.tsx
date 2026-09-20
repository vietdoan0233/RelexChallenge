// An original four-petal mark for this app (two navy, two blue leaves meeting at
// the centre). It follows the reference mockups' shape language; it is not a
// wordmark and carries no third-party name.
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <g transform="translate(16 16)">
        <path d="M0 0C-1 -5 -3 -9 -7 -12C-11 -14.5 -14.5 -11.5 -13 -7.5C-11.5 -3.5 -6 -1 0 0Z" style={{ fill: "var(--logo-navy)" }} />
        <path d="M0 0C5 -1 9 -3 12 -7C14.5 -11 11.5 -14.5 7.5 -13C3.5 -11.5 1 -6 0 0Z" fill="#1c86d1" />
        <path d="M0 0C-5 1 -9 3 -12 7C-14.5 11 -11.5 14.5 -7.5 13C-3.5 11.5 -1 6 0 0Z" fill="#1c86d1" />
        <path d="M0 0C1 5 3 9 7 12C11 14.5 14.5 11.5 13 7.5C11.5 3.5 6 1 0 0Z" style={{ fill: "var(--logo-navy)" }} />
      </g>
    </svg>
  )
}

// The EU flag (blue field, ring of twelve stars) used by the privacy badges.
export function EuFlag({ width = 20 }: { width?: number }) {
  const stars = Array.from({ length: 12 }, (_, i) => {
    const a = (i / 12) * Math.PI * 2
    return { x: 15 + Math.sin(a) * 6, y: 10 + -Math.cos(a) * 6 }
  })
  return (
    <svg width={width} height={(width * 20) / 30} viewBox="0 0 30 20" aria-hidden="true" className="shrink-0 rounded-[2px]">
      <rect width="30" height="20" fill="#0b4ea2" />
      {stars.map((s, i) => (
        <circle key={i} cx={s.x} cy={s.y} r="1" fill="#ffd617" />
      ))}
    </svg>
  )
}

// Soft canvas art shared by every page: pale blobs top-left and right, and a
// diagonal dot pattern on the right. Decorative only.
export function PageArt() {
  const dots: { x: number; y: number }[] = []
  for (let row = 0; row < 14; row++) {
    for (let col = 0; col < 16; col++) {
      // Diagonal stripes two dots wide with a two-dot gap, so they read as streaks.
      if ((row + col) % 4 >= 2) continue
      const x = col * 7 + (row % 2) * 3
      const y = row * 7
      if (x + y < 150) dots.push({ x, y })
    }
  }
  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[520px] overflow-hidden" aria-hidden="true">
      <svg className="absolute -left-24 top-[10px] h-[300px] w-[330px]" viewBox="0 0 330 300">
        <defs>
          <linearGradient id="art-l" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="var(--blob)" />
            <stop offset="1" stopColor="var(--blob-2)" />
          </linearGradient>
        </defs>
        <path
          d="M40 10C120 -10 230 20 262 90C290 150 236 190 226 236C216 282 130 300 70 268C10 236 -20 140 6 70C14 44 24 16 40 10Z"
          fill="url(#art-l)"
        />
      </svg>
      <svg className="absolute -right-14 top-[135px] h-[260px] w-[260px]" viewBox="0 0 260 260">
        <defs>
          <linearGradient id="art-r" x1="1" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--blob)" />
            <stop offset="1" stopColor="var(--blob-2)" />
          </linearGradient>
        </defs>
        <path
          d="M60 50C110 -6 210 6 240 70C266 128 248 178 200 222C154 262 90 250 50 206C12 164 6 96 60 50Z"
          fill="url(#art-r)"
        />
        <g fill="var(--dots)" opacity="0.7" transform="translate(70 96) rotate(-38)">
          {dots.map((d, i) => (
            <circle key={i} cx={d.x} cy={d.y} r="1.5" />
          ))}
        </g>
      </svg>
    </div>
  )
}
