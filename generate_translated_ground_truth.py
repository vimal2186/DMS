import os
from google.cloud import translate_v2 as translate
from PIL import Image
import pytesseract

# Set your Google Cloud project ID here
# You need to have Google Cloud credentials configured for this to work.
# For example, by setting the GOOGLE_APPLICATION_CREDENTIALS environment variable:
# export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/keyfile.json"
# Or by logging in via `gcloud auth application-default login`
PROJECT_ID = "your-google-cloud-project-id" # IMPORTANT: Replace with your actual Google Cloud Project ID

def generate_translated_ground_truth(image_dir, target_language='en'):
    """
    Performs OCR on Kannada images, translates the text to English using Google Cloud Translate,
    and saves the translated text as ground truth files.
    """
    translate_client = translate.Client(project=PROJECT_ID)

    print(f"Starting ground truth generation (OCR and translation to {target_language})...")

    for filename in os.listdir(image_dir):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif')):
            image_path = os.path.join(image_dir, filename)
            base_filename = os.path.splitext(filename)[0]
            output_txt_path = os.path.join(image_dir, f"{base_filename}.txt")

            try:
                # Step 1: Perform OCR using Tesseract to get Kannada text
                print(f"  Performing OCR on {filename}...")
                kannada_text = pytesseract.image_to_string(Image.open(image_path), lang='kan')
                kannada_text = kannada_text.strip()

                if not kannada_text:
                    print(f"  No Kannada text found in {filename}. Skipping translation.")
                    with open(output_txt_path, 'w', encoding='utf-8') as f:
                        f.write("") # Create an empty ground truth file
                    continue

                # Step 2: Translate Kannada text to target_language (English)
                print(f"  Translating text from {filename} to {target_language}...")
                result = translate_client.translate(kannada_text, target_language=target_language, source_language='kn')
                translated_text = result['translatedText']

                # Step 3: Save the translated text as the ground truth file
                with open(output_txt_path, 'w', encoding='utf-8') as f:
                    f.write(translated_text)
                print(f"  Generated ground truth for {filename} (translated to English) at {output_txt_path}")

            except Exception as e:
                print(f"  Error processing {filename}: {e}")
                # Create an empty ground truth file on error to avoid blocking subsequent steps
                with open(output_txt_path, 'w', encoding='utf-8') as f:
                    f.write("")
                continue

    print("Ground truth generation complete.")

if __name__ == "__main__":
    image_directory = "kannada_training_data/images"
    
    # Ensure pytesseract is installed and Tesseract OCR is in your PATH
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        print("Tesseract is not installed or not in your PATH. Please install Tesseract OCR.")
        print("You can download it from: https://tesseract-ocr.github.io/tessdoc/Installation.html")
        print("Also, ensure 'pytesseract' Python library is installed: pip install pytesseract")
        exit()

    # Ensure Google Cloud credentials are set up
    try:
        translate.Client(project=PROJECT_ID)
    except Exception as e:
        print(f"Google Cloud credentials not configured correctly or PROJECT_ID is missing/incorrect: {e}")
        print("Please ensure 'PROJECT_ID' in the script is set to your Google Cloud Project ID.")
        print("Also, ensure your Google Cloud authentication is set up (e.g., GOOGLE_APPLICATION_CREDENTIALS environment variable or `gcloud auth application-default login`).")
        exit()

    generate_translated_ground_truth(image_directory)
