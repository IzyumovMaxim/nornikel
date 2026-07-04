import { useState } from 'react'
import { MUTED } from './GraphCanvas.jsx'

export default function HelpButton({ meta }) {
  const [open, setOpen] = useState(false)
  const nodeTypes = meta?.nodeTypes || {}
  const roles = meta?.roles || {}

  return (
    <>
      <button className="help-fab" onClick={() => setOpen(true)} title="Справка">?</button>

      {open && (
        <div className="help-overlay" onClick={() => setOpen(false)}>
          <div className="help-panel" onClick={(e) => e.stopPropagation()}>
            <div className="help-head">
              <h3>Как пользоваться</h3>
              <button className="close" onClick={() => setOpen(false)}>×</button>
            </div>

            <div className="help-body">
              <section>
                <h4>Что это</h4>
                <p>Единая карта знаний R&D горно-металлургической отрасли: отчёты,
                эксперименты, материалы, процессы, оборудование, эксперты и выводы
                связаны в граф. Задайте вопрос — система найдёт релевантное, построит
                цепочки и синтезирует ответ со ссылками на отчёты.</p>
              </section>

              <section>
                <h4>Навигация</h4>
                <ul className="help-list">
                  <li><b>Поиск</b> — запрос на естественном языке, с подсказками.</li>
                  <li><b>Фильтры</b> — происхождение практики и числовые диапазоны (t, извлечение, pH…).</li>
                  <li><b>Панель справа</b> — быстрый переход к разделам ответа.</li>
                  <li><b>Роль</b> (сверху справа) — управляет доступом к данным (RBAC).</li>
                </ul>
              </section>

              <section>
                <h4>Типы сущностей</h4>
                <div className="help-legend">
                  {Object.entries(nodeTypes).map(([t, v]) => (
                    <div className="li" key={t}>
                      <span className="dot" style={{ background: MUTED[t] || '#7f8794' }} />{v.label}
                    </div>
                  ))}
                  <div className="li"><span className="dot" style={{ background: '#eb6b73' }} />красное ребро — противоречие</div>
                </div>
              </section>

              <section>
                <h4>Роли доступа</h4>
                <ul className="help-list">
                  {Object.entries(roles).map(([r, v]) => (
                    <li key={r}><b>{r}</b> — {v.types.length} типов сущностей
                      {v.see_contradictions ? ', видит противоречия' : ', без противоречий'}.</li>
                  ))}
                </ul>
              </section>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
