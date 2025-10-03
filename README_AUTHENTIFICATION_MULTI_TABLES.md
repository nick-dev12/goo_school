# Guide d'Authentification Multi-Tables

Ce guide explique comment ajouter de nouveaux types d'utilisateurs (professeurs, étudiants, etc.) à votre système d'authentification existant.

## 📋 Table des Matières

1. [Architecture Actuelle](#architecture-actuelle)
2. [Étapes pour Ajouter un Nouveau Type d'Utilisateur](#étapes-pour-ajouter-un-nouveau-type-dutilisateur)
3. [Exemple Pratique : Ajouter les Professeurs](#exemple-pratique--ajouter-les-professeurs)
4. [Configuration du Backend d'Authentification](#configuration-du-backend-dauthentification)
5. [Gestion des Redirections](#gestion-des-redirections)
6. [Tests et Validation](#tests-et-validation)
7. [Bonnes Pratiques](#bonnes-pratiques)

---

## 🏗️ Architecture Actuelle

Votre système d'authentification actuel gère **3 types d'utilisateurs** :

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   CompteUser    │    │  Etablissement   │    │  Nouveau Modèle     │
│                 │    │                  │    │   (ex: Professeur)  │
│ - Administrateur│    │ - Directeur      │    │ - Professeur        │
│ - Commercial    │    │ - Établissement  │    │ - Étudiant          │
│ - Support       │    │                  │    │ - Parent            │
│ - Comptable     │    │                  │    │                     │
│ - etc.          │    │                  │    │                     │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
         │                       │                        │
         └───────────────────────┼────────────────────────┘
                                 │
                    ┌─────────────────────────┐
                    │  MultiUserBackend       │
                    │  (Backend Auth)         │
                    │                         │
                    │ - authenticate()        │
                    │ - get_user()           │
                    └─────────────────────────┘
```

---

## 🚀 Étapes pour Ajouter un Nouveau Type d'Utilisateur

### **Étape 1 : Créer le Modèle**

Créez un nouveau modèle qui hérite de `AbstractUser` :

```python
# school_admin/model/professeur_model.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class Professeur(AbstractUser):
    """
    Modèle représentant un professeur
    """
    MATIERE_CHOICES = [
        ('mathematiques', 'Mathématiques'),
        ('francais', 'Français'),
        ('anglais', 'Anglais'),
        ('sciences', 'Sciences'),
        ('histoire', 'Histoire'),
        ('geographie', 'Géographie'),
        ('sport', 'Éducation Physique'),
    ]
    
    NIVEAU_CHOICES = [
        ('primaire', 'Primaire'),
        ('college', 'Collège'),
        ('lycee', 'Lycée'),
    ]
    
    # Informations personnelles
    nom = models.CharField(max_length=100, verbose_name="Nom")
    prenom = models.CharField(max_length=100, verbose_name="Prénom")
    email = models.EmailField(unique=True, verbose_name="Email")
    telephone = models.CharField(max_length=20, verbose_name="Téléphone")
    date_naissance = models.DateField(verbose_name="Date de naissance")
    photo = models.ImageField(upload_to='professeur_photos/', null=True, blank=True)
    
    # Informations professionnelles
    matiere_principale = models.CharField(max_length=50, choices=MATIERE_CHOICES)
    matieres_secondaires = models.JSONField(default=list, blank=True)
    niveau_enseigne = models.CharField(max_length=20, choices=NIVEAU_CHOICES)
    numero_employe = models.CharField(max_length=20, unique=True)
    date_embauche = models.DateField(default=timezone.now)
    
    # Relation avec l'établissement
    etablissement = models.ForeignKey(
        'school_admin.Etablissement', 
        on_delete=models.CASCADE,
        related_name='professeurs'
    )
    
    # Informations système
    date_creation = models.DateTimeField(default=timezone.now)
    date_modification = models.DateTimeField(auto_now=True)
    actif = models.BooleanField(default=True)
    
    # Configuration d'authentification
    username = models.CharField(unique=True, max_length=100)
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['nom', 'prenom', 'email']
    
    # Relations ManyToMany avec related_name uniques
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name="professeur_set",
        related_query_name="professeur",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name="professeur_set",
        related_query_name="professeur",
    )
    
    class Meta:
        verbose_name = "Professeur"
        verbose_name_plural = "Professeurs"
        ordering = ['-date_creation']
        
    def __str__(self):
        return f"{self.prenom} {self.nom} - {self.get_matiere_principale_display()}"
    
    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"
```

### **Étape 2 : Créer et Appliquer les Migrations**

```bash
# Créer la migration
python manage.py makemigrations school_admin --name add_professeur_model

# Appliquer la migration
python manage.py migrate school_admin
```

### **Étape 3 : Mettre à Jour le Backend d'Authentification**

Modifiez `school_admin/authentication_backends.py` :

```python
# school_admin/authentication_backends.py

from django.contrib.auth.backends import BaseBackend
from .model.compte_user import CompteUser
from .model.etablissement_model import Etablissement
from .model.professeur_model import Professeur  # ← Nouveau import

class MultiUserBackend(BaseBackend):
    """
    Backend d'authentification personnalisé qui gère tous les types d'utilisateurs
    """
    
    # Liste des modèles d'utilisateurs à vérifier
    USER_MODELS = [
        CompteUser,
        Etablissement,
        Professeur,  # ← Ajouter le nouveau modèle
        # Ajouter d'autres modèles ici au besoin
    ]
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authentifie un utilisateur en vérifiant tous les modèles d'utilisateurs
        """
        if username is None or password is None:
            return None
        
        # Essayer chaque modèle d'utilisateur
        for UserModel in self.USER_MODELS:
            try:
                user = UserModel.objects.get(username=username)
                if user.check_password(password):
                    return user
            except UserModel.DoesNotExist:
                continue
        
        return None
    
    def get_user(self, user_id):
        """
        Récupère un utilisateur par son ID en vérifiant tous les modèles
        """
        for UserModel in self.USER_MODELS:
            try:
                return UserModel.objects.get(pk=user_id)
            except UserModel.DoesNotExist:
                continue
        
        return None
```

### **Étape 4 : Mettre à Jour le Contrôleur de Connexion**

Modifiez `school_admin/controllers/compte_user_controller.py` :

```python
# Dans la méthode compte_user_login_view, section de redirection

# Redirection vers l'URL next si présente, sinon vers le tableau de bord approprié
if next_url:
    return None, redirect(next_url)
else:
    # Déterminer le type d'utilisateur et rediriger
    if isinstance(user, Etablissement):
        return None, redirect('school_admin:dashboard_directeur')
    elif isinstance(user, Professeur):  # ← Nouveau cas
        return None, redirect('school_admin:dashboard_professeur')
    else:
        # CompteUser - redirection basée sur la fonction
        return None, CompteUserController._redirect_based_on_function(user.fonction)
```

### **Étape 5 : Créer la Vue du Professeur**

Créez `school_admin/personal_views/professeur_view.py` :

```python
# school_admin/personal_views/professeur_view.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from ..model.professeur_model import Professeur

@login_required
def dashboard_professeur(request):
    """
    Vue du tableau de bord pour les professeurs
    """
    # Vérifier que l'utilisateur connecté est bien un professeur
    if not isinstance(request.user, Professeur):
        return redirect('school_admin:connexion_compte_user')
    
    professeur = request.user
    
    context = {
        'professeur': professeur,
        'nom_complet': professeur.nom_complet,
        'matiere_principale': professeur.get_matiere_principale_display(),
        'niveau': professeur.get_niveau_enseigne_display(),
        'etablissement': professeur.etablissement,
        'numero_employe': professeur.numero_employe,
        'date_embauche': professeur.date_embauche,
        'matieres_secondaires': professeur.matieres_secondaires,
    }
    
    return render(request, 'school_admin/professeur/dashboard_professeur.html', context)
```

### **Étape 6 : Ajouter les URLs**

Dans `school_admin/urls.py` :

```python
# Ajouter l'import
from .personal_views.professeur_view import *

# Ajouter l'URL dans urlpatterns
path('dashboard/professeur/', dashboard_professeur, name='dashboard_professeur'),
```

### **Étape 7 : Créer le Template**

Créez le template `school_admin/templates/school_admin/professeur/dashboard_professeur.html` :

```html
<!-- school_admin/templates/school_admin/professeur/dashboard_professeur.html -->
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Professeur - {{ professeur.nom_complet }}</title>
</head>
<body>
    <div class="container">
        <h1>Bienvenue {{ professeur.nom_complet }}</h1>
        
        <div class="info-card">
            <h2>Informations Professionnelles</h2>
            <p><strong>Matière principale :</strong> {{ matiere_principale }}</p>
            <p><strong>Niveau :</strong> {{ niveau }}</p>
            <p><strong>Établissement :</strong> {{ etablissement.nom }}</p>
            <p><strong>Numéro employé :</strong> {{ numero_employe }}</p>
            <p><strong>Date d'embauche :</strong> {{ date_embauche }}</p>
        </div>
        
        <!-- Ajouter d'autres sections selon les besoins -->
    </div>
</body>
</html>
```

---

## 📝 Exemple Pratique : Ajouter les Professeurs

Voici un exemple complet pour ajouter les professeurs :

### **1. Créer le Modèle Professeur**

```bash
# Créer le fichier modèle
touch school_admin/model/professeur_model.py
```

Copiez le code du modèle Professeur ci-dessus dans ce fichier.

### **2. Créer et Appliquer les Migrations**

```bash
python manage.py makemigrations school_admin --name add_professeur_model
python manage.py migrate school_admin
```

### **3. Mettre à Jour le Backend**

Modifiez `authentication_backends.py` pour inclure le modèle Professeur.

### **4. Créer un Professeur de Test**

```python
# create_test_professeur.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from school_admin.model.professeur_model import Professeur
from school_admin.model.etablissement_model import Etablissement

# Récupérer un établissement existant
etablissement = Etablissement.objects.first()

if etablissement:
    professeur = Professeur.objects.create(
        nom='Diallo',
        prenom='Moussa',
        email='moussa.diallo@example.com',
        username='prof_moussa',
        telephone='771234567',
        date_naissance='1985-05-15',
        matiere_principale='mathematiques',
        niveau_enseigne='college',
        numero_employe='PROF001',
        etablissement=etablissement
    )
    
    professeur.set_password('ProfTest123!')
    professeur.save()
    
    print(f"✅ Professeur créé : {professeur.nom_complet}")
    print(f"   Username: {professeur.username}")
    print(f"   Password: ProfTest123!")
else:
    print("❌ Aucun établissement trouvé")
```

---

## 🔧 Configuration du Backend d'Authentification

### **Version Évolutive du Backend**

Pour faciliter l'ajout de nouveaux types d'utilisateurs, utilisez cette version :

```python
# school_admin/authentication_backends.py

from django.contrib.auth.backends import BaseBackend
from django.apps import apps

class MultiUserBackend(BaseBackend):
    """
    Backend d'authentification dynamique qui découvre automatiquement
    tous les modèles héritant d'AbstractUser
    """
    
    def get_user_models(self):
        """
        Retourne tous les modèles d'utilisateurs de l'application
        """
        user_models = []
        
        # Modèles définis manuellement
        try:
            from .model.compte_user import CompteUser
            user_models.append(CompteUser)
        except ImportError:
            pass
            
        try:
            from .model.etablissement_model import Etablissement
            user_models.append(Etablissement)
        except ImportError:
            pass
            
        try:
            from .model.professeur_model import Professeur
            user_models.append(Professeur)
        except ImportError:
            pass
        
        # Ajouter d'autres modèles ici...
        
        return user_models
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        
        for UserModel in self.get_user_models():
            try:
                user = UserModel.objects.get(username=username)
                if user.check_password(password):
                    return user
            except UserModel.DoesNotExist:
                continue
        
        return None
    
    def get_user(self, user_id):
        for UserModel in self.get_user_models():
            try:
                return UserModel.objects.get(pk=user_id)
            except UserModel.DoesNotExist:
                continue
        
        return None
```

---

## 🎯 Gestion des Redirections

### **Méthode Centralisée de Redirection**

Créez une fonction centralisée pour gérer toutes les redirections :

```python
# school_admin/controllers/compte_user_controller.py

@staticmethod
def redirect_user_after_login(user):
    """
    Redirige l'utilisateur vers le bon dashboard selon son type
    """
    from ..model.etablissement_model import Etablissement
    from ..model.professeur_model import Professeur
    # Importer d'autres modèles au besoin
    
    # Mapping des types d'utilisateurs vers leurs dashboards
    redirect_mapping = {
        Etablissement: 'school_admin:dashboard_directeur',
        Professeur: 'school_admin:dashboard_professeur',
        # Ajouter d'autres mappings ici
    }
    
    # Vérifier le type d'utilisateur
    for user_type, dashboard_url in redirect_mapping.items():
        if isinstance(user, user_type):
            return redirect(dashboard_url)
    
    # Par défaut, pour CompteUser, utiliser la fonction
    if hasattr(user, 'fonction'):
        return CompteUserController._redirect_based_on_function(user.fonction)
    
    # Fallback vers le dashboard principal
    return redirect('school_admin:dashboard')
```

Puis dans la méthode de connexion :

```python
# Dans compte_user_login_view
if next_url:
    return None, redirect(next_url)
else:
    return None, CompteUserController.redirect_user_after_login(user)
```

---

## 🧪 Tests et Validation

### **Script de Test Complet**

```python
# test_multi_auth.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from django.contrib.auth import authenticate
from school_admin.model.compte_user import CompteUser
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.professeur_model import Professeur

def test_authentication():
    """
    Teste l'authentification pour tous les types d'utilisateurs
    """
    test_users = [
        ('admin_test', 'CompteUser'),
        ('directeur_test', 'Etablissement'),
        ('prof_moussa', 'Professeur'),
    ]
    
    for username, expected_type in test_users:
        print(f"\n🔍 Test de connexion pour {username} ({expected_type})")
        
        # Tenter l'authentification
        user = authenticate(username=username, password='TestPassword123!')
        
        if user:
            print(f"✅ Authentification réussie")
            print(f"   Type: {type(user).__name__}")
            print(f"   Nom: {getattr(user, 'nom_complet', user.username)}")
            print(f"   Email: {user.email}")
        else:
            print(f"❌ Échec de l'authentification")

if __name__ == "__main__":
    test_authentication()
```

---

## 📚 Bonnes Pratiques

### **1. Structure des Modèles**

- ✅ Toujours hériter de `AbstractUser`
- ✅ Définir des `related_name` uniques pour `groups` et `user_permissions`
- ✅ Utiliser des choix (`CHOICES`) pour les champs avec valeurs limitées
- ✅ Ajouter des propriétés utiles (`@property`)

### **2. Sécurité**

- ✅ Utiliser `@login_required` sur toutes les vues protégées
- ✅ Vérifier le type d'utilisateur dans chaque vue
- ✅ Valider les données d'entrée
- ✅ Utiliser des mots de passe forts

### **3. Maintenance**

- ✅ Documenter chaque nouveau type d'utilisateur
- ✅ Créer des tests pour chaque nouveau modèle
- ✅ Utiliser des migrations nommées explicitement
- ✅ Garder le backend d'authentification flexible

### **4. Performance**

- ✅ Utiliser `select_related()` pour les relations ForeignKey
- ✅ Indexer les champs de recherche fréquents
- ✅ Limiter les requêtes dans les templates

---

## 🔄 Processus d'Ajout Rapide

Pour ajouter un nouveau type d'utilisateur rapidement :

1. **Créer le modèle** → `school_admin/model/nouveau_model.py`
2. **Faire les migrations** → `makemigrations` + `migrate`
3. **Ajouter au backend** → Modifier `authentication_backends.py`
4. **Créer la vue** → `school_admin/personal_views/nouveau_view.py`
5. **Ajouter l'URL** → Modifier `urls.py`
6. **Créer le template** → `templates/school_admin/nouveau/dashboard.html`
7. **Tester** → Créer un utilisateur de test et valider la connexion

---

## 📞 Support

Si vous rencontrez des problèmes :

1. Vérifiez les logs Django
2. Testez l'authentification via le shell Django
3. Vérifiez que toutes les migrations sont appliquées
4. Assurez-vous que les `related_name` sont uniques

Ce système est extensible et vous permet d'ajouter facilement de nouveaux types d'utilisateurs selon vos besoins !
