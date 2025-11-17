# Electron Security Configuration

## Content Security Policy (CSP)

L'application Electron utilise une Content Security Policy (CSP) pour sécuriser le renderer process.

### Configuration

La CSP est configurée à deux niveaux :

1. **Dans `index.html`** : Meta tag CSP pour le navigateur
2. **Dans `main.js`** : Headers CSP via `webRequest.onHeadersReceived`

### Mode Développement vs Production

#### Mode Développement
- **`unsafe-eval` autorisé** : Nécessaire pour Vite HMR (Hot Module Replacement)
- **Connexions locales** : Permises pour le serveur de développement Vite et le backend
- **WebSockets** : Autorisés pour le HMR

#### Mode Production
- **`unsafe-eval` désactivé** : Sécurité renforcée
- **Connexions limitées** : Seulement au backend local (port 8000)
- **Pas de WebSockets** : Non nécessaires en production

### Avertissement Electron

L'avertissement suivant peut apparaître en mode développement :

```
Electron Security Warning (Insecure Content-Security-Policy)
This renderer process has either no Content Security Policy set
or a policy with "unsafe-eval" enabled.
```

**C'est normal en développement** car :
- Vite nécessite `unsafe-eval` pour le Hot Module Replacement
- L'avertissement n'apparaîtra **pas en production** une fois l'app packagée
- La CSP est correctement configurée pour la production

### Sécurité

L'application utilise les meilleures pratiques Electron :

- ✅ **Context Isolation** : Activé (`contextIsolation: true`)
- ✅ **Node Integration** : Désactivé (`nodeIntegration: false`)
- ✅ **Web Security** : Activé (`webSecurity: true`)
- ✅ **Preload Script** : Utilisé pour exposer des APIs sécurisées via `contextBridge`
- ✅ **CSP** : Configurée pour bloquer les scripts non autorisés

### Références

- [Electron Security Tutorial](https://www.electronjs.org/docs/latest/tutorial/security)
- [Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)
- [Vite HMR](https://vitejs.dev/guide/api-hmr.html)

