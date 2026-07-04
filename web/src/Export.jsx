// Экспорт ответа с источниками в Markdown / JSON-LD / PDF (печать браузера).
// Всё на клиенте: результат уже есть, кириллица в PDF идёт через print().

function download(name, text, mime) {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = name
  document.body.appendChild(a); a.click()
  document.body.removeChild(a); URL.revokeObjectURL(url)
}

const abs = (u) => (u?.startsWith('http') ? u : window.location.origin + (u || ''))

function toMarkdown(query, result) {
  const m = result.meta || {}
  const lines = [`# ${query}`, '', result.answer || '', '', '## Источники', '']
  ;(result.table || []).forEach((r, i) => {
    lines.push(`${i + 1}. **${r.filename || r.title || r.report}** — ${r.category || ''}` +
      `${r.year ? `, ${r.year}` : ''}${r.origin ? `, ${r.origin}` : ''} — [оригинал](${abs(r.url)})`)
    if (r.facts?.length) lines.push(`   - Факты: ${r.facts.join('; ')}`)
  })
  lines.push('', `---`, `_Уверенность: ${m.confidence || '—'} · источников: ${m.sources ?? '—'}` +
    `${m.years ? ` · актуальность: ${m.years[0]}–${m.years[1]}` : ''}` +
    `${m.constraints ? ` · ограничения: ${m.constraints}` : ''}_`)
  return lines.join('\n')
}

function toJsonLd(query, result) {
  const m = result.meta || {}
  return JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'Dataset',
    name: query,
    description: (result.answer || '').slice(0, 500),
    text: result.answer || '',
    creativeWorkStatus: `confidence:${m.confidence || 'unknown'}`,
    temporalCoverage: m.years ? `${m.years[0]}/${m.years[1]}` : undefined,
    citation: (result.table || []).map((r) => ({
      '@type': 'CreativeWork',
      identifier: r.report,
      name: r.filename || r.title,
      genre: r.category,
      inLanguage: r.origin === 'Зарубежная' ? 'en' : 'ru',
      datePublished: r.year || undefined,
      url: abs(r.url),
      ...(r.facts?.length ? { measurementTechnique: r.facts } : {}),
    })),
  }, null, 2)
}

function printPdf(query, result) {
  const rows = (result.table || []).map((r, i) =>
    `<li><b>${r.filename || r.title || r.report}</b> — ${r.category || ''}${r.year ? `, ${r.year}` : ''}` +
    `${r.origin ? `, ${r.origin}` : ''}${r.facts?.length ? ` <i>[${r.facts.join('; ')}]</i>` : ''}</li>`).join('')
  const answerHtml = (result.answer || '').replace(/\n/g, '<br>')
  const w = window.open('', '_blank')
  if (!w) return
  w.document.write(`<!doctype html><html lang="ru"><head><meta charset="utf-8">
    <title>${query}</title><style>
    body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:760px;margin:32px auto;
      padding:0 20px;color:#111;line-height:1.6;font-size:14px}
    h1{font-size:20px} h2{font-size:15px;margin-top:24px} li{margin:5px 0}
    .meta{color:#555;font-size:12px;border-top:1px solid #ddd;margin-top:24px;padding-top:10px}
    </style></head><body>
    <h1>${query}</h1><div>${answerHtml}</div>
    <h2>Источники</h2><ol>${rows}</ol>
    <div class="meta">Уверенность: ${result.meta?.confidence || '—'} · источников: ${result.meta?.sources ?? '—'}
    ${result.meta?.years ? ` · актуальность: ${result.meta.years[0]}–${result.meta.years[1]}` : ''}</div>
    </body></html>`)
  w.document.close()
  setTimeout(() => w.print(), 300)
}

export function ExportBar({ query, result }) {
  if (!result) return null
  const slug = (query || 'answer').slice(0, 40).replace(/[^\wа-яё]+/gi, '_')
  return (
    <div className="export-bar">
      <span className="ex-label">Экспорт:</span>
      <button onClick={() => download(`${slug}.md`, toMarkdown(query, result), 'text/markdown')}>Markdown</button>
      <button onClick={() => download(`${slug}.jsonld`, toJsonLd(query, result), 'application/ld+json')}>JSON-LD</button>
      <button onClick={() => printPdf(query, result)}>PDF</button>
    </div>
  )
}
