import os
import subprocess

def prepare_training_data(image_dir, lang='kan'):
    """
    Prepares training data for Tesseract by generating .lstmf files from images,
    ground truth (.txt), and box files.
    Requires Tesseract OCR and its training tools to be installed and in the system's PATH.
    """
    print(f"Starting training data preparation for language '{lang}'...")

    # Create a list of image base names (without extension)
    image_basenames = []
    for filename in os.listdir(image_dir):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif')):
            base_filename = os.path.splitext(filename)[0]
            image_basenames.append(base_filename)
    
    if not image_basenames:
        print("No image files found in the directory. Please ensure images are present.")
        return

    # Generate .lstmf files for each image
    for basename in image_basenames:
        image_path = os.path.join(image_dir, f"{basename}.jpg") # Assuming .jpg, adjust if other formats are primary
        ground_truth_path = os.path.join(image_dir, f"{basename}.txt")
        box_path = os.path.join(image_dir, f"{basename}.box")
        output_lstmf_path = os.path.join(image_dir, f"{basename}.lstmf")

        if not os.path.exists(image_path):
            print(f"  Warning: Image file '{image_path}' not found. Skipping .lstmf generation for '{basename}'.")
            continue
        if not os.path.exists(ground_truth_path):
            print(f"  Warning: Ground truth file '{ground_truth_path}' not found. Skipping .lstmf generation for '{basename}'.")
            continue
        if not os.path.exists(box_path):
            print(f"  Warning: Box file '{box_path}' not found. Skipping .lstmf generation for '{basename}'.")
            continue

        try:
            # Command to generate .lstmf files
            # tesseract [image_path] [output_base_name] --psm 6 lstm.train
            # The output_base_name will be used to find .box and .txt files
            command = [
                'tesseract',
                image_path,
                os.path.join(image_dir, basename), # Tesseract expects output base name without extension
                '--psm', '6',
                'lstm.train'
            ]
            
            print(f"  Generating .lstmf file for {basename}...")
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            
            if result.stderr:
                print(f"  Tesseract stderr for {basename}:\n{result.stderr}")
            
            if os.path.exists(output_lstmf_path):
                print(f"  Generated {output_lstmf_path}")
            else:
                print(f"  Error: .lstmf file {output_lstmf_path} was not created for {basename}.")

        except subprocess.CalledProcessError as e:
            print(f"  Error generating .lstmf file for {basename}: {e}")
            print(f"  Command: {' '.join(e.cmd)}")
            print(f"  Stdout: {e.stdout}")
            print(f"  Stderr: {e.stderr}")
        except FileNotFoundError:
            print("  Error: Tesseract command not found. Please ensure Tesseract OCR is installed and in your system's PATH.")
            return # Exit if tesseract is not found
        except Exception as e:
            print(f"  An unexpected error occurred for {basename}: {e}")

    print("Training data preparation complete.")

if __name__ == "__main__":
    image_directory = "kannada_training_data/images"
    prepare_training_data(image_directory, lang='kan')
