"""python manage.py create_superadmin

Creates (or resets the password of) the ONE super admin account.

Values are taken from, in this order:
  1. command-line options   (--username, --email, --password)
  2. environment / .env     (SUPERADMIN_USERNAME, SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD)
  3. an interactive prompt  (the password is never echoed)

The super admin can create and manage every other account (admins, police, hospital, ambulance)
from the app: Admin > Services > Users. There is no public sign-up.
"""
import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = "Create the super admin account (or reset its password)."

    def add_arguments(self, parser):
        parser.add_argument("--username")
        parser.add_argument("--email")
        parser.add_argument("--password")

    def handle(self, *args, **opts):
        username = opts["username"] or os.environ.get("SUPERADMIN_USERNAME") or input("Super admin username: ").strip()
        email = opts["email"] or os.environ.get("SUPERADMIN_EMAIL") or ""
        password = opts["password"] or os.environ.get("SUPERADMIN_PASSWORD")
        if not username:
            raise CommandError("A username is required.")
        if not password:
            password = getpass.getpass("Super admin password: ")
            if password != getpass.getpass("Repeat password: "):
                raise CommandError("Passwords do not match.")
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages))

        user = User.objects.filter(username=username).first()
        if user:
            user.is_superuser = True
            user.is_staff = True
            user.is_active = True
            user.set_password(password)
            if email:
                user.email = email
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Updated super admin '{username}' (password reset)."))
        else:
            User.objects.create_superuser(username=username, email=email, password=password,
                                          first_name="Super Admin")
            self.stdout.write(self.style.SUCCESS(f"Created super admin '{username}'."))
        self.stdout.write("Sign in with it, then create all other accounts from Admin > Services > Users.")
