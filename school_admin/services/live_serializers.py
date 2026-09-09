"""Sérialiseurs JSON pour le temps réel directeur."""
from __future__ import annotations

from django.urls import reverse
from django.utils import timezone


def serialize_matiere_item(matiere, est_superieur=False, est_lycee=False, coefficients_par_groupe=None):
    item = {
        'id': matiere.id,
        'nom': matiere.nom,
        'type_matiere': matiere.type_matiere,
        'type_display': matiere.type_display,
        'niveau_display': matiere.niveau_display,
        'coefficient': float(matiere.coefficient or 0),
        'credits': matiere.credits,
        'nb_classes': matiere.classes.count(),
        'department_nom': matiere.department.nom if matiere.department else '',
        'department_id': matiere.department_id,
        'module_nom': matiere.module.nom if matiere.module else '',
        'est_superieur': est_superieur,
        'est_lycee': est_lycee,
        'coefficients_par_groupe': coefficients_par_groupe or {},
        'detail_url': reverse('matiere:detail_matiere', args=[matiere.id]),
    }
    if est_superieur and matiere.department_id:
        item['dep_id'] = str(matiere.department_id)
    return item


def serialize_periode_item(periode):
    status = 'a-venir'
    if periode.est_en_cours:
        status = 'active'
    elif periode.est_passee:
        status = 'terminee'
    return {
        'id': periode.id,
        'nom_periode': periode.nom_periode,
        'type_periode': periode.type_periode,
        'type_display': periode.get_type_periode_display(),
        'niveau_lmd': periode.niveau_lmd or '',
        'date_debut': periode.date_debut.strftime('%d/%m/%Y'),
        'date_fin': periode.date_fin.strftime('%d/%m/%Y'),
        'date_debut_iso': periode.date_debut.strftime('%Y-%m-%d'),
        'date_fin_iso': periode.date_fin.strftime('%Y-%m-%d'),
        'annee_scolaire': periode.annee_scolaire,
        'est_active': periode.est_active,
        'status_class': status,
        'duree_jours': periode.duree_jours,
        'tab_key': periode.niveau_lmd or 'classic',
    }


def serialize_annee_scolaire_item(annee):
    return {
        'id': annee.id,
        'libelle': annee.libelle,
        'annee_debut': annee.annee_debut,
        'annee_fin': annee.annee_fin,
        'date_debut': annee.date_debut.strftime('%d/%m/%Y') if annee.date_debut else '',
        'date_fin': annee.date_fin.strftime('%d/%m/%Y') if annee.date_fin else '',
        'est_ouverte': annee.est_ouverte,
    }


def serialize_comptabilite_parametres(parametres, etablissement):
    def fmt_amount(value):
        try:
            return str(int(float(value or 0)))
        except (TypeError, ValueError):
            return '0'

    return {
        'montant_frais_inscription': fmt_amount(parametres.montant_frais_inscription),
        'montant_frais_reinscription': fmt_amount(parametres.montant_frais_reinscription),
        'montant_mensualite': fmt_amount(parametres.montant_mensualite),
        'montant_facturation_annuelle': fmt_amount(parametres.montant_facturation_annuelle),
        'type_facturation': parametres.type_facturation,
        'type_facturation_display': parametres.get_type_facturation_display(),
        'autoriser_retards': parametres.autoriser_retards,
        'autoriser_paiements_partiels': parametres.autoriser_paiements_partiels,
        'delai_tolerance_retard': str(parametres.delai_tolerance_retard or 0) + ' jours',
        'type_etablissement_comptabilite': etablissement.type_etablissement_comptabilite,
    }


def serialize_comptabilite_paiement_result(eleve_id, message, snapshot=None):
    item = {
        'eleve_id': eleve_id,
        'message': message,
    }
    if snapshot is not None:
        item['snapshot'] = snapshot
    return item


def _fmt_amount(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _frais_statut_badge(statut):
    if statut == 'paye':
        return 'success'
    if statut == 'en_retard':
        return 'warning'
    return 'info'


def _mensualite_statut_ui(mensualite, montant_paye):
    statut = mensualite.statut
    if statut == 'paye':
        return 'success', mensualite.get_statut_display()
    if statut == 'en_retard':
        return 'warning', mensualite.get_statut_display()
    if statut == 'impaye':
        return 'danger', mensualite.get_statut_display()
    if statut == 'mp':
        if float(montant_paye or 0) == 0:
            return 'danger', 'Impayé'
        return 'warning', 'En retard'
    return 'info', mensualite.get_statut_display()


def _comptabilite_statut_badge(statut):
    if statut == 'a_jour':
        return 'success'
    if statut == 'en_retard':
        return 'warning'
    return 'danger'


def serialize_comptabilite_eleve_snapshot(eleve_id, etablissement, annee_scolaire, devise=None):
    """Snapshot JSON de la page détails comptabilité élève."""
    from decimal import Decimal

    from ..model.comptabilite_eleve_model import (
        ComptabiliteEleve,
        FraisInscription,
        Mensualite,
        PaiementEleve,
    )
    from ..model.inscription_eleve_model import InscriptionEleve

    if devise is None:
        from ..controllers.comptabilite_controller import ComptabiliteController

        devise = ComptabiliteController._get_devise_monnaie(etablissement)

    inscription = InscriptionEleve.objects.select_related('eleve').get(
        eleve_id=eleve_id,
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
    )
    eleve = inscription.eleve
    comptabilite, _ = ComptabiliteEleve.objects.get_or_create(
        eleve=eleve,
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
        defaults={'statut_paiement': 'a_jour'},
    )
    comptabilite.verifier_statut_paiement()

    parametres = None
    if inscription.classe:
        from ..controllers.comptabilite_controller import ComptabiliteController

        parametres = ComptabiliteController._get_parametres_for_classe(etablissement, inscription.classe)

    frais_rows = []
    for frais in FraisInscription.objects.filter(comptabilite_eleve=comptabilite).order_by('-date_creation'):
        montant_paye = Decimal('0.00')
        for paiement in PaiementEleve.objects.filter(
            frais_inscription=frais,
            eleve=eleve,
            annee_scolaire=annee_scolaire,
            type_paiement='frais_inscription',
        ):
            montant_paye += Decimal(str(paiement.montant))
        reste = Decimal(str(frais.montant)) - montant_paye
        if reste < Decimal('0.00'):
            reste = Decimal('0.00')
        frais_rows.append({
            'id': frais.id,
            'type_display': frais.get_type_frais_display(),
            'montant_total': _fmt_amount(frais.montant),
            'montant_paye': _fmt_amount(montant_paye),
            'reste_a_payer': _fmt_amount(reste),
            'date_echeance': frais.date_echeance.strftime('%d/%m/%Y') if frais.date_echeance else '-',
            'statut': frais.statut,
            'statut_display': frais.get_statut_display(),
            'statut_badge': _frais_statut_badge(frais.statut),
            'can_pay': float(reste) > 0,
        })

    mensualite_rows = []
    mensualites = Mensualite.objects.filter(comptabilite_eleve=comptabilite).order_by('annee', 'mois')
    if parametres:
        for mensualite in mensualites:
            mensualite.mettre_a_jour_statut(parametres)
    for mensualite in mensualites:
        montant_paye = Decimal('0.00')
        for paiement in PaiementEleve.objects.filter(
            mensualite=mensualite,
            eleve=eleve,
            annee_scolaire=annee_scolaire,
            type_paiement='mensualite',
        ):
            montant_paye += Decimal(str(paiement.montant))
        reste = Decimal(str(mensualite.montant)) - montant_paye
        if reste < Decimal('0.00'):
            reste = Decimal('0.00')
        badge, label = _mensualite_statut_ui(mensualite, montant_paye)
        mensualite_rows.append({
            'id': mensualite.id,
            'periode': mensualite.periode,
            'montant_total': _fmt_amount(mensualite.montant),
            'montant_paye': _fmt_amount(montant_paye),
            'reste_a_payer': _fmt_amount(reste),
            'date_echeance': mensualite.date_echeance.strftime('%d/%m/%Y') if mensualite.date_echeance else '-',
            'statut': mensualite.statut,
            'statut_display': label,
            'statut_badge': badge,
            'can_pay': float(reste) > 0,
        })

    paiement_rows = []
    for paiement in PaiementEleve.objects.filter(eleve=eleve, annee_scolaire=annee_scolaire).order_by('-date_paiement'):
        paiement_rows.append({
            'id': paiement.id,
            'date_paiement': paiement.date_paiement.strftime('%d/%m/%Y %H:%M'),
            'montant': _fmt_amount(paiement.montant),
            'type_display': paiement.get_type_paiement_display() or '-',
            'methode_display': paiement.get_mode_paiement_display() or '-',
            'reference': paiement.reference_paiement or '-',
        })

    total_du = comptabilite.calculer_total_du()
    total_paye = comptabilite.calculer_total_paye()
    reste_a_payer = total_du - total_paye
    statut = comptabilite.statut_paiement

    return {
        'eleve_id': eleve_id,
        'eleve_nom': f'{eleve.nom} {eleve.prenom}',
        'devise': devise,
        'show_mensualites': etablissement.type_etablissement_comptabilite == 'prive',
        'summary': {
            'total_du': _fmt_amount(total_du),
            'total_paye': _fmt_amount(total_paye),
            'reste_a_payer': _fmt_amount(reste_a_payer),
            'statut_paiement': statut,
            'statut_display': comptabilite.get_statut_paiement_display(),
            'statut_badge': _comptabilite_statut_badge(statut),
            'reste_card_class': 'danger' if float(reste_a_payer) > 0 else 'success',
        },
        'frais': frais_rows,
        'mensualites': mensualite_rows,
        'paiements': paiement_rows,
    }


PERSONNEL_CATEGORY_ICONS = {
    'direction': 'fa-user-tie',
    'censeurs': 'fa-chalkboard-teacher',
    'surveillants': 'fa-eye',
    'administration': 'fa-briefcase',
    'autres': 'fa-users-cog',
}


def serialize_professeur_liste_item(professeur):
    matiere_id = professeur.matiere_principale_id or ''
    return {
        'id': professeur.id,
        'nom_complet': professeur.nom_complet,
        'matiere_display': professeur.matiere_display,
        'niveau_display': professeur.niveau_display,
        'matiere_id': str(matiere_id),
        'email': professeur.email or '',
        'telephone': professeur.telephone or '',
        'actif': professeur.actif,
        'detail_url': reverse('professeur:detail_professeur', args=[professeur.id]),
    }


def serialize_personnel_liste_item(personnel, category_key=None):
    from school_admin.controllers.personnel_controller import PersonnelController

    if not category_key:
        category_key = PersonnelController.get_category_key(personnel.fonction)
    return {
        'id': personnel.id,
        'nom_complet': personnel.nom_complet,
        'fonction_display': personnel.get_fonction_display(),
        'numero_employe': personnel.numero_employe,
        'email': personnel.email or '',
        'telephone': personnel.telephone or '',
        'actif': personnel.actif,
        'category_key': category_key,
        'category_icon': PERSONNEL_CATEGORY_ICONS.get(category_key, 'fa-user-tie'),
        'detail_url': reverse('personnel:detail_personnel', args=[personnel.id]),
        'toggle_url': reverse('personnel:toggle_actif', args=[personnel.id]),
    }


def serialize_emploi_refresh_item(classe_id, emploi_id=None):
    return {
        'classe_id': classe_id,
        'emploi_id': emploi_id,
        'reload': True,
    }


def serialize_affectation_refresh_item(professeur_id, action=None):
    return {
        'professeur_id': professeur_id,
        'action': action or 'update',
        'reload': True,
    }


def serialize_eleve_inscrit_item(eleve, classe, main_tab_id, nombre_absences=0):
    from django.urls import reverse

    matricule = eleve.matricule_eleve or eleve.numero_eleve or ''
    prenom_parts = (eleve.prenom or '').split()
    nom_parts = (eleve.nom or '').split()
    premier_prenom = prenom_parts[0] if prenom_parts else eleve.prenom
    premier_nom = nom_parts[0] if nom_parts else eleve.nom

    return {
        'id': eleve.id,
        'classe_id': classe.id,
        'classe_nom': classe.nom,
        'main_tab_id': main_tab_id,
        'nom_complet': eleve.nom_complet,
        'nom': eleve.nom,
        'prenom': eleve.prenom,
        'premier_nom': premier_nom,
        'premier_prenom': premier_prenom,
        'matricule': matricule,
        'email': eleve.email or '',
        'age': eleve.age,
        'sexe': eleve.sexe,
        'statut': eleve.statut,
        'date_inscription': eleve.date_inscription.strftime('%d/%m/%Y'),
        'nombre_absences': nombre_absences,
        'actif': eleve.actif,
        'detail_url': reverse('secretaire:detail_eleve', args=[eleve.id]),
        'mot_de_passe_provisoire': eleve.mot_de_passe_provisoire or '',
    }


def serialize_evaluation_live_item(evaluation):
    """Sérialise une évaluation pour le temps réel enseignant."""
    from django.urls import reverse
    from django.utils.formats import date_format

    date_str = ''
    if evaluation.date_evaluation:
        date_str = date_format(evaluation.date_evaluation, 'd/m/Y')

    return {
        'id': evaluation.id,
        'titre': evaluation.titre,
        'classe_id': evaluation.classe_id,
        'classe_nom': evaluation.classe.nom if evaluation.classe else '',
        'matiere_id': evaluation.matiere_id,
        'matiere_nom': evaluation.matiere.nom if evaluation.matiere else '',
        'date': date_str,
        'bareme': float(evaluation.bareme) if evaluation.bareme else 20,
        'periode_id': evaluation.periode_scolaire_id,
        'noter_url': reverse('enseignant:noter_eleves', args=[evaluation.classe_id]),
    }


def serialize_sanction_live_item(sanction):
    """Sérialise une sanction pour le temps réel enseignant."""
    return {
        'id': sanction.id,
        'eleve_id': sanction.eleve_id,
        'eleve_nom': sanction.eleve.nom_complet if sanction.eleve else '',
        'classe_id': sanction.classe_id,
        'classe_nom': sanction.classe.nom if sanction.classe else '',
        'type_sanction': sanction.get_type_sanction_display(),
        'gravite': sanction.gravite,
        'date_sanction': sanction.date_sanction.strftime('%d/%m/%Y') if sanction.date_sanction else '',
    }


def serialize_exercice_live_item(exercice):
    """Sérialise un exercice maison pour le temps réel enseignant."""
    return {
        'id': exercice.id,
        'titre': exercice.titre,
        'classe_id': exercice.classe_id if hasattr(exercice, 'classe_id') else None,
        'classe_nom': exercice.classe.nom if getattr(exercice, 'classe', None) else '',
        'date_limite': exercice.date_limite.strftime('%d/%m/%Y') if exercice.date_limite else '',
    }
