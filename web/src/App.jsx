import { useState, useEffect, useCallback, useMemo } from 'react'
import GraphCanvas from './GraphCanvas.jsx'
import SearchBar from './SearchBar.jsx'
import Logo from './Logo.jsx'
import HelpButton from './HelpButton.jsx'
import { ExportBar } from './Export.jsx'
import {
  RolePicker, FiltersBar, Answer, SourceStrip, Contradictions, GraphLegend,
} from './Panels.jsx'

const EMPTY = { nodes: [], links: [] }

export default function App() {
  const [meta, setMeta] = useState(null)
  const [role, setRole] = useState('Исследователь')
  const [globalGraph, setGlobalGraph] = useState(EMPTY)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [origin, setOrigin] = useState('Любое')
  const [yearFrom, setYearFrom] = useState(null)
  const [yearTo, setYearTo] = useState(null)
  const [material, setMaterial] = useState('')
  const [activeQuery, setActiveQuery] = useState('')
  const [tab, setTab] = useState('answer')     // answer | contra | graph
  const [graphMode, setGraphMode] = useState('result') // result | global
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')
  const [fast, setFast] = useState(false)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('theme', theme)
  }, [theme])

  useEffect(() => { fetch('/api/meta').then((r) => r.json()).then(setMeta).catch(() => {}) }, [])

  useEffect(() => {
    fetch(`/api/graph?role=${encodeURIComponent(role)}`)
      .then((r) => r.json()).then(setGlobalGraph).catch(() => {})
  }, [role])

  const runSearch = useCallback(async (query, fastArg = fast) => {
    setActiveQuery(query); setLoading(true); setTab('answer')
    try {
      const payload = {
        query, role, top_k: 8, fast: fastArg,
        origin: origin === 'Любое' ? null : origin,
        year_from: yearFrom, year_to: yearTo,
        material: material || null,
      }
      const r = await fetch('/api/search', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      setResult(await r.json())
      setGraphMode('result')
    } catch (e) { console.error(e) } finally { setLoading(false) }
  }, [role, origin, yearFrom, yearTo, material, fast])

  const goHome = () => { setResult(null); setActiveQuery(''); setTab('answer') }
  const inResults = !!(result || loading)

  const canSeeContra = meta?.roles?.[role]?.see_contradictions
  const activeTypes = meta?.roles?.[role]?.types
  const reportsMap = useMemo(
    () => Object.fromEntries((result?.table || []).map((r) => [r.report, r])), [result])
  const graphData = graphMode === 'result' && result?.graph?.nodes?.length ? result.graph : globalGraph
  const focus = graphMode === 'result' ? (result?.focus || []) : []

  const flashSource = (id) => {
    const el = document.getElementById(`src-${id}`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
    el.classList.add('flash'); setTimeout(() => el.classList.remove('flash'), 1200)
  }

  return (
    <div className="app">
      {loading && <div className="loading-bar" />}

      <div className="header">
        <Logo onClick={goHome} />
        <div className="header-right">
          {meta && <RolePicker roles={Object.keys(meta.roles)} role={role} setRole={setRole} />}
          <button className="theme-toggle"
            onClick={() => setTheme((t) => (t === 'light' ? 'dark' : 'light'))}
            title={theme === 'light' ? 'Тёмная тема' : 'Светлая тема'}
            aria-label="Переключить тему">
            {theme === 'light' ? '🌙' : '☀️'}
          </button>
        </div>
      </div>

      <div className={`main ${inResults ? 'results' : 'home'}`}>
        {!inResults ? (
          <div className="hero">
            <h2>Спросите базу знаний R&D</h2>
            <p>Естественно-языковой поиск по отчётам, экспериментам, материалам и процессам</p>
            <SearchBar onSearch={runSearch} loading={loading} examples={meta?.examples || []} />
            <div className="chips">
              {(meta?.examples || []).map((ex) => (
                <button className="chip" key={ex} onClick={() => runSearch(ex)}>{ex}</button>
              ))}
            </div>
          </div>
        ) : (
          <div className="results-top">
            {/* Контекст: что спросили + возврат */}
            <div className="query-head">
              <div className="query-title">{activeQuery}</div>
              <button className="ghost-btn" onClick={goHome}>↺ Новый поиск</button>
            </div>

            <SearchBar onSearch={runSearch} loading={loading} examples={meta?.examples || []}
              placeholder="Задать новый вопрос…" />
            <FiltersBar meta={meta} origin={origin} setOrigin={setOrigin}
              yearFrom={yearFrom} setYearFrom={setYearFrom}
              yearTo={yearTo} setYearTo={setYearTo}
              material={material} setMaterial={setMaterial} />

            {loading || !result ? (
              <div className="skeleton-wrap">
                <div className="skeleton-hint">Анализирую источники в графе знаний…</div>
                <div className="sk-line w95" /><div className="sk-line w80" />
                <div className="sk-line w90" /><div className="sk-line w60" />
                <div className="sk-line w75" />
              </div>
            ) : (
            <>
            {/* Вкладки: ответ / противоречия / граф — по одной за раз */}
            <div className="result-tabs">
              <button className={tab === 'answer' ? 'active' : ''} onClick={() => setTab('answer')}>Ответ</button>
              {canSeeContra && (
                <button className={tab === 'contra' ? 'active' : ''} onClick={() => setTab('contra')}>
                  Противоречия <span className="tcount">{result.contradictions.length}</span>
                </button>
              )}
              <button className={tab === 'graph' ? 'active' : ''} onClick={() => setTab('graph')}>Граф связей</button>
            </div>

            <div className="tab-content">
              {tab === 'answer' && (
                <>
                  {result.meta && (
                    <div className="meta-bar">
                      <span className="mb-item">Источников: <b>{result.meta.sources}</b></span>
                      <span className="mb-item">Уверенность: <b>{result.meta.confidence}</b></span>
                      {result.meta.years && (
                        <span className="mb-item">Актуальность: <b>{result.meta.years[0]}–{result.meta.years[1]}</b></span>
                      )}
                      {result.meta.constraints && (
                        <span className="mb-item">Ограничения: <b>{result.meta.constraints}</b></span>
                      )}
                      {result.meta.cached && <span className="mb-item mb-cache">из кэша</span>}
                      <span className="mb-spacer" />
                      <div className="seg mode-seg">
                        <button className={!fast ? 'active' : ''}
                          onClick={() => { setFast(false); runSearch(activeQuery, false) }}>Точно</button>
                        <button className={fast ? 'active' : ''}
                          onClick={() => { setFast(true); runSearch(activeQuery, true) }}>Быстро</button>
                      </div>
                    </div>
                  )}
                  <ExportBar query={activeQuery} result={result} />
                  <Answer text={result.answer} reports={reportsMap} onCite={flashSource} />
                </>
              )}

              {tab === 'contra' && (
                result.contradictions.length
                  ? <div className="contra-grid"><Contradictions items={result.contradictions} /></div>
                  : <div className="empty-note">Противоречий по запросу не обнаружено.</div>
              )}

              {tab === 'graph' && (
                <div className="card graph-card">
                  <div className="graph-toolbar">
                    <button className={graphMode === 'result' ? 'active' : ''} onClick={() => setGraphMode('result')}>Результат</button>
                    <button className={graphMode === 'global' ? 'active' : ''} onClick={() => setGraphMode('global')}>Весь граф</button>
                  </div>
                  <GraphCanvas data={graphData} focusIds={focus} theme={theme} />
                  {meta && <GraphLegend nodeTypes={meta.nodeTypes} activeTypes={activeTypes} />}
                </div>
              )}
            </div>

            {/* Источники — компактная лента снизу */}
            <div className="src-label">Источники <span className="count">{result.table.length}</span></div>
            <SourceStrip table={result.table} onPick={flashSource} />

            {/* Похожие запросы — всегда есть что нажать дальше */}
            <div className="related">
              <span className="related-label">Похожие запросы</span>
              <div className="chips">
                {(meta?.examples || []).filter((e) => e !== activeQuery).slice(0, 3).map((ex) => (
                  <button className="chip" key={ex} onClick={() => runSearch(ex)}>{ex}</button>
                ))}
              </div>
            </div>
            </>
            )}
          </div>
        )}
      </div>

      <HelpButton meta={meta} />
    </div>
  )
}
