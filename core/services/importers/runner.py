import pandas as pd
import logging
from django.db.models import Q
from core.models import Transaction
from .xtb_excel_old import XtbExcelOldImporter
from .xtb_excel_new import XtbExcelNewImporter
from .xtb_csv import XtbCsvImporter

logger = logging.getLogger('core')

def process_import(uploaded_file, portfolio_obj, overwrite_manual=False):
    filename = uploaded_file.name.lower()
    importer = None

    if filename.endswith(('.xlsx', '.xls')):
        # Try New Format First
        importer = XtbExcelNewImporter(uploaded_file, portfolio_obj)
        try:
            df = importer.load_dataframe()
            if df is None:
                # Fallback to Old Format
                importer = XtbExcelOldImporter(uploaded_file, portfolio_obj)
        except Exception:
             importer = XtbExcelOldImporter(uploaded_file, portfolio_obj)
             
    elif filename.endswith('.csv'):
        importer = XtbCsvImporter(uploaded_file, portfolio_obj)
    else:
        raise ValueError("Nieobsługiwany format pliku. Użyj .xlsx lub .csv")

    # --- LOGIKA NADPISYWANIA I CZYSZCZENIA ŚMIECI ---
    if overwrite_manual:
        df = importer.load_dataframe()
        if df is not None and not df.empty:
            if 'Time' in df.columns:
                try:
                    dates = pd.to_datetime(df['Time'], errors='coerce').dropna()
                    if not dates.empty:
                        min_date = dates.min()
                        max_date = dates.max()
                        max_date_extended = max_date.replace(hour=23, minute=59, second=59, microsecond=999999)

                        deleted_count, _ = Transaction.objects.filter(
                            portfolio=portfolio_obj,
                            date__range=(min_date, max_date_extended)
                        ).filter(
                            Q(xtb_id__startswith='MAN-') | Q(xtb_id__isnull=True)
                        ).delete()

                        logger.info(f"Usunięto {deleted_count} transakcji (MAN lub NULL ID) kolidujących z importem.")
                except Exception as e:
                    logger.warning(f"Nie udało się wyczyścić manualnych: {e}")

            uploaded_file.seek(0)

    return importer.process()