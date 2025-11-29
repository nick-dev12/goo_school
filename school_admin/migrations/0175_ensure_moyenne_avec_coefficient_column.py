# Generated manually - Migration pour s'assurer que la colonne existe

from django.db import migrations


def ensure_column_exists(apps, schema_editor):
    """S'assure que la colonne moyenne_avec_coefficient existe"""
    db_alias = schema_editor.connection.alias
    with schema_editor.connection.cursor() as cursor:
        # Vérifier si la colonne existe
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='school_admin_moyenneperiode' 
            AND column_name='moyenne_avec_coefficient'
        """)
        if not cursor.fetchone():
            # Ajouter la colonne
            cursor.execute("""
                ALTER TABLE school_admin_moyenneperiode 
                ADD COLUMN moyenne_avec_coefficient NUMERIC(8, 2) NULL
            """)


def reverse_migration(apps, schema_editor):
    """Ne rien faire en reverse"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0174_add_moyenne_avec_coefficient_to_moyenneperiode'),
    ]

    operations = [
        migrations.RunPython(ensure_column_exists, reverse_migration),
    ]

