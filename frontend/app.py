import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import os 
import json 

# --- Configuration ---
BACKEND_URL = "http://127.0.0.1:8000" # Default for local development

# Attempt to get backend URL from environment variable for Render deployment
if "BACKEND_URL" in os.environ:
    BACKEND_URL = os.environ["BACKEND_URL"]
# No need for st.secrets check if primarily using environment variables or local default

# --- Session State Initialization ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'token' not in st.session_state:
    st.session_state['token'] = None
if 'username' not in st.session_state:
    st.session_state['username'] = None

# --- Helper Functions ---
def get_auth_headers():
    """Returns authorization headers if a token is present in session state."""
    if st.session_state['token']:
        return {"Authorization": f"Bearer {st.session_state['token']}"}
    return {}

def get_documents():
    """
    Fetches all documents from the backend and ensures their _id is a valid string.
    Filters out documents with invalid or missing _id.
    """
    try:
        response = requests.get(f"{BACKEND_URL}/documents/", headers=get_auth_headers())
        response.raise_for_status()
        documents = response.json()
        
        processed_and_valid_documents = []
        for doc in documents:
            if isinstance(doc, dict):
                doc_id = doc.get('_id')
                
                # Handle {"$oid": "..."} format
                if isinstance(doc_id, dict) and '$oid' in doc_id:
                    doc['_id'] = doc_id['$oid']
                # Handle already string format
                elif isinstance(doc_id, str):
                    doc['_id'] = doc_id
                # Fallback to 'id' if '_id' is not present or invalid, and then check if it's a valid string
                elif doc.get('id') is not None and isinstance(doc.get('id'), str):
                    doc['_id'] = doc['id']
                else:
                    # If no valid _id or id, skip this document
                    st.warning(f"A document named '{doc.get('filename', 'Unknown')}' could not be loaded due to a missing or invalid ID. Please check the backend logs for details.")
                    continue
                
                processed_and_valid_documents.append(doc)
            else:
                st.warning(f"A document entry could not be loaded as it was malformed. Please check the backend logs for details.")
        
        return processed_and_valid_documents
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to the backend or fetch documents: {e}. Please ensure the backend server is running and accessible.")
        return []

# --- Streamlit UI ---
st.set_page_config(
    page_title="Document Management System", 
    layout="wide", 
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://www.extremely.cool.app/help',
        'Report a bug': "https://www.extremely.cool.app/bug",
        'About': "# This is a header. This is an *extremely* cool app!"
    }
)

# Custom CSS for a cleaner look
st.markdown("""
    <style>
    .main .block-container {
        padding-top: 2rem;
        padding-right: 2rem;
        padding-left: 2rem;
        padding-bottom: 2rem;
    }
    .stButton>button {
        background-color: #4CAF50;
        color: white;
        border-radius: 5px;
        border: none;
        padding: 10px 20px;
        text-align: center;
        text-decoration: none;
        display: inline-block;
        font-size: 16px;
        margin: 4px 2px;
        cursor: pointer;
        -webkit-transition-duration: 0.4s; /* Safari */
        transition-duration: 0.4s;
    }
    .stButton>button:hover {
        background-color: #45a049;
        color: white;
    }
    .stExpander {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("📄 Document Management System")

# --- Authentication Section ---
if not st.session_state['logged_in']:
    st.sidebar.subheader("Authentication")
    auth_choice = st.sidebar.radio("Choose", ["Login", "Register"])

    if auth_choice == "Login":
        with st.sidebar.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")

            if submitted:
                try:
                    response = requests.post(
                        f"{BACKEND_URL}/token", 
                        data={"username": username, "password": password}
                    )
                    response.raise_for_status()
                    token_data = response.json()
                    st.session_state['token'] = token_data['access_token']
                    st.session_state['username'] = username
                    st.session_state['logged_in'] = True
                    st.sidebar.success("Logged in successfully!")
                    st.rerun()
                except requests.exceptions.RequestException as e:
                    error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                    st.sidebar.error(f"Login failed: {error_detail}. Please check your username and password, or register if you don't have an account.")
    elif auth_choice == "Register":
        with st.sidebar.form("register_form"):
            new_username = st.text_input("New Username")
            new_password = st.text_input("New Password", type="password")
            new_email = st.text_input("Email")
            submitted = st.form_submit_button("Register")

            if submitted:
                try:
                    response = requests.post(
                        f"{BACKEND_URL}/register/", 
                        data={"username": new_username, "password": new_password, "email": new_email}
                    )
                    response.raise_for_status()
                    st.sidebar.success("Registration successful! You can now log in with your new account.")
                    st.rerun()
                except requests.exceptions.RequestException as e:
                    error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                    st.sidebar.error(f"Registration failed: {error_detail}. Please try again with different credentials.")
    st.stop() # Stop execution if not logged in
else:
    st.sidebar.success(f"Logged in as: {st.session_state['username']}")
    if st.sidebar.button("Logout"):
        st.session_state['logged_in'] = False
        st.session_state['token'] = None
        st.session_state['username'] = None
        st.rerun()

# --- Sidebar ---
st.sidebar.header("Actions")
selected_action = st.sidebar.radio(
    "Choose an action", 
    [
        "Dashboard", 
        "Upload Document", 
        "Search Documents", 
        "Document Q&A", 
        "Manage Reminders", 
        "Manage Uploaded Files", 
        "Backup Data", 
        "Delete Document", 
        "FAISS Management",
        "Chat with AI",
        "Admin Feedback" # New admin feature
    ]
)

# --- Main Content ---

if selected_action == "Dashboard":
    st.header("📊 Dashboard")
    st.write("Welcome to your DMS. Here's a quick overview of your documents and activities.")
    
    st.subheader("Recent Documents")
    documents = get_documents() # Now get_documents returns already processed and valid documents
    if documents:
        df = pd.DataFrame(documents)
        df['upload_date'] = pd.to_datetime(df['upload_date'])
        st.dataframe(df[['filename', 'category', 'summary', 'upload_date']].sort_values(by="upload_date", ascending=False).head(10))
    else:
        st.info("No documents uploaded yet. Start by uploading one!")

elif selected_action == "Delete Document":
    st.header("🗑️ Delete a Document")
    st.write("Permanently remove a document from the system and its associated data.")
    documents = get_documents() # Now get_documents returns already processed and valid documents
    if documents:
        # No need for valid_documents filter here, as get_documents already handles it
        # Sort documents by upload_date for easier selection of recent ones
        documents.sort(key=lambda x: datetime.fromisoformat(x['upload_date']) if isinstance(x['upload_date'], str) else x['upload_date'], reverse=True)
        
        doc_options = {f"{doc['filename']} (Uploaded: {doc['upload_date']})": doc['_id'] for doc in documents}
        selected_doc_display = st.selectbox("Select a document to delete", list(doc_options.keys()))
        
        if st.button("Confirm Delete", help="This action cannot be undone."):
            if selected_doc_display:
                doc_id_to_delete = doc_options[selected_doc_display]
                # doc_id_to_delete should always be valid here due to get_documents processing
                with st.spinner(f"Deleting document '{selected_doc_display}'..."): # Added spinner
                    try:
                        response = requests.delete(f"{BACKEND_URL}/documents/{doc_id_to_delete}", headers=get_auth_headers())
                        response.raise_for_status()
                        st.success(f"Document '{selected_doc_display}' deleted successfully!")
                        st.rerun() # Refresh the page to update the document list
                    except requests.exceptions.RequestException as e:
                        error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                        st.error(f"Failed to delete document: {error_detail}. Please try again or check backend logs.")
                        st.error(f"Response content: {e.response.content}")
    else:
        st.info("No documents to delete.")

elif selected_action == "Upload Document":
    st.header("⬆️ Upload New Document(s)")
    st.write("Upload one or more documents to be indexed and made searchable.")
    
    with st.form("upload_form", clear_on_submit=True):
        uploaded_files = st.file_uploader("Choose file(s)", type=['pdf', 'png', 'jpg', 'jpeg', 'docx', 'xlsx', 'xls', 'csv'], accept_multiple_files=True)
        
        # Collect original file paths for each uploaded file
        original_filepaths = []
        if uploaded_files:
            st.subheader("Original File Paths (Optional)")
            st.write("Enter the full path where each file is located on your computer. This path will be stored for your reference.")
            for i, file in enumerate(uploaded_files):
                original_filepaths.append(st.text_input(f"Path for {file.name}", key=f"original_path_{i}"))

        category = st.text_input("Category (optional, applies to all files)", help="Assign a category to all documents for better organization.")
        tags = st.text_input("Tags (comma-separated, optional, applies to all files)", help="Add keywords to easily find your documents later.")
        pdf_password = st.text_input("PDF Password (if applicable, optional, applies to all PDF files)", type="password", help="If your PDFs are password-protected, enter the password here.")
        
        submitted = st.form_submit_button("Upload Document(s)")
        
        if submitted and uploaded_files:
            files_to_send = []
            for file in uploaded_files:
                files_to_send.append(('files', (file.name, file.getvalue(), file.type)))
            
            data = {
                'category': category, 
                'tags': tags.split(',') if tags else [],
                'password': pdf_password if pdf_password else ''
            }
            
            # CRITICAL FIX: Send the full list of paths under the key expected by the backend alias.
            # The original loop was overwriting the value. requests will correctly encode this list.
            data['original_filepaths[]'] = original_filepaths

            with st.spinner(f"Uploading and processing {len(uploaded_files)} document(s)... This may take a moment."):
                try:
                    response = requests.post(f"{BACKEND_URL}/upload/", files=files_to_send, data=data, headers=get_auth_headers())
                    response.raise_for_status()
                    
                    response_data = response.json()
                    
                    if response.status_code == 200:
                        st.success(response_data.get("message", "Documents uploaded successfully!"))
                    elif response.status_code == 207: # Multi-Status
                        st.warning(response_data.get("message", "Some documents failed to upload/process. Check individual statuses below."))
                    
                    for doc_info in response_data.get("uploaded_documents", []):
                        if doc_info.get("status") == "failed":
                            st.error(f"Failed to process '{doc_info.get('filename')}': {doc_info.get('detail')}. Please check the file format or content.")
                        else:
                            st.success(f"Successfully processed '{doc_info.get('filename')}'")
                            # Check if extracted_text is empty and alert the user
                            if not doc_info.get('extracted_text', '').strip():
                                st.warning(f"⚠️ Warning: No text could be extracted from '{doc_info.get('filename')}'. This document may not be searchable.")
                            # Store uploaded document and potential reminders in session state for the last successful upload
                            st.session_state['last_uploaded_document'] = doc_info
                            st.session_state['potential_reminders_to_create'] = doc_info.get('potential_reminders', [])
                    
                    st.rerun() # Rerun to display reminders outside the form and update document list
                except requests.exceptions.RequestException as e:
                    error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                    if "password-protected" in error_detail.lower() or "encrypted" in error_detail.lower():
                        st.error(f"Error: One or more PDFs are password-protected or encrypted. Please provide the correct password.")
                    else:
                        st.error(f"Error uploading documents: {error_detail}. Please ensure the backend is running and the file is valid.")
                    st.error(f"Response content: {e.response.content}")
    
    # Display potential reminders if any were found in the last upload
    if 'potential_reminders_to_create' in st.session_state and st.session_state['potential_reminders_to_create']:
        st.subheader("🔔 AI Suggested Reminders")
        st.write("The AI has identified potential reminders in your document. Select which ones to create:")
        
        # Use a list to store selected reminders from checkboxes
        temp_selected_reminders = []
        for i, pr in enumerate(st.session_state['potential_reminders_to_create']):
            # Use a unique key for each checkbox
            if st.checkbox(f"**{pr['message']}** (Due: {pr['date']})", key=f"reminder_checkbox_{i}"):
                temp_selected_reminders.append(pr)
        
        # Store the currently selected reminders in session state for the button click
        st.session_state['currently_selected_reminders'] = temp_selected_reminders

        if st.button("Create Selected Reminders"):
            if 'currently_selected_reminders' in st.session_state and st.session_state['currently_selected_reminders']:
                with st.spinner("Creating reminders..."):
                    for reminder_data in st.session_state['currently_selected_reminders']:
                        try:
                            due_datetime_str = reminder_data['date']
                            
                            reminder_payload = {
                                "document_id": st.session_state['last_uploaded_document']['id'],
                                "due_date": due_datetime_str, # Send as YYYY-MM-DD string
                                "message": reminder_data['message']
                            }
                            rem_response = requests.post(f"{BACKEND_URL}/reminders/", json=reminder_payload, headers=get_auth_headers())
                            rem_response.raise_for_status()
                            st.success(f"Reminder '{reminder_data['message']}' created successfully!")
                        except requests.exceptions.RequestException as rem_e:
                            st.error(f"Failed to create reminder '{reminder_data['message']}': {rem_e}. Please try again.")
                            st.error(f"Response content: {rem_e.response.content}")
                
                # Clear potential reminders from session state after creation attempt
                del st.session_state['last_uploaded_document']
                del st.session_state['potential_reminders_to_create']
                del st.session_state['currently_selected_reminders']
                st.rerun() # Refresh to show new reminders and clear the section
            else:
                st.warning("No reminders selected to create.")

elif selected_action == "Search Documents":
    st.header("🔍 Search Documents")
    st.write("Find documents using keyword or semantic search.")
    
    search_query = st.text_input("Enter your search query")
    search_type = st.selectbox("Search Type", ["keyword", "semantic"])
    
    if st.button("Search"):
        if search_query:
            data = {'query': search_query, 'search_type': search_type}
            with st.spinner("Searching documents..."):
                try:
                    response = requests.post(f"{BACKEND_URL}/search/", json=data, headers=get_auth_headers())
                    response.raise_for_status()
                    results = response.json()
                    
                    if results:
                        st.subheader("Search Results")
                        for result in results:
                            with st.expander(f"📄 {result['filename']} (Category: {result.get('category', 'N/A')})"):
                                st.write(f"**Summary:** {result.get('summary', 'N/A')}")
                                st.write(f"**Upload Date:** {result['upload_date']}")
                                if result.get('original_filepath'):
                                    st.write(f"**Original Location:** `{result['original_filepath']}`")
                                st.write(f"**Tags:** {', '.join(result.get('tags', []))}")
                                st.text_area("Extracted Text", result.get('extracted_text', ''), height=200, key=f"extracted_text_{result['_id']}")
                    else:
                        st.info("No results found for your query.")
                except requests.exceptions.RequestException as e:
                    error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                    st.error(f"Error during search: {error_detail}. Please check your query and ensure the backend is running.")
                    st.error(f"Response content: {e.response.content}")

elif selected_action == "Document Q&A":
    st.header("❓ Ask a Question About a Document")
    st.write("Get answers directly from your indexed documents using AI.")
    
    documents = get_documents() # Now get_documents returns already processed and valid documents
    if not documents:
        st.warning("Please upload a document first to use this feature.")
    else:
        # Sort documents by upload_date for easier selection of recent ones
        documents.sort(key=lambda x: datetime.fromisoformat(x['upload_date']) if isinstance(x['upload_date'], str) else x['upload_date'], reverse=True)
        
        doc_options = {f"{doc['filename']} (Uploaded: {doc['upload_date']})": doc['_id'] for doc in documents}
        selected_doc_display = st.selectbox("Select a document to ask a question about", list(doc_options.keys()))
        
        # Extract the actual doc_id from the selected display string
        selected_doc_id = doc_options[selected_doc_display]
        
        # Display original file path if available
        selected_document = next((doc for doc in documents if doc['_id'] == selected_doc_id), None)
        if selected_document and selected_document.get('original_filepath'):
            st.info(f"**Original File Location:** `{selected_document['original_filepath']}`")

        question = st.text_input("Your Question")
        
        if st.button("Ask"):
            if selected_doc_display and question:
                doc_id = selected_doc_id # Use the extracted doc_id
                
                with st.spinner("Getting answer from the document..."):
                    try:
                        data = {'document_id': doc_id, 'question': question}
                        response = requests.post(f"{BACKEND_URL}/qa/", json=data, headers=get_auth_headers())
                        response.raise_for_status()
                        answer = response.json().get('answer')
                        st.markdown("### Answer")
                        if answer:
                            st.info(str(answer)) # Ensure answer is a string
                        else:
                            st.warning("No answer could be retrieved for your question from this document.")
                    except requests.exceptions.RequestException as e:
                        error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                        st.error(f"Failed to get answer: {error_detail}. Please ensure the backend is running and the document has extracted text.")
                        st.error(f"Response content: {e.response.content}")

elif selected_action == "Manage Reminders":
    st.header("⏰ Manage Reminders")
    st.write("Set and manage reminders for your documents.")
    
    st.subheader("Create a New Reminder")
    
    documents = get_documents() # Now get_documents returns already processed and valid documents
    doc_options = {doc['filename']: doc['_id'] for doc in documents}
    selected_doc_name = st.selectbox("Select a document", list(doc_options.keys()))
    
    due_date = st.date_input("Due Date")
    due_time = st.time_input("Due Time")
    message = st.text_input("Reminder Message")
    
    if st.button("Set Reminder"):
        if selected_doc_name and message:
            doc_id = doc_options[selected_doc_name]
            due_datetime = datetime.combine(due_date, due_time)
            
            reminder_data = {
                "document_id": doc_id,
                "due_date": due_datetime.isoformat(),
                "message": message
            }
            
            with st.spinner("Setting reminder..."):
                try:
                    response = requests.post(f"{BACKEND_URL}/reminders/", json=reminder_data, headers=get_auth_headers())
                    response.raise_for_status()
                    st.success("Reminder set successfully!")
                    st.rerun()
                except requests.exceptions.RequestException as e:
                    st.error(f"Failed to set reminder: {e}. Please check your input and ensure the backend is running.")
                    st.error(f"Response content: {e.response.content}")

    st.subheader("Upcoming Reminders")
    try:
        response = requests.get(f"{BACKEND_URL}/reminders/", headers=get_auth_headers())
        response.raise_for_status()
        reminders = response.json()
        if reminders:
            df_reminders = pd.DataFrame(reminders)
            df_reminders['due_date'] = pd.to_datetime(df_reminders['due_date'])
            
            # Display reminders with actions
            for i, reminder in df_reminders.sort_values(by="due_date").iterrows():
                # Ensure _id is not None before proceeding
                if reminder.get('_id') is None:
                    st.warning(f"A reminder entry could not be loaded due to a missing or invalid ID. Please check the backend logs for details.")
                    continue

                col1, col2, col3, col4, col5 = st.columns([0.5, 2, 1.5, 1, 1])
                with col1:
                    st.write(f"**Status:** {reminder['status'].capitalize()}")
                with col2:
                    st.write(f"**Message:** {reminder['message']}")
                with col3:
                    st.write(f"**Due Date:** {reminder['due_date'].strftime('%Y-%m-%d %H:%M')}")
                with col4:
                    if reminder['status'] == 'pending':
                        if st.button("Mark as Done", key=f"mark_done_{reminder['_id']}"):
                            try:
                                response = requests.put(f"{BACKEND_URL}/reminders/{reminder['_id']}/status", json={"status": "done"}, headers=get_auth_headers())
                                response.raise_for_status()
                                st.success("Reminder marked as done!")
                                st.rerun()
                            except requests.exceptions.RequestException as e:
                                st.error(f"Failed to mark reminder as done: {e}. Please try again.")
                    else:
                        if st.button("Mark as Pending", key=f"mark_pending_{reminder['_id']}"):
                            try:
                                response = requests.put(f"{BACKEND_URL}/reminders/{reminder['_id']}/status", json={"status": "pending"}, headers=get_auth_headers())
                                response.raise_for_status()
                                st.success("Reminder marked as pending!")
                                st.rerun()
                            except requests.exceptions.RequestException as e:
                                st.error(f"Failed to mark reminder as pending: {e}. Please try again.")
                with col5:
                    if st.button("Delete", key=f"delete_rem_{reminder['_id']}"):
                        try:
                            response = requests.delete(f"{BACKEND_URL}/reminders/{reminder['_id']}", headers=get_auth_headers())
                            response.raise_for_status()
                            st.success("Reminder deleted successfully!")
                            st.rerun()
                        except requests.exceptions.RequestException as e:
                            st.error(f"Failed to delete reminder: {e}. Please try again.")
            
        else:
            st.info("No upcoming reminders.")
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to fetch reminders: {e}. Please ensure the backend is running.")
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to fetch reminders: {e}. Please ensure the backend is running.")

elif selected_action == "FAISS Management":
    st.header("⚙️ FAISS Index Management")
    st.write("Manage the FAISS index for semantic search. Rebuilding is recommended after significant data changes.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Clear FAISS Index", help="This will remove all documents from the semantic search index."):
            with st.spinner("Clearing FAISS index..."):
                try:
                    response = requests.post(f"{BACKEND_URL}/faiss/clear", headers=get_auth_headers())
                    response.raise_for_status()
                    st.success("FAISS index cleared successfully!")
                    st.rerun()
                except requests.exceptions.RequestException as e:
                    st.error(f"Failed to clear FAISS index: {e}. Please ensure the backend is running.")
                    st.error(f"Response content: {e.response.content}")
    with col2:
        if st.button("Rebuild FAISS Index", help="This will re-index all documents from the database for semantic search."):
            with st.spinner("Rebuilding FAISS index from all documents..."):
                try:
                    response = requests.post(f"{BACKEND_URL}/faiss/rebuild", headers=get_auth_headers())
                    response.raise_for_status()
                    st.success("FAISS index rebuilt successfully!")
                    st.rerun()
                except requests.exceptions.RequestException as e:
                    st.error(f"Failed to rebuild FAISS index: {e}. Please ensure the backend is running.")
                    st.error(f"Response content: {e.response.content}")

elif selected_action == "Backup Data":
    st.header("📦 Backup Indexed Documents")
    st.write("You can backup all indexed document metadata and extracted text to a specified folder on your system.")
    st.warning("Note: For this feature to work, the backup directory you specify must be accessible by the Docker container. This typically means it needs to be a mounted volume in your Docker setup.")

    backup_folder_path = st.text_input("Enter the backup folder path (e.g., /app/backups or C:\\Users\\YourUser\\DMS_Backups)", help="This path should be accessible from within the Docker container. If running locally, ensure it's a mounted volume.")

    if st.button("Initiate Backup"):
        if backup_folder_path:
            with st.spinner("Backing up documents..."):
                try:
                    response = requests.post(f"{BACKEND_URL}/backup/documents", json={"backup_path": backup_folder_path}, headers=get_auth_headers())
                    response.raise_for_status()
                    st.success(response.json().get("message", "Backup initiated successfully!"))
                except requests.exceptions.RequestException as e:
                    error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                    st.error(f"Failed to initiate backup: {error_detail}. Please check the backup path and backend logs.")
                    st.error(f"Response content: {e.response.content}")
        else:
            st.warning("Please provide a backup folder path.")

elif selected_action == "Manage Uploaded Files":
    st.header("📁 Manage Uploaded Files")
    st.write("Here you can view and manually delete files that are currently in the 'uploads' directory. These are temporary files that were not automatically deleted or are awaiting processing.")

    try:
        response = requests.get(f"{BACKEND_URL}/files/uploaded", headers=get_auth_headers())
        response.raise_for_status()
        uploaded_files = response.json()

        if uploaded_files:
            st.subheader("Files in 'uploads' directory:")
            for file_info in uploaded_files:
                filename = file_info['filename']
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"- {filename}")
                with col2:
                    if st.button(f"Delete {filename}", key=f"delete_uploaded_{filename}", help="Permanently delete this file from the 'uploads' directory."):
                        try:
                            delete_response = requests.delete(f"{BACKEND_URL}/files/uploaded/{filename}", headers=get_auth_headers())
                            delete_response.raise_for_status()
                            st.success(f"File '{filename}' deleted successfully!")
                            st.rerun() # Refresh the page to update the list
                        except requests.exceptions.RequestException as e:
                            st.error(f"Failed to delete file '{filename}': {e}. Please try again or check backend logs.")
                            st.error(f"Response content: {e.response.content}")
        else:
            st.info("No files found in the 'uploads' directory.")

    except requests.exceptions.RequestException as e:
        st.error(f"Failed to fetch uploaded files: {e}. Please ensure the backend is running.")
        st.error(f"Response content: {e.response.content}")

elif selected_action == "Chat with AI":
    st.header("💬 Chat with AI")
    st.write("Engage in a conversation with the AI about your documents and other data.")

    # Initialize session state for current conversation if not present
    # Initialize session state for current conversation if not present
    if 'current_conversation_id' not in st.session_state:
        st.session_state['current_conversation_id'] = None
    if 'current_conversation_title' not in st.session_state:
        st.session_state['current_conversation_title'] = "New Chat"

    # Removed debug prints for cleaner UI, as backend logs are now detailed.
    # DEBUG: Initial current_conversation_id: {st.session_state['current_conversation_id']}

    # Sidebar for conversation selection
    st.sidebar.subheader("Your Conversations")
    
    # Fetch conversations
    conversations = []
    try:
        response = requests.get(f"{BACKEND_URL}/conversations/", headers=get_auth_headers())
        response.raise_for_status()
        conversations = response.json()
        # DEBUG: Fetched conversations from backend: {conversations}
    except requests.exceptions.RequestException as e:
        st.sidebar.error(f"Failed to fetch conversations: {e}. Please ensure the backend is running.")

    conversation_options = {"New Chat": None}
    if conversations:
        for conv in conversations:
            # Ensure _id is a string
            conv_id = conv.get('_id')
            if isinstance(conv_id, dict) and '$oid' in conv_id:
                conv_id = conv_id['$oid']
            elif not isinstance(conv_id, str):
                continue # Skip malformed conversation IDs

            # Use the full conv_id for uniqueness in the display string
            display_key = f"{conv.get('title', 'Untitled')} (ID: {conv_id})"
            conversation_options[display_key] = conv_id
    # DEBUG: Constructed conversation_options: {conversation_options}

    # Determine the initial index for the selectbox
    initial_index = 0
    if st.session_state['current_conversation_id'] in conversation_options.values():
        initial_index = list(conversation_options.values()).index(st.session_state['current_conversation_id'])
    # DEBUG: Initial selectbox index: {initial_index}

    def update_conversation_selection():
        selected_key = st.session_state.conversation_selector_key
        st.session_state['current_conversation_id'] = conversation_options[selected_key]
        st.session_state['current_conversation_title'] = selected_key.split(' (ID:')[0] if st.session_state['current_conversation_id'] else "New Chat"
        st.rerun() # Rerun to load new conversation messages

    # Selectbox for conversations
    selected_conv_display = st.sidebar.selectbox(
        "Select or create a conversation",
        list(conversation_options.keys()),
        index=initial_index,
        key="conversation_selector_key", # Add a unique key
        on_change=update_conversation_selection # Use a callback
    )
    # DEBUG: Selected conversation display: {selected_conv_display}
    
    # Display current conversation title
    st.subheader(f"Conversation: {st.session_state['current_conversation_title']}")

    # Chat message display area
    chat_container = st.container(height=400, border=True)

    # Fetch and display messages for the current conversation
    messages = []
    if st.session_state['current_conversation_id']:
        try:
            response = requests.get(f"{BACKEND_URL}/conversations/{st.session_state['current_conversation_id']}/messages", headers=get_auth_headers())
            response.raise_for_status()
            # Check if response content is empty or malformed
            if not response.text.strip():
                st.warning("Received empty response for messages. This might indicate no messages or a backend issue.")
                messages = []
            else:
                messages = response.json()
            
            # DEBUG: Raw response text for messages: {response.text}
            # DEBUG: Fetched messages for current conversation: {messages}
        except requests.exceptions.RequestException as e:
            st.error(f"Failed to fetch messages for this conversation: {e}. Please ensure the backend is running.")
        except json.JSONDecodeError as e:
            st.error(f"Failed to decode messages from backend: {e}. Raw response: {response.text}. Please check backend logs.")
            messages = []
    
    for msg in messages:
        with chat_container:
            if msg['sender'] == 'user':
                st.chat_message("user").write(msg['message'])
            else:
                st.chat_message("ai").write(msg['message'])

    # Chat input
    user_input = st.chat_input("Type your message here...")

    if user_input:
        with st.spinner("Sending message..."):
            try:
                conversation_id_to_use = st.session_state['current_conversation_id']
                
                # If "New Chat" is selected, create a new conversation first
                if conversation_id_to_use is None:
                    create_conv_response = requests.post(f"{BACKEND_URL}/conversations/", json={"title": "New Chat"}, headers=get_auth_headers())
                    create_conv_response.raise_for_status()
                    new_conv = create_conv_response.json()
                    # The backend returns '_id' as per Pydantic alias, not 'id'
                    conversation_id_to_use = new_conv['_id'] 
                    st.session_state['current_conversation_id'] = conversation_id_to_use
                    st.session_state['current_conversation_title'] = new_conv['title']
                    st.success("New conversation created!")
                
                # Send user message to backend and get AI response
                message_payload = {"message": user_input}
                response = requests.post(
                    f"{BACKEND_URL}/conversations/{conversation_id_to_use}/send", # Corrected endpoint to /send
                    json=message_payload,
                    headers=get_auth_headers()
                )
                response.raise_for_status()
                
                # The backend /conversations/{conversation_id}/messages endpoint returns the AI's ChatMessage object
                # The frontend should just trigger a rerun to fetch all messages again.
                st.rerun()
            except requests.exceptions.RequestException as e:
                error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                st.error(f"Failed to send message: {error_detail}. Please try again or check backend logs.")
                st.error(f"Response content: {e.response.content}")
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}. Please try again.")
                st.error(f"Error details: {e}")

    # Conversation management buttons
    if st.session_state['current_conversation_id']:
        st.markdown("---")
        st.subheader("Manage Current Conversation")
        col_del_conv, col_del_msg = st.columns(2)
        with col_del_conv:
            if st.button("Delete Current Conversation", help="This will delete the entire conversation history."):
                if st.session_state['current_conversation_id']:
                    try:
                        response = requests.delete(f"{BACKEND_URL}/conversations/{st.session_state['current_conversation_id']}", headers=get_auth_headers())
                        response.raise_for_status()
                        st.success("Conversation deleted successfully!")
                        st.session_state['current_conversation_id'] = None
                        st.session_state['current_conversation_title'] = "New Chat"
                        st.rerun()
                    except requests.exceptions.RequestException as e:
                        error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                        st.error(f"Failed to delete conversation: {error_detail}. Please try again or check backend logs.")
                        st.error(f"Response content: {e.response.content}")
        with col_del_msg:
            if messages:
                # Create a list of display strings for the selectbox
                message_display_options = [
                    f"{msg['sender'].capitalize()}: {msg['message'][:70]}{'...' if len(msg['message']) > 70 else ''} (ID: {msg['_id']})"
                    for msg in messages
                ]
                # Map display string back to original message object or ID
                message_map = {
                    f"{msg['sender'].capitalize()}: {msg['message'][:70]}{'...' if len(msg['message']) > 70 else ''} (ID: {msg['_id']})": msg['_id']
                    for msg in messages
                }

                message_to_delete_display = st.selectbox(
                    "Select a message to delete",
                    message_display_options,
                    key="delete_msg_select"
                )
                
                if st.button("Delete Selected Message", key="confirm_delete_msg_button"):
                    if message_to_delete_display:
                        message_id_to_delete = message_map[message_to_delete_display]
                        try:
                            response = requests.delete(f"{BACKEND_URL}/messages/{message_id_to_delete}", headers=get_auth_headers())
                            response.raise_for_status()
                            st.success("Message deleted successfully!")
                            st.rerun()
                        except requests.exceptions.RequestException as e:
                            error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                            st.error(f"Failed to delete message: {error_detail}. Please try again or check backend logs.")
                            st.error(f"Response content: {e.response.content}")
            else:
                st.info("No messages in this conversation to delete.")

elif selected_action == "Admin Feedback":
    st.header("🧑‍💻 Admin Document Feedback")
    st.write("Review and manage feedback provided for documents to improve AI performance.")

    try:
        response = requests.get(f"{BACKEND_URL}/admin/feedback/", headers=get_auth_headers())
        response.raise_for_status()
        feedback_entries = response.json()

        if feedback_entries:
            st.subheader("All Document Feedback Entries")
            for feedback in feedback_entries:
                with st.expander(f"Feedback for Document ID: {feedback['document_id']} (Type: {feedback['feedback_type']})"):
                    st.write(f"**Feedback ID:** {feedback['_id']}")
                    st.write(f"**Admin User ID:** {feedback['user_id']}")
                    st.write(f"**Feedback Type:** {feedback['feedback_type']}")
                    if feedback.get('field_name'):
                        st.write(f"**Field Name:** {feedback['field_name']}")
                    if feedback.get('chunk_id'):
                        st.write(f"**Chunk ID:** {feedback['chunk_id']}")
                    if feedback.get('original_content'):
                        st.text_area("Original Content", feedback['original_content'], height=100, key=f"original_{feedback['_id']}")
                    if feedback.get('corrected_content'):
                        st.text_area("Corrected Content", feedback['corrected_content'], height=100, key=f"corrected_{feedback['_id']}")
                    if feedback.get('notes'):
                        st.text_area("Notes", feedback['notes'], height=100, key=f"notes_{feedback['_id']}")
                    st.write(f"**Created At:** {datetime.fromisoformat(feedback['created_at']).strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    col_edit, col_delete = st.columns(2)
                    with col_edit:
                        if st.button("Edit Feedback", key=f"edit_feedback_{feedback['_id']}"):
                            st.session_state['edit_feedback_id'] = feedback['_id']
                            st.session_state['edit_feedback_data'] = feedback
                            st.rerun()
                    with col_delete:
                        if st.button("Delete Feedback", key=f"delete_feedback_{feedback['_id']}"):
                            try:
                                delete_response = requests.delete(f"{BACKEND_URL}/admin/feedback/{feedback['_id']}", headers=get_auth_headers())
                                delete_response.raise_for_status()
                                st.success(f"Feedback {feedback['_id']} deleted successfully!")
                                st.rerun()
                            except requests.exceptions.RequestException as e:
                                error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                                st.error(f"Failed to delete feedback: {error_detail}")
                                st.error(f"Response content: {e.response.content}")
        else:
            st.info("No document feedback entries found.")

    except requests.exceptions.RequestException as e:
        error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
        st.error(f"Failed to fetch feedback entries: {error_detail}. Please ensure the backend is running and you are logged in as an admin.")
        st.error(f"Response content: {e.response.content}")

    st.subheader("Submit New Feedback")
    with st.form("new_feedback_form", clear_on_submit=True):
        documents = get_documents()
        doc_options = {f"{doc['filename']} (ID: {doc['_id']})": doc['_id'] for doc in documents}
        selected_doc_display = st.selectbox("Select Document", list(doc_options.keys()), key="new_feedback_doc_select")
        selected_doc_id = doc_options[selected_doc_display] if selected_doc_display else None

        feedback_type = st.selectbox("Feedback Type", ["OCR_CORRECTION", "SUMMARY_ADJUSTMENT", "CATEGORY_ADJUSTMENT", "TAG_ADJUSTMENT", "PII_VALIDATION", "QA_CORRECTION", "OTHER"], key="new_feedback_type")
        field_name = st.text_input("Field Name (e.g., extracted_text, summary, category, tags, extracted_info.name)", key="new_feedback_field_name")
        original_content = st.text_area("Original Content (if applicable)", key="new_feedback_original_content")
        corrected_content = st.text_area("Corrected Content", key="new_feedback_corrected_content")
        notes = st.text_area("Notes", key="new_feedback_notes")

        submitted = st.form_submit_button("Submit Feedback")

        if submitted:
            if not selected_doc_id or not corrected_content:
                st.error("Document and corrected content are required.")
            else:
                feedback_payload = {
                    "document_id": selected_doc_id,
                    "feedback_type": feedback_type,
                    "field_name": field_name if field_name else None,
                    "original_content": original_content if original_content else None,
                    "corrected_content": corrected_content,
                    "notes": notes if notes else None
                }
                try:
                    response = requests.post(f"{BACKEND_URL}/admin/feedback/", json=feedback_payload, headers=get_auth_headers())
                    response.raise_for_status()
                    st.success("Feedback submitted successfully!")
                    st.rerun()
                except requests.exceptions.RequestException as e:
                    error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                    st.error(f"Failed to submit feedback: {error_detail}")
                    st.error(f"Response content: {e.response.content}")

    # Edit Feedback Form (appears when 'Edit Feedback' button is clicked)
    if 'edit_feedback_id' in st.session_state and st.session_state['edit_feedback_id']:
        st.subheader(f"Edit Feedback Entry: {st.session_state['edit_feedback_id']}")
        feedback_to_edit = st.session_state['edit_feedback_data']

        with st.form("edit_feedback_form", clear_on_submit=False):
            # Pre-fill fields with existing data
            edit_feedback_type = st.selectbox("Feedback Type", ["OCR_CORRECTION", "SUMMARY_ADJUSTMENT", "CATEGORY_ADJUSTMENT", "TAG_ADJUSTMENT", "PII_VALIDATION", "QA_CORRECTION", "OTHER"], index=["OCR_CORRECTION", "SUMMARY_ADJUSTMENT", "CATEGORY_ADJUSTMENT", "TAG_ADJUSTMENT", "PII_VALIDATION", "QA_CORRECTION", "OTHER"].index(feedback_to_edit['feedback_type']), key="edit_feedback_type")
            edit_field_name = st.text_input("Field Name", value=feedback_to_edit.get('field_name', ''), key="edit_feedback_field_name")
            edit_original_content = st.text_area("Original Content", value=feedback_to_edit.get('original_content', ''), key="edit_feedback_original_content")
            edit_corrected_content = st.text_area("Corrected Content", value=feedback_to_edit.get('corrected_content', ''), key="edit_feedback_corrected_content")
            edit_notes = st.text_area("Notes", value=feedback_to_edit.get('notes', ''), key="edit_feedback_notes")

            col_update, col_cancel = st.columns(2)
            with col_update:
                if st.form_submit_button("Update Feedback"):
                    if not edit_corrected_content:
                        st.error("Corrected content is required.")
                    else:
                        update_payload = {
                            "document_id": feedback_to_edit['document_id'], # Document ID remains the same
                            "feedback_type": edit_feedback_type,
                            "field_name": edit_field_name if edit_field_name else None,
                            "original_content": edit_original_content if edit_original_content else None,
                            "corrected_content": edit_corrected_content,
                            "notes": edit_notes if edit_notes else None
                        }
                        try:
                            response = requests.put(f"{BACKEND_URL}/admin/feedback/{st.session_state['edit_feedback_id']}", json=update_payload, headers=get_auth_headers())
                            response.raise_for_status()
                            st.success("Feedback updated successfully!")
                            del st.session_state['edit_feedback_id']
                            del st.session_state['edit_feedback_data']
                            st.rerun()
                        except requests.exceptions.RequestException as e:
                            error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                            st.error(f"Failed to update feedback: {error_detail}")
                            st.error(f"Response content: {e.response.content}")
            with col_cancel:
                if st.form_submit_button("Cancel Edit"):
                    del st.session_state['edit_feedback_id']
                    del st.session_state['edit_feedback_data']
                    st.rerun()
