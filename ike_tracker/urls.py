from django.contrib import admin
from django.urls import path
from core.views import upload_view, dashboard_view # <--- Dodaj import

urlpatterns = [
    path('admin/', admin.site.urls),
    path('upload/', upload_view, name='upload'),
    path('', dashboard_view, name='dashboard'), # <--- Strona główna to teraz Dashboard
]