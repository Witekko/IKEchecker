from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from core import views

urlpatterns = [
    # --- PANEL ADMINA ---
    path('admin/', admin.site.urls),

    # --- APLIKACJA (CORE) ---
    path('', views.dashboard_view, name='dashboard'),
    path('assets/', views.assets_list_view, name='assets_list'),

    # --- NOWA ŚCIEŻKA: ZARZĄDZANIE AKTYWAMI ---
    path('assets/manage/', views.manage_assets_view, name='manage_assets'),
    # ------------------------------------------

    path('upload/', views.upload_view, name='upload'),
    path('dividends/', views.dividends_view, name='dividends'),
    path('asset/<str:symbol>/', views.asset_details_view, name='asset_details'),
    path('taxes/', views.taxes_view, name='taxes'),

    # --- PORTFEL ---
    path('portfolio/switch/<int:portfolio_id>/', views.switch_portfolio_view, name='switch_portfolio'),
    path('portfolio/create/', views.create_portfolio_view, name='create_portfolio'),
    path('portfolio/settings/', views.portfolio_settings_view, name='portfolio_settings'),
    path('settings/delete-transaction/<int:transaction_id>/', views.delete_transaction_view, name='delete_transaction'),
    # --- AUTORYZACJA ---
    path('register/', views.register_view, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
]