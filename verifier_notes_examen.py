import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from school_admin.model.note_examen_model import NoteExamen
from school_admin.model.session_examen_model import SessionExamen
from school_admin.model.classe_model import Classe
from school_admin.model.eleve_model import Eleve
from school_admin.model.matiere_model import Matiere

# Récupérer la session et les données
session = SessionExamen.objects.filter(nom_examen__contains='Mathematiques').first()
classe = Classe.objects.get(id=78)
matiere = Matiere.objects.filter(nom__contains='Mathematiques').first()

print("=" * 80)
print("VERIFICATION DU SYSTEME DE NOTATION D'EXAMENS")
print("=" * 80)

if session:
    print(f"\nSession trouvee: {session.nom_examen}")
    print(f"  - Periode: {session.periode.nom_periode}")
    print(f"  - Dates: {session.date_debut} -> {session.date_fin}")
    print(f"  - Classes: {session.nombre_classes}")
    print(f"  - Matieres: {session.nombre_matieres}")
    
    # Vérifier les notes d'examen
    notes_examen = NoteExamen.objects.filter(
        session_examen=session,
        matiere=matiere,
        classe=classe,
        actif=True
    ).order_by('eleve__nom')
    
    print(f"\n{'=' * 80}")
    print(f"NOTES D'EXAMEN ENREGISTREES : {notes_examen.count()} note(s)")
    print(f"{'=' * 80}")
    
    if notes_examen.exists():
        for note in notes_examen:
            statut = "[SOUMIS]" if note.soumis else "[EN COURS]"
            if note.absent:
                print(f"  - {note.eleve.nom_complet:<30} ABSENT {statut}")
            elif note.note_sur_20:
                print(f"  - {note.eleve.nom_complet:<30} {note.note_sur_20:>5.2f}/20 {statut}")
                if note.commentaire:
                    print(f"    Commentaire: {note.commentaire}")
            else:
                print(f"  - {note.eleve.nom_complet:<30} NON NOTE {statut}")
    else:
        print("  Aucune note enregistree")
else:
    print("\nAucune session d'examen trouvee")

print("\n" + "=" * 80)
print("INSTRUCTIONS POUR VERIFIER DANS LE NAVIGATEUR")
print("=" * 80)
print("\n1. Connectez-vous en tant qu'enseignant:")
print("   Email: amadou.diop@blaisepascal.sn")
print("   Mot de passe: 6097")
print("\n2. Naviguez vers:")
print("   http://127.0.0.1:8000/enseignant/releve/78/?periode=2")
print("\n3. Verifiez:")
print("   - Colonne 'Moyenne Devoirs de Classe' (bleu)")
print("   - Colonne 'Note Examen' APRES la moyenne (orange)")
print("   - Bordures gauches colorees")
print("   - Notes d'examen affichees avec style orange")
print("\n" + "=" * 80)

