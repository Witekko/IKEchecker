from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from .forms import UploadFileForm, CustomUserCreationForm

# Teraz importujemy gotowe klocki z services
from .services import (
    process_xtb_file,
    get_dashboard_context,
    get_dividend_context,
    get_asset_details_context
)


@login_required
def upload_view(request):
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                stats = process_xtb_file(request.FILES['file'], request.user)
                messages.success(request, f"Sukces! Dodano: {stats['added']}, Pominięto: {stats['skipped']}.")
                return redirect('/admin/core/transaction/')
            except Exception as e:
                messages.error(request, f"Błąd: {e}")
    else:
        form = UploadFileForm()
    return render(request, 'upload.html', {'form': form})


@login_required
def dashboard_view(request):
    context = get_dashboard_context(request.user)
    if 'error' in context:
        return render(request, 'dashboard.html', {'error': context['error']})
    return render(request, 'dashboard.html', context)

# --- NOWA FUNKCJA (WKLEJ POD DASHBOARD_VIEW) ---
@login_required
def assets_list_view(request):
    context = get_dashboard_context(request.user)
    if 'error' in context:
        return render(request, 'dashboard.html', {'error': context['error']}) # Fallback
    return render(request, 'assets_list.html', context)
@login_required
def dividends_view(request):
    context = get_dividend_context(request.user)
    return render(request, 'dividends.html', context)


@login_required
def asset_details_view(request, symbol):
    # Cała logika przeniesiona do serwisu!
    context = get_asset_details_context(request.user, symbol)

    if 'error' in context:
        return render(request, 'dashboard.html', {'error': context['error']})

    return render(request, 'asset_details.html', context)
def register_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user) # Automatyczne logowanie po rejestracji
            messages.success(request, "Konto utworzone pomyślnie!")
            return redirect('dashboard')
        else:
            messages.error(request, "Błąd rejestracji. Sprawdź formularz.")
    else:
        form = CustomUserCreationForm()
    return render(request, 'register.html', {'form': form})