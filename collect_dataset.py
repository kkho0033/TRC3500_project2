import serial
import csv
import os
import time
from datetime import datetime

# =========================
# USER SETTINGS
# =========================
PORT = "COM11"
BAUDRATE = 921600
TIMEOUT = 1
SAVE_FOLDER = "coin_dataset"
CSV_FILE = "all_peaks.csv"
# CAPTURE_LEN = 2560
CAPTURE_LEN = 8000


VALID_LABELS = ["D10_H10", "D10_H30", "D30_H10", "D30_H30"]


# =========================
# HELPERS
# =========================
def create_folder(folder_path):
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)


def parse_uart_line(line):
    line = line.strip()
    if not line:
        return None

    try:
        return int(line)
    except ValueError:
        return None


def ensure_csv_header(filepath):
    if not os.path.exists(filepath):
        with open(filepath, mode="w", newline="") as f:
            writer = csv.writer(f)
            header = ["timestamp", "label", "peak_index"] + [f"s{i}" for i in range(CAPTURE_LEN)]
            writer.writerow(header)


def get_next_peak_index(filepath):
    """
    Continue peak numbering across program runs.
    """
    if not os.path.exists(filepath):
        return 1

    last_peak_index = 0
    with open(filepath, mode="r", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if len(row) >= 3:
                try:
                    last_peak_index = int(row[2])
                except ValueError:
                    pass

    return last_peak_index + 1


def append_peak_row(filepath, label, peak_index, samples):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    row = [timestamp, label, peak_index] + samples

    with open(filepath, mode="a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row)


def record_peaks(ser, label, csv_path):
    """
    Wait for:
        START
        <2560 numeric lines>
        END

    Then save one CSV row for that peak.
    """
    print(f"\nRecording label: {label}")
    print("Drop coins now. Press Ctrl+C to stop.\n")

    peak_index = get_next_peak_index(csv_path)

    in_capture = False
    peak_samples = []

    ser.reset_input_buffer()

    while True:
        raw_bytes = ser.readline()

        if not raw_bytes:
            continue

        line = raw_bytes.decode("utf-8", errors="ignore").strip()

        # ---- marker handling ----
        if line == "START":
            # start a fresh capture block
            in_capture = True
            peak_samples = []
            continue

        if line == "END":
            if in_capture:
                if len(peak_samples) == CAPTURE_LEN:
                    append_peak_row(csv_path, label, peak_index, peak_samples)
                    print(f"Saved peak {peak_index} with {len(peak_samples)} samples")
                    peak_index += 1
                else:
                    print(f"Warning: incomplete peak ignored ({len(peak_samples)}/{CAPTURE_LEN} samples)")
            in_capture = False
            peak_samples = []
            continue

        # ---- ignore anything outside START...END ----
        if not in_capture:
            continue

        # ---- parse numeric ADC line ----
        value = parse_uart_line(line)
        if value is None:
            # ignore text like ADC ERROR or corrupted lines
            continue

        peak_samples.append(value)

        # optional safety check
        if len(peak_samples) > CAPTURE_LEN:
            print("Warning: too many samples before END, resyncing...")
            in_capture = False
            peak_samples = []


def main():
    create_folder(SAVE_FOLDER)
    csv_path = os.path.join(SAVE_FOLDER, CSV_FILE)
    ensure_csv_header(csv_path)

    try:
        ser = serial.Serial(port=PORT, baudrate=BAUDRATE, timeout=TIMEOUT)
        time.sleep(2)
        print(f"Connected to {ser.name} at {BAUDRATE} baud")
    except serial.SerialException as e:
        print(f"Could not open serial port: {e}")
        return

    print("\nValid labels:")
    for label in VALID_LABELS:
        print(f"  - {label}")

    try:
        while True:
            label = input("\nEnter label (or q to quit): ").strip()

            if label.lower() == "q":
                break

            if label not in VALID_LABELS:
                print("Invalid label.")
                continue

            try:
                record_peaks(ser, label, csv_path)
            except KeyboardInterrupt:
                print("\nStopped current recording session.")

    finally:
        if ser.is_open:
            ser.close()
            print("Serial port closed.")


if __name__ == "__main__":
    main()