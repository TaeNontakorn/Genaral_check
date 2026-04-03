import os
import tempfile
import asyncio
import logging
from typing import Optional
import sys

from dotenv import load_dotenv
from google import genai
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

import magic

# =========================================================
# CONFIG
# =========================================================
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://genaralcheckgit-s6v9h3jnqkjbk3hasdshd9.streamlit.app/"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_api_key(form_key: str = "") -> str:
    if form_key and form_key.strip():
        return form_key.strip()
    return os.getenv("api_key", "")


# ================================================================================================================================================
#                                                               PROMPT & OCR  PDF
# ================================================================================================================================================

OCR_PROMPT = """
คุณคือผู้เชี่ยวชาญด้านการสกัดข้อมูล (Data Extraction Expert)

หน้าที่ของคุณคือสกัดเนื้อหาหลักและตารางจากไฟล์ PDF ในช่วงหน้า {page_range} 
โดยต้องมีความถูกต้องตรงตามต้นฉบับ 100% และห้ามมีการแต่งเติมข้อมูลใด ๆ

### กฎการสกัดข้อมูล (Strict Rules):

1. เนื้อหาที่ต้องสกัด:
- สกัดเฉพาะเนื้อหาหลัก (Main Body Text) และตารางทั้งหมด
- ต้องรักษาลำดับเนื้อหาให้ตรงกับต้นฉบับ 100%

2. สิ่งที่ต้องตัดออก (Exclude):
- หน้าปก, สารบัญ, ดัชนี, ภาคผนวก
- Header, Footer, เลขหน้า
- Footnote และคำอธิบายรูปภาพ

3. ความถูกต้อง (Critical Accuracy):
- ต้องคงข้อความตามต้นฉบับแบบตัวอักษรต่ออักษร (character-by-character)
- ห้ามเพิ่ม ลบ หรือแก้ไขเนื้อหา
- หากข้อความอ่านไม่ออก ให้ใช้ [unclear]
- ห้ามคาดเดาหรือเติมคำเองโดยเด็ดขาด
- หากข้อมูลไม่ปรากฏในต้นฉบับ ห้ามสร้างขึ้นใหม่

4. โครงสร้างเอกสาร:
- ใช้ Markdown Heading (#, ##, ###)
- รักษาย่อหน้าเดิม
- รักษาการขึ้นบรรทัดใหม่ (line break)
- ใช้ list ตามต้นฉบับ
- คง **bold** และ *italic*

5. การจัดการ Layout:
- หากเป็นหลายคอลัมน์ ให้อ่านจากซ้ายไปขวา ทีละคอลัมน์

6. การจัดการตาราง (Table Precision):
- แปลงเป็น Markdown Table (|---|)
- คัดลอกแบบคำต่อคำ (word-for-word)
- ห้ามสรุป
- ต้องครบทุกแถวและคอลัมน์
- ต้องจัดตำแหน่งข้อมูลให้ตรงกับคอลัมน์เดิม
- หากมี merged cell ให้กระจายข้อมูลให้ถูกต้อง
- หาก cell มีหลายบรรทัด ให้รวมเป็นบรรทัดเดียว

7. ขอบเขตหน้า:
- สกัดเฉพาะหน้า {page_range} เท่านั้น

8. Fallback:
- หากไม่สามารถแยกโครงสร้างได้ ให้แสดงเป็น raw text โดยไม่ดัดแปลง

9. Validation:
- ตรวจสอบความครบถ้วนของข้อมูลก่อนตอบทุกครั้ง

### รูปแบบการตอบ:
- ตอบเป็น Markdown เท่านั้น
- หากข้อมูลยาว ให้หยุดเมื่อจบย่อหน้าหรือตาราง
- รักษาการเว้นวรรคและวรรคตอนตามต้นฉบับ
- ห้ามแปลงคำย่อหรือขยายความ
"""

# ===========================================================================================================
#                                                  Docx read
# ===========================================================================================================

def smart_docx_extract(file_path: str) -> str:
    import re, os
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table as DocxTable

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    doc = Document(file_path)

    W_P       = qn("w:p")
    W_TBL     = qn("w:tbl")
    W_T       = qn("w:t")
    W_BR      = qn("w:br")
    W_TAB     = qn("w:tab")
    W_SYM     = qn("w:sym")
    W_CHAR    = qn("w:char")
    W_TXBX    = qn("w:txbxContent")
    W_DRAWING = qn("w:drawing")
    W_ANCHOR  = qn("wp:anchor")

    seen_txbx = set()

    def read_paragraph(p_el):
        """อ่าน text ใน paragraph — ข้าม w:drawing เพื่อไม่ให้ซ้ำกับ textbox pass"""
        parts = []
        for child in p_el.iter():
            tag = child.tag
            # ข้าม subtree ของ drawing (textbox ลอยอยู่ใน drawing)
            if tag == W_DRAWING:
                continue
            if tag == W_T and child.text:
                parts.append(child.text)
            elif tag == W_BR:
                parts.append("\n")
            elif tag == W_TAB:
                parts.append("\t")
            elif tag == W_SYM:
                char_val = child.get(W_CHAR)
                if char_val:
                    try:
                        parts.append(chr(int(char_val, 16)))
                    except (ValueError, OverflowError):
                        pass
        return "".join(parts)

    def collect_textbox_text(root_el):
        """อ่าน text ทุก txbxContent ใน element นี้"""
        lines = []
        for txbx in root_el.iter(W_TXBX):
            for p_el in txbx.iter(W_P):
                line = read_paragraph(p_el)
                if line.strip():
                    lines.append(line.strip())
        return "\n".join(lines)

    def read_table(table):
        rows_text = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            deduped = []
            for c in cells:
                if not deduped or c != deduped[-1]:
                    deduped.append(c)
            rows_text.append(" | ".join(deduped))
        return rows_text

    blocks = []

    for child in doc.element.body:
        if child.tag == W_P:
            # อ่าน paragraph text (ไม่รวม drawing)
            para_text = read_paragraph(child)

            # อ่าน textbox ที่ลอยอยู่ใน paragraph นี้ (wp:anchor)
            txbx_parts = []
            for drawing in child.iter(W_DRAWING):
                for anchor in drawing.iter(W_ANCHOR):
                    tb = collect_textbox_text(anchor)
                    if tb.strip() and tb.strip() not in seen_txbx:
                        seen_txbx.add(tb.strip())
                        txbx_parts.append(tb.strip())

            combined = para_text.strip()
            if txbx_parts:
                combined = (combined + "\n" + "\n".join(txbx_parts)).strip()

            if combined:
                blocks.append(combined)

        elif child.tag == W_TBL:
            blocks.extend(read_table(DocxTable(child, doc)))

    # เก็บ textbox ที่อาจหลุดจาก body loop (เช่น nested ลึก)
    for txbx in doc.element.body.iter(W_TXBX):
        lines = [read_paragraph(p) for p in txbx.iter(W_P)]
        text = "\n".join(l.strip() for l in lines if l.strip())
        if text and text not in seen_txbx:
            seen_txbx.add(text)
            blocks.append(text)

    raw = "\n\n".join(blocks)
    raw = re.sub(r"\n{3,}", "\n\n", raw.replace("\r\n", "\n").replace("\r", "\n"))
    return raw.strip()


# ================================================================================================
#                                      Excel / CSV Read
# ================================================================================================

def get_sheet_names(file_path: str) -> list:
    return pd.ExcelFile(file_path).sheet_names

def convert_excel_to_markdown(file_path: str, sheet_name: Optional[str] = None, columns: Optional[list] = None) -> str:
    if sheet_name:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        if df.empty:
            return "(ไม่มีข้อมูลใน sheet นี้)"
        if columns:
            valid_cols = [c for c in columns if c in df.columns]
            if valid_cols:
                df = df[valid_cols]
        return f"### Sheet: {sheet_name}\n{df.to_markdown(index=False)}"
    else:
        sheets = pd.read_excel(file_path, sheet_name=None)
        parts = []
        for sname, df in sheets.items():
            if not df.empty:
                if columns:
                    valid_cols = [c for c in columns if c in df.columns]
                    if valid_cols:
                        df = df[valid_cols]
                parts.append(f"### Sheet: {sname}\n{df.to_markdown(index=False)}")
        return "\n\n".join(parts) if parts else "(ไม่มีข้อมูลในไฟล์)"

def convert_csv_to_markdown(file_path: str) -> str:
    df = pd.read_csv(file_path)
    return df.to_markdown(index=False)


# ================================================================================================
#                                     Extract (shared utility)
# ================================================================================================

async def extract_text(upload: UploadFile, gemini_client: genai.Client, sheet_name: Optional[str] = None, columns: Optional[list] = None) -> str:
    """Extract text จากไฟล์ที่อัปโหลด รองรับ PDF, DOCX, XLSX, CSV"""
    file_bytes = await upload.read()
    suffix = os.path.splitext(upload.filename)[1] or ".tmp"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        detector = magic.Magic(mime=True)
        file_type = detector.from_file(tmp_path)
        logger.info(f"[ EXTRACT ] {upload.filename} → {file_type}")

        if file_type == "application/pdf":
            return await pdf_run_ocr_from_path(tmp_path, OCR_PROMPT, gemini_client)

        elif file_type in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ) or (file_type == "application/zip" and upload.filename.lower().endswith(".docx")):
            return smart_docx_extract(tmp_path)

        elif file_type in (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ) or (file_type == "application/zip" and upload.filename.lower().endswith(".xlsx")):
            return convert_excel_to_markdown(tmp_path, sheet_name=sheet_name, columns=columns)

        elif file_type in ("text/csv", "text/plain") and upload.filename.lower().endswith(".csv"):
            return convert_csv_to_markdown(tmp_path)

        else:
            raise ValueError(f"Unsupported file type: {file_type}. Please upload PDF, DOCX, XLSX, or CSV.")

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ================================================================================================
#                                     Check Typo (PDF / DOCX)
# ================================================================================================

def pdf_check_typo(text: str, gemini_client: genai.Client, page: Optional[int] = None) -> str:
    page_hint = f"หน้า {page}: " if page is not None else ""

    prompt = f"""
        บทบาท: คุณคือบรรณาธิการตรวจทานเอกสารภาษาไทยมืออาชีพ
        ภารกิจ: ตรวจสอบคำสะกดผิดและตรวจสอบความถูกต้องของลำดับเลขข้อ (Ordering) ในข้อความต่อไปนี้: {text}

        กฎการตรวจสอบ:
        1. การสะกดคำ: 
           - เน้นคำที่ผิดพจนานุกรม หรือ Typo จากการพิมพ์ (เช่น "กน" แทน "กิน")
           - รูปแบบ: <strong style="color: red;">คำผิด</strong> (คำที่ถูกต้อง)
        
        2. ลำดับเลขข้อ (Sequence):
           - ตรวจสอบว่าเลขข้อ (เช่น 1., 2., 3. หรือ ก., ข., ค.) เรียงลำดับถูกต้องหรือไม่
           - หากเลขข้อกระโดด ซ้ำ หรือผิดลำดับ ให้เน้นที่เลขข้อนั้นด้วยสีส้ม
           - รูปแบบ: <strong style="color: orange;">เลขที่ผิด</strong> (เลขที่ควรจะเป็น)

        3. การแสดงผล:
           - แสดงประโยคเต็มที่มีจุดผิดเพื่อให้เห็นบริบท
           - ถ้ามีหมายเลขหน้า ให้ขึ้นต้นด้วย "{page_hint}"
           - หากทุกอย่างถูกต้อง (ไม่มีคำผิดและเลขข้อเรียงปกติ) ให้ Return ข้อความเดิมทั้งหมด
        
        ตัวอย่างการตรวจเลขข้อ:
        Input: "1. เดินหน้า 2. ถอยหลัง 4. เลี้ยวซ้าย"
        Output: "{page_hint}1. เดินหน้า 2. ถอยหลัง <strong style=\"color: orange;\">4.</strong> (3.) เลี้ยวซ้าย"

        Input: "{text}"
        Output:
        """
    response = gemini_client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
        config={"temperature": 0},
    )
    return response.text


async def pdf_run_ocr_from_path(file_path: str, prompt: str, gemini_client: genai.Client) -> str:
    uploaded_file = await asyncio.to_thread(gemini_client.files.upload, file=file_path)
    response = await asyncio.to_thread(
        gemini_client.models.generate_content,
        model="gemini-2.5-pro",
        contents=[uploaded_file, prompt],
    )
    return response.text.strip()


# ================================================================================================
#                                     Excel Check (XLSX / CSV)
# ================================================================================================

def excel_check(table: str, gemini_client: genai.Client) -> str:
    prompt = f"""
        คุณคือผู้เชี่ยวชาญด้านการตรวจสอบข้อมูล (Data Auditor) 
        นี่คือข้อมูลจากตารางที่ฉันต้องการให้คุณ Recheck:
        
        {table}
        
        ภารกิจของคุณ:
        1. ตรวจสอบหาจุดที่ 'ข้อมูลขัดแย้งกัน' (Inconsistency) ในทุกมิติที่เป็นไปได้
        2. หากพบข้อมูลที่ดูเหมือนจะเป็นรายการเดียวกัน (เช่น ID เดียวกัน หรือชื่อคล้ายกันมาก) แต่ค่าในคอลัมน์อื่นไม่ตรงกัน ให้ระบุออกมา
        3. รายงานผลโดยระบุ: 
           - ชื่อคอลัมน์ที่พบปัญหา
           - เลข Row ของแถว (Row Index)
           - สาเหตุที่คิดว่าผิดปกติ
        4. หากข้อมูลถูกต้องทั้งหมด ให้สรุปสั้นๆ ว่าไม่พบจุดผิดปกติ
        """
    response = gemini_client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
        config={"temperature": 0},
    )
    return response.text


# ================================================================================================
#                                     Compare Documents
# ================================================================================================

def compare_documents(text_a: str, text_b: str, name_a: str, name_b: str, gemini_client: genai.Client) -> str:
    prompt = f"""
        คุณคือผู้เชี่ยวชาญด้านการตรวจสอบเอกสาร
        เปรียบเทียบเนื้อหาของเอกสาร 2 ฉบับต่อไปนี้ และระบุความแตกต่างทั้งหมด

        === เอกสาร A: {name_a} ===
        {text_a}

        === เอกสาร B: {name_b} ===
        {text_b}

        ภารกิจของคุณ:
        1. ระบุข้อความ / ข้อมูล / ตัวเลข ที่มีอยู่ใน {name_a} แต่ไม่มีใน {name_b}
        2. ระบุข้อความ / ข้อมูล / ตัวเลข ที่มีอยู่ใน {name_b} แต่ไม่มีใน {name_a}
        3. ระบุข้อความที่มีทั้งสองฉบับที่มีความแตกต่างกันทั้งหมด 
        4. สรุปภาพรวมว่าเอกสารทั้งสองมีความแตกต่างกันมากน้อยแค่ไหน

        รายงานผลเป็นภาษาไทย จัดหมวดหมู่ให้ชัดเจน ถ้าไม่เจอหมวดหมู่ที่มีปัญหาไม่ต้องรายงาน
        หากเอกสารทั้งสองเหมือนกันทุกประการ ให้ระบุว่า "ไม่พบความแตกต่าง"
        """
    response = gemini_client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
        config={"temperature": 0},
    )
    return response.text


# ================================================================================================
#                                     ENDPOINTS
# ================================================================================================

@app.post("/check")
async def check(
    quotation: UploadFile = File(...),
    api_key: str = Form(""),
    sheet_name: str = Form(""),
    columns: str = Form(""),
):
    key = get_api_key(api_key)
    gemini_client = genai.Client(api_key=key)

    try:
        logger.info("[ CHECK ] เริ่มต้น...")

        suffix = os.path.splitext(quotation.filename)[1].lower()
        file_bytes = await quotation.read()

        # detect MIME จาก bytes ชั่วคราว
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            detector = magic.Magic(mime=True)
            file_type = detector.from_file(tmp_path)
        finally:
            os.remove(tmp_path)

        # reset ให้ extract_text อ่านได้ใหม่
        import io
        quotation.file = io.BytesIO(file_bytes)

        is_table = file_type in (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ) or (file_type in ("text/csv", "text/plain") and suffix == ".csv")

        cols = [c.strip() for c in columns.split(",") if c.strip()] if columns else None
        document_text = await extract_text(quotation, gemini_client, sheet_name=sheet_name or None, columns=cols)

        if is_table:
            logger.info("[ TABLE CHECK ] ตรวจข้อมูลตาราง...")
            check_result = await asyncio.to_thread(excel_check, document_text, gemini_client)
            return {
                "ocr_text": document_text,
                "table_result": check_result,
            }
        else:
            logger.info("[ TYPO ] ตรวจคำผิด...")
            typo_result = await asyncio.to_thread(pdf_check_typo, document_text, gemini_client)
            return {
                "ocr_text": document_text,
                "typo_result": typo_result,
            }

    except Exception as e:
        logger.error(f"SYSTEM ERROR: {e}")
        return {"error": str(e)}


@app.post("/compare")
async def compare(
    main_document: UploadFile = File(...),
    secon_document: UploadFile = File(...),
    api_key: str = Form(""),
    sheet_a: str = Form(""),
    sheet_b: str = Form(""),
    columns_a: str = Form(""),
    columns_b: str = Form(""),
):
    key = get_api_key(api_key)
    gemini_client = genai.Client(api_key=key)

    try:
        logger.info("[ COMPARE ] กำลัง extract ทั้ง 2 ไฟล์...")

        # อ่าน bytes ก่อน แล้ว reset stream เพื่อให้ extract_text อ่านได้ถูกต้อง
        import io
        bytes_a = await main_document.read()
        bytes_b = await secon_document.read()
        main_document.file = io.BytesIO(bytes_a)
        secon_document.file = io.BytesIO(bytes_b)

        # extract ทั้งคู่พร้อมกัน
        cols_a = [c.strip() for c in columns_a.split(",") if c.strip()] if columns_a else None
        cols_b = [c.strip() for c in columns_b.split(",") if c.strip()] if columns_b else None
        text_a, text_b = await asyncio.gather(
            extract_text(main_document, gemini_client, sheet_name=sheet_a or None, columns=cols_a),
            extract_text(secon_document, gemini_client, sheet_name=sheet_b or None, columns=cols_b),
        )

        logger.info("[ COMPARE ] กำลังเปรียบเทียบ...")
        compare_result = await asyncio.to_thread(
            compare_documents,
            text_a, text_b,
            main_document.filename, secon_document.filename,
            gemini_client,
        )

        return {
            "text_a": text_a,
            "text_b": text_b,
            "compare_result": compare_result,
        }

    except Exception as e:
        logger.error(f"SYSTEM ERROR: {e}")
        return {"error": str(e)}