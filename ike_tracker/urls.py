from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from core import views  # Upewnij się, że ten import jest poprawny

urlpatterns = [
    # --- PANEL ADMINA ---
    path('admin/', admin.site.urls),

    # --- APLIKACJA (CORE) ---
    path('', views.dashboard_view, name='dashboard'),

    # !!! TO JEST LINIA, KTÓREJ BRAKUJE LUB JEST BŁĘDNA !!!
    path('assets/', views.assets_list_view, name='assets_list'),
    # -----------------------------------------------------

    path('upload/', views.upload_view, name='upload'),
    path('dividends/', views.dividends_view, name='dividends'),
    path('asset/<str:symbol>/', views.asset_details_view, name='asset_details'),
    path('taxes/', views.taxes_view, name='taxes'),
# --- PORTFEL---
    path('portfolio/switch/<int:portfolio_id>/', views.switch_portfolio_view, name='switch_portfolio'),
    path('portfolio/create/', views.create_portfolio_view, name='create_portfolio'),
    # --- AUTORYZACJA ---
    path('register/', views.register_view, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
]