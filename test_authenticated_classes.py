#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de la page des classes avec authentification
"""

import requests
from bs4 import BeautifulSoup

def test_authenticated_classes():
    """Test de la page des classes avec authentification"""
    try:
        # Créer une session pour maintenir les cookies
        session = requests.Session()
        
        # URL de connexion
        login_url = "http://localhost:8000/connexion/administrateur/"
        classes_url = "http://localhost:8000/classes/"
        
        # Récupérer la page de connexion pour obtenir le CSRF token
        login_page = session.get(login_url)
        soup = BeautifulSoup(login_page.content, 'html.parser')
        
        # Trouver le CSRF token
        csrf_token = None
        csrf_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
        if csrf_input:
            csrf_token = csrf_input.get('value')
            print(f"CSRF token trouvé: {csrf_token[:20]}...")
        else:
            print("CSRF token non trouvé")
            return
        
        # Données de connexion (utiliser les identifiants de test)
        login_data = {
            'csrfmiddlewaretoken': csrf_token,
            'username': 'oyono01@gmail.com',
            'password': 'Ludvanne12'
        }
        
        # Se connecter
        print("Tentative de connexion...")
        login_response = session.post(login_url, data=login_data, allow_redirects=True)
        
        if login_response.status_code == 200:
            print("Connexion réussie")
            
            # Tester la page des classes
            print("Test de la page des classes...")
            classes_response = session.get(classes_url)
            
            if classes_response.status_code == 200:
                print(f"Page des classes accessible - Status: {classes_response.status_code}")
                
                # Parser le HTML
                soup = BeautifulSoup(classes_response.content, 'html.parser')
                
                # Vérifier le titre de la page
                title = soup.find('title')
                if title:
                    print(f"Page Title: {title.get_text()}")
                
                # Vérifier la présence du CSS
                css_links = soup.find_all('link', rel='stylesheet')
                css_found = False
                for link in css_links:
                    href = link.get('href', '')
                    if 'classes_clean.css' in href:
                        print(f"CSS trouvé: {href}")
                        css_found = True
                        break
                
                if not css_found:
                    print("CSS classes_clean.css non trouvé")
                    print("CSS trouvés:")
                    for link in css_links:
                        print(f"  - {link.get('href', '')}")
                
                # Vérifier la présence des onglets de catégories
                category_tabs = soup.find_all(class_='tab-btn')
                print(f"Onglets de catégories trouvés: {len(category_tabs)}")
                for tab in category_tabs:
                    category = tab.get('data-category', 'N/A')
                    print(f"  - Catégorie: {category}")
                
                # Vérifier la présence des panneaux de catégories
                category_panels = soup.find_all(class_='tab-panel')
                print(f"Panneaux de catégories trouvés: {len(category_panels)}")
                
                # Vérifier la présence des cartes de classes
                classe_cards = soup.find_all(class_='classe-card')
                print(f"Cartes de classes trouvées: {len(classe_cards)}")
                
                # Vérifier la présence du modal
                modal = soup.find(id='addClasseModal')
                if modal:
                    print("Modal d'ajout trouvé")
                else:
                    print("Modal d'ajout non trouvé")
                
                # Vérifier les statistiques
                stat_cards = soup.find_all(class_='stat-card')
                print(f"Cartes de statistiques trouvées: {len(stat_cards)}")
                
                print("\n[SUCCES] Test de la page des classes avec regroupement réussi !")
                
            else:
                print(f"Erreur HTTP pour la page des classes: {classes_response.status_code}")
                print(f"Response: {classes_response.text[:500]}")
        else:
            print(f"Erreur de connexion: {login_response.status_code}")
            print(f"Response: {login_response.text[:500]}")
            
    except Exception as e:
        print(f"Erreur: {e}")

if __name__ == "__main__":
    test_authenticated_classes()
