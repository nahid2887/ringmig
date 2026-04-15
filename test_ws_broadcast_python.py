#!/usr/bin/env python3
"""Python websocket utility for conversation-list and notifications sockets.

This script is backend-developer friendly (no JS) and supports:
1) Listening to /ws/conversations/
2) Listening to /ws/notifications/
3) Optionally triggering a conversation-list broadcast by sending a
   `chat_message` on /ws/chat/<conversation_id>/

Example usage:

python test_ws_broadcast_python.py \
  --conversations-url "ws://10.10.13.27:8005/ws/conversations/?token=YOUR_TOKEN" \
  --notifications-url "ws://10.10.13.27:8005/ws/notifications/?token=YOUR_TOKEN" \
  --chat-url "ws://10.10.13.27:8005/ws/chat/1/?token=YOUR_TOKEN" \
  --chat-message "Broadcast test from Python" \
  --duration 60
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from datetime import datetime
from typing import Any, Optional

import websocket


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def pretty_json(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=True)
    except Exception:
        return raw


class SocketListener:
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url
        self._app: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = threading.Event()

    def on_open(self, ws: websocket.WebSocketApp) -> None:
        print(f"[{ts()}] [{self.name}] connected")
        self._connected.set()

    def on_message(self, ws: websocket.WebSocketApp, message: str) -> None:
        print(f"[{ts()}] [{self.name}] message:\n{pretty_json(message)}")

    def on_error(self, ws: websocket.WebSocketApp, error: Any) -> None:
        print(f"[{ts()}] [{self.name}] error: {error}")

    def on_close(
        self,
        ws: websocket.WebSocketApp,
        close_status_code: Optional[int],
        close_msg: Optional[str],
    ) -> None:
        print(f"[{ts()}] [{self.name}] closed: code={close_status_code}, msg={close_msg}")

    def start(self) -> None:
        self._app = websocket.WebSocketApp(
            self.url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )

        def _run() -> None:
            self._app.run_forever(ping_interval=0)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def wait_connected(self, timeout: float = 8.0) -> bool:
        return self._connected.wait(timeout)

    def close(self) -> None:
        if self._app:
            self._app.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)


def send_chat_message(chat_url: str, message: str) -> None:
    print(f"[{ts()}] [chat-trigger] connecting: {chat_url}")
    ws = websocket.create_connection(chat_url, timeout=10)
    try:
        payload = {
            "type": "chat_message",
            "message": message,
        }
        print(f"[{ts()}] [chat-trigger] sending chat_message")
        ws.send(json.dumps(payload))

        ws.settimeout(3)
        try:
            first_response = ws.recv()
            print(f"[{ts()}] [chat-trigger] response:\n{pretty_json(first_response)}")
        except Exception:
            print(f"[{ts()}] [chat-trigger] no immediate response (this can be normal)")
    finally:
        ws.close()
        print(f"[{ts()}] [chat-trigger] closed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Listen to websocket endpoints and optionally trigger broadcast."
    )
    parser.add_argument(
        "--conversations-url",
        required=True,
        help="Full ws://.../ws/conversations/?token=... URL",
    )
    parser.add_argument(
        "--notifications-url",
        required=False,
        help="Full ws://.../ws/notifications/?token=... URL",
    )
    parser.add_argument(
        "--chat-url",
        required=False,
        help="Full ws://.../ws/chat/<conversation_id>/?token=... URL to trigger broadcast",
    )
    parser.add_argument(
        "--chat-message",
        default="Broadcast test from Python backend script",
        help="Message body sent to chat socket when --chat-url is provided",
    )
    parser.add_argument(
        "--trigger-delay",
        type=float,
        default=3.0,
        help="Seconds to wait before sending --chat-message",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="How long to keep listeners alive (seconds)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    websocket.enableTrace(False)

    listeners = [SocketListener("conversations", args.conversations_url)]
    if args.notifications_url:
        listeners.append(SocketListener("notifications", args.notifications_url))

    for listener in listeners:
        print(f"[{ts()}] Starting {listener.name}: {listener.url}")
        listener.start()

    for listener in listeners:
        if not listener.wait_connected(timeout=10):
            print(f"[{ts()}] Warning: {listener.name} did not confirm connection in time")

    if args.chat_url:
        time.sleep(max(0, args.trigger_delay))
        send_chat_message(args.chat_url, args.chat_message)
    else:
        print(f"[{ts()}] No chat trigger configured. Listening only.")

    try:
        print(f"[{ts()}] Listening for {args.duration} seconds...")
        time.sleep(max(0, args.duration))
    except KeyboardInterrupt:
        print(f"[{ts()}] Interrupted by user")
    finally:
        for listener in listeners:
            listener.close()
        print(f"[{ts()}] Done")


if __name__ == "__main__":
    main()
