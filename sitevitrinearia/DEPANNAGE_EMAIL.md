# 🔧 Dépannage - Envoi d'Email

## ❌ Erreur : "Une erreur est survenue lors de l'envoi"

Cette erreur signifie que EmailJS n'est pas correctement configuré. Suivez ces étapes :

## ✅ Solution Rapide

### Étape 1 : Vérifier la Configuration

Ouvrez le fichier `js/script.js` et vérifiez que vous avez remplacé ces valeurs :

```javascript
const EMAILJS_CONFIG = {
    publicKey: 'VOTRE_CLE_PUBLIQUE',      // ❌ Ne doit PAS être 'YOUR_PUBLIC_KEY'
    serviceID: 'VOTRE_SERVICE_ID',       // ❌ Ne doit PAS être 'YOUR_SERVICE_ID'
    templateID: 'VOTRE_TEMPLATE_ID',     // ❌ Ne doit PAS être 'YOUR_TEMPLATE_ID'
    toEmail: 'ariaedu55@gmail.com'       // ✅ Déjà correct
};
```

### Étape 2 : Obtenir vos Identifiants EmailJS

#### A. Créer un compte EmailJS
1. Allez sur [https://www.emailjs.com/](https://www.emailjs.com/)
2. Créez un compte gratuit
3. Connectez-vous

#### B. Obtenir la Clé Publique (Public Key)
1. Dans le dashboard, allez dans **Account** > **General**
2. Copiez votre **Public Key** (ex: `abcdefghijklmnopqrstuvwxyz123456`)
3. Collez-la dans `script.js` à la place de `YOUR_PUBLIC_KEY`

#### C. Créer un Service Email
1. Allez dans **Email Services**
2. Cliquez sur **Add New Service**
3. Choisissez **Gmail** (recommandé)
4. Connectez votre compte Gmail
5. Notez le **Service ID** (ex: `service_abc123`)
6. Collez-le dans `script.js` à la place de `YOUR_SERVICE_ID`

#### D. Créer un Template Email
1. Allez dans **Email Templates**
2. Cliquez sur **Create New Template**
3. Utilisez ce template :

**Sujet :**
```
Nouveau message de contact - {{from_name}}
```

**Contenu :**
```
Bonjour,

Vous avez reçu un nouveau message depuis le formulaire de contact :

Nom: {{from_name}}
Email: {{from_email}}
Établissement: {{etablissement}}
Message: {{message}}

---
Ce message a été envoyé depuis le site vitrine ARIA.
Répondre à: {{reply_to}}
```

4. Dans les paramètres du template :
   - **To Email:** `ariaedu55@gmail.com`
   - **From Name:** `{{from_name}}`
   - **Reply To:** `{{reply_to}}`

5. Sauvegardez et notez le **Template ID** (ex: `template_xyz789`)
6. Collez-le dans `script.js` à la place de `YOUR_TEMPLATE_ID`

### Étape 3 : Vérifier la Console du Navigateur

1. Ouvrez votre site dans un navigateur
2. Appuyez sur **F12** pour ouvrir les outils de développement
3. Allez dans l'onglet **Console**
4. Vérifiez les messages :
   - ✅ `EmailJS initialisé avec succès` = Tout est OK
   - ❌ `EmailJS n'est pas configuré` = Vérifiez vos identifiants
   - ❌ `EmailJS n'est pas chargé` = Vérifiez que le script est dans le HTML

## 🔍 Vérifications Courantes

### ✅ Vérification 1 : Le script EmailJS est-il chargé ?
Dans le HTML, vous devez avoir cette ligne AVANT `script.js` :
```html
<script type="text/javascript" src="https://cdn.jsdelivr.net/npm/@emailjs/browser@4/dist/email.min.js"></script>
<script src="js/script.js"></script>
```

### ✅ Vérification 2 : Les identifiants sont-ils corrects ?
- Public Key : Commence généralement par des lettres (ex: `abc123...`)
- Service ID : Commence par `service_` (ex: `service_abc123`)
- Template ID : Commence par `template_` (ex: `template_xyz789`)

### ✅ Vérification 3 : Le compte EmailJS est-il actif ?
- Vérifiez que vous êtes connecté à EmailJS
- Vérifiez que vous n'avez pas dépassé la limite de 200 emails/mois (gratuit)

### ✅ Vérification 4 : Le template est-il publié ?
- Dans EmailJS, allez dans **Email Templates**
- Assurez-vous que votre template est **Published** (publié)
- Un template non publié ne fonctionnera pas

## 📧 Test Rapide

1. Ouvrez la console du navigateur (F12)
2. Remplissez le formulaire
3. Cliquez sur "Envoyer"
4. Regardez les messages dans la console :
   - Si vous voyez `✅ Email envoyé avec succès!` = Ça fonctionne !
   - Si vous voyez une erreur, notez le code d'erreur (ex: 400, 401, 404)

## 🆘 Codes d'Erreur Courants

- **400** : Mauvais format de données
- **401** : Clé publique invalide
- **403** : Accès refusé (vérifiez vos permissions)
- **404** : Service ou Template introuvable (vérifiez les IDs)
- **429** : Trop de requêtes (attendez quelques minutes)

## 💡 Astuce

Si vous avez toujours des problèmes, vous pouvez temporairement utiliser cette alternative simple :

```javascript
// Alternative simple (sans EmailJS)
contactForm.addEventListener('submit', function(e) {
    e.preventDefault();
    const email = 'ariaedu55@gmail.com';
    const subject = 'Nouveau message de contact';
    const body = `Nom: ${formData.nom}\nEmail: ${formData.email}\nMessage: ${formData.message}`;
    window.location.href = `mailto:${email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
});
```

Mais cette méthode ouvre le client email de l'utilisateur, ce qui n'est pas idéal.

## 📞 Besoin d'Aide ?

Si le problème persiste :
1. Vérifiez la console du navigateur pour les erreurs détaillées
2. Consultez [CONFIGURATION_EMAILJS.md](CONFIGURATION_EMAILJS.md) pour le guide complet
3. Consultez la [documentation EmailJS](https://www.emailjs.com/docs/)
