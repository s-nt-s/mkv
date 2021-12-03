import re

from munch import DefaultMunch
from os.path import isfile, getsize, basename

from .shell import Shell
from .util import LANG_ES, trim, read_file, get_printable, to_utf8
from .sub import Sub
from .pgsreader import PGSReader

re_doblage = re.compile(r"((?:19|20)\d\d+)", re.IGNORECASE)


class MkvLang:
    def __init__(self):
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
        if "source_file" not in self:
            self.source_file = None
        if self.source_file:
            if self.track_name is None:
                self.track_name = basename(self.source_file)
                self.fake_name = True
            if self.isUnd:
                lw_name = basename(self.source_file).lower()
                st_name = set(re.split(r"[\.]+", lw_name))
                if re.search(r"\b(español|castellano|spanish|)\b|\[esp\]", lw_name) or st_name.intersection({"es", }):
                    self.set_lang("spa")
                if re.search(r"\b(ingles|english)\b", lw_name) or st_name.intersection({"en", }):
                    self.set_lang("eng")
                if re.search(r"\b(japon[ée]s|japanese)\b", lw_name) or st_name.intersection({"ja", }):
                    self.set_lang("jpn")
                if self.isUnd:
                    self.set_lang(self.und or "und")
                if re.search(r"\b(forzados?)\b", lw_name) or st_name.intersection({"forzados", "forzado"}):
                    self.forced_track = 1

    @staticmethod
    def build(source, arg):
        file = None
        track = None
        rm_chapters = None
        if isinstance(arg, str) and isfile(arg):
            file = str(arg)
        elif isinstance(arg, dict):
            track = arg.copy()
        else:
            raise Exception("Tipo invalido en el argumento: %s" % arg)

        if file:
            tinfo = Shell.mkvinfo(file)
            track = tinfo.tracks[0]
            if track.get('type') == "subtitles":
                f = to_utf8(file)
                if f not in (None, file):
                    return Track.build_track(source, f)
            if len(tinfo.get("chapters", [])) == 1 and tinfo.chapters[0].num_entries == 1:
                rm_chapters = True

        data = track.properties.copy()
        data.id = track.id
        data.codec = track.codec
        data.type = track.type
        data.source = source
        data.source_file = file

        if track.type == 'subtitles':
            return SubTrack(**dict(data), rm_chapters=rm_chapters, _original=track.properties.copy())
        if track.type == 'audio':
            return AudioTrack(**dict(data), rm_chapters=rm_chapters, _original=track.properties.copy())
        if track.type == 'video':
            return VideoTrack(**dict(data), rm_chapters=rm_chapters, _original=track.properties.copy())
        raise Exception("Tipo de Track no reconocido %s" % track.type)

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
        if self.codec == "Opus":
            return "opus"
        raise Exception("Extensión no encontrada para: {codec}".format(**dict(self)))

    def set_lang(self, lang):
        if len(lang) == 3 and lang != self.language_ietf:
            self.language_ietf = lang
            self.language = MKVLANG.code.get(lang)
            self.isNewLang = True
        if len(lang) == 2 and lang != self.language:
            self.language_ietf = MKVLANG.code.get(lang)
            self.language = lang
            self.isNewLang = True

    def to_dict(self) -> dict:
        d = {k: v for k, v in dict(self).items() if not k.startswith("_")}
        for name in dir(self.__class__):
            obj = getattr(self.__class__, name)
            if isinstance(obj, property):
                val = obj.__get__(self, self.__class__)
                d[name] = val
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

    @property
    def new_name(self) -> str:
        return self.track_name

    def has_file(self) -> bool:
        return self.source_file and isfile(self.source_file)

    def is_empty_source(self) -> bool:
        if not self.has_file():
            return None
        if getsize(self.source_file) == 0:
            return True
        return False


class VideoTrack(Track):
    @property
    def new_name(self) -> str:
        lb = None
        if "H.264" in self.codec:
            lb = "H.264"
        if "H.265" in self.codec:
            lb = "H.265"
        if "HDMV" in self.codec:
            lb = "HDMV"
        if lb is None:
            raise Exception("codec no reconocido %s" % self.dodec)
        if self.pixel_dimensions:
            lb = "{} ({})".format(lb, self.pixel_dimensions)
        if self.duration is not None and self.duration.minutes > 59:
            lb = lb + " ({}m)".format(self.duration.minutes)
        return lb


class AudioTrack(Track):
    @property
    def new_name(self) -> str:
        arr = [self.lang_name]
        if self.track_name:
            m = set(i for i in re_doblage.findall(self.track_name) if len(i) == 4)
            if len(m) == 1:
                arr.append(m.pop())
        arr.append("(" + self.file_extension + ")")
        return " ".join(arr)


class SubTrack(Track):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fix_text_subtitles()

    def fix_text_subtitles(self):
        if self.has_file():
            self.text_subtitles = True
            return
        if "text_subtitles" in self and self.text_subtitles is not None:
            return
        if self.codec_id in ("S_VOBSUB", "S_HDMV/PGS"):
            self.text_subtitles = False
            return
        raise Exception(
            "No se ha podido determinar si es un subtitulo de texto {id}:{codec_id}".format(self.__dict__))

    @property
    def new_name(self) -> str:
        arr = [self.lang_name]
        if self.forced_track:
            arr.append("forzados")
        arr.append("(" + self.file_extension + ")")
        if self.lines:
            arr.append("({} línea{})".format(self.lines, "s" if self.lines > 1 else ""))
        return " ".join(arr)

    def is_empty_source(self) -> bool:
        if super().is_empty_source():
            return True
        if self.text_subtitles and self.has_file():
            cnt = read_file(self.source_file)
            cnt = get_printable(cnt)
            if len(cnt) == 0:
                return True
        return False

    @property
    def lines(self) -> int:
        if not self.has_file():
            return None
        if self.is_empty_source():
            return 0
        if self.text_subtitles:
            sb = Sub(self.source_file)
            lines = len(sb.load("srt"))
            return lines
        if self.source_file.endswith(".pgs"):
            pgs = PGSReader(self.source_file)
            dss = list(ds for ds in pgs.displaysets if ds.has_image)
            return len(dss)
        if self.source_file.endswith(".sub"):
            idx = self.source_file.rsplit(".", 1)[0] + ".idx"
            txt = read_file(idx)
            if txt is not None:
                lines = 0
                for l in txt.split("\n"):
                    if l.strip().startswith("timestamp: "):
                        lines = lines + 1
                return lines

    @property
    def fonts(self) -> tuple:
        if not self.has_file():
            return None
        if not self.text_subtitles or self.is_empty_source():
            return tuple()
        return Sub(self.source_file).fonts

    @property
    def collisions(self) -> int:
        if not (self.text_subtitles and self.has_file()):
            return None
        if self.is_empty_source() or self.lines < 2:
            return 0
        colls = list(Sub(self.source_file).get_collisions())
        return len(colls)

    def is_srt_candidate(self):
        if self.file_extension == "srt":
            return False
        if self.text_subtitles:
            return True
        return False

    def to_srt(self, **kwargs):
        for k, v in dict(self).items():
            if k not in kwargs:
                kwargs[k]=v
        s = SubTrack(**kwargs)
        s.id = 0
        s.source_file = Sub(self.source_file).save("srt")
        return s
