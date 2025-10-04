from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from datetime import datetime, date
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..model.etablissement_model import Etablissement
from ..model.classe_model import Classe
from ..model.eleve_model import Eleve


@login_required
def dashboard_secretaire(request):
    """
    Dashboard pour le secrétaire d'établissement
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est du personnel administratif avec fonction secrétaire
    if not isinstance(user, PersonnelAdministratif) or user.fonction != 'secretaire':
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'établissement
    etablissement = user.etablissement
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True)
    
    # Statistiques du secrétaire
    stats = {
        'nom_complet': user.nom_complet,
        'fonction': user.get_fonction_display(),
        'etablissement': etablissement.nom,
        'date_creation': user.date_creation,
        'actif': user.actif,
        'numero_employe': user.numero_employe,
    }
    
    # Statistiques de l'établissement
    etablissement_stats = {
        'nom': etablissement.nom,
        'type': etablissement.get_type_etablissement_display(),
        'code': etablissement.code_etablissement,
        'ville': etablissement.ville,
        'pays': etablissement.pays,
    }
    
    # Statistiques des élèves et classes (placeholder pour l'instant)
    dashboard_stats = {
        'total_eleves': 0,  # TODO: Implémenter le comptage des élèves
        'nouveaux_eleves': 0,  # TODO: Implémenter le comptage des nouveaux élèves
        'total_classes': classes.count(),
        'evaluations_en_cours': 0,  # TODO: Implémenter le comptage des évaluations
        'taches_urgentes': 3,  # Placeholder
    }
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'stats': stats,
        'etablissement_stats': etablissement_stats,
        'dashboard_stats': dashboard_stats,
        'classes': classes,
    }
    
    return render(request, 'school_admin/directeur/secretaire/dashboard_secretaire.html', context)


@login_required
def inscription_eleves(request):
    """
    Page d'inscription des élèves pour le secrétaire
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est du personnel administratif avec fonction secrétaire
    if not isinstance(user, PersonnelAdministratif) or user.fonction != 'secretaire':
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'établissement
    etablissement = user.etablissement
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    form_data = {}
    field_errors = {}
    
    # Générer un mot de passe provisoire pour l'affichage initial
    import random
    mot_de_passe_initial = f"{random.randint(1000, 9999)}"
    form_data['mot_de_passe_provisoire'] = mot_de_passe_initial
    
    if request.method == 'POST':
        # Récupération des données
        form_data = {
            'nom': request.POST.get('nom', '').strip(),
            'prenom': request.POST.get('prenom', '').strip(),
            'date_naissance': request.POST.get('date_naissance', ''),
            'lieu_naissance': request.POST.get('lieu_naissance', '').strip(),
            'sexe': request.POST.get('sexe', ''),
            'nationalite': request.POST.get('nationalite', '').strip(),
            'adresse': request.POST.get('adresse', '').strip(),
            'telephone': request.POST.get('telephone', '').strip(),
            'email': request.POST.get('email', '').strip(),
            'classe': request.POST.get('classe', ''),
            'date_inscription': request.POST.get('date_inscription', ''),
            'statut': request.POST.get('statut', ''),
            'numero_eleve': request.POST.get('numero_eleve', '').strip(),
            'type_responsable': request.POST.get('type_responsable', ''),
            # Champs parents
            'nom_pere': request.POST.get('nom_pere', '').strip(),
            'nom_mere': request.POST.get('nom_mere', '').strip(),
            'telephone_pere': request.POST.get('telephone_pere', '').strip(),
            'telephone_mere': request.POST.get('telephone_mere', '').strip(),
            'email_pere': request.POST.get('email_pere', '').strip(),
            'email_mere': request.POST.get('email_mere', '').strip(),
            # Champs tuteur
            'tuteur_nom': request.POST.get('tuteur_nom', '').strip(),
            'tuteur_prenom': request.POST.get('tuteur_prenom', '').strip(),
            'tuteur_telephone': request.POST.get('tuteur_telephone', '').strip(),
            'tuteur_email': request.POST.get('tuteur_email', '').strip(),
            'tuteur_adresse': request.POST.get('tuteur_adresse', '').strip(),
            'tuteur_profession': request.POST.get('tuteur_profession', '').strip(),
            'tuteur_lien': request.POST.get('tuteur_lien', ''),
            # Mot de passe provisoire
            'mot_de_passe_provisoire': request.POST.get('mot_de_passe_provisoire', ''),
            # Documents d'identité
            'document_acte_naissance': request.POST.get('document_acte_naissance') == 'true',
            'document_cni': request.POST.get('document_cni') == 'true',
            'document_passeport': request.POST.get('document_passeport') == 'true',
            # Documents scolaires
            'document_bulletin_precedent': request.POST.get('document_bulletin_precedent') == 'true',
            'document_certificat_scolarite': request.POST.get('document_certificat_scolarite') == 'true',
            'document_livret_scolaire': request.POST.get('document_livret_scolaire') == 'true',
            # Documents médicaux
            'document_certificat_medical': request.POST.get('document_certificat_medical') == 'true',
            'document_carnet_vaccination': request.POST.get('document_carnet_vaccination') == 'true',
            'document_assurance_maladie': request.POST.get('document_assurance_maladie') == 'true',
            # Documents administratifs
            'document_justificatif_domicile': request.POST.get('document_justificatif_domicile') == 'true',
            'document_photo_identite': request.POST.get('document_photo_identite') == 'true',
            'document_autorisation_parentale': request.POST.get('document_autorisation_parentale') == 'true',
        }
        
        # Validation
        is_valid = True
        
        # Champs obligatoires
        required_fields = ['nom', 'prenom', 'date_naissance', 'lieu_naissance', 'sexe', 'nationalite', 'classe', 'date_inscription', 'statut', 'type_responsable']
        for field in required_fields:
            if not form_data[field]:
                field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                is_valid = False
        
        # Validation spécifique selon le type de responsable
        if form_data['type_responsable'] == 'parents':
            # Validation des champs parents - au moins un parent doit être renseigné
            pere_renseigne = form_data['nom_pere'] and form_data['telephone_pere']
            mere_renseignee = form_data['nom_mere'] and form_data['telephone_mere']
            
            if not pere_renseigne and not mere_renseignee:
                field_errors['nom_pere'] = "Au moins un parent doit être renseigné (nom et téléphone)."
                field_errors['nom_mere'] = "Au moins un parent doit être renseigné (nom et téléphone)."
                is_valid = False
            elif pere_renseigne and not mere_renseignee:
                # Si le père est renseigné, la mère devient optionnelle
                pass
            elif mere_renseignee and not pere_renseigne:
                # Si la mère est renseignée, le père devient optionnel
                pass
            else:
                # Les deux parents sont renseignés, c'est parfait
                pass
        elif form_data['type_responsable'] == 'tuteur':
            # Validation des champs tuteur (email optionnel)
            tuteur_required = ['tuteur_nom', 'tuteur_prenom', 'tuteur_telephone', 'tuteur_adresse', 'tuteur_lien']
            for field in tuteur_required:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire pour le tuteur."
                    is_valid = False
        
        # Validation de la date de naissance
        if form_data['date_naissance']:
            try:
                birth_date = datetime.strptime(form_data['date_naissance'], '%Y-%m-%d').date()
                if birth_date > date.today():
                    field_errors['date_naissance'] = "La date de naissance ne peut pas être dans le futur."
                    is_valid = False
            except ValueError:
                field_errors['date_naissance'] = "Format de date invalide."
                is_valid = False
        
        # Validation de la date d'inscription
        if form_data['date_inscription']:
            try:
                inscription_date = datetime.strptime(form_data['date_inscription'], '%Y-%m-%d').date()
                if inscription_date > date.today():
                    field_errors['date_inscription'] = "La date d'inscription ne peut pas être dans le futur."
                    is_valid = False
            except ValueError:
                field_errors['date_inscription'] = "Format de date invalide."
                is_valid = False
        
        # Validation de l'email
        if form_data['email'] and '@' not in form_data['email']:
            field_errors['email'] = "L'adresse email n'est pas valide."
            is_valid = False
        
        # Validation des emails parents/tuteur (optionnels)
        if form_data['type_responsable'] == 'parents':
            if form_data['email_pere'] and '@' not in form_data['email_pere']:
                field_errors['email_pere'] = "L'adresse email du père n'est pas valide."
                is_valid = False
            if form_data['email_mere'] and '@' not in form_data['email_mere']:
                field_errors['email_mere'] = "L'adresse email de la mère n'est pas valide."
                is_valid = False
        elif form_data['type_responsable'] == 'tuteur':
            if form_data['tuteur_email'] and '@' not in form_data['tuteur_email']:
                field_errors['tuteur_email'] = "L'adresse email du tuteur n'est pas valide."
                is_valid = False
        
        # Génération automatique du mot de passe de 4 chiffres
        import random
        mot_de_passe = f"{random.randint(1000, 9999)}"
        form_data['mot_de_passe_provisoire'] = mot_de_passe
        
        # Validation de la classe
        if form_data['classe']:
            try:
                classe = Classe.objects.get(id=form_data['classe'], etablissement=etablissement)
                
                # Vérifier les places disponibles dans la classe
                places_disponibles = classe.places_disponibles
                if places_disponibles <= 0:
                    field_errors['classe'] = f"La classe {classe.nom} est pleine. Aucune place disponible ({classe.capacite_max}/{classe.capacite_max} élèves)."
                    is_valid = False
                elif places_disponibles == 1:
                    # Avertissement si il ne reste qu'une place
                    messages.warning(request, f"Attention : Il ne reste qu'une place disponible dans la classe {classe.nom}.")
                    
            except Classe.DoesNotExist:
                field_errors['classe'] = "La classe sélectionnée n'existe pas."
                is_valid = False
        
        # Validation du sexe
        if form_data['sexe'] not in ['M', 'F']:
            field_errors['sexe'] = "Le sexe doit être Masculin ou Féminin."
            is_valid = False
        
        # Validation du statut
        if form_data['statut'] not in ['nouvelle', 'transfert', 'reinscription']:
            field_errors['statut'] = "Le type d'inscription sélectionné n'est pas valide."
            is_valid = False
        
        # Validation du type de responsable
        if form_data['type_responsable'] not in ['parents', 'tuteur']:
            field_errors['type_responsable'] = "Le type de responsable sélectionné n'est pas valide."
            is_valid = False
        
        # Si tout est valide, traiter l'inscription
        if is_valid:
            try:
                with transaction.atomic():
                    # Générer le numéro d'élève si non fourni
                    if not form_data['numero_eleve']:
                        now = datetime.now()
                        year = now.year % 100
                        random_num = f"{now.microsecond % 1000:03d}"
                        form_data['numero_eleve'] = f"ELE-{year}-{random_num}"
                    
                    # Récupérer la classe et vérifier à nouveau les places disponibles
                    classe = Classe.objects.get(id=form_data['classe'], etablissement=etablissement)
                    
                    # Vérification finale des places disponibles (au cas où la capacité aurait changé)
                    if classe.places_disponibles <= 0:
                        field_errors['classe'] = f"La classe {classe.nom} est maintenant pleine. Aucune place disponible ({classe.capacite_max}/{classe.capacite_max} élèves)."
                        is_valid = False
                        raise Exception("Classe pleine")
                    
                    # Créer l'élève
                    eleve = Eleve(
                        nom=form_data['nom'],
                        prenom=form_data['prenom'],
                        date_naissance=datetime.strptime(form_data['date_naissance'], '%Y-%m-%d').date(),
                        lieu_naissance=form_data['lieu_naissance'],
                        sexe=form_data['sexe'],
                        nationalite=form_data['nationalite'],
                        adresse=form_data['adresse'],
                        telephone=form_data['telephone'],
                        email=form_data['email'],
                        numero_eleve=form_data['numero_eleve'],
                        etablissement=etablissement,
                        classe=classe,
                        date_inscription=datetime.strptime(form_data['date_inscription'], '%Y-%m-%d').date(),
                        statut=form_data['statut'],
                        type_responsable=form_data['type_responsable'],
                        # Champs parents
                        nom_pere=form_data['nom_pere'] if form_data['type_responsable'] == 'parents' else None,
                        nom_mere=form_data['nom_mere'] if form_data['type_responsable'] == 'parents' else None,
                        telephone_pere=form_data['telephone_pere'] if form_data['type_responsable'] == 'parents' else None,
                        telephone_mere=form_data['telephone_mere'] if form_data['type_responsable'] == 'parents' else None,
                        email_pere=form_data['email_pere'] if form_data['type_responsable'] == 'parents' else None,
                        email_mere=form_data['email_mere'] if form_data['type_responsable'] == 'parents' else None,
                        # Champs tuteur
                        tuteur_nom=form_data['tuteur_nom'] if form_data['type_responsable'] == 'tuteur' else None,
                        tuteur_prenom=form_data['tuteur_prenom'] if form_data['type_responsable'] == 'tuteur' else None,
                        tuteur_telephone=form_data['tuteur_telephone'] if form_data['type_responsable'] == 'tuteur' else None,
                        tuteur_email=form_data['tuteur_email'] if form_data['type_responsable'] == 'tuteur' else None,
                        tuteur_adresse=form_data['tuteur_adresse'] if form_data['type_responsable'] == 'tuteur' else None,
                        tuteur_profession=form_data['tuteur_profession'] if form_data['type_responsable'] == 'tuteur' else None,
                        tuteur_lien=form_data['tuteur_lien'] if form_data['type_responsable'] == 'tuteur' else None,
                        # Mot de passe provisoire
                        mot_de_passe_provisoire=form_data['mot_de_passe_provisoire'],
                        # Documents d'identité
                        document_acte_naissance=form_data['document_acte_naissance'],
                        document_cni=form_data['document_cni'],
                        document_passeport=form_data['document_passeport'],
                        # Documents scolaires
                        document_bulletin_precedent=form_data['document_bulletin_precedent'],
                        document_certificat_scolarite=form_data['document_certificat_scolarite'],
                        document_livret_scolaire=form_data['document_livret_scolaire'],
                        # Documents médicaux
                        document_certificat_medical=form_data['document_certificat_medical'],
                        document_carnet_vaccination=form_data['document_carnet_vaccination'],
                        document_assurance_maladie=form_data['document_assurance_maladie'],
                        # Documents administratifs
                        document_justificatif_domicile=form_data['document_justificatif_domicile'],
                        document_photo_identite=form_data['document_photo_identite'],
                        document_autorisation_parentale=form_data['document_autorisation_parentale'],
                        # Configuration de base
                        username=form_data['numero_eleve'],
                        is_active=True,
                        is_staff=False,
                        is_superuser=False,
                    )
                    
                    # Définir le mot de passe pour la connexion
                    eleve.set_password(form_data['mot_de_passe_provisoire'])
                    
                    # Sauvegarder l'élève
                    eleve.save()
                    
                    # Log des documents fournis
                    documents_fournis = eleve.documents_fournis_liste
                    documents_text = ", ".join(documents_fournis) if documents_fournis else "Aucun document"
                    
                    messages.success(request, f"L'élève {form_data['prenom']} {form_data['nom']} a été inscrit avec succès ! Documents fournis: {documents_text}")
                    return redirect('secretaire:reçu_inscription_eleve', eleve_id=eleve.id)
                    
            except Exception as e:
                field_errors['__all__'] = f"Une erreur est survenue lors de l'inscription: {str(e)}. Veuillez réessayer."
                is_valid = False
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'classes': classes,
        'form_data': form_data,
        'field_errors': field_errors,
    }
    
    return render(request, 'school_admin/directeur/secretaire/inscription_eleves.html', context)


@login_required
def liste_eleves(request):
    """
    Page de liste des élèves inscrits par classe
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est du personnel administratif avec fonction secrétaire
    if not isinstance(user, PersonnelAdministratif) or user.fonction != 'secretaire':
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'établissement
    etablissement = user.etablissement
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer les classes de l'établissement avec leurs élèves
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Préparer les données pour chaque classe
    classes_data = []
    total_eleves = 0
    total_capacite = 0
    
    for classe in classes:
        eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('prenom', 'nom')
        
        # Statistiques de la classe
        stats_classe = {
            'total_eleves': eleves.count(),
            'nouveaux_eleves': eleves.filter(statut='nouvelle').count(),
            'transferts': eleves.filter(statut='transfert').count(),
            'reinscriptions': eleves.filter(statut='reinscription').count(),
            'taux_occupation': classe.taux_occupation,
            'places_disponibles': classe.places_disponibles,
        }
        
        classes_data.append({
            'classe': classe,
            'eleves': eleves,
            'stats': stats_classe,
        })
        
        total_eleves += stats_classe['total_eleves']
        total_capacite += classe.capacite_max
    
    # Statistiques générales
    stats_generales = {
        'total_eleves': total_eleves,
        'total_classes': classes.count(),
        'taux_occupation_global': round((total_eleves / total_capacite * 100), 1) if total_capacite > 0 else 0,
        'nouveaux_eleves': sum(classe['stats']['nouveaux_eleves'] for classe in classes_data),
        'transferts': sum(classe['stats']['transferts'] for classe in classes_data),
        'reinscriptions': sum(classe['stats']['reinscriptions'] for classe in classes_data),
    }
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'classes_data': classes_data,
        'stats_generales': stats_generales,
    }
    
    return render(request, 'school_admin/directeur/secretaire/liste_eleves.html', context)


@login_required
def reçu_inscription_eleve(request, eleve_id):
    """
    Page de reçu d'inscription pour un élève
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est du personnel administratif avec fonction secrétaire
    if not isinstance(user, PersonnelAdministratif) or user.fonction != 'secretaire':
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'établissement
    etablissement = user.etablissement
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        # Récupérer l'élève
        eleve = Eleve.objects.get(id=eleve_id, etablissement=etablissement)
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('secretaire:liste_eleves')
    
    # Informations de l'établissement
    etablissement_info = {
        'nom': etablissement.nom,
        'type': etablissement.get_type_etablissement_display(),
        'code': etablissement.code_etablissement,
        'adresse': etablissement.adresse,
        'ville': etablissement.ville,
        'pays': etablissement.pays,
        'telephone': etablissement.telephone,
        'email': etablissement.email,
    }
    
    # Informations de l'élève
    eleve_info = {
        'nom_complet': eleve.nom_complet,
        'numero_eleve': eleve.numero_eleve,
        'date_naissance': eleve.date_naissance,
        'lieu_naissance': eleve.lieu_naissance,
        'sexe': eleve.get_sexe_display(),
        'nationalite': eleve.nationalite,
        'adresse': eleve.adresse,
        'telephone': eleve.telephone,
        'email': eleve.email,
        'classe': eleve.classe.nom if eleve.classe else "Non assigné",
        'niveau_classe': eleve.classe.get_niveau_display() if eleve.classe else "",
        'date_inscription': eleve.date_inscription,
        'statut': eleve.get_statut_display(),
        'type_responsable': eleve.get_type_responsable_display(),
        'mot_de_passe_provisoire': eleve.mot_de_passe_provisoire,
        'documents_fournis': eleve.documents_fournis_liste,
        'nombre_documents': eleve.nombre_documents_fournis,
    }
    
    # Informations des parents/tuteurs
    responsable_info = {}
    if eleve.type_responsable == 'parents':
        responsable_info = {
            'type': 'Parents',
            'pere': {
                'nom': eleve.nom_pere or "Non renseigné",
                'telephone': eleve.telephone_pere or "Non renseigné",
                'email': eleve.email_pere or "Non renseigné",
            },
            'mere': {
                'nom': eleve.nom_mere or "Non renseigné",
                'telephone': eleve.telephone_mere or "Non renseigné",
                'email': eleve.email_mere or "Non renseigné",
            }
        }
    elif eleve.type_responsable == 'tuteur':
        responsable_info = {
            'type': 'Tuteur légal',
            'nom': f"{eleve.tuteur_prenom or ''} {eleve.tuteur_nom or ''}".strip() or "Non renseigné",
            'telephone': eleve.tuteur_telephone or "Non renseigné",
            'email': eleve.tuteur_email or "Non renseigné",
            'adresse': eleve.tuteur_adresse or "Non renseigné",
            'profession': eleve.tuteur_profession or "Non renseigné",
            'lien': eleve.get_tuteur_lien_display() or "Non renseigné",
        }
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'etablissement_info': etablissement_info,
        'eleve': eleve,
        'eleve_info': eleve_info,
        'responsable_info': responsable_info,
    }
    
    return render(request, 'school_admin/directeur/secretaire/reçu_inscription_eleve.html', context)


@login_required
def detail_eleve(request, eleve_id):
    """
    Page de détails d'un élève avec formulaire de modification
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est du personnel administratif avec fonction secrétaire
    if not isinstance(user, PersonnelAdministratif) or user.fonction != 'secretaire':
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'établissement
    etablissement = user.etablissement
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        # Récupérer l'élève
        eleve = Eleve.objects.get(id=eleve_id, etablissement=etablissement)
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('secretaire:liste_eleves')
    
    # Récupérer les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    form_data = {}
    field_errors = {}
    
    if request.method == 'POST':
        # Récupération des données
        form_data = {
            'nom': request.POST.get('nom', '').strip(),
            'prenom': request.POST.get('prenom', '').strip(),
            'date_naissance': request.POST.get('date_naissance', ''),
            'lieu_naissance': request.POST.get('lieu_naissance', '').strip(),
            'sexe': request.POST.get('sexe', ''),
            'nationalite': request.POST.get('nationalite', '').strip(),
            'adresse': request.POST.get('adresse', '').strip(),
            'telephone': request.POST.get('telephone', '').strip(),
            'email': request.POST.get('email', '').strip(),
            'type_responsable': request.POST.get('type_responsable', ''),
            # Champs parents
            'nom_pere': request.POST.get('nom_pere', '').strip(),
            'nom_mere': request.POST.get('nom_mere', '').strip(),
            'telephone_pere': request.POST.get('telephone_pere', '').strip(),
            'telephone_mere': request.POST.get('telephone_mere', '').strip(),
            'email_pere': request.POST.get('email_pere', '').strip(),
            'email_mere': request.POST.get('email_mere', '').strip(),
            # Champs tuteur
            'tuteur_nom': request.POST.get('tuteur_nom', '').strip(),
            'tuteur_prenom': request.POST.get('tuteur_prenom', '').strip(),
            'tuteur_telephone': request.POST.get('tuteur_telephone', '').strip(),
            'tuteur_email': request.POST.get('tuteur_email', '').strip(),
            'tuteur_adresse': request.POST.get('tuteur_adresse', '').strip(),
            'tuteur_profession': request.POST.get('tuteur_profession', '').strip(),
            'tuteur_lien': request.POST.get('tuteur_lien', ''),
            # Documents d'identité
            'document_acte_naissance': request.POST.get('document_acte_naissance') == 'true',
            'document_cni': request.POST.get('document_cni') == 'true',
            'document_passeport': request.POST.get('document_passeport') == 'true',
            # Documents scolaires
            'document_bulletin_precedent': request.POST.get('document_bulletin_precedent') == 'true',
            'document_certificat_scolarite': request.POST.get('document_certificat_scolarite') == 'true',
            'document_livret_scolaire': request.POST.get('document_livret_scolaire') == 'true',
            # Documents médicaux
            'document_certificat_medical': request.POST.get('document_certificat_medical') == 'true',
            'document_carnet_vaccination': request.POST.get('document_carnet_vaccination') == 'true',
            'document_assurance_maladie': request.POST.get('document_assurance_maladie') == 'true',
            # Documents administratifs
            'document_justificatif_domicile': request.POST.get('document_justificatif_domicile') == 'true',
            'document_photo_identite': request.POST.get('document_photo_identite') == 'true',
            'document_autorisation_parentale': request.POST.get('document_autorisation_parentale') == 'true',
        }
        
        # Validation
        is_valid = True
        
        # Champs obligatoires
        required_fields = ['nom', 'prenom', 'date_naissance', 'lieu_naissance', 'sexe', 'nationalite', 'type_responsable']
        for field in required_fields:
            if not form_data[field]:
                field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
                is_valid = False
        
        # Validation spécifique selon le type de responsable
        if form_data['type_responsable'] == 'parents':
            pere_renseigne = form_data['nom_pere'] and form_data['telephone_pere']
            mere_renseignee = form_data['nom_mere'] and form_data['telephone_mere']
            
            if not pere_renseigne and not mere_renseignee:
                field_errors['nom_pere'] = "Au moins un parent doit être renseigné (nom et téléphone)."
                field_errors['nom_mere'] = "Au moins un parent doit être renseigné (nom et téléphone)."
                is_valid = False
        elif form_data['type_responsable'] == 'tuteur':
            tuteur_required = ['tuteur_nom', 'tuteur_prenom', 'tuteur_telephone', 'tuteur_adresse', 'tuteur_lien']
            for field in tuteur_required:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire pour le tuteur."
                    is_valid = False
        
        # Validation des dates
        if form_data['date_naissance']:
            try:
                birth_date = datetime.strptime(form_data['date_naissance'], '%Y-%m-%d').date()
                if birth_date > date.today():
                    field_errors['date_naissance'] = "La date de naissance ne peut pas être dans le futur."
                    is_valid = False
            except ValueError:
                field_errors['date_naissance'] = "Format de date invalide."
                is_valid = False
        
        # Validation des emails
        if form_data['email'] and '@' not in form_data['email']:
            field_errors['email'] = "L'adresse email n'est pas valide."
            is_valid = False
        
        if form_data['type_responsable'] == 'parents':
            if form_data['email_pere'] and '@' not in form_data['email_pere']:
                field_errors['email_pere'] = "L'adresse email du père n'est pas valide."
                is_valid = False
            if form_data['email_mere'] and '@' not in form_data['email_mere']:
                field_errors['email_mere'] = "L'adresse email de la mère n'est pas valide."
                is_valid = False
        elif form_data['type_responsable'] == 'tuteur':
            if form_data['tuteur_email'] and '@' not in form_data['tuteur_email']:
                field_errors['tuteur_email'] = "L'adresse email du tuteur n'est pas valide."
                is_valid = False
        
        
        # Si tout est valide, sauvegarder les modifications
        if is_valid:
            try:
                with transaction.atomic():
                    # Mettre à jour les informations de base
                    eleve.nom = form_data['nom']
                    eleve.prenom = form_data['prenom']
                    eleve.date_naissance = datetime.strptime(form_data['date_naissance'], '%Y-%m-%d').date()
                    eleve.lieu_naissance = form_data['lieu_naissance']
                    eleve.sexe = form_data['sexe']
                    eleve.nationalite = form_data['nationalite']
                    eleve.adresse = form_data['adresse']
                    eleve.telephone = form_data['telephone']
                    eleve.email = form_data['email']
                    eleve.type_responsable = form_data['type_responsable']
                    
                    # Mettre à jour les informations parents/tuteur
                    if form_data['type_responsable'] == 'parents':
                        eleve.nom_pere = form_data['nom_pere']
                        eleve.nom_mere = form_data['nom_mere']
                        eleve.telephone_pere = form_data['telephone_pere']
                        eleve.telephone_mere = form_data['telephone_mere']
                        eleve.email_pere = form_data['email_pere']
                        eleve.email_mere = form_data['email_mere']
                        # Effacer les champs tuteur
                        eleve.tuteur_nom = None
                        eleve.tuteur_prenom = None
                        eleve.tuteur_telephone = None
                        eleve.tuteur_email = None
                        eleve.tuteur_adresse = None
                        eleve.tuteur_profession = None
                        eleve.tuteur_lien = None
                    elif form_data['type_responsable'] == 'tuteur':
                        eleve.tuteur_nom = form_data['tuteur_nom']
                        eleve.tuteur_prenom = form_data['tuteur_prenom']
                        eleve.tuteur_telephone = form_data['tuteur_telephone']
                        eleve.tuteur_email = form_data['tuteur_email']
                        eleve.tuteur_adresse = form_data['tuteur_adresse']
                        eleve.tuteur_profession = form_data['tuteur_profession']
                        eleve.tuteur_lien = form_data['tuteur_lien']
                        # Effacer les champs parents
                        eleve.nom_pere = None
                        eleve.nom_mere = None
                        eleve.telephone_pere = None
                        eleve.telephone_mere = None
                        eleve.email_pere = None
                        eleve.email_mere = None
                    
                    # Mettre à jour les documents
                    eleve.document_acte_naissance = form_data['document_acte_naissance']
                    eleve.document_cni = form_data['document_cni']
                    eleve.document_passeport = form_data['document_passeport']
                    eleve.document_bulletin_precedent = form_data['document_bulletin_precedent']
                    eleve.document_certificat_scolarite = form_data['document_certificat_scolarite']
                    eleve.document_livret_scolaire = form_data['document_livret_scolaire']
                    eleve.document_certificat_medical = form_data['document_certificat_medical']
                    eleve.document_carnet_vaccination = form_data['document_carnet_vaccination']
                    eleve.document_assurance_maladie = form_data['document_assurance_maladie']
                    eleve.document_justificatif_domicile = form_data['document_justificatif_domicile']
                    eleve.document_photo_identite = form_data['document_photo_identite']
                    eleve.document_autorisation_parentale = form_data['document_autorisation_parentale']
                    
                    # Sauvegarder
                    eleve.save()
                    
                    messages.success(request, f"Les informations de {eleve.prenom} {eleve.nom} ont été mises à jour avec succès !")
                    return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
                    
            except Exception as e:
                field_errors['__all__'] = f"Une erreur est survenue lors de la modification: {str(e)}. Veuillez réessayer."
                is_valid = False
    else:
        # Remplir le formulaire avec les données actuelles de l'élève
        form_data = {
            'nom': eleve.nom,
            'prenom': eleve.prenom,
            'date_naissance': eleve.date_naissance.strftime('%Y-%m-%d') if eleve.date_naissance else '',
            'lieu_naissance': eleve.lieu_naissance,
            'sexe': eleve.sexe,
            'nationalite': eleve.nationalite,
            'adresse': eleve.adresse,
            'telephone': eleve.telephone,
            'email': eleve.email,
            'type_responsable': eleve.type_responsable,
            # Champs parents
            'nom_pere': eleve.nom_pere,
            'nom_mere': eleve.nom_mere,
            'telephone_pere': eleve.telephone_pere,
            'telephone_mere': eleve.telephone_mere,
            'email_pere': eleve.email_pere,
            'email_mere': eleve.email_mere,
            # Champs tuteur
            'tuteur_nom': eleve.tuteur_nom,
            'tuteur_prenom': eleve.tuteur_prenom,
            'tuteur_telephone': eleve.tuteur_telephone,
            'tuteur_email': eleve.tuteur_email,
            'tuteur_adresse': eleve.tuteur_adresse,
            'tuteur_profession': eleve.tuteur_profession,
            'tuteur_lien': eleve.tuteur_lien,
            # Documents
            'document_acte_naissance': eleve.document_acte_naissance,
            'document_cni': eleve.document_cni,
            'document_passeport': eleve.document_passeport,
            'document_bulletin_precedent': eleve.document_bulletin_precedent,
            'document_certificat_scolarite': eleve.document_certificat_scolarite,
            'document_livret_scolaire': eleve.document_livret_scolaire,
            'document_certificat_medical': eleve.document_certificat_medical,
            'document_carnet_vaccination': eleve.document_carnet_vaccination,
            'document_assurance_maladie': eleve.document_assurance_maladie,
            'document_justificatif_domicile': eleve.document_justificatif_domicile,
            'document_photo_identite': eleve.document_photo_identite,
            'document_autorisation_parentale': eleve.document_autorisation_parentale,
        }
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'eleve': eleve,
        'classes': classes,
        'form_data': form_data,
        'field_errors': field_errors,
    }
    
    return render(request, 'school_admin/directeur/secretaire/detail_eleve.html', context)


@login_required
def transfer_eleve(request, eleve_id):
    """
    Transfert d'un élève vers une autre classe
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est du personnel administratif avec fonction secrétaire
    if not isinstance(user, PersonnelAdministratif) or user.fonction != 'secretaire':
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'établissement
    etablissement = user.etablissement
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        # Récupérer l'élève
        eleve = Eleve.objects.get(id=eleve_id, etablissement=etablissement)
    except Eleve.DoesNotExist:
        messages.error(request, "Élève non trouvé.")
        return redirect('secretaire:liste_eleves')
    
    if request.method == 'POST':
        nouvelle_classe_id = request.POST.get('new_class')
        raison_transfert = request.POST.get('transfer_reason', '').strip()
        
        if not nouvelle_classe_id:
            messages.error(request, "Veuillez sélectionner une classe de destination.")
            return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
        
        try:
            nouvelle_classe = Classe.objects.get(id=nouvelle_classe_id, etablissement=etablissement)
            
            # Vérifier si c'est la même classe
            if nouvelle_classe.id == eleve.classe.id:
                messages.warning(request, f"L'élève est déjà dans la classe {nouvelle_classe.nom}.")
                return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
            
            # Vérifier les places disponibles
            places_disponibles = nouvelle_classe.places_disponibles
            if places_disponibles <= 0:
                messages.error(
                    request, 
                    f"❌ Transfert impossible : La classe {nouvelle_classe.nom} est pleine. "
                    f"Capacité : {nouvelle_classe.capacite_max}/{nouvelle_classe.capacite_max} élèves. "
                    f"Aucune place disponible."
                )
                return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
            
            # Avertissement si il ne reste qu'une place
            if places_disponibles == 1:
                messages.warning(
                    request, 
                    f"⚠️ Attention : Il ne reste qu'une place disponible dans la classe {nouvelle_classe.nom}."
                )
            
            # Effectuer le transfert
            ancienne_classe = eleve.classe
            eleve.classe = nouvelle_classe
            eleve.save()
            
            # Message de succès
            messages.success(
                request, 
                f"✅ Transfert réussi : {eleve.nom_complet} a été transféré de {ancienne_classe.nom} vers {nouvelle_classe.nom}. "
                f"Places restantes : {nouvelle_classe.places_disponibles - 1}/{nouvelle_classe.capacite_max}"
            )
            
            # Log du transfert (optionnel)
            if raison_transfert:
                messages.info(request, f"Raison du transfert: {raison_transfert}")
            
            return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
            
        except Classe.DoesNotExist:
            messages.error(request, "La classe sélectionnée n'existe pas.")
            return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
        except Exception as e:
            messages.error(request, f"Une erreur est survenue lors du transfert: {str(e)}")
            return redirect('secretaire:detail_eleve', eleve_id=eleve.id)
    
    # Redirection si accès GET direct
    return redirect('secretaire:detail_eleve', eleve_id=eleve.id)


@login_required
def gestion_classes(request):
    """
    Page de gestion des classes pour le secrétaire
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est du personnel administratif avec fonction secrétaire
    if not isinstance(user, PersonnelAdministratif) or user.fonction != 'secretaire':
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'établissement
    etablissement = user.etablissement
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer les classes de l'établissement
    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
    
    # Statistiques des classes
    stats_classes = {
        'total_classes': classes.count(),
        'total_capacite': sum(classe.capacite_max for classe in classes),
        'total_eleves': sum(classe.eleves.count() for classe in classes),
        'taux_occupation_moyen': 0,
    }
    
    if stats_classes['total_capacite'] > 0:
        stats_classes['taux_occupation_moyen'] = round(
            (stats_classes['total_eleves'] / stats_classes['total_capacite']) * 100, 1
        )
    
    # Préparer les données pour chaque classe
    classes_data = []
    for classe in classes:
        eleves_count = classe.eleves.count()
        classes_data.append({
            'classe': classe,
            'eleves_count': eleves_count,
            'places_disponibles': classe.places_disponibles,
            'taux_occupation': classe.taux_occupation,
            'statut_capacite': 'pleine' if classe.places_disponibles == 0 else 'libre' if classe.places_disponibles == classe.capacite_max else 'partielle',
        })
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'classes_data': classes_data,
        'stats_classes': stats_classes,
    }
    
    return render(request, 'school_admin/directeur/secretaire/gestion_classes.html', context)


@login_required
def detail_classe(request, classe_id):
    """
    Page de détails d'une classe avec liste des élèves
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est du personnel administratif avec fonction secrétaire
    if not isinstance(user, PersonnelAdministratif) or user.fonction != 'secretaire':
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'établissement
    etablissement = user.etablissement
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        # Récupérer la classe
        classe = Classe.objects.get(id=classe_id, etablissement=etablissement, actif=True)
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('secretaire:gestion_classes')
    
    # Récupérer les élèves de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('prenom', 'nom')
    
    # Statistiques de la classe
    stats_classe = {
        'total_eleves': eleves.count(),
        'nouveaux_eleves': eleves.filter(statut='nouvelle').count(),
        'transferts': eleves.filter(statut='transfert').count(),
        'reinscriptions': eleves.filter(statut='reinscription').count(),
        'taux_occupation': classe.taux_occupation,
        'places_disponibles': classe.places_disponibles,
        'capacite_max': classe.capacite_max,
    }
    
    # Statistiques par sexe
    stats_sexe = {
        'masculin': eleves.filter(sexe='M').count(),
        'feminin': eleves.filter(sexe='F').count(),
    }
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'classe': classe,
        'eleves': eleves,
        'stats_classe': stats_classe,
        'stats_sexe': stats_sexe,
    }
    
    return render(request, 'school_admin/directeur/secretaire/detail_classe.html', context)


@login_required
def imprimer_liste_eleves(request, classe_id):
    """
    Page d'impression de la liste des élèves d'une classe
    """
    # Récupérer l'utilisateur connecté
    user = request.user
    
    # Vérifier que l'utilisateur est du personnel administratif avec fonction secrétaire
    if not isinstance(user, PersonnelAdministratif) or user.fonction != 'secretaire':
        messages.error(request, "Accès non autorisé. Vous devez être un secrétaire.")
        return redirect('school_admin:connexion_compte_user')
    
    # Récupérer l'établissement
    etablissement = user.etablissement
    
    if not etablissement:
        messages.error(request, "Aucun établissement associé à votre compte.")
        return redirect('school_admin:connexion_compte_user')
    
    try:
        # Récupérer la classe
        classe = Classe.objects.get(id=classe_id, etablissement=etablissement, actif=True)
    except Classe.DoesNotExist:
        messages.error(request, "Classe non trouvée.")
        return redirect('secretaire:gestion_classes')
    
    # Récupérer les élèves de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True).order_by('prenom', 'nom')
    
    # Informations de l'établissement
    etablissement_info = {
        'nom': etablissement.nom,
        'type': etablissement.get_type_etablissement_display(),
        'code': etablissement.code_etablissement,
        'adresse': etablissement.adresse,
        'ville': etablissement.ville,
        'pays': etablissement.pays,
        'telephone': etablissement.telephone,
        'email': etablissement.email,
    }
    
    # Informations de la classe
    classe_info = {
        'nom': classe.nom,
        'niveau': classe.get_niveau_display(),
        'capacite_max': classe.capacite_max,
        'total_eleves': eleves.count(),
        'places_disponibles': classe.places_disponibles,
        'taux_occupation': classe.taux_occupation,
        'description': classe.description,
    }
    
    context = {
        'user': user,
        'etablissement': etablissement,
        'etablissement_info': etablissement_info,
        'classe': classe,
        'classe_info': classe_info,
        'eleves': eleves,
    }
    
    return render(request, 'school_admin/directeur/secretaire/imprimer_liste_eleves.html', context)
