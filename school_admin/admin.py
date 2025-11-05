from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CompteUser, Parent, LienFamilial, DemandeLiaisonParent
from .model.session_examen_model import SessionExamen
from .model.creneau_examen_model import CreneauExamen
from .model.note_examen_model import NoteExamen
from .model.convocation_model import Convocation

class CompteUserAdmin(UserAdmin):
    list_display = ('email', 'nom', 'prenom', 'type_compte', 'departement', 'is_active')
    list_filter = ('type_compte', 'departement', 'is_active')
    search_fields = ('email', 'nom', 'prenom')
    ordering = ('email',)  # Utiliser email au lieu de username
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Informations personnelles', {'fields': ('nom', 'prenom', 'telephone', 'date_naissance', 'photo')}),
        ('Informations professionnelles', {'fields': ('type_compte', 'fonction', 'departement')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates importantes', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'nom', 'prenom', 'password1', 'password2'),
        }),
    )

class SessionExamenAdmin(admin.ModelAdmin):
    list_display = ('nom_examen', 'matieres_liste', 'classes_str', 'date_debut', 'date_fin', 'periode', 'nombre_matieres', 'nombre_classes', 'est_publie', 'est_annule', 'actif')
    list_filter = ('periode', 'est_publie', 'est_annule', 'actif')
    search_fields = ('nom_examen', 'matieres__nom', 'classes__nom')
    filter_horizontal = ('classes', 'matieres')
    date_hierarchy = 'date_debut'
    ordering = ('-date_creation',)
    
    fieldsets = (
        ('Informations de base', {
            'fields': ('nom_examen', 'etablissement', 'periode')
        }),
        ('Classes et matières concernées', {
            'fields': ('classes', 'matieres')
        }),
        ('Période de la session', {
            'fields': ('date_debut', 'date_fin', 'duree_totale')
        }),
        ('Informations complémentaires', {
            'fields': ('description',)
        }),
        ('Statut', {
            'fields': ('est_publie', 'est_annule', 'actif')
        }),
    )
    
    readonly_fields = ('duree_totale', 'date_creation', 'date_modification')

class CreneauExamenAdmin(admin.ModelAdmin):
    list_display = ('session_examen', 'matiere', 'date_examen', 'heure_debut', 'heure_fin', 'surveillant', 'salle', 'est_confirme', 'est_annule', 'actif')
    list_filter = ('session_examen__periode', 'matiere', 'date_examen', 'est_confirme', 'est_annule', 'actif')
    search_fields = ('session_examen__nom_examen', 'matiere__nom', 'surveillant__nom', 'surveillant__prenom')
    date_hierarchy = 'date_examen'
    ordering = ('-date_examen', 'heure_debut')
    
    fieldsets = (
        ('Session d\'examen', {
            'fields': ('session_examen', 'matiere')
        }),
        ('Date et horaires', {
            'fields': ('date_examen', 'heure_debut', 'heure_fin', 'duree_estimee')
        }),
        ('Surveillance et salle', {
            'fields': ('surveillant', 'salle')
        }),
        ('Informations complémentaires', {
            'fields': ('consignes_specifiques',)
        }),
        ('Statut', {
            'fields': ('est_confirme', 'est_annule', 'actif')
        }),
    )
    
    readonly_fields = ('duree_estimee', 'date_creation', 'date_modification')

admin.site.register(CompteUser, CompteUserAdmin)
admin.site.register(SessionExamen, SessionExamenAdmin)
admin.site.register(CreneauExamen, CreneauExamenAdmin)


# Admin pour NoteExamen
class NoteExamenAdmin(admin.ModelAdmin):
    list_display = ('eleve', 'matiere', 'session_examen', 'classe', 'note_sur_20', 'absent', 'professeur', 'date_saisie')
    list_filter = ('session_examen', 'matiere', 'classe', 'absent', 'actif')
    search_fields = ('eleve__nom', 'eleve__prenom', 'matiere__nom', 'session_examen__nom_examen')
    readonly_fields = ('note_sur_20', 'date_saisie', 'date_modification')
    
    fieldsets = (
        ('Informations principales', {
            'fields': ('eleve', 'session_examen', 'creneau_examen', 'matiere', 'professeur', 'classe')
        }),
        ('Note', {
            'fields': ('note', 'bareme', 'note_sur_20', 'absent', 'commentaire')
        }),
        ('Métadonnées', {
            'fields': ('date_saisie', 'date_modification', 'actif'),
            'classes': ('collapse',)
        }),
    )

class ConvocationAdmin(admin.ModelAdmin):
    list_display = ('eleve', 'objet', 'date_convocation', 'heure_convocation', 'lieu', 'statut', 'actif')
    list_filter = ('statut', 'actif', 'date_convocation', 'etablissement')
    search_fields = ('eleve__nom', 'eleve__prenom', 'objet', 'motif')
    date_hierarchy = 'date_convocation'
    ordering = ('-date_convocation', '-heure_convocation')
    
    fieldsets = (
        ('Élève concerné', {
            'fields': ('eleve', 'etablissement')
        }),
        ('Informations de la convocation', {
            'fields': ('objet', 'motif', 'date_convocation', 'heure_convocation', 'lieu')
        }),
        ('Statut', {
            'fields': ('statut', 'actif')
        }),
        ('Métadonnées', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('date_creation', 'date_modification')

admin.site.register(NoteExamen, NoteExamenAdmin)
admin.site.register(Convocation, ConvocationAdmin)


# Admin pour Parent
class ParentAdmin(admin.ModelAdmin):
    list_display = ('matricule_parental', 'nom', 'prenom', 'type_parent', 'telephone', 'email', 'etablissement', 'nombre_enfants', 'actif')
    list_filter = ('type_parent', 'etablissement', 'actif', 'mot_de_passe_modifie')
    search_fields = ('matricule_parental', 'nom', 'prenom', 'email', 'telephone')
    ordering = ('-date_creation',)
    
    fieldsets = (
        ('Informations d\'identification', {
            'fields': ('matricule_parental', 'mot_de_passe_provisoire', 'mot_de_passe_modifie')
        }),
        ('Informations personnelles', {
            'fields': ('nom', 'prenom', 'type_parent', 'telephone', 'email', 'adresse', 'profession')
        }),
        ('Établissement', {
            'fields': ('etablissement',)
        }),
        ('Statut', {
            'fields': ('actif', 'is_active')
        }),
        ('Métadonnées', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('date_creation', 'date_modification')


# Admin pour LienFamilial
class LienFamilialAdmin(admin.ModelAdmin):
    list_display = ('parent', 'eleve', 'type_lien', 'statut', 'est_inscripteur', 'actif', 'date_creation')
    list_filter = ('type_lien', 'statut', 'est_inscripteur', 'actif')
    search_fields = ('parent__nom', 'parent__prenom', 'parent__matricule_parental', 
                    'eleve__nom', 'eleve__prenom', 'eleve__matricule_eleve')
    ordering = ('-date_creation',)
    
    fieldsets = (
        ('Relation familiale', {
            'fields': ('parent', 'eleve', 'type_lien')
        }),
        ('Statut du lien', {
            'fields': ('statut', 'est_inscripteur', 'actif', 'date_validation')
        }),
        ('Métadonnées', {
            'fields': ('date_creation',),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('date_creation', 'date_validation')


admin.site.register(Parent, ParentAdmin)
admin.site.register(LienFamilial, LienFamilialAdmin)


class DemandeLiaisonParentAdmin(admin.ModelAdmin):
    list_display = ('parent_demandeur', 'matricule_eleve', 'nom_eleve', 'prenom_eleve', 
                    'classe_eleve', 'type_lien', 'statut', 'nombre_tentatives', 'date_demande')
    list_filter = ('statut', 'type_lien', 'nombre_tentatives', 'date_demande')
    search_fields = ('parent_demandeur__nom', 'parent_demandeur__prenom', 'matricule_eleve', 
                    'nom_eleve', 'prenom_eleve', 'nom_parent_inscripteur')
    ordering = ('-date_demande',)
    
    fieldsets = (
        ('Informations du parent', {
            'fields': ('parent_demandeur',)
        }),
        ('Informations de l\'élève', {
            'fields': ('matricule_eleve', 'nom_eleve', 'prenom_eleve', 'date_naissance_eleve', 
                      'classe_eleve', 'eleve_valide')
        }),
        ('Informations de vérification', {
            'fields': ('nom_parent_inscripteur', 'type_lien')
        }),
        ('Statut de la demande', {
            'fields': ('statut', 'nombre_tentatives', 'raison_echec')
        }),
        ('Dates', {
            'fields': ('date_demande', 'date_traitement'),
            'classes': ('collapse',)
        }),
        ('Traitement administratif', {
            'fields': ('traite_par', 'motif_refus', 'message'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('date_demande',)
    
    def has_add_permission(self, request):
        # Empêcher la création manuelle de demandes depuis l'admin
        return False


admin.site.register(DemandeLiaisonParent, DemandeLiaisonParentAdmin)