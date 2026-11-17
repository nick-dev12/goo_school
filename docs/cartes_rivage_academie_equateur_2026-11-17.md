# Nouveaux modèles de cartes scolaires — 17 novembre 2026

Trois modèles inspirés des références fournies complètent la galerie : dix modèles au total.

- **Rivage** : ruban géométrique latéral, fond clair et portrait encadré.
- **Académie** : grand portrait, présentation institutionnelle et bandeau au nom de l’établissement.
- **Équateur** : cadre arrondi de couleur uniforme, titre en cartouche et bandeau inférieur.

Les quatre couleurs restent personnalisables. Les styles sont partagés entre l’aperçu fictif, la carte individuelle, les cartes de classe et le profil élève. Le choix enregistré est propre à l’établissement.

## Vérifications réalisées

- Migration locale `0255_carte_rivage_academie_equateur` appliquée après autorisation explicite de l’utilisateur ; changement des choix du champ uniquement.
- Contrôle navigateur des dix modèles, recto et verso, aux largeurs 390 et 1 200 px : vingt combinaisons. Aucun débordement horizontal de page, aucune image manquante, aucune superposition du QR avec les informations, aucun enfant du verso dépassant la carte. Les quatre côtés du contour ont la même couleur.
- Un débordement de texte de l’ancien modèle Signature a été détecté puis corrigé en répartissant les informations doubles sur deux lignes ; nouveau contrôle à 390 px sans débordement.
- Inspection visuelle des trois nouveaux modèles dans l’aperçu. Les changements de sélection effectués pour ces contrôles n’ont pas été enregistrés sur le compte local.
- `python manage.py check --settings=school.test_settings` : aucun problème.
- `python manage.py test school_admin.tests.test_cartes_personnalisation.CartesPersonnalisationTests --settings=school.test_settings` : neuf tests réussis, base de test en mémoire. Couverture des choix, couleurs, sauvegarde, propagation aux pages et restrictions d’accès.
- `git diff --check` : aucune erreur de contenu ; avertissement Git de conversion LF/CRLF sur un fichier existant.

Le runner signale l’absence du dossier `staticfiles` dans cet environnement de test, sans faire échouer les tests.

## Impression et limites

Le format physique existant 85,6 × 53,98 mm reste défini dans les styles d’impression ; les nouveaux modèles disposent d’ajustements typographiques dédiés. Aucune impression physique ni export PDF contrôlé n’a été réalisé. La lecture réelle des QR codes n’a pas été testée ; le QR de l’aperçu est volontairement fictif. Les contrôles responsive portent sur les informations fictives de l’aperçu, pas sur toutes les longueurs possibles de données réelles.

Les relevés initiaux sont conservés dans `tmp/verification_cartes_personnalisation/controle_10_modeles.json` (ils incluent le débordement Signature avant correction). Une capture d’Équateur est disponible dans le même dossier sous `equateur.jpg`.
