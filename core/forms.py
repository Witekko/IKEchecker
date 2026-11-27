from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Portfolio, Transaction, Asset

class UploadFileForm(forms.Form):
    file = forms.FileField(label="Wybierz raport XTB (.xlsx)")
class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email']

    def clean_email(self):
        # Unique, case-insensitive: one e-mail = one account (Google login links by e-mail)
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this e-mail already exists.")
        return email

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Stylujemy każde pole, żeby było ciemne
        for field in self.fields:
            self.fields[field].widget.attrs.update({
                'class': 'form-control bg-dark text-white border-secondary border-opacity-50 mb-3',
                'placeholder': f'Enter {field}'
            })
# core/forms.py (DODAJ NA KOŃCU PLIKU)



class PortfolioSettingsForm(forms.ModelForm):
    class Meta:
        model = Portfolio
        fields = ['name', 'portfolio_type', 'currency']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control bg-dark text-white border-secondary'}),
            'portfolio_type': forms.Select(attrs={'class': 'form-select bg-dark text-white border-secondary'}),
            'currency': forms.Select(choices=[
                ('PLN', 'PLN (Polish Złoty)'),
                ('USD', 'USD (US Dollar)'),
                ('EUR', 'EUR (Euro)'),
                ('GBP', 'GBP (British Pound)'),
            ], attrs={'class': 'form-select bg-dark text-white border-secondary'}),
        }


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control bg-dark text-white border-secondary', 'required': 'true'}),
        }