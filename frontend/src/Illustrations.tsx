// Illustrations décoratives dessinées en SVG (aucune image externe) : carte de la CEMAC et port.

/** Silhouette simplifiée de l'Afrique, zone CEMAC en vert, Gabon en vert clair. */
export function CemacMap({ size = 92 }: { size?: number }) {
  return (
    <svg width={size} height={size * 1.1} viewBox="0 0 100 110" aria-hidden="true" className="cemac-map">
      <path
        d="M18 8 30 4 42 6 55 8 64 9 68 12 72 22 78 32 88 36 96 38 90 48 82 58 78 66 76 74 72 82 68 90 60 100 50 104 44 100 40 88 36 76 34 66 30 58 28 54 30 48 26 46 20 44 12 44 6 40 2 30 4 22 10 14Z"
        fill="none"
        stroke="rgba(255,255,255,0.55)"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <path d="M40 18 52 20 54 34 60 38 62 46 50 48 44 52 42 62 34 62 30 56 28 50 30 46 34 40 38 36 40 28Z" fill="#3E9B3A" opacity="0.9" />
      <path d="M28 50 34 48 36 54 32 58 29 56Z" fill="#9BD34D" />
    </svg>
  );
}

/** Scène de port : portiques, conteneurs et navire, en tons discrets. */
export function PortScene() {
  const stack = (x: number, y: number, colors: string[]) =>
    colors.map((c, i) => <rect key={`${x}-${i}`} x={x} y={y - i * 9} width="26" height="8" rx="1" fill={c} />);
  return (
    <svg viewBox="0 0 420 160" className="port-scene" aria-hidden="true" preserveAspectRatio="xMaxYMax meet">
      <defs>
        <linearGradient id="sea" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#cfe3ea" />
          <stop offset="1" stopColor="#e9f2f2" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="fade" x1="0" x2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="1" />
          <stop offset="0.35" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x="0" y="120" width="420" height="40" fill="url(#sea)" />
      <rect x="40" y="116" width="250" height="6" fill="#9aa9a6" />
      {stack(50, 108, ["#b5523b", "#2f6f8f", "#c98a2e", "#4f7f52"])}
      {stack(78, 108, ["#2f6f8f", "#8c3b3b", "#4f7f52"])}
      {stack(106, 108, ["#c98a2e", "#2f6f8f", "#b5523b", "#2f6f8f", "#4f7f52"])}
      {stack(134, 108, ["#4f7f52", "#b5523b", "#2f6f8f"])}
      {stack(162, 108, ["#8c3b3b", "#c98a2e", "#2f6f8f", "#b5523b"])}
      <g stroke="#2d4b5a" strokeWidth="3" fill="none">
        <path d="M205 116V40M235 116V40M200 40h110M205 60h30M220 40l-15 20M220 40l15 20M300 40v22" />
        <path d="M255 116V20M285 116V20M250 20h120M255 42h30M270 20l-15 22M270 20l15 22M360 20v26" />
      </g>
      <rect x="296" y="62" width="8" height="10" fill="#2d4b5a" />
      <rect x="356" y="46" width="8" height="10" fill="#2d4b5a" />
      <path d="M290 122h125l-12 18H302z" fill="#24343d" />
      <rect x="380" y="104" width="22" height="18" fill="#e8ecec" stroke="#24343d" strokeWidth="2" />
      {stack(300, 120, ["#b5523b", "#2f6f8f"])}
      {stack(328, 120, ["#c98a2e", "#4f7f52", "#2f6f8f"])}
      {stack(356, 120, ["#2f6f8f"])}
      <rect x="0" y="0" width="420" height="160" fill="url(#fade)" />
    </svg>
  );
}
