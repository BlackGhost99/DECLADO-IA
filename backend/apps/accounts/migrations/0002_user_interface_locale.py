from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="user",
            name="interface_locale",
            field=models.CharField(max_length=2, default="fr", choices=[
                ("fr", "Français"), ("en", "English"), ("es", "Español"), ("ar", "العربية")
            ]),
        ),
    ]
