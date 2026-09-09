import os
import sys
import threading
from pathlib import Path
from werkzeug.serving import make_server

_server = None


def start(root_dir: str, port: int = 5000):
    global _server
    root = Path(root_dir)
    sys.path.insert(0, str(root))
    os.environ["PATH"] = os.environ.get("PATH", "")
    import app
    _server = make_server("127.0.0.1", int(port), app.app, threaded=True)
    _server.serve_forever()


def stop():
    global _server
    if _server is not None:
        _server.shutdown()
        _server = None
