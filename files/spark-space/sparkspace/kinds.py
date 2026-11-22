"""What kind of file something is, for the Types view and the treemap's colours. By the name's
extension, and "games" by where it is (a Steam library, ~/Games, Heroic, Lutris)."""

import os

KINDS = ('video', 'games', 'models', 'archives', 'apps', 'images', 'audio', 'documents', 'other')

_EXT = {}
for _kind, _names in {
    'video': 'mp4 mkv webm avi mov m4v wmv flv mpg mpeg ts m2ts mts 3gp ogv vob',
    'audio': 'mp3 flac ogg oga opus wav m4a aac wma aiff aif alac ape mka mid midi',
    'images': 'jpg jpeg png gif webp bmp tif tiff heic heif avif svg raw cr2 cr3 nef arw dng '
              'orf rw2 raf psd xcf kra ico',
    'archives': 'zip 7z rar tar gz tgz bz2 tbz2 xz txz zst tzst lz lzma cab iso img qcow2 '
                'vdi vmdk vhd vhdx wim dmg',
    'models': 'gguf ggml safetensors ckpt pth onnx tflite',
    'apps': 'appimage flatpak flatpakref rpm deb exe msi msix apk jar run bin',
    'documents': 'pdf doc docx odt ods odp xls xlsx ppt pptx txt md rtf epub csv json xml '
                 'html htm tex',
}.items():
    for _e in _names.split():
        _EXT[_e] = _kind

# folder names that mean "this is a game library"; matched case-insensitively
GAME_DIRS = {'steamapps', 'steamlibrary', 'games', 'heroic', 'gog games', 'epic games',
             'lutris', 'xboxgames', 'riot games', 'ea games', 'ubisoft game launcher'}


def kind_of(name: str, in_games: bool = False) -> str:
    if in_games:
        return 'games'
    _, ext = os.path.splitext(name)
    ext = ext[1:].lower()
    if ext in ('gz', 'xz', 'bz2', 'zst') and name.lower().endswith(('.tar.' + ext)):
        return 'archives'
    return _EXT.get(ext, 'other')


def is_game_dir(name: str) -> bool:
    return name.lower() in GAME_DIRS
