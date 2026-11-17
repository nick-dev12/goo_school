# Galerie de modèles de carte scolaire — 17 novembre 2026

La personnalisation propose quatre modèles : Classique, Moderne, Horizon et Signature. Horizon utilise un bandeau diagonal et une photo aux coins décalés ; Signature privilégie un en-tête clair, un médaillon photo et des filets fins.

Le bouton « Choisir un modèle » ouvre un dialogue natif avec les quatre aperçus, les informations fictives et les couleurs courantes de l'établissement. Les miniatures sont créées à l'ouverture à partir du composant réel du recto : pas d'images distantes ni de copie d'informations d'élèves réels.

Le choix actualise l'aperçu et ferme le dialogue. Fermer avec la croix, Échap ou en cliquant sur l'arrière-plan ne change pas le modèle. Le focus revient au bouton d'ouverture. Sur mobile, une colonne et un défilement interne permettent de voir tous les modèles ; le titre et la fermeture restent accessibles. Le bouton Enregistrer applique ensuite le modèle aux cartes de tout l'établissement.

Migration `0253_carte_horizon_signature` appliquée localement : elle élargit uniquement la liste des choix, sans changer les données existantes. Les contours extérieurs conservent une couleur unique et les dimensions physiques d'impression restent de 85,6 × 53,98 mm.

Vérifications :

- `python manage.py check` : réussi.
- 9 tests ciblés via `python manage.py test school_admin.tests.test_cartes_personnalisation.CartesPersonnalisationTests --settings=school.test_settings` : réussis, y compris la persistance et la propagation des deux nouveaux modèles.
- Navigateur : galerie et miniatures à 1100 px et 390 px, sélection d'Horizon puis de Signature, couleurs conservées, aperçu recto/verso, fermeture avec Échap et restauration du focus.
- Les choix effectués lors du contrôle visuel n'ont pas été enregistrés sur le compte local. L'impression papier n'a pas été effectuée.

Capture : `tmp/verification_cartes_personnalisation/galerie_quatre_modeles.png`.
