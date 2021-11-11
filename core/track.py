import re

from munch import DefaultMunch

from .shell import Shell
from .util import LANG_ES

re_doblage = re.compile(r"((?:19|20)\d\d+)", re.IGNORECASE)


class MkvLang:
    def __init__(self):
        def trim(s):
            s = s.strip()
            if len(s) == 0:
                return None
            return s

        self.code = {}
        self.description = {}
        langs = Shell.get("mkvmerge", "--list-languages", do_print=False)
        for l in langs.strip().split("\n")[2:]:
            label, cod1, cod2 = map(trim, l.split(" |"))
            if cod1:
                self.code[cod1] = cod2
                self.description[cod1] = label
            if cod2:
                self.code[cod2] = cod1
                self.description[cod2] = label


MKVLANG = MkvLang()


class Track(DefaultMunch):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "track_name" not in self:
            self.track_name = None

    @property
    def lang(self) -> str:
        lg = [self.language_ietf, self.language]
        lg = [l for l in lg if l not in (None, "", "und")]
        if len(lg) == 0:
            return "und"
        lg = lg[0]
        if len(lg) == 2 and MKVLANG.code.get(lg):
            lg = MKVLANG.code.get(lg)
        return lg

    @property
    def isUnd(self) -> bool:
        return self.lang in (None, "", "und")

    @property
    def lang_name(self) -> str:
        if self.lang in LANG_ES:
            return "Español"
        if self.lang in ("ja", "jpn"):
            return "Japonés"
        if self.lang in ("en", "eng"):
            return "Inglés"
        if self.lang in ("hi", "hin"):
            return "Hindi"
        if self.lang in ("ko", "kor"):
            return "Coreano"
        if self.lang in ("fr", "fre"):
            return "Francés"
        label = MKVLANG.description.get(self.lang)
        if label:
            return label
        return self.lang

    @property
    def isLatino(self) -> bool:
        if self.track_name is None or self.lang not in LANG_ES:
            return False
        if "latino" in self.track_name.lower():
            return True
        if self.track_name == "LRL":
            return True
        return False

    @property
    def file_extension(self) -> str:
        if self.codec == "SubStationAlpha":
            return "ssa"
        if self.codec == "SubRip/SRT":
            return "srt"
        if self.type == "subtitles" and "PGS" in self.codec:
            return "pgs"
        if self.codec in ("AC-3", "AC-3 Dolby Surround EX", "E-AC-3"):
            return "ac3"
        if self.codec in ("DTS", "DTS-ES"):
            return "dts"
        if self.codec_id == "A_VORBIS":
            return "ogg"
        if self.codec == "MP3":
            return "mp3"
        if self.codec == "FLAC":
            return "flac"
        if self.codec in ("AAC",):
            return "aac"
        if self.codec == "VobSub":
            return "sub"
        raise Exception("Extensión no encontrada para: {codec}".format(**dict(self)))

    @property
    def new_name(self) -> str:
        if self.type == "video":
            lb = None
            if "H.264" in self.codec:
                lb = "H.264"
            if "H.265" in self.codec:
                lb = "H.265"
            if "HDMV" in self.codec:
                lb = "HDMV"
            if lb is None:
                return None
            if self.pixel_dimensions:
                lb = "{} ({})".format(lb, self.pixel_dimensions)
            if self.duration is not None and self.duration.minutes > 59:
                lb = lb + " ({}m)".format(self.duration.minutes)
            return lb
        arr = [self.lang_name]
        if self.type == "subtitles" and self.forced_track:
            arr.append("forzados")
        if self.type == "audio" and self.track_name:
            m = set(i for i in re_doblage.findall(self.track_name) if len(i) == 4)
            if len(m) == 1:
                arr.append(m.pop())
        arr.append("(" + self.file_extension + ")")
        if self.type == "subtitles" and self.lines:
            arr.append("({} línea{})".format(self.lines, "s" if self.lines > 1 else ""))
        return " ".join(arr)

    def set_lang(self, lang):
        if len(lang) == 3 and lang != self.language_ietf:
            self.language_ietf = lang
            self.language = MKVLANG.code.get(lang)
            self.isNewLang = True
        if len(lang) == 2 and lang != self.language:
            self.language = lang
            self.language_ietf = MKVLANG.code.get(lang)
            self.isNewLang = True

    def to_dict(self) -> dict:
        d = dict(self)
        d['new_name'] = self.new_name
        d['file_extension'] = self.file_extension
        d['isLatino'] = self.isLatino
        d['lang'] = self.lang
        d['lang_name'] = self.lang_name
        d['track_name'] = self.track_name
        return d

    def get_changes(self, mini=False) -> DefaultMunch:
        chg = DefaultMunch(
            language=self.lang,
            track_name=self.new_name,
            default_track=int(self.get("default_track", 0)),
            forced_track=int(self.type == "subtitles" and bool(self.forced_track))
        )
        if mini:
            if not self.isNewLang:
                del chg["language"]
            if self._original:
                if chg.track_name == self._original.track_name:
                    del chg["track_name"]
                if chg.default_track == int(self._original.get("default_track", 0)):
                    del chg["default_track"]
                if chg.forced_track == int(self._original.get("forced_track", 0)):
                    del chg["forced_track"]
        return chg
