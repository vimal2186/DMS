import ollama
import json # Added for JSON parsing
from typing import List, Dict, Any # Added for type hints
from datetime import datetime # Added for date validation

OLLAMA_MODEL = 'mistral'

def get_embedding(text: str):
    """
    Generates embeddings for a given text using the Ollama model.
    """
    try:
        response = ollama.embeddings(model=OLLAMA_MODEL, prompt=text)
        return response["embedding"]
    except Exception as e:
        print(f"Error getting embedding from Ollama: {e}")
        return []

def get_summary_and_category(text: str):
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
    {text[:4000]} 
    ---
    """
    try:
        response = ollama.generate(model=OLLAMA_MODEL, prompt=prompt)
        
        # Parse the response
        content = response['response']
        category = "Uncategorized"
        summary = "Could not generate summary."

        lines = content.strip().split('\n')
        for line in lines:
            if line.lower().startswith('category:'):
                category = line.split(':', 1)[1].strip()
            elif line.lower().startswith('summary:'):
                summary = line.split(':', 1)[1].strip()
        
        return summary, category
    except Exception as e:
        print(f"Error getting summary from Ollama: {e}")
        return "Could not generate summary.", "Uncategorized"

def answer_question(full_prompt: str):
    """
    Generates an answer based on a comprehensive prompt that includes context and question.
    """
    try:
        response = ollama.generate(model=OLLAMA_MODEL, prompt=full_prompt)
        return response['response']
    except Exception as e:
        print(f"Error getting answer from Ollama: {e}")
        return "There was an error processing your question."

def extract_dates_for_reminders(text: str) -> List[Dict[str, Any]]:
    """
    Uses the LLM to identify potential due dates or renewal dates from document text
    and suggests reminder messages.
    """
    prompt = f"""
    Analyze the following document text for any mentions of due dates, renewal dates,
    or important deadlines related to bills, subscriptions, contracts, or other recurring events.
    For each identified date, suggest a concise reminder message.
    
    If no such dates are found, return an empty JSON array.
    
    Format your response as a JSON array of objects, where each object has:
    - "date": The identified date in YYYY-MM-DD format.
    - "message": A suggested reminder message (e.g., "Bill due", "Subscription renewal").

    Example:
    Document Text: "Your electricity bill of $120 is due on 2025-10-15. Renewal for your annual software license is on 2026-01-01."
    Response:
    [
      {{"date": "2025-10-15", "message": "Electricity bill due"}},
      {{"date": "2026-01-01", "message": "Software license renewal"}}
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
                # If it's a single object, wrap it in a list
                if isinstance(reminders_data, dict):
                    reminders_data = [reminders_data]
                else:
                    print(f"LLM response is neither a JSON list nor a JSON object: {content}")
                    return []

            valid_reminders = []
            for item in reminders_data:
                if isinstance(item, dict) and "date" in item and "message" in item:
                    try:
                        # Validate date format
                        datetime.strptime(item["date"], "%Y-%m-%d")
                        valid_reminders.append(item)
                    except ValueError:
                        print(f"Invalid date format in LLM response: {item['date']}")
            return valid_reminders
        except json.JSONDecodeError:
            print(f"LLM response is not valid JSON: {content}")
            return []

    except Exception as e:
        print(f"Error extracting dates for reminders from Ollama: {e}")
        return []
