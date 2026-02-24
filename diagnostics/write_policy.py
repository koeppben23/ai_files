from __future__ import annotations

import importlib

_module = importlib.import_module("governance.entrypoints.write_policy")
_module = importlib.reload(_module)

globals().update({k: getattr(_module, k) for k in dir(_module) if not k.startswith("__")})
