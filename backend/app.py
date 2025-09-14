import os
import shutil
import logging
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, Form, Query, Body # Added Body
from fastapi.responses import JSONResponse
from typing import List, Optional
from datetime import datetime, date, time
from .database import get_document_collection, get_reminder_collection
from .models import Document, Reminder
from .ocr import extract_text
from .search import add_to_faiss_index, semantic_search, keyword_search, delete_from_faiss_index, clear_faiss_index, build_faiss_index
from .scheduler import start_scheduler
from .llm import get_summary_and_category, answer_question, extract_dates_for_reminders # Added extract_dates_for_reminders
from bson import ObjectId
from pymongo.collection import Collection
import json

# Create uploads and data directories if they don't exist
os.makedirs("uploads", exist_ok=True)
os.makedirs("data", exist_ok=True)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    start_scheduler()

@app.post("/upload/", response_model=Document)
async def upload_document(
    file: UploadFile = File(...),
    category: Optional[str] = Form(None),
    tags: Optional[List[str]] = Form(None, alias="tags[]"),
    password: Optional[str] = Form(None), # New: Optional password field
    doc_collection: Collection = Depends(get_document_collection)
):
    try:
        file_path = f"uploads/{file.filename}"
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        
        extracted_text = extract_text(file_path, file.content_type, password) # Pass password
        summary, inferred_category = get_summary_and_category(extracted_text)
        potential_reminders = extract_dates_for_reminders(extracted_text) # Extract potential reminders
        
        # Use the user-provided category if available, otherwise use the inferred one
        final_category = category if category else inferred_category

        document = Document(
            filename=file.filename,
            filepath=file_path,
            category=final_category,
            tags=tags if tags else [],
            extracted_text=extracted_text,
            summary=summary,
            potential_reminders=potential_reminders # Store potential reminders
        )

        # Insert into MongoDB
        document_dict = document.model_dump(by_alias=True)
        # Remove _id if it's None, so MongoDB can generate a new ObjectId
        if document_dict.get('_id') is None:
            document_dict.pop('_id')
            
        result = doc_collection.insert_one(document_dict)
        
        # Add to FAISS index
        # Use the generated _id from the insert result
        add_to_faiss_index(str(result.inserted_id), extracted_text)

        # Ensure the content is fully JSON-serializable before returning
        response_content = json_serializable_doc({**document_dict, "id": str(result.inserted_id)})
        return JSONResponse(
            content=response_content, 
            status_code=201
        )

    except ValueError as e: # Catch specific ValueError for password issues
        logger.error(f"Document processing error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading document: {e}")

@app.get("/documents/")
async def get_documents(doc_collection: Collection = Depends(get_document_collection)):
    documents = list(doc_collection.find({}))
    # Manually serialize the results to handle ObjectId and datetime
    serialized_docs = [json_serializable_doc(doc) for doc in documents]
    return JSONResponse(content=serialized_docs)

@app.get("/search/")
async def search_documents(
    query: str = Query(..., min_length=1),
    search_type: str = "keyword",
    doc_collection: Collection = Depends(get_document_collection)
):
    if search_type == "semantic":
        results = semantic_search(query)
    else: # Default to keyword search
        results = keyword_search(query)
        
    # Manually serialize the results to handle ObjectId and datetime
    serialized_results = [json_serializable_doc(doc) for doc in results]
    
    if not serialized_results:
        return JSONResponse(content=[], status_code=404) # Removed encoder argument
    
    return JSONResponse(content=serialized_results)

@app.delete("/documents/{document_id}")
async def delete_document(document_id: str, doc_collection: Collection = Depends(get_document_collection)):
    try:
        # Get the document to find its file path
        document = doc_collection.find_one({"_id": ObjectId(document_id)})
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Delete the document from the database
        result = doc_collection.delete_one({"_id": ObjectId(document_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Document not found or already deleted")
        
        # Delete the physical file
        file_path = document.get("filepath")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted physical file: {file_path}")
        else:
            logger.warning(f"Physical file not found for document {document_id}: {file_path}")
        
        # Delete from FAISS index mappings
        delete_from_faiss_index(document_id)
        
        return JSONResponse(content={"message": f"Document {document_id} deleted successfully"})
    
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error deleting document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting document: {e}")

@app.post("/faiss/clear")
async def clear_faiss_index_endpoint():
    """Clears the FAISS index."""
    clear_faiss_index()
    return JSONResponse(content={"message": "FAISS index cleared successfully."})

@app.post("/faiss/rebuild")
async def rebuild_faiss_index_endpoint():
    """Rebuilds the FAISS index from all documents in the database."""
    build_faiss_index()
    return JSONResponse(content={"message": "FAISS index rebuilt successfully."})

@app.post("/qa/")
async def question_answering(
    document_id: str = Form(...),
    question: str = Form(...),
    doc_collection: Collection = Depends(get_document_collection)
):
    document = doc_collection.find_one({"_id": ObjectId(document_id)})
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    context = document.get("extracted_text", "")
    if not context:
        raise HTTPException(status_code=400, detail="Document has no extracted text to perform Q&A")

    answer = answer_question(context, question)
    
    return JSONResponse(content={"answer": answer})

@app.post("/reminders/", response_model=Reminder)
async def create_reminder(
    document_id: str = Body(...),
    due_date: str = Body(...),
    message: str = Body(...),
    reminder_collection: Collection = Depends(get_reminder_collection)
):
    try:
        due_datetime = datetime.fromisoformat(due_date)
        reminder = Reminder(document_id=document_id, due_date=due_datetime, message=message, status="pending") # Set initial status
        
        # Insert into MongoDB
        reminder_dict = reminder.model_dump(by_alias=True)
        # Remove _id if it's None, so MongoDB can generate a new ObjectId
        if reminder_dict.get('_id') is None:
            reminder_dict.pop('_id')
            
        result = reminder_collection.insert_one(reminder_dict)
        
        # Ensure the content is fully JSON-serializable before returning
        response_content = json_serializable_doc({**reminder_dict, "id": str(result.inserted_id)})
        return JSONResponse(
            content=response_content, 
            status_code=201
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    except Exception as e:
        logger.error(f"Error creating reminder: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating reminder: {e}")

@app.get("/reminders/")
async def get_reminders(reminder_collection: Collection = Depends(get_reminder_collection)):
    reminders = []
    for rem in reminder_collection.find({}):
        # Ensure 'status' field is present, defaulting to 'pending' if not found (for old entries)
        if 'status' not in rem:
            rem['status'] = 'pending'
        reminders.append(rem)
    # Manually serialize the results to handle ObjectId and datetime
    serialized_reminders = [json_serializable_doc(rem) for rem in reminders]
    return JSONResponse(content=serialized_reminders)

@app.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str, reminder_collection: Collection = Depends(get_reminder_collection)):
    try:
        result = reminder_collection.delete_one({"_id": ObjectId(reminder_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Reminder not found")
        return JSONResponse(content={"message": f"Reminder {reminder_id} deleted successfully"})
    except Exception as e:
        logger.error(f"Error deleting reminder {reminder_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting reminder: {e}")

@app.put("/reminders/{reminder_id}/status")
async def update_reminder_status(
    reminder_id: str,
    status: str = Body(..., embed=True), # Expects {"status": "done"} or {"status": "pending"}
    reminder_collection: Collection = Depends(get_reminder_collection)
):
    if status not in ["pending", "done"]:
        raise HTTPException(status_code=400, detail="Status must be 'pending' or 'done'")
    
    try:
        result = reminder_collection.update_one(
            {"_id": ObjectId(reminder_id)},
            {"$set": {"status": status}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Reminder not found")
        return JSONResponse(content={"message": f"Reminder {reminder_id} status updated to {status}"})
    except Exception as e:
        logger.error(f"Error updating reminder {reminder_id} status: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating reminder status: {e}")
