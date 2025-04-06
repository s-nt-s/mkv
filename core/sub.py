import re

import pysubs2
from typing import Tuple, List
from os.path import splitext

from .util import backtwo, to_utf8

re_nosub = re.compile("|".join(x.pattern for x in map(re.compile, [
    r"\bnewpct(\d+)?\.com",
    r"\baddic7ed\.com",
    r"atomixhq\.com",
    r"^Subida x",
    r"YTS",
    r"UNA?.*ORIGINAL DE NETFLIX",
    r"PRODUCID[OA] POR NETFLIX",
    r"EN COLABORACIÓN CON NETFLIX",
    r"UNA SERIE.* DE NETFLIX"
])))

class SSAFile(pysubs2.SSAFile):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _enum(self) -> List[Tuple[int, pysubs2.SSAEvent]]:
        return list(enumerate(self))

    def _revenum(self) -> List[Tuple[int, pysubs2.SSAEvent]]:
        return list(reversed(self._enum()))

    def _backtwo(self) -> List[Tuple[int, pysubs2.SSAEvent, pysubs2.SSAEvent]]:
        return list(backtwo(self))

    def improve(self):
        bk_len = len(self)
        self.sort()
        for i, s in self._revenum():
            if re_nosub.search(s.text) or len(s.text.strip()) == 0:
                del self[i]
        flag = len(self) + 1
        while len(self) < flag:
            flag = len(self)
            for i, s in self._revenum():
                for o in self[:i]:
                    if o.text == s.text and o.start <= s.start <= o.end:
                        if s.end > o.end:
                            o.end = s.end
                        del self[i]
                        break
            for i, s, prev in self._backtwo():
                if s.text != prev.text and (s.start, s.end) == (prev.start, s.end):
                    prev.text = prev.text + "\n" + s.text
                    del self[i]
            self.sort()
        return (len(self) < bk_len)


class SubLine:
    def __init__(self, index, line):
        self.index = index
        self.line = line

    def __str__(self):
        fk_sub = SSAFile()
        fk_sub.insert(0, self.line)
        fk_str = fk_sub.to_string('srt')
        fk_str = re.sub(r"^\d+\s*|\s*$", "", fk_str)
        fk_str = re.sub(r"\s*\n\s*", " ", fk_str)
        return str(self.index) + ": " + fk_str


class SubLines:
    def __init__(self, *lines):
        self.lines = list(lines)

    def append(self, line):
        self.lines.append(line)

    def __str__(self):
        return "\n".join(str(l) for l in self.lines)


class Sub:
    def __init__(self, file: str):
        self.file = to_utf8(file)
        self.__improvable = None

    @staticmethod
    def read(file: str) -> SSAFile:
        try:
            subs = pysubs2.load(file)
            subs.__class__ = SSAFile
            return subs
        except ValueError:
            typ = file.rsplit(".", 1)[-1].lower()
            with open(file, "r") as f:
                text = f.read()
            text = text.replace("Dialogue: Marked=0,", "Dialogue: 0,")
            subs = pysubs2.SSAFile.from_string(text, format=typ)
            subs.__class__ = SSAFile
            return subs

    def transform(self, format_: str):
        subs = self.load()
        strng = subs.to_string(format_)
        if strng.strip():
            subs = pysubs2.SSAFile.from_string(strng, format=format_)
            subs.__class__ = SSAFile
        subs.sort()
        return subs

    def load(self) -> SSAFile:
        subs = Sub.read(self.file)
        subs.improve()
        if self.format == "srt":
            text = subs.to_string(self.format)
            n_text = str(text)
            n_text = re.sub(r"</(i|b)>([ \t]*)<\1>", r"\2", n_text)
            n_text = re.sub(r"<(i|b)>([ \t]*)</\1>", r"\2", n_text)
            if text != n_text:
                subs = pysubs2.SSAFile.from_string(n_text, format=self.format)
                subs.__class__ = SSAFile
        return subs

    @property
    def isImprovable(self):
        with open(self.file, "r") as f:
            old = f.read()
        subs = self.load()
        new = subs.to_string(self.format)
        return old.strip() != new.strip()

    @property
    def fonts(self) -> tuple[str]:
        subs = Sub.read(self.file)
        fonts = set()
        for f in subs.styles.values():
            fonts.add(f.fontname)
            fonts.add(f.fontname.split()[0])
        fonts = sorted(fonts)
        return tuple(fonts)

    def save(self, out: str) -> str:
        if "." not in out:
            out = self.file + "." + out
        if out == self.file:
            out = out + "." + out.rsplit(".", 1)[-1]
        subs = self.load()
        subs.save(out)
        return out

    def get_collisions(self):
        subs = self.transform("srt")
        subs.sort()
        times = {}
        for indx, s in subs._enum():
            for i in range(s.start, s.end):
                if i not in times:
                    times[i] = []
                times[i].append(indx)

        colls = set()
        for k in sorted(times.keys()):
            v = times[k]
            if len(v) < 2:
                continue
            colls.add(tuple(v))

        if len(colls) == 0:
            return

        for v in sorted(colls):
            rtn = SubLines()
            for indx in v:
                rtn.append(SubLine(indx + 1, subs[indx]))
            yield rtn

    @property
    def format(self):
        return Sub.get_format(self.file)

    @staticmethod
    def get_format(file: str):
        ext = splitext(file)[1].lower()
        return pysubs2.ssafile.get_format_identifier(ext)
