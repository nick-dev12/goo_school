from django import forms
from django.core.validators import RegexValidator


class ProfesseurOtpRequestForm(forms.Form):
    """
    Formulaire pour initier la connexion OTP des professeurs.
    """

    phone_number = forms.CharField(
        max_length=25,
        label="Numéro de téléphone",
        validators=[
            RegexValidator(
                regex=r"^[0-9+ ]{8,}$",
                message="Le numéro doit contenir uniquement des chiffres, espaces ou '+'.",
            )
        ],
    )

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"]
        normalized = phone.replace(" ", "").replace("-", "")
        if not normalized.startswith("+") and not normalized.isdigit():
            raise forms.ValidationError(
                "Le format du numéro n'est pas valide. Exemple: +237699112233."
            )
        if normalized.startswith("+") and len(normalized) < 10:
            raise forms.ValidationError(
                "Le numéro international doit comporter au moins 10 chiffres."
            )
        if normalized.isdigit() and len(normalized) < 8:
            raise forms.ValidationError(
                "Le numéro local doit comporter au moins 8 chiffres."
            )
        return normalized


class ProfesseurOtpVerifyForm(forms.Form):
    """
    Formulaire pour vérifier l'OTP saisi par le professeur.
    """

    otp_code = forms.CharField(
        max_length=6,
        min_length=6,
        label="Code de validation",
        validators=[
            RegexValidator(
                regex=r"^\d{6}$",
                message="Le code doit être un nombre de 6 chiffres.",
            )
        ],
    )
    otp_token = forms.UUIDField(widget=forms.HiddenInput())

