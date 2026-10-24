from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_user_interface_locale"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TotpDevice",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("encrypted_secret", models.TextField()),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("last_step", models.BigIntegerField(default=-1)),
                ("recovery_hashes", models.JSONField(default=list)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="totp_device",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
