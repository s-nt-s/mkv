import logging
import re
import subprocess
import sys
from os import getcwd, chdir
from os.path import isfile, dirname, basename

log = logging.getLogger(__name__)
re_track = re.compile(r"^(\d+):.*")


class Args(list):
    def extend(self, s, *args, **kwargs):
        """
        Si s es un str, lo formate con *args, **kwargs y le hace un split
        Si s es un list, formatea con *args, **kwargs todos sus elementos
        El resultado se pasa a super().extend
        """
        if isinstance(s, str):
            s = s.format(*args, **kwargs)
            s = s.split()
        elif args or kwargs:
            s = [str(i).format(*args, **kwargs) for i in s]
        super().extend(s)


class Shell:

    @staticmethod
    def to_str(*args: str):
        arr = []
        for index, a in enumerate(args):
            if " " in a or "!" in a:
                a = "'" + a + "'"
            if args[0] == "mkvpropedit" and a == "--edit":
                a = "\\\n  --edit"
            if args[0] == "mkvmerge" and index > 1:
                if a == "--track-order":
                    a = "\\\n  " + a
                elif args[index - 2] == "-o" and "--title" not in args:
                    a = "\\\n  " + a
                elif args[index - 2] in ("--title", "--global-tags", "--split", "--track-order"):
                    a = "\\\n  " + a
                elif isfile(args[index - 1]) and a != "--title":
                    a = "\\\n  " + a
                elif a.startswith("--") and 0 < index < len(args) - 1 and not a == "--sub-charset":
                    m1 = re_track.match(args[index - 1])
                    m2 = re_track.match(args[index + 1])
                    if m1:
                        m1 = int(m1.group(1))
                    if m2:
                        m2 = int(m2.group(1))
                    if m2 is not None and m2 != m1:
                        a = "\\\n  " + a
            arr.append(a)
        return " ".join(arr)

    @staticmethod
    def run(*args: str, do_print: bool = True, dry: bool = False, **kwargs) -> int:
        do_print = (do_print, kwargs.get("stdout") == subprocess.DEVNULL) == (True, False)
        if do_print:
            print("$", Shell.to_str(*args))
        if dry is True:
            return
        out = subprocess.call(args, **kwargs)
        if out != 0:
            if not do_print:
                print("$", Shell.to_str(*args))
            print("# exit code", out)
        return out

    @staticmethod
    def safe_get(*args, **kwargs) -> int:
        try:
            return Shell.get(*args, **kwargs)
        except subprocess.CalledProcessError:
            pass
        return None

    @staticmethod
    def get(*args: str, do_print: bool = True, dry: bool = False, **kargv) -> str:
        if do_print:
            print("$", Shell.to_str(*args))
        if dry is True:
            return
        output = subprocess.check_output(args, **kargv)
        output = output.decode(sys.stdout.encoding)
        return output

    @staticmethod
    def mediainfo(file, **kwargs):
        cwd = getcwd()
        dr = dirname(file)
        if dr:
            chdir(dr)
        out = Shell.get("mediainfo", basename(file), **kwargs)
        chdir(cwd)
        out = out.strip()
        arr = []
        for l in out.split("\n"):
            l = [i.strip() for i in l.split(" : ", 1)]
            arr.append(tuple(l))
        frt = max(len(i[0]) for i in arr)
        frt = "%-" + str(frt) + "s : %s"
        for i, l in enumerate(arr):
            if len(l) == 1:
                arr[i] = l[0]
                continue
            arr[i] = frt % l
        out = "\n".join(arr)
        return out
