from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("dms", "0002_username_auth")]

    operations = [
        migrations.RenameField(
            model_name="documentversion",
            old_name="drive_file_id",
            new_name="storage_key",
        ),
        migrations.AlterField(
            model_name="documentversion",
            name="storage_key",
            field=models.CharField(max_length=500, unique=True),
        ),
        migrations.RenameField(
            model_name="backuprecord",
            old_name="drive_file_id",
            new_name="storage_key",
        ),
        migrations.AlterField(
            model_name="backuprecord",
            name="storage_key",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.DeleteModel(name="GoogleDriveCredential"),
    ]
