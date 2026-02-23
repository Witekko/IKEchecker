import pandas as pd
from .base_importer import BaseImporter

class XtbCsvImporter(BaseImporter):
    def load_dataframe(self):
        attempts = [
            {'encoding': 'utf-16', 'sep': '\t'},
            {'encoding': 'utf-16', 'sep': ';'},
            {'encoding': 'utf-16', 'sep': ','},
            {'encoding': 'utf-8', 'sep': ';'},
            {'encoding': 'utf-8', 'sep': ','},
            {'encoding': 'cp1250', 'sep': ';'}
        ]

        df_raw = None
        for params in attempts:
            try:
                self.file.seek(0)
                temp = pd.read_csv(self.file, encoding=params['encoding'], sep=params['sep'])
                if len(temp.columns) > 1:
                    df_raw = temp
                    break
            except:
                continue

        if df_raw is None:
            raise ValueError("Nie udało się odczytać pliku CSV (błąd kodowania).")

        header_idx = self._find_header_row(df_raw.head(40))

        if header_idx is None:
            s = " ".join([str(c) for c in df_raw.columns])
            if "ID" in s and "Type" in s:
                return df_raw
            else:
                raise ValueError("Nie znaleziono nagłówka w pliku CSV.")

        new_header = df_raw.iloc[header_idx]
        df = df_raw[header_idx + 1:].copy()
        df.columns = new_header
        return df

    def _find_header_row(self, df):
        for idx, row in df.iterrows():
            s = " ".join([str(v) for v in row.fillna('').values])
            if "ID" in s and "Type" in s:
                return idx
        return None