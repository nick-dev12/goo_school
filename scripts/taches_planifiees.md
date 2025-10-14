# Configuration des Tâches Planifiées

## Mise à Jour Automatique des Statuts de Factures

### 1. Commande Django
```bash
# Exécution manuelle
python manage.py mettre_a_jour_statuts_factures

# Mode dry-run (test sans modification)
python manage.py mettre_a_jour_statuts_factures --dry-run
```

### 2. Script Python Autonome
```bash
# Exécution du script
python scripts/mettre_a_jour_statuts_automatique.py
```

### 3. Configuration Cron (Linux/Mac)
```bash
# Éditer le crontab
crontab -e

# Ajouter une tâche quotidienne à 2h du matin
0 2 * * * cd /chemin/vers/goo_school && python scripts/mettre_a_jour_statuts_automatique.py

# Ajouter une tâche hebdomadaire le dimanche à 1h
0 1 * * 0 cd /chemin/vers/goo_school && python scripts/mettre_a_jour_statuts_automatique.py
```

### 4. Configuration Windows (Tâche Planifiée)
1. Ouvrir le "Planificateur de tâches"
2. Créer une tâche de base
3. Nom: "Mise à jour statuts factures"
4. Déclencheur: Quotidien à 2h00
5. Action: Démarrer un programme
   - Programme: `python`
   - Arguments: `scripts/mettre_a_jour_statuts_automatique.py`
   - Dossier de départ: `C:\Users\jomas\Desktop\goo_school`

### 5. Configuration avec Celery (Recommandé pour production)
```python
# Dans settings.py
CELERY_BEAT_SCHEDULE = {
    'mettre-a-jour-statuts-factures': {
        'task': 'school_admin.tasks.mettre_a_jour_statuts_factures',
        'schedule': crontab(hour=2, minute=0),  # Tous les jours à 2h
    },
}
```

## Logs et Monitoring

### Fichiers de Log
- `logs/statuts_factures.log` - Logs détaillés des mises à jour
- Console - Affichage en temps réel

### Monitoring
- Vérifier les logs quotidiennement
- Surveiller les factures en contentieux
- Alertes en cas d'erreur

## Règles de Mise à Jour

### Statuts Automatiques
1. **En retard** : Date d'échéance dépassée
2. **Impayé** : 1 mois de retard
3. **Contentieux** : 2 mois de retard

### Factures Concernées
- Factures avec échéance principale dépassée
- Factures avec échéance du reste à payer dépassée
- Exclut les factures déjà payées complètement

### Fréquence Recommandée
- **Quotidienne** : Pour un suivi précis
- **Hebdomadaire** : Minimum acceptable
- **Manuelle** : En cas de besoin urgent
