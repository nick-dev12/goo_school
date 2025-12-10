import secrets
from django.db import models, transaction
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth.hashers import make_password

from .etablissement_model import Etablissement
from .classe_model import Classe


class LienPreinscription(models.Model):
    """
    Modèle pour stocker les liens de préinscription uniques par établissement
    """
    etablissement = models.OneToOneField(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='lien_preinscription',
        verbose_name="Établissement",
        help_text="Établissement associé à ce lien"
    )
    
    token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        verbose_name="Token unique",
        help_text="Token unique pour le lien de préinscription"
    )
    
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif",
        help_text="Indique si le lien est actif et peut être utilisé"
    )
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
        help_text="Date de création du lien"
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification",
        help_text="Date de dernière modification"
    )
    
    nombre_utilisations = models.IntegerField(
        default=0,
        verbose_name="Nombre d'utilisations",
        help_text="Nombre de fois que le lien a été utilisé"
    )
    
    class Meta:
        verbose_name = "Lien de préinscription"
        verbose_name_plural = "Liens de préinscription"
        ordering = ['-date_creation']
    
    def __str__(self):
        return f"Lien préinscription - {self.etablissement.nom}"
    
    def save(self, *args, **kwargs):
        if not self.token:
            self.token = self.generer_token_unique()
        super().save(*args, **kwargs)
    
    @staticmethod
    def generer_token_unique():
        """Génère un token unique pour le lien"""
        while True:
            token = secrets.token_urlsafe(32)
            if not LienPreinscription.objects.filter(token=token).exists():
                return token
    
    def get_url_absolue(self, request=None):
        """Retourne l'URL absolue du lien de préinscription"""
        if request:
            return request.build_absolute_uri(
                reverse('school_admin:preinscription:formulaire', kwargs={'token': self.token})
            )
        return f"/preinscription/formulaire/{self.token}/"
    
    def incrementer_utilisation(self):
        """Incrémente le compteur d'utilisations"""
        self.nombre_utilisations += 1
        self.save(update_fields=['nombre_utilisations'])


class PreinscriptionEleve(models.Model):
    """
    Modèle pour stocker les préinscriptions d'élèves en attente de validation
    """
    STATUT_CHOICES = [
        ('en_attente', 'En attente de validation'),
        ('validee', 'Validée'),
        ('rejetee', 'Rejetée'),
    ]
    
    # Lien avec l'établissement
    lien_preinscription = models.ForeignKey(
        LienPreinscription,
        on_delete=models.CASCADE,
        related_name='preinscriptions',
        verbose_name="Lien de préinscription",
        help_text="Lien utilisé pour cette préinscription"
    )
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='preinscriptions_eleves',
        verbose_name="Établissement",
        help_text="Établissement concerné"
    )
    
    # Informations personnelles de l'élève
    nom = models.CharField(
        max_length=100,
        verbose_name="Nom de famille",
        help_text="Nom de famille de l'élève"
    )
    
    prenom = models.CharField(
        max_length=100,
        verbose_name="Prénom",
        help_text="Prénom de l'élève"
    )
    
    date_naissance = models.DateField(
        verbose_name="Date de naissance",
        help_text="Date de naissance de l'élève"
    )
    
    lieu_naissance = models.CharField(
        max_length=100,
        verbose_name="Lieu de naissance",
        help_text="Lieu de naissance de l'élève"
    )
    
    SEXE_CHOICES = [
        ('M', 'Masculin'),
        ('F', 'Féminin'),
    ]
    sexe = models.CharField(
        max_length=1,
        choices=SEXE_CHOICES,
        verbose_name="Sexe",
        help_text="Sexe de l'élève"
    )
    
    nationalite = models.CharField(
        max_length=100,
        verbose_name="Nationalité",
        help_text="Nationalité de l'élève"
    )
    
    adresse = models.TextField(
        blank=True,
        null=True,
        verbose_name="Adresse",
        help_text="Adresse de résidence de l'élève"
    )
    
    # Informations scolaires
    classe_souhaitee = models.ForeignKey(
        Classe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='preinscriptions',
        verbose_name="Classe souhaitée",
        help_text="Classe souhaitée pour l'inscription"
    )
    
    statut_inscription = models.CharField(
        max_length=20,
        choices=[
            ('nouvelle', 'Nouvelle inscription'),
            ('reinscription', 'Réinscription'),
        ],
        default='nouvelle',
        verbose_name="Type d'inscription",
        help_text="Type d'inscription"
    )
    
    # Informations parent/tuteur
    parent_nom = models.CharField(
        max_length=100,
        verbose_name="Nom du parent/tuteur",
        help_text="Nom de famille du parent ou tuteur"
    )
    
    parent_prenom = models.CharField(
        max_length=100,
        verbose_name="Prénom du parent/tuteur",
        help_text="Prénom du parent ou tuteur"
    )
    
    parent_telephone = models.CharField(
        max_length=20,
        verbose_name="Téléphone du parent/tuteur",
        help_text="Numéro de téléphone du parent ou tuteur"
    )
    
    parent_adresse = models.TextField(
        blank=True,
        null=True,
        verbose_name="Adresse du parent/tuteur",
        help_text="Adresse du parent ou tuteur"
    )
    
    parent_profession = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Profession du parent/tuteur",
        help_text="Profession du parent ou tuteur"
    )
    
    parent_lien = models.CharField(
        max_length=50,
        choices=[
            ('pere', 'Père'),
            ('mere', 'Mère'),
            ('grand_parent', 'Grand-parent'),
            ('oncle_tante', 'Oncle/Tante'),
            ('frere_soeur', 'Frère/Sœur'),
            ('autre_famille', 'Autre membre de la famille'),
            ('tuteur_legal', 'Tuteur légal'),
            ('autre', 'Autre'),
        ],
        verbose_name="Lien avec l'élève",
        help_text="Lien de parenté ou relation avec l'élève"
    )
    
    # Statut de la préinscription
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='en_attente',
        verbose_name="Statut",
        help_text="Statut de la préinscription"
    )
    
    # Commentaires et notes
    commentaires_parent = models.TextField(
        blank=True,
        null=True,
        verbose_name="Commentaires du parent",
        help_text="Commentaires ou informations supplémentaires fournis par le parent"
    )
    
    commentaires_etablissement = models.TextField(
        blank=True,
        null=True,
        verbose_name="Commentaires de l'établissement",
        help_text="Commentaires ou notes de l'établissement lors de la validation"
    )
    
    # Dates
    date_soumission = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de soumission",
        help_text="Date à laquelle la préinscription a été soumise"
    )
    
    date_validation = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Date de validation",
        help_text="Date à laquelle la préinscription a été validée ou rejetée"
    )
    
    valide_par = models.ForeignKey(
        Etablissement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='preinscriptions_validees',
        verbose_name="Validé par",
        help_text="Directeur ayant validé la préinscription"
    )
    
    class Meta:
        verbose_name = "Préinscription d'élève"
        verbose_name_plural = "Préinscriptions d'élèves"
        ordering = ['-date_soumission']
    
    def __str__(self):
        return f"Préinscription - {self.prenom} {self.nom} ({self.etablissement.nom})"
    
    def valider(self, validateur, commentaires=None, documents=None):
        """
        Valide la préinscription et crée automatiquement :
        - L'élève dans la table Eleve
        - Le parent dans la table Parent (s'il n'existe pas)
        - L'inscription dans InscriptionEleve avec l'année scolaire active
        - L'inscription dans InscriptionParent avec l'année scolaire active
        
        Args:
            validateur: L'établissement qui valide la préinscription
            commentaires: Commentaires optionnels
            documents: Dictionnaire des documents fournis (optionnel)
        """
        from .eleve_model import Eleve
        from .parent_model import Parent
        from .inscription_eleve_model import InscriptionEleve
        from .inscription_parent_model import InscriptionParent
        from .lien_familial_model import LienFamilial
        from .annee_scolaire_model import AnneeScolaire
        
        # Récupérer l'année scolaire active
        annee_scolaire_active = AnneeScolaire.get_session_active(self.etablissement)
        if not annee_scolaire_active:
            raise ValueError("Aucune année scolaire active trouvée pour cet établissement. Veuillez créer ou activer une année scolaire.")
        
        with transaction.atomic():
            # 1. Créer ou récupérer le parent
            parent = None
            try:
                # Chercher un parent existant par téléphone
                parent = Parent.objects.filter(
                    telephone=self.parent_telephone,
                    etablissement=self.etablissement
                ).first()
                
                if not parent:
                    # Créer un nouveau parent
                    matricule_parent = Parent.generer_matricule_parent(self.etablissement)
                    mot_de_passe_parent = Parent.generer_mot_de_passe()
                    
                    # Déterminer le type de parent basé sur parent_lien
                    type_parent_map = {
                        'pere': 'pere',
                        'mere': 'mere',
                        'tuteur_legal': 'tuteur',
                        'autre': 'tuteur',
                        'grand_parent': 'tuteur',
                        'oncle_tante': 'tuteur',
                        'frere_soeur': 'tuteur',
                        'autre_famille': 'tuteur',
                    }
                    type_parent = type_parent_map.get(self.parent_lien, 'tuteur')
                    
                    # Formater les noms et prénoms du parent
                    from ..utils.formatting_utils import formater_nom, formater_prenom
                    parent_nom_formate = formater_nom(self.nom_parent)
                    parent_prenom_formate = formater_prenom(self.prenom_parent)
                    
                    parent = Parent.objects.create(
                        username=matricule_parent,
                        matricule_parental=matricule_parent,
                        nom=parent_nom_formate,
                        prenom=parent_prenom_formate,
                        telephone=self.parent_telephone,
                        type_parent=type_parent,
                        adresse=self.parent_adresse or '',
                        profession=self.parent_profession or '',
                        etablissement=self.etablissement,
                        mot_de_passe_provisoire=mot_de_passe_parent,
                        mot_de_passe_modifie=False,
                        email='',  # Email optionnel
                        password=make_password(mot_de_passe_parent),
                        is_active=True,
                    )
                    
                    # Générer le token QR pour le parent si nécessaire (normalement généré automatiquement par save())
                    if not parent.qr_auth_token:
                        parent.generer_et_sauvegarder_token_qr()
            except Exception as e:
                raise ValueError(f"Erreur lors de la création du parent : {str(e)}")
            
            # 2. Créer l'élève
            try:
                # Générer le matricule et mot de passe de l'élève
                matricule_eleve = Eleve.generer_matricule_eleve(self.etablissement)
                mot_de_passe_eleve = Eleve.generer_mot_de_passe()
                
                # Le statut d'inscription est toujours "nouvelle" pour les préinscriptions
                statut_inscription = 'nouvelle'
                
                # Formater les noms et prénoms
                from ..utils.formatting_utils import formater_nom, formater_prenom
                nom_formate = formater_nom(self.nom_eleve)
                prenom_formate = formater_prenom(self.prenom_eleve)
                parent_nom_formate = formater_nom(self.nom_parent)
                parent_prenom_formate = formater_prenom(self.prenom_parent)
                
                # Créer l'élève
                eleve = Eleve.objects.create(
                    username=matricule_eleve,
                    matricule_eleve=matricule_eleve,
                    numero_eleve=matricule_eleve,  # Assigner numero_eleve avec le matricule
                    nom=nom_formate,
                    prenom=prenom_formate,
                    date_naissance=self.date_naissance,
                    lieu_naissance=self.lieu_naissance,
                    sexe=self.sexe,
                    nationalite=self.nationalite,
                    adresse=self.adresse or None,
                    telephone=None,  # Pas de téléphone pour l'élève dans la préinscription
                    etablissement=self.etablissement,
                    classe=self.classe_souhaitee,
                    date_inscription=timezone.now().date(),
                    statut=statut_inscription,
                    parent_nom=parent_nom_formate,
                    parent_prenom=parent_prenom_formate,
                    parent_telephone=self.parent_telephone,
                    parent_email=None,  # Pas d'email parent dans la préinscription
                    parent_adresse=self.parent_adresse or None,
                    parent_profession=self.parent_profession or None,
                    parent_lien=self.parent_lien,
                    mot_de_passe_provisoire=mot_de_passe_eleve,
                    password=make_password(mot_de_passe_eleve),
                    is_active=True,
                    actif=True,
                )
                
                # Générer le token QR pour l'élève si nécessaire (normalement généré automatiquement par save())
                if not eleve.qr_auth_token:
                    eleve.generer_et_sauvegarder_token_qr()
            except Exception as e:
                raise ValueError(f"Erreur lors de la création de l'élève : {str(e)}")
            
            # 3. Créer le lien familial entre le parent et l'élève
            try:
                # Mapper parent_lien vers type_lien pour LienFamilial
                type_lien_map = {
                    'pere': 'pere',
                    'mere': 'mere',
                    'tuteur_legal': 'tuteur',
                    'autre': 'tuteur',
                    'grand_parent': 'tuteur',
                    'oncle_tante': 'tuteur',
                    'frere_soeur': 'tuteur',
                    'autre_famille': 'tuteur',
                }
                type_lien = type_lien_map.get(self.parent_lien, 'tuteur')
                
                LienFamilial.objects.get_or_create(
                    parent=parent,
                    eleve=eleve,
                    defaults={
                        'type_lien': type_lien,
                        'est_inscripteur': True,  # Le parent qui a fait la préinscription est l'inscripteur
                        'actif': True,
                        'statut': 'valide',
                    }
                )
            except Exception as e:
                # Ne pas bloquer si le lien existe déjà
                pass
            
            # 4. Créer l'inscription élève dans InscriptionEleve
            try:
                # Préparer les valeurs des documents (utiliser ceux fournis ou False par défaut)
                documents_data = documents if documents else {}
                InscriptionEleve.objects.update_or_create(
                    annee_scolaire=annee_scolaire_active,
                    matricule_eleve=eleve.matricule_eleve,
                    defaults={
                        'eleve': eleve,
                        'nom': eleve.nom,
                        'prenom': eleve.prenom,
                        'date_naissance': eleve.date_naissance,
                        'lieu_naissance': eleve.lieu_naissance,
                        'sexe': eleve.sexe,
                        'nationalite': eleve.nationalite,
                        'adresse': eleve.adresse,
                        'telephone': eleve.telephone,
                        'email': eleve.email,
                        'numero_eleve': eleve.numero_eleve,
                        'etablissement': self.etablissement,
                        'classe': eleve.classe,
                        'date_inscription': eleve.date_inscription,
                        'statut': eleve.statut,
                        'parent_nom': eleve.parent_nom,
                        'parent_prenom': eleve.parent_prenom,
                        'parent_telephone': eleve.parent_telephone,
                        'parent_email': eleve.parent_email,
                        'parent_adresse': eleve.parent_adresse,
                        'parent_profession': eleve.parent_profession,
                        'parent_lien': eleve.parent_lien,
                        # Documents : utiliser ceux fournis ou False par défaut
                        'document_acte_naissance': documents_data.get('document_acte_naissance', False),
                        'document_cni': documents_data.get('document_cni', False),
                        'document_passeport': documents_data.get('document_passeport', False),
                        'document_bulletin_precedent': documents_data.get('document_bulletin_precedent', False),
                        'document_certificat_scolarite': documents_data.get('document_certificat_scolarite', False),
                        'document_livret_scolaire': documents_data.get('document_livret_scolaire', False),
                        'document_certificat_medical': documents_data.get('document_certificat_medical', False),
                        'document_carnet_vaccination': documents_data.get('document_carnet_vaccination', False),
                        'document_assurance_maladie': documents_data.get('document_assurance_maladie', False),
                        'document_justificatif_domicile': documents_data.get('document_justificatif_domicile', False),
                        'document_photo_identite': documents_data.get('document_photo_identite', False),
                        'document_autorisation_parentale': documents_data.get('document_autorisation_parentale', False),
                    }
                )
                
                # Mettre à jour aussi les documents dans l'objet Eleve
                eleve.document_acte_naissance = documents_data.get('document_acte_naissance', False)
                eleve.document_cni = documents_data.get('document_cni', False)
                eleve.document_passeport = documents_data.get('document_passeport', False)
                eleve.document_bulletin_precedent = documents_data.get('document_bulletin_precedent', False)
                eleve.document_certificat_scolarite = documents_data.get('document_certificat_scolarite', False)
                eleve.document_livret_scolaire = documents_data.get('document_livret_scolaire', False)
                eleve.document_certificat_medical = documents_data.get('document_certificat_medical', False)
                eleve.document_carnet_vaccination = documents_data.get('document_carnet_vaccination', False)
                eleve.document_assurance_maladie = documents_data.get('document_assurance_maladie', False)
                eleve.document_justificatif_domicile = documents_data.get('document_justificatif_domicile', False)
                eleve.document_photo_identite = documents_data.get('document_photo_identite', False)
                eleve.document_autorisation_parentale = documents_data.get('document_autorisation_parentale', False)
                eleve.save(update_fields=[
                    'document_acte_naissance', 'document_cni', 'document_passeport',
                    'document_bulletin_precedent', 'document_certificat_scolarite', 'document_livret_scolaire',
                    'document_certificat_medical', 'document_carnet_vaccination', 'document_assurance_maladie',
                    'document_justificatif_domicile', 'document_photo_identite', 'document_autorisation_parentale'
                ])
            except Exception as e:
                raise ValueError(f"Erreur lors de la création de l'inscription élève : {str(e)}")
            
            # 5. Créer l'inscription parent dans InscriptionParent
            try:
                type_parent = parent.type_parent if parent.type_parent in ['mere', 'pere', 'tuteur'] else 'tuteur'
                InscriptionParent.objects.update_or_create(
                    annee_scolaire=annee_scolaire_active,
                    matricule_parental=parent.matricule_parental,
                    defaults={
                        'parent': parent,
                        'nom': parent.nom,
                        'prenom': parent.prenom,
                        'telephone': parent.telephone,
                        'email': parent.email,
                        'type_parent': type_parent,
                        'adresse': parent.adresse,
                        'profession': parent.profession,
                        'etablissement': self.etablissement,
                        'date_inscription': eleve.date_inscription,
                    }
                )
            except Exception as e:
                raise ValueError(f"Erreur lors de la création de l'inscription parent : {str(e)}")
            
            # 6. Mettre à jour le statut de la préinscription
            self.statut = 'validee'
            self.date_validation = timezone.now()
            self.valide_par = validateur
            if commentaires:
                self.commentaires_etablissement = commentaires
            self.save()
            
            # Retourner l'élève et le parent créés (pour redirection vers le reçu)
            return eleve, parent
    
    def rejeter(self, validateur, commentaires=None):
        """Rejette la préinscription"""
        self.statut = 'rejetee'
        self.date_validation = timezone.now()
        self.valide_par = validateur
        if commentaires:
            self.commentaires_etablissement = commentaires
        self.save()

