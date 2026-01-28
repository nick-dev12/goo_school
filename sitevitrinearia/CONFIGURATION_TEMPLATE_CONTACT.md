# 📧 Configuration du Template EmailJS pour le Formulaire de Contact

## ✅ Vos Identifiants (déjà configurés dans le code)
- **Public Key:** `snCOiYbrXCdP_U1Tf`
- **Service ID:** `service_zgrt1as`
- **Template ID:** `template_l5sb6bl`
- **Email de destination:** `ariaedu55@gmail.com`

## 🔧 Configuration du Template dans EmailJS

### Étape 1 : Modifier le Sujet de l'Email

Dans le champ **Subject**, remplacez :
```
demande de demo
```

Par :
```
Nouveau message de contact - {{from_name}}
```

### Étape 2 : Modifier le Contenu de l'Email

Dans la section **Content**, remplacez tout le contenu actuel par :

```
Bonjour,

Vous avez reçu un nouveau message depuis le formulaire de contact du site vitrine ARIA :

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 INFORMATIONS DU CONTACT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 Nom complet : {{from_name}}
📧 Email : {{from_email}}
📞 Téléphone : {{telephone}}
🏫 Établissement : {{etablissement}}
📚 Type d'établissement : {{type_etablissement}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💬 MESSAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{{message}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ce message a été envoyé depuis le formulaire de contact du site vitrine ARIA.

Pour répondre à ce message, répondez directement à cet email.
```

### Étape 3 : Configurer les Paramètres (Settings)

Dans le panneau de droite, configurez :

1. **To Email** : 
   ```
   ariaedu55@gmail.com
   ```
   (Déjà configuré ✅)

2. **From Name** :
   ```
   {{from_name}}
   ```
   (Laissez vide ou mettez "Site Vitrine ARIA" si vous préférez)

3. **From Email** :
   - ✅ Cochez "Use Default Email Address" (utilise l'email par défaut du service)

4. **Reply To** :
   ```
   {{reply_to}}
   ```
   ⚠️ **IMPORTANT** : Cela permet de répondre directement à la personne qui a rempli le formulaire

5. **Bcc** et **Cc** : Laissez vides

### Étape 4 : Sauvegarder le Template

1. Cliquez sur le bouton bleu **"Save"** en haut à droite
2. Assurez-vous que le template est **Published** (publié)

## 📋 Variables Utilisées dans le Template

Le code JavaScript envoie ces variables :

- `{{from_name}}` → Nom complet de la personne
- `{{from_email}}` → Email de la personne
- `{{telephone}}` → Numéro de téléphone de la personne
- `{{etablissement}}` → Nom de l'établissement (ou "Non spécifié")
- `{{type_etablissement}}` → Type d'établissement (École Primaire, Collège, Lycée, etc.)
- `{{message}}` → Message de la personne
- `{{to_email}}` → Email de destination (ariaedu55@gmail.com)
- `{{reply_to}}` → Email pour répondre (même que from_email)

## ✅ Vérification

Après avoir configuré le template :

1. **Testez le template directement dans EmailJS** :
   - Cliquez sur **"Test It"** en haut
   - Remplissez les variables manuellement :
     - `from_name`: Test
     - `from_email`: test@test.com
     - `telephone`: +221 77 123 45 67
     - `etablissement`: École Test
     - `type_etablissement`: École Primaire
     - `message`: Ceci est un message de test
     - `reply_to`: test@test.com
   - Cliquez sur **Send Test Email**
   - Vérifiez que l'email arrive à ariaedu55@gmail.com

2. **Testez depuis le site** :
   - Ouvrez votre site
   - Remplissez le formulaire de contact
   - Envoyez le message
   - Vérifiez la console (F12) pour voir les logs
   - Vérifiez votre boîte email ariaedu55@gmail.com

## 🎨 Template Alternatif (Plus Simple)

Si vous préférez un template plus simple, utilisez ceci :

**Sujet :**
```
Contact ARIA - {{from_name}}
```

**Contenu :**
```
Nouveau message de contact

Nom: {{from_name}}
Email: {{from_email}}
Téléphone: {{telephone}}
Établissement: {{etablissement}}
Type d'établissement: {{type_etablissement}}

Message:
{{message}}

---
Répondre à: {{reply_to}}
```

## ⚠️ Problèmes Courants

### L'email n'arrive pas
1. Vérifiez les **spams** de ariaedu55@gmail.com
2. Vérifiez que le template est **Published**
3. Vérifiez que le service email est **actif**

### Les variables ne s'affichent pas
- Assurez-vous d'utiliser exactement `{{from_name}}` et non `{{nom}}`
- Les variables doivent être entre doubles accolades `{{ }}`

### Erreur 400
- Vérifiez que toutes les variables utilisées dans le template existent dans les paramètres envoyés
- Le code envoie : from_name, from_email, telephone, etablissement, type_etablissement, message, to_email, reply_to

## 📞 Support

Si vous avez toujours des problèmes :
1. Vérifiez la console du navigateur (F12) pour les erreurs
2. Testez le template directement dans EmailJS
3. Vérifiez que tous les identifiants sont corrects dans `js/script.js`
