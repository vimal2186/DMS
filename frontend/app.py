import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# --- Configuration ---
BACKEND_URL = "http://127.0.0.1:8000"

# --- Helper Functions ---
def get_documents():
    """
    Fetches all documents from the backend and ensures their _id is a valid string.
    Filters out documents with invalid or missing _id.
    """
    try:
        response = requests.get(f"{BACKEND_URL}/documents/")
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
                    st.warning(f"Skipping document with invalid or missing ID: {doc.get('filename', 'Unknown')}")
                    continue
                
                processed_and_valid_documents.append(doc)
            else:
                st.warning(f"Skipping malformed document entry (not a dictionary): {doc}")
        
        return processed_and_valid_documents
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching documents: {e}")
        return []

# --- Streamlit UI ---
st.set_page_config(page_title="Document Management System", layout="wide")

st.title("📄 Document Management System")

# --- Sidebar ---
st.sidebar.header("Actions")
selected_action = st.sidebar.radio("Choose an action", ["Dashboard", "Upload Document", "Search Documents", "Document Q&A", "Manage Reminders", "Delete Document", "FAISS Management"])

# --- Main Content ---

if selected_action == "Dashboard":
    st.header("Dashboard")
    st.write("Welcome to your DMS. Here's a quick overview:")
    
    st.subheader("Recent Documents")
    documents = get_documents() # Now get_documents returns already processed and valid documents
    if documents:
        df = pd.DataFrame(documents)
        df['upload_date'] = pd.to_datetime(df['upload_date'])
        st.dataframe(df[['filename', 'category', 'summary', 'upload_date']].sort_values(by="upload_date", ascending=False).head(10))
    else:
        st.info("No documents uploaded yet.")

elif selected_action == "Delete Document":
    st.header("Delete a Document")
    documents = get_documents() # Now get_documents returns already processed and valid documents
    if documents:
        # No need for valid_documents filter here, as get_documents already handles it
        # Sort documents by upload_date for easier selection of recent ones
        documents.sort(key=lambda x: datetime.fromisoformat(x['upload_date']) if isinstance(x['upload_date'], str) else x['upload_date'], reverse=True)
        
        doc_options = {f"{doc['filename']} (Uploaded: {doc['upload_date']})": doc['_id'] for doc in documents}
        selected_doc_display = st.selectbox("Select a document to delete", list(doc_options.keys()))
        
        if st.button("Confirm Delete"):
            if selected_doc_display:
                doc_id_to_delete = doc_options[selected_doc_display]
                # doc_id_to_delete should always be valid here due to get_documents processing
                try:
                    response = requests.delete(f"{BACKEND_URL}/documents/{doc_id_to_delete}")
                    response.raise_for_status()
                    st.success(f"Document {selected_doc_display} deleted successfully!")
                    st.rerun() # Refresh the page to update the document list
                except requests.exceptions.RequestException as e:
                    st.error(f"Error deleting document: {e}")
                    st.error(f"Response content: {e.response.content}")
    else:
        st.info("No documents to delete.")

elif selected_action == "Upload Document":
    st.header("Upload a New Document")
    
    with st.form("upload_form", clear_on_submit=True):
        uploaded_file = st.file_uploader("Choose a file", type=['pdf', 'png', 'jpg', 'jpeg', 'docx', 'xlsx', 'xls', 'csv'])
        category = st.text_input("Category (optional)")
        tags = st.text_input("Tags (comma-separated, optional)")
        pdf_password = st.text_input("PDF Password (if applicable, optional)", type="password") # New: Password input
        
        submitted = st.form_submit_button("Upload")
        
        if submitted and uploaded_file is not None:
            files = {'file': (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            data = {'category': category, 'tags': tags.split(',')}
            if pdf_password: # Add password to data if provided
                data['password'] = pdf_password
            
            with st.spinner("Uploading and processing document..."):
                try:
                    response = requests.post(f"{BACKEND_URL}/upload/", files=files, data=data)
                    response.raise_for_status()
                    uploaded_document = response.json()
                    st.success("Document uploaded successfully!")
                    
                    # Store uploaded document and potential reminders in session state
                    st.session_state['last_uploaded_document'] = uploaded_document
                    st.session_state['potential_reminders_to_create'] = uploaded_document.get('potential_reminders', [])
                    st.rerun() # Rerun to display reminders outside the form
                except requests.exceptions.RequestException as e:
                    error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                    if "password-protected" in error_detail.lower() or "encrypted" in error_detail.lower():
                        st.error(f"Error: The PDF is password-protected or encrypted. Please provide the correct password.")
                    else:
                        st.error(f"Error uploading document: {error_detail}")
                    st.error(f"Response content: {e.response.content}")
    
    # Display potential reminders if any were found in the last upload
    if 'potential_reminders_to_create' in st.session_state and st.session_state['potential_reminders_to_create']:
        st.subheader("AI Suggested Reminders")
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
                            rem_response = requests.post(f"{BACKEND_URL}/reminders/", json=reminder_payload)
                            rem_response.raise_for_status()
                            st.success(f"Reminder '{reminder_data['message']}' created successfully!")
                        except requests.exceptions.RequestException as rem_e:
                            st.error(f"Error creating reminder '{reminder_data['message']}': {rem_e}")
                            st.error(f"Response content: {rem_e.response.content}")
                
                # Clear potential reminders from session state after creation attempt
                del st.session_state['last_uploaded_document']
                del st.session_state['potential_reminders_to_create']
                del st.session_state['currently_selected_reminders']
                st.rerun() # Refresh to show new reminders and clear the section
            else:
                st.warning("No reminders selected to create.")

elif selected_action == "Search Documents":
    st.header("Search Documents")
    
    search_query = st.text_input("Enter your search query")
    search_type = st.selectbox("Search Type", ["keyword", "semantic"])
    
    if st.button("Search"):
        if search_query:
            params = {'query': search_query, 'search_type': search_type}
            try:
                response = requests.get(f"{BACKEND_URL}/search/", params=params)
                response.raise_for_status()
                results = response.json()
                
                if results:
                    st.subheader("Search Results")
                    for result in results:
                        with st.expander(f"{result['filename']} (Category: {result.get('category', 'N/A')})"):
                            st.write(f"**Summary:** {result.get('summary', 'N/A')}")
                            st.write(f"**Upload Date:** {result['upload_date']}")
                            st.write(f"**Tags:** {', '.join(result.get('tags', []))}")
                            st.text_area("Extracted Text", result.get('extracted_text', ''), height=200)
                else:
                    st.info("No results found.")
            except requests.exceptions.RequestException as e:
                st.error(f"Error during search: {e}")

elif selected_action == "Document Q&A":
    st.header("Ask a Question About a Document")
    
    documents = get_documents() # Now get_documents returns already processed and valid documents
    if not documents:
        st.warning("Please upload a document first.")
    else:
        # Sort documents by upload_date for easier selection of recent ones
        documents.sort(key=lambda x: datetime.fromisoformat(x['upload_date']) if isinstance(x['upload_date'], str) else x['upload_date'], reverse=True)
        
        doc_options = {f"{doc['filename']} (Uploaded: {doc['upload_date']})": doc['_id'] for doc in documents}
        selected_doc_display = st.selectbox("Select a document to ask a question about", list(doc_options.keys()))
        
        # Extract the actual doc_id from the selected display string
        selected_doc_id = doc_options[selected_doc_display]
        
        question = st.text_input("Your Question")
        
        if st.button("Ask"):
            if selected_doc_display and question:
                doc_id = selected_doc_id # Use the extracted doc_id
                
                with st.spinner("Getting answer from the document..."):
                    try:
                        data = {'document_id': doc_id, 'question': question}
                        response = requests.post(f"{BACKEND_URL}/qa/", data=data)
                        response.raise_for_status()
                        answer = response.json().get('answer')
                        st.markdown("### Answer")
                        st.info(answer)
                    except requests.exceptions.RequestException as e:
                        st.error(f"Error getting answer: {e}")
                        st.error(f"Response content: {e.response.content}")

elif selected_action == "Manage Reminders":
    st.header("Manage Reminders")
    
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
            
            try:
                response = requests.post(f"{BACKEND_URL}/reminders/", json=reminder_data)
                response.raise_for_status()
                st.success("Reminder set successfully!")
            except requests.exceptions.RequestException as e:
                st.error(f"Error setting reminder: {e}")
                st.error(f"Response content: {e.response.content}")

    st.subheader("Upcoming Reminders")
    try:
        response = requests.get(f"{BACKEND_URL}/reminders/")
        response.raise_for_status()
        reminders = response.json()
        if reminders:
            df_reminders = pd.DataFrame(reminders)
            df_reminders['due_date'] = pd.to_datetime(df_reminders['due_date'])
            
            # Display reminders with actions
            for i, reminder in df_reminders.sort_values(by="due_date").iterrows():
                # Ensure _id is not None before proceeding
                if reminder.get('_id') is None:
                    st.warning(f"Skipping malformed reminder with missing ID: {reminder.get('message', 'Unknown')}")
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
                                response = requests.put(f"{BACKEND_URL}/reminders/{reminder['_id']}/status", json={"status": "done"})
                                response.raise_for_status()
                                st.success("Reminder marked as done!")
                                st.rerun()
                            except requests.exceptions.RequestException as e:
                                st.error(f"Error marking reminder as done: {e}")
                    else:
                        if st.button("Mark as Pending", key=f"mark_pending_{reminder['_id']}"):
                            try:
                                response = requests.put(f"{BACKEND_URL}/reminders/{reminder['_id']}/status", json={"status": "pending"})
                                response.raise_for_status()
                                st.success("Reminder marked as pending!")
                                st.rerun()
                            except requests.exceptions.RequestException as e:
                                st.error(f"Error marking reminder as pending: {e}")
                with col5:
                    if st.button("Delete", key=f"delete_rem_{reminder['_id']}"):
                        try:
                            response = requests.delete(f"{BACKEND_URL}/reminders/{reminder['_id']}")
                            response.raise_for_status()
                            st.success("Reminder deleted successfully!")
                            st.rerun()
                        except requests.exceptions.RequestException as e:
                            st.error(f"Error deleting reminder: {e}")
            
        else:
            st.info("No upcoming reminders.")
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching reminders: {e}")
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching reminders: {e}")

elif selected_action == "FAISS Management":
    st.header("FAISS Index Management")
    st.write("Manage the FAISS index for semantic search.")

    if st.button("Clear FAISS Index"):
        with st.spinner("Clearing FAISS index..."):
            try:
                response = requests.post(f"{BACKEND_URL}/faiss/clear")
                response.raise_for_status()
                st.success("FAISS index cleared successfully!")
                st.rerun()
            except requests.exceptions.RequestException as e:
                st.error(f"Error clearing FAISS index: {e}")
                st.error(f"Response content: {e.response.content}")

    if st.button("Rebuild FAISS Index"):
        with st.spinner("Rebuilding FAISS index from all documents..."):
            try:
                response = requests.post(f"{BACKEND_URL}/faiss/rebuild")
                response.raise_for_status()
                st.success("FAISS index rebuilt successfully!")
                st.rerun()
            except requests.exceptions.RequestException as e:
                st.error(f"Error rebuilding FAISS index: {e}")
                st.error(f"Response content: {e.response.content}")
