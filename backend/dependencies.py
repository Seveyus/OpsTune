from fastapi import Depends

def get_config():
    from .config import config
    return config
