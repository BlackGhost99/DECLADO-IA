import { useEffect, useRef } from 'react';
import './Globe3D.css';

export function Globe3D() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size
    const size = 450;
    canvas.width = size;
    canvas.height = size;

    const centerX = size / 2;
    const centerY = size / 2;
    const radius = size * 0.35;

    let rotation = 0;

    // Generate latitude and longitude lines
    const latitudes: number[] = [];
    const longitudes: number[] = [];

    // Latitude lines (horizontal circles)
    for (let lat = -80; lat <= 80; lat += 20) {
      latitudes.push(lat);
    }

    // Longitude lines (vertical semi-circles)
    for (let lon = 0; lon < 360; lon += 30) {
      longitudes.push(lon);
    }

    // Add detailed continents outlines
    const continents: Array<{ lat: number; lon: number }[]> = [
      // Africa (détaillé)
      [
        { lat: 37, lon: -6 },
        { lat: 37, lon: 12 },
        { lat: 32, lon: 22 },
        { lat: 31, lon: 32 },
        { lat: 22, lon: 37 },
        { lat: 15, lon: 42 },
        { lat: 12, lon: 43 },
        { lat: 4, lon: 42 },
        { lat: -4, lon: 40 },
        { lat: -12, lon: 40 },
        { lat: -18, lon: 36 },
        { lat: -26, lon: 32 },
        { lat: -29, lon: 29 },
        { lat: -33, lon: 26 },
        { lat: -35, lon: 20 },
        { lat: -33, lon: 18 },
        { lat: -28, lon: 17 },
        { lat: -23, lon: 15 },
        { lat: -18, lon: 13 },
        { lat: -12, lon: 12 },
        { lat: -6, lon: 12 },
        { lat: 4, lon: 9 },
        { lat: 10, lon: 8 },
        { lat: 15, lon: -5 },
        { lat: 20, lon: -13 },
        { lat: 28, lon: -10 },
        { lat: 33, lon: -8 },
        { lat: 37, lon: -6 },
      ],
      // Europe (détaillé)
      [
        { lat: 71, lon: 26 },
        { lat: 70, lon: 30 },
        { lat: 65, lon: 40 },
        { lat: 60, lon: 30 },
        { lat: 55, lon: 20 },
        { lat: 54, lon: 10 },
        { lat: 50, lon: 5 },
        { lat: 48, lon: -5 },
        { lat: 43, lon: -8 },
        { lat: 36, lon: -6 },
        { lat: 36, lon: 0 },
        { lat: 38, lon: 10 },
        { lat: 41, lon: 15 },
        { lat: 45, lon: 14 },
        { lat: 48, lon: 17 },
        { lat: 50, lon: 24 },
        { lat: 55, lon: 28 },
        { lat: 60, lon: 30 },
        { lat: 65, lon: 28 },
        { lat: 69, lon: 25 },
        { lat: 71, lon: 26 },
      ],
      // Amérique du Nord
      [
        { lat: 72, lon: -95 },
        { lat: 70, lon: -110 },
        { lat: 65, lon: -130 },
        { lat: 60, lon: -140 },
        { lat: 55, lon: -130 },
        { lat: 50, lon: -125 },
        { lat: 45, lon: -124 },
        { lat: 35, lon: -118 },
        { lat: 32, lon: -117 },
        { lat: 25, lon: -112 },
        { lat: 20, lon: -105 },
        { lat: 15, lon: -92 },
        { lat: 10, lon: -85 },
        { lat: 8, lon: -77 },
        { lat: 10, lon: -75 },
        { lat: 25, lon: -80 },
        { lat: 30, lon: -81 },
        { lat: 35, lon: -76 },
        { lat: 42, lon: -70 },
        { lat: 45, lon: -67 },
        { lat: 50, lon: -65 },
        { lat: 55, lon: -60 },
        { lat: 60, lon: -65 },
        { lat: 65, lon: -70 },
        { lat: 70, lon: -80 },
        { lat: 72, lon: -95 },
      ],
      // Amérique du Sud
      [
        { lat: 10, lon: -75 },
        { lat: 8, lon: -77 },
        { lat: 0, lon: -80 },
        { lat: -5, lon: -81 },
        { lat: -10, lon: -78 },
        { lat: -18, lon: -70 },
        { lat: -25, lon: -70 },
        { lat: -35, lon: -72 },
        { lat: -45, lon: -73 },
        { lat: -52, lon: -70 },
        { lat: -55, lon: -68 },
        { lat: -54, lon: -65 },
        { lat: -50, lon: -62 },
        { lat: -40, lon: -60 },
        { lat: -30, lon: -57 },
        { lat: -23, lon: -52 },
        { lat: -18, lon: -48 },
        { lat: -8, lon: -35 },
        { lat: -5, lon: -35 },
        { lat: 0, lon: -50 },
        { lat: 5, lon: -60 },
        { lat: 8, lon: -65 },
        { lat: 10, lon: -70 },
        { lat: 10, lon: -75 },
      ],
      // Asie (détaillé)
      [
        { lat: 70, lon: 60 },
        { lat: 75, lon: 80 },
        { lat: 77, lon: 100 },
        { lat: 75, lon: 120 },
        { lat: 70, lon: 140 },
        { lat: 65, lon: 150 },
        { lat: 60, lon: 155 },
        { lat: 50, lon: 145 },
        { lat: 45, lon: 142 },
        { lat: 40, lon: 140 },
        { lat: 35, lon: 138 },
        { lat: 30, lon: 130 },
        { lat: 25, lon: 122 },
        { lat: 20, lon: 110 },
        { lat: 10, lon: 105 },
        { lat: 5, lon: 103 },
        { lat: 1, lon: 104 },
        { lat: -5, lon: 110 },
        { lat: -8, lon: 115 },
        { lat: -5, lon: 120 },
        { lat: 0, lon: 125 },
        { lat: 5, lon: 120 },
        { lat: 10, lon: 107 },
        { lat: 15, lon: 100 },
        { lat: 20, lon: 95 },
        { lat: 23, lon: 88 },
        { lat: 28, lon: 80 },
        { lat: 30, lon: 75 },
        { lat: 35, lon: 70 },
        { lat: 40, lon: 65 },
        { lat: 45, lon: 65 },
        { lat: 50, lon: 60 },
        { lat: 55, lon: 60 },
        { lat: 60, lon: 65 },
        { lat: 65, lon: 70 },
        { lat: 70, lon: 60 },
      ],
      // Australie
      [
        { lat: -10, lon: 142 },
        { lat: -12, lon: 145 },
        { lat: -17, lon: 146 },
        { lat: -23, lon: 150 },
        { lat: -28, lon: 153 },
        { lat: -33, lon: 151 },
        { lat: -38, lon: 148 },
        { lat: -39, lon: 145 },
        { lat: -38, lon: 140 },
        { lat: -35, lon: 135 },
        { lat: -32, lon: 130 },
        { lat: -28, lon: 125 },
        { lat: -22, lon: 114 },
        { lat: -18, lon: 122 },
        { lat: -14, lon: 130 },
        { lat: -12, lon: 136 },
        { lat: -10, lon: 142 },
      ],
    ];

    function toRadians(deg: number): number {
      return (deg * Math.PI) / 180;
    }

    function project3D(lat: number, lon: number, rot: number) {
      const latRad = toRadians(lat);
      const lonRad = toRadians(lon + rot);

      const x = radius * Math.cos(latRad) * Math.sin(lonRad);
      const y = radius * Math.sin(latRad);
      const z = radius * Math.cos(latRad) * Math.cos(lonRad);

      // Simple perspective projection
      const scale = 200 / (200 + z);
      const projX = centerX + x * scale;
      const projY = centerY - y * scale;

      return { x: projX, y: projY, z, visible: z > 0 };
    }

    function animate() {
      if (!ctx || !canvas) return;

      // Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw glow effect
      const gradient = ctx.createRadialGradient(
        centerX,
        centerY,
        radius * 0.8,
        centerX,
        centerY,
        radius * 1.3
      );
      gradient.addColorStop(0, 'rgba(0, 234, 255, 0.1)');
      gradient.addColorStop(1, 'rgba(0, 234, 255, 0)');
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Draw base sphere
      const sphereGradient = ctx.createRadialGradient(
        centerX - radius * 0.3,
        centerY - radius * 0.3,
        radius * 0.1,
        centerX,
        centerY,
        radius
      );
      sphereGradient.addColorStop(0, 'rgba(15, 35, 70, 0.9)');
      sphereGradient.addColorStop(1, 'rgba(5, 15, 30, 0.9)');
      ctx.fillStyle = sphereGradient;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.fill();

      // Draw latitude lines
      ctx.strokeStyle = 'rgba(0, 234, 255, 0.3)';
      ctx.lineWidth = 1;
      latitudes.forEach(lat => {
        const points: Array<{ x: number; y: number; z: number }> = [];
        for (let lon = 0; lon <= 360; lon += 5) {
          const p = project3D(lat, lon, rotation);
          points.push(p);
        }

        ctx.beginPath();
        let started = false;
        points.forEach((p, i) => {
          if (p.z > 0) {
            if (!started || (i > 0 && points[i - 1].z <= 0)) {
              ctx.moveTo(p.x, p.y);
              started = true;
            } else {
              ctx.lineTo(p.x, p.y);
            }
          }
        });
        ctx.stroke();
      });

      // Draw longitude lines
      longitudes.forEach(lon => {
        const points: Array<{ x: number; y: number; z: number }> = [];
        for (let lat = -90; lat <= 90; lat += 5) {
          const p = project3D(lat, lon, rotation);
          points.push(p);
        }

        ctx.beginPath();
        let started = false;
        points.forEach((p, i) => {
          if (p.z > 0) {
            if (!started || (i > 0 && points[i - 1].z <= 0)) {
              ctx.moveTo(p.x, p.y);
              started = true;
            } else {
              ctx.lineTo(p.x, p.y);
            }
          }
        });
        ctx.stroke();
      });

      // Draw continents
      ctx.strokeStyle = 'rgba(0, 234, 255, 0.6)';
      ctx.fillStyle = 'rgba(0, 234, 255, 0.15)';
      ctx.lineWidth = 1.5;

      continents.forEach(continent => {
        const projectedPoints = continent.map(point => project3D(point.lat, point.lon, rotation));

        // Only draw if at least some points are visible
        const visiblePoints = projectedPoints.filter(p => p.visible);
        if (visiblePoints.length > 2) {
          ctx.beginPath();
          let started = false;
          projectedPoints.forEach(p => {
            if (p.visible) {
              if (!started) {
                ctx.moveTo(p.x, p.y);
                started = true;
              } else {
                ctx.lineTo(p.x, p.y);
              }
            }
          });
          ctx.closePath();
          ctx.fill();
          ctx.stroke();
        }
      });

      // Add some random stars/points for visual interest
      ctx.fillStyle = 'rgba(0, 234, 255, 0.8)';
      for (let i = 0; i < 30; i++) {
        const lat = Math.random() * 160 - 80;
        const lon = Math.random() * 360;
        const p = project3D(lat, lon, rotation);
        if (p.visible && Math.random() > 0.7) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, 1.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      rotation += 0.3; // Rotation speed
      requestAnimationFrame(animate);
    }

    animate();
  }, []);

  return (
    <div className="globe-container">
      <canvas ref={canvasRef} className="globe-canvas" />
      <div className="globe-label">🌍</div>
    </div>
  );
}
