from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("documents", "0001_initial")]
    operations = [
        migrations.AddField(model_name="document", name="detected_locale",
            field=models.CharField(max_length=2, blank=True, default="", choices=[
                ("", "Unknown"), ("fr", "Français"), ("en", "English"),
                ("es", "Español"), ("ar", "العربية")])),
        migrations.AddField(model_name="document", name="language_detection",
            field=models.JSONField(default=dict, blank=True)),
    ]
