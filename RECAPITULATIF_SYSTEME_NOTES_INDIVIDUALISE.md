# 📊 SYSTÈME DE CALCUL DES MOYENNES INDIVIDUALISÉ ET SIMPLIFIÉ

## ✅ Objectifs atteints

### 1. **Calcul individualisé par élève**
Chaque élève a **sa propre sélection** des meilleures notes :
- ✅ Si pour un élève ce sont **2 devoirs** qui sont les meilleurs → on prend 2 devoirs
- ✅ Si pour un autre c'est **1 devoir + 1 paire d'interrogations** → on prend cette combinaison
- ✅ Si pour un autre ce sont **3 devoirs** → on prend 3 devoirs
- ✅ La sélection est **automatique et intelligente** selon les performances

### 2. **Affichage simplifié du relevé**
- ✅ **Colonnes génériques** : "Devoir 1", "Devoir 2", etc. au lieu des titres d'évaluations
- ✅ **2 meilleures notes** → Affiche **2 colonnes** (Devoir 1, Devoir 2)
- ✅ **3 meilleures notes** → Affiche **3 colonnes** (Devoir 1, Devoir 2, Devoir 3)
- ✅ Les **paires d'interrogations** comptent comme **un devoir** dans l'affichage

### 3. **Persistance et traçabilité**
- ✅ Les **détails des notes** sont enregistrés dans la base de données
- ✅ Chaque note stockée contient : titre, valeur, barème, type, IDs d'évaluations
- ✅ Le **mode de calcul** est sauvegardé pour chaque moyenne
- ✅ Les données persistent après actualisation

---

## 📋 Exemple concret : Mode "2 meilleures notes"

### Élève 1 : **Fatou DIAGNE**
**Notes disponibles** :
- Interro 1 : 8.5/10 → 17/20
- Interro 2 : 8/10 → 16/20
- Devoir 1 : **18.5/20** ⭐
- Contrôle : **18/20** ⭐
- Devoir 3 : 17.5/20

**Paires créées** :
- Paire (Interro 1 + Interro 2) : (17 + 16) / 2 = **16.5/20**
- Devoir 1 : **18.5/20**
- Contrôle : **18/20**
- Devoir 3 : 17.5/20

**2 meilleures** : 18.5 et 18
**Moyenne** : (18.5 + 18) / 2 = **18.25/20**

**Affichage dans le relevé** :
| Devoir 1 | Devoir 2 | Moyenne |
|----------|----------|---------|
| **18,50** | **18,00** | **18,25/20** |

---

### Élève 2 : **Justine JOVILA**
**Notes disponibles** :
- Interro 1 : 7/10 → 14/20
- Interro 2 : 6.5/10 → 13/20
- Devoir 1 : **15/20** ⭐
- Contrôle : 13.5/20
- Devoir 3 : 13/20

**Paires créées** :
- Paire (Interro 1 + Interro 2) : (14 + 13) / 2 = **13.5/20** ⭐
- Devoir 1 : **15/20**
- Contrôle : 13.5/20
- Devoir 3 : 13/20

**2 meilleures** : 15 et 13.5 (paire)
**Moyenne** : (15 + 13.5) / 2 = **14.25/20**

**Affichage dans le relevé** :
| Devoir 1 | Devoir 2 | Moyenne |
|----------|----------|---------|
| **15,00** | **13,50** (Interro 1+2) | **14,25/20** |

---

## 🔧 Modifications techniques

### 1. **Modèle `Moyenne` étendu**

**Nouveau champ** :
```python
details_notes = models.JSONField(
    default=list,
    blank=True,
    verbose_name="Détails des notes utilisées (valeurs, titres, barèmes)"
)
```

**Structure stockée** :
```json
[
  {
    "titre": "Devoir 1",
    "note": 18.5,
    "bareme": 20,
    "evaluations_ids": [23],
    "type": "devoir"
  },
  {
    "titre": "Devoir 2",
    "note": 18.0,
    "bareme": 20,
    "evaluations_ids": [18],
    "type": "devoir"
  }
]
```

### 2. **Logique de calcul individualisée**

**Fonction** : `calculer_moyennes_classe()` dans `enseignant_view.py`

**Pour chaque élève** :
1. Récupérer toutes ses notes
2. Séparer interrogations et devoirs
3. Créer les paires d'interrogations (2 interros = 1 note)
4. Créer la liste de notes composées
5. **Trier et sélectionner les N meilleures pour CET ÉLÈVE**
6. Stocker les détails avec titres simplifiés ("Devoir 1", "Devoir 2", etc.)

### 3. **Affichage du relevé**

**Vue** : `voir_releve_notes()` et `imprimer_releve_notes()`

**Logique** :
1. Récupérer le `mode_calcul` de la première moyenne
2. Déterminer le nombre de colonnes à afficher
3. Créer des `colonnes_devoirs` génériques (Devoir 1, Devoir 2, etc.)
4. Pour chaque élève, afficher ses `notes_simplifiees` depuis la base

### 4. **Template tag amélioré**

**Filtre** : `get_item()` dans `notes_tags.py`

Maintenant compatible avec :
- **Dictionnaires** : `{{ mon_dict|get_item:ma_cle }}`
- **Listes** : `{{ ma_liste|get_item:0 }}`

---

## 📊 Modes de calcul disponibles

### a) **Toutes les notes**
Chaque élève : toutes ses notes (paires d'interros + devoirs)

### b) **2 meilleures notes (composées)**
Chaque élève : ses 2 meilleures notes parmi toutes les notes composées

### c) **3 meilleures notes (composées)**
Chaque élève : ses 3 meilleures notes parmi toutes les notes composées

### d) **4 meilleures notes (composées)**
Chaque élève : ses 4 meilleures notes parmi toutes les notes composées

### e) **1 Meilleure interro × 2**
Chaque élève : sa meilleure interrogation (comptée 2 fois) + tous ses devoirs

---

## 🎯 Points clés du système

### Individualisation
- ✅ Chaque élève a **sa propre combinaison** de notes
- ✅ Un élève peut avoir 2 devoirs, un autre 1 devoir + 1 paire d'interros
- ✅ La sélection se fait **automatiquement** selon les performances

### Simplification de l'affichage
- ✅ **Colonnes génériques** : Devoir 1, Devoir 2, Devoir 3
- ✅ **Pas de titres d'évaluations** dans le relevé
- ✅ **2 interrogations** affichées comme **1 devoir** dans le relevé
- ✅ **Clarté maximale** pour les parents

### Traçabilité complète
- ✅ Chaque note stocke les **IDs des évaluations** utilisées
- ✅ Le **type** de chaque note est enregistré (devoir, paire_interro, etc.)
- ✅ Le **mode de calcul** est sauvegardé
- ✅ **Audit trail** complet de la composition de chaque moyenne

---

## 📁 Fichiers modifiés

### Models
- `school_admin/model/moyenne_model.py` : Ajout du champ `details_notes`
- **Migration** : `0087_moyenne_details_notes.py`

### Views
- `school_admin/personal_views/enseignant_view.py` :
  - `calculer_moyennes_classe()` : Individualisation + stockage des détails
  - `voir_releve_notes()` : Affichage avec colonnes simplifiées
  - `imprimer_releve_notes()` : Affichage avec colonnes simplifiées

### Templates
- `school_admin/templates/school_admin/enseignant/voir_releve_notes.html` : Boucle sur `colonnes_devoirs`
- `school_admin/templates/school_admin/enseignant/imprimer_releve_notes.html` : Boucle sur `colonnes_devoirs`

### Template Tags
- `school_admin/templatetags/notes_tags.py` : `get_item()` compatible avec listes et dictionnaires

---

## ✅ Tests réussis

### Test 1 : Mode "2 meilleures notes"
- ✅ Fatou : 2 devoirs sélectionnés
- ✅ Justine : 1 devoir + 1 paire d'interros
- ✅ Ludvanne : 2 devoirs sélectionnés
- ✅ Nick : 2 devoirs sélectionnés
- ✅ Cheikh : 2 devoirs sélectionnés (pas les mêmes que les autres)

### Test 2 : Affichage simplifié
- ✅ Relevé affiche "Devoir 1" et "Devoir 2"
- ✅ Page d'impression affiche "Devoir 1" et "Devoir 2"
- ✅ Statistiques : "2 Notes sur 20" au lieu de "2 Évaluations"
- ✅ Mode de calcul expliqué clairement

### Test 3 : Persistance
- ✅ Les détails persistent après actualisation
- ✅ Les notes affichées sont identiques après rechargement
- ✅ Les moyennes restent stables

---

## 🚀 Avantages du système

1. **Équité maximale** : Chaque élève est évalué sur ses meilleures performances
2. **Flexibilité** : Un élève peut avoir une combinaison différente d'un autre
3. **Clarté** : L'affichage "Devoir 1, Devoir 2" est simple et compréhensible
4. **Professionnalisme** : Le relevé est épuré et professionnel
5. **Transparence** : Le mode de calcul est clairement indiqué

---

*Document généré le 21/10/2025*  
*Système Goo-School - Calcul individualisé des moyennes*


