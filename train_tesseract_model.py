import os
import subprocess
import glob
import shutil

def train_tesseract_model(training_data_dir, lang_code='kan', model_name='kannada_fine_tuned', iterations=1000):
    """
    Trains a Tesseract OCR model using the generated .lstmf files.
    Requires Tesseract training tools to be installed and in the system's PATH.
    """
    print(f"Starting Tesseract model training for language '{lang_code}'...")
    print(f"Model name: {model_name}, Iterations: {iterations}")

    # output_base will be a prefix for files created in training_data_dir
    output_base = model_name 
    # checkpoint_prefix is the base traineddata file to continue from
    checkpoint_prefix = f"{lang_code}.traineddata"

    # Create a file list for lstmtraining
    list_file_path = os.path.join(training_data_dir, 'all_lstmf.txt')
    lstmf_files = glob.glob(os.path.join(training_data_dir, '*.lstmf'))
    if not lstmf_files:
        print("Error: No .lstmf files found for training. Please ensure training data preparation was successful.")
        return

    with open(list_file_path, 'w') as f:
        for lstmf_file in lstmf_files:
            f.write(os.path.basename(lstmf_file) + '\n')

    print(f"Created list file: {list_file_path}")

    # Command to start training
    # lstmtraining --continue_from [existing_model_checkpoint] --old_traineddata [existing_traineddata]
    #              --traineddata [output_traineddata] --net_spec '[net_spec]'
    #              --model_output [output_model_prefix] --train_listfile [list_file]
    #              --max_iterations [iterations]
    
    # For fine-tuning, we usually start from an existing traineddata file (e.g., kan.traineddata)
    # and continue training.
    
    # First, ensure the base traineddata file exists in the tessdata directory
    # This is a common location, but might vary. User needs to ensure it's accessible.
    # For simplicity, we'll assume it's in the Tesseract tessdata path or current directory.
    # A more robust solution would check TESSDATA_PREFIX environment variable.
    
    # Let's assume 'kan.traineddata' is available in the Tesseract tessdata path.
    # We need to specify a base model to continue from.
    
    # The `lstmtraining` command requires a starter traineddata file.
    # If we are starting from scratch, we would use `lstmtraining --debug_interval 0 --append_index 5 --net_spec "[1,36,0,1 Ct3,3,16 Mp2,2 Lfys64 Lfx96 Lrx96 Lfx256 O1c100]" --model_output [output_model_prefix] --train_listfile [list_file] --max_iterations [iterations]`
    # However, the task is to fine-tune, so we need to continue from an existing model.
    
    # For fine-tuning, we need a base model. Let's assume 'kan.traineddata' is the base.
    # We need to copy it to the training_data_dir for the training process to find it easily.
    
    # Check if a base traineddata file exists in the tessdata directory
    # This path is typical for Windows installations. Adjust for other OS if needed.
    tessdata_path = os.environ.get('TESSDATA_PREFIX', 'C:\\Program Files\\Tesseract-OCR\\tessdata')
    base_traineddata_path = os.path.join(tessdata_path, f"{lang_code}.traineddata")

    if not os.path.exists(base_traineddata_path):
        print(f"Error: Base traineddata file '{base_traineddata_path}' not found.")
        print("Please ensure Tesseract's Kannada language data (kan.traineddata) is installed correctly.")
        return

    # Copy the base traineddata to the training directory
    shutil.copy(base_traineddata_path, os.path.join(training_data_dir, f"{lang_code}.traineddata"))
    print(f"Copied '{lang_code}.traineddata' to training directory.")

    # Define the training command
    # Define the training command to generate checkpoints
    training_command = [
        'lstmtraining',
        '--old_traineddata', checkpoint_prefix, # Specify the base traineddata
        '--model_output', output_base, # Output prefix for checkpoints
        '--train_listfile', os.path.basename(list_file_path), # Should be relative to cwd
        '--max_iterations', str(iterations)
    ]

    try:
        print(f"  Executing training command (this may take a long time): {' '.join(training_command)}")
        training_process = subprocess.Popen(training_command, cwd=training_data_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Stream output for long-running process
        while True:
            output = training_process.stdout.readline()
            if output == '' and training_process.poll() is not None:
                break
            if output:
                print(output.strip())
        
        training_process.wait() # Wait for the training process to finish
        
        if training_process.returncode == 0:
            print(f"  Tesseract model training completed successfully. Checkpoints generated with prefix: {output_base}")
            
            # Step 2: Combine checkpoints into a .traineddata file
            print(f"  Combining checkpoints into final '{model_name}.traineddata'...")
            combine_command = [
                'lstmtraining',
                '--stop_training',
                '--continue_from', f"{output_base}_checkpoint", # Use the last generated checkpoint
                '--traineddata', f"{model_name}.traineddata" # Final output traineddata file
            ]
            
            combine_process = subprocess.run(combine_command, cwd=training_data_dir, capture_output=True, text=True, check=True)
            
            if combine_process.stderr:
                print(f"  Tesseract combine stderr:\n{combine_process.stderr}")
            
            final_traineddata_path = os.path.join(training_data_dir, f"{model_name}.traineddata")
            if os.path.exists(final_traineddata_path):
                print(f"  Final traineddata file created at: {final_traineddata_path}")
            else:
                print(f"  Error: Final traineddata file {final_traineddata_path} was not created.")

        else:
            print(f"  Error: Tesseract model training failed with exit code {training_process.returncode}.")

    except subprocess.CalledProcessError as e:
        print(f"  Error during training or combining: {e}")
        print(f"  Command: {' '.join(e.cmd)}")
        print(f"  Stdout: {e.stdout}")
        print(f"  Stderr: {e.stderr}")
    except FileNotFoundError:
        print("  Error: lstmtraining command not found. Please ensure Tesseract training tools are installed and in your system's PATH.")
    except Exception as e:
        print(f"  An unexpected error occurred during training: {e}")

    print("Tesseract model training process completed.")

if __name__ == "__main__":
    training_data_directory = "kannada_training_data/images"
    # You can adjust iterations based on your needs. More iterations generally mean better accuracy but longer training time.
    train_tesseract_model(training_data_directory, iterations=500) # Reduced iterations for initial test
