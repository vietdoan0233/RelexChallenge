import { useEffect, useRef } from 'react'
// particles.js is a sloppy-mode classic script (it uses arguments.callee), so it cannot be
// bundled as an ES module. Vite serves it as a plain asset and it is loaded with a <script> tag.
import particlesUrl from 'particles.js/particles.js?url'

interface PJSInstance {
  pJS: { fn: { vendors: { destroypJS: () => void } } }
}
declare global {
  interface Window {
    particlesJS?: (tagId: string, params: unknown) => void
    pJSDom?: PJSInstance[] | null
  }
}

const TAG_ID = 'hero-particles'

let loading: Promise<void> | null = null
function loadParticles(): Promise<void> {
  if (window.particlesJS) return Promise.resolve()
  loading ??= new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = particlesUrl
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => {
      loading = null
      reject(new Error('particles.js failed to load'))
    }
    document.head.appendChild(script)
  })
  return loading
}

// White-and-blue palette to match the theme; kept faint so text stays readable.
const CONFIG = {
  particles: {
    number: { value: 90, density: { enable: true, value_area: 900 } },
    color: { value: '#1772b8' },
    shape: { type: 'circle' },
    opacity: { value: 0.5, random: true },
    size: { value: 3.5, random: true },
    line_linked: { enable: true, distance: 150, color: '#5aa3dc', opacity: 0.34, width: 1 },
    move: { enable: true, speed: 1.1, direction: 'none', random: false, straight: false, out_mode: 'out', bounce: false },
  },
  interactivity: {
    // "canvas" because the canvas is not hit-testable (it sits behind the hero);
    // pointer events are forwarded to it by hand below.
    detect_on: 'canvas',
    events: { onhover: { enable: true, mode: 'grab' }, onclick: { enable: true, mode: 'push' }, resize: true },
    modes: { grab: { distance: 170, line_linked: { opacity: 0.6 } }, push: { particles_nb: 3 } },
  },
  retina_detect: true,
}

/** An interactive particle field behind the Ask hero. Decorative only: it never takes
 *  pointer events itself, is hidden from assistive tech, and is skipped entirely for
 *  visitors who ask their system for reduced motion. */
export function ParticlesBackground() {
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const host = box.current
    if (!host) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    let cancelled = false
    let cleanup: (() => void) | undefined

    loadParticles()
      .then(() => {
        if (cancelled || !window.particlesJS) return
        window.pJSDom = []
        window.particlesJS(TAG_ID, CONFIG)
        const canvas = host.querySelector<HTMLCanvasElement>('canvas')

        // The hero text sits above the canvas, so mirror the pointer onto it.
        const forward = (type: string, e: MouseEvent) =>
          canvas?.dispatchEvent(new MouseEvent(type, { clientX: e.clientX, clientY: e.clientY }))
        const inside = (e: MouseEvent) => {
          const r = host.getBoundingClientRect()
          return e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom
        }
        const onMove = (e: MouseEvent) => forward(inside(e) ? 'mousemove' : 'mouseleave', e)
        const onLeave = (e: MouseEvent) => forward('mouseleave', e)
        const onClick = (e: MouseEvent) => {
          // Clicks on real controls must not also spawn particles.
          const onControl = e.target instanceof Element && e.target.closest('a, button, input, textarea, label')
          if (inside(e) && !onControl) forward('click', e)
        }
        window.addEventListener('mousemove', onMove)
        window.addEventListener('click', onClick)
        document.addEventListener('mouseleave', onLeave)

        cleanup = () => {
          window.removeEventListener('mousemove', onMove)
          window.removeEventListener('click', onClick)
          document.removeEventListener('mouseleave', onLeave)
          window.pJSDom?.forEach((p) => p.pJS.fn.vendors.destroypJS())
          // destroypJS nulls the registry; the next mount (StrictMode remounts) needs an array.
          window.pJSDom = []
        }
      })
      .catch(() => {
        /* Decorative only: without the script the hero simply has no particles. */
      })

    return () => {
      cancelled = true
      cleanup?.()
    }
  }, [])

  return (
    <div
      id={TAG_ID}
      ref={box}
      aria-hidden="true"
      className="pointer-events-none absolute inset-x-0 top-0 -z-[5] h-[440px] [&>canvas]:size-full [mask-image:linear-gradient(to_bottom,black_60%,transparent)]"
    />
  )
}
