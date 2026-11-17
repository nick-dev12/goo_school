# Carte d'identité : aperçu mobile (16 novembre 2026)

Page vérifiée : `/carte-identite/eleve/375/` (établissement supérieur de test).

La largeur minimale de 480 px de la carte provoquait un débordement horizontal sur téléphone. Un aperçu réduit proportionnellement à la largeur disponible est désormais appliqué à cette page. Le recto et le verso s'empilent sur les petits écrans ; les boutons et les titres restent lisibles à leur taille normale.

La feuille supplémentaire est chargée avec `media="screen"`. Elle utilise une variable calculée par `ResizeObserver` pour le zoom des cartes. Les styles partagés existants et leurs règles d'impression ne sont pas modifiés : format conservé de **85,6 × 53,98 mm**, A4 portrait.

Vérification dans le navigateur : largeurs 320, 360, 390, 430, 768 et 1366 px, sans débordement horizontal. À 390 px, chaque face occupe 344 px. À 1366 px, les deux faces de 480 px restent côte à côte. Photo, informations et QR code visibles.

Capture : `tmp/verification_carte_mobile/carte_390.png`.

Les règles d'impression chargées dans le navigateur ont été contrôlées. L'interface d'impression du navigateur intégré n'a pas pu être inspectée (expiration de la commande lors de l'ouverture) ; aucune impression papier effectuée.

`python manage.py check --settings=school.test_settings` passe. Le contrôle avec les paramètres de développement n'a pas retourné de résultat pendant cette vérification. Aucun test d'écriture sur la base locale exécuté.
