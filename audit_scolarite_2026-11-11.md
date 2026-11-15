# Audit scolarité — 11 novembre 2026

## Corrections appliquées après audit

Les sept défauts ci-dessous ont été traités : paiements conservés lors des baisses (montant de la charge plafonné vers le bas au déjà payé, sans remboursement ou crédit automatique), décision individuelle limitée au code visé, anciennes charges laissées en attente de décision, marqueur distinguant liste vide et formulaire absent pour la préinscription, échéance des nouvelles activations à 30 jours après la date de référence ou aujourd'hui si elle est passée, erreurs comptables propagées avec annulation du paiement, verrou de ligne et nouvelle vérification du solde pour les paiements annexes.

Les tests transactionnels confirment la préservation du choix cantine lors de l'activation du transport, le maintien des paiements après baisse, l'échéance future, et l'annulation conjointe du versement et du reçu après panne comptable simulée. Les cinq pages HTTP direction/parent/élève passent. Aucun test de paiement simultané en deux processus ni envoi réel de relance n'a été effectué. Les échéances déjà enregistrées ne sont pas reportées automatiquement.

Les constats suivants décrivent l'état initial de l'audit.

Verdict : les branchements principaux existent, mais le système ne doit pas encore être considéré comme entièrement validé.

## Défauts confirmés

1. **Critique — baisse de tarif modifiant le paiement enregistré.** `utils/frais_annexes.py`, `appliquer_nouveau_montant` remplace `montant_paye` par le nouveau montant lorsque le paiement le dépasse. Reproduction en mémoire : 8 000 payés deviennent 5 000 après baisse du tarif à 5 000. Le reçu n'est pas corrigé avec cette valeur : incohérence entre charge et versements.
2. **Élevé — action individuelle affectant les autres frais.** `controllers/comptabilite_controller.py`, `gerer_choix_frais_annexes_directeur` appelle la fonction de remplacement de tous les choix pour activer/désactiver un seul code. Test HTTP : activer transport transforme une cantine non choisie en refus et supprime sa charge impayée. Il faut modifier uniquement le choix ciblé.
3. **Élevé — régression de la transition explicite.** `utils/frais_annexes.py`, `synchroniser_frais_annexes_eleve` réinscrit automatiquement l'élève lorsqu'une ancienne charge ouverte existe sans choix. L'ancienne dette est conservée, mais la décision devient automatique contrairement au plan validé.
4. **Élevé — tout décocher dans une préinscription rétablit les anciens choix.** `controllers/preinscription_controller.py`, lignes 508–510 : une liste POST vide est remplacée par les choix initiaux. Il faut distinguer formulaire soumis vide et information absente.
5. **Échéances — activation tardive potentiellement immédiatement en retard.** `date_echeance_frais_annexe` fixe un frais annuel au début d'année + 30 jours. Exemple : début 1er septembre, échéance 1er octobre, même lors d'une activation en novembre. La règle métier doit être précisée ; risque de relance immédiate.
6. **Comptabilité générale — échec de liaison masqué.** Le paiement annexe appelle `pont_paiement_eleve` dans un `try/except` qui ignore toute exception. Un reçu peut être enregistré alors que l'écriture comptable correspondante échoue. Défaut de gestion d'erreur constaté dans le code ; aucune panne comptable volontaire n'a été déclenchée.
7. **Concurrence des paiements.** Le paiement annexe vérifie le reste avant la transaction puis modifie la charge sans verrou de ligne. Deux paiements simultanés peuvent passer la même vérification. Risque établi par lecture du code, non reproduit en concurrence.

## Contrôles réussis

Tests transactionnels sur des données temporaires, intégralement annulés :

- Aucun frais au choix créé sans sélection.
- Sélection : création de la charge au montant configuré.
- Refus sans paiement : suppression et absence de recréation à la synchronisation.
- Refus après paiement partiel : statut clos, paiement conservé, reste nul.
- Totaux de la comptabilité élève équilibrés après clôture.
- Charge close exclue du résumé de dette utilisé par les relances.
- Parcours sans sélection explicite : choix refusé préservé.
- Réponses HTTP 200 : paramètres, liste scolarité, fiche comptable, espace élève, espace parent.
- Contrôle Django sans erreur ; migrations 0243, 0244 et 0245 appliquées.

## Branchements examinés

- Inscription et réinscription : cases selon classe, transmission des codes au service de création des frais.
- Préinscription : JSON des choix conservé dans la demande, sélection par classe et transmission lors de la validation ; défaut de liste vide ci-dessus.
- Exemptions : choix indépendant par élève/année/code, clôture des charges payées et conservation des versements.
- Affichages direction : fiche détaillée et totaux ; parent/élève : résumé commun de dette ; reçus parent récupérés séparément.
- Relances : résumé excluant les charges closes, vérification du reste, délais avant/après échéance, prévention des doublons journaliers automatiques.

## Limites de validation

Les tests HTTP vérifient le rendu serveur, pas l'apparence visuelle sur chaque taille d'écran. Les formulaires complets d'inscription et réinscription n'ont pas été soumis avec tous leurs documents. Aucun WhatsApp ni notification réelle n'a été envoyé. La présence de la commande `envoyer_relances_impayes` ne prouve pas sa planification effective sur le serveur. La cohérence des écritures comptables réelles et les paiements simultanés restent à tester avec des scénarios dédiés. L'audit couvre le code actuel et un établissement primaire de démonstration, pas tous les établissements en base.

Aucun tarif, choix ou paiement de test n'a été conservé. Aucun code métier n'a été modifié pendant cet audit.
