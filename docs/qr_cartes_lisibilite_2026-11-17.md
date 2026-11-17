# Lisibilité des QR des cartes — 17 novembre 2026

## Changements

Le QR affiché était très dense. Les cartes individuelles, de classe et du profil élève utilisent désormais un SVG noir sur fond blanc généré à partir de l’adresse de vérification actuelle. Cela remplace également les anciennes images éventuellement chargées de données JSON, sans modification en base.

- Adresse courte `/q/<identifiant>/`, identifiant inchangé. Ancienne route conservée pour les cartes déjà imprimées.
- Correction d’erreur M au lieu de H : compromis permettant moins de modules et des cases plus grosses à taille égale. Une augmentation des pixels du PNG seule ne changeait pas la densité réelle.
- Marge blanche de quatre modules et fond blanc explicite, indépendants des couleurs du modèle.
- SVG vectoriel net au redimensionnement. Cache mémoire limité à 512 rendus par processus, sans données nominatives dans le contenu encodé.
- Génération des futurs PNG alignée sur M et quatre modules.
- Zone QR imprimée portée à 18 × 18 mm ; format physique de carte inchangé. Colonnes d’information doubles réparties sur deux lignes en impression pour dégager la place.

## Vérifications

`python manage.py check` : aucun problème.

`python manage.py test school_admin.tests.test_cartes_personnalisation --settings=school.test_settings` : dix tests réussis. Le nouveau test vérifie l’adresse courte, les deux routes de vérification compatibles, l’identifiant inchangé, le fond blanc SVG et une matrice moins dense qu’avec l’ancienne configuration pour une adresse témoin.

Navigateur sur la carte élève 375 : image SVG chargée, aucun débordement horizontal de page. Capture : `tmp/verification_cartes_personnalisation/qr_vectoriel.jpg`.

## Limites

Aucun scan physique, aucune impression papier ni simulation du rendu imprimé n’ont été réalisés. Une validation sur imprimante et téléphone reste nécessaire, notamment après réduction supplémentaire du document. L’adresse SITE_URL doit désigner le domaine accessible aux téléphones en production ; une adresse localhost ne peut pas servir de destination à un autre appareil. Le QR fictif de personnalisation reste volontairement non scannable.
