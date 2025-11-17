# 📱 Guide Mode Hors Ligne - PWA Aria

## ✅ Configuration terminée

Votre application PWA est maintenant configurée pour mettre en cache **automatiquement toutes les pages visitées** et les rendre disponibles hors ligne.

## 🎯 Fonctionnalités implémentées

### Cache automatique des pages
- ✅ **Toutes les pages visitées** sont automatiquement mises en cache
- ✅ **Préchargement** des pages lors des clics sur les liens
- ✅ **Cache des formulaires GET** pour les résultats de recherche
- ✅ **Limite de cache** : 100 pages maximum (les plus anciennes sont supprimées automatiquement)

### Stratégie de cache
- **Network First** : Essaie d'abord le réseau, puis utilise le cache si hors ligne
- **Cache automatique** : Chaque page visitée est sauvegardée pour usage hors ligne
- **Fallback intelligent** : Si une page n'est pas en cache, redirige vers la page d'accueil

## 🚀 Comment ça fonctionne

### 1. Visite d'une page
Quand vous visitez une page :
1. La page est chargée depuis le serveur
2. Le service worker met automatiquement la page en cache
3. La page est maintenant disponible hors ligne

### 2. Navigation hors ligne
Quand vous êtes hors ligne :
1. Le service worker détecte l'absence de connexion
2. Il cherche la page dans le cache
3. Si trouvée, elle s'affiche immédiatement
4. Si non trouvée, redirection vers la page d'accueil (si disponible)

### 3. Préchargement
Quand vous cliquez sur un lien :
1. Le service worker précharge la page cible
2. La page est mise en cache avant même que vous y accédiez
3. Navigation plus rapide et disponible hors ligne

## 📋 Pages mises en cache automatiquement

Toutes les pages suivantes sont mises en cache :
- ✅ Page d'accueil (`/`)
- ✅ Toutes les pages visitées
- ✅ Pages de dashboard
- ✅ Pages de profil
- ✅ Pages de liste (élèves, classes, etc.)
- ✅ Pages de détail
- ✅ Résultats de recherche (formulaires GET)

## 🔧 Fonctions JavaScript disponibles

### Mettre en cache une page manuellement
```javascript
// Mettre en cache une page spécifique
window.cachePage('https://votre-domaine.com/ma-page');
```

### Obtenir la liste des pages en cache
```javascript
// Obtenir toutes les pages mises en cache
const cachedPages = await window.getCachedPages();
console.log('Pages en cache:', cachedPages);
```

### Vérifier la connexion
```javascript
// Vérifier si l'utilisateur est en ligne
if (window.isOnline()) {
  console.log('En ligne');
} else {
  console.log('Hors ligne');
}
```

## 🧪 Tester le mode hors ligne

### Méthode 1 : DevTools Chrome/Edge
1. Ouvrez l'application dans Chrome/Edge
2. Ouvrez les DevTools (F12)
3. Allez dans l'onglet **Network**
4. Cochez **Offline**
5. Rechargez la page ou naviguez
6. Les pages visitées devraient s'afficher

### Méthode 2 : Désactiver le WiFi
1. Visitez quelques pages de l'application
2. Désactivez votre connexion WiFi/Internet
3. Rechargez la page
4. Les pages visitées devraient s'afficher

### Méthode 3 : Mode avion
1. Visitez quelques pages de l'application
2. Activez le mode avion
3. Rechargez la page
4. Les pages visitées devraient s'afficher

## 📊 Vérifier le cache

### Dans les DevTools
1. Ouvrez les DevTools (F12)
2. Allez dans **Application** > **Cache Storage**
3. Cherchez `aria-pages-v1.0.1`
4. Vous verrez toutes les pages mises en cache

### Dans la console
```javascript
// Obtenir la liste des pages en cache
const pages = await window.getCachedPages();
console.log(`${pages.length} pages en cache`);
pages.forEach(url => console.log('-', url));
```

## ⚙️ Configuration avancée

### Modifier la limite de cache
Éditez `school_admin/static/school_admin/service-worker.js` :
```javascript
// Limite de taille du cache (en nombre d'éléments)
const MAX_CACHE_ITEMS = 100; // Changez cette valeur
```

### Exclure certaines pages du cache
Modifiez la fonction `isHTMLRequest` dans le service worker pour exclure des chemins spécifiques.

## 🐛 Dépannage

### Les pages ne se mettent pas en cache
1. Vérifiez que le service worker est actif (DevTools > Application > Service Workers)
2. Vérifiez la console pour les erreurs
3. Vérifiez que vous êtes sur HTTPS (ou localhost)

### Les pages ne s'affichent pas hors ligne
1. Vérifiez que vous avez visité la page au moins une fois en ligne
2. Vérifiez le cache dans DevTools > Application > Cache Storage
3. Vérifiez la console pour les erreurs

### Le cache est trop volumineux
1. Réduisez `MAX_CACHE_ITEMS` dans le service worker
2. Le cache se nettoie automatiquement (les plus anciennes pages sont supprimées)

## 📝 Notes importantes

- ⚠️ **Seules les pages visitées** sont mises en cache
- ⚠️ **Les données dynamiques** (API, formulaires POST) ne sont pas mises en cache
- ⚠️ **Les fichiers média** uploadés ne sont pas mis en cache
- ✅ **Les assets statiques** (CSS, JS, images) sont toujours mis en cache
- ✅ **Le cache se met à jour** automatiquement quand vous revenez en ligne

## 🎉 Résultat

Maintenant, **toutes les pages que vous visitez sont automatiquement disponibles hors ligne** ! 

Il suffit de :
1. Visiter les pages que vous voulez avoir hors ligne
2. Une fois visitées, elles sont automatiquement mises en cache
3. Vous pouvez y accéder même sans connexion Internet

---

**Votre application est maintenant complètement fonctionnelle hors ligne !** 🚀

