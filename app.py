import streamlit as st
import os
from dotenv import load_dotenv
from openai import OpenAI
import PyPDF2
import docx
import pandas as pd
import base64
import json
# Remove streamlit-elements import
# from streamlit_elements import elements, mui
from jd_analyzer import analyze_job_description, format_requirements_for_display, parse_edited_requirements
from resume_analyzer import analyze_resume

# Sheet-based Analysis (Tab 2) scores resumes via the standalone backend API
# deployed on Render, instead of calling the LLM in-process - this is the
# same backend other applications call directly. Tab 1 (manual upload) is
# unaffected and still uses analyze_resume() in-process.
BACKEND_API_URL = "https://bta-resume-screener.onrender.com"
# Load environment variables
load_dotenv()

st.set_page_config(layout="wide")
# Initialize OpenAI client

# Initialize session state for API key verification
if 'api_key_verified' not in st.session_state:
    st.session_state.api_key_verified = False

# Initialize other session states
if "requirements" not in st.session_state:
    st.session_state.requirements = None
if "job_description" not in st.session_state:
    st.session_state.job_description = None
if "formatted_reqs" not in st.session_state:
    st.session_state.formatted_reqs = None
FIREWORKS_MODEL = "accounts/fireworks/models/gpt-oss-120b"
if "selected_models" not in st.session_state:
    st.session_state.selected_models = {"primary": FIREWORKS_MODEL, "reasoning": FIREWORKS_MODEL}

def extract_text_from_pdf(pdf_file):
    text = ""
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    for page in pdf_reader.pages:
        text += page.extract_text()
    return text

def extract_text_from_docx(docx_file):
    doc = docx.Document(docx_file)
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text + "\n"
    return text

def process_file(file):
    if file.name.endswith('.pdf'):
        return extract_text_from_pdf(file)
    elif file.name.endswith('.docx'):
        return extract_text_from_docx(file)
    else:
        return file.getvalue().decode('utf-8')

def create_collapsible_section(header, content):
    """Create a collapsible section using HTML and JavaScript"""
    # Generate a unique ID for this section
    import random
    import string
    section_id = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    
    html = f"""
        <div style="margin: 10px 0;">
            <button type="button" style="background-color: #262730; color: #fff; border: 1px solid #555; padding: 5px 10px; cursor: pointer; width: 100%; text-align: left; border-radius: 4px;"
                    onclick="toggleSection_{section_id}()">
                ▼ {header}
            </button>
            <div id="section_{section_id}" style="display: none; margin-left: 20px; margin-top: 8px;">
                {content}
            </div>
        </div>
        <script>
            function toggleSection_{section_id}() {{
                var content = document.getElementById('section_{section_id}');
                var button = content.previousElementSibling;
                if (content.style.display === 'none') {{
                    content.style.display = 'block';
                    button.innerHTML = button.innerHTML.replace('▼', '▲');
                }} else {{
                    content.style.display = 'none';
                    button.innerHTML = button.innerHTML.replace('▲', '▼');
                }}
            }}
        </script>
    """
    return html

def create_details_element(summary, content):
    """Create a custom HTML details element with styling"""
    return f"""
        <style>
            details {{
                background: #1E1E1E;
                padding: 10px;
                margin: 5px 0;
                border-radius: 4px;
                border: 1px solid #333;
            }}
            details summary {{
                cursor: pointer;
                padding: 5px;
                font-weight: bold;
                color: #FFFFFF;
            }}
            details summary:hover {{
                background: #2E2E2E;
                border-radius: 4px;
            }}
            .details-content {{
                margin-top: 10px;
                padding: 10px;
                background: #262630;
                border-radius: 4px;
            }}
            .checkmark {{
                color: #28a745;
            }}
            .cross {{
                color: #dc3545;
            }}
        </style>
        <details>
            <summary>{summary}</summary>
            <div class="details-content">
                {content}
            </div>
        </details>
    """

def display_simple_minimal_requirements(analysis):
    """Display requirements using custom HTML details elements"""
    req_match = analysis.get("requirement_match", {})
    must_have = req_match.get("must_have_requirements", {})
    good_to_have = req_match.get("good_to_have_requirements", {})
    screening = req_match.get("additional_screening_criteria", {})

    st.subheader("Requirements Match Summary")
    
    # --- Must-Have Section --- 
    st.markdown("<h4><b>Must-Have</b></h4>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        tech_skills = must_have.get("technical_skills", {})
        true_count = sum(1 for v in tech_skills.values() if v is True)
        total = len(tech_skills)
        value_str = f"{true_count}/{total}" if total > 0 else "N/A"
        
        # Create content for technical skills
        content = "<br>".join([
            f"<span class='{'checkmark' if met else 'cross'}'>{('✓' if met else '✗')}</span> {skill}" 
            for skill, met in tech_skills.items()
        ])
        summary = f"Technical Skills: {value_str}"
        st.markdown(create_details_element(summary, content), unsafe_allow_html=True)
                
    with col2:
        core_resp = must_have.get("core_responsibilities", {})
        true_count = sum(1 for v in core_resp.values() if v is True)
        total = len(core_resp)
        value_str = f"{true_count}/{total}" if total > 0 else "N/A"
        
        # Create content for core responsibilities
        content = "<br>".join([
            f"<span class='{'checkmark' if met else 'cross'}'>{('✓' if met else '✗')}</span> {resp}" 
            for resp, met in core_resp.items()
        ])
        summary = f"Core Responsibilities: {value_str}"
        st.markdown(create_details_element(summary, content), unsafe_allow_html=True)
                
    # --- Experience & Qualifications --- 
    col_exp, col_qual = st.columns(2)
    with col_exp:
        exp_met = must_have.get("experience", None)
        exp_status = '✓ Met' if exp_met is True else ('✗ Not Met' if exp_met is False else 'N/A')
        st.markdown(f"<span style='font-size: 1.1em; font-weight: 600;'>Experience:</span> <span class='{'checkmark' if exp_met else 'cross'}'>{exp_status}</span>", unsafe_allow_html=True)
    with col_qual:
        qual_met = must_have.get("qualifications", None)
        qual_status = '✓ Met' if qual_met is True else ('✗ Not Met' if qual_met is False else 'N/A')
        st.markdown(f"<span style='font-size: 1.1em; font-weight: 600;'>Qualifications:</span> <span class='{'checkmark' if qual_met else 'cross'}'>{qual_status}</span>", unsafe_allow_html=True)
    
    # --- Good-to-Have & Screening Section --- 
    st.markdown("<h4><b>Good-to-Have & Screening</b></h4>", unsafe_allow_html=True)
    col3, col4 = st.columns(2)
    with col3:
        add_skills = good_to_have.get("additional_skills", {})
        true_count = sum(1 for v in add_skills.values() if v is True)
        total = len(add_skills)
        value_str = f"{true_count}/{total}" if total > 0 else "N/A"
        
        # Create content for additional skills
        content = "<br>".join([
            f"<span class='{'checkmark' if met else 'cross'}'>{('✓' if met else '✗')}</span> {skill}" 
            for skill, met in add_skills.items()
        ])
        summary = f"Additional Skills: {value_str}"
        st.markdown(create_details_element(summary, content), unsafe_allow_html=True)
                
    with col4:
        true_count = sum(1 for v in screening.values() if v is True)
        total = len(screening)
        value_str = f"{true_count}/{total}" if total > 0 else "N/A"
        
        # Create content for screening criteria
        content = "<br>".join([
            f"<span class='{'checkmark' if met else 'cross'}'>{('✓' if met else '✗')}</span> {crit}" 
            for crit, met in screening.items()
        ])
        summary = f"Screening Criteria: {value_str}"
        st.markdown(create_details_element(summary, content), unsafe_allow_html=True)

def display_requirement_matches(matches):
    st.subheader("Requirement Matches")
    st.json(matches)

def display_qualitative_assessment(assessment):
    # Define mapping from qualitative labels to numerical values 
    qualitative_map = {
        "very low": 10,
        "low": 25,
        "moderate": 50,
        "medium": 50,
        "medium-high": 65,
        "high": 85,
        "very high": 95,
        "strong": 85, 
        "n/a": 0,
        None: 0
    }
    
    # Define mapping from numerical ranges/categories to colors
    color_map = {
        "high": "#28a745", # Green
        "mid": "#ffc107", # Yellow
        "low": "#dc3545", # Red
        "n/a": "#6c757d" # Grey
    }
    
    # Helper function to get category from value
    def get_category(value):
        num_val = qualitative_map.get(value.lower().replace(" ", "-").strip(), 0)
        if num_val >= 75: return "high"
        if num_val >= 40: return "mid"
        if num_val > 0: return "low"
        return "n/a"

    # Fields to display as meters - Update label here
    meter_fields = {
        "project_gravity": "Project Gravity",
        "ownership_and_initiative": "Ownership & Initiative",
        "transferability_to_role": "Fit for Role" # Changed Label
    }
    
    st.markdown("<h5><b>Qualitative Factors</b></h5>", unsafe_allow_html=True)
    
    # Create columns for horizontal layout
    cols = st.columns(len(meter_fields))
    
    # Iterate and place each factor in a column
    for i, (key, label) in enumerate(meter_fields.items()):
        value_str = assessment.get(key, "N/A")
        category = get_category(value_str)
        color = color_map.get(category, "#6c757d")
        text_color = "#ffffff" if category != "n/a" else "#212529"
        
        badge_text = category.capitalize() if category != "n/a" else "N/A"
        badge_html = f"<span style='background-color: {color}; color: {text_color}; padding: 3px 8px; border-radius: 5px; font-size: 0.9em; font-weight: 600;'>{badge_text}</span>"
        
        # Place the markdown in the corresponding column
        with cols[i]:
            st.markdown(f"<span style='font-size: 0.9em; font-weight: 600;'>{label}:</span> {badge_html}", unsafe_allow_html=True)

    # Add some space below the horizontal factors before strengths/weaknesses
    st.write("") 

    # Displaying strengths/weaknesses (keep as before)
    if "strengths" in assessment:
        st.markdown("<span style='font-size: 0.9em; font-weight: 600;'>Strengths:</span>", unsafe_allow_html=True)
        for strength in assessment["strengths"]:
             st.markdown(f"<span style='font-size: 0.9em;'>- {strength}</span>", unsafe_allow_html=True)
             
    if "weaknesses" in assessment:
        st.markdown("<span style='font-size: 0.9em; font-weight: 600;'>Weaknesses:</span>", unsafe_allow_html=True)
        for weakness in assessment["weaknesses"]:
             st.markdown(f"<span style='font-size: 0.9em;'>- {weakness}</span>", unsafe_allow_html=True)

def display_requirement_progress(section, title, key):
    """Display requirement progress as a bar or list of checkmarks."""
    if key == "screening":
        # Handle the special case for screening criteria
        items = section.get(key, {})
    else:
        items = section.get(key, {})
    
    if not items:
        st.write(f"**{title}**: No data available")
        return
        
    true_count = sum(1 for v in items.values() if v is True)
    total = len(items)
    
    # Display header with count
    st.write(f"**{title}**: {true_count}/{total}")
    
    # Display individual items with checkmarks
    for item, met in items.items():
        st.write(f"{'✅' if met else '❌'} {item}")

def format_requirements_for_editing(requirements):
    must_have = []
    if "must_have_requirements" in requirements:
        must = requirements["must_have_requirements"]
        must_have.append("Technical Skills:")
        must_have.extend([f"- {skill}" for skill in must.get("technical_skills", [])])
        must_have.append("\nExperience:")
        must_have.append(f"- {must.get('experience', '')}")
        must_have.append("\nQualifications:")
        must_have.extend([f"- {qual}" for qual in must.get("qualifications", [])])
        must_have.append("\nCore Responsibilities:")
        must_have.extend([f"- {resp}" for resp in must.get("core_responsibilities", [])])
    
    preferred = []
    if "good_to_have_requirements" in requirements:
        good = requirements["good_to_have_requirements"]
        preferred.append("Additional Skills:")
        preferred.extend([f"- {skill}" for skill in good.get("additional_skills", [])])
        preferred.append("\nExtra Qualifications:")
        preferred.extend([f"- {qual}" for qual in good.get("extra_qualifications", [])])
        preferred.append("\nBonus Experience:")
        preferred.extend([f"- {exp}" for exp in good.get("bonus_experience", [])])
    
    additional = []
    if "additional_screening_criteria" in requirements:
        additional.extend([f"- {criteria}" for criteria in requirements["additional_screening_criteria"]])
    
    return {
        "must_have": "\n".join(must_have),
        "preferred": "\n".join(preferred),
        "additional": "\n".join(additional)
    }

def calculate_percentage(score):
    """Convert score like '10/21' to percentage"""
    try:
        numerator, denominator = map(int, score.split('/'))
        percentage = (numerator / denominator) * 100
        return round(percentage)
    except:
        return 0

def display_contact_info(contact_info):
    """Display candidate contact information in a clean format"""
    # Display name in larger font with custom styling
    if contact_info.get("full_name"):
        st.markdown(f"""
            <div style='margin-bottom: 15px;'>
                <h2 style='margin: 0; color: #1E88E5; font-size: 24px; font-weight: 600;'>
                    {contact_info['full_name']}
                </h2>
            </div>
        """, unsafe_allow_html=True)
    
    # Create a clean two-column layout for contact info with consistent styling
    col1, col2 = st.columns(2)
    
    # Define the style for info labels and values with lighter colors for dark mode
    info_style = """
        <div style='margin-bottom: 8px;'>
            <span style='color: #9AA0A6; font-size: 13px; font-weight: 500;'>{label}:</span>
            <span style='color: #FFFFFF; font-size: 14px; margin-left: 4px;'>{value}</span>
        </div>
    """
    
    with col1:
        if contact_info.get("email"):
            st.markdown(info_style.format(
                label="Email",
                value=f"<a href='mailto:{contact_info['email']}' style='color: #8AB4F8;'>{contact_info['email']}</a>"
            ), unsafe_allow_html=True)
        if contact_info.get("phone"):
            st.markdown(info_style.format(
                label="Phone",
                value=contact_info['phone']
            ), unsafe_allow_html=True)
            
    with col2:
        if contact_info.get("location"):
            st.markdown(info_style.format(
                label="Location",
                value=contact_info['location']
            ), unsafe_allow_html=True)
        if contact_info.get("linkedin") and contact_info['linkedin'] != "N/A":
            st.markdown(info_style.format(
                label="LinkedIn",
                value=f"<a href='{contact_info['linkedin']}' target='_blank' style='color: #8AB4F8;'>Profile ↗</a>"
            ), unsafe_allow_html=True)
        
    # Display other links if present
    if contact_info.get("other_links") and len(contact_info["other_links"]) > 0:
        st.markdown("<div style='margin-top: 10px;'>", unsafe_allow_html=True)
        st.markdown("""
            <span style='color: #9AA0A6; font-size: 13px; font-weight: 500;'>Other Profiles:</span>
        """, unsafe_allow_html=True)
        for link in contact_info["other_links"]:
            st.markdown(f"""
                <div style='margin-left: 10px; font-size: 14px;'>
                    <a href='https://{link}' target='_blank' style='color: #8AB4F8;'>• {link} ↗</a>
                </div>
            """, unsafe_allow_html=True)

def flatten_analysis_for_csv(analysis):
    """Flatten the analysis JSON for CSV with specific columns"""
    flattened = {}
    
    # Contact Information
    contact_info = analysis.get('contact_info', {})
    flattened['full_name'] = contact_info.get('full_name', '')
    flattened['email'] = contact_info.get('email', '')
    flattened['phone'] = contact_info.get('phone', '')
    flattened['location'] = contact_info.get('location', '')
    flattened['linkedin'] = contact_info.get('linkedin', '')
    flattened['other_links'] = ', '.join(contact_info.get('other_links', []))

    # Requirement Match - Core Responsibilities (combined in one column)
    req_match = analysis.get('requirement_match', {})
    must_have = req_match.get('must_have_requirements', {})
    core_resp = must_have.get('core_responsibilities', {})
    flattened['core_responsibilities'] = ', '.join([f"{k}: {str(v)}" for k, v in core_resp.items()])

    # Additional Skills (combined in one column)
    good_to_have = req_match.get('good_to_have_requirements', {})
    add_skills = good_to_have.get('additional_skills', {})
    flattened['additional_skills'] = ', '.join([f"{k}: {str(v)}" for k, v in add_skills.items()])

    # Screening Criteria (combined in one column)
    screening = req_match.get('additional_screening_criteria', {})
    flattened['additional_screening_criteria'] = ', '.join([f"{k}: {str(v)}" for k, v in screening.items()])

    # Qualitative Assessment
    qual_assessment = analysis.get('qualitative_assessment', {})
    flattened['inferred_skills_from_projects'] = ', '.join(qual_assessment.get('inferred_skills_from_projects', []))
    flattened['project_gravity'] = qual_assessment.get('project_gravity', '')
    flattened['ownership_and_initiative'] = qual_assessment.get('ownership_and_initiative', '')
    flattened['transferability_to_role'] = qual_assessment.get('transferability_to_role', '')
    flattened['recruiter_style_summary'] = qual_assessment.get('recruiter_style_summary', '')

    # Summary of Key Factors
    flattened['summary_of_key_factors'] = ', '.join(analysis.get('summary_of_key_factors', []))

    return flattened

# Streamlit page setup
st.set_page_config(layout="wide")
st.title("📄 Resume Analyzer")

# --- JD Input ---
with st.expander("📝 Job Description (Required)"):
    st.session_state.jd_input = st.text_area("Paste the Job Description", height=300)
    if st.button("Analyze JD"):
        if st.session_state.jd_input:
            st.session_state.requirements = analyze_job_description(st.session_state.jd_input, model=st.session_state.selected_models["primary"])
            st.success("✅ JD analyzed and stored in session.")
        else:
            st.error("Please paste a job description first.")

# Model: single Fireworks model used for both JD analysis and resume evaluation
st.sidebar.title("Model")
st.sidebar.markdown(f"`{FIREWORKS_MODEL}` (Fireworks)")
st.session_state.selected_models = {"primary": FIREWORKS_MODEL, "reasoning": FIREWORKS_MODEL}

# Tabs for workflows
tabs = st.tabs(["📁 Upload Resumes", "📊 Sheet-based Analysis"])

# --- Tab 1: Manual Upload ---
with tabs[0]:
    st.header("📁 Resume Upload & Analysis")
    if st.session_state.requirements is not None:
        uploaded_files = st.file_uploader("Upload Resumes (PDF, DOCX, or TXT)", accept_multiple_files=True)

        if uploaded_files and st.button("Analyze Resumes"):
            if 'resume_results' not in st.session_state:
                st.session_state.resume_results = []
                st.session_state.csv_data = []
            else:
                st.session_state.resume_results = []
                st.session_state.csv_data = []

            st.markdown("### 📊 Analyzing Resumes...")
            progress_bar = st.progress(0)
            total_files = len(uploaded_files)
            results_section = st.container()

            for idx, file in enumerate(uploaded_files, 1):
                with st.spinner(f"Analyzing {file.name}..."):
                    resume_text = process_file(file)
                    analysis = analyze_resume(resume_text, st.session_state.requirements, model=st.session_state.selected_models["reasoning"])

                    if analysis:
                        percentage = calculate_percentage(analysis['score'])
                        result = {
                            'filename': file.name,
                            'percentage': percentage,
                            'score': analysis['score'],
                            'analysis': analysis['analysis']
                        }
                        st.session_state.resume_results.append(result)
                        flattened_data = flatten_analysis_for_csv(analysis['analysis'])
                        flattened_data['filename'] = file.name
                        flattened_data['percentage'] = percentage
                        st.session_state.csv_data.append(flattened_data)
                        progress_bar.progress(idx / total_files)

                        with results_section:
                            with st.expander(f"{file.name} - {percentage}%", expanded=True):
                                if 'contact_info' in analysis['analysis']:
                                    st.write("📇 Contact Info", analysis['analysis']['contact_info'])
                                st.write("📝 Summary", analysis['analysis']['qualitative_assessment'].get("recruiter_style_summary", "N/A"))
                                st.write("✅ Final Recommendation", analysis['analysis']['final_recommendation'])

            progress_bar.empty()
            st.success("✅ All resumes processed!")
            if st.session_state.csv_data:
                df = pd.DataFrame(st.session_state.csv_data)
                csv = df.to_csv(index=False)
                st.download_button("📥 Download Results as CSV", data=csv, file_name="resume_analysis_results.csv", mime="text/csv")

    else:
        st.warning("Please analyze a Job Description first.")

# --- Tab 2: Google Sheet Analysis ---
with tabs[1]:
    st.header("📊 Resume Analysis via Google Sheet")
    st.caption("Reads resume links from the sheet, evaluates each resume against the JD above, and writes Skills / Summary / Score back into the sheet.")
    sheet_url = st.text_input("Google Sheet URL")
    worksheet_name = st.text_input("Enter worksheet name (case-sensitive)", value="Sheet1")

    resume_column_name = st.text_input("Column name with Resume Links", value="Resume")
    delay_seconds = st.number_input(
        "Delay between resumes (seconds)", min_value=0, max_value=120, value=3,
        help="Fireworks has no daily token cap, just generous per-minute limits (higher still once a payment method is on file). A small delay is just a safety buffer, not a workaround for a hard ceiling."
    )

    with st.expander("⚖️ Weighted Scoring Criteria (optional)"):
        st.caption(
            "Add specific requirements with a weight each, e.g. \"4 to 7 years of experience building "
            "production systems, not just internal tools\" with weight 40. The final score becomes a "
            "weighted average of how well the resume satisfies each criterion, computed deterministically "
            "(not left to the model's own math). Weights don't need to sum to 100 - they're normalized "
            "automatically. Leave this empty to use the default single holistic score instead."
        )
        if "criteria_df" not in st.session_state:
            st.session_state.criteria_df = pd.DataFrame([{"Criterion": "", "Weight": 0}])

        criteria_df = st.data_editor(
            st.session_state.criteria_df,
            num_rows="dynamic",
            use_container_width=True,
            key="criteria_editor",
            column_config={
                "Criterion": st.column_config.TextColumn("Criterion", width="large"),
                "Weight": st.column_config.NumberColumn("Weight", min_value=0, max_value=1000, step=1),
            },
        )
        st.session_state.criteria_df = criteria_df

    trigger = st.button("Start Sheet-Based Resume Analysis")

    # Columns this flow writes results into (auto-created in the sheet if missing).
    # Prefixed with "AI:" so results are visually distinct from manually-entered
    # columns, and so reruns reuse these exact columns instead of duplicating them.
    OUTPUT_COLUMNS = ["AI: Skills", "AI: Strongest Language", "AI: Summary", "AI: Score", "AI: Criteria Breakdown"]

    def get_or_create_col_map(worksheet, needed_columns):
        """Return {column_name: 1-based col index}, appending any missing
        needed_columns as new headers in row 1 so each gets its own column.
        Expands the sheet's grid first if it doesn't have room for them."""
        col_map = worksheet.row_values(1)
        missing = [name for name in needed_columns if name not in col_map]

        if missing:
            needed_width = len(col_map) + len(missing)
            if needed_width > worksheet.col_count:
                worksheet.add_cols(needed_width - worksheet.col_count)
            for name in missing:
                col_map.append(name)
                worksheet.update_cell(1, len(col_map), name)

        return {name: col_map.index(name) + 1 for name in col_map}

    if trigger:
        if not st.session_state.get("jd_input") or not sheet_url or not resume_column_name:
            st.error("Please provide a Job Description (top of page), Sheet URL, and resume link column name.")
            st.stop()

        # Build the weighted criteria list from the editor, dropping blank/zero-weight rows
        criteria_list = [
            {"text": str(row["Criterion"]).strip(), "weight": float(row["Weight"])}
            for _, row in st.session_state.criteria_df.iterrows()
            if str(row.get("Criterion", "")).strip() and float(row.get("Weight") or 0) > 0
        ]

        import gspread
        from oauth2client.service_account import ServiceAccountCredentials
        import tempfile
        import requests
        import time

        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        service_account_info = st.secrets["google_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
        client = gspread.authorize(creds)

        try:
            sheet = client.open_by_url(sheet_url)
            worksheet = sheet.worksheet(worksheet_name)
            rows = worksheet.get_all_records()
            col_map = get_or_create_col_map(worksheet, OUTPUT_COLUMNS)
            is_first_call = True

            for i, row in enumerate(rows, start=2):
                # Skip rows already processed (AI: Score already filled in)
                if str(row.get("AI: Score", "")).strip():
                    continue

                link = row.get(resume_column_name, "").strip()
                if not link:
                    continue

                if not is_first_call and delay_seconds > 0:
                    st.write(f"Waiting {delay_seconds}s before next call to avoid rate limits...")
                    time.sleep(delay_seconds)
                is_first_call = False

                st.write(f"Processing Row {i}...")

                try:
                    # Extract file ID from Google Drive link
                    if "id=" in link:
                        file_id = link.split("id=")[-1]
                    elif "/d/" in link:
                        file_id = link.split("/d/")[1].split("/")[0]
                    else:
                        raise ValueError("Invalid Drive Link")

                    url = f"https://drive.google.com/uc?export=download&id={file_id}"
                    r = requests.get(url)
                    if r.status_code != 200:
                        raise Exception("Download failed")

                    temp_path = tempfile.mktemp(suffix=".pdf")
                    with open(temp_path, "wb") as f:
                        f.write(r.content)

                    resume_text = extract_text_from_pdf(open(temp_path, "rb"))

                    # Score via the backend API (Render) instead of calling the LLM
                    # in-process - Render's free tier can take 30-60s to wake from
                    # idle, so this uses a generous timeout rather than failing fast.
                    backend_key = st.secrets["backend-key"]["BACKEND_API_KEY"]
                    request_payload = {"job_description": st.session_state.jd_input, "resume_text": resume_text}
                    if criteria_list:
                        request_payload["criteria"] = criteria_list
                    try:
                        api_resp = requests.post(
                            f"{BACKEND_API_URL}/score-resume",
                            headers={"X-API-Key": backend_key},
                            json=request_payload,
                            timeout=120,
                        )
                        record = api_resp.json() if api_resp.status_code == 200 else None
                        if record is None:
                            st.error(f"⚠️ Backend returned {api_resp.status_code} for row {i}: {api_resp.text}")
                    except requests.exceptions.Timeout:
                        record = None
                        st.error(f"⚠️ Backend timed out for row {i} (it may be waking up from idle - try again)")

                    if record:
                        worksheet.update_cell(i, col_map["AI: Skills"], record.get("skills", ""))
                        worksheet.update_cell(i, col_map["AI: Strongest Language"], record.get("strongest_language", ""))
                        worksheet.update_cell(i, col_map["AI: Summary"], record.get("summary", ""))
                        worksheet.update_cell(i, col_map["AI: Score"], record.get("score", ""))

                        breakdown = record.get("criteria_breakdown")
                        if breakdown:
                            breakdown_text = " | ".join(
                                f"{item['criterion']} (weight {item['weight']:g}): {item['score']}" for item in breakdown
                            )
                            worksheet.update_cell(i, col_map["AI: Criteria Breakdown"], breakdown_text)

                        st.success(f"✅ Row {i} processed")

                    else:
                        worksheet.update_cell(i, col_map["AI: Summary"], "Analysis failed")
                        st.error(f"❌ Row {i} analysis failed")

                except Exception as e:
                    st.error(f"⚠️ Error on row {i}: {e}")
                    worksheet.update_cell(i, col_map["AI: Summary"], f"Error: {str(e)}")

        except Exception as e:
            st.error(f"Could not open sheet: {e}")