import { useState, useEffect } from 'react'

export default function NavRail({ sections }) {
  const [active, setActive] = useState(sections[0]?.id)

  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => { if (e.isIntersecting) setActive(e.target.id) })
      },
      { rootMargin: '-30% 0px -55% 0px', threshold: 0 },
    )
    sections.forEach((s) => {
      const el = document.getElementById(s.id)
      if (el) obs.observe(el)
    })
    return () => obs.disconnect()
  }, [sections])

  const go = (id) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <nav className="nav-rail">
      {sections.map((s) => (
        <button key={s.id} className={`nav-item ${active === s.id ? 'active' : ''}`}
          onClick={() => go(s.id)}>
          <span className="nav-dot" />
          <span className="nav-label">{s.label}{s.count != null ? ` · ${s.count}` : ''}</span>
        </button>
      ))}
    </nav>
  )
}
