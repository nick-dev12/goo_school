"""
Admissions du supérieur : campagnes (dossier / concours), candidatures, épreuves et notes,
classement, désistements, inscription des admis ; formulaire public de candidature.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..model.admission_model import Candidature, Concours, EpreuveConcours
from ..model.classe_model import Classe
from ..services import admissions as svc
from ..utils.decorators_permissions import require_permission


def _acces(request):
    from ..utils.decorators_permissions import _get_user_etablissement
    from ..utils.session_utils import get_session_active

    etablissement = _get_user_etablissement(request, 'eleves_liste')[0]
    if etablissement is None:
        return None, None
    return etablissement, get_session_active(request, etablissement)


def _dec(v, nom, mini=0, maxi=20, vide_ok=True):
    v = (v or '').strip().replace(',', '.')
    if not v:
        if vide_ok:
            return None
        raise ValueError(nom)
    try:
        d = Decimal(v)
    except InvalidOperation:
        raise ValueError(nom)
    if d < mini or d > maxi:
        raise ValueError(nom)
    return d


def _ent(v, defaut=None):
    try:
        return int(v) if str(v or '').strip() else defaut
    except ValueError:
        return defaut


def remplir_candidature(c, post):
    """Remplit une candidature depuis un formulaire (administration ou public). Lève ValueError."""
    for champ in ('nom', 'prenom', 'lieu_naissance', 'telephone'):
        if not (post.get(champ) or '').strip():
            raise ValueError({'nom': 'le nom', 'prenom': 'le prénom', 'lieu_naissance': 'le lieu de naissance',
                              'telephone': 'le téléphone'}[champ] + ' est obligatoire')
    c.nom = post.get('nom').strip()[:100]
    c.prenom = post.get('prenom').strip()[:100]
    c.sexe = 'F' if post.get('sexe') == 'F' else 'M'
    try:
        c.date_naissance = date.fromisoformat(post.get('date_naissance') or '')
    except ValueError:
        raise ValueError('la date de naissance est invalide')
    c.lieu_naissance = post.get('lieu_naissance').strip()[:120]
    c.nationalite = (post.get('nationalite') or 'Sénégalaise').strip()[:60]
    c.telephone = post.get('telephone').strip()[:30]
    c.email = (post.get('email') or '').strip()[:254]
    c.adresse = (post.get('adresse') or '').strip()[:200]
    c.contact_nom = (post.get('contact_nom') or '').strip()[:100]
    c.contact_prenom = (post.get('contact_prenom') or '').strip()[:100]
    c.contact_telephone = (post.get('contact_telephone') or '').strip()[:30]
    if post.get('contact_lien') in dict(Candidature._meta.get_field('contact_lien').choices):
        c.contact_lien = post.get('contact_lien')
    c.serie_bac = post.get('serie_bac') if post.get('serie_bac') in dict(Candidature.SERIES_BAC) else ''
    c.annee_bac = _ent(post.get('annee_bac'))
    c.mention_bac = post.get('mention_bac') if post.get('mention_bac') in dict(Candidature.MENTIONS) else ''
    c.numero_table = (post.get('numero_table') or '').strip()[:30]
    c.moyenne_bac = _dec(post.get('moyenne_bac'), 'moyenne du bac')
    c.diplome_precedent = (post.get('diplome_precedent') or '').strip()[:160]
    c.etablissement_precedent = (post.get('etablissement_precedent') or '').strip()[:160]
    c.annee_diplome = _ent(post.get('annee_diplome'))
    c.moyenne_diplome = _dec(post.get('moyenne_diplome'), 'moyenne du diplôme')
    c.pieces = [p for p, _ in Candidature.PIECES if post.get(f'piece_{p}') == 'on']
    besoin = c.concours.diplome_requis
    if besoin == 'bac' and c.moyenne_bac is None and c.concours.mode != 'concours':
        raise ValueError('la moyenne du bac est obligatoire pour une admission sur dossier')
    if besoin in ('licence', 'master') and not c.diplome_precedent:
        raise ValueError('le diplôme précédent est obligatoire pour cette admission')
    return c


@login_required
@require_permission('eleves_liste')
def liste_concours(request):
    etablissement, annee = _acces(request)
    if etablissement is None or annee is None:
        return redirect('directeur:dashboard_directeur')
    if etablissement.type_etablissement != 'superieur':
        messages.info(request, "Les admissions par campagne concernent l'enseignement supérieur.")
        return redirect('directeur:dashboard_directeur')
    if request.method == 'POST':
        try:
            classe = Classe.objects.filter(id=request.POST.get('classe_cible'), etablissement=etablissement).first()
            mode = request.POST.get('mode') if request.POST.get('mode') in dict(Concours.MODE_CHOICES) else 'dossier'
            intitule = (request.POST.get('intitule') or '').strip()
            if not intitule:
                raise ValueError("l'intitulé est obligatoire")
            c = Concours.objects.create(
                etablissement=etablissement, annee_scolaire=annee, intitule=intitule[:160], classe_cible=classe,
                mode=mode, places=_ent(request.POST.get('places'), 30) or 1,
                places_attente=_ent(request.POST.get('places_attente'), 10) or 0,
                seuil_admission=_dec(request.POST.get('seuil_admission'), 'seuil', vide_ok=False),
                poids_dossier=100 if mode == 'dossier' else (0 if mode == 'concours' else
                                                            max(0, min(100, _ent(request.POST.get('poids_dossier'), 50)))),
                diplome_requis=request.POST.get('diplome_requis') if request.POST.get('diplome_requis') in
                dict(Concours._meta.get_field('diplome_requis').choices) else 'bac',
                date_limite=date.fromisoformat(request.POST['date_limite']) if request.POST.get('date_limite') else None,
                date_epreuves=date.fromisoformat(request.POST['date_epreuves']) if request.POST.get('date_epreuves') else None,
            )
            messages.success(request, f"Campagne « {c.intitule} » créée. Ajoutez les épreuves et partagez le lien de candidature.")
            return redirect('directeur:detail_concours', concours_id=c.id)
        except ValueError as exc:
            messages.error(request, f"Champ invalide : {exc}.")
        return redirect('directeur:liste_concours')
    campagnes = list(Concours.objects.filter(etablissement=etablissement, annee_scolaire=annee)
                     .select_related('classe_cible'))
    for c in campagnes:
        c.stats = svc.statistiques(c)
    return render(request, 'school_admin/directeur/admissions/liste.html', {
        'etablissement': etablissement, 'annee_scolaire_active': annee, 'campagnes': campagnes,
        'classes': Classe.objects.filter(etablissement=etablissement, actif=True, niveau='superieur').order_by('nom'),
        'modes': Concours.MODE_CHOICES, 'diplomes': Concours._meta.get_field('diplome_requis').choices,
        'nb_candidatures': sum(c.stats['total'] for c in campagnes),
        'nb_admis': sum(c.stats['admis'] for c in campagnes),
    })


@login_required
@require_permission('eleves_liste')
def detail_concours(request, concours_id):
    etablissement, annee = _acces(request)
    if etablissement is None:
        return redirect('directeur:dashboard_directeur')
    concours = get_object_or_404(Concours.objects.select_related('classe_cible'), id=concours_id,
                                 etablissement=etablissement)
    onglet = request.GET.get('onglet') or request.POST.get('onglet') or 'candidatures'
    url = f"{reverse('directeur:detail_concours', args=[concours.id])}?onglet={onglet}"

    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'candidature':
                c = Candidature(concours=concours)
                remplir_candidature(c, request.POST)
                c.statut = 'recevable'
                svc.numeroter(c)
                c.save()
                messages.success(request, f"Candidature {c.numero} enregistrée ({c.nom_complet}).")
            elif action == 'statut':
                c = get_object_or_404(Candidature, id=request.POST.get('id'), concours=concours)
                nouveau = request.POST.get('statut')
                if nouveau in ('recevable', 'irrecevable'):
                    c.statut, c.motif = nouveau, (request.POST.get('motif') or '').strip()[:255]
                    c.save()
                    messages.success(request, f"{c.nom_complet} : dossier {c.get_statut_display().lower()}.")
            elif action == 'epreuve_ajouter':
                nom = (request.POST.get('nom') or '').strip()
                if not nom:
                    raise ValueError("nom de l'épreuve")
                EpreuveConcours.objects.create(concours=concours, nom=nom[:120],
                                               coefficient=_dec(request.POST.get('coefficient'), 'coefficient', 0, 20, False),
                                               note_eliminatoire=_dec(request.POST.get('note_eliminatoire'), 'note éliminatoire'),
                                               ordre=concours.epreuves.count())
                messages.success(request, f"Épreuve « {nom} » ajoutée.")
            elif action == 'epreuve_supprimer':
                EpreuveConcours.objects.filter(concours=concours, id=request.POST.get('id')).delete()
                messages.success(request, "Épreuve supprimée.")
            elif action == 'notes':
                saisies = {}
                for k, v in request.POST.items():
                    if k.startswith('n_'):
                        _, cid, eid = k.split('_')
                        saisies[(int(cid), int(eid))] = v
                erreurs = svc.enregistrer_notes(concours, saisies)
                for e in erreurs:
                    messages.error(request, e)
                if not erreurs:
                    messages.success(request, "Notes enregistrées.")
            elif action == 'calculer':
                st = svc.calculer(concours)
                messages.success(request, f"Classement calculé : {st['admis']} admis, {st['attente']} en liste d'attente.")
            elif action == 'publier':
                svc.calculer(concours)
                concours.statut = 'publie'
                concours.save(update_fields=['statut'])
                messages.success(request, "Résultats publiés.")
            elif action == 'cloturer':
                concours.statut = 'clos' if concours.statut == 'ouvert' else 'ouvert'
                concours.save(update_fields=['statut'])
                messages.success(request, "Candidatures " + ("closes." if concours.statut == 'clos' else "rouvertes."))
            elif action == 'desister':
                c = get_object_or_404(Candidature, id=request.POST.get('id'), concours=concours)
                promu = svc.desister(c)
                messages.success(request, f"Désistement de {c.nom_complet} enregistré."
                                          + (f" {promu.nom_complet} est admis depuis la liste d'attente." if promu else ''))
            elif action == 'inscrire':
                c = get_object_or_404(Candidature, id=request.POST.get('id'), concours=concours)
                classe = Classe.objects.filter(id=request.POST.get('classe'), etablissement=etablissement).first()
                eleve = svc.inscrire(c, classe)
                messages.success(request, f"{eleve.nom_complet} est inscrit(e) en {eleve.classe.nom} (matricule {eleve.matricule_eleve or eleve.numero_eleve}).")
        except (ValueError, svc.AdmissionErreur) as exc:
            messages.error(request, f"{exc}".capitalize() + '.')
        return redirect(url)

    cands = list(concours.candidatures.prefetch_related('notes'))
    epreuves = list(concours.epreuves.all())
    notes = {(n.candidature_id, n.epreuve_id): n for c in cands for n in c.notes.all()}
    grille = [{'c': c, 'cellules': [{'epreuve': e, 'note': notes.get((c.id, e.id))} for e in epreuves]}
              for c in cands if c.statut not in ('irrecevable', 'desiste')]
    filtre = request.GET.get('statut', '')
    if filtre:
        cands = [c for c in cands if c.statut == filtre]
    resultats = sorted([c for c in concours.candidatures.all() if c.statut in ('admis', 'attente', 'inscrit', 'refuse', 'desiste')],
                       key=lambda c: (c.rang is None, c.rang or 0, c.nom))
    lien = request.build_absolute_uri(reverse('school_admin:candidature_publique', args=[concours.jeton]))
    return render(request, 'school_admin/directeur/admissions/detail.html', {
        'etablissement': etablissement, 'concours': concours, 'onglet': onglet, 'candidatures': cands,
        'epreuves': epreuves, 'grille': grille, 'resultats': resultats, 'stats': svc.statistiques(concours),
        'filtre': filtre, 'statuts': Candidature.STATUT_CHOICES, 'lien_public': lien,
        'series': Candidature.SERIES_BAC, 'mentions': Candidature.MENTIONS, 'pieces': Candidature.PIECES,
        'liens_contact': Candidature._meta.get_field('contact_lien').choices,
        'classes': Classe.objects.filter(etablissement=etablissement, actif=True, niveau='superieur').order_by('nom'),
    })


def candidature_publique(request, jeton):
    """Formulaire public (sans compte) : un candidat dépose sa candidature en ligne."""
    concours = get_object_or_404(Concours.objects.select_related('etablissement', 'classe_cible'), jeton=jeton)
    from django.utils import timezone

    ferme = concours.statut != 'ouvert' or (concours.date_limite and timezone.localdate() > concours.date_limite)
    contexte = {'concours': concours, 'etablissement': concours.etablissement, 'ferme': ferme,
                'series': Candidature.SERIES_BAC, 'mentions': Candidature.MENTIONS, 'pieces': Candidature.PIECES,
                'liens_contact': Candidature._meta.get_field('contact_lien').choices, 'post': {}}
    if request.method == 'POST' and not ferme:
        c = Candidature(concours=concours, en_ligne=True)
        try:
            remplir_candidature(c, request.POST)
            svc.numeroter(c)
            c.save()
            return render(request, 'school_admin/admissions/candidature_publique.html',
                          dict(contexte, confirmation=c))
        except ValueError as exc:
            contexte.update({'erreur': f"{exc}".capitalize() + '.', 'post': request.POST})
    return render(request, 'school_admin/admissions/candidature_publique.html', contexte)
