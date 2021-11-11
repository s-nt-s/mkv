#!/usr/bin/python3
import argparse
import sys
from os.path import isfile, basename

from core.mkv import MkvMerge
from core.shell import Shell
from core.sub import Sub
from core.track import MKVLANG


def parse_track(tracks):
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
        if isfile(fln) and ext in ("srt", "ssa", "ass"):
            out = Sub(fln).save("srt")
            print("OUT:", out)
            sys.exit()
    if len(sys.argv) > 2 and sys.argv[1] == "info":
        print("[spoiler=mediainfo][code]", end="")
        fls = sys.argv[2:]
        for i, f in enumerate(fls):
            out = Shell.mediainfo(f)
            if len(fls) > 1:
                print("$", "mediainfo '" + basename(f) + "'")
            print(out, end="" if i == len(fls) - 1 else "\n\n")
        print("[/code][/spoiler]")
        sys.exit()

    langs = sorted(k for k in MKVLANG.code.keys() if len(k) == 2)
    parser = argparse.ArgumentParser("Remezcla mkv")
    parser.add_argument('--und', help='Idioma para pistas und (mkvmerge --list-languages)', choices=langs)
    parser.add_argument('--vo', help='Idioma de la versión original (mkvmerge --list-languages)', choices=langs)
    parser.add_argument('--do-srt', action='store_true', help='Genera subtitulos srt si no los hay')
    parser.add_argument('--do-ac3', action='store_true', help='Genera audio ac3 si no lo hay')
    parser.add_argument('--tracks', nargs="*", help='tracks a preservar en formato source:id')
    parser.add_argument('--out', type=str, help='Fichero salida para mkvmerge')
    parser.add_argument('files', nargs="+", help='Ficheros a mezclar')
    pargs = parser.parse_args()

    if pargs.out in pargs.files:
        sys.exit("El fichero de entrada y salida no pueden ser el mismo")
    for file in pargs.files:
        if not isfile(file):
            sys.exit("No existe: " + file)
    if isfile(pargs.out):
        sys.exit("Ya existe: " + pargs.out)

    pargs.tracks = parse_track(pargs.tracks)
    mrg = MkvMerge(vo=pargs.vo, und=pargs.und, do_srt=pargs.do_srt, do_ac3=pargs.do_ac3)
    mrg.merge(pargs.out, *pargs.files, tracks_selected=pargs.tracks)
