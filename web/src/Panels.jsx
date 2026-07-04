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

export function FiltersBar({ meta, origin, setOrigin, ranges, setRanges, open, setOpen }) {
  const params = meta?.numericParams || {}
  const activeCount = Object.values(ranges).filter((r) => r?.enabled).length
  const setRange = (k, patch) => setRanges((p) => ({ ...p, [k]: { ...p[k], ...patch } }))

  return (
    <div>
      <div className="filters-bar">
        <div className="seg">
          {['Любое', 'Отечественная', 'Зарубежная'].map((o) => (
            <button key={o} className={origin === o ? 'active' : ''} onClick={() => setOrigin(o)}>
              {o === 'Любое' ? 'Все практики' : o}
            </button>
          ))}
        </div>
        <button className={`filters-toggle ${open || activeCount ? 'on' : ''}`} onClick={() => setOpen(!open)}>
          ⚙ Числовые фильтры{activeCount ? ` · ${activeCount}` : ''}
        </button>
      </div>

      {open && (
        <div className="numeric-panel">
          {Object.entries(params).map(([k, p]) => {
            const r = ranges[k] || { enabled: false, min: p.min, max: p.max }
            return (
              <div className="numeric-item" key={k}>
                <div className="head">
                  <label className="chk">
                    <input type="checkbox" checked={r.enabled}
                      onChange={(e) => setRange(k, { enabled: e.target.checked, min: p.min, max: p.max })} />
                    {p.name}{p.unit ? `, ${p.unit}` : ''}
                  </label>
                  {r.enabled && <span className="range-val">{r.min}–{r.max}</span>}
                </div>
                {r.enabled && (
                  <>
                    <input type="range" min={p.min} max={p.max} value={r.min}
                      onChange={(e) => setRange(k, { min: Math.min(+e.target.value, r.max) })} />
                    <input type="range" min={p.min} max={p.max} value={r.max}
                      onChange={(e) => setRange(k, { max: Math.max(+e.target.value, r.min) })} />
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function Answer({ text, reports = {}, onCite }) {
  let html = marked.parse(text || '')
  html = html.replace(/\[(R-\d+)\]/g, (m, id) => {
    const r = reports[id]
    const title = r ? `${r.process} · извлечение ${r.recovery ?? '—'}% · ${r.origin}` : ''
    return `<span class="cite" data-rep="${id}" title="${title.replace(/"/g, '')}">[${id}]</span>`
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
            <span className="rep">[{r.report}]</span>
            {r.sentiment && (
              <span className={`pill ${r.sentiment === 'positive' ? 'pos' : 'neg'}`}>
                {r.sentiment === 'positive' ? 'успех' : 'риск'}
              </span>
            )}
          </div>
          <div className="sc-proc">{r.process}</div>
          <div className="sc-meta">извл. {r.recovery ?? '—'}% · {r.origin}</div>
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
