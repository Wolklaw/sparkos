"""Spark Media: the SparkOS app for photos, videos and music. It opens what you double-click,
plays a folder in order, and browses Pictures, Videos and Music. Everything runs on this
computer; nothing is uploaded.
"""

APP_NAME = "Spark Media"
APP_SLUG = "spark-media"         # command, folders, log names
APP_CLASS = "SparkMedia"         # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkMedia"
VERSION = "1.2.0"

KINDS = ("photo", "video", "music")

# What each kind opens, by file extension. Pillow reads the photos (libheif the HEIC and AVIF
# ones, LibRaw the RAWs); GStreamer plays the rest with whatever decoders the system has.
PHOTO_EXT = frozenset("""
    jpg jpeg jpe jfif png apng gif webp bmp dib tif tiff ico cur avif heic heif hif tga ppm pgm pbm
    pnm pcx qoi dds psd
    cr2 cr3 crw nef nrw arw srf sr2 dng raf orf rw2 pef srw rwl 3fr iiq x3f
""".split())             # the last line: camera RAW (sparkmedia/raw.py)
VIDEO_EXT = frozenset("""
    mp4 m4v mkv webm avi mov qt wmv asf flv mpg mpeg mpe vob ts m2ts mts 3gp 3g2 ogv divx
""".split())
MUSIC_EXT = frozenset("""
    mp3 flac ogg oga opus m4a m4b aac wav wave wma aif aiff aifc mka wv ape mpc ac3 dts amr spx
""".split())
