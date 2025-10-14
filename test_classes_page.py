#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de test pour vérifier la page des classes
"""

import requests
from bs4 import BeautifulSoup

def test_classes_page():
    """Test de la page des classes"""
    try:
        # URL de la page des classes
        url = "http://localhost:8000/classes/"
        
        # Faire une requête GET
        response = requests.get(url)
        
        if response.status_code == 200:
            print("[OK] Page des classes accessible")
            
            # Parser le HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Vérifier la présence des éléments clés
            page_title = soup.find('h1')
            if page_title and 'Gestion des Classes' in page_title.get_text():
                print("[OK] Titre de la page correct")
            else:
                print("[ERREUR] Titre de la page incorrect")
            
            # Vérifier la présence des statistiques
            stats_cards = soup.find_all(class_='stat-card')
            print(f"[OK] {len(stats_cards)} cartes de statistiques trouvées")
            
            # Vérifier la présence des cartes de classes
            classe_cards = soup.find_all(class_='classe-card')
            print(f"[OK] {len(classe_cards)} cartes de classes trouvées")
            
            # Vérifier la présence du modal
            modal = soup.find(id='addClasseModal')
            if modal:
                print("[OK] Modal d'ajout de classe présent")
            else:
                print("[ERREUR] Modal d'ajout de classe manquant")
            
            # Vérifier la présence du CSS
            css_links = soup.find_all('link', rel='stylesheet')
            css_found = False
            for link in css_links:
                if 'classes_clean.css' in link.get('href', ''):
                    css_found = True
                    break
            
            if css_found:
                print("[OK] CSS clean chargé")
            else:
                print("[ERREUR] CSS clean non chargé")
            
            print("\n[SUCCES] Test de la page des classes réussi !")
            
        else:
            print(f"[ERREUR] Erreur HTTP: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("[ERREUR] Impossible de se connecter au serveur. Assurez-vous que le serveur Django est démarré.")
    except Exception as e:
        print(f"[ERREUR] Erreur lors du test: {e}")

if __name__ == "__main__":
    test_classes_page()
