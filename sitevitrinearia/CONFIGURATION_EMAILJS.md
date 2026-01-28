# Configuration EmailJS pour le Formulaire de Contact

Ce guide vous explique comment configurer EmailJS pour permettre l'envoi d'emails depuis le formulaire de contact.

## Étapes de Configuration

### 1. Créer un compte EmailJS

1. Allez sur [https://www.emailjs.com/](https://www.emailjs.com/)
2. Créez un compte gratuit (200 emails/mois gratuits)
3. Connectez-vous à votre compte

### 2. Configurer un Service Email

1. Dans le dashboard EmailJS, allez dans **Email Services**
2. Cliquez sur **Add New Service**
3. Choisissez votre fournisseur d'email (Gmail recommandé)
4. Suivez les instructions pour connecter votre compte Gmail
5. Notez le **Service ID** (ex: `service_xxxxxxx`)

### 3. Créer un Template Email

1. Allez dans **Email Templates**
2. Cliquez sur **Create New Template**
3. Utilisez le template suivant :

**Template ID:** `template_xxxxxxx` (vous le verrez après création)

**Sujet de l'email:**
```
Nouveau message de contact - {{from_name}}
```

**Contenu de l'email:**
```
Bonjour,

Vous avez reçu un nouveau message depuis le formulaire de contact :

Nom: {{from_name}}
Email: {{from_email}}
Établissement: {{etablissement}}
Message: {{message}}

---
Ce message a été envoyé depuis le site vitrine ARIA.
```

4. Dans les paramètres du template, définissez :
   - **To Email:** `aria@gmail.com`
   - **From Name:** `{{from_name}}`
   - **Reply To:** `{{from_email}}`

5. Sauvegardez le template et notez le **Template ID**

### 4. Obtenir votre Clé Publique

1. Allez dans **Account** > **General**
2. Trouvez votre **Public Key** (ex: `xxxxxxxxxxxxxxxxxxxx`)
3. Copiez cette clé

### 5. Configurer le Code JavaScript

Ouvrez le fichier `js/script.js` et remplacez les valeurs suivantes :

```javascript
// Ligne 3 : Remplacez YOUR_PUBLIC_KEY
emailjs.init("VOTRE_CLE_PUBLIQUE_ICI");

// Ligne 48 : Remplacez YOUR_SERVICE_ID
const serviceID = 'VOTRE_SERVICE_ID_ICI';

// Ligne 49 : Remplacez YOUR_TEMPLATE_ID
const templateID = 'VOTRE_TEMPLATE_ID_ICI';
```

**Exemple complet :**
```javascript
emailjs.init("abcdefghijklmnopqrstuvwxyz123456");

const serviceID = 'service_abc123';
const templateID = 'template_xyz789';
```

### 6. Tester le Formulaire

1. Ouvrez votre site dans un navigateur
2. Remplissez le formulaire de contact
3. Cliquez sur "Envoyer le message"
4. Vérifiez que vous recevez l'email à `aria@gmail.com`

## Résolution des Problèmes

### L'email n'est pas envoyé

1. Vérifiez que tous les IDs sont corrects dans `script.js`
2. Vérifiez la console du navigateur (F12) pour voir les erreurs
3. Assurez-vous que votre compte EmailJS est actif
4. Vérifiez que vous n'avez pas dépassé la limite de 200 emails/mois

### Erreur "Invalid public key"

- Vérifiez que votre clé publique est correctement copiée
- Assurez-vous qu'il n'y a pas d'espaces avant ou après la clé

### Erreur "Service not found"

- Vérifiez que le Service ID est correct
- Assurez-vous que le service est bien activé dans EmailJS

### Erreur "Template not found"

- Vérifiez que le Template ID est correct
- Assurez-vous que le template est bien publié dans EmailJS

## Sécurité

⚠️ **Important :** 
- Ne partagez jamais votre clé publique sur des dépôts publics
- La clé publique est visible dans le code JavaScript, mais c'est normal pour EmailJS
- EmailJS limite automatiquement le nombre d'emails pour éviter les abus

## Support

Pour plus d'aide, consultez la documentation EmailJS :
- [Documentation EmailJS](https://www.emailjs.com/docs/)
- [Guide de démarrage](https://www.emailjs.com/docs/examples/reactjs/)
