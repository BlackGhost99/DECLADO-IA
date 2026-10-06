/** Traces de mise au point : affichées en développement, muettes dans l'application livrée. */
export function debugLog(...args: unknown[]): void {
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.log(...args);
  }
}
