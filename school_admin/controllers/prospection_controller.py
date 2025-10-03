from django.shortcuts import render, redirect
from ..model.prospection_model import Prospection
from django.contrib import messages



class ProspectionController:
    @staticmethod
    def ajouter_prospection(request):
        if request.method == 'POST':
            is_valid = True
            field_errors = {}
            form_data = {
                'nom_etablissement': request.POST.get('nom_etablissement', ''),
                'type_etablissement': request.POST.get('type_etablissement', ''),
                'genre_etablissement': request.POST.get('genre_etablissement', ''),
                'statut_etablissement': request.POST.get('statut_etablissement', ''),
                'ville_etablissement': request.POST.get('ville_etablissement', ''),
                'pays_etablissement': request.POST.get('pays_etablissement', ''),
                'adresse_etablissement': request.POST.get('adresse_etablissement', ''),
                'potentiel_etablissement': request.POST.get('potentiel_etablissement', ''),
                'priorite_etablissement': request.POST.get('priorite_etablissement', ''),
                'source_etablissement': request.POST.get('source_etablissement', ''),
                'prochaine_action_etablissement': request.POST.get('prochaine_action_etablissement', ''),
                'notes_commercial': request.POST.get('notes_commercial', ''),
            }
            
            # Validation des champs obligatoires
            if not form_data['nom_etablissement']:
                field_errors['nom_etablissement'] = "Le nom de l'établissement est obligatoire."
                is_valid = False
            
            if not form_data['type_etablissement']:
                field_errors['type_etablissement'] = "Le type de l'établissement est obligatoire."
                is_valid = False
            
            if not form_data['genre_etablissement']:
                field_errors['genre_etablissement'] = "Le genre de l'établissement est obligatoire."
                is_valid = False
            
            if not form_data['statut_etablissement']:
                field_errors['statut_etablissement'] = "Le statut de l'établissement est obligatoire."
                is_valid = False
            
            if not form_data['ville_etablissement']:
                field_errors['ville_etablissement'] = "La ville de l'établissement est obligatoire."
                is_valid = False
            
            if not form_data['pays_etablissement']:
                field_errors['pays_etablissement'] = "Le pays de l'établissement est obligatoire."
                is_valid = False
            
            if not form_data['adresse_etablissement']:
                field_errors['adresse_etablissement'] = "L'adresse de l'établissement est obligatoire."
                is_valid = False
            
            if not form_data['potentiel_etablissement']:
                field_errors['potentiel_etablissement'] = "Le potentiel de l'établissement est obligatoire."
                is_valid = False
            
            if not form_data['priorite_etablissement']:
                field_errors['priorite_etablissement'] = "La priorité de l'établissement est obligatoire."
                is_valid = False
            
            # Les champs suivants sont optionnels pour la prospection
            # if not form_data['source_etablissement']:
            #     field_errors['source_etablissement'] = "La source de l'établissement est obligatoire."
            #     is_valid = False
            
            # if not form_data['prochaine_action_etablissement']:
            #     field_errors['prochaine_action_etablissement'] = "La prochaine action de l'établissement est obligatoire."
            #     is_valid = False
            
            # if not form_data['notes_commercial']:
            #     field_errors['notes_commercial'] = "Les notes de la prospection sont obligatoires."
            #     is_valid = False
            
            if is_valid:
                try:
                    prospection = Prospection(
                        nom_etablissement=form_data['nom_etablissement'],
                        type_etablissement=form_data['type_etablissement'],
                        genre_etablissement=form_data['genre_etablissement'],
                        statut_etablissement=form_data['statut_etablissement'],
                        ville_etablissement=form_data['ville_etablissement'],
                        pays_etablissement=form_data['pays_etablissement'],
                        adresse_etablissement=form_data['adresse_etablissement'],
                        potentiel_etablissement=form_data['potentiel_etablissement'],
                        priorite_etablissement=form_data['priorite_etablissement'],
                        source_etablissement=form_data['source_etablissement'] or None,
                        prochaine_action_etablissement=form_data['prochaine_action_etablissement'] or None,
                        notes_commercial=form_data['notes_commercial'] or None,
                        cree_par=request.user if request.user.is_authenticated else None
                    )
                    prospection.save()
                    messages.success(request, "Établissement ajouté avec succès à votre pipeline de prospection !")
                    return redirect('school_admin:commercial_ajouter_etablissement')
                except Exception as e:
                    messages.error(request, f"Erreur lors de la sauvegarde : {str(e)}")
                    return {
                        'field_errors': {'general': 'Erreur lors de la sauvegarde'},
                        'form_data': form_data,
                    }, None
            else:
                return {
                    'field_errors': field_errors,
                    'form_data': form_data,
                }, None
        else:
            # Si ce n'est pas une requête POST, retourner None
            return None
                
        