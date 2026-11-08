# Generated for staging engine self-test categorization.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("supervision", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="operationalevent",
            name="category",
            field=models.CharField(
                choices=[
                    ("antivirus", "Antivirus"),
                    ("document", "Pièce refusée"),
                    ("request", "Action refusée"),
                    ("server", "Erreur serveur"),
                    ("engine", "Diagnostic moteur"),
                ],
                max_length=20,
            ),
        ),
    ]
