import json
import time
import serial
import numpy as np
import torch
import torch.nn as nn

# =========================
# USER SETTINGS
# =========================
PORT = "COM11"
BAUDRATE = 921600
TIMEOUT = 1

CAPTURE_LEN = 8000
MODEL_PATH = "best_1dcnn.pth"
CLASS_NAMES_PATH = "class_names.json"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


# =========================
# MODEL DEFINITION
# Must match the training notebook exactly
# =========================
class Coin1DCNN(nn.Module):
    def __init__(self, num_classes):
        super().__init__()

        self.features = nn.Sequential(
            nn.Conv1d(1, 16, kernel_size=7, stride=1, padding=3),
            nn.BatchNorm1d(16),
            nn.ReLU(),
            nn.MaxPool1d(2),

            nn.Conv1d(16, 32, kernel_size=5, stride=1, padding=2),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.MaxPool1d(2),

            nn.Conv1d(32, 64, kernel_size=5, stride=1, padding=2),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(2),

            nn.Conv1d(64, 128, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1)
        )

        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(0.3),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, num_classes)
        )

    def forward(self, x):
        x = self.features(x)
        x = self.classifier(x)
        return x


# =========================
# HELPERS
# =========================
def load_class_names(path):
    with open(path, "r", encoding="utf-8") as f:
        class_names = json.load(f)

    if not isinstance(class_names, list) or len(class_names) == 0:
        raise ValueError("class_names.json is invalid or empty.")

    return class_names


def load_model(model_path, class_names):
    model = Coin1DCNN(num_classes=len(class_names)).to(DEVICE)
    state_dict = torch.load(model_path, map_location=DEVICE)
    model.load_state_dict(state_dict)
    model.eval()
    return model


def preprocess_single_signal(signal_1d):
    signal_1d = np.asarray(signal_1d, dtype=np.float32)

    mean = signal_1d.mean()
    std = signal_1d.std()
    signal_1d = (signal_1d - mean) / (std + 1e-8)

    tensor = torch.tensor(signal_1d, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
    return tensor.to(DEVICE)


def parse_uart_line(line):
    line = line.strip()
    if not line:
        return None

    try:
        return int(line)
    except ValueError:
        return None


def predict_peak(model, class_names, peak_samples):
    x = preprocess_single_signal(peak_samples)

    with torch.no_grad():
        logits = model(x)
        probs = torch.softmax(logits, dim=1)[0].cpu().numpy()
        pred_idx = int(np.argmax(probs))
        pred_label = class_names[pred_idx]
        confidence = float(probs[pred_idx])

    return pred_label, confidence, probs


def main():
    print(f"Using device: {DEVICE}")

    class_names = load_class_names(CLASS_NAMES_PATH)
    print("Loaded class names:", class_names)

    model = load_model(MODEL_PATH, class_names)
    print(f"Loaded model: {MODEL_PATH}")

    try:
        ser = serial.Serial(port=PORT, baudrate=BAUDRATE, timeout=TIMEOUT)
        time.sleep(2)
        ser.reset_input_buffer()
        print(f"Connected to {ser.name} at {BAUDRATE} baud")
    except serial.SerialException as e:
        print(f"Could not open serial port: {e}")
        return

    in_capture = False
    peak_samples = []
    peak_counter = 0

    print("\nWaiting for UART data...")
    print("Expecting blocks in this format:")
    print("START")
    print("<8000 ADC samples>")
    print("END\n")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            raw_bytes = ser.readline()

            if not raw_bytes:
                continue

            line = raw_bytes.decode("utf-8", errors="ignore").strip()

            if not line:
                continue

            if line == "START":
                if in_capture:
                    print("Warning: received START before previous capture ended. Resyncing.")
                in_capture = True
                peak_samples = []
                continue

            if line == "END":
                if not in_capture:
                    continue

                if len(peak_samples) == CAPTURE_LEN:
                    peak_counter += 1
                    pred_label, confidence, probs = predict_peak(model, class_names, peak_samples)

                    print(f"Peak {peak_counter}: {pred_label}  | confidence={confidence:.4f}")
                    for name, p in zip(class_names, probs):
                        print(f"  {name}: {p:.4f}")
                    print("-" * 40)
                else:
                    print(f"Warning: incomplete capture ignored ({len(peak_samples)}/{CAPTURE_LEN} samples)")

                in_capture = False
                peak_samples = []
                continue

            if line == "ADC ERROR":
                print("STM32 reported ADC ERROR")
                continue

            if not in_capture:
                continue

            value = parse_uart_line(line)
            if value is None:
                continue

            peak_samples.append(value)

            if len(peak_samples) > CAPTURE_LEN:
                print("Warning: too many samples before END. Dropping this capture and resyncing.")
                in_capture = False
                peak_samples = []

    except KeyboardInterrupt:
        print("\nStopped by user.")

    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("Serial port closed.")


if __name__ == "__main__":
    main()
