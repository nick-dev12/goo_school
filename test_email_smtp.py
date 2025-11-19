#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de test pour vérifier l'envoi d'email via SMTP
Ce script teste la configuration SMTP et envoie un email de test
"""

import os
import sys
import django

# Forcer l'encodage UTF-8 pour Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Configuration du chemin Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')

# Initialiser Django
django.setup()

from django.core.mail import send_mail, EmailMessage
from django.conf import settings
from django.template.loader import render_to_string

def test_smtp_connection():
    """
    Teste la connexion SMTP et l'envoi d'un email de test
    """
    print("=" * 60)
    print("TEST D'ENVOI D'EMAIL SMTP")
    print("=" * 60)
    print()
    
    # Afficher la configuration SMTP
    print("📧 Configuration SMTP:")
    print(f"   Host: {settings.EMAIL_HOST}")
    print(f"   Port: {settings.EMAIL_PORT}")
    print(f"   Use SSL: {settings.EMAIL_USE_SSL}")
    print(f"   Use TLS: {settings.EMAIL_USE_TLS}")
    print(f"   User: {settings.EMAIL_HOST_USER}")
    print(f"   From: {settings.DEFAULT_FROM_EMAIL}")
    print()
    
    # Email de test
    recipient_email = "webgeniuses12@gmail.com"
    subject = "Test SMTP - Aria Plateforme de gestion scolaire"
    
    # Message HTML de test
    html_message = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }
            .header {
                background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
                color: white;
                padding: 20px;
                text-align: center;
                border-radius: 10px 10px 0 0;
            }
            .content {
                background: #f9fafb;
                padding: 30px;
                border-radius: 0 0 10px 10px;
            }
            .success-box {
                background: #d1fae5;
                border: 2px solid #10b981;
                border-radius: 8px;
                padding: 15px;
                margin: 20px 0;
            }
            .info-box {
                background: #eff6ff;
                border-left: 4px solid #3b82f6;
                padding: 15px;
                margin: 20px 0;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>✅ Test SMTP Réussi</h1>
        </div>
        <div class="content">
            <p>Bonjour,</p>
            <p>Ceci est un email de test pour vérifier que la configuration SMTP fonctionne correctement.</p>
            
            <div class="success-box">
                <strong>✅ Statut : SUCCÈS</strong><br>
                L'email a été envoyé avec succès via le serveur SMTP configuré.
            </div>
            
            <div class="info-box">
                <strong>📋 Informations de configuration :</strong><br>
                <ul>
                    <li>Serveur SMTP : aria-edu.com</li>
                    <li>Port : 465 (SSL)</li>
                    <li>Expéditeur : nick@aria-edu.com</li>
                </ul>
            </div>
            
            <p>Si vous recevez cet email, cela signifie que :</p>
            <ul>
                <li>✅ La connexion SMTP fonctionne</li>
                <li>✅ L'authentification est réussie</li>
                <li>✅ L'email peut être envoyé</li>
                <li>✅ Le système d'envoi d'email est opérationnel</li>
            </ul>
            
            <p>Vous pouvez maintenant utiliser cette configuration pour envoyer des emails aux établissements lors de leur création.</p>
            
            <p style="margin-top: 30px; color: #6b7280; font-size: 14px;">
                Cet email a été envoyé automatiquement par le script de test SMTP.<br>
                Aria - Plateforme de gestion scolaire
            </p>
        </div>
    </body>
    </html>
    """
    
    # Message texte simple (fallback)
    plain_message = """
    Test SMTP - Aria Plateforme de gestion scolaire
    
    Bonjour,
    
    Ceci est un email de test pour vérifier que la configuration SMTP fonctionne correctement.
    
    Statut : SUCCÈS
    L'email a été envoyé avec succès via le serveur SMTP configuré.
    
    Si vous recevez cet email, cela signifie que :
    - La connexion SMTP fonctionne
    - L'authentification est réussie
    - L'email peut être envoyé
    - Le système d'envoi d'email est opérationnel
    
    Aria - Plateforme de gestion scolaire
    """
    
    try:
        print(f"📤 Tentative d'envoi d'email à: {recipient_email}")
        print()
        
        # Tester la connexion SMTP d'abord
        import smtplib
        import socket
        
        print("🔍 Test de connexion SMTP...")
        
        # Test 1: Vérifier si le serveur est accessible
        print(f"   → Test de connexion au serveur {settings.EMAIL_HOST}...")
        try:
            sock = socket.create_connection((settings.EMAIL_HOST, settings.EMAIL_PORT), timeout=10)
            sock.close()
            print(f"   ✅ Le serveur {settings.EMAIL_HOST}:{settings.EMAIL_PORT} est accessible")
        except Exception as conn_error:
            print(f"   ❌ Impossible de se connecter au serveur: {str(conn_error)}")
            print()
            print("   💡 Tentative avec le port 587 (TLS)...")
            try:
                sock = socket.create_connection((settings.EMAIL_HOST, 587), timeout=10)
                sock.close()
                print(f"   ✅ Le port 587 est accessible, essayons avec TLS...")
                # Tester avec TLS sur le port 587
                server = smtplib.SMTP(settings.EMAIL_HOST, 587, timeout=10)
                server.starttls()
                server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                print("   ✅ Connexion SMTP réussie avec TLS sur le port 587")
                server.quit()
                print()
                print("   ⚠️  NOTE: Le serveur semble préférer le port 587 avec TLS")
                print("   → Vous devriez peut-être modifier settings.py:")
                print("      EMAIL_PORT = 587")
                print("      EMAIL_USE_SSL = False")
                print("      EMAIL_USE_TLS = True")
                raise Exception("Configuration SMTP à ajuster: utiliser port 587 avec TLS")
            except Exception as tls_error:
                print(f"   ❌ Échec également avec TLS: {str(tls_error)}")
                raise conn_error
        
        # Test 2: Connexion SMTP avec les paramètres configurés
        print(f"   → Tentative de connexion SMTP avec les paramètres configurés...")
        try:
            import ssl
            if settings.EMAIL_USE_SSL:
                # Créer un contexte SSL sans vérification du certificat
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                server = smtplib.SMTP_SSL(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=10, context=context)
            else:
                server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=10)
                if settings.EMAIL_USE_TLS:
                    # Créer un contexte TLS sans vérification du certificat
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    server.starttls(context=context)
            
            print("   → Authentification...")
            server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            print("   ✅ Connexion SMTP et authentification réussies")
            server.quit()
        except Exception as smtp_error:
            print(f"   ❌ Erreur de connexion SMTP: {type(smtp_error).__name__}: {str(smtp_error)}")
            print()
            print("   💡 Suggestions:")
            print("      - Vérifiez que le serveur SMTP est accessible depuis votre réseau")
            print("      - Vérifiez les identifiants (username/password)")
            print("      - Vérifiez le port (465 pour SSL, 587 pour TLS)")
            print("      - Vérifiez votre connexion internet")
            print("      - Vérifiez les paramètres de pare-feu")
            print("      - Le serveur peut nécessiter une connexion depuis une IP autorisée")
            raise
        
        print()
        print("📧 Envoi de l'email...")
        
        # Créer un backend SMTP personnalisé pour désactiver la vérification SSL
        from django.core.mail.backends.smtp import EmailBackend
        import ssl
        
        class CustomEmailBackend(EmailBackend):
            def open(self):
                if self.connection:
                    return False
                try:
                    self.connection = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
                    if self.use_tls:
                        context = ssl.create_default_context()
                        context.check_hostname = False
                        context.verify_mode = ssl.CERT_NONE
                        self.connection.starttls(context=context)
                    if self.username and self.password:
                        self.connection.login(self.username, self.password)
                    return True
                except Exception:
                    if not self.fail_silently:
                        raise
        
        # Utiliser le backend personnalisé temporairement
        from django.core import mail
        original_backend = settings.EMAIL_BACKEND
        settings.EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
        
        # Méthode 1: Utiliser send_mail (simple)
        try:
            result = send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as email_error:
            # Si erreur SSL, essayer avec un backend personnalisé
            if 'certificate' in str(email_error).lower() or 'ssl' in str(email_error).lower():
                print("   ⚠️  Erreur de certificat SSL détectée, tentative avec vérification désactivée...")
                # Utiliser EmailMessage directement avec connexion manuelle
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = settings.DEFAULT_FROM_EMAIL
                msg['To'] = recipient_email
                
                part1 = MIMEText(plain_message, 'plain', 'utf-8')
                part2 = MIMEText(html_message, 'html', 'utf-8')
                msg.attach(part1)
                msg.attach(part2)
                
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                
                server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=10)
                server.starttls(context=context)
                server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                server.send_message(msg)
                server.quit()
                result = 1
            else:
                raise
        
        if result == 1:
            print("✅ SUCCÈS ! Email envoyé avec succès")
            print(f"   → Email envoyé à: {recipient_email}")
            print(f"   → Sujet: {subject}")
            print(f"   → Statut: {result} (1 = succès)")
            print()
            print("=" * 60)
            print("✅ TEST RÉUSSI - Le système d'envoi d'email fonctionne correctement")
            print("=" * 60)
            return True
        else:
            print(f"❌ ÉCHEC ! Résultat inattendu: {result}")
            return False
            
    except Exception as e:
        print("❌ ERREUR lors de l'envoi de l'email:")
        print(f"   Type d'erreur: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        print()
        print("=" * 60)
        print("❌ TEST ÉCHOUÉ - Vérifiez la configuration SMTP")
        print("=" * 60)
        return False

if __name__ == "__main__":
    try:
        success = test_smtp_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrompu par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Erreur fatale: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

