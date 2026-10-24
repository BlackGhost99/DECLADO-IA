from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_totpdevice")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_platform_operator",
            field=models.BooleanField(default=False),
        ),
    ]
