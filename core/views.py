from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import UploadFileForm

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