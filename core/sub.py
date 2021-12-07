import re

import pysubs2
from functools import lru_cache

from .util import backtwo, to_utf8

re_nosub = re.compile(r"\bnewpct(\d+)?\.com|\baddic7ed\.com|^Subida x ")


class SubLine:
    def __init__(self, index, line):
        self.index = index
        self.line = line

    def __str__(self):
        fk_sub = pysubs2.SSAFile()
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

    @staticmethod
    @lru_cache(maxsize=None)
    def read(file) -> pysubs2.SSAFile:
        try:
            return pysubs2.load(file)
        except ValueError:
            typ = file.rsplit(".", 1)[-1].lower()
            with open(file, "r") as f:
                text = f.read()
            text = text.replace("Dialogue: Marked=0,", "Dialogue: 0,")
            return pysubs2.SSAFile.from_string(text, format=typ)

    @staticmethod
    @lru_cache(maxsize=None)
    def st_load(file, to_type: str = None) -> pysubs2.SSAFile:
        subs = Sub.read(file)
        subs.sort()
        if to_type and not file.endswith("." + to_type):
            strng = subs.to_string(to_type)
            if strng.strip():
                subs = pysubs2.SSAFile.from_string(strng, format=to_type)
            subs.sort()
        for i, s in reversed(list(enumerate(subs))):
            if re_nosub.search(s.text) or len(s.text.strip()) == 0:
                del subs[i]
        flag = len(subs) + 1
        while len(subs) < flag:
            flag = len(subs)
            for i, s in reversed(list(enumerate(subs))):
                for o in subs[:i]:
                    if o.text == s.text and o.start <= s.start <= o.end:
                        if s.end > o.end:
                            o.end = s.end
                        del subs[i]
                        break
            for i, s, prev in backtwo(subs):
                if s.text != prev.text and (s.start, s.end) == (prev.start, s.end):
                    prev.text = prev.text + "\n" + s.text
                    del subs[i]
            subs.sort()
        return subs

    def load(self, to_type: str = None) -> pysubs2.SSAFile:
        return Sub.st_load(self.file, to_type)

    @property
    def fonts(self) -> tuple:
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
        to_type = out.rsplit(".", 1)[-1]
        if out == self.file:
            out = out + "." + to_type
        subs = self.load(to_type=to_type)
        subs.save(out)

        if to_type == "srt":
            with open(out, "r") as f:
                text = f.read()
            n_text = str(text)
            n_text = re.sub(r"</(i|b)>([ \t]*)<\1>", r"\2", n_text)
            n_text = re.sub(r"<(i|b)>([ \t]*)</\1>", r"\2", n_text)
            if text != n_text:
                with open(out, "w") as f:
                    f.write(n_text)
        return out

    def get_collisions(self):
        subs = self.load("srt")
        subs.sort()
        times = {}
        for indx, s in enumerate(subs):
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
