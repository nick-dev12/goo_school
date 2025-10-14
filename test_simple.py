#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test simple de la page des classes
"""

import requests
from bs4 import BeautifulSoup

def test_simple():
    """Test simple de la page des classes"""
    try:
        # Créer une session pour maintenir les cookies
        session = requests.Session()
        
        # URL de la page des classes
        url = "http://localhost:8000/classes/"
        
        # Faire une requête GET
        response = session.get(url)
        
        print(f"Status Code: {response.status_code}")
        print(f"Content Length: {len(response.content)}")
        
        if response.status_code == 200:
            # Parser le HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Vérifier le titre de la page
            title = soup.find('title')
            if title:
                print(f"Page Title: {title.get_text()}")
            
            # Vérifier la présence du CSS
            css_links = soup.find_all('link', rel='stylesheet')
            for link in css_links:
                href = link.get('href', '')
                if 'classes_clean.css' in href:
                    print(f"CSS trouvé: {href}")
                    break
            else:
                print("CSS classes_clean.css non trouvé")
                print("CSS trouvés:")
                for link in css_links:
                    print(f"  - {link.get('href', '')}")
            
            # Vérifier la présence des éléments principaux
            h1_tags = soup.find_all('h1')
            print(f"Nombre de h1: {len(h1_tags)}")
            for h1 in h1_tags:
                print(f"  - {h1.get_text()}")
            
            # Vérifier la présence du modal
            modal = soup.find(id='addClasseModal')
            if modal:
                print("Modal d'ajout trouvé")
            else:
                print("Modal d'ajout non trouvé")
            
            # Vérifier la présence des cartes
            stat_cards = soup.find_all(class_='stat-card')
            classe_cards = soup.find_all(class_='classe-card')
            print(f"Stat cards: {len(stat_cards)}")
            print(f"Classe cards: {len(classe_cards)}")
            
        else:
            print(f"Erreur HTTP: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            
    except Exception as e:
        print(f"Erreur: {e}")

if __name__ == "__main__":
    test_simple()