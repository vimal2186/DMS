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
        "Chat with AI"
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
                try:
                    response = requests.delete(f"{BACKEND_URL}/documents/{doc_id_to_delete}")
                    response.raise_for_status()
                    st.success(f"Document '{selected_doc_display}' deleted successfully!")
                    st.rerun() # Refresh the page to update the document list
                except requests.exceptions.RequestException as e:
                    st.error(f"Error deleting document: {e}")
                    st.error(f"Response content: {e.response.content}")
    else:
        st.info("No documents to delete.")

elif selected_action == "Upload Document":
    st.header("⬆️ Upload a New Document")
    st.write("Upload a document to be indexed and made searchable.")
    
    with st.form("upload_form", clear_on_submit=True):
        uploaded_file = st.file_uploader("Choose a file", type=['pdf', 'png', 'jpg', 'jpeg', 'docx', 'xlsx', 'xls', 'csv'])
        original_filepath = st.text_input("Original File Path (e.g., C:\\Users\\YourUser\\Documents\\file.pdf)", help="Enter the full path where this file is located on your computer. This path will be stored for your reference.")
        category = st.text_input("Category (optional)", help="Assign a category to your document for better organization.")
        tags = st.text_input("Tags (comma-separated, optional)", help="Add keywords to easily find your document later.")
        pdf_password = st.text_input("PDF Password (if applicable, optional)", type="password", help="If your PDF is password-protected, enter the password here.") # New: Password input
        
        submitted = st.form_submit_button("Upload Document")
        
        if submitted and uploaded_file is not None:
            files = {'file': (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            data = {'category': category, 'tags': tags.split(',')}
            if pdf_password: # Add password to data if provided
                data['password'] = pdf_password
            if original_filepath: # Add original_filepath to data if provided
                data['original_filepath'] = original_filepath
            
            with st.spinner("Uploading and processing document... This may take a moment."):
                try:
                    response = requests.post(f"{BACKEND_URL}/upload/", files=files, data=data)
                    response.raise_for_status()
                    uploaded_document = response.json()
                    st.success("Document uploaded successfully! The original file has been deleted from the 'uploads' folder.")
                    
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
    st.header("🔍 Search Documents")
    st.write("Find documents using keyword or semantic search.")
    
    search_query = st.text_input("Enter your search query")
    search_type = st.selectbox("Search Type", ["keyword", "semantic"])
    
    if st.button("Search"):
        if search_query:
            params = {'query': search_query, 'search_type': search_type}
            with st.spinner("Searching documents..."):
                try:
                    response = requests.get(f"{BACKEND_URL}/search/", params=params)
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
                                st.text_area("Extracted Text", result.get('extracted_text', ''), height=200)
                    else:
                        st.info("No results found for your query.")
                except requests.exceptions.RequestException as e:
                    st.error(f"Error during search: {e}")

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
                        response = requests.post(f"{BACKEND_URL}/qa/", data=data)
                        response.raise_for_status()
                        answer = response.json().get('answer')
                        st.markdown("### Answer")
                        st.info(answer)
                    except requests.exceptions.RequestException as e:
                        st.error(f"Error getting answer: {e}")
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
                    response = requests.post(f"{BACKEND_URL}/reminders/", json=reminder_data)
                    response.raise_for_status()
                    st.success("Reminder set successfully!")
                    st.rerun()
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
    st.header("⚙️ FAISS Index Management")
    st.write("Manage the FAISS index for semantic search. Rebuilding is recommended after significant data changes.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Clear FAISS Index", help="This will remove all documents from the semantic search index."):
            with st.spinner("Clearing FAISS index..."):
                try:
                    response = requests.post(f"{BACKEND_URL}/faiss/clear")
                    response.raise_for_status()
                    st.success("FAISS index cleared successfully!")
                    st.rerun()
                except requests.exceptions.RequestException as e:
                    st.error(f"Error clearing FAISS index: {e}")
                    st.error(f"Response content: {e.response.content}")
    with col2:
        if st.button("Rebuild FAISS Index", help="This will re-index all documents from the database for semantic search."):
            with st.spinner("Rebuilding FAISS index from all documents..."):
                try:
                    response = requests.post(f"{BACKEND_URL}/faiss/rebuild")
                    response.raise_for_status()
                    st.success("FAISS index rebuilt successfully!")
                    st.rerun()
                except requests.exceptions.RequestException as e:
                    st.error(f"Error rebuilding FAISS index: {e}")
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
                    response = requests.post(f"{BACKEND_URL}/backup/documents", json={"backup_path": backup_folder_path})
                    response.raise_for_status()
                    st.success(response.json().get("message", "Backup initiated successfully!"))
                except requests.exceptions.RequestException as e:
                    error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
                    st.error(f"Error during backup: {error_detail}")
                    st.error(f"Response content: {e.response.content}")
        else:
            st.warning("Please provide a backup folder path.")

elif selected_action == "Manage Uploaded Files":
    st.header("📁 Manage Uploaded Files")
    st.write("Here you can view and manually delete files that are currently in the 'uploads' directory. These are temporary files that were not automatically deleted or are awaiting processing.")

    try:
        response = requests.get(f"{BACKEND_URL}/files/uploaded")
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
                            delete_response = requests.delete(f"{BACKEND_URL}/files/uploaded/{filename}")
                            delete_response.raise_for_status()
                            st.success(f"File '{filename}' deleted successfully!")
                            st.rerun() # Refresh the page to update the list
                        except requests.exceptions.RequestException as e:
                            st.error(f"Error deleting file '{filename}': {e}")
                            st.error(f"Response content: {e.response.content}")
        else:
            st.info("No files found in the 'uploads' directory.")

    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching uploaded files: {e}")
        st.error(f"Response content: {e.response.content}")

elif selected_action == "Chat with AI":
    st.header("💬 Chat with AI")
    st.write("Engage in a conversation with the AI about your documents and other data.")

    # Initialize session state for current conversation if not present
    if 'current_conversation_id' not in st.session_state:
        st.session_state['current_conversation_id'] = None
    if 'current_conversation_title' not in st.session_state:
        st.session_state['current_conversation_title'] = "New Chat"

    # Sidebar for conversation selection
    st.sidebar.subheader("Your Conversations")
    
    # Fetch conversations
    conversations = []
    try:
        response = requests.get(f"{BACKEND_URL}/conversations/")
        response.raise_for_status()
        conversations = response.json()
    except requests.exceptions.RequestException as e:
        st.sidebar.error(f"Error fetching conversations: {e}")

    conversation_options = {"New Chat": None}
    if conversations:
        for conv in conversations:
            # Ensure _id is a string
            conv_id = conv.get('_id')
            if isinstance(conv_id, dict) and '$oid' in conv_id:
                conv_id = conv_id['$oid']
            elif not isinstance(conv_id, str):
                continue # Skip malformed conversation IDs

            conversation_options[f"{conv.get('title', 'Untitled')} (ID: {conv_id[:4]}...)"] = conv_id

    # Selectbox for conversations
    selected_conv_display = st.sidebar.selectbox(
        "Select or create a conversation",
        list(conversation_options.keys()),
        index=0 if st.session_state['current_conversation_id'] is None else 
              list(conversation_options.values()).index(st.session_state['current_conversation_id']) if st.session_state['current_conversation_id'] in list(conversation_options.values()) else 0
    )
    
    new_selected_conv_id = conversation_options[selected_conv_display]

    # Update current conversation if selection changes
    if new_selected_conv_id != st.session_state['current_conversation_id']:
        st.session_state['current_conversation_id'] = new_selected_conv_id
        st.session_state['current_conversation_title'] = selected_conv_display.split(' (ID:')[0] if new_selected_conv_id else "New Chat"
        st.rerun() # Rerun to load new conversation messages

    # Display current conversation title
    st.subheader(f"Conversation: {st.session_state['current_conversation_title']}")

    # Chat message display area
    chat_container = st.container(height=400, border=True)

    # Fetch and display messages for the current conversation
    messages = []
    if st.session_state['current_conversation_id']:
        try:
            response = requests.get(f"{BACKEND_URL}/conversations/{st.session_state['current_conversation_id']}/messages")
            response.raise_for_status()
            messages = response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Error fetching messages: {e}")
    
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
                    create_conv_response = requests.post(f"{BACKEND_URL}/conversations/", json={"title": "New Chat"})
                    create_conv_response.raise_for_status()
                    new_conv = create_conv_response.json()
                    conversation_id_to_use = new_conv['id']
                    st.session_state['current_conversation_id'] = conversation_id_to_use
                    st.session_state['current_conversation_title'] = new_conv['title']
                    st.success("New conversation created!")
                
                # Send message
                message_payload = {"message": user_input}
                response = requests.post(f"{BACKEND_URL}/conversations/{conversation_id_to_use}/messages", json=message_payload)
                response.raise_for_status()
                st.rerun() # Refresh to show new messages
            except requests.exceptions.RequestException as e:
                st.error(f"Error sending message: {e}")
                st.error(f"Response content: {e.response.content}")

    # Conversation management buttons
    if st.session_state['current_conversation_id']:
        st.markdown("---")
        st.subheader("Manage Current Conversation")
        col_del_conv, col_del_msg = st.columns(2)
        with col_del_conv:
            if st.button("Delete Current Conversation", help="This will delete the entire conversation history."):
                if st.session_state['current_conversation_id']:
                    try:
                        response = requests.delete(f"{BACKEND_URL}/conversations/{st.session_state['current_conversation_id']}")
                        response.raise_for_status()
                        st.success("Conversation deleted successfully!")
                        st.session_state['current_conversation_id'] = None
                        st.session_state['current_conversation_title'] = "New Chat"
                        st.rerun()
                    except requests.exceptions.RequestException as e:
                        st.error(f"Error deleting conversation: {e}")
                        st.error(f"Response content: {e.response.content}")
        with col_del_msg:
            if messages:
                message_to_delete_display = st.selectbox(
                    "Select a message to delete",
                    [f"{msg['sender']}: {msg['message'][:50]}..." for msg in messages],
                    key="delete_msg_select"
                )
                if st.button("Delete Selected Message"):
                    selected_msg_index = [f"{msg['sender']}: {msg['message'][:50]}..." for msg in messages].index(message_to_delete_display)
                    message_id_to_delete = messages[selected_msg_index]['_id']
                    try:
                        response = requests.delete(f"{BACKEND_URL}/messages/{message_id_to_delete}")
                        response.raise_for_status()
                        st.success("Message deleted successfully!")
                        st.rerun()
                    except requests.exceptions.RequestException as e:
                        st.error(f"Error deleting message: {e}")
                        st.error(f"Response content: {e.response.content}")
            else:
                st.info("No messages to delete in this conversation.")
