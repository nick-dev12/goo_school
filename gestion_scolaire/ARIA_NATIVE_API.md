# API AriaNative - Guide d'utilisation

Cette application Flutter embarque votre application web Django dans une WebView et expose une API JavaScript (`AriaNative`) pour accéder aux fonctionnalités natives du téléphone.

## Fonctionnalités disponibles

### 1. Accès à la caméra

Permet de prendre une photo avec la caméra du téléphone.

```javascript
// Utilisation dans votre application Django
try {
  const result = await window.AriaNative.requestCamera();
  if (result.success) {
    // result.image contient l'image en base64
    // result.path contient le chemin du fichier
    console.log('Image capturée:', result.image);
    
    // Vous pouvez envoyer l'image à votre serveur Django
    const formData = new FormData();
    formData.append('image', result.image);
    
    fetch('/api/upload-image/', {
      method: 'POST',
      body: formData,
      headers: {
        'X-CSRFToken': getCookie('csrftoken')
      }
    });
  }
} catch (error) {
  console.error('Erreur caméra:', error);
}
```

### 2. Accès à la localisation GPS

Récupère la position GPS actuelle de l'utilisateur.

```javascript
// Utilisation dans votre application Django
try {
  const location = await window.AriaNative.requestLocation();
  if (location.success) {
    console.log('Latitude:', location.latitude);
    console.log('Longitude:', location.longitude);
    console.log('Précision:', location.accuracy);
    
    // Envoyer la localisation à votre serveur Django
    fetch('/api/save-location/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
      },
      body: JSON.stringify({
        latitude: location.latitude,
        longitude: location.longitude,
        accuracy: location.accuracy
      })
    });
  }
} catch (error) {
  console.error('Erreur localisation:', error);
}
```

### 3. Stockage local

Sauvegarder et récupérer des données localement sur le téléphone.

```javascript
// Sauvegarder des données
try {
  await window.AriaNative.saveData({
    'user_token': 'abc123',
    'user_preferences': JSON.stringify({theme: 'dark'}),
    'last_sync': new Date().toISOString()
  });
  console.log('Données sauvegardées');
} catch (error) {
  console.error('Erreur sauvegarde:', error);
}

// Récupérer des données
try {
  const token = await window.AriaNative.getData('user_token');
  console.log('Token:', token);
} catch (error) {
  console.error('Erreur récupération:', error);
}
```

### 4. Notifications

Afficher des notifications natives.

```javascript
// Afficher une notification
try {
  await window.AriaNative.showNotification(
    'Nouvelle note',
    'Vous avez reçu une nouvelle note en Mathématiques'
  );
} catch (error) {
  console.error('Erreur notification:', error);
}
```

## Exemple d'intégration dans un template Django

```html
<!-- Dans votre template Django -->
<script>
// Vérifier si l'API est disponible (dans l'app mobile)
if (window.AriaNative) {
  console.log('Application mobile détectée');
  
  // Exemple: Prendre une photo pour un profil
  document.getElementById('take-photo-btn').addEventListener('click', async function() {
    try {
      const result = await window.AriaNative.requestCamera();
      if (result.success) {
        // Afficher l'image dans un élément img
        document.getElementById('profile-image').src = result.image;
        
        // Envoyer au serveur
        const form = document.getElementById('profile-form');
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'profile_image';
        input.value = result.image;
        form.appendChild(input);
        form.submit();
      }
    } catch (error) {
      alert('Erreur lors de la capture: ' + error.message);
    }
  });
  
  // Exemple: Récupérer la localisation pour l'assiduité
  document.getElementById('check-in-btn').addEventListener('click', async function() {
    try {
      const location = await window.AriaNative.requestLocation();
      if (location.success) {
        // Envoyer la localisation au serveur
        fetch('{% url "check_in" %}', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': '{{ csrf_token }}'
          },
          body: JSON.stringify({
            latitude: location.latitude,
            longitude: location.longitude,
            timestamp: new Date().toISOString()
          })
        });
      }
    } catch (error) {
      alert('Erreur de localisation: ' + error.message);
    }
  });
} else {
  console.log('Application web standard');
  // Comportement alternatif pour le navigateur web
}
</script>
```

## Gestion des erreurs

Toutes les méthodes retournent une Promise qui peut être rejetée. Toujours utiliser try/catch :

```javascript
try {
  const result = await window.AriaNative.requestCamera();
  // Traiter le succès
} catch (error) {
  // Gérer l'erreur
  console.error('Erreur:', error.message);
  // Afficher un message à l'utilisateur
  alert('Impossible d\'accéder à la caméra. Veuillez vérifier les permissions.');
}
```

## Permissions

L'application demande automatiquement les permissions nécessaires au démarrage :
- Caméra
- Stockage
- Localisation
- Notifications

Si une permission est refusée, l'API retournera une erreur appropriée.

## Notes importantes

1. L'API `AriaNative` n'est disponible que dans l'application mobile Flutter, pas dans un navigateur web standard.
2. Toujours vérifier la disponibilité de l'API avant de l'utiliser : `if (window.AriaNative)`
3. Les images retournées sont en format base64, vous pouvez les convertir côté serveur Django si nécessaire.
4. Le stockage local persiste même après la fermeture de l'application.

