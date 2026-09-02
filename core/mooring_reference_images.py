"""Embedded mooring-station reference drawings supplied by the user.

These drawings are reference overlays only; engineering coordinates must be
validated against dimensions/calibration before being used by the solver.
"""
import base64
from io import BytesIO
from PIL import Image

FWD_MOORING_PLAN_WEBP_B64 = 'UklGR...'