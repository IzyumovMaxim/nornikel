export default function Logo({ onClick }) {
  const petals = [0, 45, 90, 135, 180, 225, 270, 315]
  return (
    <div className="logo" title="На главную" onClick={onClick} role="button">
      <svg viewBox="0 0 48 48" width="34" height="34" className="logo-svg">
        <g className="petals">
          {petals.map((a) => (
            <ellipse key={a} cx="24" cy="13" rx="4.6" ry="10"
              fill="#6ea8fe" opacity="0.85" transform={`rotate(${a} 24 24)`} />
          ))}
        </g>
        <circle cx="24" cy="24" r="4.5" fill="#e8ecf1" />
      </svg>
      <div className="logo-word">Граф&nbsp;знаний</div>
    </div>
  )
}
