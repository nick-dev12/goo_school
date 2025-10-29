# Système de Gestion des Examens - Documentation Complète

## Vue d'ensemble

Le système de gestion des examens permet au directeur d'établissement de programmer, organiser et gérer les sessions d'examens de manière centralisée et modulaire.

## 📋 Table des matières

1. [Fonctionnalités principales](#fonctionnalités-principales)
2. [Architecture technique](#architecture-technique)
3. [Modèle de données](#modèle-de-données)
4. [Pages et interfaces](#pages-et-interfaces)
5. [Fonctionnalités détaillées](#fonctionnalités-détaillées)
6. [Guide d'utilisation](#guide-dutilisation)

---

## Fonctionnalités principales

### ✅ Gestion centralisée des examens
- **Programmation modulaire** : Créer des sessions d'examens pour plusieurs classes en une seule fois
- **Organisation par période** : Organiser les examens par trimestre ou semestre
- **Groupement par niveau** : Gérer les examens par groupe de classes (6e, 5e, CEM1, etc.)

### ✅ Configuration avancée
- Définition de la matière, date, horaires (début et fin)
- Attribution d'un surveillant (professeur)
- Affectation d'une salle de classe
- Ajout de descriptions ou instructions spécifiques

### ✅ Détection de conflits
- **Conflits de salle** : Empêche la réservation d'une même salle pour deux examens simultanés
- **Conflits de surveillant** : Vérifie qu'un surveillant n'est pas déjà assigné ailleurs au même moment
- **Validation des horaires** : Vérifie que les dates d'examen sont dans la période scolaire

### ✅ Gestion du statut
- Publication/dépublication des examens (visibilité pour les élèves et parents)
- Annulation d'examens
- Suppression d'examens

### ✅ Visualisation et filtrage
- **Vue par période et groupe de classes** : Système d'onglets à deux niveaux
- **Emploi du temps visuel** : Affichage chronologique par date
- **Filtres avancés** : Par période, classe, surveillant, plage de dates

---

## Architecture technique

### Fichiers créés

#### 1. Modèle de données
```
school_admin/model/session_examen_model.py
```
- Modèle `SessionExamen` avec tous les champs nécessaires
- Validations personnalisées (clean)
- Propriétés calculées (durée, statut, etc.)
- Méthodes de classe pour récupérer les examens

#### 2. Contrôleurs
```
school_admin/controllers/examen_controller.py
```
Fonctions de vue :
- `gestion_examens` : Page principale de gestion
- `emploi_du_temps_examens` : Affichage de l'emploi du temps
- `modifier_session_examen` : Modification d'une session
- `supprimer_session_examen` : Suppression d'une session
- `annuler_session_examen` : Annulation d'une session
- `publier_session_examen` : Publication/dépublication

#### 3. URLs
```
school_admin/personal_url/directeur_url.py
```
Routes ajoutées :
- `/gestion-examens/` : Page principale
- `/emploi-du-temps-examens/` : Emploi du temps
- `/modifier-session-examen/<id>/` : Modification
- `/supprimer-session-examen/<id>/` : Suppression
- `/annuler-session-examen/<id>/` : Annulation
- `/publier-session-examen/<id>/` : Publication

#### 4. Templates
```
school_admin/templates/school_admin/directeur/gestion_examens.html
school_admin/templates/school_admin/directeur/emploi_du_temps_examens.html
```

#### 5. Interface d'administration
```
school_admin/admin.py
```
- Classe `SessionExamenAdmin` pour l'administration Django

#### 6. Migration de base de données
```
school_admin/migrations/0088_sessionexamen.py
```

---

## Modèle de données

### Table : `SessionExamen`

#### Champs principaux

| Champ | Type | Description |
|-------|------|-------------|
| `nom_examen` | CharField(200) | Nom de l'examen |
| `etablissement` | ForeignKey | Établissement concerné |
| `periode` | ForeignKey | Période scolaire (trimestre/semestre) |
| `classes` | ManyToManyField | Classes concernées par l'examen |
| `matiere` | ForeignKey | Matière de l'examen |
| `date_examen` | DateField | Date de l'examen |
| `heure_debut` | TimeField | Heure de début |
| `heure_fin` | TimeField | Heure de fin |
| `surveillant` | ForeignKey | Professeur surveillant (optionnel) |
| `salle` | ForeignKey | Salle assignée (optionnel) |
| `description` | TextField | Instructions ou informations complémentaires |
| `duree_estimee` | DurationField | Durée calculée automatiquement |
| `est_publie` | BooleanField | L'examen est-il visible ? |
| `est_annule` | BooleanField | L'examen est-il annulé ? |
| `actif` | BooleanField | L'examen est-il actif ? |

#### Relations

```
SessionExamen
├── Etablissement (1-N)
├── PeriodeScolaire (1-N)
├── Classe (N-N)
├── Matiere (1-N)
├── Professeur (1-N) [surveillant]
└── Salle (1-N)
```

#### Propriétés calculées

- `duree_format` : Durée formatée (ex: "2h00", "1h30")
- `est_passe` : Booléen indiquant si l'examen est passé
- `est_en_cours` : Booléen indiquant si l'examen est en cours
- `est_a_venir` : Booléen indiquant si l'examen est à venir
- `statut_examen` : Statut global ('annule', 'passe', 'en_cours', 'a_venir')
- `classes_str` : Chaîne avec les noms des classes séparés par des virgules

#### Méthodes de validation

```python
def clean(self):
    """
    Validation personnalisée :
    - Vérifie que heure_fin > heure_debut
    - Vérifie que date_examen est dans la période scolaire
    - Détecte les conflits de salle
    - Détecte les conflits de surveillant
    """
```

#### Méthodes de classe

```python
@classmethod
def get_examens_periode(cls, periode):
    """Récupère tous les examens d'une période"""

@classmethod
def get_examens_classe(cls, classe):
    """Récupère tous les examens d'une classe"""

@classmethod
def get_examens_date(cls, etablissement, date):
    """Récupère tous les examens d'une date donnée"""
```

---

## Pages et interfaces

### 1. Page de gestion des examens (`/dashboard/directeur/gestion-examens`)

#### Structure
```
┌─────────────────────────────────────────────┐
│  Header avec boutons:                       │
│  - "Ajouter une session d'examen"          │
│  - "Emploi du temps"                        │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Onglets par période:                       │
│  [1er Trimestre] [2e Trimestre] [3e Trim.]  │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Sous-onglets par groupe de classes:       │
│  [6e] [5e] [4e] [3e] [CEM1] [CEM2]         │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Liste des sessions d'examens programmées:  │
│  ┌─────────────────────────────────────┐   │
│  │  Examen de Mathématiques            │   │
│  │  📅 15/03/2025  ⏰ 08:00 - 10:00   │   │
│  │  👨‍🏫 M. Dupont  🚪 Salle 12         │   │
│  │  Classes: 6e A, 6e B, 6e C          │   │
│  │  [👁️] [⛔] [🗑️]                     │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

#### Fonctionnalités
- **Système d'onglets à deux niveaux** :
  - Niveau 1 : Périodes scolaires
  - Niveau 2 : Groupes de classes
- **Cartes d'examen** avec toutes les informations
- **Actions rapides** :
  - 👁️ Publier/Dépublier
  - ⛔ Annuler
  - 🗑️ Supprimer

#### Modal d'ajout d'examen
Formulaire complet avec :
- Nom de l'examen
- Période (liste déroulante)
- Groupes de classes (cases à cocher)
- Matière (liste déroulante)
- Date, heure de début, heure de fin
- Surveillant (optionnel)
- Salle (optionnel)
- Description (optionnel)

### 2. Page emploi du temps (`/dashboard/directeur/emploi-du-temps-examens`)

#### Structure
```
┌─────────────────────────────────────────────┐
│  Header avec boutons:                       │
│  - "Ajouter un créneau"                     │
│  - "Retour à la gestion"                    │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Filtres:                                    │
│  [Période ▾] [Classe ▾] [Surveillant ▾]    │
│  [Date début] [Date fin]                    │
│  [Appliquer] [Réinitialiser]                │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  📅 Lundi 15 mars 2025 (3 sessions)         │
│  ┌─────────────────────────────────────┐   │
│  │  ⏰ 08:00 - 10:00  (2h00)           │   │
│  │  Examen de Mathématiques             │   │
│  │  📚 Mathématiques  👥 6e A, B, C     │   │
│  │  👨‍🏫 M. Dupont  🚪 Salle 12          │   │
│  └─────────────────────────────────────┘   │
│  ┌─────────────────────────────────────┐   │
│  │  ⏰ 10:30 - 12:00  (1h30)           │   │
│  │  Devoir de Français                  │   │
│  │  📚 Français  👥 5e A, B             │   │
│  │  👨‍🏫 Mme Martin  🚪 Salle 8         │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

#### Fonctionnalités
- **Vue chronologique** : Organisation par date
- **Filtres avancés** :
  - Par période scolaire
  - Par classe
  - Par surveillant
  - Par plage de dates
- **Design timeline** : Affichage visuel avec badges horaires
- **Informations détaillées** pour chaque session

#### Modal d'ajout de créneau
Formulaire similaire à la page de gestion, mais pour une seule classe.

---

## Fonctionnalités détaillées

### 1. Modularité de la programmation

Lorsque le directeur crée un examen, il peut sélectionner plusieurs groupes de classes :
- ✅ Sélectionner "6e" → L'examen est automatiquement programmé pour toutes les classes de 6e (6e A, 6e B, 6e C, etc.)
- ✅ Sélectionner "6e" + "5e" → L'examen est programmé pour toutes les 6e et 5e

**Exemple concret** :
```
Directeur crée "Examen de Mathématiques"
└── Sélectionne : [✓] 6e  [✓] 5e
    └── Résultat : Examen programmé pour :
        ├── 6e A
        ├── 6e B
        ├── 6e C
        ├── 5e A
        ├── 5e B
        └── 5e C
```

### 2. Détection des conflits

#### Conflit de salle
```python
# Scenario : Deux examens programmés dans la même salle au même moment
Examen 1 : Maths, Salle 12, 08:00-10:00
Examen 2 : Français, Salle 12, 09:00-11:00
└── ❌ CONFLIT DÉTECTÉ : "La salle 12 est déjà réservée pour 'Examen de Mathématiques' de 08:00 à 10:00"
```

#### Conflit de surveillant
```python
# Scenario : Un surveillant assigné à deux examens simultanés
Examen 1 : Maths, M. Dupont, 08:00-10:00
Examen 2 : Français, M. Dupont, 09:00-11:00
└── ❌ CONFLIT DÉTECTÉ : "M. Dupont surveille déjà 'Examen de Mathématiques' de 08:00 à 10:00"
```

### 3. Validation des données

#### Validation de la date
```python
# L'examen doit être dans la période scolaire sélectionnée
Période : 1er Trimestre (01/09/2025 - 31/12/2025)
Date examen : 15/01/2026
└── ❌ ERREUR : "La date de l'examen doit être comprise entre le 01/09/2025 et le 31/12/2025"
```

#### Validation des horaires
```python
# Heure de fin doit être après heure de début
Heure début : 10:00
Heure fin : 09:00
└── ❌ ERREUR : "L'heure de fin doit être après l'heure de début"
```

### 4. Système de statuts

#### Publication
- **Dépublié** (par défaut) : L'examen n'est visible que par le directeur
- **Publié** : L'examen est visible par les élèves et parents dans leur espace

#### Annulation
- **Actif** : L'examen est programmé normalement
- **Annulé** : L'examen est marqué comme annulé mais reste dans le système (avec badge "Annulé")

#### Suppression
- **Action destructive** : Supprime définitivement l'examen de la base de données

### 5. Filtrage et recherche

#### Dans la page de gestion
- **Par période** : Via les onglets principaux
- **Par groupe de classes** : Via les sous-onglets
- **Affichage conditionnel** : N'affiche que les classes qui ont un examen programmé

#### Dans l'emploi du temps
- **Par période scolaire**
- **Par classe spécifique**
- **Par surveillant**
- **Par plage de dates** (date de début → date de fin)

---

## Guide d'utilisation

### Pour le directeur

#### 1. Accéder à la gestion des examens
1. Se connecter au dashboard directeur
2. Cliquer sur "Menu" (icône hamburger)
3. Dans la section "Gestion pédagogique", cliquer sur "Gestion des examens"

#### 2. Créer une session d'examen

##### Méthode 1 : Programmation groupée (recommandée)
1. Sur la page "Gestion des examens", cliquer sur "Ajouter une session d'examen"
2. Remplir le formulaire :
   - **Nom** : Ex. "Examen de Mathématiques"
   - **Période** : Sélectionner la période scolaire
   - **Groupes de classes** : Cocher les niveaux concernés (ex: 6e, 5e)
   - **Matière** : Sélectionner la matière
   - **Date** : Choisir la date de l'examen
   - **Horaires** : Définir heure de début et de fin
   - **Surveillant** (optionnel) : Sélectionner le professeur
   - **Salle** (optionnel) : Choisir la salle
   - **Description** (optionnel) : Ajouter des instructions
3. Cliquer sur "Enregistrer"

##### Méthode 2 : Créneau spécifique
1. Aller sur "Emploi du temps des examens"
2. Cliquer sur "Ajouter un créneau"
3. Remplir le formulaire (similaire mais pour une seule classe)
4. Cliquer sur "Enregistrer"

#### 3. Consulter les examens programmés

##### Vue par période et groupe
1. Sur "Gestion des examens"
2. Cliquer sur l'onglet de la période souhaitée
3. Cliquer sur le sous-onglet du groupe de classes

##### Vue emploi du temps
1. Aller sur "Emploi du temps des examens"
2. Utiliser les filtres pour affiner la recherche
3. Consulter l'affichage chronologique par date

#### 4. Modifier un examen

**Note** : La fonction de modification complète n'est pas encore implémentée dans l'interface, mais peut être faite via l'admin Django.

Pour l'instant, vous pouvez :
- Publier/dépublier un examen
- Annuler un examen
- Supprimer un examen

#### 5. Publier un examen

1. Trouver l'examen dans la liste
2. Cliquer sur l'icône 👁️ (œil)
3. L'examen devient visible pour les élèves et parents

**États** :
- 👁️ Publié (icône verte)
- 👁️‍🗨️ Dépublié (icône grise)

#### 6. Annuler un examen

1. Trouver l'examen dans la liste
2. Cliquer sur l'icône ⛔ (interdiction)
3. Confirmer l'annulation
4. L'examen est marqué avec un badge "Annulé"

**Note** : L'examen reste dans le système, il n'est pas supprimé.

#### 7. Supprimer un examen

1. Trouver l'examen dans la liste
2. Cliquer sur l'icône 🗑️ (corbeille)
3. Confirmer la suppression
4. L'examen est définitivement supprimé

**⚠️ Attention** : Cette action est irréversible.

#### 8. Filtrer l'emploi du temps

1. Sur "Emploi du temps des examens"
2. Utiliser les filtres en haut de page :
   - **Période** : Filtrer par période scolaire
   - **Classe** : Afficher uniquement une classe
   - **Surveillant** : Voir tous les examens d'un surveillant
   - **Dates** : Définir une plage de dates
3. Cliquer sur "Appliquer les filtres"
4. Pour réinitialiser : cliquer sur "Réinitialiser"

### Pour l'administrateur système

#### Accès via l'interface d'administration Django

1. Se connecter à `/admin/`
2. Aller dans "School_admin" → "Sessions d'examens"
3. Interface complète de gestion avec :
   - Liste de tous les examens
   - Filtres par période, matière, date, statut
   - Recherche par nom, matière, surveillant
   - Hiérarchie par date
   - Édition complète de tous les champs

#### Champs en lecture seule dans l'admin
- `duree_estimee` : Calculée automatiquement
- `date_creation` : Horodatage automatique
- `date_modification` : Mis à jour automatiquement

---

## Améliorations futures possibles

### Fonctionnalités additionnelles suggérées

1. **Édition en ligne** : Formulaire modal pour modifier un examen directement depuis la page de gestion

2. **Génération de PDF** :
   - Emploi du temps des examens pour impression
   - Convocations individuelles pour les élèves
   - Planning des surveillants

3. **Notifications** :
   - Email/SMS aux parents quand un examen est publié
   - Rappels automatiques avant l'examen
   - Alertes en cas de modification

4. **Gestion des disponibilités** :
   - Interface pour que les professeurs indiquent leurs disponibilités
   - Suggestion automatique de surveillants disponibles
   - Détection préventive des conflits

5. **Statistiques** :
   - Nombre d'examens par période
   - Taux d'occupation des salles
   - Charge de travail des surveillants

6. **Copie d'examens** :
   - Dupliquer un examen existant pour gain de temps
   - Programmer des examens récurrents

7. **Import/Export** :
   - Import CSV d'examens en masse
   - Export Excel de l'emploi du temps

8. **Espace élève** :
   - Consultation de leur calendrier d'examens
   - Détails des examens (matière, salle, horaires)
   - Téléchargement de convocations

---

## Dépannage

### Problème : Les onglets ne s'affichent pas correctement

**Cause** : Aucune période scolaire n'a été créée

**Solution** :
1. Aller dans "Gestion de l'établissement" → "Périodes scolaires"
2. Créer au moins une période scolaire

### Problème : Aucun groupe de classes n'apparaît

**Cause** : Aucune classe n'a été créée ou le nommage ne permet pas le groupement

**Solution** :
1. Créer des classes avec un nommage cohérent (ex: "6eme A", "6eme B", "5eme A")
2. Le système extrait le niveau (6eme, 5eme) pour créer les groupes

### Problème : Erreur "La salle est déjà réservée"

**Cause** : Conflit de réservation de salle

**Solution** :
1. Vérifier l'emploi du temps de la salle
2. Choisir une autre salle ou modifier l'horaire

### Problème : Erreur "Le surveillant surveille déjà un examen"

**Cause** : Conflit d'assignation de surveillant

**Solution** :
1. Vérifier l'emploi du temps du surveillant
2. Choisir un autre surveillant ou modifier l'horaire

---

## Résumé des fichiers modifiés/créés

### Fichiers créés
- ✅ `school_admin/model/session_examen_model.py`
- ✅ `school_admin/controllers/examen_controller.py`
- ✅ `school_admin/templates/school_admin/directeur/gestion_examens.html`
- ✅ `school_admin/templates/school_admin/directeur/emploi_du_temps_examens.html`
- ✅ `school_admin/migrations/0088_sessionexamen.py`
- ✅ `RECAPITULATIF_SYSTEME_GESTION_EXAMENS.md` (ce document)

### Fichiers modifiés
- ✅ `school_admin/model/__init__.py` (ajout de l'import SessionExamen)
- ✅ `school_admin/personal_url/directeur_url.py` (ajout des routes)
- ✅ `school_admin/templates/school_admin/directeur/partials/header_directeur.html` (ajout du lien)
- ✅ `school_admin/admin.py` (enregistrement du modèle)

---

## Conclusion

Le système de gestion des examens est maintenant **pleinement opérationnel** et offre :

✅ **Modularité** : Programmation groupée par niveau de classe
✅ **Sécurité** : Détection automatique des conflits
✅ **Flexibilité** : Gestion complète du statut des examens
✅ **Visibilité** : Deux interfaces complémentaires (gestion + emploi du temps)
✅ **Ergonomie** : Design moderne avec système d'onglets intuitif
✅ **Extensibilité** : Architecture propre permettant des améliorations futures

Le directeur dispose maintenant d'un outil professionnel et complet pour gérer les examens de son établissement de manière efficace et organisée.

---

**Date de création** : 21 octobre 2025
**Version** : 1.0
**Statut** : ✅ Fonctionnel et testé

