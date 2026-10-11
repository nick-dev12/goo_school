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

    # ------------------------------------------------------------------ accès
    @staticmethod
    def _acces(request, paiement=False):
        """(établissement, is_directeur, personnel) ; pour payer il faut la permission comptabilité."""
        from school_admin.controllers.pointage_controller import acces_direction

        acces = acces_direction(request, 'comptabilite_paiements')
        if acces is None and not paiement:
            acces = acces_direction(request, 'pointage_controle')
        return acces

    @staticmethod
    def _refus(request):
        messages.error(request, "Accès non autorisé.")
        return redirect('directeur:dashboard_directeur')

    @staticmethod
    def _calculs(etablissement, annee_scolaire, periode, professeurs):
        from school_admin.services import pointage as pt

        activation = pt.preparer_periode(etablissement, periode.date_debut, periode.date_fin, annee_scolaire)
        return activation, {p.id: pt.calculer_paie(p, periode.date_debut, periode.date_fin, annee_scolaire, activation)
                            for p in professeurs}

    # ------------------------------------------------------------------ liste
    @staticmethod
    @login_required
    def liste_volume_horaire_directeur(request):
        acces = VolumeHoraireController._acces(request)
        if acces is None:
            return VolumeHoraireController._refus(request)
        etablissement, is_directeur, personnel = acces
        annee_scolaire = VolumeHoraireController._get_session_directeur(request, etablissement)
        context = VolumeHoraireController._contexte_commun(request, etablissement, is_directeur, personnel,
                                                           annee_scolaire)
        periode = context['periode']
        professeurs = list(Professeur.objects.filter(etablissement=etablissement)
                           .select_related('matiere_principale').order_by('nom', 'prenom'))
        activation, calculs = VolumeHoraireController._calculs(etablissement, annee_scolaire, periode, professeurs)
        lignes = []
        totaux = {'prevues': Decimal('0'), 'validees': Decimal('0'), 'montant': Decimal('0'), 'a_verifier': 0,
                  'absentes': 0, 'payes': 0}
        for prof in professeurs:
            c = calculs[prof.id]
            if not c.minutes_prevues and not c.minutes_remplacements:
                continue
            paie = VolumeHoraireController._paie_periode(prof, periode)
            lignes.append({'professeur': prof, 'calcul': c, 'paie': paie})
            totaux['prevues'] += c.heures_prevues
            totaux['validees'] += c.heures_validees
            totaux['montant'] += c.brut or Decimal('0')
            totaux['a_verifier'] += 1 if c.minutes_a_verifier else 0
            totaux['absentes'] += c.minutes_absentes
            totaux['payes'] += 1 if paie else 0
        totaux['absentes_h'] = minutes_vers_heures(totaux['absentes'])
        totaux['taux'] = round(totaux['validees'] / totaux['prevues'] * 100) if totaux['prevues'] else None
        context.update({
            'lignes': lignes, 'totaux': totaux, 'activation': activation, 'periode_vide': periode.est_vide,
            'nb_professeurs': len(lignes), 'query_periode': VolumeHoraireController._query_periode(periode),
            'peut_payer': VolumeHoraireController._acces(request, paiement=True) is not None,
        })
        return render(request, 'school_admin/directeur/volume_horaire/liste_volume_horaire.html', context)

    # ------------------------------------------------------------------ détail
    @staticmethod
    @login_required
    def detail_volume_horaire_directeur(request, professeur_id):
        from school_admin.model.finances_model import CompteTresorerie
        from school_admin.model.pointage_model import SeanceCours
        from school_admin.services import pointage as pt

        acces = VolumeHoraireController._acces(request)
        if acces is None:
            return VolumeHoraireController._refus(request)
        etablissement, is_directeur, personnel = acces
        professeur = get_object_or_404(Professeur.objects.select_related('matiere_principale', 'etablissement'),
                                       pk=professeur_id, etablissement=etablissement)
        annee_scolaire = VolumeHoraireController._get_session_directeur(request, etablissement)
        context = VolumeHoraireController._contexte_commun(request, etablissement, is_directeur, personnel,
                                                           annee_scolaire)
        periode = context['periode']
        activation, calculs = VolumeHoraireController._calculs(etablissement, annee_scolaire, periode, [professeur])
        seances = list(SeanceCours.objects.filter(Q(professeur=professeur) | Q(remplacant=professeur),
                                                  date__gte=periode.date_debut, date__lte=periode.date_fin)
                       .select_related('classe', 'matiere', 'remplacant', 'professeur', 'borne', 'paie')
                       .order_by('-date', '-heure_debut'))
        for seance in seances:
            seance.libelles_anomalies = pt.libelles_anomalies(seance)
        creneaux = list(VolumeHoraireController._creneaux_publies(etablissement, annee_scolaire, professeur=professeur))
        context.update({
            'professeur': professeur, 'calcul': calculs[professeur.id], 'seances': seances,
            'activation': activation, 'periode_vide': periode.est_vide,
            'paie': VolumeHoraireController._paie_periode(professeur, periode),
            'creneaux_lignes': VolumeHoraireController._lignes_creneaux(creneaux, periode),
            'autres_profs': Professeur.objects.filter(etablissement=etablissement).exclude(pk=professeur.id)
                                              .order_by('nom', 'prenom'),
            'absences': list(AbsenceEnseignant.objects.filter(etablissement=etablissement, professeur=professeur,
                                                              date__gte=periode.date_debut, date__lte=periode.date_fin)
                             .select_related('remplacant').order_by('-date')),
            'comptes_tresorerie': CompteTresorerie.objects.filter(etablissement=etablissement, actif=True,
                                                                  statut='ouvert'),
            'peut_payer': VolumeHoraireController._acces(request, paiement=True) is not None,
            'query_periode': VolumeHoraireController._query_periode(periode),
        })
        return render(request, 'school_admin/directeur/volume_horaire/detail_volume_horaire.html', context)

    @staticmethod
    def _retour_detail(professeur_id, periode):
        url = reverse('directeur:detail_volume_horaire', args=[professeur_id])
        return HttpResponseRedirect(url + VolumeHoraireController._query_periode(periode))

    @staticmethod
    def _retour_liste(periode):
        url = reverse('directeur:liste_volume_horaire')
        return HttpResponseRedirect(url + VolumeHoraireController._query_periode(periode))

    # ------------------------------------------------------------------ paie
    @staticmethod
    @login_required
    @require_POST
    def marquer_paie_directeur(request, professeur_id):
        from school_admin.model.finances_model import CompteTresorerie
        from school_admin.services import pointage as pt

        acces = VolumeHoraireController._acces(request, paiement=True)
        if acces is None:
            return VolumeHoraireController._refus(request)
        etablissement, _is_directeur, _personnel = acces
        professeur = get_object_or_404(Professeur, pk=professeur_id, etablissement=etablissement)
        annee_scolaire = VolumeHoraireController._get_session_directeur(request, etablissement)
        periode, _kind, _ref = VolumeHoraireController._periode_depuis_request(request, annee_scolaire)
        _activation, calculs = VolumeHoraireController._calculs(etablissement, annee_scolaire, periode, [professeur])
        try:
            retenue_pct = Decimal(str(request.POST.get('retenue_pct') or '0').replace(',', '.'))
        except (InvalidOperation, ValueError):
            retenue_pct = Decimal('0.00')
        retenue_pct = min(max(retenue_pct, Decimal('0')), Decimal('100'))
        compte = None
        if request.POST.get('compte_tresorerie_id'):
            compte = CompteTresorerie.objects.filter(pk=request.POST['compte_tresorerie_id'],
                                                     etablissement=etablissement).first()
        try:
            paie = pt.enregistrer_paie(calculs[professeur.id], etablissement, annee_scolaire, retenue_pct,
                                       compte_tresorerie=compte, user=request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            from school_admin.services.realtime_helpers import emit_live

            emit_live(etablissement.id, 'paie.mise_a_jour',
                      {'event': 'paie.mise_a_jour', 'id': paie.id, 'professeur_id': professeur.id})
            net = f"{paie.montant_net:,.0f}".replace(',', ' ')
            messages.success(request, f"Paie enregistrée : {net} {devise_etablissement(etablissement)} net pour "
                                      f"{professeur.nom_complet}. L'écriture comptable est passée.")
        if (request.POST.get('next') or '') == 'liste':
            return VolumeHoraireController._retour_liste(periode)
        return VolumeHoraireController._retour_detail(professeur.id, periode)

    @staticmethod
    @login_required
    def fiche_paie_directeur(request, professeur_id):
        acces = VolumeHoraireController._acces(request)
        if acces is None:
            return VolumeHoraireController._refus(request)
        etablissement, is_directeur, personnel = acces
        professeur = get_object_or_404(Professeur, pk=professeur_id, etablissement=etablissement)
        annee_scolaire = VolumeHoraireController._get_session_directeur(request, etablissement)
        periode, _kind, _ref = VolumeHoraireController._periode_depuis_request(request, annee_scolaire)
        paie = VolumeHoraireController._paie_periode(professeur, periode)
        if paie is None:
            messages.error(request, "Enregistrez d'abord la paie de cette période.")
            return VolumeHoraireController._retour_detail(professeur.id, periode)
        return render(request, 'school_admin/directeur/volume_horaire/fiche_paie.html', {
            'etablissement': etablissement, 'professeur': professeur, 'paie': paie, 'periode': periode,
            'seances': paie.seances.select_related('classe', 'matiere').order_by('date', 'heure_debut'),
            'annee_scolaire_active': annee_scolaire, 'devise_monnaie': devise_etablissement(etablissement),
            'is_directeur': is_directeur, 'personnel': personnel,
            'query_periode': VolumeHoraireController._query_periode(periode),
        })

    # ------------------------------------------------------------------ absences déclarées
    @staticmethod
    @login_required
    @require_POST
    def enregistrer_absence_directeur(request, professeur_id):
        """Absence prévue ou justifiée : les séances du jour passent en absence justifiée, ou en
        remplacées si un remplaçant est choisi. Avant la mise en service du pointage, une fiche
        d'absence est enregistrée comme avant."""
        from school_admin.model.pointage_model import SeanceCours
        from school_admin.services import pointage as pt

        acces = VolumeHoraireController._acces(request)
        if acces is None:
            return VolumeHoraireController._refus(request)
        etablissement, _is_directeur, _personnel = acces
        professeur = get_object_or_404(Professeur, pk=professeur_id, etablissement=etablissement)
        annee_scolaire = VolumeHoraireController._get_session_directeur(request, etablissement)
        periode, _kind, _ref = VolumeHoraireController._periode_depuis_request(request, annee_scolaire)
        try:
            jour = datetime.strptime(request.POST.get('date') or '', '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Indiquez la date d'absence.")
            return VolumeHoraireController._retour_detail(professeur.id, periode)
        remplacant = None
        if (request.POST.get('remplacant_id') or '').strip():
            remplacant = Professeur.objects.filter(pk=request.POST['remplacant_id'],
                                                   etablissement=etablissement).exclude(pk=professeur.id).first()
        activation = pt.preparer_periode(etablissement, jour, jour, annee_scolaire)
        if activation and jour >= activation:
            seances = (SeanceCours.objects.filter(professeur=professeur, date=jour, paie__isnull=True)
                       .exclude(statut__in=('validee', 'annulee')))
            n = 0
            for seance in seances:
                pt.decider(seance, request.user, 'remplacer' if remplacant else 'justifier',
                           request.POST.get('motif', 'Absence déclarée'), remplacant=remplacant)
                n += 1
            if not n:
                messages.info(request, "Aucune séance modifiable ce jour-là.")
            elif remplacant:
                messages.success(request, f"{n} séance(s) du {jour:%d/%m/%Y} confiée(s) à {remplacant.nom_complet}.")
            else:
                messages.success(request, f"{n} séance(s) du {jour:%d/%m/%Y} marquée(s) absence justifiée.")
            return VolumeHoraireController._retour_detail(professeur.id, periode)

        creneaux = list(VolumeHoraireController._creneaux_publies(etablissement, annee_scolaire, professeur=professeur))
        _obj, created = AbsenceEnseignant.objects.get_or_create(
            professeur=professeur, date=jour,
            defaults={'etablissement': etablissement, 'remplacant': remplacant,
                      'minutes': minutes_creneaux_pour_date(creneaux, jour)},
        )
        if created:
            messages.success(request, "Absence enregistrée. Les heures à payer sont recalculées.")
        else:
            messages.info(request, "Une absence est déjà enregistrée pour ce jour.")
        return VolumeHoraireController._retour_detail(professeur.id, periode)

    @staticmethod
    @login_required
    @require_POST
    def supprimer_absence_directeur(request, professeur_id, absence_id):
        acces = VolumeHoraireController._acces(request)
        if acces is None:
            return VolumeHoraireController._refus(request)
        etablissement, _is_directeur, _personnel = acces
        professeur = get_object_or_404(Professeur, pk=professeur_id, etablissement=etablissement)
        annee_scolaire = VolumeHoraireController._get_session_directeur(request, etablissement)
        periode, _kind, _ref = VolumeHoraireController._periode_depuis_request(request, annee_scolaire)
        absence = get_object_or_404(AbsenceEnseignant, pk=absence_id, professeur=professeur,
                                    etablissement=etablissement)
        absence.delete()
        messages.success(request, "Absence supprimée.")
        return VolumeHoraireController._retour_detail(professeur.id, periode)

    @staticmethod
    @login_required
    @require_POST
    def contrat_directeur(request, professeur_id):
        """Type de contrat, tarif horaire, salaire mensuel et heures prévues au contrat."""
        acces = VolumeHoraireController._acces(request, paiement=True)
        if acces is None:
            return VolumeHoraireController._refus(request)
        etablissement, _is_directeur, _personnel = acces
        professeur = get_object_or_404(Professeur, pk=professeur_id, etablissement=etablissement)
        annee_scolaire = VolumeHoraireController._get_session_directeur(request, etablissement)
        periode, _kind, _ref = VolumeHoraireController._periode_depuis_request(request, annee_scolaire)

        def montant(nom):
            brut = (request.POST.get(nom) or '').replace(' ', '').replace(',', '.').strip()
            if not brut:
                return None
            valeur = Decimal(brut)
            if valeur < 0:
                raise InvalidOperation
            return valeur

        try:
            professeur.prix_volume_horaire = montant('prix_volume_horaire')
            professeur.salaire_mensuel = montant('salaire_mensuel')
            professeur.heures_contrat_semaine = montant('heures_contrat_semaine')
        except (InvalidOperation, ValueError):
            messages.error(request, "Montants invalides.")
            return VolumeHoraireController._retour_detail(professeur.id, periode)
        contrat = request.POST.get('type_contrat')
        if contrat in dict(Professeur.TYPE_CONTRAT_CHOICES):
            professeur.type_contrat = contrat
        if professeur.type_contrat == 'permanent' and professeur.salaire_mensuel is None:
            messages.warning(request, "Contrat permanent : indiquez le salaire mensuel pour pouvoir calculer la paie.")
        professeur.save(update_fields=['prix_volume_horaire', 'salaire_mensuel', 'heures_contrat_semaine',
                                       'type_contrat'])
        messages.success(request, f"Contrat de {professeur.nom_complet} mis à jour.")
        return VolumeHoraireController._retour_detail(professeur.id, periode)
