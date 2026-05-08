import pdfplumber
import pandas as pd

with pdfplumber.open("QO2025100012.R1.pdf") as pdf:
    page = pdf.pages[0] # เลือกหน้า 1
    table = page.extract_table() # ดึงข้อมูลตาราง
    
    # แปลงเป็น DataFrame
    df = pd.DataFrame(table[1:], columns=table[0])
    print(df)
