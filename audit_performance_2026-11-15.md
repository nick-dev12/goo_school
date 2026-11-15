# Audit de performance — Aria / Goo School

Date : 15 novembre 2026. Objectif : un site très rapide, y compris sur une connexion 3G faible.

## 1. En bref

- **Avant** : la première ouverture d'une page pesait entre 0,8 et 1,3 Mo et prenait **17 à 28 secondes** sur une 3G lente (400 kbit/s, 400 ms de latence). Le texte utile ne représentait que 2 % de ce poids.
- **Après** (code optimisé + compression activée sur le serveur) : **0,2 à 0,36 Mo** et **6 à 9,5 secondes** ; le premier affichage arrive en **2 à 3 secondes** au lieu de 4 à 9.
- Les visites suivantes (fichiers déjà en mémoire du téléphone) restent à **0,5 – 0,7 seconde**, comme avant.
- **Une action reste à faire sur le serveur de production** : activer la compression des CSS / JavaScript dans Nginx (2 lignes, voir § 6). Sans elle, le gain existe mais il est réduit (pages 25 à 40 % plus légères, premier affichage inchangé).
- Le serveur local `localhost:8000` a été redémarré le 15/11 : il sert le code optimisé.

## 2. Comment les mesures ont été faites

- Un banc de mesure reproductible a été ajouté : `school_admin/tests/test_perf_pages.py`. Il crée un établissement de test (base en mémoire, jamais la base de développement), ouvre chaque page dans Chromium avec le débit bridé à **400 kbit/s et 400 ms de latence**, cache vide, puis une seconde fois avec le cache du navigateur. Les CDN externes sont bridés de la même façon.
- Il relève aussi le temps de calcul du serveur et le nombre de requêtes SQL de chaque page.
- Commande : `PERF_MESURE=1 PERF_STATIC=whitenoise PERF_SORTIE=mesures.json python manage.py test school_admin.tests.test_perf_pages --settings=school.test_settings` (après `collectstatic`).
- Vocabulaire : **premier affichage** = moment où le texte apparaît ; **chargement complet** = tout est téléchargé ; **à froid** = première visite, rien en mémoire.

Limites, à lire avec les chiffres :

- Les données sont un petit jeu de test (2 classes, quelques élèves). Les **poids et temps réseau sont fiables** ; les **temps serveur sont des planchers** : avec les données réelles ils seront plus élevés.
- La mesure « avant » imite la production actuelle : pages HTML compressées (Nginx le fait déjà), CSS / JS non compressés (vérifié sur `aria-edu.com` le 15/11).
- La mesure « après » suppose la compression des CSS / JS active (§ 6). Le cas « production non réglée » est donné à part.

## 3. Constat avant optimisation

### 3.1 Poids et temps par page (3G lente, à froid)

| Espace | Page | Requêtes | Poids | dont CDN | Premier affichage | Chargement complet |
|---|---|---:|---:|---:|---:|---:|
| Connexion | `/connexion/` | 15 | 424 Ko | 333 Ko | 6,0 s | 10,1 s |
| Direction | Tableau de bord | 45 | 1 171 Ko | 429 Ko | 5,8 s | 25,4 s |
| Direction | Élèves | 43 | 1 140 Ko | 360 Ko | 6,9 s | 24,9 s |
| Direction | Notes et résultats | 52 | 1 275 Ko | 360 Ko | 9,1 s | 27,6 s |
| Direction | Suivi des présences | 54 | 1 291 Ko | 360 Ko | 9,3 s | 28,1 s |
| Direction | Scolarité (comptabilité) | 54 | 1 217 Ko | 360 Ko | 8,4 s | 26,5 s |
| Personnel | Tableau de bord | 47 | 1 183 Ko | 429 Ko | 5,8 s | 26,0 s |
| Personnel | Élèves | 42 | 1 139 Ko | 360 Ko | 6,9 s | 24,8 s |
| Professeur secondaire | Tableau de bord | 56 | 1 030 Ko | 356 Ko | 6,3 s | 22,9 s |
| Professeur secondaire | Classes | 58 | 977 Ko | 286 Ko | 6,4 s | 21,8 s |
| Professeur secondaire | Élèves | 64 | 1 050 Ko | 286 Ko | 7,2 s | 23,3 s |
| Professeur primaire | Tableau de bord | 56 | 1 030 Ko | 356 Ko | 6,3 s | 22,9 s |
| Professeur primaire | Classes | 57 | 975 Ko | 286 Ko | 6,2 s | 21,6 s |
| Professeur primaire | Élèves | 63 | 1 045 Ko | 286 Ko | 7,1 s | 23,2 s |
| Élève | Tableau de bord | 30 | 895 Ko | 324 Ko | 5,1 s | 19,8 s |
| Élève | Emploi du temps | 29 | 824 Ko | 254 Ko | 5,1 s | 18,3 s |
| Élève | Devoirs | 28 | 818 Ko | 254 Ko | 5,1 s | 18,2 s |
| Parent | Tableau de bord | 25 | 768 Ko | 254 Ko | 4,2 s | 17,0 s |
| Parent | Scolarité | 25 | 770 Ko | 254 Ko | 4,1 s | 16,9 s |

Deuxième visite d'une même page (cache chaud) : 0,5 à 0,7 s, 2 à 4 requêtes, 5 à 14 Ko.

### 3.2 Ce qui pesait

| Ressource | Poids | Présente sur | Remarque |
|---|---:|---|---|
| `img/aria-assistante.png` | 241 Ko | toutes les pages privées | photo 1024 × 1024 affichée en vignette de 40 px |
| Police d'icônes Font Awesome (cdnjs) | 147 Ko + 19 Ko | toutes les pages | 1 400 icônes téléchargées, environ 400 utilisées |
| `html5-qrcode` (unpkg) | 106 Ko | connexion + toutes les pages direction | bloque l'affichage ; ne sert qu'à l'ouverture du scanner |
| `assistant_vocal.js` | 79 Ko | toutes les pages privées | non compressé (18 Ko une fois compressé) |
| `chart.js` (jsdelivr) | 70 Ko | tableaux de bord | |
| `directeur_live.js` | 56 Ko | pages direction | non compressé (11 Ko compressé) |
| Police Inter (Google Fonts) | 48 Ko | toutes les pages | 2 hôtes externes de plus |
| Feuilles CSS du site | 250 à 450 Ko | selon la page | 20 à 30 fichiers, non compressés |
| Firebase (gstatic) | 32 Ko | toutes les pages privées | notifications push |
| `logo_wordmark.png`, `logo.jpeg` | 26 Ko, 42 Ko | en-têtes, connexion | images plus grandes que leur affichage |

### 3.3 Bibliothèques servies par des CDN

Sept hôtes externes pouvaient être contactés pour une seule page : `cdnjs.cloudflare.com` (Font Awesome, 245 gabarits), `fonts.googleapis.com` + `fonts.gstatic.com` (Inter, Poppins, 222 gabarits), `unpkg.com` (html5-qrcode), `cdn.jsdelivr.net` (chart.js), `www.gstatic.com` (Firebase), `cdn.gtranslate.net` (traduction). Chaque nouvel hôte coûte environ 1,2 à 1,6 s sur une 3G lente (résolution du nom, connexion, chiffrement) avant le premier octet, et rend le site dépendant d'un service tiers : même sans bridage, la page de connexion s'affichait en 4,5 s depuis ce poste à cause d'eux.

Cas particuliers relevés :

- 15 pages d'impression (bulletins, certificats, relevés) chargeaient la version **JavaScript** de Font Awesome : **400 Ko compressés**, soit 8 s de téléchargement pour 5 icônes.
- 4 versions différentes de Font Awesome étaient appelées (6.0.0, 6.4.0, 6.5.0, 6.5.2), dont une adresse invalide (« 6.40 »).
- `tabs_nav_overflow.js` était téléchargé deux fois par page (deux numéros de version différents).

### 3.4 Compression et cache

| Point | Constat |
|---|---|
| Pages HTML | compressées par Nginx en production ; **pas** par l'application (rien en local) |
| CSS et JavaScript | **non compressés en production** (`connexion_admin.css` : 18,8 Ko envoyés tels quels) |
| Réponses JSON des API | non compressées |
| Cache navigateur des fichiers statiques | bon en production : 30 jours (`Cache-Control: max-age=2592000, public, immutable`) |
| Protocole | HTTP/1.1 : 6 téléchargements en parallèle au plus par hôte |
| Service worker (`/service-worker.js`) | correct : garde en mémoire les fichiers `/static/` (150 au plus), aucune page privée ; il est servi sans cache, ce qui convient |
| `collectstatic` | ne produisait aucune copie compressée |

### 3.5 Temps serveur et SQL (jeu de test)

| Page | Temps serveur | Requêtes SQL |
|---|---:|---:|
| Direction — tableau de bord | 106 ms | 149 |
| Personnel — tableau de bord | 120 ms | 170 |
| Professeur — tableau de bord (secondaire / primaire) | 39 / 40 ms | 48 / 45 |
| Parent — tableau de bord | 41 ms | 45 |
| Élève — tableau de bord | 23 ms | 27 |
| Direction — notes, présences, scolarité, élèves | 12 à 32 ms | 15 à 26 |

- Le tableau de bord de la direction n'a pas de boucle « N+1 » : ce sont environ 150 requêtes **différentes**, une ou plusieurs par indicateur (effectifs, présences, moyennes, finances). Leur nombre ne dépend pas du nombre d'élèves, mais chacune parcourt plus de lignes sur une vraie base.
- L'année scolaire active était relue 3 à 8 fois par page (middleware, vue, gabarit).

### 3.6 Appel « rappels » sur chaque page

Le composant de rappels appelle `POST /api/context-popup/` après chaque chargement de page. Mesure : **20 à 45 requêtes SQL à chaque page** (parent : 38 à 42, personnel : 45 à 49), soit davantage que la plupart des pages elles-mêmes, uniquement pour recalculer le chiffre de la pastille « À faire ». L'appel part après l'affichage et ne le retarde pas ; son coût est la charge du serveur.

### 3.7 Middlewares et context processors

- `school_admin/middleware.py` : `AuthenticationMiddleware` reconstruit 9 adresses à chaque requête (négligeable) ; `SessionActiveMiddleware` lit l'année active (1 requête) ; `CaissierAccessMiddleware` et `SeoMiddleware` ne font pas de requête.
- `SESSION_SAVE_EVERY_REQUEST = True` : une écriture en base à chaque requête d'un utilisateur connecté. C'est voulu (expiration par inactivité) ; non modifié.
- `context_popup_middleware.py` : ajoute une balise script, sans requête SQL.
- `context_processors.py` : les compteurs de notifications et la période active sont paresseux (calculés seulement si le gabarit les affiche). Rien de coûteux.

## 4. Optimisations appliquées

| # | Changement | Fichiers |
|---|---|---|
| 1 | **Compression** des pages et des réponses JSON par l'application (les flux audio / événements passent tels quels) | `school_admin/compression_middleware.py`, `school/settings.py` |
| 2 | `collectstatic` crée une copie **`.gz`** de chaque CSS / JS ; cache de 30 jours quand WhiteNoise sert les fichiers | `school/settings.py` (`STORAGES`, `WHITENOISE_MAX_AGE`) |
| 3 | Fragment Nginx prêt à inclure (compression, `gzip_static`, HTTP/2) | `deploy/nginx/aria-static-compression.conf` |
| 4 | **Font Awesome hébergé sur le site** : police réduite aux icônes utilisées (150 Ko → 38 Ko), feuille de style réduite (102 Ko → 40 Ko, 8 Ko compressée). La police complète reste en secours pour une icône absente de la liste | `static/school_admin/vendor/fontawesome/`, 245 gabarits |
| 5 | **Polices Inter et Poppins hébergées sur le site** (mêmes fichiers que Google Fonts) | `static/school_admin/vendor/fonts/`, 222 gabarits, 2 CSS |
| 6 | Version JavaScript de Font Awesome (400 Ko) remplacée par la feuille de style sur les 15 pages d'impression | gabarits `imprimer_*`, `generer_*`, `bulletin_eleve.html`… |
| 7 | **Scanner QR chargé à la demande** : la bibliothèque (106 Ko) n'est téléchargée qu'à l'ouverture du scanner | `js/shared/qr_scanner_loader.js`, `connexion.html`, `header_directeur.html`, `pointage.html` |
| 8 | `chart.js` hébergé sur le site | `static/school_admin/vendor/chartjs/`, 10 gabarits |
| 9 | **Images allégées** : vignette de l'assistante 241 Ko → 3,5 Ko, logo de l'en-tête 26 Ko → 11 Ko, logo de la connexion 42 Ko → 2,3 Ko. Les fichiers d'origine restent en place | `img/aria-assistante-192.webp`, `img/logo_wordmark.webp`, `img/logo-256.webp`, 10 gabarits |
| 10 | `tabs_nav_overflow.js` téléchargé une seule fois (numéro de version unifié) | 10 gabarits |
| 11 | **Pastille « À faire »** : sur les pages suivantes d'une même visite, le nombre d'actions est réutilisé 30 secondes au lieu d'être recalculé | `api_views/context_popup_views.py`, réglage `CONTEXT_POPUP_TOTAL_TTL` |
| 12 | Année scolaire active lue une seule fois par page (en lecture seulement) | `utils/session_utils.py` |
| 13 | Script de l'assistante (79 Ko) chargé en différé : il ne retarde plus l'affichage du contenu de la page | 5 gabarits `assistant_vocal_*.html` |

Outils ajoutés : `scripts/build_vendor_assets.py` (reconstruit les polices et icônes locales), `school_admin/tests/test_perf_pages.py` (banc de mesure), `school_admin/tests/test_performance.py` (8 tests de non-régression).

Le banc contient aussi trois contrôles dans un vrai navigateur (`PERF_IMPRESSION=<dossier>`) : captures des pages d'impression, scanner QR de la direction, ouverture de l'assistante dans chaque espace.

Hôtes externes restants : `cdn.gtranslate.net` (traduction) et `www.gstatic.com` (Firebase), tous deux chargés après l'affichage.

## 5. Résultats après optimisation (3G lente, à froid)

| Espace | Page | Poids avant → après | Premier affichage | Chargement complet |
|---|---|---:|---:|---:|
| Connexion | `/connexion/` | 424 → 130 Ko | 6,0 → 2,2 s | 10,1 → 4,0 s |
| Direction | Tableau de bord | 1 171 → 348 Ko | 5,8 → 2,5 s | 25,4 → 8,8 s |
| Direction | Élèves | 1 140 → 281 Ko | 6,9 → 2,8 s | 24,9 → 7,8 s |
| Direction | Notes et résultats | 1 275 → 314 Ko | 9,1 → 3,3 s | 27,6 → 9,0 s |
| Direction | Suivi des présences | 1 291 → 318 Ko | 9,3 → 3,3 s | 28,1 → 8,7 s |
| Direction | Scolarité (comptabilité) | 1 217 → 305 Ko | 8,4 → 3,3 s | 26,5 → 8,6 s |
| Personnel | Tableau de bord | 1 183 → 353 Ko | 5,8 → 2,5 s | 26,0 → 8,7 s |
| Personnel | Élèves | 1 139 → 280 Ko | 6,9 → 2,9 s | 24,8 → 8,3 s |
| Professeur secondaire | Tableau de bord | 1 030 → 365 Ko | 6,3 → 2,9 s | 22,9 → 9,5 s |
| Professeur secondaire | Classes | 977 → 300 Ko | 6,4 → 2,9 s | 21,8 → 8,6 s |
| Professeur secondaire | Élèves | 1 050 → 319 Ko | 7,2 → 3,2 s | 23,3 → 9,0 s |
| Professeur primaire | Tableau de bord | 1 030 → 365 Ko | 6,3 → 3,0 s | 22,9 → 9,5 s |
| Professeur primaire | Classes | 975 → 299 Ko | 6,2 → 3,0 s | 21,6 → 8,5 s |
| Professeur primaire | Élèves | 1 045 → 317 Ko | 7,1 → 3,1 s | 23,2 → 9,0 s |
| Élève | Tableau de bord | 895 → 297 Ko | 5,1 → 1,9 s | 19,8 → 7,4 s |
| Élève | Emploi du temps | 824 → 228 Ko | 5,1 → 1,9 s | 18,3 → 6,6 s |
| Élève | Devoirs | 818 → 226 Ko | 5,1 → 1,9 s | 18,2 → 6,6 s |
| Parent | Tableau de bord | 768 → 215 Ko | 4,2 → 1,7 s | 17,0 → 6,3 s |
| Parent | Scolarité | 770 → 214 Ko | 4,1 → 1,8 s | 16,9 → 6,5 s |

- Toutes les requêtes ont abouti dans les trois séries de mesures (aucun échec, aucune erreur 4xx / 5xx).
- Deuxième visite (cache chaud) : 0,5 à 0,7 s, inchangé.
- Poids venant de CDN : 254 à 429 Ko → 39 Ko (12 Ko sur la connexion).
- Après le changement n° 13, mesuré à part sur les tableaux de bord : le contenu principal du tableau de bord de la direction s'affiche en **3,7 s** (6,0 s avant ce changement, 21,5 s au départ) ; les autres chiffres ne bougent pas.
- Le nombre de requêtes par page ne change pas (25 à 64) : les fichiers sont plus légers et viennent du même serveur, mais ils restent nombreux (voir § 7).

### Si la compression Nginx n'est pas activée (production laissée telle quelle)

| Page | Poids avant → après | Premier affichage | Chargement complet |
|---|---:|---:|---:|
| Connexion | 424 → 189 Ko | 6,0 → 3,6 s | 10,1 → 5,4 s |
| Direction — tableau de bord | 1 171 → 855 Ko | 5,8 → 6,1 s | 25,4 → 19,0 s |
| Direction — suivi des présences | 1 291 → 847 Ko | 9,3 → 9,7 s | 28,1 → 20,0 s |
| Professeur — tableau de bord | 1 030 → 822 Ko | 6,3 → 6,8 s | 22,9 → 18,7 s |
| Élève — tableau de bord | 895 → 683 Ko | 5,1 → 5,2 s | 19,8 → 16,0 s |
| Parent — tableau de bord | 768 → 425 Ko | 4,2 → 4,4 s | 17,0 → 9,8 s |

Le chargement complet gagne 20 à 40 %, mais le premier affichage ne s'améliore pas (0,1 à 0,6 s de plus) : les feuilles CSS du site partent encore non compressées. **C'est la compression qui apporte l'essentiel du gain.**

### Contrôle sur le serveur local avec les établissements de test (base `aria`)

Mesure faite le 15/11 sur `localhost:8000` après redémarrage, en se connectant avec les comptes du Lycée Les Palmiers (26 élèves) et de l'École Primaire Les Manguiers (voir `README_COMPTES_TEST.md`). Le temps serveur est la médiane de 5 chargements, sans bridage.

| Espace | Page | Temps serveur | HTML envoyé (compressé / d'origine) |
|---|---|---:|---:|
| Direction | Tableau de bord | 494 ms | 11,7 / 54 Ko |
| Direction | Élèves | 122 ms | 8,6 / 37 Ko |
| Direction | Notes et résultats | 462 ms | 22,0 / 492 Ko |
| Direction | Suivi des présences | 185 ms | 18,2 / 173 Ko |
| Direction | Scolarité (comptabilité) | 380 ms | 14,6 / 159 Ko |
| Personnel (secrétaire) | Tableau de bord | 421 ms | 10,6 / 46 Ko |
| Personnel (secrétaire) | Élèves | 128 ms | 7,9 / 32 Ko |
| Professeur secondaire | Tableau de bord / Classes / Élèves | 198 / 126 / 192 ms | 7,5 / 6,0 / 8,2 Ko |
| Professeur primaire | Tableau de bord / Classes / Élèves | 212 / 122 / 135 ms | 7,7 / 6,2 / 8,0 Ko |
| Élève | Tableau de bord / Devoirs / Emploi du temps | 153 / 106 / 217 ms | 6,0 / 5,2 / 4,9 Ko |
| Parent | Tableau de bord / Scolarité | 145 / 137 ms | 5,4 / 4,4 Ko |

- Les 18 pages répondent (code 200), sans requête en échec ; rendu contrôlé sur captures dans les quatre espaces (icônes, polices, logos, vignette de l'assistante, pastille « À faire »).
- La compression des pages compte beaucoup dès que les listes grossissent : « Notes et résultats » passe de 492 Ko à 22 Ko pour 26 élèves.
- Les temps serveur réels sont 3 à 15 fois plus élevés que sur le jeu de test du banc : le tableau de bord de la direction (494 ms) et « Notes et résultats » (462 ms) sont les deux pages à optimiser côté serveur en priorité.
- En 3G lente sur ce serveur de développement, le chargement à froid reste de 10 à 19 s (425 à 850 Ko) : en mode développement (`DEBUG=True`), Django sert les CSS / JS **non compressés**, comme la production tant que Nginx n'est pas réglé. Ces chiffres rejoignent le tableau « Si la compression Nginx n'est pas activée ».
- Le compte parent du lycée de test est refusé à la connexion (« Email ou mot de passe incorrect ») : l'espace parent a été mesuré avec le parent de l'école primaire.

### Serveur

| Mesure | Avant | Après |
|---|---:|---:|
| Appel « rappels », pages suivantes d'une visite | 20 à 45 requêtes SQL, 12 à 32 ms | 7 à 8 requêtes SQL, 4 à 6 ms |
| Appel « rappels », première page d'une visite | 23 à 49 requêtes SQL | inchangé (calcul complet) |
| Tableau de bord parent | 45 requêtes SQL | 38 |
| Tableau de bord direction | 149 requêtes SQL | 148 |
| Page de connexion (HTML envoyé) | 30,6 Ko | 7,5 Ko |

Les temps serveur des pages sont inchangés à la précision de la mesure.

## 6. À faire sur le serveur de production

1. **Nginx** : inclure `deploy/nginx/aria-static-compression.conf` dans le bloc `server {}` et ajouter `gzip_static on;` dans le bloc `location /static/`. Recharger Nginx. Vérification : `curl -sI -H "Accept-Encoding: gzip" https://aria-edu.com/static/school_admin/css/connexion_admin.css` doit afficher `Content-Encoding: gzip`.
2. Déploiement habituel avec `python manage.py collectstatic --noinput` : il crée désormais les fichiers `.gz`.
3. Recommandé : activer HTTP/2 dans Nginx. Avec 25 à 64 fichiers par page, une seule connexion partagée évite les files d'attente d'HTTP/1.1.

## 7. Ce qui n'a pas été fait (pistes suivantes)

- **Regrouper les feuilles CSS** : 20 à 30 fichiers CSS par page direction ou professeur. Les fusionner par espace réduirait les allers-retours, coûteux quand la latence est élevée.
- **Scripts placés dans le corps de page** sans `defer` (`aria_shell.js`, `realtime_client.js`, `realtime_page.js`, `directeur_live.js`) : ils retardent l'affichage du contenu situé après l'en-tête. Non modifiés, car les scripts propres à chaque page (`bulletins_live.js`, `liste_eleves_live.js`…) les appellent dès leur chargement ; à traiter page par page. Seul le script de l'assistante, autonome, a été différé.
- **Tableau de bord direction** : environ 150 requêtes SQL. Une mise en cache courte par indicateur serait efficace, mais afficherait des chiffres en retard de quelques secondes après une saisie : décision à prendre.
- **Firebase** (32 Ko, `www.gstatic.com`) et le widget de traduction restent externes. Pendant une des mesures, les deux fichiers Firebase n'ont pas répondu : la page était affichée et utilisable, mais son chargement complet est passé de 9,5 à 32 s. Héberger Firebase sur le site supprimerait ce risque (le service worker et `fcm_notifications.js` sont à adapter).
- `intl-tel-input`, `qrcodejs`, `bootstrap`, `apexcharts` restent servis par des CDN sur quelques pages secondaires.
- Pas de minification des CSS / JS (la compression en apporte l'essentiel).

## 8. Ce qui n'a pas pu être mesuré ou vérifié

- **Temps serveur avec de vraies données** : mesurés seulement sur les deux établissements de test de la base locale (26 élèves au plus). Aucune mesure sur un établissement de taille réelle (plusieurs centaines d'élèves), ni du nombre de requêtes SQL sur la base locale.
- **Production** : rien n'a été modifié ni mesuré en bridage sur `aria-edu.com` ; seuls ses en-têtes ont été lus. Le gain en production dépend du § 6.
- **Serveur local `localhost:8000`** : redémarré le 15/11 avec le nouveau code ; page de connexion et 18 pages privées contrôlées (voir § 5). Dans le panneau navigateur de l'application, l'enregistrement du service worker échoue alors qu'il s'active dans Chromium : cause non trouvée.
- **Rendu** : comparé par captures d'écran avant / après sur 19 pages, en mobile et en bureau : même mise en page, moins de 1 % de pixels différents (ordre des données de test, lissage du texte).
- **Pages d'impression** : 10 pages (certificats, attestations, fiches, bulletins, liste nominative, relevé) comparées entre la nouvelle police d'icônes et l'ancienne version JavaScript : toutes les icônes s'affichent, moins de 0,5 % de pixels différents. L'impression papier elle-même et les 5 autres pages concernées (convocations, liste de présence, bulletin côté élève, relevé côté enseignant) n'ont pas été vérifiées.
- **Scanner QR** : testé avec une caméra simulée sur la page de connexion et depuis l'en-tête de la direction (la bibliothèque se charge à l'ouverture, le scan démarre). Non testé sur un vrai téléphone ni sur la page de pointage des enseignants.
- **Assistante** : le panneau s'ouvre dans les quatre espaces avec le script différé ; la conversation vocale elle-même n'a pas été testée.
- **Pastille « À faire »** : le chiffre peut avoir jusqu'à 30 secondes de retard après une action faite ailleurs que dans la liste. La synthèse d'arrivée, la liste « À faire » et ses boutons restent calculés à chaque fois. `CONTEXT_POPUP_TOTAL_TTL=0` rétablit le recalcul à chaque page.
- **Icônes** : la liste des icônes gardées est déduite du code. Une icône dont le nom serait fabriqué par morceaux ne s'afficherait pas ; aucune n'a été trouvée. Après l'ajout d'une icône, relancer `scripts/build_vendor_assets.py` (un test le signale).
- **Tests** : `python manage.py check` passe. 213 tests lancés avec `--settings=school.test_settings` (rappels, parcours de toutes les pages primaire / secondaire, tableaux de bord, navigation professeur, pointage, fiche élève, sécurité, assistante, performance, logo) : 203 réussis, 6 ignorés (le banc de mesure, désactivé par défaut), **4 en échec**. Ces 4 échecs ne touchent pas des lignes modifiées ici : `test_prof_nav_auth_hotfix` bute sur `enseignant/justifications_notes.html`, déjà en erreur de syntaxe (« else » ligne 264) dans la version enregistrée du dépôt ; `test_prof_hub_nav_live` (2 tests) et `test_liste_responsive` vérifient le contenu de pages dont seules les adresses de polices et d'icônes ont changé. Ils n'ont pas pu être rejoués sur le code d'avant (interdiction d'annuler les modifications en cours), leur antériorité est donc déduite, pas démontrée. La suite complète du projet n'a pas été lancée.
- Deux autres gabarits sont en erreur de syntaxe sans lien avec ce chantier : `commercial/detail_message.html` et `enseignant/partials/header_enseignant.html`. Le texte parasite (`{% trans "` … `" %}`) qui s'affichait sur quatre pages d'impression a été retiré (voir § 9).

## 9. Pages d'impression : logo de l'établissement et corrections de rendu

Demande du 15/11 : afficher dans l'en-tête des pages d'impression le logo que l'établissement ajoute dans son profil (champ `logo` du modèle `Etablissement`), et corriger les écarts de rendu.

| Page | Avant | Après |
|---|---|---|
| Attestation de réussite, attestation de conduite, fiche d'inscription, fiches de la classe, certificat de radiation, liste nominative | pas de logo | logo au-dessus du nom de l'établissement |
| Certificat de scolarité | logo présent dans le code mais masqué par le CSS | logo affiché |
| Bulletin d'un élève, bulletins de la classe, relevé de notes | logo affiché (image d'origine) | logo affiché (version allégée) |

- **Poids** : une version réduite du logo (320 px au plus, JPEG, ou PNG s'il est transparent) est créée une fois dans `media/etablissements/logos/impression/` puis réutilisée. Dans le test, un logo de 3,1 Mo est servi en 14 Ko. Un logo de moins de 60 Ko est servi tel quel ; si la réduction n'allège rien, l'image d'origine est gardée.
- **Taille** : 72 px de haut au plus à l'écran, 18 mm à l'impression, proportions conservées. Dans les bulletins et le relevé, le logo reste dans sa pastille ronde de 80 px.
- **Sans logo** : aucun bloc, aucune image cassée, aucun espace vide sur les sept premières pages. Les bulletins et le relevé gardent leur pastille avec une icône d'école, comme avant. Si le fichier du logo a disparu du disque, la page se comporte comme sans logo.
- **Corrections de rendu** :
  - « None » s'affichait à la place du téléphone, de l'adresse ou de l'e-mail manquant sur six pages ;
  - une balise de traduction apparaissait en clair dans le texte du certificat de radiation ;
  - un reste de balise (`" %}`) s'affichait en bas des bulletins et du relevé de notes ; le même défaut est corrigé sur `directeur/secretaire/imprimer_liste_eleves.html`.
- **Fichiers** : `school_admin/templatetags/logo_tags.py`, `directeur/partials/_logo_entete_impression.html`, `css/directeur/entete_logo_impression.css`, les 10 gabarits, 6 tests dans `tests/test_performance.py`, un contrôle navigateur dans `tests/test_perf_pages.py` (`PERF_LOGO=<dossier>`).

Vérifié dans un navigateur, sur l'établissement du banc de test, avec un logo puis sans : les 10 pages, à l'écran et en rendu d'impression (dimensions, proportions, poids servi, absence d'image cassée, aucun « None » ni balise en clair dans le texte visible). Les icônes ont été recomparées avec l'ancien rendu JavaScript : aucune manquante.

Non vérifié : impression papier et export PDF réels ; un vrai logo d'établissement (aucun établissement de la base locale n'en a) ; l'envoi d'un logo depuis la page de profil. Les convocations et la liste de présence n'ont pas reçu le logo et affichent encore « None » quand un champ manque.
