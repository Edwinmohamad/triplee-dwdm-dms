from datetime import timedelta
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import DocumentComment, InstallationBatch, LoginAttempt, Review, User


class InitialSetupForm(forms.Form):
    full_name = forms.CharField(label="Nama lengkap", max_length=160)
    username = forms.CharField(label="Username", max_length=150)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Ulangi password", widget=forms.PasswordInput)

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            raise ValidationError("Konfirmasi password tidak sama.")
        if cleaned.get("password1") and len(cleaned["password1"]) < 10:
            raise ValidationError("Password minimal 10 karakter.")
        return cleaned

    def save(self):
        return User.objects.create_superuser(
            username=self.cleaned_data["username"],
            full_name=self.cleaned_data["full_name"],
            password=self.cleaned_data["password1"],
            must_change_password=False,
        )


class SecureAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="Username", widget=forms.TextInput(attrs={"autofocus": True}))

    def clean(self):
        identifier = (self.data.get("username") or "").strip().lower()
        normalized_data = self.data.copy()
        normalized_data["username"] = identifier
        self.data = normalized_data
        attempt, _ = LoginAttempt.objects.get_or_create(identifier=identifier or "unknown")
        if attempt.is_locked:
            remaining = max(1, int((attempt.locked_until - timezone.now()).total_seconds() / 60) + 1)
            raise ValidationError(f"Akun dikunci sementara. Coba lagi dalam {remaining} menit.")
        try:
            cleaned = super().clean()
        except ValidationError:
            attempt.attempts += 1
            if attempt.attempts >= 5:
                attempt.locked_until = timezone.now() + timedelta(minutes=15)
                attempt.attempts = 0
            attempt.save(update_fields=["attempts", "locked_until", "updated_at"])
            raise
        attempt.attempts = 0
        attempt.locked_until = None
        attempt.save(update_fields=["attempts", "locked_until", "updated_at"])
        return cleaned


class UserCreateForm(forms.ModelForm):
    temporary_password = forms.CharField(label="Password sementara", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["full_name", "username", "role", "is_active"]

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        if actor and actor.role != User.Role.SUPER_ADMIN:
            self.fields["role"].choices = [
                choice for choice in User.Role.choices if choice[0] != User.Role.SUPER_ADMIN
            ]

    def clean_temporary_password(self):
        value = self.cleaned_data["temporary_password"]
        if len(value) < 10:
            raise ValidationError("Password minimal 10 karakter.")
        return value

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["temporary_password"])
        user.must_change_password = True
        if commit:
            user.save()
        return user


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["full_name", "role", "is_active"]

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        if actor and actor.role != User.Role.SUPER_ADMIN:
            self.fields["role"].choices = [
                choice for choice in User.Role.choices if choice[0] != User.Role.SUPER_ADMIN
            ]


class BatchUpdateForm(forms.ModelForm):
    class Meta:
        model = InstallationBatch
        fields = ["label", "pic_name", "scheduled_date", "installed_at", "status", "notes"]
        widgets = {
            "scheduled_date": forms.DateInput(attrs={"type": "date"}),
            "installed_at": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class DocumentUploadForm(forms.Form):
    file = forms.FileField(label="Pilih dokumen")
    change_summary = forms.CharField(
        label="Catatan revisi",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Contoh: melengkapi foto power connection"}),
    )

    allowed_extensions = {".pdf", ".docx", ".xlsx", ".jpg", ".jpeg", ".png", ".zip"}

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        ext = Path(uploaded.name).suffix.lower()
        if ext not in self.allowed_extensions:
            raise ValidationError("Format file tidak diizinkan.")
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if uploaded.size > max_bytes:
            raise ValidationError(f"Ukuran file maksimal {settings.MAX_UPLOAD_SIZE_MB} MB.")
        return uploaded


class ReviewForm(forms.Form):
    decision = forms.ChoiceField(label="Keputusan", choices=Review.Decision.choices)
    comment = forms.CharField(label="Komentar", required=False, widget=forms.Textarea(attrs={"rows": 4}))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("decision") in {Review.Decision.REVISION_REQUIRED, Review.Decision.REJECTED} and not cleaned.get("comment", "").strip():
            raise ValidationError("Komentar wajib untuk Request Revision atau Reject.")
        return cleaned


class CommentForm(forms.ModelForm):
    class Meta:
        model = DocumentComment
        fields = ["body"]
        labels = {"body": "Komentar"}
        widgets = {"body": forms.Textarea(attrs={"rows": 3, "placeholder": "Tambahkan catatan atau pertanyaan..."})}
