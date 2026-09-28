"""
Contrôleur directeur : volume horaire EDT × tarif → montant à payer.
"""
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from school_admin.model.caisse_etablissement_model import (
    AbsenceEnseignant,
    PaieProfesseurPeriode,
)
from school_admin.model.compte_user import CompteUser
from school_admin.services.caisse import net_apres_retenue
from school_admin.services.recouvrement import devise_etablissement

from ..model.emploi_du_temps_model import CreneauEmploiDuTemps
from ..model.professeur_model import Professeur
from ..utils.volume_horaire import (
    calculer_volume_horaire,
    minutes_creneaux_pour_date,
    minutes_vers_heures,
    montant_a_payer,
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
        data = request.POST if request.method == 'POST' else request.GET
        kind = (data.get('periode') or 'mois').strip().lower()
        if kind not in ('semaine', 'mois', 'annee'):
            kind = 'mois'

        if kind == 'semaine':
            reference = VolumeHoraireController._parse_date(
                data.get('semaine_du') or data.get('date'), aujourdhui
            )
        elif kind == 'mois':
            reference = VolumeHoraireController._parse_mois(
                data.get('mois'), date(aujourdhui.year, aujourdhui.month, 1)
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
    def _query_periode(periode):
        params = f"?periode={periode.kind}"
        if periode.kind == 'semaine':
            params += f"&date={periode.date_debut.isoformat()}"
        elif periode.kind == 'mois':
            params += f"&mois={periode.date_debut.year:04d}-{periode.date_debut.month:02d}"
        return params

    @staticmethod
    def _minutes_absences_et_remplacements(etablissement, professeur_id, periode):
        absences = AbsenceEnseignant.objects.filter(
            etablissement=etablissement,
            professeur_id=professeur_id,
            date__gte=periode.date_debut,
            date__lte=periode.date_fin,
        )
        remplacements = AbsenceEnseignant.objects.filter(
            etablissement=etablissement,
            remplacant_id=professeur_id,
            date__gte=periode.date_debut,
            date__lte=periode.date_fin,
        )
        minutes_abs = absences.aggregate(s=Sum('minutes'))['s'] or 0
        minutes_rempl = remplacements.aggregate(s=Sum('minutes'))['s'] or 0
        return int(minutes_abs), int(minutes_rempl), absences.exists() or remplacements.exists()

    @staticmethod
    def _resultat_avec_absences(creneaux, periode, professeur, etablissement):
        minutes_abs, minutes_rempl, _has_fiches = (
            VolumeHoraireController._minutes_absences_et_remplacements(
                etablissement, professeur.id, periode
            )
        )
        base = calculer_volume_horaire(
            creneaux,
            periode,
            professeur.prix_volume_horaire,
            minutes_absences=minutes_abs,
            absences_disponibles=True,
        )
        minutes_finales = base.minutes_a_payer + minutes_rempl
        heures = minutes_vers_heures(minutes_finales)
        montant = montant_a_payer(heures, professeur.prix_volume_horaire)
        return base.__class__(
            heures_planifiees=base.heures_planifiees,
            heures=heures,
            minutes_planifiees=base.minutes_planifiees,
            minutes_absences=base.minutes_absences,
            minutes_a_payer=minutes_finales,
            montant=montant,
            prix_horaire=base.prix_horaire,
            note_absences=None,
            absences_disponibles=True,
            heures_semaine=base.heures_semaine,
        ), minutes_abs, minutes_rempl

    @staticmethod
    def _paie_periode(professeur, periode):
        return PaieProfesseurPeriode.objects.filter(
            professeur=professeur,
            date_debut=periode.date_debut,
            date_fin=periode.date_fin,
        ).first()

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

        for professeur in professeurs:
            creneaux_prof = par_prof.get(professeur.id, [])
            resultat, _abs, _rempl = VolumeHoraireController._resultat_avec_absences(
                creneaux_prof, periode, professeur, etablissement
            )
            total_heures += resultat.heures
            if resultat.montant is not None:
                total_montant += resultat.montant
                nb_avec_tarif += 1
            lignes.append({
                'professeur': professeur,
                'resultat': resultat,
                'paie': VolumeHoraireController._paie_periode(professeur, periode),
            })

        context.update({
            'lignes': lignes,
            'total_heures': total_heures,
            'total_montant': total_montant,
            'nb_professeurs': len(lignes),
            'nb_avec_tarif': nb_avec_tarif,
            'note_absences': None,
            'periode_vide': periode.est_vide,
            'query_periode': VolumeHoraireController._query_periode(periode),
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
        resultat, minutes_abs, minutes_rempl = VolumeHoraireController._resultat_avec_absences(
            creneaux, periode, professeur, etablissement
        )
        autres_profs = Professeur.objects.filter(
            etablissement=etablissement
        ).exclude(pk=professeur.id).order_by('nom', 'prenom')
        absences = list(
            AbsenceEnseignant.objects.filter(
                etablissement=etablissement,
                professeur=professeur,
                date__gte=periode.date_debut,
                date__lte=periode.date_fin,
            ).select_related('remplacant').order_by('-date')
        )
        context.update({
            'professeur': professeur,
            'resultat': resultat,
            'creneaux_lignes': VolumeHoraireController._lignes_creneaux(creneaux, periode),
            'note_absences': None,
            'periode_vide': periode.est_vide,
            'paie': VolumeHoraireController._paie_periode(professeur, periode),
            'autres_profs': autres_profs,
            'absences': absences,
            'minutes_remplacements': minutes_rempl,
            'query_periode': VolumeHoraireController._query_periode(periode),
        })
        return render(
            request,
            'school_admin/directeur/volume_horaire/detail_volume_horaire.html',
            context,
        )

    @staticmethod
    def _retour_detail(professeur_id, periode):
        url = reverse('directeur:detail_volume_horaire', args=[professeur_id])
        return HttpResponseRedirect(url + VolumeHoraireController._query_periode(periode))

    @staticmethod
    def _retour_liste(periode):
        url = reverse('directeur:liste_volume_horaire')
        return HttpResponseRedirect(url + VolumeHoraireController._query_periode(periode))

    @staticmethod
    @login_required
    @require_POST
    def marquer_paie_directeur(request, professeur_id):
        result = VolumeHoraireController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        etablissement, _is_directeur, _personnel = result
        professeur = get_object_or_404(
            Professeur, pk=professeur_id, etablissement=etablissement
        )
        annee_scolaire = VolumeHoraireController._get_session_directeur(
            request, etablissement
        )
        periode, _kind, _ref = VolumeHoraireController._periode_depuis_request(
            request, annee_scolaire
        )
        creneaux = list(
            VolumeHoraireController._creneaux_publies(
                etablissement, annee_scolaire, professeur=professeur
            )
        )
        resultat, _abs, _rempl = VolumeHoraireController._resultat_avec_absences(
            creneaux, periode, professeur, etablissement
        )
        if resultat.montant is None:
            messages.error(request, "Renseignez d'abord le tarif horaire sur la fiche du professeur.")
            return VolumeHoraireController._retour_detail(professeur.id, periode)

        try:
            retenue_pct = Decimal(str(request.POST.get('retenue_pct') or '0').replace(',', '.'))
        except (InvalidOperation, ValueError):
            retenue_pct = Decimal('0.00')
        if retenue_pct < 0:
            retenue_pct = Decimal('0.00')
        if retenue_pct > 100:
            retenue_pct = Decimal('100.00')

        net = net_apres_retenue(resultat.montant, retenue_pct)
        enregistre_par = request.user if isinstance(request.user, CompteUser) else None
        paie, created = PaieProfesseurPeriode.objects.get_or_create(
            professeur=professeur,
            date_debut=periode.date_debut,
            date_fin=periode.date_fin,
            defaults={
                'etablissement': etablissement,
                'annee_scolaire': annee_scolaire,
                'heures': resultat.heures,
                'montant_brut': resultat.montant,
                'retenue_pct': retenue_pct,
                'montant_net': net,
                'enregistre_par': enregistre_par,
            },
        )
        if not created:
            messages.info(request, "Cette période est déjà marquée comme payée.")
        else:
            try:
                from school_admin.services.comptabilite_generale import pont_paie

                pont_paie(paie, annee_scolaire=annee_scolaire, user=enregistre_par)
            except Exception:
                pass
        if created:
            from school_admin.services.realtime_helpers import emit_live

            emit_live(
                etablissement.id,
                'paie.mise_a_jour',
                {
                    'event': 'paie.mise_a_jour',
                    'id': paie.id,
                    'professeur_id': professeur.id,
                },
            )
            devise = devise_etablissement(etablissement)
            messages.success(
                request,
                f"Paie enregistrée : {net} {devise} net pour {professeur.nom_complet}.",
            )
        suivant = (request.POST.get('next') or 'detail').strip()
        if suivant == 'liste':
            return VolumeHoraireController._retour_liste(periode)
        return VolumeHoraireController._retour_detail(professeur.id, periode)

    @staticmethod
    @login_required
    def fiche_paie_directeur(request, professeur_id):
        result = VolumeHoraireController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        etablissement, is_directeur, personnel = result
        professeur = get_object_or_404(
            Professeur, pk=professeur_id, etablissement=etablissement
        )
        annee_scolaire = VolumeHoraireController._get_session_directeur(
            request, etablissement
        )
        periode, _kind, _ref = VolumeHoraireController._periode_depuis_request(
            request, annee_scolaire
        )
        paie = VolumeHoraireController._paie_periode(professeur, periode)
        if paie is None:
            messages.error(request, "Marquez d'abord cette période comme payée.")
            return VolumeHoraireController._retour_detail(professeur.id, periode)
        return render(
            request,
            'school_admin/directeur/volume_horaire/fiche_paie.html',
            {
                'etablissement': etablissement,
                'professeur': professeur,
                'paie': paie,
                'periode': periode,
                'annee_scolaire_active': annee_scolaire,
                'devise_monnaie': devise_etablissement(etablissement),
                'is_directeur': is_directeur,
                'personnel': personnel,
                'query_periode': VolumeHoraireController._query_periode(periode),
            },
        )

    @staticmethod
    @login_required
    @require_POST
    def enregistrer_absence_directeur(request, professeur_id):
        result = VolumeHoraireController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        etablissement, _is_directeur, _personnel = result
        professeur = get_object_or_404(
            Professeur, pk=professeur_id, etablissement=etablissement
        )
        annee_scolaire = VolumeHoraireController._get_session_directeur(
            request, etablissement
        )
        periode, _kind, _ref = VolumeHoraireController._periode_depuis_request(
            request, annee_scolaire
        )
        try:
            jour = datetime.strptime(request.POST.get('date') or '', '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Indiquez la date d'absence.")
            return VolumeHoraireController._retour_detail(professeur.id, periode)

        remplacant = None
        remplacant_id = (request.POST.get('remplacant_id') or '').strip()
        if remplacant_id:
            remplacant = Professeur.objects.filter(
                pk=remplacant_id, etablissement=etablissement
            ).exclude(pk=professeur.id).first()

        creneaux = list(
            VolumeHoraireController._creneaux_publies(
                etablissement, annee_scolaire, professeur=professeur
            )
        )
        minutes = minutes_creneaux_pour_date(creneaux, jour)
        _obj, created = AbsenceEnseignant.objects.get_or_create(
            professeur=professeur,
            date=jour,
            defaults={
                'etablissement': etablissement,
                'remplacant': remplacant,
                'minutes': minutes,
            },
        )
        if not created:
            messages.info(request, "Une absence est déjà enregistrée pour ce jour.")
        else:
            messages.success(request, "Absence enregistrée. Les heures à payer sont recalculées.")
        return VolumeHoraireController._retour_detail(professeur.id, periode)

    @staticmethod
    @login_required
    @require_POST
    def supprimer_absence_directeur(request, professeur_id, absence_id):
        result = VolumeHoraireController._get_user_etablissement(request)
        if result[0] is None:
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        etablissement, _is_directeur, _personnel = result
        professeur = get_object_or_404(
            Professeur, pk=professeur_id, etablissement=etablissement
        )
        annee_scolaire = VolumeHoraireController._get_session_directeur(
            request, etablissement
        )
        periode, _kind, _ref = VolumeHoraireController._periode_depuis_request(
            request, annee_scolaire
        )
        absence = get_object_or_404(
            AbsenceEnseignant,
            pk=absence_id,
            professeur=professeur,
            etablissement=etablissement,
        )
        absence.delete()
        messages.success(request, "Absence supprimée.")
        return VolumeHoraireController._retour_detail(professeur.id, periode)
