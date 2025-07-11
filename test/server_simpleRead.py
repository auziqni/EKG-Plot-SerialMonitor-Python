#!/usr/bin/env python3
"""
WebSocket server adapted for ESP32 12-channel EKG text data
Handles variable sample count and bracket format from ESP32

menerima teks data EKG dari ESP32
Expected format: [d1a0,d1a1,d1a2,d1a3,d2a0,d2a1,d2a2,d2a3,d3a0,d3a1,d3a2,d3a3],...
"""

import asyncio
import websockets
import time
import re
from datetime import datetime

async def handle(websocket, path):
    client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
    print(f"ESP32 EKG connected from {client_ip}")
    print(f"Connection time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        async for message in websocket:
            try:
                # Generate timestamp for this batch
                timestamp = int(time.time())
                
                if isinstance(message, str) and message.strip():
                    # Parse EKG text data format: [d1a0,d1a1,d1a2,d1a3,d2a0,d2a1,d2a2,d2a3,d3a0,d3a1,d3a2,d3a3],...
                    
                    # Count total sample sets (bracket groups)
                    bracket_pattern = r'\[([^\]]+)\]'
                    matches = re.findall(bracket_pattern, message)
                    
                    if matches:
                        # Parse sample data
                        total_sets = len(matches)
                        channels = 12  # Known: 12 channels (3 devices × 4 channels)
                        
                        # Parse first set to verify channel count
                        first_set = matches[0].split(',')
                        actual_channels = len(first_set)
                        
                        # Calculate samples per channel
                        samples_per_channel = total_sets
                        
                        # Data validation
                        if actual_channels == channels:
                            print(f"Timestamp: {timestamp}, Channels: {channels}, Samples: {samples_per_channel} per channel, Total sets: {total_sets}")
                            
                            # Optional: Parse and show sample data snippet
                            sample_values = [int(val) for val in first_set]
                            print(f"First set values: {sample_values[:6]}...{sample_values[-3:]} (showing first 6 and last 3)")
                            
                            # Optional: Calculate basic statistics
                            all_values = []
                            for match in matches[:5]:  # Sample first 5 sets for stats
                                values = [int(val) for val in match.split(',')]
                                all_values.extend(values)
                            
                            if all_values:
                                avg_value = sum(all_values) / len(all_values)
                                min_value = min(all_values)
                                max_value = max(all_values)
                                print(f"Sample stats - Avg: {avg_value:.1f}, Min: {min_value}, Max: {max_value}")
                            
                        else:
                            print(f"Warning: Expected {channels} channels, got {actual_channels}")
                            print(f"Timestamp: {timestamp}, Sets: {total_sets}, Channels per set: {actual_channels}")
                    
                    else:
                        # Handle non-bracket format (fallback)
                        data_points = message.split(',')
                        print(f"Timestamp: {timestamp}, Raw data points: {len(data_points)}")
                        print(f"Sample: {message[:50]}...")
                
                else:
                    print(f"Timestamp: {timestamp}, Empty or invalid message received")
                
                # Send acknowledgment back to ESP32
                try:
                    await websocket.send("OK")
                except websockets.exceptions.ConnectionClosed:
                    print(f"Timestamp: {timestamp}, Connection closed while sending acknowledgment")
                    return
                except Exception as send_error:
                    print(f"Timestamp: {timestamp}, Error sending acknowledgment: {send_error}")
                    return
                
            except websockets.exceptions.ConnectionClosed:
                print(f"Timestamp: {int(time.time())}, ESP32 connection closed gracefully")
                return
            except OSError as os_error:
                print(f"Timestamp: {int(time.time())}, Network error: {os_error}")
                print("ESP32 likely disconnected - waiting for reconnection...")
                return
            except Exception as e:
                timestamp = int(time.time())
                print(f"Timestamp: {timestamp}, Error parsing data: {e}")
                print(f"Message preview: {str(message)[:100]}...")
                
                # Still try to send acknowledgment
                try:
                    await websocket.send("ERROR")
                except:
                    print("Failed to send error acknowledgment - connection likely lost")
                    return
    
    except websockets.exceptions.ConnectionClosed:
        print(f"Connection with {client_ip} closed")
    except Exception as handler_error:
        print(f"Connection handler failed for {client_ip}: {handler_error}")
    finally:
        print(f"ESP32 {client_ip} disconnected at {datetime.now().strftime('%H:%M:%S')}")
        print("-" * 50)

async def main():
    print("=== ESP32 EKG WebSocket Server ===")
    print("Adapted for 12-channel text data format")
    print("Expected format: [d1a0,d1a1,d1a2,d1a3,d2a0,d2a1,d2a2,d2a3,d3a0,d3a1,d3a2,d3a3],...")
    print("Enhanced error handling for Windows network issues")
    print()
    
    # Enhanced server with better error handling
    async with websockets.serve(
        handle, 
        "0.0.0.0", 
        8765,
        ping_interval=30,      # Send ping every 30 seconds
        ping_timeout=10,       # Wait 10 seconds for pong
        close_timeout=5        # Wait 5 seconds for close
    ):
        print("Server running on 0.0.0.0:8765")
        print("Waiting for ESP32 EKG connection...")
        print("Server will auto-recover from connection drops")
        print("-" * 50)
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Server error: {e}")