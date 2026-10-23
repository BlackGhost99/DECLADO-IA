// Visionneuse PDF intégrée (pdf.js) : pages, zoom, et surlignage de la zone d'où vient une valeur lue.
import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";

type PdfDoc = {
  numPages: number;
  getPage: (n: number) => Promise<{
    getViewport: (o: { scale: number }) => { width: number; height: number };
    render: (o: { canvasContext: CanvasRenderingContext2D; viewport: unknown }) => { promise: Promise<void>; cancel: () => void };
  }>;
  destroy: () => Promise<void>;
};

export interface Highlight {
  page: number;
  /** Zone normalisée 0–1 depuis le coin supérieur gauche : x0, y0, x1, y1. */
  bbox: [number, number, number, number] | null;
}

async function loadPdf(url: string): Promise<PdfDoc> {
  const pdfjs = await import("pdfjs-dist");
  const worker = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
  pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
  return (await pdfjs.getDocument({ url, withCredentials: true }).promise) as unknown as PdfDoc;
}

/** Impression de la pièce telle quelle, sans quitter le dossier. */
function printPdf(url: string) {
  const frame = document.createElement("iframe");
  frame.style.display = "none";
  frame.src = url;
  frame.onload = () => {
    try {
      frame.contentWindow?.print();
    } catch {
      window.open(url, "_blank", "noreferrer");
    }
  };
  document.body.appendChild(frame);
  setTimeout(() => frame.remove(), 60000);
}

export function PdfViewer({
  url,
  name,
  highlight,
  onDownload,
}: {
  url: string;
  name: string;
  highlight: Highlight | null;
  onDownload: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [doc, setDoc] = useState<PdfDoc | null>(null);
  const [failed, setFailed] = useState(false);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    let alive = true;
    let loaded: PdfDoc | null = null;
    setDoc(null);
    setFailed(false);
    loadPdf(url).then(
      (d) => {
        loaded = d;
        if (alive) setDoc(d);
        else void d.destroy();
      },
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
      if (loaded) void loaded.destroy();
    };
  }, [url]);

  useEffect(() => {
    if (highlight?.page) setPage(highlight.page);
  }, [highlight]);

  useEffect(() => {
    if (!doc || !canvasRef.current) return;
    let task: { cancel: () => void } | null = null;
    let alive = true;
    void doc.getPage(Math.min(page, doc.numPages)).then((p) => {
      if (!alive || !canvasRef.current) return;
      const canvas = canvasRef.current;
      const base = p.getViewport({ scale: 1 });
      const width = (canvas.parentElement?.parentElement?.clientWidth ?? 600) - 12;
      const scale = (width / base.width) * zoom;
      const viewport = p.getViewport({ scale: scale * (window.devicePixelRatio || 1) });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      setSize({ w: viewport.width / (window.devicePixelRatio || 1), h: viewport.height / (window.devicePixelRatio || 1) });
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const t = p.render({ canvasContext: ctx, viewport });
      task = t;
      t.promise.catch(() => undefined);
    });
    return () => {
      alive = false;
      task?.cancel();
    };
  }, [doc, page, zoom]);

  if (failed) {
    return <iframe title={name} src={highlight?.page ? `${url}#page=${highlight.page}` : url} className="preview" />;
  }

  const pages = doc?.numPages ?? 1;
  const box = highlight && highlight.page === page ? highlight.bbox : null;
  return (
    <>
      <div className="viewer-bar">
        <span className="viewer-name" title={name}><Icon name="menu" size={20} /> {name}</span>
        <label className="viewer-pagebox">
          <span className="visually-hidden">Page</span>
          <input
            type="number"
            min={1}
            max={pages}
            value={page}
            onChange={(e) => {
              const n = Number(e.target.value);
              if (n >= 1 && n <= pages) setPage(n);
            }}
          />
          <span aria-live="polite">/ {pages}</span>
        </label>
        <span className="viewer-tools">
          <button type="button" className="icon-button" disabled={zoom <= 0.6} onClick={() => setZoom(Math.round((zoom - 0.2) * 10) / 10)} aria-label="Réduire">
            <Icon name="minus" size={18} />
          </button>
          <span className="viewer-zoom">{Math.round(zoom * 100)}%</span>
          <button type="button" className="icon-button" disabled={zoom >= 2.4} onClick={() => setZoom(Math.round((zoom + 0.2) * 10) / 10)} aria-label="Agrandir">
            <Icon name="plus" size={18} />
          </button>
        </span>
        <span className="viewer-tools">
          <button type="button" className="icon-button" onClick={onDownload} aria-label="Télécharger">
            <Icon name="download" size={18} />
          </button>
          <button type="button" className="icon-button" onClick={() => printPdf(url)} aria-label="Imprimer">
            <Icon name="printer" size={18} />
          </button>
          <a className="icon-button" href={url} target="_blank" rel="noreferrer" aria-label="Ouvrir dans un nouvel onglet">
            <Icon name="external" size={18} />
          </a>
        </span>
      </div>
      <div className="viewer-body pdf-body">
        {!doc && <p className="muted center-text">Chargement de la pièce…</p>}
        <div className="pdf-page" style={size ? { width: size.w, height: size.h } : undefined}>
          <canvas ref={canvasRef} style={size ? { width: size.w, height: size.h } : undefined} />
          {box && (
            <span
              className="pdf-highlight"
              style={{
                left: `${box[0] * 100}%`,
                top: `${box[1] * 100}%`,
                width: `${(box[2] - box[0]) * 100}%`,
                height: `${(box[3] - box[1]) * 100}%`,
              }}
            />
          )}
        </div>
      </div>
    </>
  );
}
