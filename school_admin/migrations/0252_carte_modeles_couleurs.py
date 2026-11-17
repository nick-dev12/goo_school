from django.core.validators import RegexValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('school_admin', '0251_rappel_cours_demain')]
    operations = [
        migrations.AddField(model_name='carteidentitepersonnalisation', name='modele',
            field=models.CharField(max_length=20, default='classique', verbose_name='Modèle de carte',
                                   choices=[('classique', 'Classique'), ('moderne', 'Moderne')])),
        *[migrations.AddField(model_name='carteidentitepersonnalisation', name=nom,
            field=models.CharField(max_length=7, default=defaut, verbose_name=label,
                validators=[RegexValidator(r'^#[0-9a-fA-F]{6}$', 'Utilisez une couleur au format #RRGGBB.')]))
          for nom, defaut, label in [
              ('couleur_principale', '#3b82f6', 'Couleur principale'),
              ('couleur_secondaire', '#7c3aed', 'Couleur secondaire'),
              ('couleur_fond', '#ffffff', 'Fond de la carte'),
              ('couleur_texte', '#1f2937', 'Texte de la carte')]],
    ]
