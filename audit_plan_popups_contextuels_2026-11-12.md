# Audit et plan des popups contextuels Aria

Date : 12 novembre 2026. Statut : proposition avant développement.

## Mise en place réalisée après validation

Fréquence ajustée à la demande : une synthèse par visite, avec réapparition au retour sur le site même sans reconnexion. La fermeture/réouverture d'onglet, le retour depuis l'extérieur et le retour après masquage de l'onglet renouvellent la visite. Les navigations internes et rechargements gardent la visite ; le report volontaire reste respecté. Le composant est également présent dans les pages privées ordinaires, hors API, authentification, reçus, impressions et exports. Test transactionnel : même visite silencieuse, nouvelle visite visible, report conservé.

Le moteur, le composant partagé, les API et l'historique serveur sont maintenant développés. Migration 0248 installée. Branchement sur les dashboards direction, professeur primaire/secondaire, parent, élève et personnel administratif (dont secrétaire/comptable selon les droits disponibles).

Situations livrées : devoirs à rendre sous trois jours, évaluations proches, convocations sous sept jours, échéances parentales réellement ouvertes sous trois jours ou dépassées, notifications récentes autorisées, demandes direction en attente, dossiers de recouvrement accessibles au personnel autorisé et inscriptions récentes pour le secrétariat habilité. Les cartes récentes sans situation utile ne sont pas remplacées par un message artificiel.

La fenêtre affiche au maximum trois cartes, une seule fois par connexion. Consultation, fermeture et report sont disponibles. Les informations présentées sont persistées par utilisateur et type de compte ; un changement significatif peut réactiver une carte, une diminution de la liste de dossiers ne crée pas seule une nouveauté. La lecture des cartes ne marque pas les notifications comme lues. Les actions sont revalidées au moment du clic. L'API est authentifiée, protégée par CSRF pour les écritures et sans cache.

Tests transactionnels : cinq rôles, visite concurrente simulée par deux réservations, reconnexion sans répétition, changement de version, report, action d'une ancienne connexion rejetée, situation résolue rejetée et personnel sans droits. Le test ne remplace pas une charge simultanée en plusieurs processus. Données de test annulées.

Vérification navigateur : popup direction sur deux dossiers réels en retard, bouton vers la liste des impayés et absence de nouvelle fenêtre au retour à l'accueil. Design à fonds unis, accessible au clavier, adapté à la largeur et respectant la réduction d'animations. Le centrage a été ajusté après inspection visuelle.

Les espaces internes support/commercial/RH de la plateforme et les situations dont la source métier n'est pas suffisamment définie (par exemple un « appel manquant » sans horaire vérifiable) ne reçoivent pas de cartes inventées. Le système peut être étendu avec un fournisseur supplémentaire. Les modifications de planning purement push sans notification persistante dédiée ne sont pas converties en une carte détaillant un ancien/nouveau créneau absent de la base.

Le reste du document conserve l'audit et le plan initiaux.

## 1. Objectif

À l'arrivée dans son espace après connexion, présenter à l'utilisateur les informations récentes qui le concernent et une action utile. Le contenu provient des données réelles : publication, échéance, convocation, demande à traiter, changement de situation. Aucun message de remplissage si rien ne justifie une interruption.

Le système doit distinguer une nouveauté, une action encore en attente et une urgence qui vient de changer de niveau. Un changement cosmétique ou une simple reconnexion ne rend pas une information nouvelle.

## 2. Audit de l'existant

| Espace / source examinée | Données réutilisables | Point d'intégration proposé |
|---|---|---|
| Direction : services/dashboard/context.py, executive.py, alerts.py, today.py, activity.py | Alertes, tâches, activité, contexte année et établissement, permissions | Tableau de bord directeur et shell partagé |
| Direction : services/hubs_directeur.py | Demandes de liaison, préinscriptions, classes incomplètes, liens d'action selon permissions | Fournisseurs de situations ; réutiliser les règles d'accès et URLs |
| Professeurs : services/dashboard/teacher.py ; vues enseignant primaire/secondaire | Évaluations à venir, classes affectées, relevés, emploi du temps | Tableaux de bord primaire/secondaire, en-têtes enseignants |
| Élève : services/dashboard/student.py ; personal_views/eleve_view.py | Notes publiées, devoirs, évaluations, emploi du temps, convocations, alertes | Dashboard élève et shell élève |
| Parent : personal_views/parent_view.py ; services/parent_dashboard.py | Enfants liés, classe annuelle, notifications par enfant, assiduité, dette et échéance | Dashboard parent ; synthèse regroupée par enfant |
| Scolarité : services/recouvrement.py | Charges réelles, reste, prochaine échéance, moratoire | Source unique pour les alertes financières |
| Notifications : modèles parent/élève/professeur/direction et PushDelivery | Événements persistants, publication, destinataire, lien métier | Complément aux données métier, avec déduplication |
| Secrétariat : personal_views/secretaire_view.py | Dossiers et opérations d'inscription accessibles | Dashboard secrétaire et permissions du personnel |
| Comptabilité : personal_views/comptable_view.py, interfaces de caisse/direction | Encaissements, échéances et dossiers selon périmètre | Fournisseur distinct selon fonction et établissement |
| Personnel administratif : personal_views/personnel_administratif_view.py | Dashboard et permissions propres à la fonction | Adapter les règles à la fonction, pas seulement au nom du dashboard |

La recherche ciblée n'a pas révélé de moteur partagé de popups contextuels avec historique serveur par personne et version d'information. Les fenêtres de formulaires, menus et sélecteurs existants remplissent d'autres fonctions. Un historique localStorage seul ne couvrirait ni plusieurs appareils, ni les changements de compte.

Les espaces internes support/RH/commercial/administration plateforme possèdent aussi des dashboards. Leurs données et autorisations doivent avoir leurs propres fournisseurs si ces espaces font partie du déploiement ; les règles d'établissement ne doivent pas leur être appliquées automatiquement.

### Risques observés à prendre en compte

- Les tableaux de bord construisent déjà plusieurs agrégats : éviter de recalculer tous les graphiques pour ouvrir une fenêtre.
- Certaines pages de notifications marquent les éléments comme lus lors de leur consultation. La lecture des données pour un popup devra être sans cet effet de bord.
- Les données financières et familiales doivent garder leurs filtres d'année, d'établissement et de liens actifs. Ne pas se fier uniquement à la classe actuelle ou à un montant configuré pour le groupe.
- Les différentes interfaces ont plusieurs shells : un composant unique devra être branché sur les entrées réellement utilisées, y compris les variantes primaire/secondaire et le personnel.
- Les notifications push peuvent déjà informer du même événement : leur réception ne constitue pas une preuve que le contenu a été consulté. Prévoir un état de consultation commun, sans déduire « vu » du seul statut FCM envoyé.

## 3. Situations proposées par espace

Les lignes suivantes constituent les règles envisagées ; leur présence dans ce document ne signifie pas qu'elles sont déjà développées.

| Espace | Situation concrète | Contenu et bouton |
|---|---|---|
| Direction | Nouvelles préinscriptions ou demandes de liaison depuis la dernière consultation | Nombre et ancienneté ; « Examiner les demandes » |
| Direction | Nouveau relevé soumis ou justification à examiner | Classe, matière, période, date ; « Examiner » |
| Direction | Nouvelle anomalie nécessitant une action autorisée | Nature et périmètre exacts ; « Voir les dossiers » |
| Direction / gestionnaire | Nouvelle échéance de recouvrement ou rupture de moratoire confirmée | Dossiers concernés, sans inventer une dette ; « Consulter le suivi » |
| Professeur primaire/secondaire | Demande de correction ou décision reçue | Classe, matière, décision et date ; « Ouvrir le relevé » |
| Professeur | Changement publié de son emploi du temps | Créneau modifié, classe, date d'effet ; « Voir mon planning » |
| Professeur | Appel ou transmission à effectuer aujourd'hui | Seulement si la source permet de vérifier réellement que l'action manque ; « Faire l'appel » ou « Ouvrir les notes » |
| Professeur | Évaluation de sa classe proche d'une échéance | Date et matière, uniquement si cela oriente une action réelle ; « Voir l'évaluation » |
| Élève | Devoir nouveau ou modifié à rendre prochainement | Matière, consigne résumée, date ; « Ouvrir le devoir » |
| Élève | Évaluation annoncée, déplacée ou annulée | Ancienne/nouvelle date si disponibles ; « Voir mes évaluations » |
| Élève | Nouvelle note ou bulletin publié | Période et matière ; « Consulter mes résultats » ; aucune note non publiée |
| Élève | Convocation prochaine ou changement de planning | Date, lieu, heure ; « Voir les détails » |
| Parent | Nouvelle information importante pour un enfant | Prénom, classe, événement ; « Consulter son suivi » |
| Parent | Absence, convocation ou devoir proche d'une échéance | Enfant concerné et date ; « Voir les détails » ; priorité adaptée à la nature de l'événement |
| Parent | Échéance réelle de scolarité qui approche ou vient de changer | Enfant, frais, montant restant et date ; « Voir la scolarité » |
| Parent | Paiement enregistré ou choix de frais modifié | Confirmation précise et référence si disponible ; « Voir le reçu » ou « Voir les frais » |
| Parent | Liaison enfant validée, refusée ou nécessitant une action | Statut réel, motif communicable ; « Suivre ma demande » |
| Secrétaire | Nouveau dossier à compléter ou nouvelle préinscription accessible | Identité minimale, pièce/étape manquante si vérifiable ; « Ouvrir le dossier » |
| Comptable / caissier | Dossier financier ou rapprochement nécessitant une action | Seulement les opérations et montants autorisés ; « Examiner » |
| Tout espace | Annonce publiée qui cible ce rôle et n'a pas été présentée | Titre, auteur, date et extrait ; « Lire l'annonce » |

Pas d'alerte intrusive fondée uniquement sur un classement scolaire, une statistique moyenne ou une dette future de l'année entière. Les alertes de difficultés durables restent consultables dans le dashboard ; elles justifient une nouvelle interruption seulement si un événement concret ou une action attendue le permet.

## 4. Priorités et règles d'affichage

1. Situation importante avec action et échéance proche : convocation, changement de planning imminent, décision bloquant une démarche.
2. Action à réaliser : dossier, correction ou échéance réellement due.
3. Nouveauté informative : résultat publié, paiement reçu, annonce ciblée.

Proposition par défaut : une seule fenêtre à l'arrivée après connexion, contenant au maximum trois cartes. Une action principale et au plus une action secondaire par carte. Les autres nouveautés restent accessibles via « Tout consulter ». Aucun enchaînement automatique de fenêtres.

La fréquence et la priorité sont décidées par le serveur. Une fenêtre déjà ouverte, une saisie ou une opération de paiement empêchent une interruption concurrente. Après connexion avec redirection vers un formulaire ou une page demandée, différer au prochain écran d'accueil approprié. Recharger une page, ouvrir un second onglet ou changer de rubrique ne relance pas la fenêtre.

## 5. Prévenir les répétitions

### Identité d'une information

Identifier séparément : utilisateur et type de compte, établissement, année, enfant éventuel, type d'événement, objet métier et version significative. Une même clé de situation présentée sur un ordinateur ne doit pas réapparaître immédiatement sur téléphone.

Exemples :

- Bulletin déjà présenté : silencieux aux connexions suivantes. Bulletin republié avec un contenu réellement différent : nouvelle version.
- Devoir déjà présenté : silencieux si inchangé. Date de rendu déplacée : nouvelle information.
- Frais exempté ou soldé : retiré immédiatement, même si une ancienne notification d'impayé existe.
- Échéance déjà vue : pas de répétition à chaque connexion. Un rappel peut être admis au changement de seuil (par exemple J-3, jour J, puis retard), avec un plafond et seulement si le reste demeure réel.
- Compteur direction : l'arrivée de nouveaux dossiers peut créer une nouvelle synthèse ; un compteur identique ne réaffiche rien. Les identifiants et états des dossiers, pas seulement le nombre, servent à reconnaître le changement.

### Choix utilisateur

- « Consulter » : ouvrir la page adaptée ; mémoriser l'ouverture sans prétendre que l'action métier est terminée.
- « Plus tard » : reporter jusqu'au délai prévu (par défaut le lendemain, ou avant l'échéance si elle survient plus tôt).
- Fermer : enregistrer une présentation, sans marquer toutes les notifications comme lues.
- « Masquer cette information » pour les nouveautés purement informatives ; les rappels nécessaires gardent des règles explicites et espacées.
- Aucun « ignoré pour toujours » automatique pour toutes les versions futures d'un même objet.

La fermeture ne retire jamais une dette, ne valide pas un dossier et ne justifie pas une absence.

## 6. Architecture proposée

### Moteur commun

Un service serveur produit des cartes normalisées à partir de fournisseurs par rôle. Chaque carte contient une clé stable, version, priorité, titre, texte, contexte (classe/enfant), date, expiration et actions internes autorisées.

Les fournisseurs réutilisent les filtres métier existants et les services du dashboard, sans appeler les vues qui marquent les notifications comme lues. Les sources métier résolues prennent le dessus sur les anciennes notifications.

### Historique persistant

Un modèle d'état par utilisateur/type de compte et situation : première/dernière présentation, version présentée, ouverture, report et masquage. Une contrainte d'unicité prévient les doublons. L'acquisition d'une présentation doit être atomique pour deux onglets ouverts simultanément.

Une table de préférences peut permettre de réduire les nouveautés informatives. L'historique conserve les identifiants et états minimaux ; il n'a pas besoin de dupliquer les notes ou détails financiers dans le navigateur.

### API et sécurité

Lecture authentifiée et sans écriture implicite pour connaître les cartes éligibles ; action explicite séparée pour réserver/confirmer une présentation, ouvrir ou reporter. CSRF pour les écritures, validation serveur du périmètre et des clés. Une carte reçue du client ne fait jamais autorité sur son destinataire ou son URL.

Les actions pointent vers les routes existantes autorisées ; elles sont filtrées et recalculées côté serveur. Un personnel sans droit comptable ne reçoit pas les montants ni les actions de comptabilité. Le parent ne reçoit que les informations des enfants liés et autorisés. Si une autorisation est retirée après la génération, la page cible vérifie encore l'accès.

### Composant visuel réutilisable

Un composant partagé : en-tête de synthèse (« À voir aujourd'hui »), cartes compactes, pictogramme, date, contexte et boutons lisibles. Fonds unis, contraste clair, pas de bordure colorée ni de dégradé conformément aux préférences déjà exprimées. Couleurs sobres selon la nature, animation courte et désactivable via prefers-reduced-motion.

Sur mobile : panneau adapté à la largeur, hauteur limitée et défilement interne. Clavier : focus placé dans la fenêtre, tabulation contenue, fermeture par Échap et retour du focus ; titre accessible et boutons suffisamment grands. Les autorisations navigateur et la connexion ne doivent pas être déclenchées automatiquement par ce composant.

### Coexistence avec le push

Le push sert à prévenir hors de l'espace. Le popup sert à orienter à l'arrivée. Un clic sur un push menant déjà à l'objet ne doit pas faire réapparaître la même carte par-dessus. Le statut FCM « envoyé » ne suffit pas à supprimer une carte ; une consultation explicite peut le faire. Les nouvelles informations reçues pendant la saisie vont d'abord dans le centre de notifications.

## 7. Déroulement proposé

1. Définir le contrat des cartes, les seuils initiaux et les fournisseurs autorisés ; documenter les sources réellement fiables.
2. Construire le moteur, l'historique et les API ; vérifier les exclusions et la déduplication avant l'affichage.
3. Créer le composant et brancher les entrées direction, enseignant primaire/secondaire, parent et élève.
4. Étendre aux fonctions secrétaire/comptable/personnel en conservant leurs permissions exactes.
5. Recetter avec des données temporaires : nouveauté, disparition après résolution, modification, report, plusieurs enfants, plusieurs onglets, plusieurs appareils et session expirée.
6. Redémarrer le serveur, puis montrer des cas concrets dans le navigateur pour validation de l'ergonomie.

## 8. Tests nécessaires

- Aucune carte sans situation utile ; aucun montant inventé ; aucune note avant publication.
- Deux connexions successives sans changement : pas de répétition.
- Changement significatif : nouvelle carte ; modification cosmétique : aucune nouvelle carte.
- Paiement, exemption, annulation : disparition de l'alerte devenue fausse.
- Parent à plusieurs enfants et enfants dans des établissements distincts : contexte explicite, aucun mélange de devises ou d'années.
- Primaire/secondaire/supérieur : bon enseignant, bonne classe annuelle, bons liens d'action.
- Personnel aux permissions restreintes : aucun accès par la carte ou son API.
- Concurrence entre onglets : une présentation ; fonctionnement dégradé si API indisponible sans bloquer la page.
- Lisibilité mobile, clavier, lecteur d'écran, animations réduites et absence de collision avec une autre fenêtre.

## 9. État de cette intervention

Audit ciblé et plan uniquement : aucun popup, modèle, migration, paramètre de fréquence ou code métier ajouté à ce stade. Les exemples décrivent le comportement proposé ; les sources complexes et les seuils seront validés pendant l'implémentation. L'audit du code ne remplace pas la recette sur toutes les fonctions et tous les appareils.
