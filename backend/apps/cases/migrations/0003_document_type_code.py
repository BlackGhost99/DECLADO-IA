"""Optional precise type per attachment: existing documents remain intentionally unclassified."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="casedocument",
            name="document_type_code",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
    ]
