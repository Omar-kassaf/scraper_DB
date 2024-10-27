import streamlit as st
import threading
import time
import os
import json
import pandas as pd
from users import user_data
from send_email import send_email
from dotenv import load_dotenv
from utils_funcs import *
from send_email_without_results import *
from google.cloud import firestore
from google.oauth2 import service_account

credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
credentials = service_account.Credentials.from_service_account_info(
    json.loads(credentials_json)
)

db = firestore.Client(credentials=credentials, project="rfp-scraping-438613")

load_dotenv()
# Save progress to a file for each user
def save_user_progress_to_firestore(username, task_id, progress):
    doc_ref = db.collection('user_progress').document(f"{username}_{task_id}")
    doc_ref.set(progress)


def load_user_progress_from_firestore(username, task_id):
    doc_ref = db.collection('user_progress').document(f"{username}_{task_id}")
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    return {"task_complete": True}


# Function to check user credentials
def check_credentials(username, password):
    return username in user_data and user_data[username]["password"] == password

# Function to check if the current user's task is complete
def check_user_task(username):
    progress = load_user_progress_from_firestore(username)
    return not progress.get("task_complete", True)

# Save task progress
def save_user_progress(username, task_id,keywords, selected_option, task_complete):
    progress = {
        "keywords": keywords,
        "selected_option": selected_option,
        "task_complete": task_complete
    }
    save_user_progress_to_firestore(username, task_id,progress)

# Function to check if any task is in progress for the logged-in user
def is_task_in_progress(username, task_id):
    progress = load_user_progress_from_firestore(username, task_id)
    return not progress.get("task_complete", True)

def extract_keywords_from_file(uploaded_file):
    try:
        # Read the uploaded file
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        elif uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file)
        else:
            st.error("Unsupported file format. Please upload a CSV or Excel file.")
            return []

        # Ensure the 'keywords' column exists
        if 'keywords' not in df.columns:
            st.error("The uploaded file must contain a column named 'keywords'.")
            return []

        # Extract and return the keywords as a list
        keywords = df['keywords'].dropna().tolist()
        return keywords
    except Exception as e:
        st.error("Error reading file. Please ensure it is a valid CSV or Excel file.")
        return []
  

def main():
    # User Authentication
    st.title("User Login")

    if "username" not in st.session_state:
        st.session_state["username"] = ""

    if "password" not in st.session_state:
        st.session_state["password"] = ""

    st.session_state["username"] = st.text_input("Username", value=st.session_state["username"])
    st.session_state["password"] = st.text_input("Password", type="password", value=st.session_state["password"])

    if st.button("Login"):
        if check_credentials(st.session_state["username"], st.session_state["password"]):
            st.success("Login successful!")
            st.session_state["authenticated"] = True
        else:
            st.error("Invalid username or password.")

    if st.session_state.get("authenticated"):
        show_email_input_page()

def show_email_input_page():
    st.title("Search Input")

    if "email" not in st.session_state:
        st.session_state["email"] = ""

    if "keywords" not in st.session_state:
        st.session_state["keywords"] = ""

    if "selected_option" not in st.session_state:
        st.session_state["selected_option"] = ""

    if "task_in_progress" not in st.session_state:
        st.session_state["task_in_progress"] = False

    st.session_state["email"] = st.text_input("Please Enter your email(s) (comma separated).", value=st.session_state["email"])
    
    if not st.session_state["email"]:
        st.warning("Please enter your email to proceed.")
        return

    # Block new requests for the current user if a task is still in progress
    if is_task_in_progress(st.session_state["username"], st.session_state.get("task_id", "")):
        st.warning(f"A task is already running for {st.session_state['username']}. Please wait until it is complete.")
        return

    # File upload for keywords
    uploaded_file = st.file_uploader("Upload a file containing keywords (CSV or Excel)", type=["csv", "xlsx"])
    file_keywords = extract_keywords_from_file(uploaded_file) if uploaded_file else []

    # Manual keyword entry
    manual_keywords = st.text_input("Enter keywords for search (comma-separated)", value=st.session_state["keywords"])
    manual_keywords_list = [kw.strip() for kw in manual_keywords.split(",") if kw.strip()]

    # Combine keywords from both file and manual entry
    all_keywords = list(set(file_keywords + manual_keywords_list))

    dropdown_options = ["التجارة", "المقاولات", "التشغيل والصيانة والنظافة للمنشآت", "العقارات والأراضي", "الصناعة والتعدين والتدوير", "الغاز والمياه والطاقة",
                          "المناجم والبترول والمحاجر", "الإعلام والنشر والتوزيع", "الاتصالات وتقنية المعلومات",
                          "الزراعة والصيد", "الرعاية الصحية والنقاهة", "التعليم والتدريب",
                          "التوظيف والاستقدام", "الأمن والسلامة", "النقل والبريد والتخزين",
                          "المهن الاستشارية", "السياحة والمطاعم والفنادق وتنظيم المعارض",
                          "المالية والتمويل والتأمين", "الخدمات الأخرى"]

    st.session_state["selected_option"] = st.selectbox("النشاط الاساسي", dropdown_options, index=dropdown_options.index(st.session_state["selected_option"]) if st.session_state["selected_option"] else 0)

    emails = [email.strip() for email in st.session_state["email"].split(",") if email.strip()]

    if st.button("Submit"):
        st.session_state["task_id"] = str(int(time.time()))
        save_user_progress_to_firestore(
            st.session_state["username"],
            st.session_state["task_id"],
            {
                "keywords": all_keywords,
                "selected_option": st.session_state["selected_option"],
                "task_complete": False,
            },
        )
        st.info("The process is running in the background. You will receive an email shortly.")
        # Start the background process in a thread
        process_request(emails, all_keywords, st.session_state["selected_option"], st.session_state["username"], st.session_state["task_id"])
        

        

    # Check task completion
    if check_user_task(st.session_state["username"], st.session_state.get("task_id", "")):
        st.success("Task completed successfully! You can now submit a new request.")

def process_request(emails, keywords, selected_option, username,task_id):
    try:
        progress = load_user_progress_from_firestore(username,task_id)
        progress["task_complete"] = False
        save_user_progress_to_firestore(username,task_id ,progress)

        time.sleep(5)  # Simulate processing time

        subject = f"Search Results for {', '.join(keywords)}"
        body = f"Keywords: {', '.join(keywords)}\nSelected Option: {selected_option}\nPlease find the attached results."

        get_terms_files(keywords, str(selected_option))  
        agg_files() 

        today_date = pd.to_datetime("today").strftime("%Y-%m-%d")
        file_name = f"tenders_{today_date}_filtered.csv"

        if not os.path.isfile(file_name):
            # Handle case where no results are found
            send_email_without_results(emails, subject, body)
            return  # Early return if no results found

        # Send email with results
        send_email(emails, subject, body)

    except Exception as e:
        print(f"Error: {e}")  # Log the error

    finally:
        # Mark task as complete regardless of success or failure
        progress = load_user_progress_from_firestore(username,task_id)
        progress["task_complete"] = True
        save_user_progress_to_firestore(username, task_id,progress)


if __name__ == "__main__":
    main()

