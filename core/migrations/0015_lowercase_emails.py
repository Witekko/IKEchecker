"""
Lowercases e-mails in auth.User and allauth's EmailAddress.

allauth looks up users by the lowercased e-mail when linking a Google login,
so an account stored as "Jan@Example.com" would not be found. New registrations
already store e-mails lowercased (CustomUserCreationForm.clean_email).

E-mails that differ only by case between several rows (e.g. two accounts
"a@x.com" and "A@x.com") are NOT changed: merging them could link the wrong
person's data. They are printed to the deploy log for manual review.
"""
from collections import defaultdict

from django.conf import settings
from django.db import migrations


def _lowercase(queryset, label):
    groups = defaultdict(list)
    for pk, email in queryset.exclude(email="").values_list("pk", "email"):
        groups[email.strip().lower()].append((pk, email))

    changed, conflicts = 0, []
    for lowered, rows in groups.items():
        if len(rows) > 1:
            conflicts.append(lowered)
            continue
        pk, email = rows[0]
        if email != lowered:
            queryset.filter(pk=pk).update(email=lowered)
            changed += 1

    print(f"\n  [lowercase_emails] {label}: {changed} lowercased", end="")
    if conflicts:
        print(f", {len(conflicts)} left unchanged (case-only duplicates, review manually): "
              + ", ".join(sorted(conflicts)), end="")
    return changed, conflicts


def lowercase_emails(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    EmailAddress = apps.get_model("account", "EmailAddress")
    _lowercase(User.objects.all(), "User.email")
    _lowercase(EmailAddress.objects.all(), "EmailAddress.email")
    print()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_userannouncementread"),
        ("account", "0009_emailaddress_unique_primary_email"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Not reversible in a meaningful way (original casing is not stored): reverse is a no-op.
        migrations.RunPython(lowercase_emails, migrations.RunPython.noop),
    ]
