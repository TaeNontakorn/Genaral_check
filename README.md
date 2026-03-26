# Genaral_check# 📄 ระบบตรวจสอบเอกสาร (Document Checker)

ระบบตรวจสอบและเปรียบเทียบเอกสารด้วย AI (Gemini) รองรับไฟล์ PDF, DOCX, XLSX และ CSV

---

## 🏗️ โครงสร้างโปรเจกต์

```
├── main.py       # FastAPI backend — OCR, ตรวจคำผิด, เปรียบเทียบเอกสาร
├── app.py        # Streamlit frontend — UI สำหรับผู้ใช้งาน
├── .env          # เก็บ API Key (ไม่ควร commit)
└── requirements.txt
```

---

## ⚙️ การติดตั้ง

### 1. ติดตั้ง dependencies

```bash
pip install -r requirements.txt
```

> **Windows:** ใช้ `python-magic-bin` แทน `python-magic`

### 2. ตั้งค่า API Key

สร้างไฟล์ `.env` แล้วใส่:

```env
api_key=YOUR_GEMINI_API_KEY
```

> หรือจะกรอก API Key ผ่าน UI โดยตรงก็ได้ โดยไม่ต้องตั้งค่า `.env`

### 3. รัน Backend (FastAPI)

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. รัน Frontend (Streamlit)

```bash
streamlit run app.py --server.port 8501
```

เปิดเบราว์เซอร์ที่ `http://localhost:8501`

---

## 🚀 ฟีเจอร์หลัก

### 📝 ตรวจคำผิด / ตรวจข้อมูล

| ประเภทไฟล์ | การทำงาน |
|---|---|
| PDF | OCR ด้วย Gemini แล้วตรวจคำผิดและลำดับเลขข้อ |
| DOCX | อ่านข้อความ (รองรับ Text Box) แล้วตรวจคำผิดและลำดับเลขข้อ |
| XLSX / CSV | แปลงเป็นตาราง Markdown แล้วตรวจหาข้อมูลที่ขัดแย้งกัน |

### 🔄 เปรียบเทียบเอกสาร

- อัปโหลด 2 ไฟล์ (ข้ามประเภทได้ เช่น DOCX vs PDF)
- AI วิเคราะห์และรายงานความแตกต่างเป็นภาษาไทย
- แสดงข้อความต้นฉบับของทั้งสองไฟล์เพื่อตรวจสอบเพิ่มเติม

---

## 🔌 API Endpoints

| Method | Endpoint | คำอธิบาย |
|---|---|---|
| POST | `/check` | ตรวจคำผิด หรือตรวจความขัดแย้งของข้อมูล |
| POST | `/compare` | เปรียบเทียบเอกสาร 2 ฉบับ |

### `/check` — Form Data

| Field | Type | คำอธิบาย |
|---|---|---|
| `quotation` | file | ไฟล์ที่ต้องการตรวจ (PDF/DOCX/XLSX/CSV) |
| `api_key` | string | Gemini API Key (optional ถ้าตั้งใน `.env`) |

### `/compare` — Form Data

| Field | Type | คำอธิบาย |
|---|---|---|
| `main_document` | file | เอกสาร A |
| `secon_document` | file | เอกสาร B |
| `api_key` | string | Gemini API Key (optional ถ้าตั้งใน `.env`) |

---

## 📦 Requirements

```
fastapi
uvicorn
python-dotenv
google-genai
python-magic        # Linux/Mac
python-magic-bin    # Windows (ใช้อันนี้แทน python-magic)
python-docx
pandas
tabulate
openpyxl
requests
streamlit
lxml
```

---

## 📝 หมายเหตุ

- โมเดล AI ที่ใช้: **Gemini 2.5 Pro**
- PDF ใช้ Gemini OCR โดยตรง (อัปโหลดไฟล์ผ่าน Gemini Files API)
- DOCX รองรับ Text Box แบบลอยตัว (Floating Text Box)
- API Key สามารถกรอกผ่าน UI ได้โดยตรง หรือตั้งค่าใน `.env` ก็ได้ โดย UI จะมีความสำคัญกว่า