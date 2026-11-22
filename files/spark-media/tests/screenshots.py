"""Screenshots of the new screens with invented music and photos, to look at the interface
without a desktop. CI runs it under Xvfb and keeps the PNGs; it also runs on Windows.

    xvfb-run -a -s "-screen 0 1280x800x24" python3 tests/screenshots.py OUT [en|fr]
"""

import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from PIL import Image, ImageDraw, ImageGrab  # noqa: E402

COLOURS = ['#ff4d8d', '#22d8ff', '#3de8c8', '#f4c95d', '#8a6cff', '#ff8a3d', '#5ad16a',
           '#d04dff', '#4d7cff', '#ff5a5a', '#c8e83d', '#3dc8e8']
ARTISTS = [('Les Ondes Courtes', ['Signal faible', 'Bruit blanc']), ('Night Bus', ['Last Stop']),
           ('Marie Delorme', ['Hiver', 'Printemps', 'Nord']), ('Quartz', ['Glass']),
           ('The Static', ['Interference', 'Carrier Wave']), ('Vélo Club', ['Tour'])]


def grab(root, path):
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    kwargs = {} if os.name == 'nt' else {'xdisplay': os.environ.get('DISPLAY')}
    ImageGrab.grab(bbox=(x, y, x + w, y + h), **kwargs).save(path)
    print("wrote", path)


def settle(root, ms):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        root.update()
        time.sleep(0.01)


def fake_library(home):
    """A library index and covers that look real, for files that exist but are empty."""
    from sparkmedia import musiclib
    music = os.path.join(home, 'Music')
    lib = musiclib.Library()
    songs = []
    n = 0
    for a, (artist, albums) in enumerate(ARTISTS):
        for b, album in enumerate(albums):
            for t in range(1, 8 + (a + b) % 5):
                n += 1
                path = os.path.join(music, artist, album, f'{t:02d} Track {t}.flac')
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, 'wb').close()
                st = os.stat(path)
                songs.append({'path': path, 'mtime': st.st_mtime, 'size': st.st_size,
                              'title': f"{album} {['Intro', 'Light', 'Rain', 'Dust', 'Echo', 'Wire', 'Halo', 'Drift', 'Static', 'Last', 'Home', 'Field'][t % 12]}",
                              'artist': artist, 'albumartist': artist, 'album': album,
                              'track': t, 'disc': 0, 'year': 2000 + (a * 3 + b) % 24,
                              'genre': '', 'length': 150.0 + (n * 37) % 200})
    lib.update(songs)
    lib.roots = [music]
    os.makedirs(os.path.join(music, 'Playlists'))
    for name in ('Road trip', 'Focus', 'Sunday'):
        from sparkmedia import playlists
        path = os.path.join(music, 'Playlists', name + '.m3u8')
        playlists.write(path, [s['path'] for s in songs[::7]])
        lib.playlists.append(path)
    for i, album in enumerate(lib.albums()):
        image = Image.new('RGB', (320, 320), COLOURS[i % len(COLOURS)])
        draw = ImageDraw.Draw(image)
        for k in range(0, 320, 24):
            draw.line((0, k + i * 5 % 24, 320, k), fill='#04090b', width=3)
        musiclib.store_cover(album.cover_id, image)
    lib.save()
    return songs


def main():
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else 'screenshots')
    lang = sys.argv[2] if len(sys.argv) > 2 else 'en'
    os.makedirs(out, exist_ok=True)
    tmp = tempfile.mkdtemp()
    home = os.path.join(tmp, 'home')
    os.makedirs(home)
    os.environ.update(HOME=home, USERPROFILE=home, XDG_CACHE_HOME=os.path.join(tmp, 'cache'),
                      XDG_CONFIG_HOME=os.path.join(tmp, 'config'),
                      XDG_STATE_HOME=os.path.join(tmp, 'state'), SPARK_LANG=lang,
                      SPARK_MEDIA_REDUCED_MOTION='1', SPARK_MEDIA_AUDIO_SINK='fakesink')
    songs = fake_library(home)
    import fixtures
    from sparkmedia.app import App
    app = App([], 'music')
    root = app.root
    root.geometry('1180x760+0+0')
    settle(root, 1500)
    view = app.view
    view._tab('albums')
    settle(root, 800)
    grab(root, os.path.join(out, f'{lang}-music-albums.png'))
    view._tab('artists')
    settle(root, 300)
    grab(root, os.path.join(out, f'{lang}-music-artists.png'))
    view._tab('songs')
    app.play_songs([s['path'] for s in songs], 3)
    view._after_play()
    settle(root, 500)
    grab(root, os.path.join(out, f'{lang}-music-songs.png'))
    album = app.library().albums()[4]
    view.open_page('album', album.key)
    settle(root, 500)
    grab(root, os.path.join(out, f'{lang}-music-album.png'))
    view._tab('playlists')
    view.list.on_activate(0)
    settle(root, 300)
    grab(root, os.path.join(out, f'{lang}-music-playlist.png'))
    app.show_now_playing()
    settle(root, 600)
    grab(root, os.path.join(out, f'{lang}-music-now-playing.png'))

    pics = os.path.join(home, 'Pictures')
    os.makedirs(pics)
    photo = os.path.join(pics, 'lake.jpg')
    image = Image.linear_gradient('L').resize((1600, 1067)).convert('RGB')
    draw = ImageDraw.Draw(image)
    draw.rectangle((200, 600, 1400, 1067), fill='#1f6a66')
    draw.ellipse((1100, 150, 1350, 400), fill='#f4c95d')
    image = Image.blend(image, Image.new('RGB', image.size, '#556070'), 0.45)
    image.save(photo, quality=92)
    dng = fixtures.make_dng(os.path.join(pics, 'IMG_2041.dng'), orientation=1,
                            raw_size=(600, 400), preview_size=(300, 200))
    app.open_path(photo)
    settle(root, 600)
    viewer = app.view
    viewer.start_edit()
    viewer.set_ratio('3:2')
    viewer.edits.crop = (300, 200, 1200, 800)
    viewer.set_enhance(True)
    settle(root, 600)
    grab(root, os.path.join(out, f'{lang}-photo-edit.png'))
    viewer.cancel_edit()
    viewer.show(viewer.files.index(dng))
    settle(root, 2500)
    grab(root, os.path.join(out, f'{lang}-photo-raw.png'))
    app._on_close()
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
