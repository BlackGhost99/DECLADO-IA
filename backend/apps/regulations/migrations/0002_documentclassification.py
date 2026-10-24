from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("regulations", "0001_initial"),
        ("cases", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentClassification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("confirmed_at", models.DateTimeField(auto_now_add=True)),
                ("reason", models.CharField(max_length=300)),
                (
                    "case_document",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="confirmed_classification",
                        to="cases.casedocument",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"),
                ),
                (
                    "document_type",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="regulations.documenttype"),
                ),
                (
                    "confirmed_by",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
                ),
            ],
        )
    ]
