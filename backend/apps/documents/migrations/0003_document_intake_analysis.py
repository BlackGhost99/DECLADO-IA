from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("documents", "0002_document_languages")]

    operations = [
        migrations.AddField(
            model_name="document",
            name="intake_analysis",
            field=models.JSONField(blank=True, default=dict, editable=False),
        ),
    ]
