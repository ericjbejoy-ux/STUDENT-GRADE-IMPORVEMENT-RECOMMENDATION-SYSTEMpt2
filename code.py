import streamlit as st
import sqlite3
import pandas as pd
import base64
import time
import requests

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Student Grade Improvement System", 
    page_icon="🎓", 
    layout="centered"
)

# ==========================================
# ### USER CONFIGURATION & API KEYS ###
# ==========================================
# Securely fetch API Keys from Streamlit Secrets
# Create a .streamlit/secrets.toml file to use these
YOUTUBE_API_KEY = st.secrets.get("YOUTUBE_API_KEY", None)
OPENROUTER_API_KEY = st.secrets.get("OPENROUTER_API_KEY", None)

# --- DATABASE FUNCTIONS ---
def init_db():
    with sqlite3.connect('student_data.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (username TEXT PRIMARY KEY, password TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS student_marks 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      username TEXT, 
                      cgpa REAL, 
                      semester_details TEXT)''')
        # Create a default admin user for testing
        try:
            c.execute("INSERT INTO users (username, password) VALUES ('admin', '1234')")
            conn.commit()
        except sqlite3.IntegrityError:
            pass 

def create_user(username, password):
    try:
        with sqlite3.connect('student_data.db') as conn:
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False 

def check_login(username, password):
    with sqlite3.connect('student_data.db') as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        return c.fetchone()

def save_data(username, cgpa, details):
    with sqlite3.connect('student_data.db') as conn:
        c = conn.cursor()
        c.execute("INSERT INTO student_marks (username, cgpa, semester_details) VALUES (?, ?, ?)", 
                  (username, cgpa, str(details)))
        conn.commit()

# --- LLM ANALYSIS (OPENROUTER) ---
def analyze_student_performance(cgpa, subject_data, exam_type):
    if cgpa >= 9.0: category = "Excellent"
    elif 7.5 <= cgpa < 9.0: category = "Good"
    elif 6.0 <= cgpa < 7.5: category = "Average"
    else: category = "Below Average"

    if not OPENROUTER_API_KEY:
        return category, ["⚠️ **OpenRouter API Key Missing.**"]

    grades_summary = ", ".join([f"{item['Subject']} ({item['Marks']}/50, Grade: {item['Grade']})" for item in subject_data])
    
    prompt = f"""
    You are an academic counselor. Student finished {exam_type}. 
    CGPA: {cgpa}. Scores: {grades_summary}.
    Provide 3-4 bulleted study tips and a daily evening study table (7 PM - 12 AM) in Markdown.
    Focus on subjects with grades below B.
    """

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={
                "model": "google/gemini-2.0-flash-001", # High speed & reliable model
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        data = response.json()
        return category, [data['choices'][0]['message']['content']]
    except Exception as e:
        return category, [f"⚠️ AI Service Unavailable: {str(e)}"]

# --- YOUTUBE RECOMMENDATION ---
def get_dynamic_course_link(subject_name):
    fallback_url = f"https://www.youtube.com/results?search_query={subject_name.replace(' ', '+')}+tutorial"
    if not YOUTUBE_API_KEY:
        return fallback_url, "Search YouTube"

    try:
        search_url = "https://www.googleapis.com/youtube/v3/search"
        params = {'part': 'snippet', 'q': f"{subject_name} academic lecture", 'type': 'video', 'maxResults': 1, 'key': YOUTUBE_API_KEY}
        r = requests.get(search_url, params=params).json()
        item = r['items'][0]
        return f"https://www.youtube.com/watch?v={item['id']['videoId']}", item['snippet']['title'][:30] + "..."
    except:
        return fallback_url, "Search YouTube"

# --- UI STYLING ---
def set_background():
    # Subtle CSS for clean look
    st.markdown("""
        <style>
        .main { background-color: #f5f7f9; }
        .stButton>button { width: 100%; border-radius: 5px; height: 3em; }
        .stExpander { background-color: white !important; border-radius: 10px; }
        </style>
        """, unsafe_allow_html=True)

# --- APP PAGES ---
def login_page():
    st.title("🎓 Grade Improvement System")
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        u = st.text_input("Username", key="l_u")
        p = st.text_input("Password", type="password", key="l_p")
        if st.button("Login"):
            if check_login(u, p):
                st.session_state.logged_in = True
                st.session_state.username = u
                st.rerun()
            else:
                st.error("Invalid credentials")
                
    with tab2:
        new_u = st.text_input("New Username")
        new_p = st.text_input("New Password", type="password")
        if st.button("Register Account"):
            if create_user(new_u, new_p):
                st.success("Success! Go to Login tab.")
            else:
                st.error("User already exists.")

def data_entry_page():
    st.title(f"👋 Welcome, {st.session_state.username}")
    if st.button("Logout", key="logout"):
        st.session_state.logged_in = False
        st.rerun()

    cgpa = st.sidebar.number_input("Historical CGPA", 0.0, 10.0, 7.5)
    exam_type = st.sidebar.selectbox("Exam", ["CAT1", "CAT2", "FAT"])
    num_subs = st.sidebar.number_input("Number of Subjects", 1, 10, 3)

    subject_data = []
    with st.form("entry_form"):
        cols = st.columns(2)
        for i in range(num_subs):
            with cols[0]: s_name = st.text_input(f"Subject {i+1}", key=f"s_{i}")
            with cols[1]: s_mark = st.number_input(f"Marks/50", 0, 50, 30, key=f"m_{i}")
            
            grade = "F"
            if s_mark > 45: grade = "A"
            elif s_mark > 35: grade = "B"
            elif s_mark > 25: grade = "C"
            
            subject_data.append({"Subject": s_name, "Marks": s_mark, "Grade": grade})
        
        submitted = st.form_submit_button("Analyze & Save")

    if submitted:
        save_data(st.session_state.username, cgpa, subject_data)
        cat, sug = analyze_student_performance(cgpa, subject_data, exam_type)
        
        st.divider()
        st.subheader(f"Analysis: {cat}")
        st.markdown(sug[0])

        st.subheader("🔗 Recommended Learning")
        for sub in subject_data:
            if sub['Grade'] != "A":
                url, label = get_dynamic_course_link(sub['Subject'])
                st.link_button(f"Improve {sub['Subject']}: {label}", url)

# --- RUN APP ---
if __name__ == "__main__":
    init_db()
    set_background()
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    if st.session_state.logged_in:
        data_entry_page()
    else:
        login_page()
