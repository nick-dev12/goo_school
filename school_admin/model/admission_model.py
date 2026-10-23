"""
Admissions du supérieur : campagnes (sur dossier ou concours), épreuves, candidatures d'étudiants,
notes, classement ; diplômes délivrés.
"""
import secrets

from django.db import models

from .classe_model import Classe
from .eleve_model import Eleve
from .etablissement_model import Etablissement


def _jeton():
    return secrets.token_urlsafe(16)


class Concours(models.Model):
    MODE_CHOICES = [('dossier', 'Sur dossier'), ('concours', 'Concours (épreuves écrites / orales)'),
                    ('mixte', 'Dossier + épreuves')]
    STATUT_CHOICES = [('ouvert', 'Candidatures ouvertes'), ('clos', 'Candidatures closes'),
                      ('publie', 'Résultats publiés')]

    etablissement = models.ForeignKey(Etablissement, on_delete=models.CASCADE, related_name='concours')
    annee_scolaire = models.ForeignKey('AnneeScolaire', on_delete=models.CASCADE, related_name='concours')
    intitule = models.CharField(max_length=160, verbose_name="Intitulé")
    classe_cible = models.ForeignKey(Classe, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='concours', verbose_name="Classe d'admission")
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='dossier')
    places = models.PositiveIntegerField(default=30, verbose_name="Places (liste principale)")
    places_attente = models.PositiveIntegerField(default=10, verbose_name="Places en liste d'attente")
    seuil_admission = models.DecimalField(max_digits=4, decimal_places=2, default=10,
                                          verbose_name="Note minimale d'admission (/20)")
    poids_dossier = models.PositiveSmallIntegerField(
        default=100, verbose_name="Poids du dossier (%)",
        help_text="Dossier = moyenne du bac ou du diplôme précédent. Mode mixte : le reste vient des épreuves.",
    )
    date_limite = models.DateField(null=True, blank=True, verbose_name="Date limite de candidature")
    date_epreuves = models.DateField(null=True, blank=True, verbose_name="Date des épreuves")
    diplome_requis = models.CharField(max_length=20, default='bac',
                                      choices=[('bac', 'Baccalauréat'), ('licence', 'Licence (ou équivalent)'),
                                               ('master', 'Master'), ('aucun', 'Aucun')])
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES, default='ouvert')
    jeton = models.CharField(max_length=40, unique=True, default=_jeton)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Campagne d'admission"
        verbose_name_plural = "Campagnes d'admission"
        ordering = ['-date_creation']

    def __str__(self):
        return self.intitule


class EpreuveConcours(models.Model):
    concours = models.ForeignKey(Concours, on_delete=models.CASCADE, related_name='epreuves')
    nom = models.CharField(max_length=120)
    coefficient = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    note_eliminatoire = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'id']

    def __str__(self):
        return f"{self.nom} (coef. {self.coefficient})"


class Candidature(models.Model):
    STATUT_CHOICES = [
        ('soumise', 'Soumise'), ('recevable', 'Dossier recevable'), ('irrecevable', 'Dossier irrecevable'),
        ('admis', 'Admis'), ('attente', "Liste d'attente"), ('refuse', 'Non admis'),
        ('desiste', 'Désisté'), ('inscrit', 'Inscrit'),
    ]
    SERIES_BAC = [('S1', 'S1'), ('S2', 'S2'), ('S3', 'S3'), ('S4', 'S4'), ('S5', 'S5'), ('L1', 'L1'), ('L2', 'L2'),
                  ("L'1", "L'1"), ('G', 'G'), ('T1', 'T1'), ('T2', 'T2'), ('STEG', 'STEG'), ('AUTRE', 'Autre')]
    MENTIONS = [('passable', 'Passable'), ('assez_bien', 'Assez bien'), ('bien', 'Bien'),
                ('tres_bien', 'Très bien'), ('', '—')]
    PIECES = [('bac', 'Attestation / relevé du bac'), ('releves', 'Relevés de notes'),
              ('naissance', 'Extrait de naissance'), ('identite', "Pièce d'identité"), ('photo', 'Photos'),
              ('diplome', 'Diplôme précédent'), ('motivation', 'Lettre de motivation')]

    concours = models.ForeignKey(Concours, on_delete=models.CASCADE, related_name='candidatures')
    numero = models.CharField(max_length=30, blank=True, verbose_name="N° de candidature")
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    sexe = models.CharField(max_length=1, choices=[('M', 'Masculin'), ('F', 'Féminin')])
    date_naissance = models.DateField()
    lieu_naissance = models.CharField(max_length=120)
    nationalite = models.CharField(max_length=60, default='Sénégalaise')
    telephone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    adresse = models.CharField(max_length=200, blank=True)
    # Personne à contacter (responsable dans le dossier d'inscription)
    contact_nom = models.CharField(max_length=100, blank=True, verbose_name="Personne à contacter — nom")
    contact_prenom = models.CharField(max_length=100, blank=True, verbose_name="Personne à contacter — prénom")
    contact_telephone = models.CharField(max_length=30, blank=True, verbose_name="Personne à contacter — téléphone")
    contact_lien = models.CharField(max_length=30, default='pere', choices=[
        ('pere', 'Père'), ('mere', 'Mère'), ('tuteur_legal', 'Tuteur légal'), ('frere_soeur', 'Frère/Sœur'),
        ('oncle_tante', 'Oncle/Tante'), ('autre_famille', 'Autre membre de la famille'), ('autre', 'Autre')])
    serie_bac = models.CharField(max_length=10, choices=SERIES_BAC, blank=True)
    annee_bac = models.PositiveSmallIntegerField(null=True, blank=True)
    mention_bac = models.CharField(max_length=12, choices=MENTIONS, blank=True)
    numero_table = models.CharField(max_length=30, blank=True, verbose_name="N° de table du bac")
    moyenne_bac = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    diplome_precedent = models.CharField(max_length=160, blank=True, verbose_name="Diplôme précédent")
    etablissement_precedent = models.CharField(max_length=160, blank=True)
    annee_diplome = models.PositiveSmallIntegerField(null=True, blank=True)
    moyenne_diplome = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    pieces = models.JSONField(default=list, blank=True, verbose_name="Pièces fournies")
    statut = models.CharField(max_length=12, choices=STATUT_CHOICES, default='soumise')
    motif = models.CharField(max_length=255, blank=True, verbose_name="Motif (irrecevabilité, refus…)")
    note_dossier = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    total = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    rang = models.PositiveIntegerField(null=True, blank=True)
    eleve = models.ForeignKey(Eleve, on_delete=models.SET_NULL, null=True, blank=True, related_name='candidatures')
    en_ligne = models.BooleanField(default=False, verbose_name="Déposée en ligne")
    date_depot = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Candidature'
        verbose_name_plural = 'Candidatures'
        ordering = ['rang', 'nom', 'prenom']

    def __str__(self):
        return f"{self.numero} — {self.prenom} {self.nom}"

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom.upper()}"


class NoteConcours(models.Model):
    candidature = models.ForeignKey(Candidature, on_delete=models.CASCADE, related_name='notes')
    epreuve = models.ForeignKey(EpreuveConcours, on_delete=models.CASCADE, related_name='notes')
    note = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    absent = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['candidature', 'epreuve'], name='note_concours_unique')]


class Diplome(models.Model):
    eleve = models.ForeignKey(Eleve, on_delete=models.CASCADE, related_name='diplomes')
    etablissement = models.ForeignKey(Etablissement, on_delete=models.CASCADE, related_name='diplomes')
    annee_scolaire = models.ForeignKey('AnneeScolaire', on_delete=models.SET_NULL, null=True, blank=True)
    classe = models.ForeignKey(Classe, on_delete=models.SET_NULL, null=True, blank=True)
    intitule = models.CharField(max_length=200, verbose_name="Intitulé du diplôme")
    grade = models.CharField(max_length=40, blank=True)
    domaine = models.CharField(max_length=160, blank=True)
    mention = models.CharField(max_length=30, blank=True)
    moyenne = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    credits = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    numero = models.CharField(max_length=40, unique=True)
    date_delivrance = models.DateField()
    annule = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Diplôme délivré'
        verbose_name_plural = 'Diplômes délivrés'
        ordering = ['-date_delivrance']

    def __str__(self):
        return f"{self.numero} — {self.intitule} — {self.eleve}"
