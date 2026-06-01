import json
import dbm


class Database:
    def __init__(self, path="main.db"):
        self.path = path

    def __enter__(self):
        self.db = dbm.open(self.path, "c")
        return self

    def __exit__(self, *args, **kwargs):
        self.db.close()
        return True

    # Convenience methods that handle JSON
    def get(self, key: str):
        raw = self.db.get(key.encode())
        if raw is None:
            return None
        return json.loads(raw.decode())

    def put(self, key: str, value: dict):
        self.db[key.encode()] = json.dumps(value).encode()

    def __getitem__(self, key: str):
        return self.get(key)

    def __setitem__(self, key: str, value: dict):
        self.put(key, value)
