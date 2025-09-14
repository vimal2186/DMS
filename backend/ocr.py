import pytesseract
import cv2
import pdfplumber
import docx
import pandas as pd
from PIL import Image
import fitz # PyMuPDF
import io
import numpy as np
import os

def extract_text_from_image(file_path: str) -> str:
    """Extracts text from an image file."""
    try:
        image = cv2.imread(file_path)
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        text = pytesseract.image_to_string(gray_image)
        return text
    except Exception as e:
        print(f"Error extracting text from image {file_path}: {e}")
        return ""

def extract_text_from_pdf(file_path: str, password: str = None) -> str:
    """
    Extracts text from a PDF file, attempting both text-based and image-based (OCR) extraction.
    Handles password-protected PDFs.
    """
    text = ""
    try:
        print(f"Attempting text-based extraction for {file_path}...")
        # Attempt text-based extraction first
        try:
            with pdfplumber.open(file_path, password=password) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_text = page.extract_text() or ""
                    text += page_text
                    print(f"  Page {page_num + 1} (text-based): {len(page_text.strip())} characters.")
            print(f"Total text-based extraction yielded {len(text.strip())} characters.")
        except Exception as e:
            if "password" in str(e).lower() or "encrypted" in str(e).lower():
                raise ValueError("PDF is password-protected or encrypted.")
            print(f"Error during text-based extraction with pdfplumber for {file_path}: {e}")
            text = "" # Reset text if extraction fails
        
        # If text-based extraction yields little or no text, try OCR
        if len(text.strip()) < 50: # Threshold for "little text"
            print(f"Low text density from pdfplumber for {file_path}, attempting OCR...")
            ocr_text = ""
            try:
                doc = fitz.open(file_path)
                if doc.is_encrypted:
                    if not doc.authenticate(password):
                        raise ValueError("PDF is password-protected or encrypted.")
                print(f"  Opened PDF with PyMuPDF. Page count: {doc.page_count}")
                for page_num in range(doc.page_count):
                    page = doc.load_page(page_num)
                    print(f"  Processing page {page_num + 1} for OCR...")
                    
                    # Render page to image with higher resolution (e.g., 300 DPI)
                    pix = page.get_pixmap(dpi=300) 
                    img_bytes = pix.tobytes("png")
                    img = Image.open(io.BytesIO(img_bytes))
                    print(f"    Page {page_num + 1} rendered to image.")
                    
                    # Convert PIL Image to OpenCV format for pre-processing
                    cv_img = np.array(img)
                    cv_img = cv2.cvtColor(cv_img, cv2.COLOR_RGB2BGR)
                    print(f"    Page {page_num + 1} converted to OpenCV format.")
                    
                    # Optional: Noise reduction (Non-local Means Denoising)
                    denoised_img = cv2.fastNlMeansDenoisingColored(cv_img, None, 10, 10, 7, 21)
                    print(f"    Page {page_num + 1} denoised.")
                    
                    # Convert to grayscale for binarization
                    gray_img = cv2.cvtColor(denoised_img, cv2.COLOR_BGR2GRAY)
                    
                    # Image pre-processing for better OCR (adaptive binarization)
                    binarized_img = cv2.adaptiveThreshold(gray_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
                    print(f"    Page {page_num + 1} binarized.")
                    
                    tesseract_config = r'--oem 3 --psm 11' # OEM 3 is default, PSM 11 for sparse text
                    page_ocr_text = pytesseract.image_to_string(binarized_img, lang='eng+kan+hin', config=tesseract_config)
                    
                    ocr_text += page_ocr_text + "\n"
                    print(f"    OCR for page {page_num + 1} of {file_path}: {len(page_ocr_text.strip())} characters found. Raw OCR: '{page_ocr_text.strip()[:100]}...'")

                doc.close()
                
                if ocr_text.strip():
                    text = ocr_text # Use OCR text if successful
                    print(f"OCR successfully extracted {len(ocr_text.strip())} characters from {file_path}.")
                else:
                    print(f"OCR also yielded no text for {file_path}.")
            except ValueError as ve:
                raise ve # Re-raise the ValueError for password issues
            except Exception as e:
                print(f"Error during OCR processing for {file_path}: {e}")
                ocr_text = "" # Reset ocr_text if OCR fails
                
    except ValueError as ve:
        raise ve # Re-raise the ValueError for password issues
    except Exception as e:
        print(f"General error extracting text from PDF {file_path}: {e}")
    return text

def extract_text_from_docx(file_path: str) -> str:
    """Extracts text from a DOCX file."""
    text = ""
    try:
        doc = docx.Document(file_path)
        for para in doc.paragraphs:
            text += para.text + "\n"
    except Exception as e:
        print(f"Error extracting text from DOCX {file_path}: {e}")
    return text

def extract_text_from_excel(file_path: str) -> str:
    """Extracts text from an Excel (XLSX, XLS) file."""
    text = ""
    try:
        df = pd.read_excel(file_path, sheet_name=None)
        for sheet_name, sheet_df in df.items():
            text += f"--- Sheet: {sheet_name} ---\n"
            text += sheet_df.to_string() + "\n\n"
    except Exception as e:
        print(f"Error extracting text from Excel file {file_path}: {e}")
    return text

def extract_text_from_csv(file_path: str) -> str:
    """Extracts text from a CSV file."""
    text = ""
    try:
        df = pd.read_csv(file_path)
        text = df.to_string()
    except Exception as e:
        print(f"Error extracting text from CSV file {file_path}: {e}")
    return text

def extract_text(file_path: str, mime_type: str, password: str = None) -> str:
    """Extracts text from a file based on its MIME type."""
    if mime_type.startswith('image/'):
        return extract_text_from_image(file_path)
    elif mime_type == 'application/pdf':
        return extract_text_from_pdf(file_path, password)
    elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        return extract_text_from_docx(file_path)
    elif mime_type in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
        return extract_text_from_excel(file_path)
    elif mime_type == 'text/csv':
        return extract_text_from_csv(file_path)
    else:
        return ""
