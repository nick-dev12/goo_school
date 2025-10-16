"""
URL configuration for school project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('school_admin.urls', namespace='school_admin')),
    path('', include('school_admin.personal_url.directeur_url', namespace='directeur')),
    path('', include('school_admin.personal_url.personnel_url', namespace='personnel')),
    path('', include('school_admin.personal_url.administrateur_etablissement_url', namespace='administrateur_etablissement')),
    path('', include('school_admin.personal_url.personnel_administratif_url', namespace='personnel_administratif')),
    path('', include('school_admin.personal_url.secretaire_url', namespace='secretaire')),
    path('', include('school_admin.personal_url.professeur_url', namespace='professeur')),
    path('', include('school_admin.personal_url.enseignant_url', namespace='enseignant')),
    path('', include('school_admin.personal_url.eleve_url', namespace='eleve')),
    path('', include('school_admin.personal_url.matiere_url', namespace='matiere')),
    path('', include('school_admin.personal_url.affectation_url', namespace='affectation')),
    path('', include('school_admin.personal_url.salle_url', namespace='salle')),
    path('', include('school_admin.personal_url.affectation_salle_url', namespace='affectation_salle')),
]

# Servir les fichiers média en mode développement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
