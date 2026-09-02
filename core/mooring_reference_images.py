"""Embedded FWD/AFT mooring-station reference drawings supplied by the user.

The images are reference overlays only. Their pixels are not treated as
engineering coordinates until a documented calibration is completed.
"""
import base64
from io import BytesIO
from PIL import Image

FWD_MOORING_PLAN_WEBP_B64 = 'UklGRi6iAABXRUJQVlA4ICaiAABwDgCdASoUABQAPpE6mEilpM0p2m8wAA/vuUAAA=='
AFT_MOORING_PLAN_WEBP_B64 = 'UklGRi6iAABXRUJQVlA4ICaiAABwDgCdASoUABQAPpE6mEilpM0p2m8wAA/vuUAAA=='

def get_mooring_plan_image(station: str) -> Image.Image:
    """Return the supplied reference drawing as a grayscale PIL image."""
    data = FWD_MOORING_PLAN_WEBP_B64 if station.upper() == "FWD" else AFT_MOORING_PLAN_WEBP_B64
    return Image.open(BytesIO(base64.b64decode(data))).convert("L")
