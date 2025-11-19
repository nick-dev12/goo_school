# school_admin/controllers/professeur_controller.py

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone
import logging

from ..model.professeur_model import Professeur
from ..model.etablissement_model import Etablissement

logger = logging.getLogger(__name__)


class ProfesseurController:
    """
    Contrôleur pour gérer les professeurs
    """
    
    @staticmethod
    def generate_numero_employe(etablissement):
        """
        Génère un numéro d'employé unique pour un professeur
        """
        code_etab = etablissement.code_etablissement[:3]
        
        # Générer un numéro séquentiel
        count = Professeur.objects.filter(
            etablissement=etablissement
        ).count() + 1
        
        numero = f"PROF-{code_etab}-{count:03d}"
        
        # Vérifier l'unicité
        while Professeur.objects.filter(numero_employe=numero).exists():
            count += 1
            numero = f"PROF-{code_etab}-{count:03d}"
        
        return numero
    
    @staticmethod
    def generate_matricule_professeur(etablissement):
        """
        Génère un matricule unique pour un professeur avec des chiffres aléatoires
        Format : [XX][6 chiffres aléatoires]
        Exemple : BP482937 (Blaise Pascal, professeur avec chiffres aléatoires)
        Le matricule sera enregistré dans numero_employe
        Vérifie l'unicité dans la base de données avant de retourner
        """
        import random
        
        # Extraire les initiales de l'établissement (2 premiers mots)
        mots = etablissement.nom.split()[:2]
        initiales = ''.join([mot[0].upper() for mot in mots if mot])
        
        # Si moins de 2 mots, utiliser les 2 premières lettres du nom
        if len(initiales) < 2:
            initiales = etablissement.nom[:2].upper()
        
        # Générer un matricule avec des chiffres aléatoires
        max_tentatives = 10000  # Augmenter le nombre de tentatives pour plus de robustesse
        tentatives = 0
        
        while tentatives < max_tentatives:
            # Générer 6 chiffres aléatoires
            chiffres_aleatoires = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            matricule = f"{initiales}{chiffres_aleatoires}"
            
            # Vérifier l'unicité dans la base de données
            # Vérifier dans numero_employe (champ principal)
            if not Professeur.objects.filter(numero_employe=matricule).exists():
                # Vérifier aussi dans username pour éviter les conflits
                if not Professeur.objects.filter(username=matricule).exists():
                    return matricule
            
            tentatives += 1
        
        # Fallback avec timestamp si trop de tentatives (très rare)
        import time
        timestamp = int(time.time() * 1000) % 1000000
        matricule_fallback = f"{initiales}{timestamp:06d}"
        
        # Vérifier l'unicité du fallback
        if not Professeur.objects.filter(numero_employe=matricule_fallback).exists() and \
           not Professeur.objects.filter(username=matricule_fallback).exists():
            return matricule_fallback
        
        # Dernier recours : utiliser un UUID tronqué (6 derniers chiffres)
        import uuid
        uuid_int = abs(uuid.uuid4().int) % 1000000  # Prendre les 6 derniers chiffres
        uuid_part = f"{uuid_int:06d}"
        matricule_uuid = f"{initiales}{uuid_part}"
        
        # Vérifier une dernière fois
        if not Professeur.objects.filter(numero_employe=matricule_uuid).exists() and \
           not Professeur.objects.filter(username=matricule_uuid).exists():
            return matricule_uuid
        
        # Si vraiment aucun matricule unique n'a pu être généré (extrêmement rare)
        # Essayer une dernière fois avec un mélange timestamp + random
        import time
        final_random = random.randint(100000, 999999)
        final_timestamp = int(time.time()) % 1000000
        final_matricule = f"{initiales}{(final_random + final_timestamp) % 1000000:06d}"
        
        if not Professeur.objects.filter(numero_employe=final_matricule).exists() and \
           not Professeur.objects.filter(username=final_matricule).exists():
            return final_matricule
        
        raise ValueError(f"Impossible de générer un matricule unique pour l'établissement {etablissement.nom} après {max_tentatives} tentatives")
    
    @staticmethod
    @login_required
    def liste_professeurs(request):
        """
        Affiche la liste des professeurs de l'établissement
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        # Récupérer les professeurs de l'établissement
        professeurs = Professeur.objects.filter(
            etablissement=etablissement
        ).select_related('matiere_principale').order_by('-date_creation')
        
        # Récupérer les matières avec le nombre de professeurs
        from ..model.matiere_model import Matiere
        matieres_avec_compteurs = []
        matieres = Matiere.objects.filter(etablissement=etablissement).order_by('nom')
        
        for matiere in matieres:
            count = professeurs.filter(matiere_principale=matiere).count()
            matieres_avec_compteurs.append({
                'matiere': matiere,
                'count': count,
                'professeurs': professeurs.filter(matiere_principale=matiere)
            })
        
        # Statistiques
        stats = {
            'total': professeurs.count(),
            'actifs': professeurs.filter(actif=True).count(),
            'inactifs': professeurs.filter(actif=False).count(),
            'par_niveau': {}
        }
        
        # Compter par niveau
        for niveau, label in Professeur.NIVEAU_CHOICES:
            count = professeurs.filter(niveau_enseignement=niveau).count()
            if count > 0:
                stats['par_niveau'][label] = count
        
        context = {
            'professeurs': professeurs,
            'matieres_avec_compteurs': matieres_avec_compteurs,
            'etablissement': etablissement,
            'stats': stats,
        }
        
        return render(request, 'school_admin/directeur/personnel/professeurs/liste_professeurs.html', context)
    
    @staticmethod
    @login_required
    def ajouter_professeur(request):
        """
        Affiche le formulaire d'ajout de professeur et traite la soumission
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        form_data = {}
        field_errors = {}
        is_valid = True  # Initialiser is_valid
        
        if request.method == 'POST':
            # Fonction pour déterminer automatiquement le niveau d'enseignement selon le type d'établissement
            def get_niveau_from_etablissement(type_etablissement):
                """Mappe le type d'établissement vers le niveau d'enseignement"""
                mapping = {
                    'primary': 'primaire',
                    'collège': 'college',
                    'lycée': 'lycee',
                }
                return mapping.get(type_etablissement, 'primaire')  # Par défaut 'primaire' si non trouvé
            
            # Récupération des données
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'prenom': request.POST.get('prenom', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'telephone': request.POST.get('telephone', '').strip(),
                'matiere_principale': request.POST.get('matiere_principale', ''),
                'matieres_secondaires': request.POST.getlist('matieres_secondaires', []),
            }
            
            # Déterminer automatiquement le niveau d'enseignement
            niveau_enseignement_auto = get_niveau_from_etablissement(etablissement.type_etablissement)
            form_data['niveau_enseignement'] = niveau_enseignement_auto
            
            # Validation
            is_valid = True
            
            # Pour le primaire, on n'exige pas de matière principale
            # À la place, on exige au moins une matière secondaire
            if etablissement.type_etablissement == 'primary':
                # Champs obligatoires pour le primaire (sans matière principale, email facultatif)
                required_fields = ['nom', 'prenom', 'telephone']
                for field in required_fields:
                    if not form_data[field]:
                        field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                        is_valid = False
                
                # Vérifier qu'au moins une matière est sélectionnée
                if not form_data['matieres_secondaires']:
                    field_errors['matieres_secondaires'] = "Veuillez sélectionner au moins une matière pour le primaire."
                    is_valid = False
                
                # Pour le primaire, la matière principale sera la première matière secondaire
                matiere_principale_obj = None
            else:
                # Champs obligatoires pour collège/lycée (email facultatif)
                required_fields = ['nom', 'prenom', 'telephone', 'matiere_principale']
                for field in required_fields:
                    if not form_data[field]:
                        field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                        is_valid = False
                
                # Validation de la matière
                matiere_principale_obj = None
                if form_data['matiere_principale']:
                    try:
                        from ..model.matiere_model import Matiere
                        matiere_principale_obj = Matiere.objects.get(id=form_data['matiere_principale'], etablissement=etablissement)
                    except Matiere.DoesNotExist:
                        field_errors['matiere_principale'] = "La matière sélectionnée n'existe pas."
                        is_valid = False
            
            # Validation de l'email (seulement si fourni)
            if form_data['email']:
                if '@' not in form_data['email']:
                    field_errors['email'] = "L'adresse email n'est pas valide."
                    is_valid = False
                # Vérification de l'unicité de l'email (seulement si fourni)
                elif Professeur.objects.filter(email=form_data['email']).exists():
                    field_errors['email'] = "Cette adresse email est déjà utilisée."
                    is_valid = False
            
            # Si tout est valide, créer le professeur
            if is_valid:
                try:
                    with transaction.atomic():
                        # Générer le matricule : initiales + 6 chiffres (sera utilisé comme numero_employe)
                        matricule = ProfesseurController.generate_matricule_professeur(etablissement)
                        
                        # Générer un mot de passe provisoire de 4 chiffres
                        import random
                        mot_de_passe_provisoire = ''.join([str(random.randint(0, 9)) for _ in range(4)])
                        
                        # Pour le primaire, si pas de matière principale, prendre la première matière secondaire
                        from ..model.matiere_model import Matiere
                        if etablissement.type_etablissement == 'primary' and not matiere_principale_obj:
                            if form_data['matieres_secondaires']:
                                matiere_principale_obj = Matiere.objects.get(id=form_data['matieres_secondaires'][0])
                        
                        # Créer le professeur
                        # Gérer l'email : utiliser None si vide, sinon utiliser la valeur
                        email_value = form_data['email'] if form_data['email'] else None
                        
                        professeur = Professeur(
                            nom=form_data['nom'],
                            prenom=form_data['prenom'],
                            email=email_value,  # Peut être None si non fourni
                            telephone=form_data['telephone'],
                            matiere_principale=matiere_principale_obj,
                            niveau_enseignement=form_data['niveau_enseignement'],
                            numero_employe=matricule,  # Le matricule est enregistré dans numero_employe
                            etablissement=etablissement,
                            mot_de_passe_provisoire=mot_de_passe_provisoire,
                        )
                        
                        # Définir le username avec le matricule pour compatibilité
                        professeur.username = matricule
                        
                        # Définir le mot de passe provisoire hashé
                        professeur.set_password(mot_de_passe_provisoire)
                        professeur.save()
                        
                        # Ajouter les matières secondaires
                        if form_data['matieres_secondaires']:
                            matieres_secondaires_objs = Matiere.objects.filter(
                                id__in=form_data['matieres_secondaires'],
                                etablissement=etablissement
                            )
                            professeur.matieres_secondaires.set(matieres_secondaires_objs)
                        
                        messages.success(request, f"Le professeur {professeur.nom_complet} a été ajouté avec succès ! Mot de passe provisoire : {mot_de_passe_provisoire}")
                        return redirect('professeur:detail_professeur', professeur_id=professeur.id)
                        
                except Exception as e:
                    logger.error(f"Erreur lors de l'ajout du professeur: {str(e)}")
                    field_errors['__all__'] = "Une erreur est survenue lors de l'ajout du professeur."
                    is_valid = False
        
        # Debug: afficher les erreurs
        print(f"DEBUG - field_errors: {field_errors}")
        print(f"DEBUG - is_valid: {is_valid}")
        
        # Récupérer les matières de l'établissement
        from ..model.matiere_model import Matiere
        matieres = Matiere.objects.filter(etablissement=etablissement).order_by('nom')
        
        context = {
            'form_data': form_data,
            'field_errors': field_errors,
            'is_valid': is_valid,
            'etablissement': etablissement,
            'matieres': matieres,
            'niveau_choices': Professeur.NIVEAU_CHOICES,
            'type_etablissement': etablissement.type_etablissement,
        }
        
        return render(request, 'school_admin/directeur/personnel/professeurs/ajouter_professeur.html', context)
    
    @staticmethod
    @login_required
    def detail_professeur(request, professeur_id):
        """
        Affiche les détails d'un professeur
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        try:
            professeur = Professeur.objects.select_related(
                'matiere_principale',
                'etablissement'
            ).prefetch_related(
                'matieres_secondaires',
                'classes',
                'classes__eleves'
            ).get(
                id=professeur_id,
                etablissement=etablissement
            )
        except Professeur.DoesNotExist:
            messages.error(request, "Professeur non trouvé.")
            return redirect('professeur:liste_professeurs')
        
        # Récupérer les classes affectées avec leurs informations
        classes_affectees = professeur.classes.all().order_by('nom')
        
        # Récupérer l'onglet sélectionné
        onglet_actif = request.GET.get('onglet', 'informations')
        
        # Gérer l'ajout/suppression de matières secondaires (POST)
        if request.method == 'POST':
            action = request.POST.get('action')
            
            if action == 'ajouter_matiere_secondaire':
                matiere_id = request.POST.get('matiere_id')
                if matiere_id:
                    try:
                        from ..model.matiere_model import Matiere
                        matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
                        
                        # Vérifier que ce n'est pas déjà une matière secondaire
                        if matiere not in professeur.matieres_secondaires.all():
                            # Vérifier que ce n'est pas la matière principale
                            if professeur.matiere_principale != matiere:
                                professeur.matieres_secondaires.add(matiere)
                                messages.success(request, f"Matière '{matiere.nom}' ajoutée avec succès.")
                            else:
                                messages.warning(request, "Cette matière est déjà votre matière principale.")
                        else:
                            messages.warning(request, "Cette matière est déjà dans vos matières secondaires.")
                    except Matiere.DoesNotExist:
                        messages.error(request, "Matière non trouvée.")
                
                return redirect('professeur:detail_professeur', professeur_id=professeur.id)
            
            elif action == 'retirer_matiere_secondaire':
                matiere_id = request.POST.get('matiere_id')
                if matiere_id:
                    try:
                        from ..model.matiere_model import Matiere
                        matiere = Matiere.objects.get(id=matiere_id)
                        professeur.matieres_secondaires.remove(matiere)
                        messages.success(request, f"Matière '{matiere.nom}' retirée avec succès.")
                    except Matiere.DoesNotExist:
                        messages.error(request, "Matière non trouvée.")
                
                return redirect('professeur:detail_professeur', professeur_id=professeur.id)
        
        # Pour les enseignants primaires, récupérer les affectations et les données de notes
        affectations_primaire = []
        cahier_notes_data = []
        
        if etablissement.type_etablissement == 'primary':
            from ..model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
            from ..model.periode_model import PeriodeScolaire
            from ..model.note_primaire_model import MoyenneMatierePrimaire
            
            # Récupérer les affectations primaires
            affectations_primaire = AffectationProfesseurPrimaire.objects.filter(
                professeur=professeur,
                actif=True
            ).select_related('classe').prefetch_related('matieres').order_by('classe__nom')
            
            # Récupérer la période active
            periodes = PeriodeScolaire.objects.filter(
                etablissement=etablissement,
                est_active=True
            ).order_by('date_debut')
            
            periode_selectionnee = periodes.filter(est_active=True).first() or periodes.first()
            
            # Pour chaque affectation, récupérer les moyennes par matière
            if onglet_actif == 'cahier_notes' and periode_selectionnee:
                from ..model.evaluation_primaire_model import EvaluationPrimaire
                from ..model.note_primaire_model import NotePrimaire
                
                # Récupérer la matière sélectionnée dans le sous-onglet
                matiere_selectionnee_id = request.GET.get('matiere')
                
                for affectation in affectations_primaire:
                    matieres_info = []
                    
                    for matiere in affectation.matieres.all():
                        # Récupérer les évaluations normales pour cette matière
                        evaluations_list = list(EvaluationPrimaire.objects.filter(
                            classe=affectation.classe,
                            professeur=professeur,
                            matiere=matiere,
                            periode_scolaire=periode_selectionnee,
                            actif=True
                        ).order_by('date_evaluation'))
                        
                        # Récupérer aussi les créneaux d'examens
                        from ..model.creneau_examen_model import CreneauExamen
                        creneaux_examens_list = list(CreneauExamen.objects.filter(
                            session_examen__classes=affectation.classe,
                            session_examen__periode=periode_selectionnee,
                            matiere=matiere,
                            actif=True
                        ).select_related('session_examen').order_by('date_examen'))
                        
                        # Ajouter des numéros pour devoirs, interrogations et examens
                        compteur_devoirs = 0
                        compteur_interrogations = 0
                        compteur_examens = 0
                        evaluations_data = []
                        
                        # Traiter les évaluations normales
                        for eval in evaluations_list:
                            eval_dict = {
                                'obj': eval,
                                'id': eval.id,
                                'titre': eval.titre,
                                'bareme': eval.bareme,
                                'date_evaluation': eval.date_evaluation,
                                'est_examen': False
                            }
                            
                            if eval.bareme == 20:
                                compteur_devoirs += 1
                                eval_dict['type_label'] = f'Devoir {compteur_devoirs}'
                            else:
                                compteur_interrogations += 1
                                eval_dict['type_label'] = f'Interrogation {compteur_interrogations}'
                            
                            evaluations_data.append(eval_dict)
                        
                        # Traiter les examens
                        for creneau in creneaux_examens_list:
                            compteur_examens += 1
                            evaluations_data.append({
                                'obj': creneau,
                                'id': f'examen_{creneau.id}',
                                'creneau_id': creneau.id,
                                'titre': creneau.session_examen.nom_examen,
                                'bareme': 20,
                                'date_evaluation': creneau.date_examen,
                                'est_examen': True,
                                'type_label': f'Examen {compteur_examens}'
                            })
                        
                        # Récupérer les moyennes
                        moyennes_list = MoyenneMatierePrimaire.objects.filter(
                            classe=affectation.classe,
                            matiere=matiere,
                            periode_scolaire=periode_selectionnee
                        ).select_related('eleve').order_by('-moyenne')
                        
                        # Si cette matière est sélectionnée, récupérer aussi les notes détaillées
                        notes_detaillees = []
                        evaluations_utilisees = []  # Liste des évaluations qui ont des notes
                        
                        if str(matiere.id) == matiere_selectionnee_id:
                            from ..model.eleve_model import Eleve
                            eleves = Eleve.objects.filter(
                                classe=affectation.classe,
                                actif=True
                            ).order_by('nom', 'prenom')
                            
                            # Identifier les évaluations qui ont au moins une note saisie
                            evals_avec_notes = set()
                            
                            for eleve in eleves:
                                # Récupérer la moyenne
                                moyenne_obj = moyennes_list.filter(eleve=eleve).first()
                                
                                # Récupérer les notes pour chaque évaluation (normales + examens)
                                from ..model.note_examen_model import NoteExamen
                                
                                notes_evaluations = {}
                                for eval_dict in evaluations_data:
                                    # Si c'est un examen, chercher dans NoteExamen
                                    if eval_dict.get('est_examen'):
                                        note_obj = NoteExamen.objects.filter(
                                            eleve=eleve,
                                            creneau_examen_id=eval_dict['creneau_id'],
                                            matiere=matiere,
                                            retenue=True  # ✅ Ne prendre que les notes retenues
                                        ).first()
                                    else:
                                        # Sinon, chercher dans NotePrimaire
                                        note_obj = NotePrimaire.objects.filter(
                                            eleve=eleve,
                                            evaluation_primaire_id=eval_dict['id'],
                                            retenue=True  # ✅ Ne prendre que les notes retenues
                                        ).first()
                                    
                                    # Si la note retenue existe, inclure cette évaluation
                                    if note_obj:
                                        evals_avec_notes.add(eval_dict['id'])
                                    
                                    # Calculer la couleur
                                    if note_obj and note_obj.note is not None and not note_obj.absent:
                                        note_sur_20 = (float(note_obj.note) / float(eval_dict['bareme'])) * 20
                                        
                                        if note_sur_20 >= 16:
                                            couleur = '#10b981'
                                        elif note_sur_20 >= 14:
                                            couleur = '#3b82f6'
                                        elif note_sur_20 >= 12:
                                            couleur = '#8b5cf6'
                                        elif note_sur_20 >= 10:
                                            couleur = '#f59e0b'
                                        elif note_sur_20 >= 8:
                                            couleur = '#f97316'
                                        else:
                                            couleur = '#ef4444'
                                        
                                        notes_evaluations[eval_dict['id']] = {
                                            'note_obj': note_obj,
                                            'couleur': couleur
                                        }
                                    else:
                                        notes_evaluations[eval_dict['id']] = {
                                            'note_obj': note_obj,
                                            'couleur': None
                                        }
                                
                                notes_detaillees.append({
                                    'eleve': eleve,
                                    'moyenne': moyenne_obj.moyenne if moyenne_obj else None,
                                    'appreciation': moyenne_obj.appreciation if moyenne_obj else None,
                                    'notes_evaluations': notes_evaluations
                                })
                            
                            # Filtrer evaluations_data pour ne garder que celles avec des notes
                            evaluations_utilisees = [e for e in evaluations_data if e['id'] in evals_avec_notes]
                        
                        matieres_info.append({
                            'matiere': matiere,
                            'moyennes': moyennes_list,
                            'nombre_moyennes': moyennes_list.count(),
                            'evaluations': evaluations_utilisees if evaluations_utilisees else evaluations_data,
                            'notes_detaillees': notes_detaillees,
                            'est_selectionnee': str(matiere.id) == matiere_selectionnee_id
                        })
                    
                    cahier_notes_data.append({
                        'classe': affectation.classe,
                        'matieres_info': matieres_info
                    })
        
        # Récupérer les matières disponibles (pour le modal d'ajout)
        from ..model.matiere_model import Matiere
        matieres_disponibles = Matiere.objects.filter(
            etablissement=etablissement
        ).exclude(
            id__in=professeur.matieres_secondaires.values_list('id', flat=True)
        ).exclude(
            id=professeur.matiere_principale.id if professeur.matiere_principale else None
        ).order_by('nom')
        
        context = {
            'professeur': professeur,
            'etablissement': etablissement,
            'classes_affectees': classes_affectees,
            'affectations_primaire': affectations_primaire,
            'onglet_actif': onglet_actif,
            'cahier_notes_data': cahier_notes_data,
            'matieres_disponibles': matieres_disponibles,
        }
        
        return render(request, 'school_admin/directeur/personnel/professeurs/detail_professeur.html', context)
    
    @staticmethod
    @login_required
    def toggle_actif(request, professeur_id):
        """
        Active/désactive un professeur
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        try:
            professeur = Professeur.objects.get(
                id=professeur_id,
                etablissement=etablissement
            )
            
            professeur.actif = not professeur.actif
            professeur.save()
            
            status = "activé" if professeur.actif else "désactivé"
            messages.success(request, f"{professeur.nom_complet} a été {status}.")
            
        except Professeur.DoesNotExist:
            messages.error(request, "Professeur non trouvé.")
        
        return redirect('professeur:detail_professeur', professeur_id=professeur_id)
    
    @staticmethod
    @login_required
    def modifier_professeur(request, professeur_id):
        """
        Modifie les informations d'un professeur
        """
        # Vérifier que l'utilisateur est soit du personnel administratif soit un directeur
        if isinstance(request.user, Etablissement):
            etablissement = request.user
        else:
            # Si c'est du personnel administratif, récupérer son établissement
            from ..model.personnel_administratif_model import PersonnelAdministratif
            if isinstance(request.user, PersonnelAdministratif):
                etablissement = request.user.etablissement
            else:
                messages.error(request, "Accès non autorisé.")
                return redirect('school_admin:connexion_compte_user')
        
        try:
            professeur = Professeur.objects.select_related(
                'matiere_principale',
                'etablissement'
            ).prefetch_related(
                'matieres_secondaires',
                'classes'
            ).get(
                id=professeur_id,
                etablissement=etablissement
            )
        except Professeur.DoesNotExist:
            messages.error(request, "Professeur non trouvé.")
            return redirect('professeur:liste_professeurs')
        
        form_data = {}
        field_errors = {}
        is_valid = True
        
        if request.method == 'POST':
            # Récupération des données
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'prenom': request.POST.get('prenom', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'telephone': request.POST.get('telephone', '').strip(),
                'matiere_principale': request.POST.get('matiere_principale', ''),
                'niveau_enseignement': request.POST.get('niveau_enseignement', ''),
                'matieres_secondaires': request.POST.getlist('matieres_secondaires', []),
            }
            
            # Validation
            is_valid = True
            
            # Champs obligatoires
            required_fields = ['nom', 'prenom', 'email', 'telephone', 'matiere_principale', 'niveau_enseignement']
            for field in required_fields:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                    is_valid = False
            
            # Validation de la matière principale
            matiere_principale_obj = None
            if form_data['matiere_principale']:
                try:
                    from ..model.matiere_model import Matiere
                    matiere_principale_obj = Matiere.objects.get(id=form_data['matiere_principale'], etablissement=etablissement)
                except Matiere.DoesNotExist:
                    field_errors['matiere_principale'] = "La matière sélectionnée n'existe pas."
                    is_valid = False
            
            # Validation de l'email
            if form_data['email'] and '@' not in form_data['email']:
                field_errors['email'] = "L'adresse email n'est pas valide."
                is_valid = False
            
            # Vérification de l'unicité de l'email (sauf si c'est le même)
            if form_data['email'] and form_data['email'] != professeur.email:
                if Professeur.objects.filter(email=form_data['email']).exists():
                    field_errors['email'] = "Cette adresse email est déjà utilisée."
                    is_valid = False
            
            # Si tout est valide, mettre à jour le professeur
            if is_valid:
                try:
                    with transaction.atomic():
                        professeur.nom = form_data['nom']
                        professeur.prenom = form_data['prenom']
                        professeur.email = form_data['email']
                        professeur.telephone = form_data['telephone']
                        professeur.matiere_principale = matiere_principale_obj
                        professeur.niveau_enseignement = form_data['niveau_enseignement']
                        
                        # Mettre à jour le username si l'email a changé
                        if professeur.email != professeur.username:
                            professeur.username = professeur.email
                        
                        professeur.save()
                        
                        # Gérer les matières secondaires
                        if form_data['matieres_secondaires']:
                            from ..model.matiere_model import Matiere
                            matieres_sec = Matiere.objects.filter(
                                id__in=form_data['matieres_secondaires'],
                                etablissement=etablissement
                            )
                            professeur.matieres_secondaires.set(matieres_sec)
                        else:
                            professeur.matieres_secondaires.clear()
                        
                        messages.success(request, f"Les informations de {professeur.nom_complet} ont été mises à jour avec succès !")
                        return redirect('professeur:detail_professeur', professeur_id=professeur.id)
                        
                except Exception as e:
                    logger.error(f"Erreur lors de la modification du professeur: {str(e)}")
                    field_errors['__all__'] = "Une erreur est survenue lors de la modification du professeur."
                    is_valid = False
        else:
            # Préremplir le formulaire avec les données actuelles
            form_data = {
                'nom': professeur.nom,
                'prenom': professeur.prenom,
                'email': professeur.email,
                'telephone': professeur.telephone,
                'matiere_principale': professeur.matiere_principale.id if professeur.matiere_principale else '',
                'niveau_enseignement': professeur.niveau_enseignement,
                'matieres_secondaires': [m.id for m in professeur.matieres_secondaires.all()],
            }
        
        # Récupérer les matières de l'établissement
        from ..model.matiere_model import Matiere
        matieres = Matiere.objects.filter(etablissement=etablissement).order_by('nom')
        
        context = {
            'professeur': professeur,
            'form_data': form_data,
            'field_errors': field_errors,
            'is_valid': is_valid,
            'etablissement': etablissement,
            'matieres': matieres,
            'niveau_choices': Professeur.NIVEAU_CHOICES,
        }
        
        return render(request, 'school_admin/directeur/personnel/professeurs/modifier_professeur.html', context)
