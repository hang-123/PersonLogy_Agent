import os

_orig_os_mkdir = os.mkdir

def _mkdir(path, mode=0o777, *args, **kwargs):
    if mode == 0o700:
        mode = 0o755
    return _orig_os_mkdir(path, mode, *args, **kwargs)

os.mkdir = _mkdir
