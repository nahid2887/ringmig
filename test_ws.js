const WebSocket = require('ws');

const TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzc3NjMwNTQxLCJpYXQiOjE3NzUwMzg1NDEsImp0aSI6ImY5NGE1MTAyMWUzMzRiY2Y5MTY0YWFhMjE2MzY5NGQyIiwidXNlcl9pZCI6IjI0In0.HeAKihZ1xhkm8ugIehrnmdz2PFHV4Zq7009P8uP2LVw";
const WS_URL = `ws://localhost:8005/ws/availability/my-availability/?token=${TOKEN}`;

console.log("Connecting to:", WS_URL);

const ws = new WebSocket(WS_URL);

ws.on('open', () => {
    console.log("✓ WebSocket connected!");
});

ws.on('message', (data) => {
    try {
        const message = JSON.parse(data);
        console.log("\n✓ Received message:");
        console.log(JSON.stringify(message, null, 2));
    } catch (e) {
        console.log("Received (raw):", data);
    }
});

ws.on('error', (error) => {
    console.error("✗ WebSocket error:", error.message);
});

ws.on('close', (code) => {
    console.log("✗ WebSocket closed with code:", code);
});

// Keep connection open for 15 seconds
setTimeout(() => {
    console.log("\nClosing connection...");
    ws.close();
}, 15000);
