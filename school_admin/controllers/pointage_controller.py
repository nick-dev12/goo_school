"""Pointage des enseignants : borne QR, contrôle des cours par la direction, pointage côté enseignant."""
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from school_admin.model.pointage_model import BornePointage, SeanceCours
from school_admin.model.professeur_model import Professeur
from school_admin.services import pointage as pt


def acces_direction(request, permission='pointage_controle'):
    """(établissement, is_directeur, personnel) si l'utilisateur peut contrôler le pointage, sinon None."""
    from school_admin.personal_views.directeur_view import _get_user_etablissement
    from school_admin.utils.decorators_permissions import check_permission

    etablissement, is_directeur, personnel = _get_user_etablissement(request)
    if etablissement is None:
        return None
    if not is_directeur and not check_permission(request.user, permission):
        return None
    return etablissement, is_directeur, personnel


def _annee(request, etablissement):
    from school_admin.personal_views.directeur_view import _get_session_directeur

    return _get_session_directeur(request, etablissement)


def _jour(valeur, defaut):
    try:
        return datetime.strptime(valeur or '', '%Y-%m-%d').date()
    except ValueError:
        return defaut


class PointageController:
    # ------------------------------------------------------------------ contrôle (direction)
    @staticmethod
    @login_required
    def controle(request):
        acces = acces_direction(request)
        if acces is None:
            messages.error(request, "Vous n'avez pas accès au contrôle du pointage.")
            return redirect('directeur:dashboard_directeur')
        etab, is_directeur, personnel = acces
        annee = _annee(request, etab)
        today = timezone.localdate()
        jour = _jour(request.GET.get('jour'), today)

        if request.method == 'POST':
            action = request.POST.get('action')
            try:
                if action == 'decider':
                    seance = get_object_or_404(SeanceCours, pk=request.POST.get('seance_id'), etablissement=etab)
                    remplacant = None
                    if request.POST.get('remplacant_id'):
                        remplacant = Professeur.objects.filter(pk=request.POST['remplacant_id'],
                                                               etablissement=etab).first()
                    pt.decider(seance, request.user, request.POST.get('decision'),
                               request.POST.get('commentaire', ''), remplacant=remplacant)
                    messages.success(request, f"Séance de {seance.professeur.nom_complet} ({seance.classe.nom}, "
                                              f"{seance.date:%d/%m} {seance.heure_debut:%H:%M}) : "
                                              f"{seance.get_statut_display().lower()}.")
                elif action == 'borne_creer' and is_directeur:
                    libelle = (request.POST.get('libelle') or '').strip() or 'Borne principale'
                    BornePointage.objects.create(etablissement=etab, libelle=libelle[:80],
                                                 emplacement=(request.POST.get('emplacement') or '')[:120])
                    messages.success(request, f"Borne « {libelle} » créée. Ouvrez-la sur la tablette ou l'écran de l'école.")
                elif action == 'borne_regenerer' and is_directeur:
                    borne = get_object_or_404(BornePointage, pk=request.POST.get('borne_id'), etablissement=etab)
                    borne.regenerer_secret()
                    messages.success(request, "Borne désappairée : rouvrez-la depuis l'appareil de l'école en étant connecté.")
                elif action == 'borne_activer' and is_directeur:
                    borne = get_object_or_404(BornePointage, pk=request.POST.get('borne_id'), etablissement=etab)
                    borne.actif = not borne.actif
                    borne.save(update_fields=['actif'])
                    messages.success(request, f"Borne {'activée' if borne.actif else 'désactivée'}.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect(request.get_full_path())

        activation = pt.preparer_periode(etab, jour, jour, annee)
        seances = list(SeanceCours.objects.filter(etablissement=etab, date=jour)
                       .select_related('professeur', 'classe', 'matiere', 'remplacant', 'borne')
                       .order_by('heure_debut', 'classe__nom'))
        maintenant = timezone.localtime().time()
        for s in seances:
            s.libelles_anomalies = pt.libelles_anomalies(s)
            s.est_maintenant = jour == today and s.heure_debut <= maintenant < s.heure_fin
        a_verifier = list(SeanceCours.objects.filter(etablissement=etab, statut__in=('a_verifier', 'contestee'))
                          .select_related('professeur', 'classe', 'matiere', 'borne').order_by('-date', 'heure_debut')[:80])
        for s in a_verifier:
            s.libelles_anomalies = pt.libelles_anomalies(s)
        resume = pt.resume_jour(etab, jour)
        bornes = list(BornePointage.objects.filter(etablissement=etab))
        for b in bornes:
            b.url_affichage = request.build_absolute_uri(reverse('directeur:pointage_borne', args=[b.pk]))
        return render(request, 'school_admin/directeur/volume_horaire/controle.html', {
            'etablissement': etab, 'is_directeur': is_directeur, 'personnel': personnel,
            'annee_scolaire_active': annee, 'jour': jour, 'today': today,
            'jour_precedent': jour - timedelta(days=1), 'jour_suivant': jour + timedelta(days=1),
            'seances': seances, 'a_verifier': a_verifier, 'resume': resume, 'bornes': bornes,
            'activation': activation,
            'professeurs': Professeur.objects.filter(etablissement=etab, actif=True).order_by('nom', 'prenom'),
            'en_cours': [s for s in seances if s.statut == 'en_cours'],
            'manquants': [s for s in seances if s.statut == 'prevue' and s.est_maintenant],
        })

    # ------------------------------------------------------------------ borne (appareil appairé)
    COOKIE = 'aria_borne_{}'

    @staticmethod
    def _borne_autorisee(request, borne_id):
        """La borne s'affiche sur un appareil appairé (cookie signé) ou pour la direction connectée."""
        borne = BornePointage.objects.filter(pk=borne_id, actif=True).select_related('etablissement').first()
        if borne is None:
            return None, False
        jeton = request.get_signed_cookie(PointageController.COOKIE.format(borne.pk), default=None,
                                          salt='aria-borne')
        if jeton and jeton == borne.secret:
            return borne, False
        if request.user.is_authenticated:
            acces = acces_direction(request)
            if acces is not None and acces[0].pk == borne.etablissement_id:
                return borne, True
        return None, False

    @staticmethod
    @never_cache
    def borne(request, borne_id):
        borne, appairer = PointageController._borne_autorisee(request, borne_id)
        if borne is None:
            return render(request, 'school_admin/directeur/volume_horaire/borne_refusee.html', status=403)
        response = render(request, 'school_admin/directeur/volume_horaire/borne.html', {
            'borne': borne, 'etablissement': borne.etablissement,
            'url_code': reverse('directeur:pointage_borne_code', args=[borne.pk]),
        })
        if appairer:
            response.set_signed_cookie(PointageController.COOKIE.format(borne.pk), borne.secret, salt='aria-borne',
                                       max_age=60 * 60 * 24 * 365, httponly=True, samesite='Lax',
                                       secure=request.is_secure())
        return response

    @staticmethod
    @never_cache
    def borne_code(request, borne_id):
        borne, _appairer = PointageController._borne_autorisee(request, borne_id)
        if borne is None:
            return JsonResponse({'ok': False}, status=403)
        BornePointage.objects.filter(pk=borne.pk).update(derniere_activite=timezone.now())
        today = timezone.localdate()
        maintenant = timezone.localtime().time()
        en_cours = SeanceCours.objects.filter(etablissement_id=borne.etablissement_id, date=today,
                                              statut='en_cours').count()
        limite = (datetime.combine(today, maintenant) + timedelta(minutes=pt.OUVERTURE_AVANT)).time()
        a_ouvrir = SeanceCours.objects.filter(etablissement_id=borne.etablissement_id, date=today, statut='prevue',
                                              heure_debut__lte=limite, heure_fin__gt=maintenant).count()
        return JsonResponse({
            'ok': True, 'contenu': pt.contenu_qr(borne), 'code': pt.code_borne(borne),
            'secondes': pt.secondes_restantes(), 'heure': timezone.localtime().strftime('%H:%M'),
            'en_cours': en_cours, 'a_ouvrir': a_ouvrir,
        })

    # ------------------------------------------------------------------ enseignant
    @staticmethod
    @login_required
    def enseignant(request):
        prof = request.user
        if not isinstance(prof, Professeur):
            messages.error(request, "Cette page est réservée aux enseignants.")
            return redirect('school_admin:connexion_compte_user')
        etab = prof.etablissement
        from school_admin.utils.session_utils import get_session_active

        annee = get_session_active(request, etab) if etab else None
        today = timezone.localdate()
        if request.method == 'POST':
            action = request.POST.get('action')
            seance = get_object_or_404(SeanceCours, pk=request.POST.get('seance_id'), professeur=prof)
            try:
                if action == 'commencer':
                    pt.commencer(seance, prof, saisie_qr=request.POST.get('qr', ''),
                                 sans_qr_motif=request.POST.get('motif_sans_qr', ''))
                    messages.success(request, f"Cours ouvert : {seance.classe.nom}. Faites l'appel maintenant.")
                elif action == 'terminer':
                    pt.terminer(seance, request.POST.get('cahier_texte', ''))
                    seance.refresh_from_db()
                    if seance.statut == 'validee':
                        messages.success(request, "Cours validé. Il sera compté dans votre paie.")
                    else:
                        messages.warning(request, "Cours enregistré. Il sera vérifié par la direction : "
                                         + " ; ".join(pt.libelles_anomalies(seance)) + ".")
                elif action == 'contester':
                    pt.contester(seance, prof, request.POST.get('motif', ''))
                    messages.success(request, "Contestation envoyée à la direction.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect(request.path)

        activation = pt.preparer_periode(etab, today.replace(day=1), today + timedelta(days=7), annee) if etab else None
        seances_jour = list(SeanceCours.objects.filter(professeur=prof, date=today)
                            .select_related('classe', 'matiere').order_by('heure_debut'))
        maintenant = timezone.now()
        for s in seances_jour:
            ok, retard = pt.peut_ouvrir(s, maintenant)
            s.ouvrable = ok
            s.en_retard = retard
            ouverture, _l = pt.fenetre_ouverture(s)
            s.ouverture = timezone.localtime(ouverture)
            s.libelles_anomalies = pt.libelles_anomalies(s)
        debut_mois = today.replace(day=1)
        calc = pt.calculer_paie(prof, debut_mois, today, annee, activation)
        historique = list(SeanceCours.objects.filter(professeur=prof, date__gte=debut_mois, date__lt=today)
                          .select_related('classe', 'matiere').order_by('-date', '-heure_debut')[:60])
        for s in historique:
            s.libelles_anomalies = pt.libelles_anomalies(s)
        ns = 'enseignant_primaire' if request.resolver_match.namespace == 'enseignant_primaire' else 'enseignant'
        return render(request, 'school_admin/enseignant/pointage.html', {
            'professeur': prof, 'etablissement': etab, 'annee_scolaire_active': annee, 'today': today,
            'seances_jour': seances_jour, 'historique': historique, 'calcul': calc, 'activation': activation,
            'ns': ns, 'devise_monnaie': getattr(etab, 'devise_monnaie', '') or 'FCFA',
        })
