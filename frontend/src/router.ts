// Navigation par ancre (#/…) : pas de dépendance, et le serveur n'a qu'une page à servir.
import { useEffect, useState } from "react";

export interface Route {
  parts: string[];
  query: URLSearchParams;
}

function parse(hash: string): Route {
  const [path, search = ""] = hash.replace(/^#\/?/, "").split("?");
  return { parts: path.split("/").filter(Boolean).map(decodeURIComponent), query: new URLSearchParams(search) };
}

export function navigate(path: string) {
  window.location.hash = path.startsWith("#") ? path : `#${path}`;
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

/** Dernier dossier ouvert : les entrées Documents, Marchandises… de la barre latérale y mènent. */
const CURRENT_KEY = "clairtransit.current-case";

export function rememberCase(id: string) {
  try {
    sessionStorage.setItem(CURRENT_KEY, id);
  } catch {
    // stockage indisponible (navigation privée) : la barre latérale demandera de choisir un dossier
  }
}

export function currentCase(): string | null {
  try {
    return sessionStorage.getItem(CURRENT_KEY);
  } catch {
    return null;
  }
}
