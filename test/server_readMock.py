import asyncio
import websockets

async def handle(websocket, path):
    print("ESP32 connected!")
    
    async for message in websocket:
        print(f"Data received: {len(message.split(','))} points")
        print(f"Sample: {message[:30]}...")
        await websocket.send("OK")

async def main():
    async with websockets.serve(handle, "0.0.0.0", 8765):
        print("Server running on port 8765")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())