#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script pour traduire automatiquement les fichiers .po en utilisant une API de traduction
"""
import os
import time
from pathlib import Path

try:
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False
    print("Installation de deep-translator...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "deep-translator"])
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True

try:
    from babel.messages.pofile import read_po, write_po
    from babel.messages.catalog import Catalog
except ImportError:
    print("Erreur: babel n'est pas installe. Installez-le avec: pip install babel")
    import sys
    sys.exit(1)

BASE_DIR = Path(__file__).parent
LOCALE_DIR = BASE_DIR / 'locale'

# Mapping des langues
LANGUAGE_MAP = {
    'en': 'en',
    'es': 'es',
    'ar': 'ar',
    'fr': 'fr'
}

def translate_text(text, source_lang='fr', target_lang='en'):
    """Traduit un texte en utilisant Google Translate"""
    try:
        translator = GoogleTranslator(source=source_lang, target=target_lang)
        translated = translator.translate(text)
        return translated
    except Exception as e:
        print(f"Erreur de traduction pour '{text[:50]}...': {e}")
        return text  # Retourner le texte original en cas d'erreur

def translate_po_file(po_path, target_lang):
    """Traduit un fichier .po complet"""
    print(f"\nTraduction de {po_path.name} vers {target_lang}...")
    
    try:
        # Lire le fichier .po
        with open(po_path, 'rb') as f:
            catalog = read_po(f)
        
        total_messages = len([m for m in catalog if m.id])
        translated_count = 0
        skipped_count = 0
        
        print(f"  Total de messages à traduire: {total_messages}")
        
        for message in catalog:
            if not message.id:  # Ignorer le message vide de l'en-tête
                continue
            
            # Si le msgstr est vide ou identique au msgid, traduire
            if not message.string or message.string == message.id:
                try:
                    translated = translate_text(message.id, source_lang='fr', target_lang=target_lang)
                    message.string = translated
                    translated_count += 1
                    
                    # Afficher la progression
                    if translated_count % 50 == 0:
                        print(f"  Progression: {translated_count}/{total_messages} traduits...")
                    
                    # Pause pour éviter de surcharger l'API
                    time.sleep(0.1)
                    
                except Exception as e:
                    print(f"  Erreur pour '{message.id[:50]}...': {e}")
                    skipped_count += 1
                    continue
        
        # Écrire le fichier .po traduit
        with open(po_path, 'wb') as f:
            write_po(f, catalog, width=79, no_location=True, sort_output=True)
        
        print(f"  ✓ Traduction terminée: {translated_count} traduits, {skipped_count} ignorés")
        return True
        
    except Exception as e:
        print(f"  ✗ Erreur lors de la traduction: {e}")
        return False

def main():
    print("Traduction automatique des fichiers .po")
    print("=" * 60)
    print("\nCe script va traduire automatiquement tous les fichiers .po")
    print("en utilisant Google Translate (gratuit mais avec limitations).")
    print("\nATTENTION: Cela peut prendre du temps (plusieurs minutes)")
    print("et nécessite une connexion Internet.")
    print("\nAppuyez sur Entrée pour continuer ou Ctrl+C pour annuler...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\nAnnulé par l'utilisateur.")
        return
    
    # Langues à traduire (sauf français)
    target_languages = ['en', 'es', 'ar']
    
    for lang in target_languages:
        po_path = LOCALE_DIR / lang / 'LC_MESSAGES' / 'django.po'
        
        if not po_path.exists():
            print(f"\n⚠ Fichier non trouvé: {po_path}")
            continue
        
        translate_po_file(po_path, LANGUAGE_MAP[lang])
    
    print("\n" + "=" * 60)
    print("Traduction terminée!")
    print("\nPour compiler les fichiers .po en .mo, exécutez:")
    print("  python compile_translations.py")
    print("\nNote: Vérifiez manuellement certaines traductions pour vous assurer")
    print("de leur exactitude, surtout pour les termes techniques spécifiques.")

if __name__ == '__main__':
    main()
