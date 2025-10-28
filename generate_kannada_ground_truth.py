import os
from PIL import Image
import pytesseract

def generate_kannada_ground_truth(image_dir):
    """
    Performs OCR on Kannada images and saves the recognized Kannada text as ground truth files.
    """
    print(f"Starting ground truth generation (OCR for Kannada text)...")

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

                # Step 2: Save the recognized Kannada text as the ground truth file
                with open(output_txt_path, 'w', encoding='utf-8') as f:
                    f.write(kannada_text)
                print(f"  Generated Kannada ground truth for {filename} at {output_txt_path}")

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
    
    # Check for Kannada language data
    # This is a basic check and might not cover all Tesseract configurations
    try:
        # Attempt to OCR a dummy image with 'kan' language to check if it's available
        # This is a heuristic, a more robust check would involve Tesseract's API if available
        dummy_image = Image.new('RGB', (100, 50), color = 'white')
        pytesseract.image_to_string(dummy_image, lang='kan')
    except Exception as e:
        print(f"Kannada language data ('kan.traineddata') might not be installed for Tesseract or Tesseract is not configured correctly: {e}")
        print("Please ensure 'kan.traineddata' is in your Tesseract tessdata directory.")
        print("You can usually find language data here: https://tesseract-ocr.github.io/tessdoc/Data-Files.html")
        exit()

    generate_kannada_ground_truth(image_directory)
