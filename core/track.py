import re

from os.path import isfile, getsize, basename

from .mkvutil import MkvInfo, MkvInfoTrack, MkvInfoTrackProperties, Duration, Trim
from .shell import Shell
from typing import Union, List, Tuple
from .util import LANG_ES, trim, read_file, get_printable, to_utf8, BadType
from .sub import Sub
from .pgsreader import PGSReader, InvalidSegmentError
from dataclasses import dataclass

re_doblage = re.compile(r"((?:19|20)\d\d+)", re.IGNORECASE)


@dataclass
class ChangeSet:
    language: str = None
    track_name: str = None
    default_track: int = None
    forced_track: int = None


class MkvLang:
    def __init__(self):
        self.code = {}
        self.description = {}
        langs = Shell.get("mkvmerge", "--list-languages", do_print=False)
        for l in langs.strip().split("\n")[2:]:
            label, *cods = map(trim, l.split(" |"))
            cods = sorted(set(c for c in cods if c is not None))
            for cod in cods:
                self.description[cod] = label
            if len(cods) > 1:
                self.code[cods[0]] = cods[1]
                self.code[cods[1]] = cods[0]


MKVLANG = MkvLang()


class BannableItem:
    def __init__(self, *args, **kwargs):
        self.__baned = False

    def ban(self, msg=None):
        if self.__baned:
            return
        if msg:
            print(msg)
        self.__baned = True

    @property
    def banned(self):
        return self.__baned


class Track(BannableItem):
    def __init__(
            self,
            id: int = None,
            codec: str = None,
            codec_id: str = None,
            source: str = None,
            trim: Trim = None,
            type: str = None,
            track_name: str = None,
            source_file: str = None,
            pixel_dimensions: str = None,
            language: str = None,
            language_ietf: str = None,
            default_track: int = None,
            number: int = None,
            forced_track: int = None,
            duration: Duration = None,
            rm_chapters: bool = None,
            _original: MkvInfoTrackProperties = None,
            **kwargs
    ):
        super().__init__()
        self.id = id
        self.codec = codec
        self.codec_id = codec_id
        self.type = type
        self.source = source
        self.source_file = source_file
        self.trim = trim
        self.track_name = track_name
        self.source_file = source_file
        self.pixel_dimensions = pixel_dimensions
        self.duration = duration
        self.default_track = default_track
        self.number = number
        self.language = language
        self.language_ietf = language_ietf
        self.forced_track = forced_track
        self.rm_chapters = rm_chapters
        self._original = _original
        self.fake_name = False
        self.isNewLang = False
        self.mkv = None

        guess_lang: List[str] = []
        if self.source_file:
            guess_lang.append(basename(self.source_file))
            if self.track_name is None:
                self.track_name = basename(self.source_file)
                self.fake_name = True
            else:
                guess_lang.append(self.track_name)
        elif self.track_name:
            guess_lang.append(self.track_name)
        while self.isUnd and guess_lang:
            lw_name = guess_lang.pop(0).lower()
            st_name = set(re.split(r"[\.]+", lw_name))
            if re.search(r"\b(español|castellano|spanish)\b|\[esp\]", lw_name) or st_name.intersection({"es", }):
                self.set_lang("spa")
            if re.search(r"\b(ingles|english)\b", lw_name) or st_name.intersection({"en", }):
                self.set_lang("eng")
            if re.search(r"\b(japon[ée]s|japanese)\b", lw_name) or st_name.intersection({"ja", }):
                self.set_lang("jpn")
            if self.isUnd:
                self.set_lang("und")
            if re.search(r"\b(forzados?)\b", lw_name) or st_name.intersection({"forzados", "forzado"}):
                self.forced_track = 1

    @staticmethod
    def build(source, arg: Union[MkvInfoTrack, str], trim: Trim = None):
        file = None
        track = None
        rm_chapters = None
        if isinstance(arg, str) and isfile(arg):
            file = str(arg)
        elif isinstance(arg, MkvInfoTrack):
            track = arg
        else:
            raise Exception("Tipo invalido en el argumento: %s" % arg)

        if file:
            tinfo = MkvInfo.build(file)
            track = tinfo.tracks[0]
            if track.type == "subtitles":
                f = to_utf8(file)
                if f not in (None, file):
                    return Track.build(source, f)
            if len(tinfo.chapters) == 1 and tinfo.chapters[0].num_entries == 1:
                rm_chapters = True

        data = dict(track.properties.copy())
        data['id'] = track.id
        data['codec'] = track.codec
        data['type'] = track.type
        data['source'] = source
        data['source_file'] = file
        data['trim'] = trim

        if track.type == 'subtitles':
            return SubTrack(**data, rm_chapters=rm_chapters, _original=track.properties)
        if track.type == 'audio':
            return AudioTrack(**data, rm_chapters=rm_chapters, _original=track.properties)
        if track.type == 'video':
            return VideoTrack(**data, rm_chapters=rm_chapters, _original=track.properties)
        raise Exception("Tipo de Track no reconocido %s" % track.type)

    def __str__(self):
        kys = [str(self.source), str(self.id)]
        if self.type != 'video':
            kys.append(self.lang)
        try:
            kys.append(self.file_extension)
        except Exception:
            kys.append(self.codec)

        line = ":".join(kys)

        if self.type != 'video' and self.pixel_dimensions:
            line = line + self.pixel_dimensions
        elif self.track_name:
            line = line + " " + self.track_name
        return line

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
        if self.lang in ("zh", "chi"):
            return "Chino"
        label = MKVLANG.description.get(self.lang)
        if label:
            return label
        return self.lang

    @property
    def isLatino(self) -> bool:
        if isinstance(self, SubTrack) and self.has_file():
            for line in (self.srt_lines() or []):
                if line.text == "Subtítulos: Luciana L.B.T.":
                    return True
                if line.text == "Subtítulos: Pablo Miguel Kemmerer":
                    #TODO: No estoy seguro, revisar
                    return True
        if self.track_name is None or self.lang not in LANG_ES:
            return False
        s_tn = set(re.split(r"\b", self.track_name.lower()))
        if s_tn.intersection({'latin', 'latino', 'latinoamericano', 'latam'}):
            return True
        if self.track_name == "LRL":
            return True
        return False

    @property
    def isAudioComentario(self) -> bool:
        if self.track_name is None:
            return False
        if set({'audiocomentario', 'commentary'}).intersection(self.track_name.lower().split()):
            return True
        if self.track_name.endswith(' (Audio Description)'):
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
        if self.codec in ("DTS", "DTS-ES", "DTS-HD Master Audio", "DTS-HD High Resolution Audio"):
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
        if self.codec in ("TrueHD Atmos", "TrueHD"):
            return "TrueHD"
        if "WMV3" in self.codec:
            return "wmv"
        if self.codec in ("PCM", ):
            return "pcm"
        raise Exception(f"Extensión no encontrada para: {self.codec}")

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
        d = {k: v for k, v in self.__items__.items() if not k.startswith("_")}
        for name in dir(self.__class__):
            obj = getattr(self.__class__, name)
            if isinstance(obj, property):
                val = obj.__get__(self, self.__class__)
                d[name] = val
        return d

    def get_changes(self, mini=False) -> ChangeSet:
        chg = ChangeSet(
            language=self.lang,
            track_name=self.new_name,
            default_track=int(self.default_track),
            forced_track=int(self.type == "subtitles" and bool(self.forced_track))
        )
        if mini:
            if not self.isNewLang:
                chg.language = None
            if self._original:
                if chg.track_name == self._original.track_name:
                    chg.track_name = None
                if chg.default_track == self._original.default_track:
                    chg.default_track = None
                if chg.forced_track == self._original.forced_track:
                    chg.forced_track = None
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
        if "MPEG-4p2" in self.codec:
            lb = "MPEG-4p2"
        if "WMV3" in self.codec:
            lb = "wmv"
        if self.codec in ("AV1", "VP9"):
            lb = self.codec
        if lb is None:
            raise Exception("codec no reconocido %s" % self.codec)
        if self.pixel_dimensions:
            lb = "{} ({})".format(lb, self.pixel_dimensions)
        if self.duration is not None and self.duration.minutes > 59:
            lb = lb + " ({}m)".format(self.duration.minutes)
        return lb


class AudioTrack(Track):
    def __init__(self, *args, audio_channels: int = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.audio_channels = audio_channels

    @property
    def new_name(self) -> str:
        arr = [self.lang_name]
        if self.track_name:
            m = set(i for i in re_doblage.findall(self.track_name) if len(i) == 4)
            if len(m) == 1:
                arr.append(m.pop())
        chn = ""
        if self.audio_channels == 1:
            chn = " 1.0"
        elif self.audio_channels == 2:
            chn = " 2.0"
        elif self.audio_channels == 6:
            chn = " 5.1"
        elif self.audio_channels == 8:
            chn = " 7.1"
        arr.append("(" + self.file_extension + chn + ")")
        return " ".join(arr)


class SubTrack(Track):
    def __init__(self, *args, codec_id: str = None, text_subtitles: bool = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.codec_id = codec_id
        self.text_subtitles = text_subtitles
        self.fix_text_subtitles()

    def fix_text_subtitles(self):
        if self.has_file():
            self.text_subtitles = True
            return
        if self.text_subtitles is not None:
            return
        if self.codec_id in ("S_VOBSUB", "S_HDMV/PGS"):
            self.text_subtitles = False
            return
        raise Exception(f"No se ha podido determinar si es un subtitulo de texto {self.id}:{self.codec_id}")

    @property
    def new_name(self) -> str:
        arr = [self.lang_name]
        if self.forced_track:
            arr.append("forzados")
        if self.track_name and re.search(r"\bSDH\b", self.track_name):
            arr.append("SDH")
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

    def to_sub(self) -> Sub:
        if self.text_subtitles:
            return Sub(self.source_file)

    def srt_lines(self) -> list:
        if self.text_subtitles:
            sb = self.to_sub()
            lines = list(sb.transform("srt"))
            return lines

    @property
    def lines(self) -> int:
        if not self.has_file():
            return None
        if self.is_empty_source():
            return 0
        if self.text_subtitles:
            sb = self.to_sub()
            lines = list(sb.transform("srt"))
            if self.trim:
                for i, x in reversed(list(enumerate(lines))):
                    if x.end < (self.trim.start*1000) or x.start > (self.trim.end*1000):
                        del lines[i]
            lines = len(lines)
            return lines
        if self.source_file.endswith(".pgs"):
            pgs = PGSReader(self.source_file)
            try:
                dss = list(ds for ds in pgs.displaysets if ds.has_image)
            except InvalidSegmentError:
                return 0
            return len(dss)
        if self.source_file.endswith(".sub"):
            idx = self.source_file.rsplit(".", 1)[0] + ".idx"
            txt = read_file(idx)
            if txt is not None:
                lines = 0
                for l in txt.split("\n"):
                    if l.strip().startswith("timestamp: "):
                        if self.trim is not None:
                            h, m, s, ms = map(int, l[11:23].split(":"))
                            seg = h*60*60 + m*60 + s + (ms/1000)
                            if seg < self.trim.start or seg > self.trim.end:
                                continue
                        lines = lines + 1
                return lines

    @property
    def fonts(self) -> tuple:
        if not self.has_file():
            return None
        if not self.text_subtitles or self.is_empty_source():
            return tuple()
        sb = self.to_sub()
        return sb.fonts

    @property
    def collisions(self) -> int:
        if not (self.text_subtitles and self.has_file()):
            return None
        if self.is_empty_source() or self.lines < 2:
            return 0
        sb = self.to_sub()
        colls = list(sb.get_collisions())
        return len(colls)

    def is_srt_candidate(self):
        if self.file_extension == "srt":
            return False
        if self.text_subtitles:
            return True
        return False

    def to_srt(self, **kwargs):
        for k, v in self.__dict__.items():
            if k not in kwargs:
                kwargs[k] = v
        s = SubTrack(**kwargs)
        s.id = 0
        s.codec = "SubRip/SRT"
        s.text_subtitles = True
        sb = self.to_sub()
        s.source_file = sb.save("srt")
        return s


class Attachment(BannableItem):
    def __init__(
            self,
            *args,
            id: int = None,
            content_type: str = None,
            file_name: str = None,
            **kwargs
    ):
        super().__init__()
        self.id = id
        self.content_type = content_type
        self.file_name = file_name

    @property
    def isFont(self):
        typ = (self.content_type or '').lower()
        ext = (self.file_name or '').rsplit(".", 1)[-1].lower()
        return ext in ("ttc", ) or typ.startswith("font/") or typ in ("application/x-truetype-font", "application/vnd.ms-opentype")


class TrackIter:
    def get_tracks(self, *typeids) -> Tuple['Track']:
        ids = set()
        tys = set()
        for it in typeids:
            if isinstance(it, int):
                ids.add(it)
            else:
                tys.add(it)
        arr = []
        for t in self:
            if not isinstance(t, Track):
                raise BadType(t)
            if t.id in ids or t.type in tys:
                arr.append(t)
        return TrackTuple(arr)

    @property
    def ids(self) -> Tuple[int]:
        return tuple(sorted(map(lambda x: x.id, self)))
    
    @property
    def subtitles(self) -> Tuple['SubTrack']:
        return self.get_tracks('subtitles')

    @property
    def subtitles_not_empty(self) -> Tuple['SubTrack']:
        return tuple(s for s in self.subtitles if s.lines != 0)

    @property
    def text_subtitles(self) -> Tuple['SubTrack']:
        return tuple(s for s in self.subtitles if s.text_subtitles)

    @property
    def no_text_subtitles(self) -> Tuple['SubTrack']:
        return tuple(s for s in self.subtitles if not s.text_subtitles)

    @property
    def video(self) -> Tuple['VideoTrack']:
        return self.get_tracks('video')

    @property
    def audio(self) -> Tuple['AudioTrack']:
        return self.get_tracks('audio')

    @property
    def banned(self) -> Tuple['Track']:
        arr = []
        for i in self:
            if not isinstance(i, BannableItem):
                raise BadType(i)
            if i.banned:
                arr.append(i)
        return TrackTuple(arr)

    @property
    def no_banned(self) -> Tuple['Track']:
        arr = []
        for i in self:
            if not isinstance(i, BannableItem):
                raise BadType(i)
            if not i.banned:
                arr.append(i)
        return TrackTuple(arr)


class TrackList(List[Track], TrackIter):
    pass


class TrackTuple(Tuple[Track], TrackIter):
    pass
