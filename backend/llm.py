import ollama
import json
import re 
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import os # Added for environment variable access

OLLAMA_MODEL = os.getenv('OLLAMA_LLM_MODEL', 'mistral') # Main LLM for Q&A, summary, etc.
OLLAMA_EMBEDDING_MODEL = os.getenv('OLLAMA_EMBEDDING_MODEL', OLLAMA_MODEL) # Dedicated embedding model, falls back to main LLM model

logger = logging.getLogger(__name__)

# --- NEW SECTION: STRICT REGEX PATTERNS FOR POST-PROCESSING ---
# These patterns are designed to be highly specific to prevent false positives.
STRICT_REGEX_PATTERNS = {
    # Driving License: 2 Letters (State) + 2 Digits (RTO) + 7 to 11 digits
    "DL No.": r'([A-Z]{2}\d{2}[-.\s]?\d{7,11})\b', 
    
    # CRITICAL FIX: Enhanced Mobile Number Regex: 10 digits, preceded/followed by non-alphanumeric chars (to ensure standalone).
    # Allows for optional country code (+91) but focuses on the 10-digit sequence.
    "Mobile Number": r'\b(\+?\d{0,3}[-.\s]?\d{10})\b', 
    
    # Aadhar Number: 12 digits, often grouped 4-4-4
    "Aadhar Number": r'\b(\d{4}[-.\s]?\d{4}[-.\s]?\d{4})\b', 
    
    # PAN Number: 5 Letters + 4 Digits + 1 Letter
    "PAN Number": r'([A-Z]{5}\d{4}[A-Z]{1})\b',
    
    # Date (General): Matches DD/MM/YYYY, YYYY-MM-DD, etc.
    "Date": r'(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})|(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})' 
}
# --- END NEW SECTION ---


def get_embedding(text: str):
    """
    Generates embeddings for a given text using the configured Ollama embedding model.
    Falls back to the main LLM model if a dedicated embedding model is not specified.
    """
    try:
        # Use the dedicated embedding model if specified, otherwise fall back to the main LLM model
        model_to_use = OLLAMA_EMBEDDING_MODEL if OLLAMA_EMBEDDING_MODEL else OLLAMA_MODEL
        response = ollama.embeddings(model=model_to_use, prompt=text)
        if "embedding" in response:
            logger.debug(f"Successfully generated embedding of length {len(response['embedding'])} using model '{model_to_use}'.")
            return response["embedding"]
        else:
            logger.warning(f"Ollama embeddings response missing 'embedding' key for text: {text[:50]}... using model '{model_to_use}'.")
            return []
    except Exception as e:
        logger.error(f"Error getting embedding from Ollama for text: {text[:50]}... using model '{model_to_use}'. Error: {e}")
        return []

def get_summary_and_category(text: str) -> Dict[str, Optional[str]]:
    """
    Generates a summary and suggests a category for a document.
    """
    prompt = f"""
    Based on the following document text, provide a concise one-paragraph summary and suggest a single relevant category (e.g., 'Invoice', 'Receipt', 'Contract', 'Report', 'Personal').
    Format your response as:
    Category: [Your Suggested Category]
    Summary: [Your Summary]
    
    Document Text:
    ---
    {text[:6000]}
    ---
    """
    try:
        response = ollama.generate(model=OLLAMA_MODEL, prompt=prompt)
        content = response['response']
        
        category = next((line.split(': ', 1)[1].strip() for line in content.split('\n') if line.startswith('Category:')), "Uncategorized")
        summary = next((line.split(': ', 1)[1].strip() for line in content.split('\n') if line.startswith('Summary:')), "")
        
        return {"category": category, "summary": summary}

    except Exception as e:
        logger.error(f"Error getting summary and category from Ollama: {e}")
        return {"category": "Uncategorized", "summary": f"Error processing summary: {e}"}

# --- START CRITICAL FUNCTION ---
def extract_structured_info_with_correction(text: str) -> Dict[str, Any]:
    """
    Extracts structured information using the LLM and applies a regex-based
    correction and conflict resolution layer to improve accuracy for key fields.
    """
    extraction_fields = [
        "Name", "Date of Birth", "Gender", "Address", "Mobile Number", 
        "Aadhar Number", "PAN Number", "DL No.", "Passport No.", 
        "Document Type", "Issue Date", "Expiry Date", "Father/Spouse Name"
    ]
    
    fields_list = ", ".join(f"'{field}'" for field in extraction_fields)

    prompt = f"""
    You are an expert document parser. From the text below, extract the following fields into a single JSON object.
    
    Fields to extract: [{fields_list}].
    
    Rules:
    1. If a field is found, return the clean, extracted string value.
    2. If a field is NOT found, return the empty string: "". DO NOT return '[NOT_FOUND]' or '[INFERRED]'.
    3. The output MUST be a valid, single JSON object.
    
    Document Text:
    ---
    {text[:8000]}
    ---
    """

    # 1. LLM Extraction
    raw_llm_output = {}
    try:
        response = ollama.generate(model=OLLAMA_MODEL, prompt=prompt, format='json')
        content = response['response']
        raw_llm_output = json.loads(content)
        logger.info("LLM successfully extracted structured data.")
    except Exception as e:
        logger.error(f"LLM extraction failed (or returned invalid JSON). Error: {e}")
        # Initialize with empty strings if LLM fails
        raw_llm_output = {field: "" for field in extraction_fields}

    # 2. Regex-based Correction and Conflict Resolution
    corrected_output = raw_llm_output.copy()
    
    for field, pattern in STRICT_REGEX_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        
        if match:
            # Clean match: remove spaces, dashes, dots from the matched string
            regex_value_raw = match.group(1).strip()
            # CRITICAL FIX: Escape the hyphen in the character set to avoid "bad character range" error
            regex_value_clean = re.sub(r'[\s\-\.]', '', regex_value_raw) 
            llm_value_clean = re.sub(r'[\s\-\.]', '', corrected_output.get(field, ""))

            # Priority 1: Use regex if LLM failed (returned empty string)
            if not llm_value_clean:
                corrected_output[field] = regex_value_raw
                logger.info(f"Correction for {field}: LLM failed, using regex: {corrected_output[field]}")
            
            # Priority 2: Use regex to clean/normalize other key fields (Aadhar, PAN, DL) if found and they are similar
            elif field in ["Aadhar Number", "PAN Number", "DL No."]:
                 # Check if the clean values are exactly the same (normalization)
                if regex_value_clean == llm_value_clean:
                    # They match after cleaning, use the clean regex version for consistency
                    corrected_output[field] = regex_value_raw
                    logger.info(f"Correction for {field}: Normalizing/Cleaning LLM value to regex value: {corrected_output[field]}")
                else:
                    # They differ substantially, trust the regex over LLM for pattern-based IDs
                    corrected_output[field] = regex_value_raw
                    logger.warning(f"Correction for {field}: LLM value '{corrected_output[field]}' overruled by strict regex: {regex_value_raw}")
            
            # Priority 3: Mobile Number Specific Logic
            elif field == "Mobile Number":
                # Mobile number is highly pattern specific. Trust the strong regex.
                corrected_output[field] = regex_value_clean # Store only the clean 10-digit string
                logger.info(f"Correction for {field}: Using clean regex value: {corrected_output[field]}")


    # Ensure all original fields are present, using the corrected_output
    final_output = {field: corrected_output.get(field, "") for field in extraction_fields}
    return final_output

# --- END CRITICAL FUNCTION ---

def answer_question(question: str, document_context: str, chat_history: Optional[str] = None) -> str:
    """
    Answers a question based on the document context and chat history provided.
    """
    # NOTE: The original modification_file.md indicated custom regex for DL here.
    # The logic below is a standard RAG pattern.
    
    history_section = f"\n\nChat History:\n{chat_history}" if chat_history else None # Changed default to None
    
    # CRITICAL FIX: Only include history section if it has content (avoids adding empty chat history tag)
    history_prompt = history_section if history_section and history_section.strip() else ""

    prompt = f"""
    You are an expert document Q&A system. Answer the user's question ONLY using the provided document context and chat history. 
    Do not use external knowledge. If the answer is not present in the context, state: 'I could not find the answer in the document provided.'

    {history_prompt}

    Document Context:
    ---
    {document_context}
    ---

    Question: {question}
    """
    
    logger.info(f"Full Prompt for Q&A: {prompt[:500]}...")

    try:
        # Use a more powerful model for reasoning if available, default to Mistral
        response = ollama.generate(model=OLLAMA_MODEL, prompt=prompt, stream=False)
        llm_response = response['response'].strip()
        logger.info(f"LLM Q&A Response: {llm_response[:100]}...")
        return llm_response
    except Exception as e:
        logger.error(f"Error answering question from Ollama: {e}")
        return "An internal error occurred while trying to answer your question."

def extract_dates_for_reminders(text: str) -> List[Dict[str, str]]:
    """
    Extracts potential dates and associated messages for reminders.
    """
    prompt = f"""
    From the following document text, extract all potential future dates (e.g., due dates, expiry dates) and a short message (less than 15 words) describing the reason for the date.
    Ignore dates in the past. If no future dates are found, return an empty list.

    Format your response as a single JSON list of objects:
    [
        {{"date": "YYYY-MM-DD", "message": "Short description of the event"}},
        ...
    ]

    Document Text:
    ---
    {text[:6000]} 
    ---
    """
    try:
        response = ollama.generate(model=OLLAMA_MODEL, prompt=prompt, format='json')
        content = response['response']
        
        # Attempt to parse the JSON response
        try:
            reminders_data = json.loads(content)
            
            # Ensure reminders_data is a list
            if not isinstance(reminders_data, list):
                if isinstance(reminders_data, dict):
                    reminders_data = [reminders_data]
                else:
                    logger.warning(f"LLM response is neither a JSON list nor a JSON object: {content}")
                    return []

            valid_reminders = []
            for item in reminders_data:
                if isinstance(item, dict) and "date" in item and "message" in item:
                    try:
                        # Validate date format and ensure it is not in the distant past (e.g., allow today/future)
                        date_obj = datetime.strptime(item["date"], "%Y-%m-%d").date()
                        if date_obj >= datetime.now().date():
                             valid_reminders.append(item)
                        else:
                             logger.info(f"Ignoring past date in LLM response: {item['date']}")
                    except ValueError:
                        logger.warning(f"Invalid date format in LLM response: {item['date']}")
            return valid_reminders
        except json.JSONDecodeError:
            logger.warning(f"LLM response is not valid JSON: {content}")
            return []

    except Exception as e:
        logger.error(f"Error extracting dates for reminders from Ollama: {e}")
        return []
