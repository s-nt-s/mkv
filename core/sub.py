import re

import pysubs2

from .util import backtwo, to_utf8

re_nosub = re.compile(r"\bnewpct(\d+)?\.com|\baddic7ed\.com")


class Sub:
    def __init__(self, file: str):
        self.file = to_utf8(file)

    def _load(self):
        try:
            return pysubs2.load(self.file)
        except ValueError:
            typ = self.file.rsplit(".", 1)[-1].lower()
            with open(self.file, "r") as f:
                text = f.read()
            text = text.replace("Dialogue: Marked=0,", "Dialogue: 0,")
            return pysubs2.SSAFile.from_string(text, format=typ)

    def load(self, to_type: str = None) -> pysubs2.SSAFile:
        subs = self._load()
        subs.sort()
        if to_type and not self.file.endswith("." + to_type):
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
                    if o.text == s.text and o.start <= s.start and o.end >= s.start:
                        del subs[i]
                        break
            for i, s, prev in backtwo(subs):
                if s.text != prev.text and (s.start, s.end) == (prev.start, s.end):
                    prev.text = prev.text + "\n" + s.text
                    del subs[i]
            subs.sort()
        return subs

    @property
    def fonts(self) -> tuple:
        subs = self._load()
        fonts = set()
        for f in subs.styles.values():
            fonts.add(f.fontname)
            fonts.add(f.fontname.split()[0])
        fonts = sorted(fonts)
        return tuple(fonts)

    def save(self, out: str) -> str:
        if "." not in out:
            out = self.file.rsplit(".", 1)[0] + "." + out
        to_type = out.rsplit(".", 1)[-1]
        if out == self.file:
            out = out + "." + to_type
        subs = self.load(to_type=to_type)
        subs.save(out)

        if to_type == "srt":
            with open(out, "r") as f:
                text = f.read()
            n_text = re.sub(r"</(i|b)>([ \t]*)<\1>", r"\2", text)
            n_text = re.sub(r"<(i|b)>([ \t]*)</\1>", r"\2", text)
            if text != n_text:
                with open(out, "w") as f:
                    f.write(n_text)
        return out
