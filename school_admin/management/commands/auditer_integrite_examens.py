"""Inventaire en lecture seule, sans annulation ni correction automatique."""
import json
from django.core.management.base import BaseCommand
from school_admin.model.deliberation_model import Deliberation
from school_admin.model.session_examen_model import SessionExamen
from school_admin.model.module_model import ModuleClasse
from school_admin.model.admission_model import Diplome
from school_admin.services.deliberations import controle_resultats, periodes_de

class Command(BaseCommand):
    help = 'Inventorie les dossiers examens/jury suspects, sans ecriture.'

    def add_arguments(self, parser):
        parser.add_argument('--etablissement', type=int, required=True)

    def handle(self, *args, **options):
        etab = options['etablissement']
        anomalies = []
        for d in Deliberation.objects.filter(etablissement_id=etab).select_related('classe','annee_scolaire','periode'):
            controle = controle_resultats(d.classe,periodes_de(d),d.annee_scolaire)
            decisions = d.decisions.filter(decision__in=['admis','admis_compensation','admis_conditionnel'])
            if decisions.filter(credits_total__lte=0).exists():
                anomalies.append({'type':'decision_sans_credits','deliberation_id':d.pk})
            if not controle['pret']:
                anomalies.append({'type':'resultats_a_verifier','deliberation_id':d.pk,
                                  'problemes':controle['problemes']})
        for session in SessionExamen.objects.filter(etablissement_id=etab).select_related('periode'):
            classes = list(session.classes.all())
            for classe in classes:
                if (session.periode.niveau_lmd and classe.niveau_lmd != session.periode.niveau_lmd):
                    anomalies.append({'type':'niveau_incompatible','session_id':session.pk,'classe_id':classe.pk})
                for matiere in session.matieres.filter(classes=classe).distinct():
                    if matiere.module_id and not ModuleClasse.objects.filter(classe=classe,module=matiere.module,
                                                                            periode=session.periode).exists():
                        anomalies.append({'type':'matiere_semestre_incompatible','session_id':session.pk,
                                          'classe_id':classe.pk,'matiere_id':matiere.pk})
        self.stdout.write(json.dumps({'etablissement_id':etab,'anomalies':anomalies,
            'attestations_actives_a_examiner':list(Diplome.objects.filter(etablissement_id=etab,annule=False)
                                                  .values_list('pk',flat=True)),
            'note':'Aucune correction automatique ; une ancienne empreinte absente ne prouve pas une decision erronnee.'},
            ensure_ascii=False,default=str,indent=2))
