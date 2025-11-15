from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('school_admin', '0137_note_date_publication_note_note_publiee_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='moyenneperiode',
            name='numero_serie',
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True, verbose_name='Numéro de série du bulletin'),
        ),
        migrations.AddField(
            model_name='moyenneperiode',
            name='qr_code_data',
            field=models.TextField(blank=True, null=True, verbose_name='Payload encodé dans le QR code'),
        ),
        migrations.AddField(
            model_name='moyenneperiode',
            name='qr_code_generated_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Date de génération du QR code'),
        ),
        migrations.AddField(
            model_name='moyenneperiode',
            name='qr_code_image',
            field=models.ImageField(blank=True, null=True, upload_to='bulletins/qrcodes/', verbose_name='Image du QR code du bulletin'),
        ),
        migrations.AddField(
            model_name='moyenneperiode',
            name='signature_numerique',
            field=models.CharField(blank=True, max_length=128, null=True, verbose_name='Signature numérique (SHA-256)'),
        ),
    ]

