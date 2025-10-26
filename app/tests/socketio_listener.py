import json

import socketio


def main() -> None:
    sio = socketio.Client()

    @sio.on("part_location_updated")
    def on_part(data):
        print("part_location_updated:", json.dumps(data))
        sio.disconnect()

    @sio.on("scan_update")
    def on_scan(data):
        print("scan_update:", json.dumps(data))
        sio.disconnect()

    sio.connect("http://127.0.0.1:8501", transports=["websocket"])
    sio.wait()


if __name__ == "__main__":
    main()
