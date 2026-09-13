from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0218_matiere_unique_module_partage'),
    ]

    operations = [
        TrigramExtension(),
        UnaccentExtension(),
    ]
