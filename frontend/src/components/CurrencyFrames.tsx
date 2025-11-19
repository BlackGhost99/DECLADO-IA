import { useEffect, useRef, useState } from 'react';
import './CurrencyFrames.css';

interface Rates {
  [code: string]: number;
}

interface CurrencyFrameProps {
  currency: string;
  name: string;
  rate: number;
  isReference?: boolean;
}

function CurrencyFrame({ currency, name, rate, isReference }: CurrencyFrameProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [displayRate, setDisplayRate] = useState(rate);
  const [isUpdating, setIsUpdating] = useState(false);

  // Animate rate changes
  useEffect(() => {
    if (rate !== displayRate && !isReference) {
      setIsUpdating(true);
      const duration = 500;
      const startTime = Date.now();
      const startRate = displayRate;
      const diff = rate - startRate;

      const animate = () => {
        const elapsed = Date.now() - startTime;
        const progress = Math.min(elapsed / duration, 1);
        setDisplayRate(startRate + diff * progress);

        if (progress < 1) {
          requestAnimationFrame(animate);
        } else {
          setIsUpdating(false);
        }
      };
      animate();
    }
  }, [rate, displayRate, isReference]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;

    const chars = '01デジタル0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    const fontSize = 12;
    const columns = Math.floor(canvas.width / fontSize);
    const drops: number[] = Array(columns).fill(0);

    let animationId: number;

    function draw() {
      if (!ctx || !canvas) return;

      // Semi-transparent black to create trail effect
      ctx.fillStyle = 'rgba(10, 24, 54, 0.08)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Matrix text
      ctx.fillStyle = isReference ? '#00eaff' : '#b3e5fc';
      ctx.font = `${fontSize}px monospace`;

      for (let i = 0; i < drops.length; i++) {
        const char = chars[Math.floor(Math.random() * chars.length)];
        const x = i * fontSize;
        const y = drops[i] * fontSize;

        ctx.fillText(char, x, y);

        // Reset drop to top randomly
        if (y > canvas.height && Math.random() > 0.975) {
          drops[i] = 0;
        }
        drops[i]++;
      }

      animationId = requestAnimationFrame(draw);
    }

    draw();

    return () => {
      cancelAnimationFrame(animationId);
    };
  }, [isReference]);

  return (
    <div className={`currency-frame ${isReference ? 'reference' : ''}`}>
      <canvas ref={canvasRef} className="frame-matrix-canvas" />
      <div className="frame-content">
        <div className="frame-currency">{currency}</div>
        <div className="frame-name">{name}</div>
        <div className={`frame-rate ${isUpdating ? 'updating' : ''}`}>
          {isReference ? '1.0000' : displayRate.toFixed(4)}
        </div>
        {isReference && <div className="frame-badge">Référence</div>}
        {isUpdating && <div className="frame-pulse">●</div>}
      </div>
    </div>
  );
}

export function CurrencyFrames() {
  const [rates, setRates] = useState<Rates>({});

  useEffect(() => {
    async function fetchRates() {
      try {
        // Try primary API: exchangerate.host
        const res = await fetch(
          'https://api.exchangerate.host/latest?base=USD&symbols=EUR,GBP,XOF,CNY,JPY'
        );
        const data = await res.json();

        if (data.rates && Object.keys(data.rates).length > 0) {
          setRates(data.rates);
          return;
        }
      } catch (error) {
        console.warn('Primary API failed, trying fallback...');
      }

      try {
        // Fallback 1: open.er-api.com
        const res = await fetch('https://open.er-api.com/v6/latest/USD');
        const data = await res.json();

        if (data.rates) {
          const filteredRates: Rates = {
            EUR: data.rates.EUR,
            GBP: data.rates.GBP,
            CNY: data.rates.CNY,
            JPY: data.rates.JPY,
            XOF: data.rates.XOF || data.rates.EUR * 655.957, // Fallback calculation
          };
          setRates(filteredRates);
          return;
        }
      } catch (error) {
        console.warn('Fallback 1 failed, trying fallback 2...');
      }

      try {
        // Fallback 2: frankfurter.app (doesn't have XOF)
        const res = await fetch('https://api.frankfurter.app/latest?from=USD&to=EUR,GBP,CNY,JPY');
        const data = await res.json();

        if (data.rates) {
          const filteredRates: Rates = {
            EUR: data.rates.EUR,
            GBP: data.rates.GBP,
            CNY: data.rates.CNY,
            JPY: data.rates.JPY,
            XOF: data.rates.EUR * 655.957, // Calculate XOF from EUR
          };
          setRates(filteredRates);
          return;
        }
      } catch (error) {
        console.error('All APIs failed, using fallback rates');
      }

      // Ultimate fallback - approximate rates
      setRates({
        EUR: 0.92,
        GBP: 0.79,
        XOF: 603,
        CNY: 7.25,
        JPY: 150,
      });
    }

    fetchRates();
    const interval = setInterval(fetchRates, 30_000); // Update every 30 seconds
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="currency-frames-container">
      <CurrencyFrame currency="USD" name="Dollar US" rate={1} isReference />
      <CurrencyFrame currency="EUR" name="Euro" rate={rates.EUR || 0} />
      <CurrencyFrame currency="GBP" name="Sterling" rate={rates.GBP || 0} />
      <CurrencyFrame currency="CNY" name="Yuan" rate={rates.CNY || 0} />
      <CurrencyFrame currency="JPY" name="Yen" rate={rates.JPY || 0} />
      <CurrencyFrame currency="XOF" name="Franc CFA" rate={rates.XOF || 0} />
    </div>
  );
}
