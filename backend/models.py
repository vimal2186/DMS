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

PyObjectId = Annotated[ObjectId, BeforeValidator(validate_object_id)]

class Document(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    filename: str
    filepath: str
    original_filepath: Optional[str] = None # New field to store the original path on the user's system
    upload_date: datetime = Field(default_factory=datetime.utcnow)
    category: Optional[str] = "Uncategorized"
    tags: Optional[List[str]] = []
    extracted_text: Optional[str] = ""
    summary: Optional[str] = ""
    potential_reminders: Optional[List[Dict[str, Any]]] = [] # New field for AI-suggested reminders
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }
        populate_by_name = True # Allow population by field name or alias

class Reminder(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    document_id: str
    due_date: datetime
    message: str
    status: str = "pending" # New field: "pending" or "done"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }
        populate_by_name = True # Allow population by field name or alias

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

class Conversation(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    user_id: Optional[str] = None # To link conversations to users if authentication is implemented
    title: str = "New Chat"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }
        populate_by_name = True
