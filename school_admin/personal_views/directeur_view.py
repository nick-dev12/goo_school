from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.core.exceptions import ValidationError
from django.contrib import messages
from ..model.etablissement_model import Etablissement
from ..model.facturation_model import Facturation
from ..model.eleve_model import Eleve


@login_required
def dashboard_directeur(request):
    """
    Vue du tableau de bord pour les directeurs d'établissement
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer les informations de l'établissement
    etablissement = request.user
    
    # Statistiques des élèves
    nombre_eleves_total = Eleve.objects.filter(etablissement=etablissement).count()
    nombre_eleves_actifs = Eleve.objects.filter(etablissement=etablissement, actif=True).count()
    
    # Statistiques du personnel
    from ..model.personnel_administratif_model import PersonnelAdministratif
    nombre_personnel_admin = PersonnelAdministratif.objects.filter(etablissement=etablissement).count()
    nombre_enseignants = 0  # À implémenter quand le modèle enseignant sera créé
    nombre_classes = 0  # À implémenter quand le modèle classe sera créé
    
    # Statistiques de facturation
    facturations = Facturation.objects.filter(etablissement=etablissement)
    montant_total_facture = facturations.aggregate(total=Sum('montant_total'))['total'] or 0
    nombre_factures = facturations.count()
    factures_en_attente = facturations.filter(statut='en_attente').count()
    factures_payees = facturations.filter(statut='paye').count()
    factures_en_retard = facturations.filter(statut='en_retard').count()
    
    # Dernières factures
    dernieres_factures = facturations.order_by('-date_creation')[:5]
    
    # Modules activés et inactifs
    modules_info = {
        'gestion_eleves': {'nom': 'Gestion des élèves', 'actif': etablissement.module_gestion_eleves},
        'notes_evaluations': {'nom': 'Notes et évaluations', 'actif': etablissement.module_notes_evaluations},
        'emploi_temps': {'nom': 'Emploi du temps', 'actif': etablissement.module_emploi_temps},
        'gestion_personnel': {'nom': 'Gestion du personnel', 'actif': etablissement.module_gestion_personnel},
        'surveillance': {'nom': 'Surveillance et sécurité', 'actif': etablissement.module_surveillance},
        'communication': {'nom': 'Communication parents', 'actif': etablissement.module_communication},
        'orientation': {'nom': 'Orientation scolaire', 'actif': etablissement.module_orientation},
        'formation': {'nom': 'Formation continue', 'actif': etablissement.module_formation},
        'transport_scolaire': {'nom': 'Transport scolaire', 'actif': etablissement.module_transport_scolaire},
        'cantine': {'nom': 'Gestion de la cantine', 'actif': etablissement.module_cantine},
        'bibliotheque': {'nom': 'Gestion de la bibliothèque', 'actif': etablissement.module_bibliotheque},
        'sante': {'nom': 'Suivi médical', 'actif': etablissement.module_sante},
        'activites': {'nom': 'Activités extra-scolaires', 'actif': etablissement.module_activites},
        'comptabilite': {'nom': 'Comptabilité', 'actif': etablissement.module_comptabilite},
        'censeurs': {'nom': 'Censeurs', 'actif': etablissement.module_censeurs},
    }
    
    # Préparer le contexte avec les données de l'établissement
    context = {
        'etablissement': etablissement,
        'nom_etablissement': etablissement.nom,
        'type_etablissement': etablissement.get_type_etablissement_display(),
        'code_etablissement': etablissement.code_etablissement,
        'directeur_nom_complet': f"{etablissement.directeur_prenom} {etablissement.directeur_nom}",
        'adresse_complete': f"{etablissement.adresse}, {etablissement.ville}, {etablissement.pays}",
        
        # Modules
        'modules_info': modules_info,
        'modules_actifs': {k: v['actif'] for k, v in modules_info.items()},
        
        # Statistiques élèves
        'nombre_eleves_total': nombre_eleves_total,
        'nombre_eleves_actifs': nombre_eleves_actifs,
        'nombre_personnel_admin': nombre_personnel_admin,
        'nombre_enseignants': nombre_enseignants,
        'nombre_classes': nombre_classes,
        
        # Statistiques facturation
        'montant_total_facture': montant_total_facture,
        'nombre_factures': nombre_factures,
        'factures_en_attente': factures_en_attente,
        'factures_payees': factures_payees,
        'factures_en_retard': factures_en_retard,
        'dernieres_factures': dernieres_factures,
        'statut_paiement': etablissement.get_statut_paiement_display(),
        'montant_total_facturation': etablissement.montant_total_facturation,
        'nombre_eleves_factures': etablissement.nombre_eleves_factures,
        
        # Dates
        'date_creation': etablissement.date_creation,
        'derniere_modification': etablissement.date_modification,
        'date_derniere_facturation': etablissement.date_derniere_facturation,
    }
    
    return render(request, 'school_admin/directeur/dashboard_directeur.html', context)


@login_required
def facturation_directeur(request):
    """
    Vue de la page de facturation pour les directeurs d'établissement
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Récupérer toutes les factures de l'établissement
    facturations = Facturation.objects.filter(etablissement=etablissement).order_by('-date_creation')
    
    # Filtres
    statut_filter = request.GET.get('statut', '')
    type_filter = request.GET.get('type', '')
    
    if statut_filter:
        facturations = facturations.filter(statut=statut_filter)
    if type_filter:
        facturations = facturations.filter(type_facture=type_filter)
    
    # Statistiques détaillées
    stats = {
        'total_factures': facturations.count(),
        'montant_total': facturations.aggregate(total=Sum('montant_total'))['total'] or 0,
        'en_attente': facturations.filter(statut='en_attente').count(),
        'payees': facturations.filter(statut='paye').count(),
        'en_retard': facturations.filter(statut='en_retard').count(),
        'annulees': facturations.filter(statut='annule').count(),
    }
    
    # Montants par statut
    montants_par_statut = {}
    for statut, _ in Facturation.STATUT_CHOICES:
        montant = facturations.filter(statut=statut).aggregate(total=Sum('montant_total'))['total'] or 0
        montants_par_statut[statut] = montant
    
    # Factures urgentes (en retard ou échéance proche)
    factures_urgentes = []
    for facture in facturations.filter(statut__in=['en_attente', 'en_retard']):
        if facture.est_urgente or facture.est_en_retard():
            factures_urgentes.append(facture)
    
    # Modules activés et inactifs
    modules_info = {
        'gestion_eleves': {'nom': 'Gestion des élèves', 'actif': etablissement.module_gestion_eleves, 'prix': 0},
        'notes_evaluations': {'nom': 'Notes et évaluations', 'actif': etablissement.module_notes_evaluations, 'prix': 0},
        'emploi_temps': {'nom': 'Emploi du temps', 'actif': etablissement.module_emploi_temps, 'prix': 0},
        'gestion_personnel': {'nom': 'Gestion du personnel', 'actif': etablissement.module_gestion_personnel, 'prix': 0},
        'surveillance': {'nom': 'Surveillance et sécurité', 'actif': etablissement.module_surveillance, 'prix': 0},
        'communication': {'nom': 'Communication parents', 'actif': etablissement.module_communication, 'prix': 0},
        'orientation': {'nom': 'Orientation scolaire', 'actif': etablissement.module_orientation, 'prix': 0},
        'formation': {'nom': 'Formation continue', 'actif': etablissement.module_formation, 'prix': 0},
        'transport_scolaire': {'nom': 'Transport scolaire', 'actif': etablissement.module_transport_scolaire, 'prix': 0},
        'cantine': {'nom': 'Gestion de la cantine', 'actif': etablissement.module_cantine, 'prix': 0},
        'bibliotheque': {'nom': 'Gestion de la bibliothèque', 'actif': etablissement.module_bibliotheque, 'prix': 0},
        'sante': {'nom': 'Suivi médical', 'actif': etablissement.module_sante, 'prix': 0},
        'activites': {'nom': 'Activités extra-scolaires', 'actif': etablissement.module_activites, 'prix': 0},
        'comptabilite': {'nom': 'Comptabilité', 'actif': etablissement.module_comptabilite, 'prix': 0},
        'censeurs': {'nom': 'Censeurs', 'actif': etablissement.module_censeurs, 'prix': 0},
    }
    
    # Calculer le montant total théorique
    nombre_eleves_total = Eleve.objects.filter(etablissement=etablissement).count()
    montant_par_eleve = etablissement.montant_par_eleve
    montant_total_theorique = nombre_eleves_total * montant_par_eleve
    
    # Statistiques du personnel
    from ..model.personnel_administratif_model import PersonnelAdministratif
    nombre_personnel_admin = PersonnelAdministratif.objects.filter(etablissement=etablissement).count()
    nombre_enseignants = 0  # À implémenter quand le modèle enseignant sera créé
    nombre_classes = 0  # À implémenter quand le modèle classe sera créé
    
    context = {
        'etablissement': etablissement,
        'facturations': facturations,
        'stats': stats,
        'montants_par_statut': montants_par_statut,
        'factures_urgentes': factures_urgentes,
        'modules_info': modules_info,
        'statut_choices': Facturation.STATUT_CHOICES,
        'type_choices': Facturation.TYPE_FACTURE_CHOICES,
        'statut_filter': statut_filter,
        'type_filter': type_filter,
        'montant_par_eleve': montant_par_eleve,
        'nombre_eleves_total': nombre_eleves_total,
        'montant_total_theorique': montant_total_theorique,
        'nombre_personnel_admin': nombre_personnel_admin,
        'nombre_enseignants': nombre_enseignants,
        'nombre_classes': nombre_classes,
    }
    
    return render(request, 'school_admin/directeur/facturation_directeur.html', context)


@login_required
def gestion_pedagogique(request):
    """
    Vue de la page de gestion pédagogique pour les directeurs d'établissement
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
    
   
    return render(request, 'school_admin/directeur/gestion_pedagogique.html')


@login_required
def gestion_eleves(request):
    """
    Vue de la page de gestion des élèves pour les directeurs d'établissement
    """
      # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
  
    return render(request, 'school_admin/directeur/gestion_eleves.html')


@login_required
def notes_et_resultats(request):
    """
    Page de visualisation des notes et résultats par classe et par matière
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.evaluation_model import Note, Evaluation
    from ..model.releve_notes_model import ReleveNotes
    from ..model.affectation_model import AffectationProfesseur
    import re
    from collections import defaultdict
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau numérique
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "6eme", "5eme", etc.
        else:
            categorie = nom
        
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'niveau': classe.niveau,
                'classes': [],
                'total_eleves': 0,
                'nombre_classes': 0,
            }
        
        # Récupérer les affectations de professeurs pour cette classe
        affectations = AffectationProfesseur.objects.filter(
            classe=classe,
            actif=True
        ).select_related('professeur').distinct()
        
        # Grouper par matière (matière principale du professeur)
        matieres_data = {}
        
        for affectation in affectations:
            professeur = affectation.professeur
            matiere = professeur.matiere_principale
            
            if matiere not in matieres_data:
                # Récupérer tous les élèves de la classe
                eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
                
                eleves_notes = []
                for eleve in eleves:
                    # Récupérer les notes de l'élève pour cette matière
                    notes = Note.objects.filter(
                        eleve=eleve,
                        evaluation__classe=classe,
                        evaluation__professeur=professeur
                    ).select_related('evaluation')
                    
                    # Calculer la moyenne si des notes existent
                    notes_valeurs = [note.note_sur_20 for note in notes if not note.absent]
                    moyenne = round(sum(notes_valeurs) / len(notes_valeurs), 2) if notes_valeurs else None
                    
                    # Vérifier si le relevé de note a été soumis
                    releve_soumis = ReleveNotes.objects.filter(
                        classe=classe,
                        professeur=professeur,
                        soumis=True
                    ).exists()
                    
                    eleves_notes.append({
                        'eleve': eleve,
                        'moyenne': moyenne if releve_soumis else None,
                        'nombre_notes': len(notes_valeurs),
                        'releve_soumis': releve_soumis,
                    })
                
                # Trier par moyenne décroissante (None en dernier)
                eleves_notes.sort(key=lambda x: (x['moyenne'] is None, -x['moyenne'] if x['moyenne'] is not None else 0))
                
                matieres_data[matiere] = {
                    'professeur': professeur,
                    'eleves_notes': eleves_notes,
                }
        
        classe_info = {
            'classe': classe,
            'matieres': matieres_data,
            'nombre_eleves': eleves.count() if 'eleves' in locals() else 0,
        }
        
        classes_grouped[categorie]['classes'].append(classe_info)
        classes_grouped[categorie]['total_eleves'] += classe_info['nombre_eleves']
        classes_grouped[categorie]['nombre_classes'] += 1
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': classes_grouped,
    }
    
    return render(request, 'school_admin/directeur/notes_et_resultats.html', context)


@login_required
def suivi_presence(request):
    """
    Page de suivi des présences par classe et par mois
    """
    # Vérifier que l'utilisateur est un directeur
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    from ..model.classe_model import Classe
    from ..model.eleve_model import Eleve
    from ..model.presence_model import Presence
    import re
    from collections import defaultdict
    from datetime import datetime, timedelta
    
    # Récupérer toutes les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Grouper les classes par niveau numérique
    classes_grouped = {}
    
    for classe in classes:
        nom = classe.nom
        
        # Pattern pour extraire le niveau
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
        
        if match:
            categorie = match.group(1)  # "6eme", "5eme", etc.
        else:
            categorie = nom
        
        if categorie not in classes_grouped:
            classes_grouped[categorie] = {
                'niveau': classe.niveau,
                'classes': [],
                'total_eleves': 0,
                'nombre_classes': 0,
            }
        
        # Récupérer tous les élèves de la classe
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('nom', 'prenom')
        
        # Récupérer les mois distincts où il y a des données de présence pour cette classe
        presences_classe = Presence.objects.filter(classe=classe).values('date__month', 'date__year').distinct().order_by('date__year', 'date__month')
        
        # Créer une liste des mois disponibles
        mois_disponibles = []
        for p in presences_classe:
            date_mois = datetime(p['date__year'], p['date__month'], 1)
            mois_disponibles.append({
                'numero': p['date__month'],
                'annee': p['date__year'],
                'nom': date_mois.strftime('%B'),
                'nom_court': date_mois.strftime('%b'),
            })
        
        # Pour chaque mois, calculer les statistiques de présence pour chaque élève
        mois_presences = {}
        
        for mois in mois_disponibles:
            eleves_presences = []
            
            for eleve in eleves:
                # Récupérer les présences de l'élève pour ce mois
                presences = Presence.objects.filter(
                    eleve=eleve,
                    classe=classe,
                    date__month=mois['numero'],
                    date__year=mois['annee']
                )
                
                total_jours = presences.count()
                presents = presences.filter(statut='present').count()
                absents = presences.filter(statut='absent').count()
                absents_justifies = presences.filter(statut='absent_justifie').count()
                retards = presences.filter(statut='retard').count()
                
                # Calculer le taux de présence
                if total_jours > 0:
                    taux_presence = round((presents / total_jours) * 100, 2)
                else:
                    taux_presence = None
                
                eleves_presences.append({
                    'eleve': eleve,
                    'total_jours': total_jours,
                    'presents': presents,
                    'absents': absents,
                    'absents_justifies': absents_justifies,
                    'retards': retards,
                    'taux_presence': taux_presence,
                })
            
            # Trier par taux de présence décroissant (None en dernier)
            eleves_presences.sort(key=lambda x: (x['taux_presence'] is None, -x['taux_presence'] if x['taux_presence'] is not None else 0))
            
            mois_presences[f"{mois['numero']}_{mois['annee']}"] = {
                'mois': mois,
                'eleves_presences': eleves_presences,
            }
        
        classe_info = {
            'classe': classe,
            'mois_presences': mois_presences,
            'mois_disponibles': mois_disponibles,
            'nombre_eleves': eleves.count(),
        }
        
        classes_grouped[categorie]['classes'].append(classe_info)
        classes_grouped[categorie]['total_eleves'] += classe_info['nombre_eleves']
        classes_grouped[categorie]['nombre_classes'] += 1
    
    context = {
        'etablissement': etablissement,
        'classes_grouped': classes_grouped,
    }
    
    return render(request, 'school_admin/directeur/suivi_presence.html', context)


@login_required
def gestion_etablissement(request):
    """
    Vue de la page de gestion de l'établissement pour les directeurs d'établissement
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        return redirect('school_admin:connexion_compte_user')
   
    return render(request, 'school_admin/directeur/gestion_etablissement.html')


@login_required
def gestion_periodes_scolaires(request):
    """
    Vue pour la gestion des périodes scolaires (trimestres, semestres)
    """
    # Vérifier que l'utilisateur connecté est bien un établissement
    if not isinstance(request.user, Etablissement):
        messages.error(request, "Accès non autorisé.")
        return redirect('school_admin:connexion_compte_user')
    
    etablissement = request.user
    
    # Récupérer l'année scolaire en cours (septembre N à août N+1)
    from datetime import date
    aujourdhui = date.today()
    if aujourdhui.month >= 9:
        annee_debut = aujourdhui.year
    else:
        annee_debut = aujourdhui.year - 1
    annee_scolaire_actuelle = f"{annee_debut}-{annee_debut + 1}"
    
    # Gestion de l'ajout d'une nouvelle période
    if request.method == 'POST':
        from ..model.periode_model import PeriodeScolaire
        from django.db import transaction
        from datetime import datetime
        
        try:
            with transaction.atomic():
                nom_periode = request.POST.get('nom_periode', '').strip()
                type_periode = request.POST.get('type_periode', 'trimestre')
                date_debut_str = request.POST.get('date_debut', '')
                date_fin_str = request.POST.get('date_fin', '')
                annee_scolaire = request.POST.get('annee_scolaire', annee_scolaire_actuelle)
                est_active = request.POST.get('est_active') == 'on'
                
                # Validations
                if not all([nom_periode, date_debut_str, date_fin_str, annee_scolaire]):
                    messages.error(request, "Tous les champs obligatoires doivent être remplis.")
                    return redirect('directeur:gestion_periodes_scolaires')
                
                # Convertir les dates string en objets date
                date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                
                # Créer la période
                periode = PeriodeScolaire.objects.create(
                    etablissement=etablissement,
                    nom_periode=nom_periode,
                    type_periode=type_periode,
                    date_debut=date_debut,
                    date_fin=date_fin,
                    annee_scolaire=annee_scolaire,
                    est_active=est_active
                )
                
                messages.success(request, f"La période '{periode.nom_periode}' a été créée avec succès.")
                return redirect('directeur:gestion_periodes_scolaires')
                
        except ValidationError as e:
            messages.error(request, f"Erreur de validation : {e}")
            return redirect('directeur:gestion_periodes_scolaires')
        except Exception as e:
            messages.error(request, f"Erreur lors de la création de la période : {str(e)}")
            return redirect('directeur:gestion_periodes_scolaires')
    
    # Récupérer toutes les périodes de l'établissement
    from ..model.periode_model import PeriodeScolaire
    periodes = PeriodeScolaire.objects.filter(
        etablissement=etablissement
    ).order_by('-annee_scolaire', 'date_debut')
    
    # Grouper les périodes par année scolaire
    periodes_par_annee = {}
    for periode in periodes:
        if periode.annee_scolaire not in periodes_par_annee:
            periodes_par_annee[periode.annee_scolaire] = []
        periodes_par_annee[periode.annee_scolaire].append(periode)
    
    context = {
        'user': etablissement,
        'etablissement': etablissement,
        'periodes': periodes,
        'periodes_par_annee': periodes_par_annee,
        'annee_scolaire_actuelle': annee_scolaire_actuelle,
    }
    
    return render(request, 'school_admin/directeur/gestion_periodes_scolaires.html', context)