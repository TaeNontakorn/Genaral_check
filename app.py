import streamlit as st
import requests
import base64
import pandas as pd
import io
from pypdf import PdfReader
import re

st.set_page_config(page_title="Check", layout="wide")

API_URL          = "https://genaral-check-1.onrender.com/check"
COMPARE_URL      = "https://genaral-check-1.onrender.com/compare"
OCR_URL          = "https://genaral-check-1.onrender.com/ocr_table"
EXTRACT_URL      = "https://genaral-check-1.onrender.com/extract"
COMPARE_TEXT_URL = "https://genaral-check-1.onrender.com/compare_text"
st.markdown("<style>iframe { border: none; }</style>", unsafe_allow_html=True)

# =========================================================
# Helpers
# =========================================================
def render_pdf(file):
    b64 = base64.b64encode(file.getvalue()).decode("utf-8")
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="500px" type="application/pdf"></iframe>',
        unsafe_allow_html=True,
    )

def call_api(url, files, data):
    response = requests.post(url, files=files, data=data, timeout=1000)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}

def parse_markdown_tables(text: str) -> list:
    """Parse markdown tables from OCR output into list of DataFrames"""
    tables = []
    pattern = re.compile(
        r'((?:\|[^\n]+\|\n)+)',
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        block = match.group(1).strip()
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        data_lines = [l for l in lines if not re.match(r'^\|[-\s|:]+\|$', l)]
        if len(data_lines) < 2:
            continue
        try:
            headers = [h.strip() for h in data_lines[0].strip('|').split('|')]
            headers = [h for h in headers if h]
            rows = []
            for line in data_lines[1:]:
                cells = [c.strip() for c in line.strip('|').split('|')]
                if len(cells) == len(headers):
                    rows.append(cells)
            if headers and rows:
                tables.append(pd.DataFrame(rows, columns=headers))
        except Exception:
            continue
    return tables

# =========================================================
# Sidebar Navigation
# =========================================================
st.sidebar.title("📂 เมนูการใช้งาน")
menu = st.sidebar.radio(
    "เลือกฟีเจอร์ที่ต้องการ:",
    ["📝 ตรวจคำผิด / ตรวจข้อมูล", "🔄 เปรียบเทียบเอกสาร"],
    key="main_menu"
)

st.sidebar.markdown("---")
api_key = st.sidebar.text_input("🔑 API Key", key="API_key_input", type="password")
st.sidebar.caption("กรุณาใส่ API Key ของ Gemini เพื่อเริ่มใช้งาน")

# =========================================================
# UI - Main Content
# =========================================================
if menu == "📝 ตรวจคำผิด / ตรวจข้อมูล":
    st.title("📝 ตรวจคำผิด / ตรวจข้อมูล")
    st.caption("รองรับ PDF, DOCX (ตรวจคำผิด) และ XLSX, CSV (ตรวจความขัดแย้งของข้อมูล)")
    st.markdown("---")

    col_up, col_preview = st.columns([1, 2])
    with col_up:
        uploaded_file = st.file_uploader(
            "อัปโหลดไฟล์ที่ต้องการตรวจสอบ",
            type=["pdf", "docx", "xlsx", "csv"],
            key="quotation_uploader",
        )
        check_sheet = ""
        check_columns = []
        page_range_check = ""
        btn_extract_check = False
        if uploaded_file:
            st.markdown(f"✔️ **อัปโหลดสำเร็จ** — `{uploaded_file.name}`")
            if uploaded_file.name.lower().endswith(".xlsx"):
                excel_file = pd.ExcelFile(uploaded_file)
                sheet_names = excel_file.sheet_names
                check_sheet = st.selectbox("เลือก Sheet ที่ต้องการ:", sheet_names, key="check_sheet_select")
                df_check = pd.read_excel(uploaded_file, sheet_name=check_sheet)
                check_columns = st.multiselect(
                    "เลือก Column ที่ต้องการตรวจสอบ (ปล่อยว่างเพื่อตรวจทั้งหมด):",
                    options=df_check.columns.tolist(),
                    key="check_columns_select",
                )
            elif uploaded_file.name.lower().endswith(".pdf"):
                reader_check = PdfReader(io.BytesIO(uploaded_file.getvalue()))
                total_pages_check = len(reader_check.pages)
                btn_extract_check = st.button(
                    "📥 Step 1: OCR Preview (ดึงข้อมูลก่อนเลือกคอลัมน์)",
                    key="btn_extract_check",
                    use_container_width=True,
                )

    with col_preview:
        if uploaded_file and uploaded_file.name.lower().endswith(".pdf"):
            render_pdf(uploaded_file)

    # ── Handle Extract Preview (PDF only) ────────────────────────────────────────
    if btn_extract_check and uploaded_file:
        with st.spinner("📥 กำลัง OCR..."):
            try:
                r_ext = call_api(
                    EXTRACT_URL,
                    files={"file": (uploaded_file.name, uploaded_file.getvalue())},
                    data={"api_key": api_key, "page_range": page_range_check},
                )
                if "text" in r_ext:
                    st.session_state["check_preview_text"] = r_ext["text"]
                    st.session_state["check_preview_tables"] = parse_markdown_tables(r_ext["text"])
                    st.success("✅ OCR สำเร็จ — เลือกคอลัมน์ด้านล่าง แล้วกด '🔍 Step 2'")
                elif "error" in r_ext:
                    st.error(r_ext["error"])
            except Exception as e:
                st.error(str(e))

    # ── Show table preview + column selector ─────────────────────────────────────
    check_target_columns = []
    if "check_preview_tables" in st.session_state and uploaded_file and uploaded_file.name.lower().endswith(".pdf"):
        tables = st.session_state["check_preview_tables"]
        if tables:
            st.markdown("### 📊 ตารางที่พบใน PDF")
            all_cols = []
            for i, df_t in enumerate(tables):
                with st.expander(f"ตารางที่ {i+1} — {len(df_t)} แถว, {len(df_t.columns)} คอลัมน์", expanded=(i == 0)):
                    st.dataframe(df_t, use_container_width=True)
                all_cols.extend(df_t.columns.tolist())
            all_cols = list(dict.fromkeys(all_cols))
            check_target_columns = st.multiselect(
                "🎯 เลือกคอลัมน์ที่ต้องการวิเคราะห์ (ปล่อยว่างเพื่อวิเคราะห์ทั้งหมด):",
                options=all_cols,
                key="check_target_cols_select",
            )
        else:
            with st.expander("📄 ข้อความที่ได้จาก OCR"):
                st.text(st.session_state.get("check_preview_text", ""))

    btn_check = st.button("🔍 Step 2: ตรวจสอบ", use_container_width=True, key="btn_check")
    check_result_area = st.container()

    if btn_check:
        if not uploaded_file:
            with check_result_area:
                st.warning("กรุณาอัปโหลดไฟล์ก่อน")
        else:
            with st.status("กำลังประมวลผล...", expanded=True) as status:
                try:
                    is_xlsx = uploaded_file.name.lower().endswith((".xlsx", ".csv"))
                    st.write("📤 กำลังส่งไฟล์ไปยัง server...")
                    r = call_api(
                        API_URL,
                        files={"quotation": (uploaded_file.name, uploaded_file.getvalue())},
                        data={
                            "api_key": api_key,
                            "sheet_name": check_sheet,
                            "columns": ",".join(check_columns),
                            "page_range": page_range_check,
                            "target_columns": ",".join(check_target_columns),
                        },
                    )
                    if is_xlsx:
                        st.write("🔍 กำลังตรวจสอบความขัดแย้งของข้อมูล...")
                    else:
                        st.write("🔍 กำลังตรวจสอบคำผิดด้วย AI...")
                    st.session_state["check_result"] = r
                    status.update(label="✅ ตรวจสอบเสร็จสิ้น", state="complete", expanded=False)
                except requests.exceptions.ConnectionError:
                    status.update(label="❌ เชื่อมต่อไม่ได้", state="error")
                    with check_result_area:
                        st.error("ไม่สามารถเชื่อมต่อ API ได้")
                except Exception as e:
                    status.update(label="❌ เกิดข้อผิดพลาด", state="error")
                    with check_result_area:
                        st.error(f"เกิดข้อผิดพลาด: {e}")

    if "check_result" in st.session_state:
        r = st.session_state["check_result"]
        with check_result_area:
            if "error" in r:
                st.error(f"❌ {r['error']}")
            elif "table_result" in r:
                st.success("✅ ตรวจสอบเสร็จสิ้น")
                st.markdown("## 📊 ตารางต้นฉบับ")
                if r.get("ocr_text"):
                    st.markdown(r["ocr_text"])
                else:
                    st.info("ไม่มีข้อมูลตาราง")
                st.markdown("---")
                st.markdown("## 🔍 ผลการตรวจสอบข้อมูล")
                if r.get("table_result"):
                    st.markdown(r["table_result"])
                else:
                    st.success("ไม่พบจุดผิดปกติ")
            elif "typo_result" in r:
                st.success("✅ ตรวจสอบเสร็จสิ้น")
                st.markdown("## 📝 ผลการตรวจคำผิด")
                if r.get("typo_result"):
                    st.markdown(
                        f'<div style="white-space: pre-wrap; line-height: 1.8;">{r["typo_result"]}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.success("ไม่พบคำผิด")
                with st.expander("📄 ข้อความที่ OCR ได้ (ต้นฉบับ)"):
                    st.text(r.get("ocr_text", ""))

elif menu == "🔄 เปรียบเทียบเอกสาร":
    st.title("🔄 เปรียบเทียบเอกสาร")
    compare_mode = st.sidebar.radio(
        "โหมดการเปรียบเทียบ",
        ["เปรียบเทียบทั้งไฟล์", "เลือกคอลัมน์"],
        key="compare_mode_select"
    )

    if compare_mode == "เปรียบเทียบทั้งไฟล์":
        st.info("🚀 **โหมดเปรียบเทียบทั้งไฟล์:** AI จะวิเคราะห์เนื้อหาและตารางทั้งหมดในเอกสารโดยละเอียด")
    else:
        st.info("🎯 **โหมดเลือกคอลัมน์:** ขั้นตอนที่ 1: OCR เพื่อดูตาราง -> ขั้นตอนที่ 2: เลือกคอลัมน์ที่ต้องการ -> ขั้นตอนที่ 3: เปรียบเทียบ")
    
    st.markdown("---")

    col_a, col_b = st.columns(2)
    page_range_a, page_range_b = "", ""
    selected_sheet_a, selected_columns_a = "", []
    selected_sheet_b, selected_columns_b = "", []

    with col_a:
        main_document = st.file_uploader("📄 เอกสาร A (ต้นฉบับ)", type=["pdf", "docx", "xlsx", "csv"], key="main_document")
        if main_document:
            st.markdown(f"✔️ `{main_document.name}`")
            if main_document.name.lower().endswith(".pdf"):
                reader_a = PdfReader(io.BytesIO(main_document.getvalue()))
                total_pages_a = len(reader_a.pages)
                
                if compare_mode == "เลือกคอลัมน์":
                    st.info(f"📋 ไฟล์นี้มีทั้งหมด **{total_pages_a} หน้า**")
                    page_range_a = st.text_input(
                        f"📌 ระบุหน้าที่ต้องการ (เช่น 1-3, 5):",
                        key="compare_page_range_a",
                    )
                else:
                    page_range_a = "" # ส่งทั้งไฟล์ในโหมดเปรียบเทียบทั้งไฟล์
                render_pdf(main_document)
            if main_document.name.lower().endswith(".xlsx"):
                excel_file_a = pd.ExcelFile(main_document)
                selected_sheet_a = st.selectbox("เลือก Sheet:", excel_file_a.sheet_names, key="sheet_select_a")
                df_a = pd.read_excel(main_document, sheet_name=selected_sheet_a)
                selected_columns_a = st.multiselect("เลือก Column (ปล่อยว่าง = ทั้งหมด):", df_a.columns.tolist(), key="columns_select_a")
                st.dataframe(df_a[selected_columns_a] if selected_columns_a else df_a, use_container_width=True)
            elif main_document.name.lower().endswith(".csv"):
                df_a = pd.read_csv(main_document)
                selected_columns_a = st.multiselect("เลือก Column (ปล่อยว่าง = ทั้งหมด):", df_a.columns.tolist(), key="columns_select_a")
                st.dataframe(df_a[selected_columns_a] if selected_columns_a else df_a, use_container_width=True)
                selected_sheet_a = ""

    with col_b:
        secon_document = st.file_uploader("📄 เอกสาร B (ที่ต้องการเทียบ)", type=["pdf", "docx", "xlsx", "csv"], key="secon_document")
        if secon_document:
            st.markdown(f"✔️ `{secon_document.name}`")
            if secon_document.name.lower().endswith(".pdf"):
                reader_b = PdfReader(io.BytesIO(secon_document.getvalue()))
                total_pages_b = len(reader_b.pages)

                if compare_mode == "เลือกคอลัมน์":
                    st.info(f"📋 ไฟล์นี้มีทั้งหมด **{total_pages_b} หน้า**")
                    page_range_b = st.text_input(
                        f"📌 ระบุหน้าที่ต้องการ (เช่น 1-3, 5):",
                        key="compare_page_range_b",
                    )
                else:
                    page_range_b = "" # ส่งทั้งไฟล์ในโหมดเปรียบเทียบทั้งไฟล์
                render_pdf(secon_document)
            if secon_document.name.lower().endswith(".xlsx"):
                excel_file_b = pd.ExcelFile(secon_document)
                selected_sheet_b = st.selectbox("เลือก Sheet:", excel_file_b.sheet_names, key="sheet_select_b")
                df_b = pd.read_excel(secon_document, sheet_name=selected_sheet_b)
                selected_columns_b = st.multiselect("เลือก Column (ปล่อยว่าง = ทั้งหมด):", df_b.columns.tolist(), key="columns_select_b")
                st.dataframe(df_b[selected_columns_b] if selected_columns_b else df_b, use_container_width=True)
            elif secon_document.name.lower().endswith(".csv"):
                df_b = pd.read_csv(secon_document)
                selected_columns_b = st.multiselect("เลือก Column (ปล่อยว่าง = ทั้งหมด):", df_b.columns.tolist(), key="columns_select_b")
                st.dataframe(df_b[selected_columns_b] if selected_columns_b else df_b, use_container_width=True)
                selected_sheet_b = ""

    # ── Phase 1: OCR (เฉพาะโหมดเลือกคอลัมน์) ──────────────────────────
    if compare_mode == "เลือกคอลัมน์":
        st.markdown("#### ขั้นตอนที่ 1 — OCR เอกสารเพื่อเลือกคอลัมน์")
        btn_ocr = st.button("🔍 OCR ทั้งสองเอกสาร", use_container_width=True, key="btn_ocr")
    else:
        btn_ocr = False 

    if btn_ocr:
        missing = []
        if not main_document: missing.append("เอกสาร A")
        if not secon_document: missing.append("เอกสาร B")
        if missing:
            st.warning(f"กรุณาอัปโหลด: {', '.join(missing)}")
        else:
            with st.status("กำลัง OCR เอกสาร...", expanded=True) as ocr_status:
                try:
                    st.write("📤 กำลัง OCR เอกสาร A...")
                    r_ocr_a = call_api(OCR_URL,
                        files={"file": (main_document.name, main_document.getvalue())},
                        data={"api_key": api_key, "page_range": page_range_a})
                    st.write("📤 กำลัง OCR เอกสาร B...")
                    r_ocr_b = call_api(OCR_URL,
                        files={"file": (secon_document.name, secon_document.getvalue())},
                        data={"api_key": api_key, "page_range": page_range_b})
                    if "error" in r_ocr_a:
                        st.error(f"เอกสาร A: {r_ocr_a['error']}")
                    elif "error" in r_ocr_b:
                        st.error(f"เอกสาร B: {r_ocr_b['error']}")
                    else:
                        st.session_state["ocr_text_a"] = r_ocr_a.get("ocr_text", "")
                        st.session_state["ocr_text_b"] = r_ocr_b.get("ocr_text", "")
                        st.session_state["ocr_name_a"] = main_document.name
                        st.session_state["ocr_name_b"] = secon_document.name
                        ocr_status.update(label="✅ OCR เสร็จสิ้น — เลือกคอลัมน์ด้านล่าง", state="complete", expanded=False)
                except Exception as e:
                    ocr_status.update(label="❌ OCR ล้มเหลว", state="error")
                    st.error(f"เกิดข้อผิดพลาด: {e}")

    # ── แสดงผล OCR + Column Selector ─────────────────────────
    ocr_cols_a, ocr_cols_b = [], []
    if "ocr_text_a" in st.session_state and "ocr_text_b" in st.session_state:
        st.markdown("#### 📊 ผลลัพธ์ OCR — เลือกคอลัมน์ที่ต้องการเปรียบเทียบ")
        sel_a, sel_b = st.columns(2)

        with sel_a:
            st.markdown(f"**เอกสาร A:** `{st.session_state.get('ocr_name_a','')}`")
            tables_a = parse_markdown_tables(st.session_state["ocr_text_a"])
            if tables_a:
                st.dataframe(tables_a[0], use_container_width=True)
                ocr_cols_a = st.multiselect(
                    "เลือกคอลัมน์ที่ต้องการ (ปล่อยว่าง = เปรียบเทียบทั้งหมด):",
                    options=tables_a[0].columns.tolist(),
                    key="ocr_col_select_a",
                )
            else:
                st.info("ไม่พบตารางใน OCR — จะเปรียบเทียบเนื้อหาทั้งหมด")
                with st.expander("ดูข้อความ OCR"):
                    st.text(st.session_state["ocr_text_a"])

        with sel_b:
            st.markdown(f"**เอกสาร B:** `{st.session_state.get('ocr_name_b','')}`")
            tables_b = parse_markdown_tables(st.session_state["ocr_text_b"])
            if tables_b:
                st.dataframe(tables_b[0], use_container_width=True)
                ocr_cols_b = st.multiselect(
                    "เลือกคอลัมน์ที่ต้องการ (ปล่อยว่าง = เปรียบเทียบทั้งหมด):",
                    options=tables_b[0].columns.tolist(),
                    key="ocr_col_select_b",
                )
            else:
                st.info("ไม่พบตารางใน OCR — จะเปรียบเทียบเนื้อหาทั้งหมด")
                with st.expander("ดูข้อความ OCR"):
                    st.text(st.session_state["ocr_text_b"])

    # ── Phase 2: Compare ──────────────────────────────────────
    st.markdown(f"#### ขั้นตอนที่ {'2' if compare_mode == 'เลือกคอลัมน์' else '1'} — เปรียบเทียบเอกสาร")
    btn_compare = st.button("🔄 เริ่มเปรียบเทียบ", use_container_width=True, key="btn_compare")
    compare_result_area = st.container()

    if btn_compare:
        missing = []
        if not main_document: missing.append("เอกสาร A")
        if not secon_document: missing.append("เอกสาร B")
        if missing:
            with compare_result_area:
                st.warning(f"กรุณาอัปโหลด: {', '.join(missing)}")
        else:
            with st.status("กำลังเปรียบเทียบเอกสาร...", expanded=True) as status:
                try:
                    # ถ้ามี OCR ไว้แล้ว และเป็นโหมดเลือกคอลัมน์ ใช้ /compare_text
                    if compare_mode == "เลือกคอลัมน์" and "ocr_text_a" in st.session_state and "ocr_text_b" in st.session_state:
                        st.write("🤖 AI กำลังวิเคราะห์จากข้อความที่ OCR แล้ว...")
                        all_cols = list(dict.fromkeys(ocr_cols_a + ocr_cols_b))
                        r = call_api(COMPARE_TEXT_URL, files={}, data={
                            "api_key": api_key,
                            "text_a": st.session_state["ocr_text_a"],
                            "text_b": st.session_state["ocr_text_b"],
                            "name_a": st.session_state.get("ocr_name_a", main_document.name),
                            "name_b": st.session_state.get("ocr_name_b", secon_document.name),
                            "target_columns": ",".join(all_cols),
                            "compare_mode": compare_mode,
                        })
                    else:
                        # Fallback: OCR + compare ในครั้งเดียว
                        st.write("📄 กำลังอ่านและแปลงเนื้อหาเอกสาร...")
                        r = call_api(COMPARE_URL,
                            files={
                                "main_document":  (main_document.name,  main_document.getvalue()),
                                "secon_document": (secon_document.name, secon_document.getvalue()),
                            },
                            data={
                                "api_key": api_key,
                                "sheet_a": selected_sheet_a if main_document.name.lower().endswith(".xlsx") else "",
                                "sheet_b": selected_sheet_b if secon_document.name.lower().endswith(".xlsx") else "",
                                "columns_a": ",".join(selected_columns_a),
                                "columns_b": ",".join(selected_columns_b),
                                "page_range_a": page_range_a,
                                "page_range_b": page_range_b,
                                "compare_mode": compare_mode,
                            })
                    st.session_state["compare_result"] = r
                    st.session_state["compare_name_a"] = main_document.name
                    st.session_state["compare_name_b"] = secon_document.name
                    status.update(label="✅ เปรียบเทียบเสร็จสิ้น", state="complete", expanded=False)
                except requests.exceptions.ConnectionError:
                    status.update(label="❌ เชื่อมต่อไม่ได้", state="error")
                    with compare_result_area:
                        st.error("ไม่สามารถเชื่อมต่อ API ได้")
                except Exception as e:
                    status.update(label="❌ เกิดข้อผิดพลาด", state="error")
                    with compare_result_area:
                        st.error(f"เกิดข้อผิดพลาด: {e}")

    if "compare_result" in st.session_state:
        r      = st.session_state["compare_result"]
        name_a = st.session_state.get("compare_name_a", "เอกสาร A")
        name_b = st.session_state.get("compare_name_b", "เอกสาร B")
        with compare_result_area:
            if "error" in r:
                st.error(f"❌ {r['error']}")
            else:
                st.success("✅ เปรียบเทียบเสร็จสิ้น")
                st.markdown(f"## 🔍 ผลการเปรียบเทียบ: `{name_a}` vs `{name_b}`")
                if r.get("compare_result"):
                    st.markdown(r["compare_result"])
                else:
                    st.success("ไม่พบความแตกต่าง")
                st.markdown("---")
                exp_a, exp_b = st.columns(2)
                with exp_a:
                    with st.expander(f"📄 เนื้อหาต้นฉบับ: {name_a}"):
                        st.text(r.get("text_a", ""))
                with exp_b:
                    with st.expander(f"📄 เนื้อหาต้นฉบับ: {name_b}"):
                        st.text(r.get("text_b", ""))