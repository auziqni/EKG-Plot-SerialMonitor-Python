#!/usr/bin/env python3
"""
PyQt5 Real-time EKG Visualizer
Receives 12-channel hex data from ESP32 via WebSocket
Displays selected channel with real-time plotting
"""

import sys
import json
import time
import threading
import asyncio
from collections import deque
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, 
                            QHBoxLayout, QWidget, QComboBox, QLabel)
from PyQt5.QtCore import QTimer, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QFont

import websockets
import re

class DataProcessor:
    """Handle EKG data processing and validation"""
    
    @staticmethod
    def process_value(raw_value):
        """
        Clamp EKG data to valid 12-bit range (0-4095)
        Args: raw_value (int) - Raw decimal value from hex conversion
        Returns: int - Clamped value between 0-4095
        """
        if raw_value < 0:
            return 0
        elif raw_value > 4095:
            return 4095
        else:
            return raw_value
    
    @staticmethod
    def parse_hex_line(hex_line):
        """
        Parse single line of hex data to 12 processed values
        Args: hex_line (str) - "800,801,802,C00,..."
        Returns: list - 12 processed decimal values
        """
        try:
            hex_values = hex_line.strip().split(',')
            if len(hex_values) != 12:
                return None
            
            # Convert hex to decimal and process each value
            processed_values = []
            for hex_val in hex_values:
                decimal_val = int(hex_val, 16)
                processed_val = DataProcessor.process_value(decimal_val)
                processed_values.append(processed_val)
            
            return processed_values
        
        except (ValueError, AttributeError):
            return None

class WebSocketThread(QThread):
    """
    WebSocket client thread for receiving ESP32 data
    Runs in separate thread to avoid blocking UI
    """
    # Qt signals for thread-safe communication with main UI thread
    data_received = pyqtSignal(list)  # Emits list of 12-channel data
    connection_status = pyqtSignal(str)  # Emits connection status string
    
    def __init__(self):
        super().__init__()
        self.server_ip = "0.0.0.0"
        self.server_port = 8765
        self.running = True
    
    def run(self):
        """Main thread execution - runs WebSocket server"""
        # Create new event loop for this thread (required for asyncio)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Start WebSocket server in this thread's event loop
            loop.run_until_complete(self.start_server())
        except Exception as e:
            self.connection_status.emit(f"Server Error: {e}")
        finally:
            loop.close()
    
    async def start_server(self):
        """Start WebSocket server and handle connections"""
        self.connection_status.emit("Server Starting...")
        
        async with websockets.serve(self.handle_client, self.server_ip, self.server_port):
            self.connection_status.emit(f"Server Running on {self.server_ip}:{self.server_port}")
            
            # Keep server running until thread is stopped
            while self.running:
                await asyncio.sleep(0.1)
    
    async def handle_client(self, websocket, path):
        """
        Handle individual ESP32 client connection
        Args: websocket - WebSocket connection object
              path - Connection path (unused)
        """
        client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
        self.connection_status.emit(f"ESP32 Connected: {client_ip}")
        
        try:
            async for message in websocket:
                if isinstance(message, str) and message.strip():
                    # Parse received hex data
                    lines = message.strip().split('\n')
                    
                    for line in lines:
                        if line.strip():
                            # Process each line of 12-channel hex data
                            processed_data = DataProcessor.parse_hex_line(line)
                            
                            if processed_data and len(processed_data) == 12:
                                # Emit data to main UI thread via Qt signal
                                self.data_received.emit(processed_data)
                    
                    # Send acknowledgment back to ESP32
                    try:
                        await websocket.send("OK")
                    except:
                        break  # Connection lost
        
        except websockets.exceptions.ConnectionClosed:
            self.connection_status.emit(f"ESP32 Disconnected: {client_ip}")
        except Exception as e:
            self.connection_status.emit(f"Connection Error: {e}")
    
    def stop(self):
        """Stop the WebSocket thread"""
        self.running = False

class EKGPlotWidget(QWidget):
    """
    Custom widget containing matplotlib plot for EKG visualization
    Handles real-time data plotting with rolling 10-second window
    """
    
    def __init__(self):
        super().__init__()
        
        # Data storage - deque for efficient append/pop operations
        self.max_samples = 400  # 10 seconds at ~40 Hz
        self.time_data = deque(maxlen=self.max_samples)
        self.ekg_data = deque(maxlen=self.max_samples)
        
        # Selected channel (0-11)
        self.selected_channel = 0
        
        # Setup matplotlib figure and canvas
        self.setup_plot()
        
        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)
    
    def setup_plot(self):
        """Initialize matplotlib figure and canvas"""
        # Create figure with tight layout
        self.figure = Figure(figsize=(12, 6), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        
        # Create single subplot for EKG display
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title(f'Real-time EKG - Channel {self.selected_channel}', fontsize=14, fontweight='bold')
        self.ax.set_xlabel('Time (seconds)')
        self.ax.set_ylabel('ADC Value (0-4095)')
        self.ax.grid(True, alpha=0.3)
        
        # Initialize empty line plot
        self.line, = self.ax.plot([], [], 'b-', linewidth=1.5)
        
        # Set initial axis limits
        self.ax.set_xlim(0, 10)  # 10 second window
        self.ax.set_ylim(0, 4095)  # 12-bit ADC range
        
        # Tight layout to prevent clipping
        self.figure.tight_layout()
    
    def add_data_point(self, channel_data):
        """
        Add new 12-channel data point to buffer
        Args: channel_data (list) - List of 12 processed channel values
        """
        if len(channel_data) != 12:
            return
        
        # Add timestamp and selected channel data
        current_time = time.time()
        channel_value = channel_data[self.selected_channel]
        
        self.time_data.append(current_time)
        self.ekg_data.append(channel_value)
        
        # Update plot if we have data
        if len(self.time_data) > 1:
            self.update_plot()
    
    def update_plot(self):
        """Update matplotlib plot with latest data"""
        if len(self.time_data) < 2:
            return
        
        # Convert deque to numpy arrays for plotting
        times = np.array(self.time_data)
        values = np.array(self.ekg_data)
        
        # Normalize time to show last 10 seconds (relative time)
        latest_time = times[-1]
        relative_times = times - latest_time + 10  # Last point at 10 seconds
        
        # Update line data
        self.line.set_data(relative_times, values)
        
        # Auto-scale Y axis to fit data with some padding
        if len(values) > 0:
            y_min, y_max = values.min(), values.max()
            y_padding = (y_max - y_min) * 0.1 if y_max > y_min else 200
            self.ax.set_ylim(y_min - y_padding, y_max + y_padding)
        
        # Keep X axis fixed to 10 second window
        self.ax.set_xlim(0, 10)
        
        # Redraw canvas
        self.canvas.draw()
    
    def change_channel(self, new_channel):
        """
        Change displayed channel and clear current data
        Args: new_channel (int) - Channel number (0-11)
        """
        self.selected_channel = new_channel
        
        # Clear current data for clean channel switch
        self.time_data.clear()
        self.ekg_data.clear()
        
        # Update plot title
        self.ax.set_title(f'Real-time EKG - Channel {self.selected_channel}', 
                         fontsize=14, fontweight='bold')
        
        # Clear and redraw
        self.line.set_data([], [])
        self.canvas.draw()

class MainWindow(QMainWindow):
    """
    Main application window containing control panel and EKG plot
    Coordinates WebSocket data reception and real-time visualization
    """
    
    def __init__(self):
        super().__init__()
        
        # Statistics tracking
        self.total_samples = 0
        self.start_time = time.time()
        
        self.init_ui()
        self.init_websocket()
    
    def init_ui(self):
        """Initialize user interface elements"""
        self.setWindowTitle('12-Channel EKG Real-time Visualizer')
        self.setGeometry(100, 100, 1200, 800)
        
        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Control panel at top
        control_panel = self.create_control_panel()
        main_layout.addWidget(control_panel)
        
        # EKG plot widget below control panel
        self.plot_widget = EKGPlotWidget()
        main_layout.addWidget(self.plot_widget)
        
        # Status update timer - updates UI statistics every second
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)  # Update every 1 second
    
    def create_control_panel(self):
        """Create and return control panel widget"""
        panel = QWidget()
        panel.setMaximumHeight(80)
        layout = QHBoxLayout(panel)
        
        # Channel selection dropdown
        channel_label = QLabel("Channel:")
        channel_label.setFont(QFont("Arial", 10, QFont.Bold))
        
        self.channel_combo = QComboBox()
        self.channel_combo.addItems([f"Ch{i}" for i in range(12)])
        self.channel_combo.currentIndexChanged.connect(self.on_channel_changed)
        self.channel_combo.setFont(QFont("Arial", 10))
        
        # Status labels
        self.connection_label = QLabel("Status: Starting...")
        self.connection_label.setFont(QFont("Arial", 10))
        
        self.stats_label = QLabel("Samples: 0 | Rate: 0 Hz | Format: HEX")
        self.stats_label.setFont(QFont("Arial", 10))
        
        # Add widgets to layout with spacing
        layout.addWidget(channel_label)
        layout.addWidget(self.channel_combo)
        layout.addStretch()  # Flexible space
        layout.addWidget(self.connection_label)
        layout.addStretch()
        layout.addWidget(self.stats_label)
        
        return panel
    
    def init_websocket(self):
        """Initialize WebSocket thread for ESP32 communication"""
        self.websocket_thread = WebSocketThread()
        
        # Connect Qt signals to handler methods (thread-safe communication)
        self.websocket_thread.data_received.connect(self.on_data_received)
        self.websocket_thread.connection_status.connect(self.on_connection_status)
        
        # Start WebSocket thread
        self.websocket_thread.start()
    
    def on_channel_changed(self, index):
        """
        Handle channel selection change
        Args: index (int) - Selected channel index (0-11)
        """
        self.plot_widget.change_channel(index)
    
    def on_data_received(self, channel_data):
        """
        Handle new 12-channel data from ESP32
        Args: channel_data (list) - List of 12 processed channel values
        Called via Qt signal from WebSocket thread
        """
        # Update plot with new data
        self.plot_widget.add_data_point(channel_data)
        
        # Update statistics
        self.total_samples += 1
    
    def on_connection_status(self, status):
        """
        Handle connection status updates
        Args: status (str) - Connection status message
        Called via Qt signal from WebSocket thread
        """
        self.connection_label.setText(f"Status: {status}")
    
    def update_status(self):
        """Update statistics display (called every second by timer)"""
        elapsed_time = time.time() - self.start_time
        sample_rate = self.total_samples / elapsed_time if elapsed_time > 0 else 0
        
        self.stats_label.setText(
            f"Samples: {self.total_samples} | Rate: {sample_rate:.1f} Hz | Format: HEX"
        )
    
    def closeEvent(self, event):
        """Handle application shutdown"""
        # Stop WebSocket thread gracefully
        if hasattr(self, 'websocket_thread'):
            self.websocket_thread.stop()
            self.websocket_thread.wait(3000)  # Wait up to 3 seconds
        
        event.accept()

def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("EKG Visualizer")
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    print("=== PyQt5 EKG Visualizer Started ===")
    print("Waiting for ESP32 connection on port 8765...")
    
    # Start Qt event loop
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()