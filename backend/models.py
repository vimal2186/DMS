from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer
from typing import Optional, List, Dict, Any, Annotated
from datetime import datetime
from bson import ObjectId

# Custom ObjectId type for Pydantic
def validate_object_id(v: Any) -> ObjectId:
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str) and ObjectId.is_valid(v):
        return ObjectId(v)
    raise ValueError("Invalid ObjectId")

# Annotated type for Pydantic/MongoDB ObjectId handling
PyObjectId = Annotated[
    ObjectId, 
    BeforeValidator(validate_object_id)
]

# --- CORE DATA MODELS ---

class Document(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    user_id: str # CRITICAL: Link document to user for security/ownership
    filename: str
    filepath: str
    original_filepath: Optional[str] = None
    upload_date: datetime = Field(default_factory=datetime.utcnow)
    category: Optional[str] = "Uncategorized"
    tags: Optional[List[str]] = []
    extracted_text: Optional[str] = ""
    summary: Optional[str] = ""
    potential_reminders: Optional[List[Dict[str, Any]]] = []
    extracted_info: Optional[Dict[str, Any]] = {} # Structured data from LLM
    person_id: Optional[PyObjectId] = None # Link to a Person profile
    faiss_id: Optional[int] = None # New field to store FAISS index ID

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }
        populate_by_name = True

class DocumentChunk(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    document_id: PyObjectId # Link to the parent document
    user_id: str # Link to the user who owns the document
    chunk_index: int # Order of the chunk within the document
    content: str # The text content of the chunk
    embedding: List[float] # The embedding vector for this chunk
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }
        populate_by_name = True

from enum import Enum

class FeedbackType(str, Enum):
    OCR_CORRECTION = "ocr_correction"
    SUMMARY_ADJUSTMENT = "summary_adjustment"
    CATEGORY_ADJUSTMENT = "category_adjustment"
    TAG_ADJUSTMENT = "tag_adjustment"
    PII_VALIDATION = "pii_validation"
    QA_CORRECTION = "qa_correction"
    OTHER = "other"

class DocumentFeedback(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    document_id: PyObjectId
    user_id: str # Admin user who provided feedback
    feedback_type: FeedbackType
    original_content: Optional[str] = None # Original text/value
    corrected_content: Optional[str] = None # Corrected text/value
    field_name: Optional[str] = None # e.g., "extracted_text", "summary", "category", "tags", "extracted_info.name"
    chunk_id: Optional[PyObjectId] = None # If feedback is chunk-specific
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }
        populate_by_name = True

# --- NEW MODEL: For linking documents to extracted personal data ---
class Person(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    user_id: str = Field(..., description="The ID of the user who owns this person's data.") # CRITICAL: Ownership
    name: str
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    mobile_number: Optional[str] = None
    
    # Extracted ID numbers for reliable lookups
    dl_no: Optional[str] = None 
    aadhar_number: Optional[str] = None
    pan_number: Optional[str] = None
    passport_no: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }
        populate_by_name = True

class Reminder(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    user_id: str # Link reminder to user
    document_id: PyObjectId # Link reminder to a specific document
    message: str
    due_date: datetime
    is_completed: bool = False

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }
        populate_by_name = True 

class ChatMessage(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    conversation_id: PyObjectId
    sender: str # 'user' or 'ai'
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }
        populate_by_name = True

class User(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    username: str
    password: str # This should be a hashed password
    email: str
    trial_start_date: datetime = Field(default_factory=datetime.utcnow)
    trial_end_date: datetime
    is_admin: bool = False

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }
        populate_by_name = True

class Conversation(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    user_id: Optional[str] = None 
    title: str = "New Chat"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }
        populate_by_name = True
