import pandas as pd
from .base_importer import BaseImporter

class XtbExcelOldImporter(BaseImporter):
    """Importer for the OLD XTB Excel format (Symbol column)."""
    
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
            # If not found, this importer is not applicable
            return None

        self.file.seek(0)
        df = pd.read_excel(self.file, sheet_name=target_sheet, header=header_idx)
        return self._consolidate_sales(df)

    def _find_header_row(self, df):
        for idx, row in df.iterrows():
            s = " ".join([str(v) for v in row.fillna('').values])
            # Old format specific: Symbol
            if "ID" in s and "Type" in s and "Symbol" in s:
                return idx
        return None

    def _consolidate_sales(self, df):
        if df is None or df.empty: return df
        
        df.columns = [str(c).strip() for c in df.columns]
        if not all(col in df.columns for col in ['Time', 'Symbol', 'Type', 'Amount']):
            return df
            
        rows = df.to_dict('records')
        
        from collections import defaultdict
        groups = defaultdict(list)
        for i, row in enumerate(rows):
            time_val = row.get('Time')
            sym_val = row.get('Symbol')
            # Group by exactly matching time and symbol
            groups[(time_val, sym_val)].append(i)
                
        skip_indices = set()
        consolidated = []
        
        for i, row in enumerate(rows):
            if i in skip_indices:
                continue
                
            t1 = str(row.get('Type', '')).strip().lower()
            if t1 in ['close trade', 'stock sale', 'stock sell']:
                time_val = row.get('Time')
                sym_val = row.get('Symbol')
                
                group_indices = groups.get((time_val, sym_val), [])
                matched_idx = None
                for j in group_indices:
                    if j <= i or j in skip_indices: continue
                    t2 = str(rows[j].get('Type', '')).strip().lower()
                    if (t1 == 'close trade' and t2 in ['stock sale', 'stock sell']) or \
                       (t1 in ['stock sale', 'stock sell'] and t2 == 'close trade'):
                        matched_idx = j
                        break
                        
                if matched_idx is not None:
                    # We found a pair! Combine them.
                    row2 = rows[matched_idx]
                    amt1 = self._safe_amount(row.get('Amount'))
                    amt2 = self._safe_amount(row2.get('Amount'))
                    
                    # Ensure the saved row is the 'Stock sale' row (which holds price/quantity)
                    base_row = row2.copy() if t1 == 'close trade' else row.copy()
                    base_row['Amount'] = amt1 + amt2
                    
                    consolidated.append(base_row)
                    skip_indices.add(matched_idx)
                    continue
                    
            consolidated.append(row)
            
        return pd.DataFrame(consolidated)
        
    def _safe_amount(self, val):
        try:
            if isinstance(val, str):
                val = val.replace(',', '.').replace(' ', '').replace('\xa0', '')
            return float(val)
        except:
            return 0.0