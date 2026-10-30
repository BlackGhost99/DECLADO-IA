from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("organizations", "0003_business_profiles_agencies")]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="max_agencies",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
