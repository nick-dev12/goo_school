from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Count, Q
import logging
import random
import string

from ..model.matiere_model import Matiere
from ..model.etablissement_model import Etablissement
from ..model.classe_model import Classe
from ..model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe

logger = logging.getLogger(__name__)


class MatiereController:
    """
    Contrôleur pour la gestion des matières
    """
    
    @staticmethod
    def get_niveau_from_type_etablissement(type_etablissement):
        """
        Détermine le niveau de matière à partir du type d'établissement
        
        Args:
            type_etablissement: Le type d'établissement (primary, collège, lycée, collège_lycée, mixte)
            
        Returns:
            str: Le niveau correspondant (primaire, college, lycee, tous)
        """
        mapping = {
            'primary': 'primaire',
            'collège': 'college',
            'lycée': 'lycee',
            'collège_lycée': 'college',  # Par défaut pour collège+lycée
            'mixte': 'tous',  # Pour mixte, on peut utiliser "tous" pour permettre tous les niveaux
        }
        return mapping.get(type_etablissement, 'tous')
    
    @staticmethod
    @login_required
    def liste_matieres(request):
        """
        Affiche la liste des matières avec possibilité d'ajout
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
        
        # Récupérer les matières
        matieres = Matiere.objects.filter(etablissement=etablissement).order_by('nom')
        
        # Récupérer les classes et créer les groupes
        import re
        classes = Classe.objects.filter(etablissement=etablissement).order_by('niveau', 'nom')
        
        # Créer les groupes de classes
        groupes_classes = {}
        for classe in classes:
            # Extraire le niveau de base (ex: "6eme" de "6eme A", "Premiere L" de "Premiere L1", etc.)
            match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
            if match:
                groupe_nom = match.group(1)  # "6eme", "Premiere L", "Terminale S", etc.
            else:
                groupe_nom = classe.nom
            
            if groupe_nom not in groupes_classes:
                groupes_classes[groupe_nom] = {
                    'nom': groupe_nom,
                    'niveau': classe.niveau,
                    'classes': [],
                    'count': 0
                }
            
            groupes_classes[groupe_nom]['classes'].append(classe)
            groupes_classes[groupe_nom]['count'] += 1
        
        # Convertir en liste triée
        groupes_liste = sorted(groupes_classes.values(), key=lambda x: (x['niveau'], x['nom']))
        
        # Statistiques
        stats = {
            'total': matieres.count(),
            'actives': matieres.filter(actif=True).count(),
            'inactives': matieres.filter(actif=False).count(),
            'par_type': {},
            'par_niveau': {},
        }
        
        # Compter par type
        for type_matiere, label in Matiere.TYPE_MATIERE_CHOICES:
            count = matieres.filter(type_matiere=type_matiere).count()
            if count > 0:
                stats['par_type'][label] = count
        
        # Compter par niveau
        for niveau, label in Matiere.NIVEAU_CHOICES:
            count = matieres.filter(niveau=niveau).count()
            if count > 0:
                stats['par_niveau'][label] = count
        
        # Vérifier si c'est un établissement de type lycée
        est_lycee = etablissement.type_etablissement in ['lycée', 'collège_lycée', 'lycee_college', 'mixte', 'lycee', 'college']
        
        # Pour chaque matière, récupérer les coefficients par groupe (si établissement lycée)
        matieres_avec_coefficients = []
        for matiere in matieres:
            matiere_data = {
                'matiere': matiere,
                'coefficients_par_groupe': {}
            }
            
            if est_lycee:
                # Récupérer les coefficients par groupe pour cette matière
                coeffs = CoefficientMatiereGroupe.objects.filter(
                    matiere=matiere,
                    etablissement=etablissement
                )
                for coeff in coeffs:
                    matiere_data['coefficients_par_groupe'][coeff.nom_groupe] = coeff.coefficient
            
            matieres_avec_coefficients.append(matiere_data)
        
        context = {
            'matieres': matieres,
            'matieres_avec_coefficients': matieres_avec_coefficients,
            'classes': classes,
            'groupes_classes': groupes_liste,
            'etablissement': etablissement,
            'stats': stats,
            'type_choices': Matiere.TYPE_MATIERE_CHOICES,
            'est_lycee': est_lycee,
        }
        
        return render(request, 'school_admin/directeur/pedagogique/matieres/liste_matieres.html', context)
    
    @staticmethod
    @login_required
    def ajouter_matiere(request):
        """
        Affiche le formulaire d'ajout de matière et traite la soumission
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
        is_valid = True
        
        if request.method == 'POST':
            # Récupération automatique du niveau depuis le type_etablissement
            niveau_auto = MatiereController.get_niveau_from_type_etablissement(etablissement.type_etablissement)
            
            # Vérifier si c'est un établissement de type lycée
            est_lycee = etablissement.type_etablissement in ['lycée', 'collège_lycée', 'lycee_college', 'mixte', 'lycee', 'college']
            
            # Récupération des données
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'type_matiere': request.POST.get('type_matiere', ''),
                'coefficient': request.POST.get('coefficient', '1.0'),
                'groupes_classes': request.POST.getlist('groupes_classes', []),
            }
            
            # Pour les établissements lycée, récupérer les coefficients par groupe
            if est_lycee:
                coefficients_par_groupe = {}
                for groupe in form_data['groupes_classes']:
                    coeff_key = f'coefficient_{groupe}'
                    coeff_value = request.POST.get(coeff_key, form_data['coefficient'])
                    if coeff_value:
                        try:
                            coefficients_par_groupe[groupe] = float(coeff_value)
                        except ValueError:
                            coefficients_par_groupe[groupe] = float(form_data['coefficient'])
                form_data['coefficients_par_groupe'] = coefficients_par_groupe
            
            # Ajouter le niveau récupéré automatiquement
            form_data['niveau'] = niveau_auto
            
            # Validation
            is_valid = True
            
            # Champs obligatoires (niveau n'est plus requis car récupéré automatiquement)
            required_fields = ['nom', 'type_matiere']
            for field in required_fields:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                    is_valid = False
            
            # Validation du nom
            if form_data['nom'] and len(form_data['nom']) < 2:
                field_errors['nom'] = "Le nom de la matière doit contenir au moins 2 caractères."
                is_valid = False
            
            # Vérification de l'unicité du nom
            if form_data['nom'] and Matiere.objects.filter(
                nom__iexact=form_data['nom'], 
                etablissement=etablissement
            ).exists():
                field_errors['nom'] = "Cette matière existe déjà dans cet établissement."
                is_valid = False
            
            
            # Validation du coefficient
            try:
                coefficient = float(form_data['coefficient'])
                if coefficient < 0 or coefficient > 10:
                    field_errors['coefficient'] = "Le coefficient doit être entre 0 et 10."
                    is_valid = False
            except ValueError:
                field_errors['coefficient'] = "Le coefficient doit être un nombre valide."
                is_valid = False
            
            # Validation du niveau (vérifier qu'il est valide)
            valid_niveaux = [choice[0] for choice in Matiere.NIVEAU_CHOICES]
            if form_data['niveau'] not in valid_niveaux:
                logger.error(f"Niveau invalide déterminé: '{form_data['niveau']}' depuis type_etablissement: '{etablissement.type_etablissement}'. Niveaux valides: {valid_niveaux}")
                field_errors['__all__'] = f"Erreur de niveau: Le niveau '{form_data['niveau']}' déterminé depuis le type d'établissement '{etablissement.type_etablissement}' n'est pas valide. Niveaux valides: {', '.join(valid_niveaux)}"
                is_valid = False
            
            # Si tout est valide, créer la matière
            if is_valid:
                try:
                    with transaction.atomic():
                        # Générer un code unique
                        base_code = form_data['nom'][:3].upper()
                        code = base_code
                        
                        # Vérifier si le code existe déjà et générer un nouveau si nécessaire
                        counter = 1
                        while Matiere.objects.filter(code=code).exists():
                            code = f"{base_code}{counter}"
                            counter += 1
                            if counter > 100:  # Sécurité pour éviter une boucle infinie
                                code = f"{base_code}{random.randint(1000, 9999)}"
                                break
                        
                        # Créer la matière
                        matiere = Matiere(
                            nom=form_data['nom'],
                            code=code,
                            type_matiere=form_data['type_matiere'],
                            niveau=form_data['niveau'],
                            coefficient=float(form_data['coefficient']),
                            etablissement=etablissement,
                        )
                        matiere.save()
                        
                        # Assigner les classes selon les groupes sélectionnés
                        if form_data['groupes_classes']:
                            import re
                            classes_a_assigner = []
                            
                            for groupe in form_data['groupes_classes']:
                                # Récupérer toutes les classes de ce groupe
                                classes_groupe = Classe.objects.filter(
                                    etablissement=etablissement,
                                    nom__startswith=groupe
                                )
                                classes_a_assigner.extend(list(classes_groupe))
                            
                            # Supprimer les doublons
                            classes_uniques = list(set(classes_a_assigner))
                            matiere.classes.set(classes_uniques)
                            
                            # Pour les établissements lycée, créer les coefficients par groupe
                            if est_lycee and 'coefficients_par_groupe' in form_data:
                                for groupe, coefficient in form_data['coefficients_par_groupe'].items():
                                    CoefficientMatiereGroupe.objects.update_or_create(
                                        matiere=matiere,
                                        etablissement=etablissement,
                                        nom_groupe=groupe,
                                        defaults={'coefficient': coefficient}
                                    )
                        
                        messages.success(request, f"La matière '{matiere.nom_complet}' a été ajoutée avec succès !")
                        return redirect('matiere:liste_matieres')
                        
                except Exception as e:
                    error_message = str(e)
                    error_type = type(e).__name__
                    logger.error(f"Erreur lors de l'ajout de la matière [{error_type}]: {error_message}")
                    
                    # Détecter les types d'erreurs spécifiques
                    if 'unique constraint' in error_message.lower() or 'duplicate key' in error_message.lower() or 'UNIQUE constraint' in error_message or 'IntegrityError' in error_type:
                        if 'code' in error_message.lower():
                            field_errors['nom'] = "Une matière avec ce code existe déjà. Le code est généré automatiquement à partir des 3 premières lettres du nom."
                        elif 'nom' in error_message.lower() or 'unique_together' in error_message.lower():
                            field_errors['nom'] = "Une matière avec ce nom existe déjà dans cet établissement."
                        else:
                            field_errors['__all__'] = "Une erreur est survenue lors de l'ajout de la matière. Veuillez réessayer."
                    else:
                        field_errors['__all__'] = "Une erreur est survenue lors de l'ajout de la matière. Veuillez réessayer."
                    is_valid = False
        
        # Récupérer les classes et créer les groupes
        import re
        classes = Classe.objects.filter(etablissement=etablissement).order_by('niveau', 'nom')
        
        # Créer les groupes de classes
        groupes_classes = {}
        for classe in classes:
            # Extraire le niveau de base (ex: "6eme" de "6eme A", "Premiere L" de "Premiere L1", etc.)
            match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
            if match:
                groupe_nom = match.group(1)  # "6eme", "Premiere L", "Terminale S", etc.
            else:
                groupe_nom = classe.nom
            
            if groupe_nom not in groupes_classes:
                groupes_classes[groupe_nom] = {
                    'nom': groupe_nom,
                    'niveau': classe.niveau,
                    'classes': [],
                    'count': 0
                }
            
            groupes_classes[groupe_nom]['classes'].append(classe)
            groupes_classes[groupe_nom]['count'] += 1
        
        # Convertir en liste triée
        groupes_liste = sorted(groupes_classes.values(), key=lambda x: (x['niveau'], x['nom']))
        
        # Vérifier si c'est un établissement de type lycée
        est_lycee = etablissement.type_etablissement in ['lycée', 'collège_lycée', 'lycee_college', 'mixte', 'lycee', 'college']
        
        # Pour les établissements lycée, récupérer les coefficients existants par groupe (vide pour nouveau formulaire)
        coefficients_existants = {}
        
        context = {
            'form_data': form_data,
            'field_errors': field_errors,
            'is_valid': is_valid,
            'etablissement': etablissement,
            'classes': classes,
            'groupes_classes': groupes_liste,
            'type_choices': Matiere.TYPE_MATIERE_CHOICES,
            'est_lycee': est_lycee,
            'coefficients_existants': coefficients_existants,
        }
        
        return render(request, 'school_admin/directeur/pedagogique/matieres/liste_matieres.html', context)
    
    @staticmethod
    @login_required
    def detail_matiere(request, matiere_id):
        """
        Affiche les détails d'une matière avec possibilité de modification
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
            matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
        except Matiere.DoesNotExist:
            messages.error(request, "Matière non trouvée.")
            return redirect('matiere:liste_matieres')
        
        # Récupérer les professeurs associés à cette matière
        from ..model.professeur_model import Professeur
        professeurs_principaux = Professeur.objects.filter(
            matiere_principale=matiere,
            etablissement=etablissement
        ).select_related('matiere_principale')
        
        professeurs_secondaires = Professeur.objects.filter(
            matieres_secondaires=matiere,
            etablissement=etablissement
        ).select_related('matiere_principale')
        
        # Récupérer les classes associées
        classes_associees = matiere.classes.all().order_by('nom')
        
        # Récupérer toutes les classes pour le formulaire de modification
        toutes_classes = Classe.objects.filter(etablissement=etablissement).order_by('nom')
        
        # Créer des groupes de classes pour l'affichage
        import re
        groupes_classes = {}
        for classe in toutes_classes:
            # Extraire le niveau (ex: "6eme" de "6eme A", "5eme" de "5eme B")
            match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
            if match:
                groupe_nom = match.group(1)  # "6eme", "5eme", etc.
            else:
                groupe_nom = classe.nom
            
            if groupe_nom not in groupes_classes:
                groupes_classes[groupe_nom] = {
                    'nom': groupe_nom,
                    'niveau': classe.niveau,
                    'classes': [],
                    'count': 0
                }
            
            groupes_classes[groupe_nom]['classes'].append(classe)
            groupes_classes[groupe_nom]['count'] += 1
        
        # Convertir en liste triée
        groupes_liste = sorted(groupes_classes.values(), key=lambda x: (x['niveau'], x['nom']))
        
        # Regrouper les classes associées par niveau
        classes_par_groupe = {}
        for classe in classes_associees:
            match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
            if match:
                groupe_nom = match.group(1)
            else:
                groupe_nom = classe.nom
            
            if groupe_nom not in classes_par_groupe:
                classes_par_groupe[groupe_nom] = []
            classes_par_groupe[groupe_nom].append(classe)
        
        # Données du formulaire de modification
        form_data = {}
        field_errors = {}
        is_valid = True
        
        if request.method == 'POST':
            # Récupération automatique du niveau depuis le type_etablissement
            niveau_auto = MatiereController.get_niveau_from_type_etablissement(etablissement.type_etablissement)
            
            # Vérifier si c'est un établissement de type lycée
            est_lycee = etablissement.type_etablissement in ['lycée', 'collège_lycée', 'lycee_college', 'mixte', 'lycee', 'college']
            
            # Récupération des données (utiliser 'groupes_classes' pour les groupes)
            form_data = {
                'nom': request.POST.get('nom', '').strip(),
                'type_matiere': request.POST.get('type_matiere', ''),
                'coefficient': request.POST.get('coefficient', '1.0'),
                'groupes_classes': request.POST.getlist('groupes_classes', []),
            }
            
            # Pour les établissements lycée, récupérer les coefficients par groupe
            if est_lycee:
                coefficients_par_groupe = {}
                for groupe in form_data['groupes_classes']:
                    coeff_key = f'coefficient_{groupe}'
                    coeff_value = request.POST.get(coeff_key, form_data['coefficient'])
                    if coeff_value:
                        try:
                            coefficients_par_groupe[groupe] = float(coeff_value)
                        except ValueError:
                            coefficients_par_groupe[groupe] = float(form_data['coefficient'])
                form_data['coefficients_par_groupe'] = coefficients_par_groupe
            
            # Ajouter le niveau récupéré automatiquement
            form_data['niveau'] = niveau_auto
            
            # Validation
            is_valid = True
            
            # Champs obligatoires (niveau n'est plus requis car récupéré automatiquement)
            required_fields = ['nom', 'type_matiere']
            for field in required_fields:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                    is_valid = False
            
            # Validation du nom
            if form_data['nom'] and len(form_data['nom']) < 2:
                field_errors['nom'] = "Le nom de la matière doit contenir au moins 2 caractères."
                is_valid = False
            
            # Vérification de l'unicité du nom (sauf pour la matière actuelle)
            if form_data['nom'] and Matiere.objects.filter(
                nom__iexact=form_data['nom'], 
                etablissement=etablissement
            ).exclude(id=matiere.id).exists():
                field_errors['nom'] = "Cette matière existe déjà dans cet établissement."
                is_valid = False
            
            # Validation du coefficient
            try:
                coefficient = float(form_data['coefficient'])
                if coefficient < 0 or coefficient > 10:
                    field_errors['coefficient'] = "Le coefficient doit être entre 0 et 10."
                    is_valid = False
            except ValueError:
                field_errors['coefficient'] = "Le coefficient doit être un nombre valide."
                is_valid = False
            
            # Validation du niveau (vérifier qu'il est valide)
            valid_niveaux = [choice[0] for choice in Matiere.NIVEAU_CHOICES]
            if form_data['niveau'] not in valid_niveaux:
                logger.error(f"Niveau invalide déterminé: '{form_data['niveau']}' depuis type_etablissement: '{etablissement.type_etablissement}'. Niveaux valides: {valid_niveaux}")
                field_errors['__all__'] = f"Erreur de niveau: Le niveau '{form_data['niveau']}' déterminé depuis le type d'établissement '{etablissement.type_etablissement}' n'est pas valide. Niveaux valides: {', '.join(valid_niveaux)}"
                is_valid = False
            
            # Si tout est valide, modifier la matière
            if is_valid:
                try:
                    with transaction.atomic():
                        # Vérifier si le nom a changé
                        nom_ancien = matiere.nom
                        nom_nouveau = form_data['nom']
                        
                        # Si le nom a changé, générer un nouveau code unique
                        if nom_ancien != nom_nouveau:
                            base_code = nom_nouveau[:3].upper()
                            code = base_code
                            counter = 1
                            
                            # Vérifier si le code existe déjà (en excluant la matière actuelle)
                            while Matiere.objects.filter(code=code).exclude(id=matiere.id).exists():
                                code = f"{base_code}{counter}"
                                counter += 1
                                if counter > 100:  # Sécurité pour éviter une boucle infinie
                                    code = f"{base_code}{random.randint(1000, 9999)}"
                                    break
                            matiere.code = code
                        # Si le nom n'a pas changé, on garde le code actuel (pas besoin de le modifier)
                        
                        # Modifier la matière
                        matiere.nom = form_data['nom']
                        matiere.type_matiere = form_data['type_matiere']
                        matiere.niveau = form_data['niveau']
                        matiere.coefficient = float(form_data['coefficient'])
                        matiere.save()
                        
                        # Assigner les classes selon les groupes sélectionnés
                        if form_data['groupes_classes']:
                            import re
                            classes_a_assigner = []
                            
                            for groupe in form_data['groupes_classes']:
                                # Récupérer toutes les classes de ce groupe
                                classes_groupe = Classe.objects.filter(
                                    etablissement=etablissement,
                                    nom__startswith=groupe
                                )
                                classes_a_assigner.extend(list(classes_groupe))
                            
                            # Supprimer les doublons
                            classes_uniques = list(set(classes_a_assigner))
                            matiere.classes.set(classes_uniques)
                            
                            # Pour les établissements lycée, mettre à jour les coefficients par groupe
                            if est_lycee and 'coefficients_par_groupe' in form_data:
                                # Supprimer les anciens coefficients pour les groupes non sélectionnés
                                CoefficientMatiereGroupe.objects.filter(
                                    matiere=matiere,
                                    etablissement=etablissement
                                ).exclude(nom_groupe__in=form_data['groupes_classes']).delete()
                                
                                # Créer ou mettre à jour les coefficients pour les groupes sélectionnés
                                for groupe, coefficient in form_data['coefficients_par_groupe'].items():
                                    CoefficientMatiereGroupe.objects.update_or_create(
                                        matiere=matiere,
                                        etablissement=etablissement,
                                        nom_groupe=groupe,
                                        defaults={'coefficient': coefficient}
                                    )
                        else:
                            matiere.classes.clear()
                            # Supprimer tous les coefficients par groupe si aucune classe n'est assignée
                            if est_lycee:
                                CoefficientMatiereGroupe.objects.filter(
                                    matiere=matiere,
                                    etablissement=etablissement
                                ).delete()
                        
                        messages.success(request, f"La matière '{matiere.nom_complet}' a été modifiée avec succès !")
                        return redirect('matiere:detail_matiere', matiere_id=matiere.id)
                        
                except Exception as e:
                    error_message = str(e)
                    error_type = type(e).__name__
                    logger.error(f"Erreur lors de la modification de la matière [{error_type}]: {error_message}")
                    
                    # Détecter les types d'erreurs spécifiques
                    if 'unique constraint' in error_message.lower() or 'duplicate key' in error_message.lower() or 'UNIQUE constraint' in error_message or 'IntegrityError' in error_type:
                        if 'code' in error_message.lower():
                            field_errors['nom'] = "Une matière avec ce code existe déjà. Le code est généré automatiquement à partir des 3 premières lettres du nom."
                        elif 'nom' in error_message.lower() or 'unique_together' in error_message.lower():
                            field_errors['nom'] = "Une matière avec ce nom existe déjà dans cet établissement."
                        else:
                            field_errors['__all__'] = "Une erreur est survenue lors de la modification de la matière. Veuillez réessayer."
                    else:
                        field_errors['__all__'] = "Une erreur est survenue lors de la modification de la matière. Veuillez réessayer."
                    is_valid = False
        else:
            # Pré-remplir le formulaire avec les données actuelles
            # Extraire les groupes de classes associées
            groupes_selectionnes = set()
            for classe in classes_associees:
                import re
                match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
                if match:
                    groupes_selectionnes.add(match.group(1))
                else:
                    groupes_selectionnes.add(classe.nom)
            
            form_data = {
                'nom': matiere.nom,
                'type_matiere': matiere.type_matiere,
                'niveau': matiere.niveau,
                'coefficient': str(matiere.coefficient),
                'groupes_classes': list(groupes_selectionnes),
            }
        
        # Vérifier si c'est un établissement de type lycée
        est_lycee = etablissement.type_etablissement in ['lycée', 'collège_lycée','lycee_college','mixte','lycee','college']
        
        # Pour les établissements lycée, récupérer les coefficients existants par groupe
        coefficients_existants = {}
        if est_lycee:
            coeffs = CoefficientMatiereGroupe.objects.filter(
                matiere=matiere,
                etablissement=etablissement
            )
            for coeff in coeffs:
                coefficients_existants[coeff.nom_groupe] = coeff.coefficient
        
        context = {
            'matiere': matiere,
            'professeurs_principaux': professeurs_principaux,
            'professeurs_secondaires': professeurs_secondaires,
            'classes_associees': classes_associees,
            'classes_par_groupe': classes_par_groupe,
            'toutes_classes': toutes_classes,
            'groupes_classes': groupes_liste,
            'form_data': form_data,
            'field_errors': field_errors,
            'is_valid': is_valid,
            'etablissement': etablissement,
            'type_choices': Matiere.TYPE_MATIERE_CHOICES,
            'est_lycee': est_lycee,
            'coefficients_existants': coefficients_existants,
        }
        
        return render(request, 'school_admin/directeur/pedagogique/matieres/detail_matiere.html', context)
    
    @staticmethod
    @login_required
    def toggle_actif(request, matiere_id):
        """
        Active/désactive une matière
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
            matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
            matiere.actif = not matiere.actif
            matiere.save()
            
            status = "activée" if matiere.actif else "désactivée"
            messages.success(request, f"La matière '{matiere.nom_complet}' a été {status}.")
            
        except Matiere.DoesNotExist:
            messages.error(request, "Matière non trouvée.")
        
        return redirect('matiere:liste_matieres')
    
    @staticmethod
    @login_required
    def supprimer_matiere(request, matiere_id):
        """
        Supprime une matière
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
            matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
            nom_matiere = matiere.nom_complet
            
            # Vérifier s'il y a des professeurs associés
            from ..model.professeur_model import Professeur
            professeurs_principaux = Professeur.objects.filter(matiere_principale=matiere).count()
            professeurs_secondaires = Professeur.objects.filter(matieres_secondaires=matiere).count()
            
            if professeurs_principaux > 0 or professeurs_secondaires > 0:
                messages.error(request, f"Impossible de supprimer la matière '{nom_matiere}' car elle est associée à {professeurs_principaux + professeurs_secondaires} professeur(s).")
                return redirect('matiere:detail_matiere', matiere_id=matiere_id)
            
            # Supprimer la matière
            matiere.delete()
            messages.success(request, f"La matière '{nom_matiere}' a été supprimée avec succès !")
            
        except Matiere.DoesNotExist:
            messages.error(request, "Matière non trouvée.")
        
        return redirect('matiere:liste_matieres')
