from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View




def dashboard_comptable(request):
    # Vue simple pour le tableau de bord comptable
    # Les données sont maintenant statiques dans le HTML
    return render(request, 'school_admin/gestion_comptable/dashboard_comptable.html')


def suivi_revenus(request):
    # Vue pour le suivi des revenus avec onglets Entrées/Dépenses
    return render(request, 'school_admin/gestion_comptable/suivi_revenus.html')


def paiements_retard(request):
    # Vue pour le suivi des paiements en retard
    return render(request, 'school_admin/gestion_comptable/paiements_retard.html')


def calculs_automatiques(request):
    # Vue pour les calculs automatiques
    return render(request, 'school_admin/gestion_comptable/calculs_automatiques.html')


def rapports_mensuels(request):
    # Vue pour les rapports mensuels (bilan mensuel)
    return render(request, 'school_admin/gestion_comptable/rapports_mensuels.html')


def rapports_annuels(request):
    # Vue pour les rapports annuels (bilan annuel)
    return render(request, 'school_admin/gestion_comptable/rapports_annuels.html')


def gestion_etablissements(request):
    # Vue pour la gestion des établissements et factures
    return render(request, 'school_admin/gestion_comptable/gestion_etablissements.html')


def details_financiers_etablissement(request):
    # Vue pour les détails financiers d'un établissement
    return render(request, 'school_admin/gestion_comptable/details_financiers_etablissement.html')


def facture_etablissement(request):
    # Vue pour afficher la facture d'un établissement
    return render(request, 'school_admin/gestion_comptable/facture_etablissement.html')


def gestion_personnel_financier(request):
    # Vue pour la gestion financière du personnel
    return render(request, 'school_admin/gestion_comptable/gestion_personnel_financier.html')


def gestion_depenses(request):
    # Vue pour la gestion des dépenses
    return render(request, 'school_admin/gestion_comptable/gestion_depenses.html')
