from django.contrib import admin
from django.urls import path
from core.views import upload_view, dashboard_view, asset_details_view # <--- DOPISZ asset_details_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('upload/', upload_view, name='upload'),
    path('', dashboard_view, name='dashboard'),
    # --- NOWA LINIA: ---
    path('asset/<str:symbol>/', asset_details_view, name='asset_details'),
]