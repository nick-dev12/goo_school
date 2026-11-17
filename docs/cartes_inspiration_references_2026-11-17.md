# Trois compositions supplémentaires inspirées des références

Ajout d'Élan, Campus et Prisme dans la galerie, soit sept modèles au total.

- Élan : titre dans un cartouche, photo rectangulaire à gauche, fond discret et pied de carte courbe.
- Campus : bandeau haut arrondi, photo à droite, identité au centre et QR à gauche.
- Prisme : photo plus grande à gauche, diagonales sur le corps et bandeau bas contrasté.

Les références de l'utilisateur ont servi à distinguer les compositions. Aucun logo, cachet ni portrait des références n'est réutilisé : les cartes reprennent les données et images de l'établissement. La personnalisation des couleurs est conservée, tout comme les contours extérieurs d'une seule couleur.

La migration `0254_carte_elan_campus_prisme` élargit les choix du modèle et est appliquée localement. Les réglages enregistrés du compte local sont conservés ; seules les prévisualisations ont changé pendant la vérification.

Validation :

- `python manage.py check` passe.
- Les neuf tests ciblés de `school_admin.tests.test_cartes_personnalisation.CartesPersonnalisationTests` passent avec `--settings=school.test_settings`. Le test de propagation couvre désormais les cinq modèles ajoutés depuis Classique et Moderne.
- Aperçus réels à 1200 px : les informations ne débordent pas de leurs lignes, photo et QR occupent les emplacements prévus.
- Recto et verso vérifiés à 390 px, sans débordement horizontal.
- Dimensions d'impression conservées à 85,6 × 53,98 mm. Grilles et tailles typographiques adaptées au média print, avec un emplacement de QR de 55 px. L'impression papier et la lecture d'un QR imprimé ne sont pas vérifiées.

Capture : `tmp/verification_cartes_personnalisation/galerie_inspiration_references.png`.
