import os
import os
import shutil
import logging
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, Form, Query, Body, status
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, date, time, timedelta
from .database import get_document_collection, get_reminder_collection, get_chat_message_collection, get_conversation_collection, get_user_collection, get_person_collection, get_document_chunk_collection, get_document_feedback_collection, pwd_context
from .models import Document, Reminder, ChatMessage, Conversation, User, Person, DocumentFeedback, FeedbackType, PyObjectId # Import Person and DocumentFeedback models
from .ocr import extract_text
from .search import add_to_faiss_index, semantic_search, keyword_search, hybrid_search, delete_from_faiss_index, clear_faiss_index, build_faiss_index, ENABLE_CHUNKING # Added hybrid_search and ENABLE_CHUNKING
from .scheduler import start_scheduler
from .llm import get_summary_and_category, answer_question, extract_dates_for_reminders, extract_structured_info_with_correction
from bson import ObjectId
from pymongo.collection import Collection
from pymongo import ReadPreference
import json
import pytesseract
import subprocess
import re # Added for regex operations
from fuzzywuzzy import fuzz # For fuzzy matching names

# For authentication
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt

# Create uploads and data directories if they don't exist
os.makedirs("uploads", exist_ok=True)
os.makedirs("data", exist_ok=True)

# Configure logging
# Create a logger for the application
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create handlers
console_handler = logging.StreamHandler()
file_handler = logging.FileHandler('ocr_debug.log') # Using this for all app logs now

# Set levels for handlers
console_handler.setLevel(logging.INFO)
file_handler.setLevel(logging.INFO)

# Create formatters and add them to handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Prevent duplicate logs from the root logger if basicConfig was called elsewhere
logger.propagate = False

# JWT settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key") # TODO: Change this to a strong, random key in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Custom JSON serializer for a more robust fix
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)

def json_serializable_doc(doc):
    """Recursively converts BSON documents to JSON-serializable dictionaries."""
    if isinstance(doc, dict):
        return {k: json_serializable_doc(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [json_serializable_doc(v) for v in doc]
    elif isinstance(doc, ObjectId):
        return str(doc)
    elif isinstance(doc, datetime):
        return doc.isoformat()
    return doc

# Helper functions for authentication
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    users_collection: Collection = Depends(get_user_collection)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = users_collection.find_one({"username": username})
    if user is None:
        raise credentials_exception
    return User(**user)

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.trial_end_date < datetime.utcnow() and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Trial period has ended. Please contact support.")
    return current_user

async def get_current_admin_user(current_user: User = Depends(get_current_active_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin users can access this resource.")
    return current_user

app = FastAPI()

async def find_or_create_person(
    extracted_info: Dict[str, Any],
    person_collection: Collection = Depends(get_person_collection)
) -> PyObjectId:
    """
    Finds an existing person based on extracted PII or creates a new one.
    Prioritizes exact matches on unique identifiers (Aadhar, PAN, DL)
    and falls back to fuzzy matching on Name + DOB + Address.
    """
    logger.info(f"Attempting to find or create person for extracted info: {extracted_info}")

    # 1. Prioritize exact matches on unique identifiers
    query = {}
    if extracted_info.get("Aadhar Number"):
        query["aadhar_number"] = extracted_info["Aadhar Number"]
    if extracted_info.get("PAN Number"):
        query["pan_number"] = extracted_info["PAN Number"]
    if extracted_info.get("DL No."):
        query["dl_no"] = extracted_info["DL No."]
    if extracted_info.get("Passport No."):
        query["passport_no"] = extracted_info["Passport No."]
    if extracted_info.get("Mobile Number"):
        query["mobile_number"] = extracted_info["Mobile Number"]
    if extracted_info.get("Email"):
        query["email"] = extracted_info["Email"]

    if query:
        existing_person = person_collection.find_one(query)
        if existing_person:
            logger.info(f"Found existing person by unique identifier: {existing_person['_id']}")
            # Update existing person with any new info
            update_fields = {k: v for k, v in extracted_info.items() if k in Person.model_fields and v is not None}
            if update_fields:
                person_collection.update_one({"_id": existing_person['_id']}, {"$set": {**update_fields, "updated_at": datetime.utcnow()}})
                logger.info(f"Updated existing person {existing_person['_id']} with new details.")
            return existing_person['_id']

    # 2. Fallback to fuzzy matching on Name, DOB, Address if no unique identifier match
    name = extracted_info.get("Name")
    dob = extracted_info.get("Date of Birth")
    address = extracted_info.get("Address")

    if name and dob and address:
        # Find all persons to perform fuzzy matching
        all_persons = list(person_collection.find({}))
        
        best_match_person_id = None
        highest_score = 0
        
        for person_doc in all_persons:
            person = Person(**person_doc)
            
            # Combine fields for fuzzy matching
            person_combined = f"{person.name or ''} {person.date_of_birth or ''} {person.address or ''}".lower()
            extracted_combined = f"{name} {dob} {address}".lower()
            score = fuzz.token_set_ratio(person_combined, extracted_combined)
            
            if score > highest_score and score >= 80: # Threshold for a good fuzzy match
                highest_score = score
                best_match_person_id = person.id
        
        if best_match_person_id:
            logger.info(f"Found existing person by fuzzy matching (score: {highest_score}): {best_match_person_id}")
            # Update existing person with any new info
            update_fields = {k: v for k, v in extracted_info.items() if k in Person.model_fields and v is not None}
            if update_fields:
                person_collection.update_one({"_id": best_match_person_id}, {"$set": {**update_fields, "updated_at": datetime.utcnow()}})
                logger.info(f"Updated existing person {best_match_person_id} with new details via fuzzy match.")
            return best_match_person_id

    # 3. If no match, create a new person
    new_person_data = {k: v for k, v in extracted_info.items() if k in Person.model_fields and v is not None}
    if not new_person_data:
        # If no PII was extracted, don't create an empty person
        logger.warning("No PII extracted to create a new person.")
        return None
        
    new_person = Person(**new_person_data)
    new_person_dict = new_person.model_dump(by_alias=True, exclude_none=False) # Ensure _id: None is always present
    if '_id' in new_person_dict and new_person_dict['_id'] is None:
        new_person_dict.pop('_id')
        
    result = person_collection.insert_one(new_person_dict)
    logger.info(f"Created new person with ID: {result.inserted_id}")
    return result.inserted_id

@app.post("/upload/", tags=["documents"], status_code=status.HTTP_207_MULTI_STATUS) # Use 207 for partial success/failure
async def upload_document(
    files: List[UploadFile] = File(...),
    category: Optional[str] = Form(None),
    tags_string: Optional[str] = Form(None),
    pdf_password: Optional[str] = Form(None),
    original_filepaths: Optional[List[str]] = Form(None, alias="original_filepaths[]"), # Correctly receive list of paths
    documents_collection: Collection = Depends(get_document_collection),
    person_collection: Collection = Depends(get_person_collection),
    current_user: User = Depends(get_current_active_user)
):
    """
    Handles multiple document uploads, saves files, performs OCR, extracts metadata,
    and indexes documents for search. Returns a summary of each file's processing status.
    """
    logger.info(f"[{current_user.username}] Starting document upload process for {len(files)} files.")
    uploaded_documents_results = []
    
    # Ensure original_filepaths list matches the number of files, or is empty
    if original_filepaths is None:
        original_filepaths = [""] * len(files)
    elif len(original_filepaths) != len(files):
        logger.warning(f"[{current_user.username}] Mismatch between number of files ({len(files)}) and original_filepaths ({len(original_filepaths)}). Filling missing paths with empty strings.")
        # Pad or truncate original_filepaths to match files length
        original_filepaths = (original_filepaths + [""] * len(files))[:len(files)]

    for i, file in enumerate(files):
        logger.info(f"[{current_user.username}] Processing file {i+1}/{len(files)}: {file.filename}")
        file_result = {
            "filename": file.filename,
            "status": "pending",
            "detail": "Processing started."
        }
        file_path = None # Initialize file_path for cleanup
        
        try:
            file_extension = os.path.splitext(file.filename)[1].lower()
            if file_extension not in ['.pdf', '.jpg', '.jpeg', '.png', '.docx', '.xlsx', '.xls', '.csv']: # Added more supported types
                logger.error(f"[{current_user.username}] Unsupported file type for {file.filename}: {file_extension}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported file type: {file_extension}. Only PDF, JPG, PNG, DOCX, XLSX, XLS, CSV are supported."
                )
            
            unique_filename = f"{datetime.utcnow().timestamp()}_{file.filename}"
            file_path = os.path.join("uploads", unique_filename)

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            logger.info(f"[{current_user.username}] File saved to {file_path}")
            
            # Pass password to OCR if it's a PDF
            ocr_kwargs = {}
            if file_extension == '.pdf' and pdf_password:
                ocr_kwargs['password'] = pdf_password

            logger.info(f"[{current_user.username}] Calling extract_text for {file.filename} (MIME: {file.content_type})")
            extracted_text, ocr_error = extract_text(file_path, file.content_type, **ocr_kwargs)
            logger.info(f"[{current_user.username}] extract_text returned for {file.filename}. OCR Error: {ocr_error}")
            
            if ocr_error:
                logger.error(f"[{current_user.username}] OCR failed for {file.filename}: {ocr_error}")
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"OCR failed: {ocr_error}")
            
            if not extracted_text.strip():
                logger.warning(f"[{current_user.username}] No readable text extracted from {file.filename}.")
                # If OCR succeeded but returned empty text, it's still a processing failure for content extraction
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No readable text could be extracted from the document.")

            summary_and_category_response = get_summary_and_category(extracted_text)
            
            summary = ""
            llm_category = "Uncategorized"
            
            # --- CRITICAL FIX: Handle dict return type from LLM ---
            # The get_summary_and_category function returns a dict, so we must access keys.
            if isinstance(summary_and_category_response, dict):
                summary = summary_and_category_response.get("summary", "")
                llm_category = summary_and_category_response.get("category", "Uncategorized")
            else:
                # Log an error if the LLM function returns an unexpected type (e.g., a string due to an internal LLM error)
                logger.error(f"[{current_user.username}] get_summary_and_category returned unexpected type: {type(summary_and_category_response)}")
                # Use a default summary/category in case of an LLM failure
                summary = "LLM failed to generate summary/category."
                llm_category = "LLM_Error"
            
            final_category = category if category else llm_category
            # --- CRITICAL FIX END ---
            
            potential_reminders = extract_dates_for_reminders(extracted_text)

            # PII extraction logic
            extracted_info = extract_structured_info_with_correction(extracted_text)

            person_id = await find_or_create_person(extracted_info, person_collection)

            tags = [t.strip() for t in tags_string.split(',')] if tags_string else []
            
            document_data = {
                "user_id": str(current_user.id), # Link document to the current user
                "filename": file.filename,
                "filepath": file_path,
                "original_filepath": original_filepaths[i] if original_filepaths and original_filepaths[i] else None,
                "upload_date": datetime.utcnow(),
                "category": final_category,
                "tags": tags,
                "extracted_text": extracted_text,
                "summary": summary,
                "potential_reminders": potential_reminders,
                "extracted_info": extracted_info,
                "person_id": person_id,
            }
            
            new_document = Document(**document_data)
            document_dict = new_document.model_dump(by_alias=True, exclude_none=False)
            if '_id' in document_dict and document_dict['_id'] is None:
                document_dict.pop('_id')
                
            result = documents_collection.insert_one(document_dict)
            document_id = str(result.inserted_id)
            logger.info(f"[{current_user.username}] Document {document_id} inserted into MongoDB.")
            
            # Pass user_id to add_to_faiss_index for chunking logic
            add_to_faiss_index(document_id, str(current_user.id), extracted_text)
            logger.info(f"[{current_user.username}] Document {document_id} added to FAISS index.")
            
            inserted_document = documents_collection.find_one({"_id": result.inserted_id})
            
            file_result.update({
                "status": "success",
                "detail": "Document processed successfully.",
                "id": document_id,
                "filename": file.filename, # Ensure filename is present
                "extracted_text": extracted_text, # Include for frontend check
                "potential_reminders": potential_reminders # Include for frontend
            })
            uploaded_documents_results.append(json_serializable_doc(file_result))

            # Delete the temporary file after successful processing
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"[{current_user.username}] Successfully deleted temporary uploaded file: {file_path}")
                except Exception as cleanup_e:
                    logger.error(f"[{current_user.username}] Error deleting temporary file {file_path}: {cleanup_e}")

        except HTTPException as e:
            file_result.update({"status": "failed", "detail": e.detail})
            uploaded_documents_results.append(file_result)
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            logger.error(f"[{current_user.username}] HTTPException processing {file.filename}: {e.detail}")
        except Exception as e:
            file_result.update({"status": "failed", "detail": f"An internal error occurred: {e}"})
            uploaded_documents_results.append(file_result)
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            logger.error(f"[{current_user.username}] Error processing {file.filename}: {e}", exc_info=True)
            
    # Determine overall status code
    all_succeeded = all(res["status"] == "success" for res in uploaded_documents_results)
    if all_succeeded:
        logger.info(f"[{current_user.username}] All documents processed successfully.")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "All documents uploaded and processed successfully!", "uploaded_documents": uploaded_documents_results}
        )
    else:
        logger.warning(f"[{current_user.username}] Some documents failed to process.")
        return JSONResponse(
            status_code=status.HTTP_207_MULTI_STATUS,
            content={"message": "Some documents failed to upload/process. Check individual statuses.", "uploaded_documents": uploaded_documents_results}
        )

@app.on_event("startup")
async def startup_event():
    # Build FAISS index on startup if it doesn't exist or if documents were added/removed
    build_faiss_index()
    # Start the background reminder scheduler
    start_scheduler()
    # Ensure an admin user exists
    from .database import create_admin_user_if_not_exists
    create_admin_user_if_not_exists()
    logger.info("Application startup complete.")
# ------------------------------------
# AUTHENTICATION AND USER ROUTES
# ------------------------------------

@app.post("/token", tags=["auth"])
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    users_collection: Collection = Depends(get_user_collection)
):
    user_doc = users_collection.find_one({"username": form_data.username})
    if not user_doc or not verify_password(form_data.password, user_doc.get("password")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = User(**user_doc)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "username": user.username}

@app.post("/register", response_model=User, tags=["auth"])
async def register_user(
    user_data: User,
    users_collection: Collection = Depends(get_user_collection)
):
    if users_collection.find_one({"username": user_data.username}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    if users_collection.find_one({"email": user_data.email}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Hash the password
    user_data.password = pwd_context.hash(user_data.password)
    
    # Set trial dates
    trial_start = datetime.utcnow()
    trial_end = trial_start + timedelta(days=30)
    user_data.trial_start_date = trial_start
    user_data.trial_end_date = trial_end
    
    # Prepare for insertion (Pydantic model to dict)
    user_dict = user_data.model_dump(by_alias=True, exclude_none=False) # Ensure _id: None is always present
    if '_id' in user_dict and user_dict['_id'] is None:
        user_dict.pop('_id')
    
    # Insert into database
    result = users_collection.insert_one(user_dict)
    
    # Fetch the inserted document to return the full model with _id
    inserted_user_doc = users_collection.find_one({"_id": result.inserted_id})
    return User(**inserted_user_doc)

@app.get("/users/me", response_model=User, tags=["users"])
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user

# ------------------------------------
# DOCUMENT ROUTES
# ------------------------------------

@app.get("/documents/", tags=["documents"])
async def get_documents(
    documents_collection: Collection = Depends(get_document_collection),
    current_user: User = Depends(get_current_active_user) # Protected route
):
    # For now, fetching all documents. In a real application, you'd filter by user_id
    documents = list(documents_collection.find({}))
    return [json_serializable_doc(doc) for doc in documents]

@app.get("/documents/{document_id}", tags=["documents"])
async def get_document(
    document_id: str,
    documents_collection: Collection = Depends(get_document_collection),
    current_user: User = Depends(get_current_active_user)
):
    # Add check for document ID validity
    if not ObjectId.is_valid(document_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Document ID format")
        
    document = documents_collection.find_one({"_id": ObjectId(document_id)})
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    
    return json_serializable_doc(document)

@app.delete("/documents/{document_id}", tags=["documents"])
async def delete_document(
    document_id: str,
    documents_collection: Collection = Depends(get_document_collection),
    document_chunks_collection: Collection = Depends(get_document_chunk_collection), # Added for chunk cleanup
    current_user: User = Depends(get_current_active_user)
):
    if not ObjectId.is_valid(document_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Document ID format")
        
    # First, attempt to delete from FAISS index and associated chunks
    try:
        delete_from_faiss_index(document_id) # This now handles chunk deletion from DB if ENABLE_CHUNKING
    except Exception as e:
        logger.warning(f"Failed to delete document {document_id} from FAISS index/chunks: {e}")
        # Continue to delete from DB even if FAISS fails

    # Find the document to get the filepath for cleanup
    document = documents_collection.find_one({"_id": ObjectId(document_id)})
    
    # Delete from MongoDB
    result = documents_collection.delete_one({"_id": ObjectId(document_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        
    # Clean up the file on the server
    if document and document.get("filepath"):
        file_path = document["filepath"]
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Deleted file from disk: {file_path}")
            except Exception as e:
                logger.error(f"Error deleting file from disk {file_path}: {e}")
    
    return JSONResponse(content={"message": f"Document {document_id} deleted successfully"})

@app.post("/search/", tags=["search"])
async def document_search(
    query: str = Body(..., embed=True),
    search_type: str = Body(..., embed=True),
    documents_collection: Collection = Depends(get_document_collection),
    current_user: User = Depends(get_current_active_user)
):
    try:
        if search_type == "semantic":
            # semantic_search now returns full document dictionaries
            results = semantic_search(query)
        elif search_type == "keyword":
            # keyword_search also returns full document dictionaries
            results = keyword_search(query)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid search_type. Must be 'keyword' or 'semantic'.")
        
        return [json_serializable_doc(doc) for doc in results]
    except Exception as e:
        logger.error(f"Error in document search ({search_type}): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred during document search: {e}")

@app.post("/qa", tags=["search"])
async def question_answering(
    document_id: str = Body(..., embed=True),
    question: str = Body(..., embed=True),
    documents_collection: Collection = Depends(get_document_collection),
    current_user: User = Depends(get_current_active_user)
):
    logger.info(f"Received /qa request: document_id='{document_id}', question='{question}'")
    print(f"DEBUG: Received /qa request: document_id='{document_id}', question='{question}'") # For immediate console visibility

    if not ObjectId.is_valid(document_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Document ID format")
        
    document = documents_collection.find_one({"_id": ObjectId(document_id)})
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        
    extracted_text = document.get("extracted_text", "")
    if not extracted_text:
        return {"answer": "The document has no extracted text to answer the question."}

    try:
        # The answer_question in llm.py now accepts chat_history as optional, so this call is fine.
        answer = answer_question(question, extracted_text) 
        return {"answer": answer}
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error in question answering: {e}\n{error_trace}")
        print(f"CRITICAL BACKEND ERROR IN QA: {e}\n{error_trace}") # Print to console for immediate visibility
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred during question answering: {e}")

# ------------------------------------
# REMINDER ROUTES
# ------------------------------------

@app.get("/reminders/", response_model=List[Reminder], tags=["reminders"])
async def get_reminders(
    reminder_collection: Collection = Depends(get_reminder_collection),
    current_user: User = Depends(get_current_active_user)
):
    # Filter by user_id once implemented
    reminders = list(reminder_collection.find({}))
    return [Reminder(**doc) for doc in reminders]

@app.post("/reminders/", response_model=Reminder, tags=["reminders"])
async def create_reminder(
    reminder: Reminder,
    reminder_collection: Collection = Depends(get_reminder_collection),
    current_user: User = Depends(get_current_active_user)
):
    # Ensure the reminder is linked to the current user (if user_id is in the Reminder model)
    # reminder.user_id = str(current_user.id) # Uncomment if model is updated
    
    # Prepare for insertion
    reminder_dict = reminder.model_dump(by_alias=True, exclude_none=False) # Ensure _id: None is always present
    if '_id' in reminder_dict and reminder_dict['_id'] is None:
        reminder_dict.pop('_id')
    
    # Insert into database
    result = reminder_collection.insert_one(reminder_dict)
    
    # Fetch and return the inserted document
    inserted_reminder_doc = reminder_collection.find_one({"_id": result.inserted_id})
    return Reminder(**inserted_reminder_doc)

@app.delete("/reminders/{reminder_id}", tags=["reminders"])
async def delete_reminder(
    reminder_id: str,
    reminder_collection: Collection = Depends(get_reminder_collection),
    current_user: User = Depends(get_current_active_user)
):
    if not ObjectId.is_valid(reminder_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Reminder ID format")
        
    result = reminder_collection.delete_one({"_id": ObjectId(reminder_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")
        
    return JSONResponse(content={"message": f"Reminder {reminder_id} deleted successfully"})

# ------------------------------------
# CHAT/CONVERSATION ROUTES
# ------------------------------------

@app.get("/conversations/", response_model=List[Conversation], tags=["chat"])
async def get_conversations(
    conversation_collection: Collection = Depends(get_conversation_collection),
    current_user: User = Depends(get_current_active_user)
):
    # Filter by user_id
    conversations = list(conversation_collection.find({"user_id": str(current_user.id)}).sort("created_at", -1))
    return [Conversation(**doc) for doc in conversations]

@app.post("/conversations/", response_model=Conversation, tags=["chat"])
async def start_new_conversation(
    conversation_collection: Collection = Depends(get_conversation_collection),
    current_user: User = Depends(get_current_active_user)
):
    new_conversation = Conversation(
        user_id=str(current_user.id),
        title="New Chat"
    )
    
    conv_dict = new_conversation.model_dump(by_alias=True, exclude_none=False) # Ensure _id: None is always present
    # If _id is present and its value is None, remove it for MongoDB auto-generation
    if '_id' in conv_dict and conv_dict['_id'] is None:
        conv_dict.pop('_id')
        
    result = conversation_collection.insert_one(conv_dict)
    
    inserted_conv_doc = conversation_collection.find_one({"_id": result.inserted_id})
    return Conversation(**inserted_conv_doc)

@app.get("/conversations/{conversation_id}/messages", response_model=List[ChatMessage], tags=["chat"])
async def get_conversation_messages(
    conversation_id: str,
    chat_message_collection: Collection = Depends(get_chat_message_collection),
    conversation_collection: Collection = Depends(get_conversation_collection),
    current_user: User = Depends(get_current_active_user)
):
    if not ObjectId.is_valid(conversation_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Conversation ID format")
        
    # 1. Verify conversation ownership
    conversation_doc = conversation_collection.find_one(
        {"_id": ObjectId(conversation_id), "user_id": str(current_user.id)}
    )
    
    if not conversation_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found or not owned by user")
        
    # 2. Fetch messages, sorted by timestamp
    messages = list(chat_message_collection.find(
        {"conversation_id": ObjectId(conversation_id)}
    ).sort("timestamp", 1))
    
    # logger.info(f"MongoDB Find Query ObjectId: {ObjectId(conversation_id)}, Type: {type(ObjectId(conversation_id))}")
    
    return [ChatMessage(**doc) for doc in messages]


@app.post("/conversations/{conversation_id}/send", response_model=ChatMessage, tags=["chat"])
async def send_chat_message(
    conversation_id: str,
    message: str = Body(..., embed=True),
    chat_message_collection: Collection = Depends(get_chat_message_collection),
    conversation_collection: Collection = Depends(get_conversation_collection),
    current_user: User = Depends(get_current_active_user),
    documents_collection: Collection = Depends(get_document_collection)
):
    if not ObjectId.is_valid(conversation_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Conversation ID format")
        
    # 1. Verify conversation ownership
    conversation_doc = conversation_collection.find_one(
        {"_id": ObjectId(conversation_id), "user_id": str(current_user.id)}
    )
    
    if not conversation_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found or not owned by user")
        
    # --- Process User Message ---
    # Create user message
    user_chat_message = ChatMessage(
        conversation_id=ObjectId(conversation_id),
        sender="user",
        message=message
    )
    
    user_msg_dict = user_chat_message.model_dump(by_alias=True, exclude_none=False) # Ensure _id: None is always present
    # If _id is present and its value is None, remove it for MongoDB auto-generation
    if '_id' in user_msg_dict and user_msg_dict['_id'] is None:
        user_msg_dict.pop('_id')
    
    # Save user message
    result_user = chat_message_collection.insert_one(user_msg_dict)
    # logger.info(f"User Message Inserted ID: {result_user.inserted_id}, Type: {type(result_user.inserted_id)}")
    
    # 2. RAG/LLM Response Generation
    try:
        # a. Fetch history
        history_messages = list(chat_message_collection.find(
            {"conversation_id": ObjectId(conversation_id)}
        ).sort("timestamp", 1).limit(5)) # Limit to last 5 for context
        
        # Format history for LLM prompt
        chat_history = "\n".join([f"{msg['sender'].capitalize()}: {msg['message']}" for msg in history_messages])
        
        # b. Hybrid Search for context (RAG)
        # Use hybrid_search to get a more comprehensive set of relevant documents
        relevant_documents = hybrid_search(message, semantic_limit=3, keyword_limit=5) # Adjust limits as needed
        
        context_docs = []
        retrieved_doc_names = [] # To store names of documents used for context
        for i, doc in enumerate(relevant_documents):
            doc_content = doc.get('relevant_chunk_content', doc.get('extracted_text', '')) # Prioritize chunk content if available
            context_docs.append(f"--- Document {i+1}: {doc.get('filename', 'Untitled')} ---\n{doc_content[:1500]}...")
            retrieved_doc_names.append(doc.get('filename', 'Untitled'))
            
        context = "\n\n".join(context_docs)
        
        # c. Generate LLM Answer
        llm_response_text = answer_question(message, context, chat_history)

        # Append retrieved document names to the AI's response for transparency
        if retrieved_doc_names:
            unique_names = list(set(retrieved_doc_names))
            llm_response_text += f"\n\n*Information retrieved from: {', '.join(unique_names)}*"

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error generating LLM response for chat: {e}\n{error_trace}")
        print(f"CRITICAL BACKEND ERROR IN CHAT: {e}\n{error_trace}") # Print to console for immediate visibility
        llm_response_text = "Sorry, I encountered an error while processing your request. Please check the backend logs."

    # --- Process AI Message ---
    ai_chat_message = ChatMessage(
        conversation_id=ObjectId(conversation_id),
        sender="ai",
        message=llm_response_text
    )
    
    ai_msg_dict = ai_chat_message.model_dump(by_alias=True, exclude_none=False) # Ensure _id: None is always present
    # If _id is present and its value is None, remove it for MongoDB auto-generation
    if '_id' in ai_msg_dict and ai_msg_dict['_id'] is None:
        ai_msg_dict.pop('_id')
    
    # Save AI message
    result_ai = chat_message_collection.insert_one(ai_msg_dict)
    # logger.info(f"AI Message Inserted ID: {result_ai.inserted_id}, Type: {type(result_ai.inserted_id)}")

    # Update conversation title if it's "New Chat"
    if conversation_doc.get("title") == "New Chat":
        new_title = f"{message[:30]}..." if len(message) > 30 else message
        conversation_collection.update_one(
            {"_id": ObjectId(conversation_id)},
            {"$set": {"title": new_title}}
        )

    # Fetch and return the inserted AI message (the response)
    inserted_ai_msg_doc = chat_message_collection.find_one({"_id": result_ai.inserted_id})
    return ChatMessage(**inserted_ai_msg_doc)


@app.delete("/conversations/{conversation_id}", tags=["chat"])
async def delete_conversation(
    conversation_id: str,
    conversation_collection: Collection = Depends(get_conversation_collection),
    chat_message_collection: Collection = Depends(get_chat_message_collection),
    current_user: User = Depends(get_current_active_user)
):
    if not ObjectId.is_valid(conversation_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Conversation ID format")

    # 1. Verify conversation ownership and delete the conversation document
    result_conv = conversation_collection.delete_one(
        {"_id": ObjectId(conversation_id), "user_id": str(current_user.id)}
    )
    
    if result_conv.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found or not owned by user")
        
    # 2. Delete all associated messages
    result_msg = chat_message_collection.delete_many(
        {"conversation_id": ObjectId(conversation_id)}
    )

    return JSONResponse(content={"message": f"Conversation {conversation_id} and {result_msg.deleted_count} messages deleted successfully"})

@app.delete("/messages/{message_id}", tags=["chat"])
async def delete_chat_message(
    message_id: str,
    chat_message_collection: Collection = Depends(get_chat_message_collection),
    conversation_collection: Collection = Depends(get_conversation_collection),
    current_user: User = Depends(get_current_active_user) # Used to verify message ownership via conversation
):
    try:
        # Find the message to get its conversation_id
        message_to_delete = chat_message_collection.find_one({"_id": ObjectId(message_id)})
        if not message_to_delete:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat message not found")
        
        conversation_id = message_to_delete.get("conversation_id")
        if not conversation_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Message has no associated conversation ID")

        # Verify conversation ownership
        conversation = conversation_collection.find_one({"_id": ObjectId(conversation_id), "user_id": str(current_user.id)})
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found or not owned by user")

        result = chat_message_collection.delete_one({"_id": ObjectId(message_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat message not found")
        return JSONResponse(content={"message": f"Chat message {message_id} deleted successfully"})
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error deleting chat message {message_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error deleting chat message: {e}")

# ------------------------------------
# ADMIN FEEDBACK ROUTES
# ------------------------------------

@app.get("/admin/feedback/", response_model=List[DocumentFeedback], tags=["admin"])
async def get_all_document_feedback(
    feedback_collection: Collection = Depends(get_document_feedback_collection),
    current_user: User = Depends(get_current_admin_user) # Only admins can access
):
    """
    Retrieves all document feedback entries.
    """
    feedback_entries = list(feedback_collection.find({}).sort("created_at", -1))
    return [DocumentFeedback(**json_serializable_doc(entry)) for entry in feedback_entries]

@app.post("/admin/feedback/", response_model=DocumentFeedback, tags=["admin"])
async def submit_document_feedback(
    feedback: DocumentFeedback,
    feedback_collection: Collection = Depends(get_document_feedback_collection),
    current_user: User = Depends(get_current_admin_user) # Only admins can submit
):
    """
    Submits new feedback for a document.
    """
    feedback.user_id = str(current_user.id) # Ensure feedback is linked to the admin user
    feedback_dict = feedback.model_dump(by_alias=True, exclude_none=False)
    if '_id' in feedback_dict and feedback_dict['_id'] is None:
        feedback_dict.pop('_id')
    
    result = feedback_collection.insert_one(feedback_dict)
    inserted_feedback = feedback_collection.find_one({"_id": result.inserted_id})
    return DocumentFeedback(**json_serializable_doc(inserted_feedback))

@app.put("/admin/feedback/{feedback_id}", response_model=DocumentFeedback, tags=["admin"])
async def update_document_feedback(
    feedback_id: str,
    feedback_update: DocumentFeedback, # Use the full model for updates
    feedback_collection: Collection = Depends(get_document_feedback_collection),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Updates an existing document feedback entry.
    """
    if not ObjectId.is_valid(feedback_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Feedback ID format")

    # Ensure the user_id in the update matches the current admin user
    feedback_update.user_id = str(current_user.id)
    update_data = feedback_update.model_dump(by_alias=True, exclude_none=True)
    update_data.pop("id", None) # Remove id from update data

    result = feedback_collection.update_one(
        {"_id": ObjectId(feedback_id)},
        {"$set": {**update_data, "created_at": datetime.utcnow()}} # Update timestamp on modification
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback entry not found or no changes made")
    
    updated_feedback = feedback_collection.find_one({"_id": ObjectId(feedback_id)})
    return DocumentFeedback(**json_serializable_doc(updated_feedback))

@app.delete("/admin/feedback/{feedback_id}", tags=["admin"])
async def delete_document_feedback(
    feedback_id: str,
    feedback_collection: Collection = Depends(get_document_feedback_collection),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Deletes a document feedback entry.
    """
    if not ObjectId.is_valid(feedback_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Feedback ID format")
        
    result = feedback_collection.delete_one({"_id": ObjectId(feedback_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback entry not found")
        
    return JSONResponse(content={"message": f"Feedback entry {feedback_id} deleted successfully"})

# ------------------------------------
# FAISS Management Routes
# ------------------------------------

@app.post("/faiss/rebuild", tags=["faiss"])
async def rebuild_faiss_index_endpoint(
    current_user: User = Depends(get_current_active_user)
):
    """
    Rebuilds the FAISS index from all documents in the database.
    This can be useful if the index becomes corrupted or out of sync.
    """
    logger.info("Received request to rebuild FAISS index.")
    try:
        build_faiss_index()
        logger.info("FAISS index rebuilt successfully.")
        return JSONResponse(content={"message": "FAISS index rebuilt successfully."})
    except Exception as e:
        logger.error(f"Failed to rebuild FAISS index: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to rebuild FAISS index: {e}")

# ------------------------------------
# File Management Routes (for 'uploads' directory)
# ------------------------------------

@app.get("/files/uploaded", tags=["file-management"])
async def list_uploaded_files(
    current_user: User = Depends(get_current_active_user)
):
    """
    Lists all files currently present in the 'uploads' directory.
    """
    try:
        uploaded_files = []
        for filename in os.listdir("uploads"):
            file_path = os.path.join("uploads", filename)
            if os.path.isfile(file_path):
                uploaded_files.append({
                    "filename": filename,
                    "size_bytes": os.path.getsize(file_path),
                    "last_modified": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
                })
        return uploaded_files
    except Exception as e:
        logger.error(f"Error listing uploaded files: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error listing uploaded files: {e}")

@app.delete("/files/uploaded/{filename}", tags=["file-management"])
async def delete_uploaded_file(
    filename: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    Deletes a specific file from the 'uploads' directory.
    """
    file_path = os.path.join("uploads", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found in uploads directory.")
    
    try:
        os.remove(file_path)
        logger.info(f"Manually deleted file from uploads: {file_path}")
        return JSONResponse(content={"message": f"File '{filename}' deleted successfully from uploads."})
    except Exception as e:
        logger.error(f"Error deleting file '{filename}' from uploads: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error deleting file: {e}")
