"""
Contrôleur directeur : volume horaire EDT × tarif → montant à payer.
"""
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from ..model.emploi_du_temps_model import CreneauEmploiDuTemps
from ..model.professeur_model import Professeur
from ..utils.volume_horaire import (
    calculer_volume_horaire,
    resoudre_periode,
)


class VolumeHoraireController:
    """Liste et détail du volume horaire à payer, calculés côté serveur."""

    @staticmethod
    def _get_user_etablissement(request):
        from ..personal_views.directeur_view import _get_user_etablissement as helper
        return helper(request)

    @staticmethod
    def _get_session_directeur(request, etablissement):
        from ..personal_views.directeur_view import _get_session_directeur as helper
        return helper(request, etablissement)

    @staticmethod
    def _get_devise(etablissement):
        if etablissement and getattr(etablissement, 'devise_monnaie', None):
            devise = etablissement.devise_monnaie.strip()
            if devise:
                return devise
        return 'FCFA'

    @staticmethod
    def _parse_date(value, fallback):
        if not value:
            return fallback
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _parse_mois(value, fallback):
        if not value:
            return fallback
        try:
            parsed = datetime.strptime(value, '%Y-%m').date()
            return date(parsed.year, parsed.month, 1)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _periode_depuis_request(request, annee_scolaire, aujourdhui=None):
        aujourdhui = aujourdhui or date.today()
        kind = (request.GET.get('periode') or 'mois').strip().lower()
        if kind not in ('semaine', 'mois', 'annee'):
            kind = 'mois'

        if kind == 'semaine':
            reference = VolumeHoraireController._parse_date(
                request.GET.get('date'), aujourdhui
            )
        elif kind == 'mois':
            reference = VolumeHoraireController._parse_mois(
                request.GET.get('mois'), date(aujourdhui.year, aujourdhui.month, 1)
            )
        else:
            reference = aujourdhui

        try:
            periode = resoudre_periode(
                kind,
                reference=reference,
                annee_scolaire=annee_scolaire,
            )
        except ValueError:
            periode = resoudre_periode(
                'mois',
                reference=date(aujourdhui.year, aujourdhui.month, 1),
                annee_scolaire=annee_scolaire,
            )
            kind = periode.kind
        return periode, kind, reference

    @staticmethod
    def _creneaux_publies(etablissement, annee_scolaire, professeur=None):
        qs = CreneauEmploiDuTemps.objects.filter(
            professeur__etablissement=etablissement,
            professeur__isnull=False,
            emploi_du_temps__est_actif=True,
            emploi_du_temps__statut_publication='publie',
        ).exclude(type_cours='pause')
        if professeur is not None:
            qs = qs.filter(professeur=professeur)
        if annee_scolaire is not None:
            qs = qs.filter(
                Q(emploi_du_temps__annee_scolaire_fk=annee_scolaire)
                | Q(
                    emploi_du_temps__annee_scolaire_fk__isnull=True,
                    emploi_du_temps__annee_scolaire=annee_scolaire.libelle,
                )
            )
        return qs.select_related(
            'professeur',
            'matiere',
            'emploi_du_temps__classe',
            'periode_etablissement',
        ).order_by('jour', 'heure_debut')

    @staticmethod
    def _lignes_creneaux(creneaux, periode):
        from ..utils.volume_horaire import JOURS_SEMAINE, occurrences_jours, minutes_vers_heures

        occ = occurrences_jours(periode.date_debut, periode.date_fin) if not periode.est_vide else {
            jour: 0 for jour in JOURS_SEMAINE
        }
        lignes = []
        for creneau in creneaux:
            if getattr(creneau, 'est_pause', False):
                continue
            minutes = int(creneau.duree_minutes or 0)
            if minutes <= 0:
                continue
            n = occ.get(creneau.jour, 0)
            classe = getattr(creneau.emploi_du_temps, 'classe', None)
            lignes.append({
                'creneau': creneau,
                'classe': classe,
                'matiere': creneau.matiere,
                'jour': creneau.get_jour_display() if hasattr(creneau, 'get_jour_display') else creneau.jour,
                'heure_debut': creneau.heure_debut,
                'heure_fin': creneau.heure_fin,
                'duree_minutes': minutes,
                'heures_semaine': minutes_vers_heures(minutes),
                'occurrences': n,
                'heures_periode': minutes_vers_heures(minutes * n),
            })
        return lignes

    @staticmethod
    def _contexte_commun(request, etablissement, is_directeur, personnel, annee_scolaire):
        periode, kind, reference = VolumeHoraireController._periode_depuis_request(
            request, annee_scolaire
        )
        return {
            'etablissement': etablissement,
            'is_directeur': is_directeur,
            'is_personnel_administratif': not is_directeur,
            'personnel': personnel if not is_directeur else None,
            'annee_scolaire_active': annee_scolaire,
            'periode': periode,
            'periode_kind': kind,
            'periode_reference': reference,
            'periode_date_value': reference.isoformat(),
            'periode_mois_value': f"{reference.year:04d}-{reference.month:02d}",
            'devise_monnaie': VolumeHoraireController._get_devise(etablissement),
            'note_absences': None,
            'absences_disponibles': False,
        }

    @staticmethod
    @login_required
    def liste_volume_horaire_directeur(request):
        result = VolumeHoraireController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        etablissement, is_directeur, personnel = result
        annee_scolaire = VolumeHoraireController._get_session_directeur(
            request, etablissement
        )
        context = VolumeHoraireController._contexte_commun(
            request, etablissement, is_directeur, personnel, annee_scolaire
        )
        periode = context['periode']

        professeurs = list(
            Professeur.objects.filter(etablissement=etablissement)
            .select_related('matiere_principale')
            .order_by('nom', 'prenom')
        )
        creneaux = VolumeHoraireController._creneaux_publies(etablissement, annee_scolaire)
        par_prof = defaultdict(list)
        for creneau in creneaux:
            par_prof[creneau.professeur_id].append(creneau)

        lignes = []
        total_heures = Decimal('0.00')
        total_montant = Decimal('0.00')
        nb_avec_tarif = 0
        note_absences = None

        for professeur in professeurs:
            resultat = calculer_volume_horaire(
                par_prof.get(professeur.id, []),
                periode,
                professeur.prix_volume_horaire,
            )
            if resultat.note_absences:
                note_absences = resultat.note_absences
            total_heures += resultat.heures
            if resultat.montant is not None:
                total_montant += resultat.montant
                nb_avec_tarif += 1
            lignes.append({
                'professeur': professeur,
                'resultat': resultat,
            })

        context.update({
            'lignes': lignes,
            'total_heures': total_heures,
            'total_montant': total_montant,
            'nb_professeurs': len(lignes),
            'nb_avec_tarif': nb_avec_tarif,
            'note_absences': note_absences,
            'periode_vide': periode.est_vide,
        })
        return render(
            request,
            'school_admin/directeur/volume_horaire/liste_volume_horaire.html',
            context,
        )

    @staticmethod
    @login_required
    def detail_volume_horaire_directeur(request, professeur_id):
        result = VolumeHoraireController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        etablissement, is_directeur, personnel = result
        professeur = get_object_or_404(
            Professeur.objects.select_related('matiere_principale', 'etablissement'),
            pk=professeur_id,
            etablissement=etablissement,
        )
        annee_scolaire = VolumeHoraireController._get_session_directeur(
            request, etablissement
        )
        context = VolumeHoraireController._contexte_commun(
            request, etablissement, is_directeur, personnel, annee_scolaire
        )
        periode = context['periode']
        creneaux = list(
            VolumeHoraireController._creneaux_publies(
                etablissement, annee_scolaire, professeur=professeur
            )
        )
        resultat = calculer_volume_horaire(
            creneaux, periode, professeur.prix_volume_horaire
        )
        context.update({
            'professeur': professeur,
            'resultat': resultat,
            'creneaux_lignes': VolumeHoraireController._lignes_creneaux(creneaux, periode),
            'note_absences': resultat.note_absences,
            'periode_vide': periode.est_vide,
        })
        return render(
            request,
            'school_admin/directeur/volume_horaire/detail_volume_horaire.html',
            context,
        )
