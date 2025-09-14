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
