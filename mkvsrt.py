#!/usr/bin/python3
import argparse

from core.mkv import Mkv
from core.shell import Shell
from core.sub import Sub
from core.track import MKVLANG
from os import remove
from os.path import basename
from core.util import TMP


if __name__ == "__main__":
    langs = sorted(k for k in MKVLANG.code.keys() if len(k) == 2)
    parser = argparse.ArgumentParser("Estrae el subtitulo principal y lo convirte a srt para TV antiguas")
    parser.add_argument('files', nargs="+", help='Ficheros a mezclar')
    pargs = parser.parse_args()
    for file in pargs.files:
        mkv = Mkv(file)
        track = mkv.get_main_extract()
        if track is None:
            continue
        #extraer
        name = file.rsplit(".", 1)[0]
        out = f"{TMP}/{basename(name)}.{track.file_extension}"
        Shell.run("mkvextract", "tracks", file, f"{track.id}:{out}")
        #limpiar
        print(f"# mv '{out}' '{name}.srt'")
        Sub(out).load().save(name+".srt", encoding="utf-8-sig")