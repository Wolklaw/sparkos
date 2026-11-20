"""Spark Media's words. English first; French (Quebec, "vous") below with the same keys.
Status lines and tab names are written in capitals here because that's how they show;
buttons are put in capitals by the button itself."""

from typing import Dict

EN: Dict[str, str] = {
    # what's in the library
    'kind.photo': "PHOTOS", 'kind.video': "VIDEOS", 'kind.music': "MUSIC",
    'kind.photo.files': "photos", 'kind.video.files': "videos", 'kind.music.files': "music files",
    'tab.artists': "ARTISTS", 'tab.albums': "ALBUMS", 'tab.songs': "SONGS",
    'tab.playlists': "PLAYLISTS",
    'count.song': "{n} song", 'count.songs': "{n} songs",
    'count.album': "{n} album", 'count.albums': "{n} albums",
    'time.minutes': "{n} min", 'time.hours_minutes': "{h} h {m} min",

    # buttons
    'btn.open_files': "Open files", 'btn.open_folder': "Open folder", 'btn.play_all': "Play all",
    'btn.slideshow': "Slideshow", 'btn.library': "Library", 'btn.by_folder': "By folder",
    'btn.library_folders': "Folders", 'btn.play': "Play", 'btn.shuffle': "Shuffle",
    'btn.add_queue': "Add to queue", 'btn.add_playlist': "Add to playlist",
    'btn.new_playlist': "New playlist", 'btn.delete': "Delete", 'btn.ok': "OK",
    'btn.cancel': "Cancel", 'btn.done': "Done",

    # button hints
    'tip.back': "Back", 'tip.prev': "Previous", 'tip.next': "Next", 'tip.play': "Play or pause",
    'tip.mute': "Mute", 'tip.fullscreen': "Full screen", 'tip.subtitles': "Subtitles",
    'tip.audio': "Audio track", 'tip.repeat': "Repeat", 'tip.shuffle': "Shuffle",
    'tip.trash': "Move to Trash", 'tip.slideshow': "Slideshow", 'tip.edit': "Edit",
    'tip.rotate': "Rotate", 'tip.zoom_in': "Zoom in", 'tip.zoom_out': "Zoom out",
    'tip.fit': "Fit", 'tip.rotate_left': "Rotate left", 'tip.rotate_right': "Rotate right",

    # right-click menus
    'menu.open': "Open", 'menu.play': "Play", 'menu.shuffle': "Shuffle", 'menu.play_next': "Play next",
    'menu.add_queue': "Add to queue", 'menu.add_playlist': "Add to playlist",
    'menu.new_playlist': "New playlist…", 'menu.go_album': "Go to album",
    'menu.go_artist': "Go to artist", 'menu.show_folder': "Show in folder",
    'menu.move_up': "Move up", 'menu.move_down': "Move down",
    'menu.remove_queue': "Remove from queue", 'menu.remove_playlist': "Remove from playlist",
    'menu.delete_playlist': "Delete playlist",

    # status line
    'status.ready': "READY", 'status.went_wrong': "SOMETHING WENT WRONG",
    'status.playing': "PLAYING", 'status.paused': "PAUSED", 'status.finished': "FINISHED",
    'status.play_error': "PLAYBACK ERROR", 'status.volume': "VOLUME {n}%",
    'status.muted': "MUTED", 'status.sound_on': "SOUND ON",
    'status.subs_on': "SUBTITLES ON", 'status.subs_off': "SUBTITLES OFF",
    'status.audio_track': "AUDIO TRACK {n}",
    'status.shuffle_on': "SHUFFLE ON", 'status.shuffle_off': "SHUFFLE OFF",
    'status.repeat_on': "REPEAT ON", 'status.repeat_off': "REPEAT OFF",
    'status.resumed': "RESUMED AT {time} · HOME STARTS OVER",
    'status.slideshow': "SLIDESHOW", 'status.slideshow_off': "SLIDESHOW OFF",
    'status.trashed': "MOVED TO TRASH", 'status.trash_failed': "COULD NOT MOVE TO TRASH",
    'status.queued_one': "ADDED {n} SONG TO THE QUEUE",
    'status.queued_many': "ADDED {n} SONGS TO THE QUEUE",
    'status.added_to': "ADDED TO {name}", 'status.playlist_saved': "SAVED PLAYLIST {name}",
    'status.scan_failed': "COULDN'T READ THE MUSIC FOLDER",
    'status.editing': "EDITING · THE ORIGINAL STAYS AS IT IS",
    'status.edit_cancelled': "EDIT CANCELLED", 'status.saving': "SAVING…",
    'status.saved_as': "SAVED AS {name}", 'status.save_failed': "COULD NOT SAVE",

    # app
    'app.cant_open': "Spark Media can't open this:\n{path}",
    'app.wrong_kind': "Spark Media doesn't open this kind of file:\n{path}",
    'app.unexpected': "Unexpected error:\n{error}",
    'dialog.media_files': "Media files", 'dialog.all_files': "All files",
    'cli.description': "Spark Media: photos, videos and music for SparkOS.",
    'cli.files': "files, a playlist or one folder to open",
    'cli.start_photo': "start in Photos", 'cli.start_video': "start in Videos",
    'cli.start_music': "start in Music",
    'cli.self_test': "check photo formats, decoders and playback; no display needed",
    'cli.require': "with --self-test: decoders that must exist, e.g. h264,h265,aac",
    'cli.need_display': "Spark Media needs a display: {error}",

    # folders view
    'home.none_here': "NO {what} IN THIS FOLDER",
    'home.none_hint': "Open another folder, or drop files into this one and reopen it.",
    'home.folder': "FOLDER", 'home.no_preview': "NO PREVIEW",

    # photos
    'photo.gone': "The file is gone.",
    'photo.need_heif': "{ext} photos need the pillow-heif plugin, which isn't installed.",
    'photo.damaged': "The file is damaged, or isn't a photo format Spark Media reads.",
    'photo.raw_unreadable': "This RAW file has no preview Spark Media can read, and LibRaw "
                            "couldn't develop it.",
    'photo.unreadable': "UNREADABLE", 'photo.cant_show': "CAN'T SHOW THIS PHOTO",
    'photo.frames': "{n} FRAMES", 'photo.rotated_view': "ROTATED IN VIEW ONLY",
    'photo.raw_preview': "CAMERA PREVIEW · DEVELOPING…", 'photo.raw_developed': "DEVELOPED",
    'trash.title': "Move to Trash",
    'trash.ask': "Move {name} to the Trash?\n\nYou can restore it from the Trash in the file "
                 "manager.",

    # photo edits
    'edit.crop': "CROP", 'crop.free': "FREE", 'crop.original': "ORIGINAL",
    'edit.enhance': "Auto-enhance",
    'edit.hint': "Drag on the photo to crop. The original stays as it is unless you pick Replace.",
    'edit.crop_size': "Crop: {w} × {h} px. Drag the edges or corners to change it.",
    'edit.reset': "Reset", 'edit.cancel': "Cancel", 'edit.save_copy': "Save copy",
    'edit.replace': "Replace", 'edit.replace_title': "Replace the original",
    'edit.replace_ask': "Save the edit over {name}?\n\nThe original can't be brought back.",
    'edit.save_failed': "The photo couldn't be saved:\n{error}",
    'edit.suffix': "edited",

    # players
    'play.need_gst': "VIDEO AND MUSIC NEED GSTREAMER", 'play.no_start': "THE PLAYER COULD NOT START",
    'play.no_video_out': "NO VIDEO OUTPUT",
    'play.no_video_out_detail': "None of glimagesink, xvimagesink or ximagesink is installed. "
                                "Sound will still play.",
    'play.cant': "CAN'T PLAY THIS FILE", 'play.no_picture': "NO PICTURE",
    'play.sound_only': "This file has sound only.",
    'play.no_decoder': "No decoder for {what} is installed.",
    'play.err_format': "This file uses a format no installed decoder can play.",
    'play.err_open': "The file could not be opened. It may have moved.",
    'play.err_type': "This doesn't look like a video or audio file.",
    'play.err_sound': "No sound output is available.",

    # music
    'music.filter': "SEARCH", 'music.up_next': "UP NEXT", 'music.clear': "Clear",
    'music.save_queue': "Save as playlist", 'music.nothing': "Nothing playing",
    'music.unknown_artist': "Unknown artist", 'music.unknown_album': "Unknown album",
    'music.various': "Various artists",
    'music.no_match': "Nothing matches “{text}”.",
    'music.scanning': "Looking for music…",
    'music.empty': "No music found in {folders}.\nPut songs there, or add another folder "
                   "with Folders.",
    'music.scan_progress': "READING TAGS {done} / {total}", 'music.scan_looking': "LOOKING FOR MUSIC",
    'music.playlists_where': "New playlists go to {folder}, as .m3u8 files other players open too.",
    'music.no_playlists': "No playlists yet. Make one here, or save the queue as one.",
    'music.playlist_empty': "This playlist is empty. Add songs from their right-click menu.",
    'music.playlist_unreadable': "This playlist can't be read:\n{error}",
    'music.playlist_nothing': "{name} has no music files Spark Media can play.",
    'music.missing': "{n} missing",
    'music.streams_skipped': "{n} web streams skipped",
    'music.delete_playlist_q': "Move the playlist {name} to the Trash?\n\nThe songs stay where "
                               "they are.",
    'playlist.new_title': "New playlist", 'playlist.name_prompt': "Name of the playlist:",
    'playlist.name_taken': "There's already a playlist called {name}.",
    'playlist.name_empty': "Type a name for the playlist.",
    'folders.title': "Music folders",
    'folders.intro': "The library shows the songs in these folders and the folders inside "
                     "them. Removing a folder here doesn't delete anything.",
    'folders.music': "Music", 'folders.add': "Add folder", 'folders.remove': "Remove",
}

FR: Dict[str, str] = {
    'kind.photo': "PHOTOS", 'kind.video': "VIDÉOS", 'kind.music': "MUSIQUE",
    'kind.photo.files': "photos", 'kind.video.files': "vidéos",
    'kind.music.files': "fichiers audio",
    'tab.artists': "ARTISTES", 'tab.albums': "ALBUMS", 'tab.songs': "CHANSONS",
    'tab.playlists': "LISTES",
    'count.song': "{n} chanson", 'count.songs': "{n} chansons",
    'count.album': "{n} album", 'count.albums': "{n} albums",
    'time.minutes': "{n} min", 'time.hours_minutes': "{h} h {m} min",

    'btn.open_files': "Ouvrir des fichiers", 'btn.open_folder': "Ouvrir un dossier",
    'btn.play_all': "Tout écouter", 'btn.slideshow': "Diaporama", 'btn.library': "Bibliothèque",
    'btn.by_folder': "Par dossier", 'btn.library_folders': "Dossiers", 'btn.play': "Écouter",
    'btn.shuffle': "Aléatoire", 'btn.add_queue': "Ajouter à la file",
    'btn.add_playlist': "Ajouter à une liste", 'btn.new_playlist': "Nouvelle liste",
    'btn.delete': "Supprimer", 'btn.ok': "OK", 'btn.cancel': "Annuler", 'btn.done': "Terminé",

    'tip.back': "Retour", 'tip.prev': "Précédent", 'tip.next': "Suivant",
    'tip.play': "Lecture ou pause", 'tip.mute': "Couper le son", 'tip.fullscreen': "Plein écran",
    'tip.subtitles': "Sous-titres", 'tip.audio': "Piste audio", 'tip.repeat': "Répéter",
    'tip.shuffle': "Aléatoire", 'tip.trash': "Mettre à la corbeille", 'tip.slideshow': "Diaporama",
    'tip.edit': "Modifier", 'tip.rotate': "Pivoter", 'tip.zoom_in': "Agrandir",
    'tip.zoom_out': "Réduire", 'tip.fit': "Ajuster", 'tip.rotate_left': "Pivoter à gauche",
    'tip.rotate_right': "Pivoter à droite",

    'menu.open': "Ouvrir", 'menu.play': "Écouter", 'menu.shuffle': "Écouter en aléatoire",
    'menu.play_next': "Écouter ensuite", 'menu.add_queue': "Ajouter à la file",
    'menu.add_playlist': "Ajouter à une liste", 'menu.new_playlist': "Nouvelle liste…",
    'menu.go_album': "Voir l'album", 'menu.go_artist': "Voir l'artiste",
    'menu.show_folder': "Afficher dans le dossier", 'menu.move_up': "Monter",
    'menu.move_down': "Descendre", 'menu.remove_queue': "Retirer de la file",
    'menu.remove_playlist': "Retirer de la liste", 'menu.delete_playlist': "Supprimer la liste",

    'status.ready': "PRÊT", 'status.went_wrong': "QUELQUE CHOSE N'A PAS FONCTIONNÉ",
    'status.playing': "LECTURE", 'status.paused': "EN PAUSE", 'status.finished': "TERMINÉ",
    'status.play_error': "ERREUR DE LECTURE", 'status.volume': "VOLUME {n} %",
    'status.muted': "SON COUPÉ", 'status.sound_on': "SON ACTIVÉ",
    'status.subs_on': "SOUS-TITRES ACTIVÉS", 'status.subs_off': "SOUS-TITRES DÉSACTIVÉS",
    'status.audio_track': "PISTE AUDIO {n}",
    'status.shuffle_on': "ALÉATOIRE ACTIVÉ", 'status.shuffle_off': "ALÉATOIRE DÉSACTIVÉ",
    'status.repeat_on': "RÉPÉTITION ACTIVÉE", 'status.repeat_off': "RÉPÉTITION DÉSACTIVÉE",
    'status.resumed': "REPRIS À {time} · DÉBUT POUR RECOMMENCER",
    'status.slideshow': "DIAPORAMA", 'status.slideshow_off': "DIAPORAMA ARRÊTÉ",
    'status.trashed': "MIS À LA CORBEILLE",
    'status.trash_failed': "IMPOSSIBLE DE METTRE À LA CORBEILLE",
    'status.queued_one': "{n} CHANSON AJOUTÉE À LA FILE",
    'status.queued_many': "{n} CHANSONS AJOUTÉES À LA FILE",
    'status.added_to': "AJOUTÉ À {name}", 'status.playlist_saved': "LISTE {name} ENREGISTRÉE",
    'status.scan_failed': "IMPOSSIBLE DE LIRE LE DOSSIER MUSIQUE",
    'status.editing': "MODIFICATION · L'ORIGINAL RESTE INTACT",
    'status.edit_cancelled': "MODIFICATION ANNULÉE", 'status.saving': "ENREGISTREMENT…",
    'status.saved_as': "ENREGISTRÉ SOUS {name}", 'status.save_failed': "ENREGISTREMENT IMPOSSIBLE",

    'app.cant_open': "Spark Media ne peut pas ouvrir ceci :\n{path}",
    'app.wrong_kind': "Spark Media n'ouvre pas ce type de fichier :\n{path}",
    'app.unexpected': "Erreur inattendue :\n{error}",
    'dialog.media_files': "Fichiers multimédias", 'dialog.all_files': "Tous les fichiers",
    'cli.description': "Spark Media : photos, vidéos et musique pour SparkOS.",
    'cli.files': "fichiers, une liste de lecture ou un dossier à ouvrir",
    'cli.start_photo': "ouvrir sur Photos", 'cli.start_video': "ouvrir sur Vidéos",
    'cli.start_music': "ouvrir sur Musique",
    'cli.self_test': "vérifier les formats photo, les décodeurs et la lecture; aucun écran requis",
    'cli.require': "avec --self-test : décodeurs obligatoires, p. ex. h264,h265,aac",
    'cli.need_display': "Spark Media a besoin d'un écran : {error}",

    'home.none_here': "AUCUN ÉLÉMENT ({what}) DANS CE DOSSIER",
    'home.none_hint': "Ouvrez un autre dossier, ou ajoutez des fichiers à celui-ci et "
                      "rouvrez-le.",
    'home.folder': "DOSSIER", 'home.no_preview': "AUCUN APERÇU",

    'photo.gone': "Le fichier n'existe plus.",
    'photo.need_heif': "Les photos {ext} ont besoin du module pillow-heif, qui n'est pas "
                       "installé.",
    'photo.damaged': "Le fichier est endommagé, ou ce format photo n'est pas pris en charge "
                     "par Spark Media.",
    'photo.raw_unreadable': "Ce fichier RAW n'a pas d'aperçu lisible par Spark Media, et LibRaw "
                            "n'a pas pu le développer.",
    'photo.unreadable': "ILLISIBLE", 'photo.cant_show': "IMPOSSIBLE D'AFFICHER CETTE PHOTO",
    'photo.frames': "{n} IMAGES", 'photo.rotated_view': "PIVOTÉE À L'ÉCRAN SEULEMENT",
    'photo.raw_preview': "APERÇU DE L'APPAREIL · DÉVELOPPEMENT…",
    'photo.raw_developed': "DÉVELOPPÉE",
    'trash.title': "Mettre à la corbeille",
    'trash.ask': "Mettre {name} à la corbeille?\n\nVous pourrez le récupérer dans la corbeille "
                 "du gestionnaire de fichiers.",

    'edit.crop': "RECADRER", 'crop.free': "LIBRE", 'crop.original': "ORIGINAL",
    'edit.enhance': "Amélioration auto",
    'edit.hint': "Glissez sur la photo pour recadrer. L'original reste intact, sauf si vous "
                 "choisissez Remplacer.",
    'edit.crop_size': "Recadrage : {w} × {h} px. Glissez les bords ou les coins pour l'ajuster.",
    'edit.reset': "Réinitialiser", 'edit.cancel': "Annuler", 'edit.save_copy': "Enregistrer une copie",
    'edit.replace': "Remplacer", 'edit.replace_title': "Remplacer l'original",
    'edit.replace_ask': "Enregistrer la modification par-dessus {name}?\n\nL'original ne pourra "
                        "pas être récupéré.",
    'edit.save_failed': "La photo n'a pas pu être enregistrée :\n{error}",
    'edit.suffix': "modifié",

    'play.need_gst': "LA VIDÉO ET LA MUSIQUE ONT BESOIN DE GSTREAMER",
    'play.no_start': "LE LECTEUR N'A PAS PU DÉMARRER",
    'play.no_video_out': "AUCUNE SORTIE VIDÉO",
    'play.no_video_out_detail': "Ni glimagesink, ni xvimagesink, ni ximagesink n'est installé. "
                                "Le son jouera quand même.",
    'play.cant': "IMPOSSIBLE DE LIRE CE FICHIER", 'play.no_picture': "AUCUNE IMAGE",
    'play.sound_only': "Ce fichier contient seulement du son.",
    'play.no_decoder': "Aucun décodeur pour {what} n'est installé.",
    'play.err_format': "Ce fichier utilise un format qu'aucun décodeur installé ne peut lire.",
    'play.err_open': "Le fichier n'a pas pu être ouvert. Il a peut-être été déplacé.",
    'play.err_type': "Ce fichier ne semble pas être une vidéo ni un fichier audio.",
    'play.err_sound': "Aucune sortie audio n'est disponible.",

    'music.filter': "RECHERCHE", 'music.up_next': "À SUIVRE", 'music.clear': "Vider",
    'music.save_queue': "Enregistrer en liste", 'music.nothing': "Aucune lecture",
    'music.unknown_artist': "Artiste inconnu", 'music.unknown_album': "Album inconnu",
    'music.various': "Artistes variés",
    'music.no_match': "Aucun résultat pour « {text} ».",
    'music.scanning': "Recherche de musique…",
    'music.empty': "Aucune musique trouvée dans {folders}.\nAjoutez-y des chansons, ou ajoutez "
                   "un autre dossier avec Dossiers.",
    'music.scan_progress': "LECTURE DES ÉTIQUETTES {done} / {total}",
    'music.scan_looking': "RECHERCHE DE MUSIQUE",
    'music.playlists_where': "Les nouvelles listes vont dans {folder}, en fichiers .m3u8 que "
                             "les autres lecteurs ouvrent aussi.",
    'music.no_playlists': "Aucune liste pour l'instant. Créez-en une ici, ou enregistrez la "
                          "file en liste.",
    'music.playlist_empty': "Cette liste est vide. Ajoutez des chansons avec leur menu "
                            "clic droit.",
    'music.playlist_unreadable': "Cette liste ne peut pas être lue :\n{error}",
    'music.playlist_nothing': "{name} ne contient aucun fichier audio que Spark Media peut lire.",
    'music.missing': "{n} introuvable(s)",
    'music.streams_skipped': "{n} flux Web ignoré(s)",
    'music.delete_playlist_q': "Mettre la liste {name} à la corbeille?\n\nLes chansons restent "
                               "où elles sont.",
    'playlist.new_title': "Nouvelle liste", 'playlist.name_prompt': "Nom de la liste :",
    'playlist.name_taken': "Une liste s'appelle déjà {name}.",
    'playlist.name_empty': "Entrez un nom pour la liste.",
    'folders.title': "Dossiers de musique",
    'folders.intro': "La bibliothèque affiche les chansons de ces dossiers et des dossiers "
                     "qu'ils contiennent. Retirer un dossier ici ne supprime rien.",
    'folders.music': "Musique", 'folders.add': "Ajouter un dossier", 'folders.remove': "Retirer",
}
