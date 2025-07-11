#!/usr/bin/env python3
"""
Single Channel PyQt5 EKG Visualizer
Receives single channel hex data from ESP32 via WebSocket (100ms updates)
Real-time plotting with fixed Y-axis and 10-second window
"""

import sys
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
                            QHBoxLayout, QWidget, QLabel)
from PyQt5.QtCore import QTimer, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QFont

import websockets

class DataProcessor:
    """Handle single channel EKG data processing and validation"""
    
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
    def parse_hex_data(hex_data):
        """
        Parse single line of hex data to processed values
        Args: hex_data (str) - "800,801,802,803,..."
        Returns: list - Processed decimal values
        """
        try:
            hex_values = hex_data.strip().split(',')
            
            # Convert hex to decimal and process each value
            processed_values = []
            for hex_val in hex_values:
                if hex_val.strip():  # Skip empty values
                    decimal_val = int(hex_val, 16)
                    processed_val = DataProcessor.process_value(decimal_val)
                    processed_values.append(processed_val)
            
            return processed_values
        
        except (ValueError, AttributeError):
            return []

class WebSocketThread(QThread):
    """
    WebSocket client thread for receiving ESP32 single channel data
    Optimized for 100ms real-time updates
    """
    # Qt signals for thread-safe communication
    data_received = pyqtSignal(list)  # Emits list of single channel values
    connection_status = pyqtSignal(str)  # Emits connection status
    sample_stats = pyqtSignal(int, int)  # Emits (samples_count, data_length)
    
    def __init__(self):
        super().__init__()
        self.server_ip = "0.0.0.0"
        self.server_port = 8765
        self.running = True
    
    def run(self):
        """Main thread execution - runs WebSocket server"""
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self.start_server())
        except Exception as e:
            self.connection_status.emit(f"Server Error: {e}")
        finally:
            loop.close()
    
    async def start_server(self):
        """Start WebSocket server for single channel data"""
        self.connection_status.emit("Server Starting...")
        
        async with websockets.serve(
            self.handle_client, 
            self.server_ip, 
            self.server_port,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5
        ):
            self.connection_status.emit(f"Server Running on {self.server_ip}:{self.server_port}")
            
            # Keep server running
            while self.running:
                await asyncio.sleep(0.1)
    
    async def handle_client(self, websocket, path):
        """
        Handle ESP32 client connection for single channel data
        Optimized for 100ms batch processing
        """
        client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
        self.connection_status.emit(f"ESP32 Connected: {client_ip}")
        
        try:
            async for message in websocket:
                if isinstance(message, str) and message.strip():
                    # Parse single line of hex data (100ms batch)
                    processed_data = DataProcessor.parse_hex_data(message)
                    
                    if processed_data:
                        # Emit data and statistics
                        self.data_received.emit(processed_data)
                        self.sample_stats.emit(len(processed_data), len(message))
                    
                    # Send acknowledgment
                    try:
                        await websocket.send("OK")
                    except:
                        return  # Connection lost
        
        except websockets.exceptions.ConnectionClosed:
            self.connection_status.emit(f"ESP32 Disconnected: {client_ip}")
        except Exception as e:
            self.connection_status.emit(f"Connection Error: {e}")
    
    def stop(self):
        """Stop the WebSocket thread"""
        self.running = False

class SingleChannelPlotWidget(QWidget):
    """
    Single channel EKG plot widget with real-time 100ms updates
    Fixed Y-axis (0-4095) and 10-second rolling window
    """
    
    def __init__(self):
        super().__init__()
        
        # Data storage for 10-second window at 100ms updates
        self.max_samples = 8600  # 10 seconds: 860 SPS * 10 = 8600 samples
        self.time_data = deque(maxlen=self.max_samples)
        self.ekg_data = deque(maxlen=self.max_samples)
        
        # Setup matplotlib plot
        self.setup_plot()
        
        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)
    
    def setup_plot(self):
        """Initialize matplotlib figure with fixed settings"""
        # Create figure
        self.figure = Figure(figsize=(14, 8), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        
        # Single subplot for EKG
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title('Single Channel EKG Real-time (A1) - 100ms Updates', 
                         fontsize=16, fontweight='bold')
        self.ax.set_xlabel('Time (seconds)', fontsize=12)
        self.ax.set_ylabel('ADC Value', fontsize=12)
        self.ax.grid(True, alpha=0.3)
        
        # Initialize empty line
        self.line, = self.ax.plot([], [], 'b-', linewidth=1.2, alpha=0.8)
        
        # Fixed axis limits
        self.ax.set_xlim(0, 10)      # 10 second window
        self.ax.set_ylim(0, 4095)    # Fixed 12-bit ADC range
        
        # Enhance plot appearance
        self.ax.set_facecolor('#f8f9fa')
        self.figure.patch.set_facecolor('white')
        self.figure.tight_layout()
    
    def add_data_batch(self, values):
        """
        Add batch of values from 100ms ESP32 transmission
        Args: values (list) - List of processed decimal values
        """
        current_time = time.time()
        
        # Add each value with interpolated timestamp for smooth plotting
        for i, value in enumerate(values):
            # Interpolate timestamps within 100ms batch
            timestamp = current_time + (i * 0.1 / len(values))  # Spread over 100ms
            
            self.time_data.append(timestamp)
            self.ekg_data.append(value)
        
        # Update plot immediately for real-time visualization
        if len(self.time_data) > 1:
            self.update_plot()
    
    def update_plot(self):
        """Update matplotlib plot with latest data - optimized for speed"""
        if len(self.time_data) < 2:
            return
        
        # Convert to numpy arrays for efficient plotting
        times = np.array(self.time_data)
        values = np.array(self.ekg_data)
        
        # Normalize time to 10-second window (relative time)
        latest_time = times[-1]
        relative_times = times - latest_time + 10
        
        # Update line data
        self.line.set_data(relative_times, values)
        
        # Keep fixed axis limits (no auto-scaling for stability)
        self.ax.set_xlim(0, 10)
        self.ax.set_ylim(0, 4095)
        
        # Fast redraw
        self.canvas.draw_idle()

class MainWindow(QMainWindow):
    """
    Main application window for single channel EKG visualization
    Real-time 100ms updates with statistics monitoring
    """
    
    def __init__(self):
        super().__init__()
        
        # Statistics tracking
        self.total_batches = 0
        self.total_samples = 0
        self.start_time = time.time()
        
        self.init_ui()
        self.init_websocket()
    
    def init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle('Single Channel EKG Real-time Visualizer (100ms Updates)')
        self.setGeometry(100, 100, 1400, 900)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Control panel
        control_panel = self.create_control_panel()
        main_layout.addWidget(control_panel)
        
        # EKG plot
        self.plot_widget = SingleChannelPlotWidget()
        main_layout.addWidget(self.plot_widget)
        
        # Update timer for statistics
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_statistics)
        self.status_timer.start(1000)  # Update every second
    
    def create_control_panel(self):
        """Create control panel with status information"""
        panel = QWidget()
        panel.setMaximumHeight(70)
        layout = QHBoxLayout(panel)
        
        # Channel info
        channel_label = QLabel("Channel: A1 (Single)")
        channel_label.setFont(QFont("Arial", 11, QFont.Bold))
        channel_label.setStyleSheet("color: #2c3e50; background-color: #ecf0f1; padding: 5px; border-radius: 3px;")
        
        # Connection status
        self.connection_label = QLabel("Status: Starting...")
        self.connection_label.setFont(QFont("Arial", 10))
        
        # Statistics
        self.stats_label = QLabel("Batches: 0 | Samples: 0 | Rate: 0 Hz | Format: HEX")
        self.stats_label.setFont(QFont("Arial", 10))
        
        # Data info
        self.data_label = QLabel("Last Batch: 0 samples | Data Length: 0")
        self.data_label.setFont(QFont("Arial", 10))
        
        # Layout with spacing
        layout.addWidget(channel_label)
        layout.addStretch()
        layout.addWidget(self.connection_label)
        layout.addStretch()
        layout.addWidget(self.stats_label)
        layout.addStretch()
        layout.addWidget(self.data_label)
        
        return panel
    
    def init_websocket(self):
        """Initialize WebSocket thread"""
        self.websocket_thread = WebSocketThread()
        
        # Connect signals
        self.websocket_thread.data_received.connect(self.on_data_received)
        self.websocket_thread.connection_status.connect(self.on_connection_status)
        self.websocket_thread.sample_stats.connect(self.on_sample_stats)
        
        # Start thread
        self.websocket_thread.start()
    
    def on_data_received(self, values):
        """Handle new batch of single channel data"""
        # Update plot with new batch
        self.plot_widget.add_data_batch(values)
        
        # Update statistics
        self.total_batches += 1
        self.total_samples += len(values)
    
    def on_connection_status(self, status):
        """Handle connection status updates"""
        self.connection_label.setText(f"Status: {status}")
    
    def on_sample_stats(self, sample_count, data_length):
        """Handle sample statistics from last batch"""
        self.data_label.setText(f"Last Batch: {sample_count} samples | Data Length: {data_length}")
    
    def update_statistics(self):
        """Update statistics display"""
        elapsed_time = time.time() - self.start_time
        
        if elapsed_time > 0:
            batch_rate = self.total_batches / elapsed_time
            sample_rate = self.total_samples / elapsed_time
        else:
            batch_rate = sample_rate = 0
        
        self.stats_label.setText(
            f"Batches: {self.total_batches} | Samples: {self.total_samples} | "
            f"Rate: {sample_rate:.1f} Hz | Batch Rate: {batch_rate:.1f}/s | Format: HEX"
        )
    
    def closeEvent(self, event):
        """Handle application shutdown"""
        if hasattr(self, 'websocket_thread'):
            self.websocket_thread.stop()
            self.websocket_thread.wait(3000)
        event.accept()

def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("Single Channel EKG Visualizer")
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    print("=== Single Channel EKG Visualizer Started ===")
    print("Optimized for 100ms real-time updates")
    print("Fixed Y-axis: 0-4095 | Window: 10 seconds")
    print("Waiting for ESP32 connection on port 8765...")
    
    # Start application
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()