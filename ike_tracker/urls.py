from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from core import views
urlpatterns = [
    # --- PANEL ADMINA ---
    # Zmieniony URL admina dla bezpieczeństwa
    path('management-portal-secure/', admin.site.urls),

    # --- APLIKACJA (CORE) ---
    path('', auth_views.LoginView.as_view(template_name='login.html', redirect_authenticated_user=True), name='login'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('assets/', views.assets_list_view, name='assets_list'),
    path('demo-login/', views.demo_login_view, name='demo_login'),

    # --- NOWA ŚCIEŻKA: ZARZĄDZANIE AKTYWAMI ---
    path('assets/manage/', views.manage_assets_view, name='manage_assets'),
    # ------------------------------------------

    path('upload/', views.upload_view, name='upload'),
    path('dividends/', views.dividends_view, name='dividends'),
    path('asset/<str:symbol>/', views.asset_details_view, name='asset_details'),
    path('asset/<str:symbol>/feedback/', views.submit_asset_feedback_view, name='submit_asset_feedback'),
    path('watchlist/add/', views.add_to_watchlist_view, name='add_to_watchlist'),
    path('watchlist/remove/<str:symbol>/', views.remove_from_watchlist_view, name='remove_from_watchlist'),
    path('taxes/', views.taxes_view, name='taxes'),

    # --- PORTFEL ---
    path('portfolio/switch/<int:portfolio_id>/', views.switch_portfolio_view, name='switch_portfolio'),
    path('portfolio/create/', views.create_portfolio_view, name='create_portfolio'),
    path('portfolio/settings/', views.portfolio_settings_view, name='portfolio_settings'),
    path('settings/corporate-action/spinoff/', views.corporate_action_spinoff_view, name='corporate_action_spinoff'),
    path('settings/delete-transaction/<int:transaction_id>/', views.delete_transaction_view, name='delete_transaction'),
    # --- AUTORYZACJA ---
    path('register/', views.register_view, name='register'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
]