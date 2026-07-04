import { useRef, useMemo, useState, useEffect, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

// приглушённая палитра (вместо ярких цветов онтологии)
export const MUTED = {
  Publication: '#6b7a90', Experiment: '#b39a63', Material: '#6f9169',
  Process: '#8b7aa0', Equipment: '#a87070', Person: '#6c918d', Conclusion: '#a89a5c',
}

// цвета canvas зависят от темы (CSS-переменные сюда не долетают)
const THEME = {
  dark:  { bg: '#111419', label: 'rgba(232,236,241,0.82)', ring: 'rgba(255,255,255,.75)',
           link: 'rgba(255,255,255,0.1)', linkDim: 'rgba(255,255,255,0.03)' },
  light: { bg: '#eef1f6', label: 'rgba(26,34,48,0.85)', ring: 'rgba(15,23,42,.55)',
           link: 'rgba(15,23,42,0.14)', linkDim: 'rgba(15,23,42,0.04)' },
}

export default function GraphCanvas({ data, focusIds = [], theme = 'dark' }) {
  const fgRef = useRef()
  const wrapRef = useRef()
  const [size, setSize] = useState({ w: 800, h: 440 })
  const [hover, setHover] = useState(null)
  const focus = useMemo(() => new Set(focusIds), [focusIds])
  const tc = THEME[theme] || THEME.dark

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const neighbors = useMemo(() => {
    const m = new Map()
    data.nodes.forEach((n) => m.set(n.id, new Set()))
    data.links.forEach((l) => {
      const s = typeof l.source === 'object' ? l.source.id : l.source
      const t = typeof l.target === 'object' ? l.target.id : l.target
      m.get(s)?.add(t); m.get(t)?.add(s)
    })
    return m
  }, [data])

  useEffect(() => {
    const t = setTimeout(() => fgRef.current?.zoomToFit(500, 50), 400)
    return () => clearTimeout(t)
  }, [data])

  const isDim = useCallback(
    (id) => hover && id !== hover && !neighbors.get(hover)?.has(id),
    [hover, neighbors])

  const drawNode = useCallback((node, ctx, scale) => {
    const r = Math.max(3, Math.min(9, 2.5 + Math.sqrt(node.deg || 1)))
    const dim = isDim(node.id)
    const isFocus = focus.has(node.id)
    const color = MUTED[node.type] || '#7f8794'
    ctx.globalAlpha = dim ? 0.15 : 1
    if (isFocus && !dim) { ctx.shadowColor = color; ctx.shadowBlur = 14 }
    ctx.beginPath(); ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
    ctx.fillStyle = color; ctx.fill(); ctx.shadowBlur = 0
    if (isFocus) {
      ctx.beginPath(); ctx.arc(node.x, node.y, r + 3, 0, 2 * Math.PI)
      ctx.strokeStyle = tc.ring; ctx.lineWidth = 1.3 / scale; ctx.stroke()
    }
    if ((scale > 1.5 || node.id === hover || isFocus) && !dim) {
      const label = node.label.length > 24 ? node.label.slice(0, 23) + '…' : node.label
      ctx.font = `${10.5 / scale}px -apple-system, sans-serif`
      ctx.textAlign = 'center'; ctx.textBaseline = 'top'
      ctx.fillStyle = tc.label
      ctx.fillText(label, node.x, node.y + r + 2)
    }
    ctx.globalAlpha = 1
  }, [isDim, focus, hover, tc])

  return (
    <div style={{ position: 'absolute', inset: 0 }} ref={wrapRef}>
      <ForceGraph2D
        ref={fgRef}
        width={size.w}
        height={size.h}
        graphData={data}
        backgroundColor={tc.bg}
        nodeRelSize={5}
        nodeCanvasObject={drawNode}
        nodePointerAreaPaint={(node, color, ctx) => {
          ctx.fillStyle = color
          ctx.beginPath(); ctx.arc(node.x, node.y, 7, 0, 2 * Math.PI); ctx.fill()
        }}
        nodeLabel={(n) => `<div class="node-tooltip"><b>${n.label}</b><br/>${n.type}</div>`}
        linkColor={(l) => {
          if (l.contradiction) return 'rgba(235,107,115,0.85)'
          const s = typeof l.source === 'object' ? l.source.id : l.source
          const t = typeof l.target === 'object' ? l.target.id : l.target
          if (hover && s !== hover && t !== hover) return tc.linkDim
          return tc.link
        }}
        linkWidth={(l) => (l.contradiction ? 2 : 0.8)}
        linkDirectionalParticles={(l) => (l.contradiction ? 2 : 0)}
        linkDirectionalParticleWidth={1.8}
        linkDirectionalParticleColor={() => '#f0949b'}
        onNodeHover={(n) => setHover(n ? n.id : null)}
        cooldownTicks={110}
        d3VelocityDecay={0.3}
        warmupTicks={20}
      />
    </div>
  )
}
