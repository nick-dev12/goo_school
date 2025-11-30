# 📋 Justifications des Permissions pour Google Play Store

Lors de la soumission de votre application sur Google Play Store, vous devrez justifier certaines permissions sensibles. Voici les justifications recommandées :

## 🔐 Permissions à Justifier

### 1. CAMERA (android.permission.CAMERA)
**Justification recommandée** :
```
L'application Aria permet aux utilisateurs (élèves, enseignants, parents) de prendre des photos directement depuis l'application pour :
- Ajouter une photo de profil
- Photographier des devoirs et exercices
- Capturer des documents pour les partager avec les enseignants
- Prendre des photos lors d'activités scolaires

Cette fonctionnalité est essentielle pour l'expérience utilisateur de la plateforme éducative.
```

### 2. ACCESS_FINE_LOCATION / ACCESS_COARSE_LOCATION
**Justification recommandée** :
```
L'application utilise la localisation GPS pour :
- Enregistrer la présence des élèves avec géolocalisation
- Vérifier que les utilisateurs sont bien sur le site de l'établissement lors de certaines actions
- Fournir des fonctionnalités de sécurité pour les parents (suivi de localisation des enfants)

La localisation est uniquement utilisée lorsque l'utilisateur active explicitement cette fonctionnalité.
```

### 3. READ_EXTERNAL_STORAGE / WRITE_EXTERNAL_STORAGE
**Justification recommandée** :
```
L'application nécessite l'accès au stockage pour :
- Permettre aux utilisateurs de télécharger et sauvegarder des bulletins de notes
- Partager des documents éducatifs (devoirs, cours, exercices)
- Exporter des données (bulletins, relevés de notes) au format PDF
- Permettre aux enseignants de joindre des fichiers aux devoirs

L'accès au stockage est essentiel pour le fonctionnement complet de la plateforme éducative.
```

### 4. POST_NOTIFICATIONS (Android 13+)
**Justification recommandée** :
```
Les notifications sont utilisées pour :
- Informer les élèves et parents de nouvelles notes publiées
- Rappeler les devoirs à rendre
- Notifier des messages importants de l'établissement
- Alerter en cas d'absences ou retards

Les notifications sont essentielles pour maintenir la communication entre l'école, les élèves et les parents.
```

---

## 📝 Comment Remplir dans Google Play Console

1. Allez dans **"Politique de l'application"** > **"Permissions"**
2. Pour chaque permission sensible, cliquez sur **"Justifier"**
3. Copiez-collez la justification correspondante ci-dessus
4. Assurez-vous que votre justification correspond bien à l'utilisation réelle dans votre code

---

## ⚠️ Important

- **Soyez honnête** : Ne déclarez que les permissions que vous utilisez réellement
- **Soyez précis** : Expliquez clairement pourquoi chaque permission est nécessaire
- **Soyez concis** : Google Play préfère des justifications courtes et claires

---

## ✅ Permissions Non Sensibles (Pas de Justification Requise)

Ces permissions ne nécessitent pas de justification :
- `INTERNET` - Standard pour les applications web
- `ACCESS_NETWORK_STATE` - Standard pour vérifier la connexion
- `VIBRATE` - Standard pour les notifications
- `RECEIVE_BOOT_COMPLETED` - Standard pour les notifications programmées

---

## 🔗 Références

- [Documentation Google Play - Permissions](https://support.google.com/googleplay/android-developer/answer/9888170)
- [Politique de confidentialité requise](https://support.google.com/googleplay/android-developer/answer/10787469)

