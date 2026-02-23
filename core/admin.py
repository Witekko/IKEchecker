from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Asset, Portfolio, Transaction, PriceHistory, AssetFeedback, Watchlist

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'yahoo_ticker', 'currency', 'name')
    search_fields = ('symbol', 'name')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'type', 'asset', 'amount', 'quantity', 'portfolio')
    list_filter = ('type', 'asset')
    search_fields = ('xtb_id', 'comment')

@admin.register(AssetFeedback)
class AssetFeedbackAdmin(admin.ModelAdmin):
    list_display = ('asset', 'user', 'resolved', 'created_at')
    list_filter = ('resolved',)
    search_fields = ('asset__symbol', 'user__username', 'message')

admin.site.register(Portfolio)
admin.site.register(PriceHistory)
admin.site.register(Watchlist)