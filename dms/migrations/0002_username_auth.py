import django.contrib.auth.validators
from django.db import migrations, models


def populate_usernames(apps, schema_editor):
    User = apps.get_model("dms", "User")
    used = set()
    for user in User.objects.order_by("pk"):
        base = (user.username or user.email or f"user-{user.pk}").strip().lower()[:150]
        candidate = base
        suffix = 1
        while not candidate or candidate in used:
            tail = f"-{suffix}"
            candidate = f"{base[:150 - len(tail)]}{tail}"
            suffix += 1
        if user.username != candidate:
            User.objects.filter(pk=user.pk).update(username=candidate)
        used.add(candidate)


class Migration(migrations.Migration):
    dependencies = [("dms", "0001_initial")]

    operations = [
        migrations.RunPython(populate_usernames, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="username",
            field=models.CharField(
                max_length=150,
                unique=True,
                validators=[django.contrib.auth.validators.UnicodeUsernameValidator()],
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.RenameField(
            model_name="loginattempt",
            old_name="email",
            new_name="identifier",
        ),
        migrations.AlterField(
            model_name="loginattempt",
            name="identifier",
            field=models.CharField(max_length=150, unique=True),
        ),
    ]
