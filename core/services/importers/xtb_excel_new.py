import pandas as pd
from .base_importer import BaseImporter

class XtbExcelNewImporter(BaseImporter):
    """Importer for the NEW XTB Excel format (Instrument column)."""
    
    def load_dataframe(self):
        try:
            xls = pd.ExcelFile(self.file)
        except Exception as e:
            raise ValueError(f"Excel Error: {e}")

        target_sheet = None
        for sheet in xls.sheet_names:
            if "CASH" in sheet.upper():
                target_sheet = sheet
                break
        if not target_sheet: target_sheet = xls.sheet_names[0]

        df_preview = pd.read_excel(self.file, sheet_name=target_sheet, header=None, nrows=40)
        header_idx = self._find_header_row(df_preview)

        if header_idx is None:
            return None

        self.file.seek(0)
        return pd.read_excel(self.file, sheet_name=target_sheet, header=header_idx)

    def _find_header_row(self, df):
        for idx, row in df.iterrows():
            s = " ".join([str(v) for v in row.fillna('').values])
            # New format specific: Instrument
            if "ID" in s and "Type" in s and "Instrument" in s:
                return idx
        return None