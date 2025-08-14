import json, os, threading

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "state.json")
_lock = threading.Lock()

def load(path: str = _DEFAULT_PATH):
    if not os.path.exists(path):
        return {"sent": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save(state, path: str = _DEFAULT_PATH):
    with _lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

def already_sent(state, key: str) -> bool:
    return key in state.get("sent", [])

def mark_sent(state, key: str):
    if "sent" not in state: state["sent"] = []
    state["sent"].append(key)
