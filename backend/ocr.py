import pytesseract
import cv2
import pdfplumber
import docx
import pandas as pd
from PIL import Image
import fitz # PyMuPDF
import io
import numpy as np
import os # Added for environment variable access
import logging
from typing import Optional # Import Optional

# Configuration for OCR pre-processing and debugging
ENABLE_OCR_PREPROCESSING = os.getenv('ENABLE_OCR_PREPROCESSING', 'False').lower() == 'true'
SAVE_OCR_DEBUG_IMAGES = os.getenv('SAVE_OCR_DEBUG_IMAGES', 'False').lower() == 'true'
OCR_DEBUG_IMAGE_DIR = "ocr_debug_images" # Directory to save debug images
TESSERACT_PSM = os.getenv('TESSERACT_PSM', '3') # Default PSM to 3 (fully automatic page segmentation)

# Create debug image directory if it doesn't exist
if SAVE_OCR_DEBUG_IMAGES:
    os.makedirs(OCR_DEBUG_IMAGE_DIR, exist_ok=True)

# Removed: Logging is now configured centrally in backend/app.py
# logging.basicConfig(filename='ocr_debug.log', level=logging.INFO,
#                     format='%(asctime)s - %(levelname)s - %(message)s')

# Reverted: Removed deskew_image_min_area_rect function and its calls.

def preprocess_image_for_ocr(image: np.ndarray) -> np.ndarray:
    """
    Applies a series of image processing steps to enhance OCR accuracy.
    """
    if not ENABLE_OCR_PREPROCESSING:
        return image

    # 1. Convert to grayscale
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # 2. Denoising (Non-local Means Denoising)
    # Parameters: h (filter strength), hColor (color filter strength), templateWindowSize, searchWindowSize
    denoised_img = cv2.fastNlMeansDenoising(gray_image, None, 30, 7, 21) # Using grayscale version
    
    # 3. Binarization (Adaptive Thresholding)
    # ADAPTIVE_THRESH_GAUSSIAN_C is generally good for varying lighting
    binarized_img = cv2.adaptiveThreshold(denoised_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    
    # 4. Skew Correction (Deskewing) - using moments
    coords = np.column_stack(np.where(binarized_img > 0))
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    
    (h, w) = binarized_img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(binarized_img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    
    logging.debug("Image pre-processed (grayscale, denoised, binarized, deskewed).")
    return rotated

def extract_text_from_image(file_path: str) -> str:
    """Extracts text from an image file."""
    try:
        image = cv2.imread(file_path)
        if image is None:
            raise ValueError(f"Could not read image from {file_path}")

        processed_image = preprocess_image_for_ocr(image)
        
        if SAVE_OCR_DEBUG_IMAGES:
            debug_filename = os.path.join(OCR_DEBUG_IMAGE_DIR, f"processed_image_{os.path.basename(file_path)}")
            cv2.imwrite(debug_filename, processed_image)
            logging.info(f"Saved processed image for debug: {debug_filename}")

        # --- TESSERACT CONFIG (Using configurable PSM) ---
        tesseract_config = f'--oem 3 --psm {TESSERACT_PSM} -l eng+hin+kan' 
        
        text = pytesseract.image_to_string(Image.fromarray(processed_image), config=tesseract_config)
        logging.info(f"Tesseract OCR completed for image {file_path} with config: '{tesseract_config}'")
        # --- END TESSERACT CONFIG ---

        return text, None

    except Exception as e:
        error_msg = f"Error extracting text from image file {file_path}: {e}"
        logging.error(error_msg)
        return "", error_msg

def extract_text_from_pdf(file_path: str, password: str = None) -> tuple[str, Optional[str]]:
    """Extracts text from a PDF file, falling back to OCR if text extraction fails."""
    full_text = ""
    logging.info(f"Starting PDF extraction for {file_path}")
    doc = None # Initialize doc to None for cleanup

    try:
        # First attempt: standard text extraction
        with pdfplumber.open(file_path, password=password) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + "\n\n"
        
        if full_text.strip():
            logging.info(f"Successfully extracted text from PDF {file_path} using pdfplumber.")
            return full_text, None
        
        # Second attempt: OCR on images/scanned PDF (fallback)
        logging.warning(f"No text extracted from PDF {file_path} via pdfplumber. Attempting OCR fallback.")
        
        # Using PyMuPDF (fitz) for reliable image extraction
        doc = fitz.open(file_path) 
        
        if doc.is_encrypted:
            if not password:
                raise Exception("PDF is password-protected. Please provide a password.")
            
            if not doc.authenticate(password):
                 raise Exception("PDF is password-protected and the provided password is wrong or ineffective.")
        
        for i in range(len(doc)):
            page = doc.load_page(i)
            
            # --- DPI settings for OCR ---
            # Retain matrix (2, 2) for stable processing
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) 
            # --- END DPI settings ---
            
            img_data = pix.tobytes("ppm")
            img = Image.open(io.BytesIO(img_data))

            # Convert to OpenCV format for pre-processing
            numpy_img = np.array(img)
            
            # Apply pre-processing if enabled
            processed_image = preprocess_image_for_ocr(numpy_img)
            
            if SAVE_OCR_DEBUG_IMAGES:
                debug_filename = os.path.join(OCR_DEBUG_IMAGE_DIR, f"processed_pdf_page_{i+1}_{os.path.basename(file_path)}.png")
                cv2.imwrite(debug_filename, processed_image)
                logging.info(f"Saved processed PDF page {i+1} for debug: {debug_filename}")

            # Apply the configurable Tesseract config for PDF OCR fallback
            tesseract_config = f'--oem 3 --psm {TESSERACT_PSM} -l eng+hin+kan'
            page_ocr_text = pytesseract.image_to_string(Image.fromarray(processed_image), config=tesseract_config)
            
            if page_ocr_text:
                full_text += f"--- OCR Page {i+1} ---\n" + page_ocr_text + "\n\n"
        
        doc.close() # Close document after processing all pages
        
        if full_text.strip():
            logging.info(f"Successfully extracted text from PDF {file_path} using OCR fallback with pre-processing {'enabled' if ENABLE_OCR_PREPROCESSING else 'disabled'}.")
            return full_text, None
        
        warning_msg = f"Failed to extract any text from PDF {file_path} even with OCR fallback."
        logging.warning(warning_msg)
        return "", warning_msg

    except Exception as e:
        # Clean up the document object if it was opened before the error was raised
        if 'doc' in locals() and doc is not None and not doc.is_closed:
             doc.close()

        error_msg = f"Error extracting text from PDF file {file_path}: {e}"
        logging.error(error_msg)
        return "", error_msg

def extract_text_from_word(file_path: str) -> tuple[str, Optional[str]]:
    """Extracts text from a DOCX file."""
    text = ""
    try:
        doc = docx.Document(file_path)
        for para in doc.paragraphs:
            text += para.text + "\n"
        if text.strip():
            logging.info(f"Successfully extracted text from Word file {file_path}.")
            return text, None
        else:
            warning_msg = f"No text extracted from Word file {file_path}."
            logging.warning(warning_msg)
            return "", warning_msg
    except Exception as e:
        error_msg = f"Error extracting text from Word file {file_path}: {e}"
        logging.error(error_msg)
        return "", error_msg

def extract_text_from_excel(file_path: str) -> tuple[str, Optional[str]]:
    """Extracts text from an Excel (XLSX, XLS) file."""
    text = ""
    try:
        df = pd.read_excel(file_path, sheet_name=None)
        for sheet_name, sheet_df in df.items():
            text += f"--- Sheet: {sheet_name} ---\n"
            text += sheet_df.to_string() + "\n\n"
        if text.strip():
            logging.info(f"Successfully extracted text from Excel file {file_path}.")
            return text, None
        else:
            warning_msg = f"No text extracted from Excel file {file_path}."
            logging.warning(warning_msg)
            return "", warning_msg
    except Exception as e:
        error_msg = f"Error extracting text from Excel file {file_path}: {e}"
        logging.error(error_msg)
        return "", error_msg

def extract_text_from_csv(file_path: str) -> tuple[str, Optional[str]]:
    """Extracts text from a CSV file."""
    text = ""
    try:
        df = pd.read_csv(file_path)
        text = df.to_string()
        if text.strip():
            logging.info(f"Successfully extracted text from CSV file {file_path}.")
            return text, None
        else:
            warning_msg = f"No text extracted from CSV file {file_path}."
            logging.warning(warning_msg)
            return "", warning_msg
    except Exception as e:
        error_msg = f"Error extracting text from CSV file {file_path}: {e}"
        logging.error(error_msg)
        return "", error_msg

def extract_text(file_path: str, mime_type: str, password: str = None) -> tuple[str, Optional[str]]:
    """Extracts text from a file based on its MIME type."""
    if mime_type.startswith('image/'):
        return extract_text_from_image(file_path)
    elif mime_type == 'application/pdf':
        return extract_text_from_pdf(file_path, password)
    elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        return extract_text_from_word(file_path)
    elif mime_type in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
        return extract_text_from_excel(file_path)
    elif mime_type == 'text/csv':
        return extract_text_from_csv(file_path)
    else:
        error_msg = f"File type {mime_type} not supported for text extraction."
        logging.error(error_msg)
        return "", error_msg
