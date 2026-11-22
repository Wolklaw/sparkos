"""Spark Scan: scanning for SparkOS. It finds the scanners SANE knows (USB and network),
previews the glass, lets you drag out the part to keep, scans page after page, and saves one
PDF (searchable with Tesseract, if you want) or an image per page to Documents/Scans.
Everything runs on this computer; nothing is uploaded.
"""

APP_NAME = "Spark Scan"
APP_SLUG = "spark-scan"          # command, folders, log names
APP_CLASS = "SparkScan"          # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkScan"
VERSION = "1.1.0"

DPI_CHOICES = (150, 300, 600)
MODES = ("color", "gray", "bw")          # colour, grey, black and white
FORMATS = ("pdf", "png", "jpg")
PREVIEW_DPI = 75
JPEG_QUALITY = 85                        # pages inside a PDF
JPEG_QUALITY_FILE = 92                   # a page saved as its own .jpg
SCANS_FOLDER = "Scans"                   # inside the user's Documents folder
