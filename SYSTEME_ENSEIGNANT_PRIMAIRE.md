# Système Enseignant Primaire - Documentation Complète

## Vue d'ensemble

Le système enseignant primaire est un module parallèle et indépendant du système standard, spécialement conçu pour gérer les spécificités de l'enseignement primaire au Sénégal, notamment l'enseignement polyvalent (un enseignant enseigne plusieurs matières dans une même classe).

## Architecture du Système

### 1. Modèles de Données

#### AffectationProfesseurPrimaire
- **Rôle**: Gère les affectations des enseignants primaires aux classes
- **Caractéristiques**:
  - Un enseignant peut être affecté à une ou plusieurs classes
  - Un enseignant peut enseigner plusieurs matières dans chaque classe
  - Relation ManyToMany avec les matières
  - Validation automatique (niveau primaire, unicité)

#### EvaluationPrimaire
- **Rôle**: Gère les évaluations spécifiques au primaire
- **Caractéristiques**:
  - Liée à une matière spécifique
  - Liée à une classe et une période scolaire
  - Types: contrôle, interrogation, devoir maison, projet, oral, pratique
  - Barème personnalisable

#### NotePrimaire
- **Rôle**: Stocke les notes des élèves pour les évaluations primaires
- **Caractéristiques**:
  - Liée à un élève et une évaluation
  - Gestion des absences
  - Calcul automatique de la note sur 20
  - Appréciation automatique

#### MoyenneMatierePrimaire
- **Rôle**: Stocke les moyennes calculées par matière
- **Caractéristiques**:
  - Liée à un élève, une matière et une période
  - Calcul automatique via les utilitaires
  - Appréciation automatique

### 2. Vues et URLs

#### Dashboard (`/enseignant-primaire/dashboard/`)
- Vue d'ensemble des classes et matières
- Statistiques: classes, élèves, matières, évaluations
- Emploi du temps du jour
- Prochaines évaluations

#### Gestion des Classes (`/enseignant-primaire/classes/`)
- Liste des classes affectées
- Informations par classe: élèves, matières enseignées
- Actions rapides: voir élèves, noter, voir relevé

#### Gestion des Élèves (`/enseignant-primaire/eleves/`)
- Liste des élèves par classe
- Informations: absences, sanctions
- Accès rapide aux détails de chaque élève

#### Gestion des Notes (`/enseignant-primaire/notes/`)
- Onglets par période scolaire
- Sous-onglets par matière enseignée
- Liste des évaluations par matière
- Statistiques par matière

#### Création d'Évaluation (`/enseignant-primaire/evaluation/creer/<classe_id>/`)
- Formulaire avec sélection de la matière
- Champs: titre, type, date, barème, durée, description
- Validation: matière enseignée par le professeur

#### Notation des Élèves (`/enseignant-primaire/noter/<classe_id>/`)
- Onglets dynamiques par matière
- Tableau de saisie des notes par évaluation
- Sauvegarde AJAX en temps réel
- Gestion des absences

#### Relevé Multi-Matières (`/enseignant-primaire/releve/<classe_id>/`)
- Tableau avec une colonne par matière
- Moyenne par matière et moyenne générale
- Code couleur selon les appréciations
- Export et impression

#### Liste des Évaluations (`/enseignant-primaire/evaluations/`)
- Filtres: matière, période, classe
- Vue d'ensemble de toutes les évaluations
- Actions: modifier, noter

#### Détail Élève (`/enseignant-primaire/eleve/<eleve_id>/`)
- Onglets: informations, notes, présences, sanctions
- Notes par matière avec moyennes
- Moyenne générale

### 3. Utilitaires de Calcul

#### `calculer_moyenne_matiere(eleve, matiere, periode)`
- Calcule la moyenne d'un élève pour une matière sur une période
- Retourne la moyenne sur 20 ou None

#### `calculer_moyenne_generale(eleve, periode)`
- Calcule la moyenne générale (toutes matières)
- Retourne un dictionnaire avec moyenne et détails par matière

#### `calculer_moyenne_classe_matiere(classe, matiere, periode)`
- Calcule la moyenne de la classe pour une matière
- Retourne moyenne, meilleure/moins bonne note

#### `calculer_toutes_moyennes_classe(classe, periode)`
- Calcule toutes les moyennes pour tous les élèves
- Utilisé pour générer les relevés de notes

#### `get_appreciation_moyenne(moyenne)`
- Retourne une appréciation selon la moyenne
- Échelle: Excellent (≥16), Très bien (≥14), Bien (≥12), Assez bien (≥10), Passable (≥8), Insuffisant (<8)

#### `get_repartition_moyennes_classe(classe, matiere, periode)`
- Calcule la répartition des moyennes par catégorie
- Retourne un dictionnaire avec comptages et pourcentages

### 4. Templates

Tous les templates sont dans `school_admin/templates/school_admin/enseignant/primaire/`:

- `dashboard_primaire.html`: Dashboard principal
- `gestion_classes_primaire.html`: Gestion des classes
- `gestion_eleves_primaire.html`: Gestion des élèves
- `gestion_notes_primaire.html`: Gestion des notes
- `creer_evaluation_primaire.html`: Création d'évaluation
- `noter_eleves_primaire.html`: Notation des élèves
- `voir_releve_primaire.html`: Relevé multi-matières
- `liste_evaluations_primaire.html`: Liste des évaluations
- `detail_eleve_primaire.html`: Détail d'un élève
- `detail_classe_primaire.html`: Détail d'une classe
- `liste_presence_primaire.html`: Gestion des présences
- `liste_sanctions_classe_primaire.html`: Gestion des sanctions
- `emploi_du_temps_primaire.html`: Emploi du temps
- `parametres_profil_primaire.html`: Paramètres du profil
- `imprimer_releve_primaire.html`: Impression du relevé
- `partials/header_primaire.html`: Header spécifique

### 5. CSS et JavaScript

Le système primaire réutilise les fichiers CSS/JS existants du système standard:
- `school_admin/static/school_admin/css/enseignant/`
- `school_admin/static/school_admin/js/enseignant/`

Les templates incluent du JavaScript inline pour:
- Gestion des onglets dynamiques
- Sauvegarde AJAX des notes
- Calcul automatique des notes sur 20

## Logique de Redirection Automatique

Dans `school_admin/controllers/compte_user_controller.py`:

```python
elif isinstance(user, Professeur):
    # Vérifier le type d'établissement pour rediriger vers le bon dashboard
    if user.etablissement.type_etablissement == 'primary':
        return None, redirect('enseignant_primaire:dashboard')
    else:
        return None, redirect('enseignant:dashboard_enseignant')
```

- Les enseignants d'établissements primaires sont automatiquement redirigés vers le dashboard primaire
- Les enseignants d'autres établissements (collège, lycée, mixte) sont redirigés vers le dashboard standard

## Différences avec le Système Standard

| Fonctionnalité | Système Standard | Système Primaire |
|----------------|------------------|------------------|
| Affectation | Un enseignant = une matière par classe | Un enseignant = plusieurs matières par classe |
| Évaluation | Liée à l'affectation | Liée à une matière spécifique |
| Notes | Par affectation | Par matière |
| Relevé | Une matière | Multi-matières |
| Moyennes | Par matière | Par matière + moyenne générale |

## Guide d'Utilisation

### Pour un Enseignant Primaire

1. **Connexion**: Utilisez vos identifiants habituels
2. **Dashboard**: Vous serez automatiquement redirigé vers le dashboard primaire
3. **Créer une évaluation**:
   - Allez dans "Gestion des Notes"
   - Sélectionnez une matière
   - Cliquez sur "Créer évaluation"
   - Remplissez le formulaire
4. **Noter les élèves**:
   - Allez dans "Gestion des Notes" ou "Mes Classes"
   - Cliquez sur "Noter élèves"
   - Sélectionnez la matière (onglets)
   - Saisissez les notes (sauvegarde automatique)
5. **Voir le relevé**:
   - Allez dans "Mes Classes"
   - Cliquez sur "Voir relevé"
   - Sélectionnez la période
   - Consultez les moyennes multi-matières

### Pour un Directeur/Administrateur

1. **Ajouter un enseignant primaire**:
   - Allez dans "Personnel" > "Ajouter un professeur"
   - Sélectionnez "Niveau d'enseignement": Primaire
   - Sélectionnez les matières enseignées (checkboxes)
2. **Affecter un enseignant**:
   - Allez dans "Affectations" > "Professeurs"
   - Créez une `AffectationProfesseurPrimaire`
   - Sélectionnez les matières enseignées dans la classe
3. **Vérifier les notes**:
   - Les notes primaires sont dans `NotePrimaire`
   - Les moyennes sont dans `MoyenneMatierePrimaire`

## Tests et Validation

### Données de Test

Un enseignant primaire de test existe déjà:
- **Username**: `jomas@gmail.com`
- **Mot de passe**: `5576`
- **Établissement**: Blaise pascal (primary)
- **Affectation**: CE1 - A (7 matières)

### Tests à Effectuer

1. ✅ Connexion et redirection vers dashboard primaire
2. ✅ Affichage des classes et matières
3. ⏳ Création d'évaluation avec sélection de matière
4. ⏳ Notation des élèves avec onglets par matière
5. ⏳ Affichage du relevé multi-matières
6. ⏳ Calcul des moyennes par matière et moyenne générale
7. ⏳ Gestion des présences (réutilise logique existante)
8. ⏳ Gestion des sanctions (réutilise logique existante)

## Maintenance et Évolution

### Points d'Attention

1. **Validation des Affectations**: Le modèle `AffectationProfesseurPrimaire` valide automatiquement que:
   - Le professeur est de niveau primaire
   - La classe est de niveau primaire
   - Pas de doublon d'affectation

2. **Calcul des Moyennes**: Les moyennes sont calculées à la volée et enregistrées dans `MoyenneMatierePrimaire`

3. **Cohérence des Données**: Les notes primaires sont totalement indépendantes des notes standard

### Évolutions Futures

1. **Formulaire d'ajout de professeur**: Ajouter des checkboxes pour sélectionner plusieurs matières
2. **CSS/JS spécifiques**: Créer des fichiers CSS/JS dédiés si nécessaire
3. **Présences et Sanctions**: Implémenter les vues complètes (actuellement placeholders)
4. **Emploi du temps**: Implémenter la vue complète
5. **Paramètres du profil**: Implémenter la vue complète
6. **Export PDF**: Améliorer l'export des relevés

## Dépannage

### Problème: Enseignant non redirigé vers dashboard primaire
- Vérifier que `professeur.etablissement.type_etablissement == 'primary'`
- Vérifier que `professeur.niveau_enseignement == 'primaire'`

### Problème: Erreur lors de la création d'affectation
- Vérifier que la classe est bien de niveau primaire
- Vérifier que les matières sont bien de niveau primaire

### Problème: Moyennes non calculées
- Vérifier qu'il y a des notes saisies
- Vérifier que les évaluations sont actives
- Vérifier que la période est correcte

## Contact et Support

Pour toute question ou problème, consulter:
- Ce fichier de documentation
- Le code source dans `school_admin/personal_views/enseignant_primaire_view.py`
- Les modèles dans `school_admin/model/`
- Les utilitaires dans `school_admin/utils/calcul_moyennes_primaire.py`
