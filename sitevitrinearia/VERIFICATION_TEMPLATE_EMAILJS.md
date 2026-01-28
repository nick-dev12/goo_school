# 🔍 Vérification du Template EmailJS

## ⚠️ Problème : Statut 200 mais email non reçu

Si vous recevez un statut 200 (succès) mais que l'email n'arrive pas, le problème vient probablement de la **configuration du template EmailJS**.

## ✅ Vérifications à faire

### 1. Vérifier les Variables du Template

Dans votre template EmailJS, vous DEVEZ utiliser exactement ces variables :

```
{{from_name}}
{{from_email}}
{{etablissement}}
{{message}}
{{to_email}}
{{reply_to}}
```

**❌ ERREUR COURANTE :** Si vous utilisez d'autres noms comme `{{nom}}`, `{{email}}`, etc., ça ne fonctionnera pas !

### 2. Configuration du Template EmailJS

#### A. Ouvrir votre Template
1. Allez sur [EmailJS Dashboard](https://dashboard.emailjs.com/)
2. Cliquez sur **Email Templates**
3. Ouvrez votre template

#### B. Vérifier le Sujet de l'Email
Le sujet doit contenir une variable, par exemple :
```
Nouveau message de contact - {{from_name}}
```

#### C. Vérifier le Contenu de l'Email
Le contenu doit utiliser les variables exactes :

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

#### D. Vérifier les Paramètres du Template

Dans les **Settings** du template, vérifiez :

1. **To Email** : Doit être `ariaedu55@gmail.com` OU utiliser `{{to_email}}`
2. **From Name** : `{{from_name}}`
3. **Reply To** : `{{reply_to}}` (important pour pouvoir répondre)

### 3. Vérifier le Service Email

1. Allez dans **Email Services**
2. Vérifiez que votre service est **actif** (statut vert)
3. Vérifiez que le compte email connecté est correct
4. Si vous utilisez Gmail, vérifiez que vous avez autorisé l'accès

### 4. Test dans la Console du Navigateur

Ouvrez la console (F12) et vérifiez les messages :

**✅ Si vous voyez :**
```
📤 Envoi d'email en cours...
📋 Paramètres envoyés: {from_name: "...", from_email: "...", ...}
✅ Email envoyé avec succès!
📊 Status: 200
```

Mais l'email n'arrive pas = **Problème de template ou de service email**

**❌ Si vous voyez :**
```
❌ Erreur lors de l'envoi:
📧 Status: 400
💡 Vérifiez que votre template EmailJS contient ces variables...
```

= **Les variables du template ne correspondent pas**

## 🔧 Solution : Template Correct

### Template Minimal qui Fonctionne

**Sujet :**
```
Nouveau message - {{from_name}}
```

**Contenu :**
```
Nom: {{from_name}}
Email: {{from_email}}
Établissement: {{etablissement}}
Message: {{message}}
```

**Settings :**
- **To Email:** `ariaedu55@gmail.com` (ou `{{to_email}}`)
- **From Name:** `{{from_name}}`
- **Reply To:** `{{reply_to}}`

## 📧 Vérifier les Spams

Si le statut est 200, l'email peut être dans les **spams** :

1. Vérifiez le dossier **Spam/Indésirables** de `ariaedu55@gmail.com`
2. Vérifiez le dossier **Promotions** (Gmail)
3. Ajoutez `noreply@emailjs.com` à vos contacts pour éviter les spams

## 🧪 Test Direct dans EmailJS

1. Allez dans **Email Templates**
2. Cliquez sur **Test Template**
3. Remplissez les variables manuellement :
   - `from_name`: Test
   - `from_email`: test@test.com
   - `etablissement`: Test École
   - `message`: Message de test
   - `to_email`: ariaedu55@gmail.com
   - `reply_to`: test@test.com
4. Cliquez sur **Send Test Email**
5. Vérifiez si l'email arrive

**Si le test fonctionne mais pas depuis le site** = Problème dans le code JavaScript
**Si le test ne fonctionne pas** = Problème dans le template ou le service

## 📝 Checklist Complète

- [ ] Template utilise les variables exactes : `{{from_name}}`, `{{from_email}}`, etc.
- [ ] Service email est actif et connecté
- [ ] To Email est configuré à `ariaedu55@gmail.com`
- [ ] Reply To est configuré à `{{reply_to}}`
- [ ] Template est **Published** (publié)
- [ ] Service ID et Template ID sont corrects dans `script.js`
- [ ] Vérifié les spams de `ariaedu55@gmail.com`
- [ ] Test direct dans EmailJS fonctionne

## 🆘 Si Rien ne Fonctionne

1. **Créer un nouveau template** avec les variables exactes ci-dessus
2. **Créer un nouveau service email** si nécessaire
3. **Mettre à jour les IDs** dans `script.js`
4. **Tester à nouveau**

## 💡 Astuce : Template Simplifié

Pour tester rapidement, créez un template minimal :

**Sujet :**
```
Contact: {{from_name}}
```

**Contenu :**
```
{{message}}

De: {{from_name}} ({{from_email}})
```

**Settings :**
- To Email: `ariaedu55@gmail.com`
- From Name: `Site Vitrine`
- Reply To: `{{from_email}}`

Si ce template minimal fonctionne, vous pouvez ensuite ajouter les autres variables.
