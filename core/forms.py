from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Portfolio, Transaction, Asset

class UploadFileForm(forms.Form):
    file = forms.FileField(label="Wybierz raport XTB (.xlsx)")
class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'email']

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
            'currency': forms.TextInput(attrs={'class': 'form-control bg-dark text-white border-secondary', 'readonly': 'readonly'}),
        }