# Contacts au verso des cartes — 17 novembre 2026

Ajout du téléphone de l’établissement et du parent/tuteur au verso partagé des cartes individuelles et dans les cartes de classe, pour tous les modèles.

Le parent lié actif, validé et disposant d’un téléphone est prioritaire. Le parent inscripteur est choisi en premier, puis le premier lien par identifiant. À défaut, utilisation du téléphone parent de la fiche élève ; sinon affichage « Non renseigné ». Le numéro de l’établissement vient du champ telephone, sans substitution par le téléphone du directeur.

Les liens familiaux sont préchargés en une requête pour l’ensemble d’une classe : pas de requête supplémentaire par élève. Aucune migration ni modification des données locales.

L’aperçu utilise un numéro parent fictif. L’élève 375 affiche son contact parent ; le téléphone de son établissement est absent et apparaît donc comme non renseigné.

Vérifications : douze tests réussis avec `python manage.py test school_admin.tests.test_cartes_personnalisation --settings=school.test_settings`. Couverture des deux pages, de la priorité du lien, du repli et du chargement groupé. `python manage.py check` passe. Navigateur : contacts visibles sur la carte 375, aucun débordement du verso ou des contacts à 390 px. Capture : tmp/verification_cartes_personnalisation/verso_contacts.jpg.

Le format d’impression reste inchangé ; styles des contacts adaptés à l’impression. Aucune impression physique réalisée.

## Indicatifs des pays

Les deux contacts sont formates selon le pays de l’etablissement (code ISO ou nom pris en charge), uniquement a l’affichage. Les numeros commencant par + sont conserves ; 00 devient +. Les pays inconnus conservent leur numero sans ajout arbitraire. Le Senegal affiche ainsi +221 770001122 sur la carte 375. Les valeurs absentes restent « Non renseigné ».

Treize tests reussis apres cette modification, dont les formats locaux, +, 00, indicatif deja saisi, pays inconnu, France et Cote d’Ivoire. Controle navigateur de la carte 375 : +221 visible. Capture : tmp/verification_cartes_personnalisation/verso_indicatif.jpg.
