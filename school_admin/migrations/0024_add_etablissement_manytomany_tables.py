# Generated manually to add ManyToMany tables for Etablissement

from django.db import migrations, models
from django.db.models.deletion import CASCADE


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0023_add_missing_abstractuser_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='EtablissementGroups',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('etablissement', models.ForeignKey(on_delete=CASCADE, to='school_admin.etablissement')),
                ('group', models.ForeignKey(on_delete=CASCADE, to='auth.group')),
            ],
            options={
                'db_table': 'school_admin_etablissement_groups',
            },
        ),
        migrations.CreateModel(
            name='EtablissementUserPermissions',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('etablissement', models.ForeignKey(on_delete=CASCADE, to='school_admin.etablissement')),
                ('permission', models.ForeignKey(on_delete=CASCADE, to='auth.permission')),
            ],
            options={
                'db_table': 'school_admin_etablissement_user_permissions',
            },
        ),
        migrations.AddConstraint(
            model_name='etablissementgroups',
            constraint=models.UniqueConstraint(fields=('etablissement', 'group'), name='school_admin_etablissement_groups_etablissement_id_group_id_uniq'),
        ),
        migrations.AddConstraint(
            model_name='etablissementuserpermissions',
            constraint=models.UniqueConstraint(fields=('etablissement', 'permission'), name='school_admin_etablissement_user_permissions_etablissement_id_permission_id_uniq'),
        ),
    ]
