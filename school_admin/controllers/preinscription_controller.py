import logging
from datetime import date, datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db import transaction

from ..model.preinscription_model import LienPreinscription, PreinscriptionEleve
from ..model.etablissement_model import Etablissement
from ..model.classe_model import Classe

logger = logging.getLogger(__name__)


class PreinscriptionController:
    """
    Contrôleur pour gérer les préinscriptions d'élèves
    """
    
    @staticmethod
    def formulaire_preinscription(request, token):
        """
        Affiche le formulaire de préinscription publique
        """
        # Récupérer le lien de préinscription
        lien = get_object_or_404(LienPreinscription, token=token, actif=True)
        etablissement = lien.etablissement
        
        # Récupérer les classes disponibles
        classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
        
        # Récupérer la liste des pays (similaire à inscription_eleves)
        try:
            from django_countries import countries
            pays_list = [(code, name) for code, name in countries]
        except ImportError:
            # Fallback si django_countries n'est pas installé
            pays_list = [
                ('SN', 'Sénégal'),
                ('CI', 'Côte d\'Ivoire'),
                ('CM', 'Cameroun'),
                ('FR', 'France'),
                ('ML', 'Mali'),
                ('BF', 'Burkina Faso'),
                ('GN', 'Guinée'),
                ('NE', 'Niger'),
                ('TD', 'Tchad'),
                ('MR', 'Mauritanie'),
            ]
        
        form_data = {
            'statut_inscription': 'nouvelle',
            'nationalite': '',
        }
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
                'classe_souhaitee': request.POST.get('classe_souhaitee', ''),
                'statut_inscription': request.POST.get('statut_inscription', 'nouvelle'),
                # Champs parent/tuteur
                'parent_nom': request.POST.get('parent_nom', '').strip(),
                'parent_prenom': request.POST.get('parent_prenom', '').strip(),
                'parent_telephone': request.POST.get('parent_telephone_full', '').strip() or request.POST.get('parent_telephone', '').strip(),
                'parent_adresse': request.POST.get('parent_adresse', '').strip(),
                'parent_profession': request.POST.get('parent_profession', '').strip(),
                'parent_lien': request.POST.get('parent_lien', ''),
                'commentaires_parent': request.POST.get('commentaires_parent', '').strip(),
            }
            
            # Validation
            is_valid = True
            
            # Champs obligatoires
            required_fields = ['nom', 'prenom', 'date_naissance', 'lieu_naissance', 'sexe', 'nationalite', 'parent_nom', 'parent_prenom', 'parent_telephone', 'parent_lien']
            for field in required_fields:
                if not form_data[field]:
                    field_errors[field] = f"Le champ {field.replace('_', ' ').title()} est obligatoire."
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
            
            # Validation du sexe
            if form_data['sexe'] not in ['M', 'F']:
                field_errors['sexe'] = "Le sexe doit être Masculin ou Féminin."
                is_valid = False
            
            # Validation du statut
            if form_data['statut_inscription'] not in ['nouvelle', 'reinscription']:
                field_errors['statut_inscription'] = "Le type d'inscription sélectionné n'est pas valide."
                is_valid = False
            
            # Validation du lien parent/tuteur
            if form_data['parent_lien'] not in ['pere', 'mere', 'grand_parent', 'oncle_tante', 'frere_soeur', 'autre_famille', 'tuteur_legal', 'autre']:
                field_errors['parent_lien'] = "Le lien avec l'élève sélectionné n'est pas valide."
                is_valid = False
            
            # Validation de la classe (optionnelle)
            classe_souhaitee = None
            if form_data['classe_souhaitee']:
                try:
                    classe_souhaitee = Classe.objects.get(id=form_data['classe_souhaitee'], etablissement=etablissement)
                except Classe.DoesNotExist:
                    field_errors['classe_souhaitee'] = "La classe sélectionnée n'existe pas."
                    is_valid = False
            
            # Si tout est valide, créer la préinscription
            if is_valid:
                try:
                    with transaction.atomic():
                        preinscription = PreinscriptionEleve.objects.create(
                            lien_preinscription=lien,
                            etablissement=etablissement,
                            nom=form_data['nom'],
                            prenom=form_data['prenom'],
                            date_naissance=datetime.strptime(form_data['date_naissance'], '%Y-%m-%d').date(),
                            lieu_naissance=form_data['lieu_naissance'],
                            sexe=form_data['sexe'],
                            nationalite=form_data['nationalite'],
                            adresse=form_data['adresse'] or None,
                            classe_souhaitee=classe_souhaitee,
                            statut_inscription=form_data['statut_inscription'],
                            parent_nom=form_data['parent_nom'],
                            parent_prenom=form_data['parent_prenom'],
                            parent_telephone=form_data['parent_telephone'],
                            parent_adresse=form_data['parent_adresse'] or None,
                            parent_profession=form_data['parent_profession'] or None,
                            parent_lien=form_data['parent_lien'],
                            commentaires_parent=form_data['commentaires_parent'] or None,
                            statut='en_attente'
                        )
                        
                        # Incrémenter le compteur d'utilisations
                        lien.incrementer_utilisation()
                        
                        logger.info(f"Préinscription créée avec succès: {preinscription}")
                        
                        # Rediriger vers une page de confirmation
                        return redirect('school_admin:preinscription:confirmation', token=token, preinscription_id=preinscription.id)
                        
                except Exception as e:
                    logger.error(f"Erreur lors de la création de la préinscription: {str(e)}")
                    field_errors['__all__'] = "Une erreur est survenue lors de la soumission. Veuillez réessayer."
        
        context = {
            'etablissement': etablissement,
            'classes': classes,
            'pays_list': pays_list,
            'form_data': form_data,
            'field_errors': field_errors,
            'token': token,
        }
        
        return render(request, 'school_admin/preinscription/formulaire_preinscription.html', context)
    
    @staticmethod
    def confirmation_preinscription(request, token, preinscription_id):
        """
        Affiche la page de confirmation après soumission
        """
        lien = get_object_or_404(LienPreinscription, token=token, actif=True)
        preinscription = get_object_or_404(PreinscriptionEleve, id=preinscription_id, lien_preinscription=lien)
        
        context = {
            'etablissement': lien.etablissement,
            'preinscription': preinscription,
        }
        
        return render(request, 'school_admin/preinscription/confirmation_preinscription.html', context)
    
    @staticmethod
    @login_required
    def gerer_liens_preinscription(request):
        """
        Interface directeur pour gérer les liens de préinscription
        """
        from ..model.etablissement_model import Etablissement
        
        user = request.user
        if not isinstance(user, Etablissement):
            from django.contrib import messages
            from django.shortcuts import redirect
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        etablissement = user
        
        # Récupérer ou créer le lien de préinscription
        lien, created = LienPreinscription.objects.get_or_create(
            etablissement=etablissement,
            defaults={'actif': True}
        )
        
        # Générer l'URL absolue
        url_absolue = lien.get_url_absolue(request)
        
        context = {
            'etablissement': etablissement,
            'lien': lien,
            'url_absolue': url_absolue,
            'is_directeur': True,
        }
        
        return render(request, 'school_admin/directeur/preinscription/gerer_liens.html', context)
    
    @staticmethod
    @login_required
    def toggle_lien_actif(request):
        """
        Active ou désactive le lien de préinscription
        """
        from django.http import JsonResponse
        from ..model.etablissement_model import Etablissement
        
        user = request.user
        if not isinstance(user, Etablissement):
            return JsonResponse({'success': False, 'message': 'Accès non autorisé.'}, status=403)
        
        etablissement = user
        
        try:
            lien = LienPreinscription.objects.get(etablissement=etablissement)
            lien.actif = not lien.actif
            lien.save()
            return JsonResponse({
                'success': True,
                'actif': lien.actif,
                'message': 'Lien activé' if lien.actif else 'Lien désactivé'
            })
        except LienPreinscription.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Lien introuvable.'}, status=404)
    
    @staticmethod
    @login_required
    def liste_preinscriptions(request):
        """
        Liste toutes les préinscriptions de l'établissement
        """
        from django.core.paginator import Paginator
        from ..model.etablissement_model import Etablissement
        
        user = request.user
        if not isinstance(user, Etablissement):
            from django.contrib import messages
            from django.shortcuts import redirect
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        etablissement = user
        
        # Récupérer uniquement les préinscriptions en attente
        preinscriptions = PreinscriptionEleve.objects.filter(
            etablissement=etablissement,
            statut='en_attente'
        ).order_by('-date_soumission')
        
        # Pagination
        paginator = Paginator(preinscriptions, 20)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Statistiques (seulement pour information)
        total_en_attente = preinscriptions.count()
        
        context = {
            'etablissement': etablissement,
            'preinscriptions': page_obj,
            'total_en_attente': total_en_attente,
            'is_directeur': True,
        }
        
        return render(request, 'school_admin/directeur/preinscription/liste_preinscriptions.html', context)
    
    @staticmethod
    @login_required
    def detail_preinscription(request, preinscription_id):
        """
        Affiche le formulaire d'inscription pré-rempli basé sur la préinscription
        """
        from ..model.etablissement_model import Etablissement
        from ..model.classe_model import Classe
        from django_countries import countries
        
        user = request.user
        if not isinstance(user, Etablissement):
            from django.contrib import messages
            from django.shortcuts import redirect
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        etablissement = user
        preinscription = get_object_or_404(PreinscriptionEleve, id=preinscription_id, etablissement=etablissement)
        
        # Si la préinscription est déjà validée, rediriger vers le reçu
        if preinscription.statut == 'validee':
            # Chercher l'élève créé à partir de cette préinscription
            from ..model.eleve_model import Eleve
            eleve = Eleve.objects.filter(
                nom=preinscription.nom,
                prenom=preinscription.prenom,
                date_naissance=preinscription.date_naissance,
                etablissement=etablissement
            ).first()
            
            if eleve:
                from django.urls import reverse
                return redirect('secretaire:reçu_inscription_eleve', eleve_id=eleve.id)
            else:
                from django.contrib import messages
                messages.info(request, "Cette préinscription a déjà été validée.")
                return redirect('directeur:liste_preinscriptions')
        
        # Récupérer les classes disponibles
        classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
        
        # Préparer les données du formulaire à partir de la préinscription
        form_data = {
            'nom': preinscription.nom,
            'prenom': preinscription.prenom,
            'date_naissance': preinscription.date_naissance.strftime('%Y-%m-%d') if preinscription.date_naissance else '',
            'lieu_naissance': preinscription.lieu_naissance,
            'sexe': preinscription.sexe,
            'nationalite': preinscription.nationalite,
            'adresse': preinscription.adresse or '',
            'classe': preinscription.classe_souhaitee.id if preinscription.classe_souhaitee else '',
            'statut_inscription': preinscription.statut_inscription,
            'parent_nom': preinscription.parent_nom,
            'parent_prenom': preinscription.parent_prenom,
            'parent_telephone': preinscription.parent_telephone,
            'parent_adresse': preinscription.parent_adresse or '',
            'parent_profession': preinscription.parent_profession or '',
            'parent_lien': preinscription.parent_lien,
            'parent_email': '',  # Pas d'email dans la préinscription
        }
        
        # Récupérer la liste des pays
        try:
            pays_list = [(code, str(nom)) for code, nom in countries]
        except Exception:
            pays_list = []
        
        context = {
            'etablissement': etablissement,
            'preinscription': preinscription,
            'form_data': form_data,
            'classes': classes,
            'pays_list': pays_list,
            'field_errors': {},
            'is_directeur': True,
        }
        
        return render(request, 'school_admin/directeur/preinscription/formulaire_inscription_preinscription.html', context)
    
    @staticmethod
    @login_required
    def valider_preinscription(request, preinscription_id):
        """
        Valide une préinscription avec les documents et redirige vers le reçu d'inscription
        """
        from django.contrib import messages
        from django.shortcuts import redirect
        from ..model.etablissement_model import Etablissement
        
        user = request.user
        if not isinstance(user, Etablissement):
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        etablissement = user
        preinscription = get_object_or_404(PreinscriptionEleve, id=preinscription_id, etablissement=etablissement)
        
        # Vérifier que la préinscription est en attente
        if preinscription.statut != 'en_attente':
            messages.warning(request, "Cette préinscription a déjà été traitée.")
            return redirect('directeur:liste_preinscriptions')
        
        if request.method == 'POST':
            # Récupérer les commentaires
            commentaires = request.POST.get('commentaires_etablissement', '')
            
            # Vérifier que la classe est bien présente dans la préinscription
            if not preinscription.classe_souhaitee:
                messages.error(request, "La préinscription n'a pas de classe spécifiée. Veuillez d'abord modifier la préinscription.")
                return redirect('directeur:detail_preinscription', preinscription_id=preinscription_id)
            
            # Récupérer les documents fournis
            documents = {
                'document_acte_naissance': request.POST.get('document_acte_naissance') == 'true',
                'document_cni': request.POST.get('document_cni') == 'true',
                'document_passeport': request.POST.get('document_passeport') == 'true',
                'document_bulletin_precedent': request.POST.get('document_bulletin_precedent') == 'true',
                'document_certificat_scolarite': request.POST.get('document_certificat_scolarite') == 'true',
                'document_livret_scolaire': request.POST.get('document_livret_scolaire') == 'true',
                'document_certificat_medical': request.POST.get('document_certificat_medical') == 'true',
                'document_carnet_vaccination': request.POST.get('document_carnet_vaccination') == 'true',
                'document_assurance_maladie': request.POST.get('document_assurance_maladie') == 'true',
                'document_justificatif_domicile': request.POST.get('document_justificatif_domicile') == 'true',
                'document_photo_identite': request.POST.get('document_photo_identite') == 'true',
                'document_autorisation_parentale': request.POST.get('document_autorisation_parentale') == 'true',
            }
            
            try:
                # Valider la préinscription (crée l'élève et le parent)
                # La classe et le statut sont automatiquement pris de la préinscription
                eleve, parent = preinscription.valider(etablissement, commentaires, documents)
                
                # Vérifier que les tokens QR sont bien générés
                if not eleve.qr_auth_token:
                    eleve.generer_et_sauvegarder_token_qr()
                
                if parent and not parent.qr_auth_token:
                    parent.generer_et_sauvegarder_token_qr()
                
                messages.success(request, f"Préinscription validée avec succès. L'élève {eleve.nom_complet} a été inscrit.")
                
                # Rediriger vers le reçu d'inscription
                return redirect('secretaire:reçu_inscription_eleve', eleve_id=eleve.id)
                
            except Exception as e:
                logger.error(f"Erreur lors de la validation de la préinscription: {str(e)}", exc_info=True)
                messages.error(request, f"Une erreur est survenue lors de la validation : {str(e)}")
                return redirect('directeur:detail_preinscription', preinscription_id=preinscription_id)
        
        # Si GET, rediriger vers le formulaire
        return redirect('directeur:detail_preinscription', preinscription_id=preinscription_id)
    
    @staticmethod
    @login_required
    def rejeter_preinscription(request, preinscription_id):
        """
        Rejette une préinscription
        """
        from django.http import JsonResponse
        from ..model.etablissement_model import Etablissement
        
        user = request.user
        if not isinstance(user, Etablissement):
            return JsonResponse({'success': False, 'message': 'Accès non autorisé.'}, status=403)
        
        etablissement = user
        preinscription = get_object_or_404(PreinscriptionEleve, id=preinscription_id, etablissement=etablissement)
        
        commentaires = request.POST.get('commentaires', '')
        
        try:
            preinscription.rejeter(etablissement, commentaires)
            return JsonResponse({'success': True, 'message': 'Préinscription rejetée.'})
        except Exception as e:
            logger.error(f"Erreur lors du rejet de la préinscription: {str(e)}")
            return JsonResponse({'success': False, 'message': 'Une erreur est survenue.'}, status=500)

