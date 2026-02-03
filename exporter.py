# exporter.py
import pandas as pd
from datetime import datetime
import json
import os

def export_to_excel(parsed: dict, output_dir: str = "exports"):
    os.makedirs(output_dir, exist_ok=True)
    
    income = {k: [v] for k, v in json.loads(parsed['income_json']).items()}
    expenses = {k: [v] for k, v in json.loads(parsed['expenses_json']).items()}
    
    # Create DataFrame
    data = {
        'Date': [parsed['date']],
        'Tables Served': [parsed['tables_count']],
        'Arrests': [parsed['arrests_count']],
        'Total Income': [parsed['total_income']],
        'Total Expenses': [parsed['total_expenses']],
        'Cash in Hand': [parsed['cash_in_hand']],
        'Variance': [parsed['cash_in_hand'] - (parsed['total_income'] - parsed['total_expenses'])]
    }
    
    df = pd.DataFrame(data)
    
    # Filename: Rowva_2025-01-04.xlsx
    filename = f"Rowva_{parsed['date']}.xlsx"
    path = os.path.join(output_dir, filename)
    df.to_excel(path, index=False)
    
    return path