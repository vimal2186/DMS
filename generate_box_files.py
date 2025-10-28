import os
import subprocess

def generate_box_files(image_dir, lang='kan'):
    """
    Generates .box files for each image in the specified directory using Tesseract.
    Requires Tesseract OCR to be installed and in the system's PATH.
    """
    print(f"Starting box file generation for language '{lang}'...")

    for filename in os.listdir(image_dir):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif')):
            image_path = os.path.join(image_dir, filename)
            base_filename = os.path.splitext(filename)[0]
            ground_truth_path = os.path.join(image_dir, f"{base_filename}.txt")
            output_box_path = os.path.join(image_dir, f"{base_filename}.box")

            if not os.path.exists(ground_truth_path):
                print(f"  Warning: Ground truth file '{ground_truth_path}' not found for '{filename}'. Skipping box file generation for this image.")
                continue

            try:
                # Tesseract command to generate box files
                # tesseract [image_path] [output_base_name] -l [lang] --psm 6 makebox
                # --psm 6: Assume a single uniform block of text.
                command = [
                    'tesseract',
                    image_path,
                    os.path.join(image_dir, base_filename), # Tesseract expects output base name without extension
                    '-l', lang,
                    '--psm', '6',
                    'makebox'
                ]
                
                print(f"  Generating box file for {filename}...")
                result = subprocess.run(command, capture_output=True, text=True, check=True)
                
                if result.stderr:
                    print(f"  Tesseract stderr for {filename}:\n{result.stderr}")
                
                if os.path.exists(output_box_path):
                    print(f"  Generated {output_box_path}")
                else:
                    print(f"  Error: Box file {output_box_path} was not created for {filename}.")

            except subprocess.CalledProcessError as e:
                print(f"  Error generating box file for {filename}: {e}")
                print(f"  Command: {' '.join(e.cmd)}")
                print(f"  Stdout: {e.stdout}")
                print(f"  Stderr: {e.stderr}")
            except FileNotFoundError:
                print("  Error: Tesseract command not found. Please ensure Tesseract OCR is installed and in your system's PATH.")
                return # Exit if tesseract is not found
            except Exception as e:
                print(f"  An unexpected error occurred for {filename}: {e}")

    print("Box file generation complete.")

if __name__ == "__main__":
    image_directory = "kannada_training_data/images"
    generate_box_files(image_directory, lang='kan')
