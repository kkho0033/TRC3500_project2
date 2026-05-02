'''
first, extract the 10ms of most important data from the csv

this can be done by thresholding:

- find your baseline value when it is "quiet" - value does not matter for the code
- find a suitable threshold for a "peak" - assume >= 2500
- once the first "peak" is detected, take the previous 50 values and the next 150 values
- there you have your 200 samples that matter for your LSTM


'''
import csv
import os

def extract_coin_drop(input_file, output_file, threshold=2500):
    # We will store all the rows from the CSV here
    data = []
    
    # Read the CSV file
    with open(input_file, 'r') as file:
        reader = csv.reader(file)
        header = next(reader)  # Save the header (sample_index, time_s, adc_value)
        
        for row in reader:
            try:
                # The ADC value is the 3rd column (index 2)
                adc_value = int(row[2])
                data.append(row)
            except (ValueError, IndexError):
                pass
                
    # Step 1: Find the exact moment of the peak
    peak_index = -1
    for i in range(len(data)):
        adc_value = int(data[i][2])
        if adc_value >= threshold:
            peak_index = i
            break
            
    # If no peak is found, we just skip this file
    if peak_index == -1:
        print(f"Skipping {input_file} - No peak of {threshold} or higher found.")
        return False
        
    # Step 2: Grab 50 before the peak and 149 after the peak.
    # Total = 50 + 1 (the peak itself) + 149 = 200 samples
    start_index = peak_index - 50
    end_index = peak_index + 150
    
    # Make sure we don't go below 0 or beyond the end of the data!
    if start_index < 0:
        start_index = 0
    if end_index > len(data):
        end_index = len(data)
        
    extracted_data = data[start_index:end_index]
    
    # Step 3: Save the cut slice into a new processed CSV file
    with open(output_file, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(extracted_data)
        
    print(f"Processed: saved {len(extracted_data)} lines to {output_file}")
    return True

def process_folder(input_folder="coin_dataset", output_folder="processed_dataset"):
    print(f"Looking for dataset in folder: '{input_folder}'...")
    
    # Create the output folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        
    # Find all CSV files in the input folder
    if not os.path.exists(input_folder):
        print(f"Error: Could not find the folder '{input_folder}'. Have you run collect_dataset.py yet?")
        return
        
    for filename in os.listdir(input_folder):
        if filename.endswith(".csv"):
            input_path = os.path.join(input_folder, filename)
            output_path = os.path.join(output_folder, filename)
            
            # Process each file
            extract_coin_drop(input_path, output_path)

if __name__ == "__main__":
    print("Starting data processing...")
    process_folder("coin_dataset", "processed_dataset")
    print("\nAll done!")
