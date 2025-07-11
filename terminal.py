import serial
import time

# Connect ke ESP32
ser = serial.Serial('COM6', 500000)  # Adjust port
print("EKG Data Receiver Ready...")

while True:
    try:
        line = ser.readline().decode().strip()
        if line.startswith('#'):
            print(f"Status: {line}")
        else:
            # Process EKG data
            print(f"EKG Data: {line[:50]}...")  # Show first 50 chars
    except KeyboardInterrupt:
        break

ser.close()