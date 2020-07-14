import sys as _sys
import os as _os
_sys.path.append(_os.path.join(_os.path.abspath(_os.path.dirname(__file__)), '..', 'ntx_protobuf'))  # Python yuck

from .ntx_stt import NewtonEngine, to_strings
