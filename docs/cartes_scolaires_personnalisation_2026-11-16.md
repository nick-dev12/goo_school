# Cartes scolaires — personnalisation commune et aperçu mobile

## Parcours

- `/cartes-identite/eleves/` : retrait des statistiques globales, des boutons « Gestion des élèves », « Gestion administrative » et « Imprimer la liste nominative ».
- « Imprimer toutes les cartes » et « Voir » naviguent dans le même onglet, y compris depuis la fiche mobile de l'élève.
- « Personnaliser » est placé sur la même ligne que « Imprimer toutes les cartes » pour chaque classe.
- `/cartes-identite/classe/<id>/` : aperçu du recto et du verso adapté à la largeur disponible, retrait de l'ancien éditeur et de ses boutons.
- `/cartes-identite/personnaliser/` : formulaire commun à l'établissement (pays, devise nationale, titre, devise de l'établissement), aperçu fictif d'une seule carte avec choix recto/verso et mise à jour immédiate pendant la saisie. Le motif DÉMO n'est pas un QR code d'identification.

## Enregistrement

La page réutilise `CarteIdentitePersonnalisation`, déjà lié à un établissement par une relation unique : aucune migration. Après enregistrement, les valeurs s'appliquent aux cartes individuelles, à toutes les cartes de classe et à la carte affichée dans le profil élève. Les droits restent limités à la direction et au secrétariat de l'établissement connecté.

Les champs sont obligatoires et limités à 255 caractères. Les valeurs sont affichées avec l'échappement HTML de Django ; la prévisualisation JavaScript utilise `textContent`.

## Vérification

- 6 tests ciblés passent via `python manage.py test school_admin.tests.test_cartes_personnalisation.CartesPersonnalisationTests --settings=school.test_settings` : aperçu fictif, propagation et persistance, formulaire invalide, refus professeur, secrétaire et isolation entre établissements, liens dans le même onglet.
- `python manage.py check --settings=school.test_settings` passe.
- Contrôles navigateur sur l'établissement supérieur de test : liste simplifiée, boutons sur la même ligne à 390 px, navigation « Voir » depuis le modal mobile et impression de classe dans l'onglet courant.
- Aperçu de classe vérifié à 320, 390 et 472 px, sans débordement horizontal ; nouvelle page vérifiée sur mobile et à 1200 px, aperçu en direct et bascule recto/verso.
- Les règles physiques d'impression restent inchangées : 85,6 × 53,98 mm. Les changements de largeur et de zoom de la classe sont exclusivement chargés avec `media="screen"`. Impression papier non effectuée.
- L'enregistrement a été testé dans la base en mémoire ; les valeurs du compte local n'ont pas été remplacées par les exemples saisis pendant la vérification visuelle.

Captures dans `tmp/verification_cartes_personnalisation/`.

## Deux modèles et couleurs

Ajout des modèles **Classique** et **Moderne** (bandeau plein, en-tête aligné à gauche, photo arrondie et détails de couleur secondaire). Quatre sélecteurs règlent les couleurs principale, secondaire, du fond et du texte. Le texte du bandeau moderne passe automatiquement en blanc ou en foncé pour contraster avec la couleur principale. Le QR code conserve son fond blanc.

Le choix et les couleurs sont persistés sur le même réglage par établissement et repris par les cartes individuelles, les cartes de classe et le profil élève. Les couleurs sont strictement validées au format `#RRGGBB`, y compris avant leur insertion dans les variables CSS. L'aperçu réagit immédiatement, sans enregistrement.

Migration additive `0252_carte_modeles_couleurs` appliquée à la base locale (5 nouveaux champs). Le contrôle global `makemigrations --check --dry-run` relève uniquement un écart préexistant concernant les modèles Budget, MessageCommercial et ReponseMessage ; aucune suppression de ces modèles n'a été générée ni exécutée.

8 tests ciblés : persistance et propagation du modèle et des couleurs, rejet des couleurs et modèles invalides, contraste, sécurité, accès et séparation des établissements. Le contrôle système exécuté par le runner de tests passe.

Contrôles visuels : modèle moderne vert/or au recto et au verso, quatre sélecteurs, aperçu mobile et bureau. Les valeurs vert/or utilisées pour la démonstration n'ont pas remplacé les réglages enregistrés du compte local. Dimensions physiques d'impression conservées ; impression papier non effectuée.
