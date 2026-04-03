import streamlit as st
import requests
import base64
import pandas as pd

st.set_page_config(page_title="Check", layout="wide")

API_URL     = "https://genaral-check.onrender.com/check"
COMPARE_URL = "https://genaral-check.onrender.com/compare"
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

# =========================================================
# UI
# =========================================================
st.title("ตรวจสอบเอกสาร")
api_key = st.text_input("API Key", key="API_key_input", type="password")

st.markdown("---")

# =========================================================
# ส่วนที่ 1: ตรวจคำผิด / ตรวจข้อมูล
# =========================================================
st.subheader("📝 ตรวจคำผิด / ตรวจข้อมูล")
st.caption("รองรับ PDF, DOCX (ตรวจคำผิด) และ XLSX, CSV (ตรวจความขัดแย้งของข้อมูล)")

col_up, col_preview = st.columns([1, 2])
with col_up:
    uploaded_file = st.file_uploader(
        "อัปโหลดไฟล์ที่ต้องการตรวจสอบ",
        type=["pdf", "docx", "xlsx", "csv"],
        key="quotation_uploader",
    )
    check_sheet = ""
    check_columns = []
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

with col_preview:
    if uploaded_file and uploaded_file.name.lower().endswith(".pdf"):
        render_pdf(uploaded_file)

btn_check = st.button("🔍 ตรวจสอบ", use_container_width=True, key="btn_check")
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

st.markdown("---")

# =========================================================
# ส่วนที่ 2: เปรียบเทียบเอกสาร
# =========================================================
st.subheader("🔄 เปรียบเทียบเอกสาร")
st.caption("อัปโหลด 2 ไฟล์เพื่อเปรียบเทียบเนื้อหาว่าต่างกันตรงไหน")

col_a, col_b = st.columns(2)
selected_sheet_a, selected_columns_a = "", []
selected_sheet_b, selected_columns_b = "", []

with col_a:
    main_document = st.file_uploader("📄 เอกสาร A", type=["pdf", "docx", "xlsx", "csv"], key="main_document")
    if main_document:
        st.markdown(f"✔️ `{main_document.name}`")
        if main_document.name.lower().endswith(".pdf"):
            render_pdf(main_document)
            
        if main_document.name.lower().endswith(".xlsx"):
            excel_file_a = pd.ExcelFile(main_document)
            selected_sheet_a = st.selectbox("เลือก Sheet ที่ต้องการ:", excel_file_a.sheet_names, key="sheet_select_a")
            df_a = pd.read_excel(main_document, sheet_name=selected_sheet_a)
            selected_columns_a = st.multiselect(
                "เลือก Column ที่ต้องการแสดง (ปล่อยว่างเพื่อแสดงทั้งหมด):",
                options=df_a.columns.tolist(),
                key="columns_select_a",
            )
            display_df_a = df_a[selected_columns_a] if selected_columns_a else df_a
            st.subheader(f"📊 พรีวิวข้อมูล: {selected_sheet_a}")
            st.dataframe(display_df_a, use_container_width=True)
        else:
            selected_sheet_a = ""
            selected_columns_a = []

        
with col_b:
    secon_document = st.file_uploader("📄 เอกสาร B", type=["pdf", "docx", "xlsx", "csv"], key="secon_document")
    if secon_document:
        st.markdown(f"✔️ `{secon_document.name}`")
        if secon_document.name.lower().endswith(".pdf"):
            render_pdf(secon_document)
        
        if secon_document.name.lower().endswith(".xlsx"):
            excel_file_b = pd.ExcelFile(secon_document)
            selected_sheet_b = st.selectbox("เลือก Sheet ที่ต้องการ:", excel_file_b.sheet_names, key="sheet_select_b")
            df_b = pd.read_excel(secon_document, sheet_name=selected_sheet_b)
            selected_columns_b = st.multiselect(
                "เลือก Column ที่ต้องการแสดง (ปล่อยว่างเพื่อแสดงทั้งหมด):",
                options=df_b.columns.tolist(),
                key="columns_select_b",
            )
            display_df_b = df_b[selected_columns_b] if selected_columns_b else df_b
            st.subheader(f"📊 พรีวิวข้อมูล: {selected_sheet_b}")
            st.dataframe(display_df_b, use_container_width=True)
        else:
            selected_sheet_b = ""
            selected_columns_b = []


btn_compare = st.button("🔄 เปรียบเทียบเอกสาร", use_container_width=True, key="btn_compare")
compare_result_area = st.container()

if btn_compare:
    missing = []
    if not main_document:
        missing.append("เอกสาร A")
    if not secon_document:
        missing.append("เอกสาร B")

    if missing:
        with compare_result_area:
            st.warning(f"กรุณาอัปโหลด: {', '.join(missing)}")
    else:
        with st.status("กำลังเปรียบเทียบเอกสาร...", expanded=True) as status:
            try:
                st.write("📤 กำลังส่งไฟล์ทั้งสองไปยัง server...")
                payload = {
                    "api_key": api_key,
                    "sheet_a": selected_sheet_a if main_document.name.endswith(".xlsx") else "",
                    "sheet_b": selected_sheet_b if secon_document.name.endswith(".xlsx") else "",
                    "columns_a": ",".join(selected_columns_a),
                    "columns_b": ",".join(selected_columns_b),
                }
                st.write("📄 กำลังอ่านและแปลงเนื้อหาเอกสาร...")
                r = call_api(
                    COMPARE_URL,
                    files={
                        "main_document":  (main_document.name,  main_document.getvalue()),
                        "secon_document": (secon_document.name, secon_document.getvalue()),
                    },
                    data=payload,
                )
                st.write("🤖 AI กำลังวิเคราะห์ความแตกต่าง...")
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