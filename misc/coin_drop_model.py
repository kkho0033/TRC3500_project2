'''

LSTM model for coin drop detection, takes input of 200 data points from data_processing.py
output is one of four classes: D10_H10, D10_H30, D30_H10, D30_H30

'''

import os
import csv
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

# 1. Define the Dataset
class CoinDataset(Dataset):
    def __init__(self, folder_path="processed_dataset"):
        self.data_sequences = [] # list of lists, each 200 long (ADC values)
        self.labels = [] # list of numbers (0, 1, 2, 3)
        
        # Valid classes
        self.class_map = {
            "D10_H10": 0,
            "D10_H30": 1,
            "D30_H10": 2,
            "D30_H30": 3
        }
        
        # Look at every file
        if not os.path.exists(folder_path):
            print(f"Warning: Folder '{folder_path}' not found!")
            return
            
        for filename in os.listdir(folder_path):
            if filename.endswith(".csv"):
                # Find the label from the filename
                label_str = None
                for key in self.class_map.keys():
                    if filename.startswith(key):
                        label_str = key
                        break
                        
                if label_str is None:
                    continue # Skip files we can't identify
                    
                label_idx = self.class_map[label_str]
                
                # Read the CSV to get the 200 numbers
                filepath = os.path.join(folder_path, filename)
                adc_values = []
                with open(filepath, 'r') as f:
                    reader = csv.reader(f)
                    next(reader) # Skip the top text header (sample_index, time_s, adc_value)
                    for row in reader:
                        if len(row) >= 3:
                            try:
                                adc_values.append(float(row[2]))
                            except ValueError:
                                pass
                                
                # Make sure it's exactly 200 long as expected
                if len(adc_values) == 200:
                    self.data_sequences.append(adc_values)
                    self.labels.append(label_idx)
                    
        print(f"Loaded {len(self.data_sequences)} valid items from {folder_path}.")

    def __len__(self):
        return len(self.data_sequences)

    def __getitem__(self, idx):
        # We need to give PyTorch numbers it can easily work with
        sequence = self.data_sequences[idx]
        
        # Make it a Tensor (PyTorch's number format) and reshape it for the LSTM
        # LSTM wants the shape to be (Sequence Length, Features). 
        # Here we have (200, 1), because there are 200 steps, and each has 1 feature (ADC value).
        x_tensor = torch.tensor(sequence, dtype=torch.float32).unsqueeze(1) 
        
        # The answer (label) is just an integer (0, 1, 2, or 3)
        y_tensor = torch.tensor(self.labels[idx], dtype=torch.long)
        
        return x_tensor, y_tensor

# 2. Define the LSTM Model
class CoinDropLSTM(nn.Module):
    def __init__(self, input_size=1, hidden_size=32, num_classes=4):
        super().__init__()
        
        # The memory layer that looks at the sequence
        self.lstm = nn.LSTM(input_size=input_size, hidden_size=hidden_size, batch_first=True)
        
        # The final decision layer that picks one of the 4 classes
        self.fc = nn.Linear(hidden_size, num_classes)

    def forward(self, x):
        # x is the sequence. It goes into the LSTM.
        # The LSTM spits out a lot of data, but we only care about its *very last* thought.
        lstm_out, _ = self.lstm(x)
        
        # lstm_out has all the steps, we grab the very last step (-1)
        last_thought = lstm_out[:, -1, :] 
        
        # Then we push that last thought through our final decision layer to make a guess
        predictions = self.fc(last_thought)
        return predictions

# 3. Training Loop Process
def train_model():
    # Setup the data
    dataset = CoinDataset("processed_dataset")
    if len(dataset) == 0:
        print("No data to train on. Please check the processed_dataset folder and let the script run first.")
        return
        
    # Shuffle and split: 80% for learning, 20% for testing
    data_size = len(dataset)
    train_size = int(0.8 * data_size)
    test_size = data_size - train_size
    
    # We use a manual split logic so it works consistently every time
    generator = torch.Generator().manual_seed(42)  # Keep the randomness the same each run
    
    # Check if we have enough data to split safely. (requires at least 2 usually, but PyTorch handles small pools)
    train_dataset, test_dataset = torch.utils.data.random_split(dataset, [train_size, test_size], generator=generator)
    
    # Create DataLoaders (they feed the model in smaller, manageable bite-sized batches of 8)
    train_loader = DataLoader(train_dataset, batch_size=8, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=8, shuffle=False)
    
    # Setup Device (Use graphics card CUDA if available, else normal CPU processor)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\nUsing processor: {device}")
    print(f"Training on {train_size} items, Testing on {test_size} items.\n")
    
    # Put our model onto the chosen processor
    model = CoinDropLSTM().to(device)
    
    # Setup the Loss function (measures how wrong the guesses are) 
    criterion = nn.CrossEntropyLoss()
    
    # Setup the Optimizer (the mechanic that fixes the mistakes inside the model)
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    
    num_epochs = 50
    print("Starting training...")
    
    # We will test immediately at epoch 0, then every 5 epochs and the final one.
    for epoch in range(num_epochs):
        model.train() # Tell model we are officially learning now
        total_loss = 0
        correct_guesses = 0
        total_items = 0
        
        for inputs, labels in train_loader:
            inputs, labels = inputs.to(device), labels.to(device)
            
            # Step 1: Wipe memory clean from the last batch's math
            optimizer.zero_grad()
            
            # Step 2: Make guesses on this new batch
            outputs = model(inputs)
            
            # Step 3: Check how wrong the guesses were
            loss = criterion(outputs, labels)
            
            # Step 4: Learn from mistakes (update its internal memory/weights)
            loss.backward()
            optimizer.step()
            
            # Track our score progress
            total_loss += loss.item()
            _, top_guess = torch.max(outputs, 1)
            correct_guesses += (top_guess == labels).sum().item()
            total_items += labels.size(0)
            
        train_accuracy = 100 * correct_guesses / total_items if total_items > 0 else 0
        
        # Every 5 rounds (or strictly on round 1 and 50), run a quiet test to see if it's actually getting smarter
        if (epoch + 1) % 5 == 0 or epoch == 0 or epoch == num_epochs - 1:
            model.eval() # Tell model we are just testing, no learning/cheating allowed
            test_correct = 0
            test_total = 0
            
            with torch.no_grad(): # Disable memory updating during test
                for inputs, labels in test_loader:
                    inputs, labels = inputs.to(device), labels.to(device)
                    outputs = model(inputs)
                    _, top_guess = torch.max(outputs, 1)
                    test_correct += (top_guess == labels).sum().item()
                    test_total += labels.size(0)
            
            test_accuracy = 100 * test_correct / test_total if test_total > 0 else 0
            
            error_val = total_loss/len(train_loader) if len(train_loader) > 0 else 0
            print(f"Round [{(epoch+1):2d}/{num_epochs}] - "
                  f"Error: {error_val:.4f} - "
                  f"Training Score: {train_accuracy:.1f}% - "
                  f"Test Score: {test_accuracy:.1f}%")
                  
    print("\nTraining completed!")
    
    # Save the model's brain so you don't have to retrain it next time
    torch.save(model.state_dict(), "coin_drop_lstm.pth")
    print("Saved the smart model rules to 'coin_drop_lstm.pth'")

if __name__ == "__main__":
    train_model()