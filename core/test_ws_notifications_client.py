import json
import os
import sys
import time

import websocket


def on_open(ws):
    print('connected')


def on_message(ws, message):
    print(message)
    try:
        payload = json.loads(message)
        if payload.get('type') == 'booking_reminder_notification':
            print('booking_reminder_notification_received')
            ws.close()
    except Exception:
        pass


def on_error(ws, error):
    print(f'error: {error}')


def on_close(ws, close_status_code, close_msg):
    print(f'closed: {close_status_code} {close_msg}')


if __name__ == '__main__':
    url = os.environ.get('WS_URL')
    if not url:
        print('WS_URL is required')
        sys.exit(1)

    websocket.enableTrace(False)
    app = websocket.WebSocketApp(
        url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    app.run_forever(ping_interval=0)
