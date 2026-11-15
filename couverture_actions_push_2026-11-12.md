# Vérification des actions et destinataires push — 12 novembre 2026

## Corrections appliquées

- Modification et annulation des évaluations primaire/secondaire : notifications de l'élève et de ses parents, selon inscription annuelle. Les sauvegardes sans changement ne notifient pas.
- Même mécanisme pour les changements de titre, consignes, date de rendu et annulation par désactivation d'un devoir.
- Suppression du double envoi de moyenne secondaire ; un seul service produit le push élève.
- Un seul appel familial par enfant dans les publications ; les destinataires parents sont sélectionnés par le service familial.
- Emplois du temps et bulletins ciblent les inscriptions de l'année de publication et l'établissement, pas la classe actuelle de l'élève.
- Confirmation du paiement à l'élève et aux parents, une seule fois malgré l'enregistrement ultérieur du numéro de reçu. Confirmation des créations d'inscription/réinscription (y compris celles issues de la validation d'une préinscription) ; absence de push vers une demande publique sans compte lié.
- Notification lors d'un changement de choix de frais ; les choix obligatoires initiaux ne génèrent pas cette notification. L'enregistrement groupé des choix et charges est atomique.
- Un lien familial explicitement désactivé n'est plus contourné par le champ parent_inscripteur ; compatibilité maintenue uniquement pour les anciennes données sans aucun lien enregistré pour ce parent.
- Clé de déduplication unique par événement et destinataire dans PushDelivery (migration 0247). Les publications possédant un identifiant métier sont dédupliquées sur leurs données et leur contenu ; les nouvelles confirmations portent un event_key explicite.

Tests transactionnels annulés : ciblage annuel malgré une classe actuelle différente, liens parentaux répétés, déduplication de l'événement, modification/annulation d'évaluation primaire et secondaire, sauvegarde inchangée silencieuse, paiement confirmé une seule fois et notification de changement de frais. Contrôles Django et migrations réussis. Aucun message réel envoyé. La réception sur appareil, les changements faits par mise à jour SQL/QuerySet.update (qui ne déclenchent pas les signaux Django) et les suppressions physiques de devoirs restent hors de ces scénarios.

La matrice ci-dessous décrit les constats initiaux de la vérification, avant ces corrections.

La configuration technique d'envoi ne garantit pas la couverture de chaque action métier. Vérification du code actuel des vues primaire/secondaire, services de notifications et tâches de publication. Aucun message réel envoyé et aucun code métier modifié pendant ce contrôle.

| Action | Destinataires raccordés | Verdict du branchement |
|---|---|---|
| Création évaluation primaire/secondaire | Élèves inscrits à la classe/année et parents via services | Présent ; inscription annuelle utilisée lorsque disponible |
| Modification/suppression évaluation | Pas de hook de notification trouvé dans les fonctions de modification/suppression examinées | Manquant : changement ou annulation à annoncer |
| Exercice maison primaire/secondaire | Élèves et parents de la classe | Création raccordée ; modification/annulation à recetter séparément |
| Nouvelle note primaire/secondaire | Élève et parents liés | Services raccordés |
| Publication moyenne secondaire | Élève et parents | Doublon élève : envoi Firebase direct puis notify_note, qui envoie aussi un push |
| Publication bulletin | Élèves de classe et parents | Présent ; sélection par Eleve.classe au lieu de l'inscription annuelle ; doublons possibles parent |
| Publication emploi du temps | Professeurs ayant des créneaux, élèves de classe et parents | Présent ; sélection des élèves par classe actuelle ; doublons possibles parent |
| Présence, absence, retard | Élève concerné et parents | Présent ; envoi élève direct et création in-app distincte, ce dernier service n'envoie pas un second push dans ce circuit |
| Sanction primaire/secondaire | Élève, parents et direction | Présent ; le push élève direct est complété par une notification in-app sans second push dans notify_sanction |
| Convocation direction | Élève convoqué et parents | Les deux services sont appelés et demandent un push |
| Justification de note soumise | Direction | Tâche et service présents |
| Note justifiée/modifiée par direction | Élève et parents | Services appelés dans les deux circuits examinés |
| Relevé de notes soumis par professeur | Direction | Service appelé au primaire et secondaire |
| Annonce publiée | Rôles ciblés dans l'établissement | Présent ; doublons parents possibles |
| Relance scolarité | Parents de l'élève ayant un reste | Push raccordé lors de la configuration précédente |
| Paiement reçu, choix de frais modifié, validation inscription/préinscription | Aucun événement push systématique démontré dans les chemins examinés | À compléter si information attendue pour famille |
| Personnel secrétaire/comptable | Aucun service métier dédié trouvé | Ne pas assimiler au destinataire Etablissement de la direction |

## Défauts confirmés dans le code

1. `enseignant_view.py` autour de 5094 : envoi direct de la moyenne à l'élève puis `EleveNotificationService.notify_note` autour de 5102. Ce service demande lui aussi un push. Deux jobs pour une information.
2. `notification_tasks.py::_notify_parent_links` parcourt chaque lien familial et appelle `ParentNotificationService.notify_custom` pour l'enfant. Ce service retrouve tous les parents de cet enfant. Avec deux liens actifs, chacun est donc notifié deux fois. Dédupliquer les enfants avant l'appel ou notifier exclusivement le parent du lien.
3. Emploi du temps et bulletin utilisent `Eleve.objects.filter(classe=classe, actif=True)` et `LienFamilial(eleves__classe=...)` (filtre réel : eleve__classe). L'année de publication n'est pas utilisée pour déterminer l'inscription. Après changement de classe ou consultation d'une ancienne année, les destinataires peuvent être incomplets ou incorrects.
4. Les fonctions `modifier_evaluation_enseignant`, `supprimer_evaluation_enseignant`, `modifier_evaluation_primaire` et `supprimer_evaluation_primaire` ne contiennent pas les hooks de notification recherchés, contrairement aux fonctions de création.
5. Pas d'identifiant métier unique empêchant deux traitements du même événement de générer deux envois. La file persistante protège l'exécution d'un job, pas la création répétée d'événements identiques.

## Ciblage à retenir

Événement individuel : uniquement l'élève concerné et ses responsables actifs/autorisés. Événement de classe : élèves inscrits dans cette classe pour l'année de l'événement et leurs responsables ; professeurs affectés seulement lorsque l'action les concerne. Événement de direction : rôles habilités de cet établissement. Aucun brouillon ne doit annoncer une publication ; une modification ou annulation doit reprendre l'événement initial et sa nouvelle version.

## Limites

Analyse des branchements et des filtres, sans exécuter chaque formulaire avec un vrai appareil. Les événements considérés comme obligatoires pour les familles doivent être explicités pour les opérations administratives et financières ; le fait qu'une action existe n'implique pas qu'un push soit souhaitable à chaque sauvegarde. Réception réelle et recette exhaustive de tous les scénarios restent nécessaires.
