import { marked } from 'marked'
import { MUTED } from './GraphCanvas.jsx'

marked.setOptions({ breaks: true })

export function RolePicker({ roles, role, setRole }) {
  return (
    <div className="role-picker">
      {roles.map((r) => (
        <button key={r} className={r === role ? 'active' : ''} onClick={() => setRole(r)}>{r}</button>
      ))}
    </div>
  )
}

export function FiltersBar({ meta, origin, setOrigin, yearFrom, setYearFrom,
  yearTo, setYearTo, material, setMaterial }) {
  const yr = meta?.yearRange || [1990, 2025]
  const materials = meta?.facetMaterials || []
  return (
    <div className="filters-bar">
      <div className="seg">
        {['Любое', 'Отечественная', 'Зарубежная'].map((o) => (
          <button key={o} className={origin === o ? 'active' : ''} onClick={() => setOrigin(o)}>
            {o === 'Любое' ? 'Все практики' : o}
          </button>
        ))}
      </div>

      <div className="facet year-facet">
        <span className="facet-label">Год</span>
        <input type="number" placeholder={yr[0]} value={yearFrom ?? ''} min={yr[0]} max={yr[1]}
          onChange={(e) => setYearFrom(e.target.value ? +e.target.value : null)} />
        <span className="dash">–</span>
        <input type="number" placeholder={yr[1]} value={yearTo ?? ''} min={yr[0]} max={yr[1]}
          onChange={(e) => setYearTo(e.target.value ? +e.target.value : null)} />
      </div>

      <select className="facet material-facet" value={material}
        onChange={(e) => setMaterial(e.target.value)}>
        <option value="">Любой материал</option>
        {materials.map((m) => <option key={m} value={m}>{m}</option>)}
      </select>
    </div>
  )
}

export function Answer({ text, reports = {}, onCite }) {
  let html = marked.parse(text || '')
  html = html.replace(/\[([RD]-\d+)\]/g, (m, id) => {
    const r = reports[id]
    const tip = r ? `${r.filename || r.title || ''} · ${r.category || ''} · ${r.origin || ''}` : ''
    return `<span class="cite" data-rep="${id}" title="${tip.replace(/"/g, '')}">[${id}]</span>`
  })
  return (
    <div className="answer"
      onClick={(e) => { const id = e.target?.dataset?.rep; if (id) onCite?.(id) }}
      dangerouslySetInnerHTML={{ __html: html }} />
  )
}

export function SourceStrip({ table, onPick }) {
  return (
    <div className="source-strip">
      {table.map((r, i) => (
        <div className="source-card" id={`src-${r.report}`} key={i} onClick={() => onPick?.(r.report)}>
          <div className="sc-top">
            {r.category && <span className="pill cat">{r.category}</span>}
            {r.year && <span className="sc-year">{r.year}</span>}
          </div>
          <a className="sc-name" href={r.url} target="_blank" rel="noreferrer"
            title={r.filename || r.title} onClick={(e) => e.stopPropagation()}>
            {r.filename || r.title || r.report}
          </a>
          <div className="sc-meta">{r.origin}{r.snippet ? ` · ${r.snippet.slice(0, 60)}…` : ''}</div>
          {r.facts?.length > 0 && (
            <div className="sc-facts">
              {r.facts.slice(0, 4).map((f, k) => <span className="fact" key={k}>{f}</span>)}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export function Reports({ table }) {
  return (
    <>
      {table.map((r, i) => (
        <div className="report" key={i}>
          <div className="top">
            <span className="rep">[{r.report}]</span>
            <span className="score">score {r.score}</span>
          </div>
          <div className="meta">
            {r.process} · {(r.materials || []).join(', ')}
            {r.sentiment && (
              <span className={`pill ${r.sentiment === 'positive' ? 'pos' : 'neg'}`}>
                {r.sentiment === 'positive' ? 'успех' : 'риск'}
              </span>
            )}
          </div>
          <div className="meta">
            извлечение {r.recovery ?? '—'}% · t {r.temperature ?? '—'}°C · {r.origin}
          </div>
        </div>
      ))}
    </>
  )
}

export function Contradictions({ items }) {
  if (!items.length) return <div className="empty-note">Противоречий по запросу не обнаружено.</div>
  return (
    <>
      {items.map((c, i) => (
        <div className="contra" key={i}>
          <div className="h">{c.material} · {c.process} — Δ извлечения {Math.round(c.recovery_gap)} п.п.</div>
          <div className="pair">
            <div className="a"><b>[{c.a_id}]</b> {c.a}</div>
            <div className="b"><b>[{c.b_id}]</b> {c.b}</div>
          </div>
        </div>
      ))}
    </>
  )
}

export function GraphLegend({ nodeTypes, activeTypes }) {
  return (
    <div className="graph-legend">
      {Object.entries(nodeTypes || {})
        .filter(([t]) => !activeTypes || activeTypes.includes(t))
        .map(([t, v]) => (
          <div className="li" key={t}>
            <span className="dot" style={{ background: MUTED[t] || '#7f8794' }} />{v.label}
          </div>
        ))}
      <div className="li"><span className="dot" style={{ background: '#eb6b73' }} />противоречие</div>
    </div>
  )
}
