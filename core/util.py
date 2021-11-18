import re
import tempfile
from os.path import basename, dirname, realpath

from chardet import detect

re_sp = re.compile(r"\s+")
LANG_ES = ("es", "spa", "es-ES")


class MyTMP:
    def __init__(self):
        self._tmp = None

    @property
    def tmp(self):
        if self._tmp is None:
            self._tmp = tempfile.mkdtemp()
            print("$ mkdir -p", self._tmp)
        return self._tmp

    def __str__(self):
        return self.tmp

    def __add__(self, o):
        return self.tmp + o


TMP = MyTMP()


def backtwo(arr) -> reversed:
    arr = zip(range(1, len(arr)), arr[1:], arr)
    return reversed(list(arr))


def get_encoding_type(file):
    with open(file, 'rb') as f:
        rawdata = f.read()
    return detect(rawdata)['encoding']


def to_utf8(file: str) -> str:
    enc = get_encoding_type(file)
    if enc in ("utf-8", "ascii", "UTF-8-SIG"):
        return file

    n_file = TMP + "/" + basename(file)
    while n_file == file:
        n_file = n_file + "." + n_file.split(".")[-1]
    with open(file, 'r', encoding=enc) as s:
        with open(n_file, 'w', encoding='utf-8') as t:
            text = s.read()
            t.write(text)
    print("# MV", file, "({}) -> ({})".format(enc, get_encoding_type(n_file)), n_file)
    return n_file


def get_title(file: str) -> str:
    year = None
    capi = None
    title = basename(file)
    title = title.rsplit(".", 1)[0]
    title = title.strip()
    if re.match(r"^\d+(x\d+)?$", title):
        capi = title
        title = basename(dirname(realpath(file)))
    mtc = re.match(r"(19\d\d|20\d\d)[\s\-]+(.+)", title)
    if mtc:
        year = mtc.group(1)
        title = mtc.group(2).strip()
    if capi:
        title = title + " " + capi
    if year:
        title = title + " ({})".format(year)
    return title


def trim(s):
    if s is None:
        return None
    s = s.strip()
    if len(s) == 0:
        return None
    return s
