# Document Management System (DMS)

This is a lightweight, local Document Management System (DMS) built with Python. It allows you to upload, store, process, and search PDF and image documents.

## Features

- **File Upload & Storage**: Upload and store PDF and image files (JPEG, PNG).
- **Metadata Storage**: Stores filename, upload date, and category for each document.
- **OCR & Text Extraction**: Uses Tesseract to extract text from documents, making them searchable.
- **Full-Text Search**: Search through documents by filename, tags, or extracted text content.
- **Semantic Search**: Utilizes FAISS for vector-based semantic search.
- **Reminders & Alerts**: Set reminders for important documents (e.g., bill due dates).
- **Web Interface**: A simple and clean web UI built with Streamlit.

## Tech Stack

- **Backend**: FastAPI
- **Frontend**: Streamlit
- **Database**: SQLite
- **OCR**: Tesseract, pdfplumber, opencv-python
- **Search**: FAISS (for semantic search), SQLite FTS (for keyword search)
- **Notifications**: Plyer (for local desktop notifications)
- **Scheduler**: Schedule

## Project Structure

```
DMS/
│   requirements.txt
│   README.md
│
├── backend
│   ├── app.py
│   ├── database.py
│   ├── models.py
│   ├── ocr.py
│   ├── search.py
│   └── scheduler.py
│
├── frontend
│   └── app.py
│
├── uploads/
└── data/
```

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd DMS
    ```

2.  **Create a virtual environment and activate it:**
    ```bash
    python -m venv venv
    # On Windows
    venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *Note: You may also need to install Tesseract OCR engine on your system. Follow the instructions for your OS.*

***Note on Docker:** The Docker setup is currently not maintained. Please follow the local setup instructions above.*

## How to Run

1.  **Start the Backend Server:**
    Open a terminal and run the following command from the `DMS` directory:
    ```bash
    uvicorn backend.app:app --reload
    ```
    The backend will be running at `http://127.0.0.1:8000`.

2.  **Start the Frontend Application:**
    Open a second terminal and run the following command from the `DMS` directory:
    ```bash
    streamlit run frontend/app.py
    ```
    The frontend will be accessible in your browser, usually at `http://localhost:8501`.

---

## Recent Updates (October 2025)

This section outlines the significant enhancements recently implemented to improve the AI capabilities and introduce admin-level document training features.

### 1. Enhanced Retrieval Augmented Generation (RAG) Pipeline

The "Chat with AI" feature has been significantly improved with several RAG enhancements and fallback mechanisms:

*   **Configurable LLM and Embedding Models**:
    *   Introduced environment variables (`OLLAMA_LLM_MODEL`, `OLLAMA_EMBEDDING_MODEL`) for flexible configuration of Large Language Models (LLMs) and embedding models, primarily using Ollama (e.g., Mistral).
*   **Document Chunking for Granular Retrieval**:
    *   Implemented a `DocumentChunk` model and updated FAISS indexing to support more granular document retrieval.
    *   The `chunk_text` function in `backend/search.py` now breaks documents into smaller, more manageable chunks for better context.
*   **Hybrid Search Re-ranking**:
    *   Added `ENABLE_RERANKING` environment variable to enable hybrid search with re-ranking.
    *   The `re_rank_documents` function enhances search relevance by combining semantic and keyword search results.
*   **Improved OCR Quality with Image Pre-processing**:
    *   Introduced `ENABLE_OCR_PREPROCESSING` to enable image pre-processing before OCR.
    *   The `preprocess_image_for_ocr` function in `backend/ocr.py` improves the accuracy of text extraction from images.
*   **Frontend Transparency**:
    *   AI responses in the chat now append the names of the retrieved documents used for context, providing transparency to the user.
*   **Backend Stability**:
    *   Fixed a `NameError` in `backend/app.py` related to `get_document_chunk_collection`, ensuring stable backend operation.

### 2. Admin Document Feedback System (Human-in-the-Loop Training)

New admin-level features have been implemented to allow human feedback for document training, aiming to continuously improve AI performance.

*   **Data Models for Feedback**:
    *   A `FeedbackType` enum and a `DocumentFeedback` Pydantic model were added in `backend/models.py` to categorize and store various types of feedback, including:
        *   `OCR_CORRECTION`: For correcting errors in extracted text.
        *   `SUMMARY_ADJUSTMENT`: For refining AI-generated document summaries.
        *   `CATEGORY_ADJUSTMENT`: For correcting AI-assigned document categories.
        *   `TAG_ADJUSTMENT`: For modifying AI-generated document tags.
        *   `PII_VALIDATION`: For validating or correcting Personally Identifiable Information (PII) extraction.
        *   `QA_CORRECTION`: For improving the quality of AI-generated answers to questions.
        *   `OTHER`: For general feedback.
*   **Backend Endpoints for Admin Review**:
    *   `backend/database.py` was updated to include a new collection for `document_feedback`.
    *   `backend/app.py` now includes an `get_current_admin_user` dependency to secure admin-only routes.
    *   New FastAPI endpoints were added in `backend/app.py` for:
        *   `GET /admin/feedback/`: Retrieve all document feedback entries.
        *   `POST /admin/feedback/`: Submit new feedback for a document.
        *   `PUT /admin/feedback/{feedback_id}`: Update an existing feedback entry.
        *   `DELETE /admin/feedback/{feedback_id}`: Delete a feedback entry.
*   **Frontend UI for Admin Interaction**:
    *   A new "Admin Feedback" section has been added to the Streamlit frontend (`frontend/app.py`).
    *   Admins can now view a list of all submitted feedback, submit new feedback for specific documents, and edit or delete existing feedback entries through a user-friendly interface.

### How Feedback Improves AI Models:

The collected human feedback is crucial for the continuous improvement of the AI components:

*   **OCR Corrections**: Used as ground truth to fine-tune or retrain OCR models, especially for domain-specific documents.
*   **Summary/Category/Tag Adjustments**: Utilized for fine-tuning LLMs to improve document understanding and metadata extraction.
*   **PII Extraction Validation**: Helps refine PII extraction prompts and can be used to train dedicated Named Entity Recognition (NER) models.
*   **Q&A Answer Quality**: Provides insights to refine the RAG system, including document chunking, embedding quality, retrieval relevance, and LLM answer generation.
*   **General Improvements**: The feedback data serves as a valuable dataset for monitoring AI performance, identifying areas of underperformance, and enabling active learning strategies.
