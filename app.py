import streamlit as st
import requests
import base64
import pandas as pd
import io
from pypdf import PdfReader
import re

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(page_title="Document Intelligence", layout="wide")

API_URL          = "https://genaral-check-1.onrender.com/check"
COMPARE_URL      = "https://genaral-check-1.onrender.com/compare"
OCR_URL          = "https://genaral-check-1.onrender.com/ocr_table"
EXTRACT_URL      = "https://genaral-check-1.onrender.com/extract"
COMPARE_TEXT_URL = "https://genaral-check-1.onrender.com/compare_text"

st.markdown("<style>iframe { border: none; }</style>", unsafe_allow_html=True)

# =========================================================
# HELPERS
# =========================================================
def render_pdf(file):
    """Render PDF in an iframe using base64 encoding."""
    try:
        b64 = base64.b64encode(file.getvalue()).decode("utf-8")
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="600px" type="application/pdf"></iframe>',
            unsafe_allow_html=True,
        )
    except Exception as e:
        st.error(f"ไม่สามารถแสดงตัวอย่าง PDF ได้: {e}")

def call_api(url, files, data):
    """Shared API caller with basic error handling."""
    try:
        response = requests.post(url, files=files, data=data, timeout=1000)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def parse_markdown_tables(text: str) -> list:
    """Parse markdown tables from text into list of pandas DataFrames."""
    tables = []
    # Regex to find markdown table blocks
    pattern = re.compile(r'((?:\|[^\n]+\|\n)+)', re.MULTILINE)
    for match in pattern.finditer(text):
        block = match.group(1).strip()
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        # Filter out separator lines like |---|
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
# SIDEBAR NAVIGATION
# =========================================================
st.sidebar.title("📂 Document Intelligence")
menu = st.sidebar.radio(
    "เลือกฟีเจอร์ที่ต้องการ:",
    ["📝 ตรวจคำผิด / ตรวจข้อมูล", "🔄 เปรียบเทียบเอกสาร"],
    key="main_menu"
)

st.sidebar.markdown("---")
api_key = st.sidebar.text_input("🔑 API Key", key="API_key_input", type="password")
st.sidebar.caption("ใส่ API Key ของ Gemini เพื่อเริ่มใช้งาน")

if st.sidebar.button("🧹 เคลียร์หน้าจอ / เริ่มใหม่"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# =========================================================
# UI - MAIN CONTENT
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
            key="check_uploader",
        )
        
        check_sheet = ""
        check_columns = []
        page_range_check = ""
        
        if uploaded_file:
            st.success(f"อัปโหลดสำเร็จ: `{uploaded_file.name}`")
            
            if uploaded_file.name.lower().endswith(".xlsx"):
                excel_file = pd.ExcelFile(uploaded_file)
                check_sheet = st.selectbox("เลือก Sheet:", excel_file.sheet_names)
                df_check = pd.read_excel(uploaded_file, sheet_name=check_sheet)
                check_columns = st.multiselect(
                    "เลือก Column ที่ต้องการตรวจสอบ (ปล่อยว่าง = ทั้งหมด):",
                    options=df_check.columns.tolist()
                )
            
            elif uploaded_file.name.lower().endswith(".pdf"):
                reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
                st.info(f"เอกสารมีทั้งหมด {len(reader.pages)} หน้า")
                page_range_check = st.text_input("ระบุหน้า (เช่น 1-2, 4):", placeholder="ปล่อยว่างเพื่อตรวจทั้งไฟล์")
                
                if st.button("📥 Step 1: OCR Preview (เพื่อเลือกคอลัมน์)", use_container_width=True):
                    with st.spinner("กำลัง OCR..."):
                        res = call_api(EXTRACT_URL, 
                                       files={"file": (uploaded_file.name, uploaded_file.getvalue())},
                                       data={"api_key": api_key, "page_range": page_range_check})
                        if "text" in res:
                            st.session_state["check_preview_text"] = res["text"]
                            st.session_state["check_preview_tables"] = parse_markdown_tables(res["text"])
                            st.success("OCR สำเร็จ!")
                        else:
                            st.error(res.get("error", "Unknown error"))

    with col_preview:
        if uploaded_file and uploaded_file.name.lower().endswith(".pdf"):
            render_pdf(uploaded_file)

    # Column Selection for PDF Table Analysis
    check_target_columns = []
    if "check_preview_tables" in st.session_state and uploaded_file and uploaded_file.name.lower().endswith(".pdf"):
        tables = st.session_state["check_preview_tables"]
        if tables:
            st.markdown("### 📊 เลือกคอลัมน์ที่ต้องการเน้น")
            all_cols = []
            for i, df_t in enumerate(tables):
                with st.expander(f"ตารางที่ {i+1} ({len(df_t)} แถว)", expanded=(i==0)):
                    st.dataframe(df_t, use_container_width=True)
                all_cols.extend(df_t.columns.tolist())
            
            all_cols = list(dict.fromkeys(all_cols))
            check_target_columns = st.multiselect("เลือกคอลัมน์เป้าหมาย:", options=all_cols)
        else:
            with st.expander("📄 ดูข้อความที่สกัดได้"):
                st.text(st.session_state.get("check_preview_text", ""))

    if uploaded_file:
        if st.button("🔍 Step 2: เริ่มการตรวจสอบ", use_container_width=True, type="primary"):
            with st.status("กำลังตรวจสอบ...", expanded=True) as status:
                try:
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
                    if "error" in r:
                        st.error(r["error"])
                    else:
                        st.session_state["check_result"] = r
                        status.update(label="✅ ตรวจสอบเสร็จสิ้น", state="complete")
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")

    # Display Results
    if "check_result" in st.session_state:
        res = st.session_state["check_result"]
        st.markdown("---")
        if "table_result" in res:
            st.markdown("### 🔍 ผลการตรวจสอบข้อมูล (Data Inconsistency)")
            st.markdown(res["table_result"])
        elif "typo_result" in res:
            st.markdown("### 📝 ผลการตรวจคำผิดและลำดับเลข")
            st.markdown(f'<div style="white-space: pre-wrap; line-height: 1.8;">{res["typo_result"]}</div>', unsafe_allow_html=True)
        
        with st.expander("📄 ข้อความต้นฉบับจาก OCR/Extraction"):
            st.markdown(res.get("ocr_text", "ไม่พบข้อมูล"))

elif menu == "🔄 เปรียบเทียบเอกสาร":
    st.title("🔄 เปรียบเทียบเอกสาร")
    
    comp_mode = st.sidebar.radio("โหมดการเปรียบเทียบ:", ["เปรียบเทียบทั้งไฟล์", "เลือกคอลัมน์"], key="comp_mode_side")
    
    if comp_mode == "เปรียบเทียบทั้งไฟล์":
        st.info("🚀 **โหมดเปรียบเทียบทั้งไฟล์:** AI จะวิเคราะห์เนื้อหาและตารางทั้งหมด")
    else:
        st.info("🎯 **โหมดเลือกคอลัมน์:** ขั้นตอนที่ 1: OCR -> ขั้นตอนที่ 2: เลือกคอลัมน์ -> ขั้นตอนที่ 3: เปรียบเทียบ")

    st.markdown("---")
    col_a, col_b = st.columns(2)
    
    # Inputs for Document A & B
    # (Keeping existing logic but cleaned up for consistency)
    page_range_a, page_range_b = "", ""
    sheet_a, sheet_b = "", ""
    cols_a, cols_b = [], []

    with col_a:
        doc_a = st.file_uploader("📄 เอกสาร A (ต้นฉบับ)", type=["pdf", "docx", "xlsx", "csv"], key="doc_a")
        if doc_a:
            st.success(f"`{doc_a.name}`")
            if doc_a.name.lower().endswith(".pdf"):
                reader_a = PdfReader(io.BytesIO(doc_a.getvalue()))
                if comp_mode == "เลือกคอลัมน์":
                    st.caption(f"มีทั้งหมด {len(reader_a.pages)} หน้า")
                    page_range_a = st.text_input("ระบุหน้า (A):", key="pr_a")
                render_pdf(doc_a)
            elif doc_a.name.lower().endswith((".xlsx", ".csv")):
                # Excel/CSV Preview logic
                if doc_a.name.lower().endswith(".xlsx"):
                    xl_a = pd.ExcelFile(doc_a)
                    sheet_a = st.selectbox("เลือก Sheet (A):", xl_a.sheet_names)
                    df_a = pd.read_excel(doc_a, sheet_name=sheet_a)
                else:
                    df_a = pd.read_csv(doc_a)
                cols_a = st.multiselect("เลือก Column (A):", df_a.columns.tolist())
                st.dataframe(df_a[cols_a] if cols_a else df_a, use_container_width=True)

    with col_b:
        doc_b = st.file_uploader("📄 เอกสาร B (ที่ต้องการเทียบ)", type=["pdf", "docx", "xlsx", "csv"], key="doc_b")
        if doc_b:
            st.success(f"`{doc_b.name}`")
            if doc_b.name.lower().endswith(".pdf"):
                reader_b = PdfReader(io.BytesIO(doc_b.getvalue()))
                if comp_mode == "เลือกคอลัมน์":
                    st.caption(f"มีทั้งหมด {len(reader_b.pages)} หน้า")
                    page_range_b = st.text_input("ระบุหน้า (B):", key="pr_b")
                render_pdf(doc_b)
            elif doc_b.name.lower().endswith((".xlsx", ".csv")):
                if doc_b.name.lower().endswith(".xlsx"):
                    xl_b = pd.ExcelFile(doc_b)
                    sheet_b = st.selectbox("เลือก Sheet (B):", xl_b.sheet_names)
                    df_b = pd.read_excel(doc_b, sheet_name=sheet_b)
                else:
                    df_b = pd.read_csv(doc_b)
                cols_b = st.multiselect("เลือก Column (B):", df_b.columns.tolist())
                st.dataframe(df_b[cols_b] if cols_b else df_b, use_container_width=True)

    # Phase 1: OCR for Comparison (Only for Column Selection mode)
    if comp_mode == "เลือกคอลัมน์" and doc_a and doc_b:
        if st.button("🔍 Step 1: OCR ทั้งสองเอกสาร", use_container_width=True):
            with st.status("กำลัง OCR...") as status:
                r_a = call_api(OCR_URL, files={"file": (doc_a.name, doc_a.getvalue())}, data={"api_key": api_key, "page_range": page_range_a})
                r_b = call_api(OCR_URL, files={"file": (doc_b.name, doc_b.getvalue())}, data={"api_key": api_key, "page_range": page_range_b})
                if "error" in r_a or "error" in r_b:
                    st.error(f"OCR Error: {r_a.get('error') or r_b.get('error')}")
                else:
                    st.session_state["comp_text_a"] = r_a.get("ocr_text", "")
                    st.session_state["comp_text_b"] = r_b.get("ocr_text", "")
                    st.session_state["comp_name_a"] = doc_a.name
                    st.session_state["comp_name_b"] = doc_b.name
                    status.update(label="OCR เสร็จสิ้น", state="complete")

    # Column Selection for Comparison
    ocr_comp_cols = []
    if "comp_text_a" in st.session_state and comp_mode == "เลือกคอลัมน์":
        st.markdown("### 📊 เลือกคอลัมน์เพื่อเปรียบเทียบ")
        c1, c2 = st.columns(2)
        with c1:
            st.caption(f"ตารางใน {st.session_state['comp_name_a']}")
            t_a = parse_markdown_tables(st.session_state["comp_text_a"])
            if t_a: 
                st.dataframe(t_a[0], use_container_width=True)
                sel_a = st.multiselect("คอลัมน์ (A):", t_a[0].columns.tolist(), key="sel_a")
            else: st.warning("ไม่พบตาราง")
        with c2:
            st.caption(f"ตารางใน {st.session_state['comp_name_b']}")
            t_b = parse_markdown_tables(st.session_state["comp_text_b"])
            if t_b: 
                st.dataframe(t_b[0], use_container_width=True)
                sel_b = st.multiselect("คอลัมน์ (B):", t_b[0].columns.tolist(), key="sel_b")
            else: st.warning("ไม่พบตาราง")
        ocr_comp_cols = list(dict.fromkeys((sel_a if 'sel_a' in locals() else []) + (sel_b if 'sel_b' in locals() else [])))

    # Phase 2: Final Compare
    if doc_a and doc_b:
        if st.button("🔄 Step 2: เริ่มการเปรียบเทียบ", use_container_width=True, type="primary"):
            with st.status("กำลังเปรียบเทียบ...") as status:
                # Use /compare_text if we already have OCR text
                if comp_mode == "เลือกคอลัมน์" and "comp_text_a" in st.session_state:
                    res = call_api(COMPARE_TEXT_URL, files={}, data={
                        "api_key": api_key, "text_a": st.session_state["comp_text_a"], "text_b": st.session_state["comp_text_b"],
                        "name_a": doc_a.name, "name_b": doc_b.name, "target_columns": ",".join(ocr_comp_cols), "compare_mode": comp_mode
                    })
                else:
                    res = call_api(COMPARE_URL, files={"main_document": (doc_a.name, doc_a.getvalue()), "secon_document": (doc_b.name, doc_b.getvalue())},
                                   data={"api_key": api_key, "sheet_a": sheet_a, "sheet_b": sheet_b, "columns_a": ",".join(cols_a), "columns_b": ",".join(cols_b),
                                         "page_range_a": page_range_a, "page_range_b": page_range_b, "compare_mode": comp_mode})
                
                if "error" in res:
                    st.error(res["error"])
                else:
                    st.session_state["comp_final_result"] = res
                    status.update(label="เปรียบเทียบเสร็จสิ้น", state="complete")

    if "comp_final_result" in st.session_state:
        res = st.session_state["comp_final_result"]
        st.markdown("---")
        st.markdown(f"### 🔍 ผลการเปรียบเทียบ")
        st.markdown(res.get("compare_result", "ไม่พบข้อมูล"))
        
        c1, c2 = st.columns(2)
        with c1:
            with st.expander(f"ต้นฉบับ (A): {doc_a.name if doc_a else ''}"):
                st.text(res.get("text_a", ""))
        with c2:
            with st.expander(f"ต้นฉ_บับ (B): {doc_b.name if doc_b else ''}"):
                st.text(res.get("text_b", ""))