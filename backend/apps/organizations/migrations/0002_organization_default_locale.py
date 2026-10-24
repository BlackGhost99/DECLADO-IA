from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("organizations", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="organization",
            name="default_locale",
            field=models.CharField(max_length=2, default="fr", choices=[
                ("fr", "Français"), ("en", "English"), ("es", "Español"), ("ar", "العربية")
            ]),
        ),
    ]
