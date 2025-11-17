"""
Script pour générer automatiquement les icônes PWA à partir du logo
Nécessite Pillow : pip install Pillow
"""
import os
import sys
from pathlib import Path

# Configurer l'encodage UTF-8 pour Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

try:
    from PIL import Image
except ImportError:
    print("[ERREUR] Pillow n'est pas installe. Installez-le avec : pip install Pillow")
    exit(1)

# Configuration
BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / 'static' / 'school_admin' / 'img' / 'logo.jpeg'
OUTPUT_DIR = BASE_DIR / 'static' / 'school_admin' / 'img' / 'icons'

# Tailles requises pour la PWA
SIZES = [16, 32, 72, 96, 128, 144, 152, 192, 384, 512]


def generate_icons():
    """Génère toutes les icônes PWA à partir du logo"""
    
    # Vérifier que le logo existe
    if not LOGO_PATH.exists():
        print(f"[ERREUR] Logo introuvable : {LOGO_PATH}")
        print("   Assurez-vous que le fichier logo.jpeg existe dans le bon repertoire.")
        return False
    
    # Créer le dossier de sortie si nécessaire
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Supprimer les anciennes icônes avant de générer les nouvelles
    print("[INFO] Suppression des anciennes icônes...")
    deleted_count = 0
    for size in SIZES:
        old_icon = OUTPUT_DIR / f'icon-{size}x{size}.png'
        if old_icon.exists():
            try:
                old_icon.unlink()
                deleted_count += 1
                print(f"   [SUPPRIME] {old_icon.name}")
            except Exception as e:
                print(f"   [ERREUR] Impossible de supprimer {old_icon.name}: {e}")
    
    # Supprimer aussi toutes les autres icônes qui pourraient exister
    if OUTPUT_DIR.exists():
        for icon_file in OUTPUT_DIR.glob('icon-*.png'):
            if icon_file.name not in [f'icon-{size}x{size}.png' for size in SIZES]:
                try:
                    icon_file.unlink()
                    deleted_count += 1
                    print(f"   [SUPPRIME] {icon_file.name}")
                except Exception as e:
                    print(f"   [ERREUR] Impossible de supprimer {icon_file.name}: {e}")
    
    print(f"[INFO] {deleted_count} ancienne(s) icône(s) supprimée(s)\n")
    
    try:
        # Ouvrir l'image source (JPEG)
        img = Image.open(LOGO_PATH)
        
        # Convertir en RGB puis RGBA pour les icônes PNG (JPEG est en RGB)
        # Le JPEG a un fond, donc on veut garder ce fond (pas de transparence)
        if img.mode == 'RGB':
            # Convertir RGB en RGBA (ajouter canal alpha opaque à 255)
            # Cela garantit que tous les pixels ont un fond opaque (pas transparent)
            img = img.convert('RGBA')
            # S'assurer que le canal alpha est bien opaque (255) pour tous les pixels
            # Créer une nouvelle image avec alpha opaque
            alpha = Image.new('L', img.size, 255)  # Canal alpha complètement opaque
            img.putalpha(alpha)
        elif img.mode != 'RGBA':
            img = img.convert('RGBA')
            # S'assurer que le canal alpha est opaque
            alpha = Image.new('L', img.size, 255)
            img.putalpha(alpha)
        
        print(f"[INFO] Logo source : {LOGO_PATH}")
        print(f"[INFO] Dossier de sortie : {OUTPUT_DIR}\n")
        
        # Générer les icônes
        generated = 0
        for size in SIZES:
            try:
                # Redimensionner en gardant les proportions avec un redimensionnement de haute qualité
                resized = img.resize((size, size), Image.Resampling.LANCZOS)
                
                # Sauvegarder
                output_path = OUTPUT_DIR / f'icon-{size}x{size}.png'
                resized.save(output_path, 'PNG', optimize=True)
                
                print(f"[OK] Icône {size}x{size} générée : {output_path}")
                generated += 1
                
            except Exception as e:
                print(f"[ERREUR] Erreur lors de la generation de l'icone {size}x{size} : {e}")
        
        print(f"\n[SUCCES] {generated}/{len(SIZES)} icônes générées avec succès!")
        
        # Vérifier les fichiers générés
        print("\n[LISTE] Fichiers générés :")
        for size in SIZES:
            icon_path = OUTPUT_DIR / f'icon-{size}x{size}.png'
            if icon_path.exists():
                file_size = icon_path.stat().st_size
                print(f"   [OK] icon-{size}x{size}.png ({file_size} bytes)")
            else:
                print(f"   [MANQUANT] icon-{size}x{size}.png")
        
        return True
        
    except Exception as e:
        print(f"[ERREUR] Erreur lors de la generation des icones : {e}")
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("GENERATION DES ICONES PWA POUR ARIA")
    print("=" * 60)
    print()
    
    success = generate_icons()
    
    print("\n" + "=" * 60)
    if success:
        print("\n[SUCCES] Generation terminee avec succes!")
        print("\n[ETAPES] Prochaines etapes :")
        print("   1. Verifiez que tous les fichiers d'icones sont presents")
        print("   2. Testez l'application PWA sur differents appareils")
        print("   3. Verifiez le manifest.json et le service-worker.js")
    else:
        print("\n[ERREUR] La generation a echoue. Verifiez les erreurs ci-dessus.")
    print("=" * 60)

