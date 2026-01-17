# core/services/__init__.py

from .importer import process_xtb_file
from .portfolio import get_dashboard_context, get_asset_details_context, get_assets_view_context
from .dividends import get_dividend_context
from .taxes import get_taxes_context
from .actions import add_manual_transaction
from .market import fetch_asset_metadata, get_current_currency_rates
from .news import get_asset_news
from .analytics import analyze_history, analyze_holdings