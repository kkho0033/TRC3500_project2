import serial
import sys

# Configure the serial port
# Ensure the port matches your computer (e.g., 'COM9' or '/dev/ttyACM0')
ser = serial.Serial(port="COM11", baudrate=921600, timeout=1)

print(f"Connected to: {ser.name}")
print("Reading ADC data... Press Ctrl+C to stop.\n")

def stream_adc():
    try:
        while True:
            # 1. Read a full line from the serial buffer
            if ser.in_waiting > 0:
                line_bytes = ser.readline()
                
                # 2. Decode bytes to string
                try:
                    line = line_bytes.decode('utf-8').strip()
                except UnicodeDecodeError:
                    continue # Skip messy data

                if not line:
                    continue

                # 3. Parse based on your STM32's format
                # If STM32 sends: "ADC Value = 1234"
                if "ADC Value" in line:
                    try:
                        value = line.split("=")[1].strip()
                        print(f"Live ADC: {value}")
                    except IndexError:
                        pass
                
                # If STM32 sends: "Mean Value = 1234.56"
                elif "Mean Value" in line:
                    try:
                        mean = line.split("=")[1].strip()
                        print(f"--- Average: {mean} ---")
                    except IndexError:
                        pass
                
                # If STM32 just sends the number alone: "1234"
                else:
                    print(f"Raw Data: {line}")

    except KeyboardInterrupt:
        print("\nStopping Stream...")
    finally:
        ser.close()
        print("Serial Port Closed.")

if __name__ == "__main__":
    stream_adc()