#!/usr/bin/python3
import argparse
import sys
from os import makedirs
from os.path import isfile, basename, isdir, realpath, dirname

from core.mkv import MkvMerge, Mkv
from core.shell import Shell
from core.sub import Sub
from core.track import MKVLANG
from core.pgsreader import PGSReader

try:
    from core.guess import guess_args
except ImportError:
    guess_args = lambda *args, **kwargs: None


def parse_track(tracks):
    if isinstance(tracks, str):
        tracks = [tracks]
    if tracks is None or len(tracks) == 0:
        return tracks
    trck = []
    for tr in tracks:
        for t in tr.split(","):
            trck.append(t)
    for i, t in enumerate(trck):
        if t.isdigit():
            trck[i] = "0:" + t
    return trck


if __name__ == "__main__":
    if len(sys.argv) == 2:
        fln = sys.argv[1]
        ext = fln.rsplit(".", 1)[-1].lower()
        if isfile(fln):
            if ext in ("srt", "ssa", "ass"):
                out = Sub(fln).save("srt")
                print("OUT:", out)
                colls = list(Sub(out).get_collisions())
                if colls:
                    print("COLISIONES:")
                    for cls in colls:
                        print("")
                        print(cls)
                sys.exit()
            if ext in ("sup", "pgs"):
                print("OUT:", PGSReader(fln).fake_srt())
                sys.exit()

    if len(sys.argv) > 2 and sys.argv[1] == "info":
        print("[spoiler=mediainfo][code]", end="")
        fls = sys.argv[2:]
        for i, f in enumerate(fls):
            out = Shell.mediainfo(f, do_print=False)
            if len(fls) > 1:
                print("$", "mediainfo '" + basename(f) + "'")
            print(out, end="" if i == len(fls) - 1 else "\n\n")
        print("[/code][/spoiler]")
        sys.exit()

    if len(sys.argv) > 2 and sys.argv[1] == "edit":
        for f in sys.argv[2:]:
            f = Mkv(f)
            f.fix_tracks(dry=True)
        sys.exit()

    langs = sorted(k for k in MKVLANG.code.keys() if len(k) == 2)
    parser = argparse.ArgumentParser("Remezcla mkv")
    parser.add_argument('--und', help='Idioma para pistas und (mkvmerge --list-languages)', choices=langs)
    parser.add_argument('--vo', help='Idioma de la versión original (mkvmerge --list-languages)', choices=langs)
    parser.add_argument('--tracks', nargs="*", help='tracks a preservar en formato source:id')
    parser.add_argument('--out', type=str, help='Fichero salida para mkvmerge', default='.')
    parser.add_argument('--srt', type=int, help='Convertir a srt los subtítulos con X colisiones o menos', default=-1)
    parser.add_argument('--trim', help='Recortar el video usando --split parts:')
    parser.add_argument('--dry', action="store_true", help='Imprime el comando mkvmerge sin ejecutarlo')
    parser.add_argument('files', nargs="+", help='Ficheros a mezclar')
    pargs = parser.parse_args()

    for file in pargs.files:
        if not isfile(file):
            sys.exit("No existe: " + file)

    guess_args(pargs)
    
    if pargs.out is None or isdir(pargs.out):
        sys.exit("No se puede adivinar el nombre de fichero destino, proporcionelo usando --out")
    if pargs.out in pargs.files:
        sys.exit("El fichero de entrada y salida no pueden ser el mismo")
    if isfile(pargs.out):
        sys.exit("Ya existe: " + pargs.out)
        
    drout = dirname(realpath(pargs.out))
    if drout and not isdir(drout):
        print("$ mkdir -p '{}'".format(dirname(pargs.out)))
        makedirs(drout, exist_ok=True)

    pargs.tracks = parse_track(pargs.tracks)

    mrg = MkvMerge(vo=pargs.vo, und=pargs.und, dry=pargs.dry)
    mrg.merge(pargs.out, *pargs.files, tracks_selected=pargs.tracks, do_srt=pargs.srt, do_trim=pargs.trim)
    print("")
