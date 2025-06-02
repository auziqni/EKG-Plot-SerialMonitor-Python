import serial
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque
import threading
import time

class RealTimeEKGPlotter:
    def __init__(self, port='COM3', baudrate=250000, buffer_size=2000):
        """
        Real-time EKG plotter for dual channel data
        
        Args:
            port: Serial port (adjust for your system)
            baudrate: Must match ESP32 baudrate (250000)
            buffer_size: Number of samples to display
        """
        self.port = port
        self.baudrate = baudrate
        self.buffer_size = buffer_size
        
        # Data buffers
        self.ch0_data = deque(maxlen=buffer_size)
        self.ch1_data = deque(maxlen=buffer_size)
        self.time_data = deque(maxlen=buffer_size)
        
        # Serial connection
        self.serial_conn = None
        self.is_running = False
        
        # Statistics
        self.sample_count = 0
        self.start_time = time.time()
        
        # Setup plot
        self.setup_plot()
        
    def setup_plot(self):
        """Setup matplotlib figure and axes"""
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(12, 8))
        
        # Channel 0 plot
        self.line1, = self.ax1.plot([], [], 'b-', linewidth=1.5, label='Channel A0')
        self.ax1.set_title('EKG Channel A0', fontsize=14)
        self.ax1.set_ylabel('12-bit ADC Value')
        self.ax1.grid(True, alpha=0.3)
        self.ax1.legend()
        
        # Channel 1 plot
        self.line2, = self.ax2.plot([], [], 'r-', linewidth=1.5, label='Channel A1')
        self.ax2.set_title('EKG Channel A1', fontsize=14)
        self.ax2.set_xlabel('Time (seconds)')
        self.ax2.set_ylabel('12-bit ADC Value')
        self.ax2.grid(True, alpha=0.3)
        self.ax2.legend()
        
        # Set initial limits
        self.ax1.set_xlim(0, 10)  # 10 seconds window
        self.ax2.set_xlim(0, 10)
        self.ax1.set_ylim(0, 4095)  # 12-bit range
        self.ax2.set_ylim(0, 4095)
        
        plt.tight_layout()
        
    def connect_serial(self):
        """Connect to ESP32 via serial"""
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1)
            print(f"Connected to {self.port} at {self.baudrate} baud")
            return True
        except Exception as e:
            print(f"Failed to connect to serial: {e}")
            return False
            
    def read_serial_data(self):
        """Thread function to read serial data continuously"""
        while self.is_running and self.serial_conn:
            try:
                line = self.serial_conn.readline().decode('utf-8').strip()
                
                # Skip empty lines and monitoring messages
                if not line or line.startswith('#'):
                    continue
                    
                # Parse JSON format [A0,A1]
                if line.startswith('[') and line.endswith(']'):
                    try:
                        data = json.loads(line)
                        if len(data) == 2:
                            current_time = time.time() - self.start_time
                            
                            # Add to buffers
                            self.ch0_data.append(data[0])
                            self.ch1_data.append(data[1])
                            self.time_data.append(current_time)
                            
                            self.sample_count += 1
                            
                    except json.JSONDecodeError:
                        continue  # Skip invalid JSON
                        
            except Exception as e:
                print(f"Serial read error: {e}")
                break
                
    def update_plot(self, frame):
        """Animation function to update plots"""
        if len(self.time_data) < 2:
            return self.line1, self.line2
            
        # Convert to numpy arrays for plotting
        times = np.array(list(self.time_data))
        ch0_values = np.array(list(self.ch0_data))
        ch1_values = np.array(list(self.ch1_data))
        
        # Update line data
        self.line1.set_data(times, ch0_values)
        self.line2.set_data(times, ch1_values)
        
        # Auto-scale time axis (rolling window)
        if len(times) > 0:
            current_time = times[-1]
            window_size = 10  # seconds
            
            self.ax1.set_xlim(max(0, current_time - window_size), current_time + 1)
            self.ax2.set_xlim(max(0, current_time - window_size), current_time + 1)
            
        # Auto-scale Y axis based on visible data
        if len(ch0_values) > 0:
            margin = 200
            self.ax1.set_ylim(min(ch0_values) - margin, max(ch0_values) + margin)
            self.ax2.set_ylim(min(ch1_values) - margin, max(ch1_values) + margin)
            
        # Update title with sample rate
        if hasattr(self, 'last_rate_update'):
            if time.time() - self.last_rate_update > 1.0:  # Update every second
                elapsed = time.time() - self.start_time
                if elapsed > 0:
                    rate = self.sample_count / elapsed
                    self.ax1.set_title(f'EKG Channel A0 - Rate: {rate:.1f} Hz')
                    self.ax2.set_title(f'EKG Channel A1 - Rate: {rate:.1f} Hz')
                self.last_rate_update = time.time()
        else:
            self.last_rate_update = time.time()
            
        return self.line1, self.line2
        
    def start_plotting(self):
        """Start the real-time plotting"""
        if not self.connect_serial():
            return
            
        self.is_running = True
        self.start_time = time.time()
        
        # Start serial reading thread
        serial_thread = threading.Thread(target=self.read_serial_data)
        serial_thread.daemon = True
        serial_thread.start()
        
        # Start animation
        ani = animation.FuncAnimation(
            self.fig, self.update_plot, interval=50, blit=False
        )
        
        print("Starting real-time plot... Close window to stop.")
        plt.show()
        
        # Cleanup
        self.is_running = False
        if self.serial_conn:
            self.serial_conn.close()
            
    def save_data_to_file(self, filename="ekg_data.csv"):
        """Save collected data to CSV file"""
        if len(self.time_data) == 0:
            print("No data to save")
            return
            
        import pandas as pd
        
        # Create DataFrame
        df = pd.DataFrame({
            'time': list(self.time_data),
            'channel_a0': list(self.ch0_data),
            'channel_a1': list(self.ch1_data)
        })
        
        # Save to CSV
        df.to_csv(filename, index=False)
        print(f"Data saved to {filename}")
        
def main():
    """Main function to run the plotter"""
    # Configuration
    PORT = 'COM6'  # Change this to your serial port
    # For Linux/Mac: '/dev/ttyUSB0' or '/dev/cu.usbserial-xxx'
    # For Windows: 'COM3', 'COM4', etc.
    
    BAUDRATE = 250000
    BUFFER_SIZE = 2000  # Number of samples to display
    
    try:
        # Create and start plotter
        plotter = RealTimeEKGPlotter(PORT, BAUDRATE, BUFFER_SIZE)
        plotter.start_plotting()
        
        # Optional: Save data after plotting
        save_data = input("Save data to file? (y/n): ")
        if save_data.lower() == 'y':
            plotter.save_data_to_file()
            
    except KeyboardInterrupt:
        print("Plotting stopped by user")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()