"""
Controller pour la gestion des examens selon la logique sénégalaise
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from datetime import datetime, timedelta
import json
import re

from ..model.etablissement_model import Etablissement
from ..model.session_examen_model import SessionExamen
from ..model.creneau_examen_model import CreneauExamen
from ..model.periode_model import PeriodeScolaire
from ..model.classe_model import Classe
from ..model.matiere_model import Matiere
from ..model.professeur_model import Professeur
from ..model.salle_model import Salle


@login_required
def gestion_examens(request):
    """
    Page principale de gestion des examens avec onglets par période et groupes de classes
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Traitement de l'ajout d'une nouvelle session d'examen
    if request.method == 'POST':
        try:
            with transaction.atomic():
                nom_examen = request.POST.get('nom_examen', '').strip()
                periode_id = request.POST.get('periode_id')
                date_debut_str = request.POST.get('date_debut')
                date_fin_str = request.POST.get('date_fin')
                description = request.POST.get('description', '').strip()
                groupes_classes = request.POST.getlist('groupes_classes')  # Liste des niveaux sélectionnés
                matieres_ids = request.POST.getlist('matieres')  # Liste des matières sélectionnées
                
                # Validations
                if not all([nom_examen, periode_id, date_debut_str, date_fin_str]):
                    messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                    return redirect('directeur:gestion_examens')
                
                if not groupes_classes:
                    messages.error(request, "Veuillez sélectionner au moins un groupe de classes.")
                    return redirect('directeur:gestion_examens')
                
                if not matieres_ids:
                    messages.error(request, "Veuillez sélectionner au moins une matière.")
                    return redirect('directeur:gestion_examens')
                
                # Récupération des objets
                periode = get_object_or_404(PeriodeScolaire, id=periode_id, etablissement=etablissement)
                matieres = Matiere.objects.filter(id__in=matieres_ids, etablissement=etablissement)
                
                # Conversion des dates
                date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                
                # Récupération des classes pour les groupes sélectionnés
                classes = []
                for groupe in groupes_classes:
                    # Rechercher les classes qui correspondent au groupe (ex: "6e" pour toutes les classes de 6e)
                    classes_groupe = Classe.objects.filter(
                        etablissement=etablissement,
                        nom__icontains=groupe
                    )
                    classes.extend(classes_groupe)
                
                if not classes:
                    messages.error(request, "Aucune classe trouvée pour les groupes sélectionnés.")
                    return redirect('directeur:gestion_examens')
                
                # Création de la session d'examen
                session = SessionExamen.objects.create(
                    nom_examen=nom_examen,
                    etablissement=etablissement,
                    periode=periode,
                    date_debut=date_debut,
                    date_fin=date_fin,
                    description=description
                )
                
                # Ajout des classes et matières à la session
                session.classes.set(classes)
                session.matieres.set(matieres)
                
                messages.success(request, f"Session d'examen '{nom_examen}' créée avec succès pour {len(classes)} classe(s) et {len(matieres)} matière(s).")
                return redirect('directeur:gestion_examens')
                
        except Exception as e:
            messages.error(request, f"Erreur lors de la création de la session d'examen : {str(e)}")
            return redirect('directeur:gestion_examens')
    
    # Récupérer toutes les périodes scolaires de l'établissement
    periodes = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True
    ).order_by('date_debut')
    
    # Récupérer toutes les classes de l'établissement et les grouper par niveau
    classes = Classe.objects.filter(
        etablissement=etablissement,
        actif=True
    ).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau
    groupes_classes = {}
    for classe in classes:
        # Extraire le niveau de la classe (ex: "6eme" de "6eme A")
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
        if match:
            niveau = match.group(1)
        else:
            niveau = classe.nom
        
        if niveau not in groupes_classes:
            groupes_classes[niveau] = {
                'niveau': niveau,
                'classes': []
            }
        
        groupes_classes[niveau]['classes'].append(classe)
    
    # Récupérer toutes les matières
    matieres = Matiere.objects.filter(
        etablissement=etablissement,
        actif=True
    ).order_by('nom')
    
    # Récupérer les sessions d'examens
    sessions = SessionExamen.objects.filter(
        etablissement=etablissement,
        actif=True
    ).select_related('periode').prefetch_related('classes', 'matieres').order_by('-date_creation')
    
    # Grouper les sessions par période
    sessions_par_periode = {}
    for session in sessions:
        periode_id = session.periode.id
        if periode_id not in sessions_par_periode:
            sessions_par_periode[periode_id] = {
                'periode': session.periode,
                'sessions': []
            }
        sessions_par_periode[periode_id]['sessions'].append(session)
    
    context = {
        'etablissement': etablissement,
        'periodes': periodes,
        'groupes_classes': groupes_classes,
        'matieres': matieres,
        'sessions_par_periode': sessions_par_periode,
    }
    
    return render(request, 'school_admin/directeur/gestion_examens.html', context)


@login_required
def emploi_du_temps_examens(request):
    """
    Page d'emploi du temps des examens avec affichage en grille comme un emploi du temps classique
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Traitement de l'ajout d'un nouveau créneau d'examen
    if request.method == 'POST':
        try:
            with transaction.atomic():
                session_examen_id = request.POST.get('session_examen_id')
                matiere_id = request.POST.get('matiere_id')
                date_examen_str = request.POST.get('date_examen')
                heure_debut_str = request.POST.get('heure_debut')
                heure_fin_str = request.POST.get('heure_fin')
                surveillant_id = request.POST.get('surveillant_id')
                salle_id = request.POST.get('salle_id')
                consignes_specifiques = request.POST.get('consignes_specifiques', '').strip()
                
                # Validations
                if not all([session_examen_id, matiere_id, date_examen_str, heure_debut_str, heure_fin_str]):
                    messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                    return redirect('directeur:emploi_du_temps_examens')
                
                # Récupération des objets
                session_examen = get_object_or_404(SessionExamen, id=session_examen_id, etablissement=etablissement)
                matiere = get_object_or_404(Matiere, id=matiere_id, etablissement=etablissement)
                
                # Conversion des dates et heures
                date_examen = datetime.strptime(date_examen_str, '%Y-%m-%d').date()
                heure_debut = datetime.strptime(heure_debut_str, '%H:%M').time()
                heure_fin = datetime.strptime(heure_fin_str, '%H:%M').time()
                
                # Récupération des surveillants et salles (optionnels)
                surveillant = None
                if surveillant_id:
                    surveillant = get_object_or_404(Professeur, id=surveillant_id, etablissement=etablissement)
                
                salle = None
                if salle_id:
                    salle = get_object_or_404(Salle, id=salle_id, etablissement=etablissement)
                
                # Création du créneau d'examen
                creneau = CreneauExamen.objects.create(
                    session_examen=session_examen,
                    matiere=matiere,
                    date_examen=date_examen,
                    heure_debut=heure_debut,
                    heure_fin=heure_fin,
                    surveillant=surveillant,
                    salle=salle,
                    consignes_specifiques=consignes_specifiques
                )
                
                messages.success(request, f"C Créneau d'examen créé avec succès : {creneau}")
                return redirect('directeur:emploi_du_temps_examens')
                
        except Exception as e:
            messages.error(request, f"Erreur lors de la création du créneau d'examen : {str(e)}")
            return redirect('directeur:emploi_du_temps_examens')
    
    # Récupérer les sessions d'examens
    sessions_examens = SessionExamen.objects.filter(
        etablissement=etablissement,
        actif=True
    ).select_related('periode').prefetch_related('classes', 'matieres').order_by('-date_creation')
    
    # Récupérer les créneaux d'examens
    creneaux = CreneauExamen.objects.filter(
        session_examen__etablissement=etablissement,
        actif=True
    ).select_related('session_examen', 'session_examen__periode', 'matiere', 'surveillant', 'salle').order_by('date_examen', 'heure_debut')
    
    # Organiser les créneaux en grille horaire (comme un emploi du temps classique)
    # Étape 1: Trouver toutes les heures uniques et les dates
    heures_uniques = set()
    dates_uniques = set()
    
    # Ajouter toutes les dates de la période d'examen
    for session in sessions_examens:
        if session.date_debut and session.date_fin:
            from datetime import timedelta
            date_courante = session.date_debut
            while date_courante <= session.date_fin:
                dates_uniques.add(date_courante)
                date_courante += timedelta(days=1)
    
    # Ajouter les heures des créneaux existants
    for creneau in creneaux:
        dates_uniques.add(creneau.date_examen)
        heures_uniques.add((creneau.heure_debut, creneau.heure_fin))
    
    # Convertir en listes triées
    dates_triees = sorted(list(dates_uniques))
    heures_triees = sorted(list(heures_uniques), key=lambda x: x[0])
    
    # Étape 2: Générer les plages horaires (par heure)
    plages_horaires = []
    if heures_triees:
        heure_min = min([h[0] for h in heures_triees])
        heure_max = max([h[1] for h in heures_triees])
        
        # Générer les plages horaires d'une heure
        from datetime import datetime, time
        heure_actuelle = heure_min
        while heure_actuelle < heure_max:
            # Calculer l'heure suivante
            dt = datetime.combine(datetime.today(), heure_actuelle)
            dt_suivant = dt + timedelta(hours=1)
            heure_suivante = dt_suivant.time()
            
            plages_horaires.append({
                'debut': heure_actuelle,
                'fin': heure_suivante,
                'label': f"{heure_actuelle.strftime('%H:%M')} - {heure_suivante.strftime('%H:%M')}"
            })
            heure_actuelle = heure_suivante
    
    # Étape 3: Organiser les créneaux dans la grille
    # Structure: grille[date][jour_semaine][plage_horaire] = liste de créneaux
    grille_emploi = {}
    jours_semaine_fr = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
    
    for date in dates_triees:
        jour_semaine = jours_semaine_fr[date.weekday()]
        grille_emploi[date] = {
            'date_obj': date,
            'jour_semaine': jour_semaine,
            'plages': {}
        }
        
        # Initialiser toutes les plages horaires pour ce jour
        for plage in plages_horaires:
            grille_emploi[date]['plages'][plage['label']] = []
    
    # Placer les créneaux dans la grille et calculer le rowspan
    # Aussi marquer les cellules à masquer à cause du rowspan
    cellules_masquees = {}  # Structure: cellules_masquees[date][plage_label] = True
    
    for creneau in creneaux:
        date = creneau.date_examen
        
        # Calculer le nombre de cellules (heures) que le créneau occupe
        debut_dt = datetime.combine(datetime.today(), creneau.heure_debut)
        fin_dt = datetime.combine(datetime.today(), creneau.heure_fin)
        duree_heures = (fin_dt - debut_dt).total_seconds() / 3600
        rowspan = int(duree_heures)
        
        # Trouver la plage horaire correspondante (première heure du créneau)
        plage_index = -1
        for idx, plage in enumerate(plages_horaires):
            if plage['debut'] == creneau.heure_debut:
                plage_index = idx
                if date in grille_emploi:
                    grille_emploi[date]['plages'][plage['label']].append({
                        'creneau': creneau,
                        'rowspan': rowspan
                    })
                
                # Marquer les cellules suivantes comme masquées
                if date not in cellules_masquees:
                    cellules_masquees[date] = {}
                
                for i in range(1, rowspan):
                    if plage_index + i < len(plages_horaires):
                        plage_suivante = plages_horaires[plage_index + i]
                        cellules_masquees[date][plage_suivante['label']] = True
                break
    
    # Récupérer les matières, professeurs et salles
    matieres = Matiere.objects.filter(etablissement=etablissement, actif=True).order_by('nom')
    professeurs = Professeur.objects.filter(etablissement=etablissement, actif=True).order_by('nom', 'prenom')
    salles = Salle.objects.filter(etablissement=etablissement, actif=True).order_by('nom')
    
    context = {
        'etablissement': etablissement,
        'grille_emploi': grille_emploi,
        'plages_horaires': plages_horaires,
        'dates_triees': dates_triees,
        'cellules_masquees': cellules_masquees,
        'sessions_examens': sessions_examens,
        'matieres': matieres,
        'professeurs': professeurs,
        'salles': salles,
    }
    
    return render(request, 'school_admin/directeur/emploi_du_temps_examens.html', context)


@login_required
def configurer_creneaux_examen(request, session_id):
    """
    Page de configuration des créneaux pour une session d'examen spécifique
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    session = get_object_or_404(SessionExamen, id=session_id, etablissement=etablissement)
    
    # Traitement de l'ajout d'un créneau
    if request.method == 'POST':
        try:
            with transaction.atomic():
                jour_semaine_str = request.POST.get('jour_semaine')
                heure_debut_str = request.POST.get('heure_debut')
                heure_fin_str = request.POST.get('heure_fin')
                matiere_id = request.POST.get('matiere_id')
                surveillant_id = request.POST.get('surveillant_id')
                salle_id = request.POST.get('salle_id')
                consignes_specifiques = request.POST.get('consignes_specifiques', '').strip()
                
                # Validations
                if not all([jour_semaine_str, heure_debut_str, heure_fin_str, matiere_id]):
                    messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                    return redirect('directeur:configurer_creneaux_examen', session_id=session_id)
                
                # Conversion de la date du jour sélectionné et des heures
                date_examen = datetime.strptime(jour_semaine_str, '%Y-%m-%d').date()
                heure_debut = datetime.strptime(heure_debut_str, '%H:%M').time()
                heure_fin = datetime.strptime(heure_fin_str, '%H:%M').time()
                
                # Récupérer la matière
                matiere = get_object_or_404(Matiere, id=matiere_id, etablissement=etablissement)
                
                # Vérifier que la matière fait partie de la session
                if matiere not in session.matieres.all():
                    messages.error(request, "La matière sélectionnée ne fait pas partie de cette session d'examen.")
                    return redirect('directeur:configurer_creneaux_examen', session_id=session_id)
                
                # Vérifier si un créneau existe déjà pour cette matière et cette date
                creneau_existant = CreneauExamen.objects.filter(
                    session_examen=session,
                    matiere=matiere,
                    date_examen=date_examen,
                    actif=True
                ).first()
                
                if creneau_existant:
                    messages.warning(request, f"Un créneau existe déjà pour {matiere.nom} le {date_examen.strftime('%d/%m/%Y')}.")
                    return redirect('directeur:configurer_creneaux_examen', session_id=session_id)
                
                # Récupérer le surveillant et la salle (optionnels)
                surveillant = None
                if surveillant_id:
                    surveillant = get_object_or_404(Professeur, id=surveillant_id, etablissement=etablissement)
                
                salle = None
                if salle_id:
                    salle = get_object_or_404(Salle, id=salle_id, etablissement=etablissement)
                
                # Créer le créneau
                creneau = CreneauExamen.objects.create(
                    session_examen=session,
                    matiere=matiere,
                    date_examen=date_examen,
                    heure_debut=heure_debut,
                    heure_fin=heure_fin,
                    surveillant=surveillant,
                    salle=salle,
                    consignes_specifiques=consignes_specifiques
                )
                
                messages.success(request, f"Créneau créé avec succès : {matiere.nom} le {date_examen.strftime('%d/%m/%Y')} de {heure_debut.strftime('%H:%M')} à {heure_fin.strftime('%H:%M')}.")
                return redirect('directeur:configurer_creneaux_examen', session_id=session_id)
                
        except Exception as e:
            messages.error(request, f"Erreur lors de la création du créneau : {str(e)}")
            return redirect('directeur:configurer_creneaux_examen', session_id=session_id)
    
    # Récupérer les créneaux existants pour cette session
    creneaux = CreneauExamen.objects.filter(
        session_examen=session,
        actif=True
    ).select_related('matiere', 'surveillant', 'salle').order_by('date_examen', 'heure_debut')
    
    # Récupérer les professeurs et salles
    professeurs = Professeur.objects.filter(etablissement=etablissement, actif=True).order_by('nom', 'prenom')
    salles = Salle.objects.filter(etablissement=etablissement, actif=True).order_by('nom')
    
    # Générer la liste des jours de la semaine dans la période de la session
    from datetime import timedelta
    jours_disponibles = []
    date_courante = session.date_debut
    jours_semaine_fr = {
        0: 'Lundi',
        1: 'Mardi',
        2: 'Mercredi',
        3: 'Jeudi',
        4: 'Vendredi',
        5: 'Samedi',
        6: 'Dimanche'
    }
    
    while date_courante <= session.date_fin:
        jour_semaine = date_courante.weekday()
        jours_disponibles.append({
            'date': date_courante,
            'nom_jour': jours_semaine_fr[jour_semaine],
            'date_iso': date_courante.strftime('%Y-%m-%d'),
            'date_affichage': date_courante.strftime('%d/%m/%Y')
        })
        date_courante += timedelta(days=1)
    
    context = {
        'etablissement': etablissement,
        'session': session,
        'creneaux': creneaux,
        'professeurs': professeurs,
        'salles': salles,
        'jours_disponibles': jours_disponibles,
    }
    
    return render(request, 'school_admin/directeur/configurer_creneaux_examen.html', context)


@login_required
def modifier_session_examen(request, session_id):
    """
    Modifier une session d'examen existante
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    session = get_object_or_404(SessionExamen, id=session_id, etablissement=etablissement)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Récupération des données du formulaire
                nom_examen = request.POST.get('nom_examen', '').strip()
                periode_id = request.POST.get('periode_id')
                date_debut_str = request.POST.get('date_debut')
                date_fin_str = request.POST.get('date_fin')
                groupes_classes = request.POST.getlist('groupes_classes')
                matieres_ids = request.POST.getlist('matieres_ids')
                description = request.POST.get('description', '').strip()
                
                # Validations
                if not all([nom_examen, periode_id, date_debut_str, date_fin_str]):
                    messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                    return redirect('directeur:gestion_examens')
                
                if not groupes_classes:
                    messages.error(request, "Veuillez sélectionner au moins un groupe de classes.")
                    return redirect('directeur:gestion_examens')
                
                if not matieres_ids:
                    messages.error(request, "Veuillez sélectionner au moins une matière.")
                    return redirect('directeur:gestion_examens')
                
                # Récupération de la période
                periode = get_object_or_404(PeriodeScolaire, id=periode_id, etablissement=etablissement)
                
                # Conversion des dates
                date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                
                # Mise à jour de la session
                session.nom_examen = nom_examen
                session.periode = periode
                session.date_debut = date_debut
                session.date_fin = date_fin
                session.description = description
                session.save()
                
                # Mise à jour des classes
                classes_a_assigner = []
                for groupe in groupes_classes:
                    classes_du_groupe = Classe.objects.filter(
                        etablissement=etablissement,
                        nom__startswith=groupe,
                        actif=True
                    )
                    classes_a_assigner.extend(list(classes_du_groupe))
                
                session.classes.set(classes_a_assigner)
                
                # Mise à jour des matières
                matieres = Matiere.objects.filter(id__in=matieres_ids, etablissement=etablissement)
                session.matieres.set(matieres)
                
                messages.success(request, f"Session d'examen '{session.nom_examen}' modifiée avec succès.")
                return redirect('directeur:gestion_examens')
                
        except Exception as e:
            messages.error(request, f"Erreur lors de la modification de la session : {str(e)}")
            return redirect('directeur:gestion_examens')
    
    # Si GET, rediriger vers la page de gestion
    return redirect('directeur:gestion_examens')


@login_required
def supprimer_session_examen(request, session_id):
    """
    Supprimer une session d'examen et tous ses créneaux associés (CASCADE)
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    try:
        session = get_object_or_404(SessionExamen, id=session_id, etablissement=etablissement)
        
        # Compter les créneaux avant suppression
        nb_creneaux = session.creneaux.count()
        nom_session = session.nom_examen
        
        # La suppression des créneaux se fait automatiquement grâce au CASCADE
        session.delete()
        
        messages.success(request, f"Session '{nom_session}' et ses {nb_creneaux} créneau(x) supprimé(s) avec succès.")
        
    except Exception as e:
        messages.error(request, f"Erreur lors de la suppression de la session : {str(e)}")
    
    return redirect('directeur:gestion_examens')