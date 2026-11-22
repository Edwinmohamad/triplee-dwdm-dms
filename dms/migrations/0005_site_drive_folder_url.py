from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("dms", "0004_document_attachments")]

    operations = [
        migrations.AddField(
            model_name="site",
            name="drive_folder_url",
            field=models.URLField(blank=True, max_length=500),
        ),
    ]
