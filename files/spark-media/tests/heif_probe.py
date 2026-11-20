"""Which HEIF decoders libheif has here: run inside the SparkOS image by image_report.sh."""
import ctypes
import ctypes.util
import importlib

for name in ('dbus', 'gi.repository.Gio'):
    try:
        importlib.import_module(name)
        print(f"module {name}: yes")
    except Exception as exc:      # noqa: BLE001
        print(f"module {name}: no ({type(exc).__name__}: {exc})")
path = ctypes.util.find_library('heif')
print("libheif:", path)
if path:
    lib = ctypes.CDLL(path)
    lib.heif_get_version.restype = ctypes.c_char_p
    print("libheif version:", lib.heif_get_version().decode())
    if hasattr(lib, 'heif_init'):
        lib.heif_init(None)
    for code, label in ((1, 'HEVC (HEIC)'), (2, 'AVC'), (3, 'JPEG'), (4, 'AV1 (AVIF)'), (5, 'VVC')):
        print(f"heif decoder {label}: {'yes' if lib.heif_have_decoder_for_format(code) else 'no'}")
