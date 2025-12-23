from django.contrib import admin
from django.urls import path
from core.views import upload_view, dashboard_view, asset_details_view, dividends_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('upload/', upload_view, name='upload'),
    path('', dashboard_view, name='dashboard'),
    path('asset/<str:symbol>/', asset_details_view, name='asset_details'),
    path('dividends/', dividends_view, name='dividends'),
]