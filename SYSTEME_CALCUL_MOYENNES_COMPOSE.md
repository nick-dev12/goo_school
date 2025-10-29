# 📊 SYSTÈME DE CALCUL DES MOYENNES AVEC NOTES COMPOSÉES

## Vue d'ensemble

Système avancé permettant aux professeurs de calculer les moyennes de leurs élèves avec différents modes de calcul, tenant compte que **2 interrogations (sur 10) = 1 devoir (sur 20)**.

---

## 🎯 Fonctionnalités implémentées

### 1. **Modes de calcul disponibles**

#### a) **Toutes les notes**
- Utilise toutes les évaluations sélectionnées
- Les paires d'interrogations sont combinées automatiquement
- Tous les devoirs sont inclus

#### b) **2 meilleures notes (composées)**
- Combine les interrogations par paires : 2 interros = 1 note sur 20
- Compare ces notes composées avec les devoirs individuels
- Sélectionne les 2 meilleures notes parmi toutes

**Exemple** :
```
Interro 1 : 8.5/10 → 17/20
Interro 2 : 8/10 → 16/20
Paire : (17 + 16) / 2 = 16.5/20

Devoir 1 : 18.5/20
Contrôle : 18/20
Devoir 3 : 17.5/20

Notes composées : [16.5, 18.5, 18, 17.5]
2 meilleures : 18.5 et 18
Moyenne : (18.5 + 18) / 2 = 18.25/20
```

#### c) **3 meilleures notes (composées)**
- Même principe que le mode 2, mais sélectionne les 3 meilleures

#### d) **4 meilleures notes (composées)**
- Même principe que le mode 2, mais sélectionne les 4 meilleures

#### e) **1 Meilleure interro × 2**
- Sélectionne la **meilleure interrogation**
- La multiplie par 2 (compte comme un devoir)
- Ajoute **tous les devoirs** au calcul
- Calcule la moyenne de l'ensemble

**Exemple** :
```
Interro 1 : 8.5/10 → 17/20 (meilleure)
Interro 2 : 8/10 → 16/20

Devoir 1 : 18.5/20
Contrôle : 18/20
Devoir 3 : 17.5/20

Notes utilisées : [17 (interro × 2), 18.5, 18, 17.5]
Moyenne : (17 + 18.5 + 18 + 17.5) / 4 = 17.75/20
```

---

## 📝 Workflow complet

### Étape 1 : Noter les élèves
**Page** : `http://127.0.0.1:8000/enseignant/noter/78/?periode=2`

1. Sélectionner les évaluations à inclure (cocher les cases)
2. Saisir les notes pour chaque élève
3. Cliquer sur "Enregistrer les notes"

### Étape 2 : Calculer les moyennes
1. Choisir le **mode de calcul** dans le sélecteur
2. Cliquer sur "**Calculer les moyennes**"
3. Les moyennes s'affichent instantanément
4. Les moyennes sont **enregistrées dans la base de données**

### Étape 3 : Consulter le relevé de notes
**Page** : `http://127.0.0.1:8000/enseignant/releve/78/?periode=2`

- Affiche **uniquement les évaluations utilisées** dans le calcul
- Affiche les moyennes calculées
- Boutons disponibles :
  - **Modifier les notes** (si relevé non soumis)
  - **Soumettre le relevé** (verrouille les notes)
  - **Imprimer** (page d'impression professionnelle)

### Étape 4 : Imprimer le relevé
**Page** : `http://127.0.0.1:8000/enseignant/imprimer-releve/78/?periode=2`

**Contenu du relevé imprimable** :
- En-tête avec logo et informations de l'établissement
- Détails : Classe, Matière, Professeur, Période, Effectif
- **Mode de calcul utilisé** (affiché clairement)
- **Tableau des notes** (uniquement les évaluations sélectionnées)
- Moyennes individuelles et moyenne de classe
- Légende des couleurs
- Statistiques (nombre d'évaluations, élèves, moyenne)
- Signatures : Professeur, Directeur, Parent
- Date d'impression

---

## 🔧 Modifications techniques apportées

### 1. **Modèle Moyenne étendu**

**Nouveaux champs ajoutés** :
```python
mode_calcul = models.CharField(max_length=20, default='toutes')
evaluations_utilisees = models.JSONField(default=list, blank=True)
```

**Migration** : `0086_moyenne_evaluations_utilisees_moyenne_mode_calcul.py`

### 2. **Logique de calcul améliorée**

**Fonction** : `calculer_moyennes_classe()` dans `enseignant_view.py`

**Algorithme** :
1. Séparer les interrogations et les devoirs
2. Si mode = "interro_x2" :
   - Sélectionner la meilleure interrogation
   - Ajouter tous les devoirs
3. Sinon :
   - Créer des paires d'interrogations (2 interros = 1 note)
   - Combiner avec les devoirs individuels
   - Trier et sélectionner les N meilleures notes composées
4. Enregistrer le mode et les IDs des évaluations utilisées

### 3. **Affichage intelligent du relevé**

**Fonction** : `voir_releve_notes()` et `imprimer_releve_notes()`

- Récupère le mode de calcul enregistré
- Filtre les évaluations selon les IDs enregistrés
- Affiche **uniquement les notes utilisées**
- Adapte le message selon le mode

### 4. **Templates mis à jour**

**Fichiers modifiés** :
- `noter_eleves.html` : Ajout du sélecteur de mode
- `voir_releve_notes.html` : Bouton "Soumettre le relevé"
- `imprimer_releve_notes.html` : Page d'impression professionnelle

---

## 📊 Exemples concrets

### Exemple 1 : Mode "2 meilleures notes (composées)"

**Fatou DIAGNE** :
- Interro 1 : 8.5/10 → 17/20
- Interro 2 : 8/10 → 16/20
- **Paire** : (17 + 16) / 2 = **16.5/20**
- Devoir 1 : **18.5/20**
- Contrôle : **18/20**
- Devoir 3 : 17.5/20

**Notes composées** : [16.5, 18.5, 18, 17.5]
**2 meilleures** : 18.5 et 18
**Moyenne** : (18.5 + 18) / 2 = **18.25/20** ✅

**Évaluations affichées** : Devoir 1, Interro 1, Interro 2 (car la paire n'est pas la meilleure)

---

### Exemple 2 : Mode "1 Meilleure interro × 2"

**Fatou DIAGNE** :
- Interro 1 : 8.5/10 → **17/20** (meilleure)
- Interro 2 : 8/10 → 16/20
- Devoir 1 : 18.5/20
- Contrôle : 18/20
- Devoir 3 : 17.5/20

**Notes utilisées** : [17 (interro × 2), 18.5, 18, 17.5]
**Moyenne** : (17 + 18.5 + 18 + 17.5) / 4 = **17.75/20** ✅

**Évaluations affichées** : Interro 1, Devoir 1, Contrôle, Devoir 3

---

## ✅ Tests effectués

### Test 1 : Mode "2 meilleures notes (composées)"
- ✅ 5 évaluations cochées
- ✅ Calcul avec paires d'interrogations
- ✅ Sélection des 2 meilleures
- ✅ Enregistrement dans la base
- ✅ Affichage correct dans le relevé (3 évaluations)
- ✅ Page d'impression professionnelle

### Test 2 : Mode "1 Meilleure interro × 2"
- ✅ Sélection de la meilleure interrogation
- ✅ Ajout de tous les devoirs
- ✅ Calcul de la moyenne
- ✅ Enregistrement du mode "interro_x2"
- ✅ Affichage correct dans le relevé (4 évaluations)
- ✅ Message adapté dans la page d'impression

### Test 3 : Persistance des données
- ✅ Les moyennes persistent après actualisation
- ✅ Le mode de calcul est enregistré
- ✅ Les IDs des évaluations utilisées sont sauvegardés
- ✅ Le relevé affiche uniquement les bonnes évaluations

---

## 🔐 Sécurité et cohérence

### Verrouillage du relevé
- Une fois le relevé soumis, les notes sont **verrouillées**
- Le bouton "Soumettre le relevé" est **uniquement dans la page du relevé**
- Après soumission : statut "Relevé soumis" visible

### Cohérence des données
- Les moyennes ne s'affichent **que si elles ont été calculées**
- Avant calcul : colonne "Moyenne" affiche "--"
- Après calcul : colonne "Moyenne" affiche la valeur calculée
- Les évaluations affichées correspondent **exactement** au mode utilisé

---

## 📁 Fichiers modifiés

### Models
- `school_admin/model/moyenne_model.py` : Ajout de `mode_calcul` et `evaluations_utilisees`

### Views
- `school_admin/personal_views/enseignant_view.py` :
  - `calculer_moyennes_classe()` : Logique de notes composées
  - `voir_releve_notes()` : Filtrage des évaluations
  - `imprimer_releve_notes()` : Nouvelle vue pour l'impression

### Templates
- `school_admin/templates/school_admin/enseignant/noter_eleves.html` : Sélecteur de mode
- `school_admin/templates/school_admin/enseignant/voir_releve_notes.html` : Bouton "Soumettre"
- `school_admin/templates/school_admin/enseignant/imprimer_releve_notes.html` : Page d'impression

### URLs
- `school_admin/personal_url/enseignant_url.py` : Route `imprimer_releve`

### Migrations
- `school_admin/migrations/0086_moyenne_evaluations_utilisees_moyenne_mode_calcul.py`

---

## 🎓 Avantages du système

1. **Flexibilité** : Le professeur peut choisir le mode de calcul le plus adapté
2. **Équité** : Les paires d'interrogations sont automatiquement équivalentes à un devoir
3. **Transparence** : Le mode de calcul utilisé est clairement affiché sur le relevé
4. **Traçabilité** : Toutes les évaluations utilisées sont enregistrées
5. **Professionnalisme** : Page d'impression de qualité pour les parents

---

## 🚀 Utilisation recommandée

### Pour un trimestre standard :
1. Créer **2 interrogations** (sur 10)
2. Créer **2-3 devoirs/contrôles** (sur 20)
3. Noter tous les élèves
4. Utiliser le mode "**2 meilleures notes (composées)**"
5. Calculer les moyennes
6. Vérifier le relevé
7. Soumettre le relevé
8. Imprimer pour distribution aux parents

---

*Document généré le 21/10/2025*
*Système Goo-School - Gestion de notes et évaluations*


