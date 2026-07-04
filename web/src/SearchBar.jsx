import { useState, useEffect, useRef, useCallback } from 'react'

const TYPE_COLORS = {
  Material: '#54A24B', Process: '#B279A2', Equipment: '#E45756', Person: '#72B7B2',
}

export default function SearchBar({ onSearch, loading, examples = [], placeholder }) {
  const [value, setValue] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const boxRef = useRef()

  // debounce автодополнения
  useEffect(() => {
    if (!value.trim()) { setSuggestions([]); return }
    const t = setTimeout(async () => {
      try {
        const r = await fetch(`/api/suggest?q=${encodeURIComponent(value)}`)
        const d = await r.json()
        setSuggestions(d.suggestions || [])
      } catch { setSuggestions([]) }
    }, 160)
    return () => clearTimeout(t)
  }, [value])

  // закрытие по клику вне
  useEffect(() => {
    const h = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const submit = useCallback((q) => {
    const query = (q ?? value).trim()
    if (!query) return
    setOpen(false); setActive(-1); setValue('')  // очищаем — строка готова к новому вопросу
    onSearch(query)
  }, [value, onSearch])

  // список для отображения: подсказки-сущности или примеры (когда пусто)
  const showExamples = !value.trim()
  const items = showExamples
    ? examples.map((e) => ({ text: e, kind: 'example' }))
    : suggestions.map((s) => ({ ...s, kind: 'entity' }))

  const onKey = (e) => {
    if (!open) setOpen(true)
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, -1)) }
    else if (e.key === 'Enter') {
      if (active >= 0 && items[active]) submit(items[active].text)
      else submit()
    } else if (e.key === 'Escape') setOpen(false)
  }

  return (
    <div className="searchbar-wrap" ref={boxRef}>
      <div className="searchbar">
        <svg className="icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="7" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          value={value}
          placeholder={placeholder || 'Спросите: извлечение никеля флотацией выше 80%…'}
          onChange={(e) => { setValue(e.target.value); setOpen(true); setActive(-1) }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKey}
        />
        <button className="go" disabled={loading || !value.trim()} onClick={() => submit()}>
          {loading ? '…' : 'Найти'}
        </button>
      </div>

      {open && items.length > 0 && (
        <div className="suggestions">
          <div className="group-label">{showExamples ? 'Примеры запросов' : 'Сущности графа'}</div>
          {items.map((it, i) => (
            <div
              key={i}
              className={`item ${i === active ? 'active' : ''}`}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => { e.preventDefault(); submit(it.text) }}
            >
              {it.kind === 'entity'
                ? <span className="dot" style={{ background: TYPE_COLORS[it.type] || '#888' }} />
                : <span className="icon" style={{ fontSize: 13 }}>✨</span>}
              <span>{it.text}</span>
              {it.kind === 'entity' && <span className="tag">{it.type}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
