import re
import subprocess
import sys
from itertools import zip_longest
from os.path import basename, isfile

from typing import List
from typing import Union
from textwrap import dedent

from .shell import Shell, Args
from .mkvutil import MkvInfo, Duration, Trim
from .track import Track, SubTrack, Attachment, TrackList, TrackTuple
from .util import LANG_ES, LANG_SB, LANG_EN, TMP, SetList, get_title, get_encoding_type, BadType
from .mkvcore import MkvCore
from .sub import Sub


def write_tags(file, **kwargs):
    with open(file, "w") as f:
        f.write(dedent('''
            <?xml version="1.0"?>
            <!-- <!DOCTYPE Tags SYSTEM "matroskatags.dtd"> -->
            <Tags>
        ''').strip()+"\n")
        for k, v in kwargs.items():
            if isinstance(v, list):
                v = "\n".join(v)
            f.write(dedent('''
              <Tag>
                <Simple>
                  <Name>{}</Name>
                  <String>{}</String>
                </Simple>
              </Tag>
            ''').strip().format(k, v)+"\n")
        f.write("</Tags>")


class Mkv:
    def __init__(self, file: str, vo: str = None, und: str = None, source: int = 0, tracks_selected: list = None, tracks_rm: list = None, trim=None):
        self.file = file
        self.__core: Union[MkvCore, None] = None
        self.__all_tracks: Union[TrackTuple, None] = None
        self.und = und
        self.vo = vo
        self.source = source
        self.tracks_selected = tracks_selected
        self.tracks_rm = tracks_rm
        self.trim = trim
        self.reset()

    def reset(self):
        self.__core = MkvCore(self.file)
        self.__all_tracks = None

    def mkvextract(self, *args, model="tracks", **kwargs):
        if len(args) > 0:
            Shell.run("mkvextract", self.file, model, *args, **kwargs)

    def mkvpropedit(self, *args, **kwargs):
        if len(args) == 0:
            return
        Shell.run("mkvpropedit", self.file, *args, **kwargs)
        self.reset()

    @property
    def duration(self) -> Duration:
        return self.__core.info.duration

    @property
    def num_chapters(self):
        return self.__core.num_chapters

    @property
    def info(self) -> MkvInfo:
        return self.__core.info

    @property
    def tags(self):
        return self.__core.tags

    @property
    def attachments(self) -> tuple[Attachment]:
        txt_sub = [c for c in self.tracks.subtitles if c.text_subtitles and c.file_extension != 'srt']
        arr = []
        for a in self.info.attachments:
            a = Attachment(**a)
            if not a.isFont:
                a.ban(f"# RM {self.source}:{a.id}:{a.content_type} {a.file_name} por no ser una fuente")
                continue
            elif len(txt_sub) == 0:
                a.ban(f"# RM {self.source}:{a.id}:{a.content_type} {a.file_name} por falta de subtitulos != srt")
                continue
            arr.append(a)
        return tuple(arr)

    @property
    def tracks(self) -> TrackTuple:
        """
        :return: Lista de Tracks no baneadas
        """
        arr = TrackList()
        for t in self.all_tracks:
            if not t.banned:
                arr.append(t)
        return TrackTuple(arr)

    @property
    def all_tracks(self):
        if self.__all_tracks is None:
            fl_name = self.file.lower()
            fl_name = set(n.strip() for n in re.split(r'(\W+)', fl_name) if n.strip())
            arr = TrackList()
            for t in self.info.tracks:
                track = Track.build(self.source, t, trim=self.trim)
                track.mkv = self
                if track.type == "video":
                    track.duration = self.duration
                    if self.vo is not None:
                        track.set_lang(self.vo)
                if track.lang in ("lat", "la"):
                    if track.track_name is None:
                        track.track_name = "Español latino"
                    elif "latino" not in track.track_name.lower():
                        track.track_name = track.track_name + " (latino)"
                    print("# lat -> spa {}".format(track))
                    track.set_lang("spa")
                if track.lang != 'spa' and track.lang in (("es-419", ) + LANG_ES):
                    print("# {} -> es {}".format(track.lang, track))
                    track.set_lang("spa")
                if track.lang != 'eng' and track.lang in ('en', 'en-US') + LANG_EN:
                    print("# {} -> eng {}".format(track.lang, track))
                    track.set_lang("eng")
                if track.isUnd and track.track_name is not None:
                    st_name = set(track.track_name.lower().split())
                    if st_name.intersection({"español", "castellano", "latino", "latam"}):
                        print("# und -> spa {}".format(track))
                        track.set_lang("spa")
                    if st_name.intersection({"ingles", "english"}):
                        print("# und -> eng {}".format(track))
                        track.set_lang("eng")
                arr.append(track)
            if len(arr.audio) == 1 and arr.audio[0].lang == 'und' and fl_name.intersection({"español", "castellano"}):
                track = arr.audio[0]
                print("# und -> spa {}".format(track))
                track.set_lang("spa")

            for track in arr:
                if track.isUnd and self.und:
                    track.set_lang(self.und)

            if len(arr.subtitles) == 1 and arr.subtitles[0].isUnd:
                track = arr.subtitles[0]
                print("# und -> es {}".format(track))
                track.set_lang("spa")

            if len(arr.audio) == 1 and arr.audio[0].isUnd and self.vo is not None:
                track = arr.audio[0]
                print("# und -> {} {}".format(self.vo, track))
                track.set_lang(self.vo)

            if len(arr.audio) == 2 and self.vo is not None and (arr.audio[0].isUnd, arr.audio[0].isUnd) == (True, True) :
                track = arr.audio[0]
                print("# und -> {} {}".format("es", track))
                track.set_lang("spa")
                track = arr.audio[1]
                print("# und -> {} {}".format(self.vo, track))
                track.set_lang(self.vo)

            isUnd = [t for t in arr if t.isUnd]
            if len(isUnd):
                print("Es necesario pasar el parámetro --und")
                for s in isUnd:
                    print("# {}".format(s))
                sys.exit()

            fls = self.extract(*arr.subtitles, stdout=subprocess.DEVNULL)
            for f, s in zip(fls, arr.subtitles):
                s.source_file = f

            if arr.subtitles_not_empty:
                sub_langs: dict[str, list[SubTrack]] = {}
                for s in arr.subtitles_not_empty:
                    if s.forced_track == 1 and s.lines > (self.duration.minutes * 7):
                        print("# FT=0 {}".format(s))
                        s.forced_track = 0
                    if s.lang not in sub_langs:
                        sub_langs[s.lang] = []
                    sub_langs[s.lang].append(s)

                for subs in sub_langs.values():
                    if len(subs) == 2:
                        s1, s2 = subs
                        if bool(s1.forced_track) != bool(s2.forced_track) and None not in (s1.lines, s2.lines):
                            if s1.forced_track:
                                s1, s2 = s2, s1
                            if s1.lines < (s2.lines / 2):
                                print("# FT=1 {}".format(s1))
                                print("# FT=0 {}".format(s2))
                                s1.forced_track = 1
                                s2.forced_track = 0
                    if any(s.forced_track for s in subs):
                        continue
                    forced_done = False
                    for s in subs:
                        if s.track_name is None:
                            continue
                        tn = s.track_name.lower()
                        if s.track_name and ("forzados" in tn or "forced" in tn) and not s.forced_track:
                            print("# FT=1 {}".format(track))
                            s.forced_track = 1
                            forced_done = True
                    if forced_done is False:
                        subs = [s for s in subs if s.lines is not None]
                        if len(subs) > 0:
                            max_forced = self.duration.minutes
                            if len(subs) > 1:
                                subs = sorted(subs, key=lambda x: x.lines)
                                max_forced = max(max_forced, subs[-1].lines)
                            if subs[0].lines < (max_forced / 2):
                                track = subs[0]
                                print("# FT=1 {}".format(track))
                                track.forced_track = 1
            audLang = set(s.lang for s in arr if s.type == 'audio')
            if not audLang.intersection(LANG_ES):
                esSub = [s for s in arr if s.type == 'subtitles' and s.lang in LANG_ES]
                if len(esSub) == 1 and esSub[0].forced_track:
                    track = esSub[0]
                    track.forced_track = 0
                    print("# FT=0 {}".format(track))
            self.__all_tracks = TrackTuple(arr)
            self.__mark_tracks_ban(self.__all_tracks)
        return self.__all_tracks

    def __mark_tracks_ban(self, tracks: TrackTuple):
        if self.tracks_selected is True:
            return
        if self.tracks_selected is not None:
            for s in tracks:
                srcid = "{}:{}".format(self.source, s.id)
                if srcid not in self.tracks_selected:
                    s.ban("# RM {}".format(s))
            return
        if isinstance(self.tracks_rm, list):
            for s in tracks:
                srcid = "{}:{}".format(self.source, s.id)
                if srcid in self.tracks_rm:
                    s.ban("# RM {} por parámetro".format(s))

        for s in tracks.audio:
            if s.isAudioComentario:
                s.ban("# RM {} por audiocomentario".format(s))
                continue
            if s.lang and s.lang not in self.main_lang:
                s.ban("# RM {} por idioma".format(s))
                continue
        for s in tracks.subtitles:
            if s.lines == 0:
                s.ban("# RM {} por estar vacio".format(s))
                continue
            #if s.lines == 1 and s.srt_lines():
            #    s.ban("# RM {} por tener una solo linea {}".format(s, s.srt_lines()[0]))
            #    continue
            if s.lang and s.lang not in self.main_lang:# or (s.lang not in set(LANG_SB).intersection(self.main_lang)):
                s.ban("# RM {} por idioma".format(s))
                continue

        for tp, lCastSpan in (
                ('audio', ("Castilian", "Spanish")),
                ('audio', ("European Spanish", "Spanish")),
                ('subtitles', ("Castilian", "Spanish")),
                ('subtitles', ("Castilian [Forced]", "Spanish [Forced]")),
                ('subtitles', ("European Spanish", "Spanish")),
                ('subtitles', ("Castilian [Full]", "Spanish [Full]")),
                ('subtitles', ("European Spanish (Forced)", "Spanish (Forced)")),
        ):
            esTrc = sorted([s for s in tracks if s.type == tp and s.lang in LANG_ES and s.track_name in lCastSpan], key=lambda x: lCastSpan.index(x.track_name))
            if tuple(x.track_name for x in esTrc) == lCastSpan:
                s = esTrc[1]
                s.ban("# RM {} por idioma (latino)".format(s))

        isSpa: dict[str, list[Track]] = dict()
        for s in tracks:
            if s.lang in LANG_ES and not(s.isLatino or s.banned):
                if s.type not in isSpa:
                    isSpa[s.type] = []
                isSpa[s.type].append(s)
        for s in tracks:
            if s.lang and s.isLatino and s.type in ('subtitles', 'audio') and len(isSpa.get(s.type, [])) > 0:
                s.ban("# RM {} por idioma (latino)".format(s))

    @property
    def main_lang(self) -> tuple:
        langs = set(LANG_ES)
        for s in self.tracks.video:
            if s.language_ietf:
                langs.add(s.language_ietf)
            if s.language:
                langs.add(s.language)
        return tuple(sorted(langs))

    def extract(self, *tracks, **kwargs) -> tuple:
        if len(tracks) == 0:
            return []
        name = basename(self.file).rsplit(".", 1)[0]
        arrg = []
        outs = []
        lastModel = None
        for track in tracks:
            if isinstance(track, Track):
                model = "tracks"
                out = f"{TMP}/{self.source}_{track.id}_{name}.{track.file_extension}"
            elif isinstance(track, Attachment):
                model = "attachments"
                out = f"{TMP}/{self.source}_{track.id}_{name}_{track.file_name}"
            else:
                raise BadType(track)
            if lastModel != model:
                arrg.append(model)
                lastModel = model
            outs.append(out)
            arrg.append(str(track.id) + ":" + out)

        cod = Shell.run("mkvextract", self.file, *arrg, **kwargs)
        if cod not in (0, 1):
            raise Exception("Error al usar mkvextract")
        return tuple(outs)

    def fix_tracks(self, mini=False, dry=False):
        arr = Args()
        title = get_title(self.file)
        if title != self.info.container.properties.title or not mini:
            arr.extend("--edit info --set")
            arr.append("title=" + title)

        defSub = None
        isAudEs = any(s for s in self.tracks.audio if s.lang in LANG_ES)
        subEs = dict(
            forc=None,
            full=None
        )
        for s in self.tracks.subtitles:
            if s.lang in LANG_ES:
                if s.forced_track and subEs['forc'] is None:
                    subEs['forc'] = s.number
                if not s.forced_track and subEs['full'] is None:
                    subEs['full'] = s.number
        if isAudEs:
            defSub = -1
            if subEs['forc'] is not None:
                defSub = subEs['forc']
        elif subEs['full'] is not None:
            defSub = subEs['full']

        doDefault = dict()
        for s in self.tracks:
            if s.type in ("video", "audio"):
                if doDefault.get(s.type) is None:
                    doDefault[s.type] = s.number
                s.default_track = int(s.number == doDefault[s.type])
            if s.type == "subtitles" and defSub is not None:
                s.default_track = int(s.number == defSub)

        for s in self.tracks:
            arr_track = Args()
            chg = s.get_changes(mini=mini)
            if chg.language is not None:
                arr_track.extend("--set language={}", chg.language)
            if chg.default_track is not None:
                arr_track.extend("--set flag-default={}", chg.default_track)
            if chg.track_name is not None:
                arr_track.extend(["--set", "name=" + chg.track_name])
            if chg.forced_track is not None:
                arr_track.extend("--set flag-forced={}", chg.forced_track)
            if arr_track:
                arr.extend("--edit track:{}", s.number)
                arr.extend(arr_track)

        self.mkvpropedit(*arr, dry=dry)

    def safe_extract(self, id):
        trg: dict[int, Track] = {}
        name = self.file.rsplit(".", 1)[0]
        for track in self.tracks:
            if track.file_extension is None:
                continue
            trg[track.id] = track
        track = trg.get(id)
        if track is None:
            print("No se puede extraer la pista", id)
            print("Las pistas disponibles son:")
            for _, track in sorted(trg.items(), key=lambda x: x[0]):
                print(track.id, (track.new_name or track.track_name),
                      "->", f"{name}.{track.file_extension}")
            return
        out = f"{track.id}:{name}.{track.file_extension}"
        self.mkvextract(out)

    def get_main_extract(self):
        isEs = False
        for a in self.tracks.audio:
            if a.lang in LANG_ES:
                isEs = True
        full = []
        forc = []
        for codec in ("SubRip/SRT", None):
            for s in self.tracks.subtitles:
                if s.lang not in LANG_ES:
                    continue
                if codec is not None and s.codec != codec:
                    continue
                if s.forced_track:
                    forc.append(s)
                else:
                    full.append(s)
        if isEs and len(forc):
            return forc[0]
        if len(full):
            return full[0]


class MkvMerge:
    def __init__(self, vo: str = None, und: str = None, dry: bool = False):
        self.vo = vo
        self.und = und
        self.dry = dry
        str(TMP)

    def mkvmerge(self, output: str, *args) -> Mkv:
        if len(args) == 0 or len(args) == 1 and args[0] == output:
            return
        Shell.run("mkvmerge", "-o", output, *args, dry=self.dry)
        if self.dry:
            return
        mkv = Mkv(output)
        mkv.fix_tracks(mini=True)
        return mkv

    def get_tracks(self, src: list[Union[Mkv, Track]]) -> TrackTuple:
        arr = []
        for s in src:
            if isinstance(s, Mkv):
                arr.extend(s.tracks)
            elif isinstance(s, Track):
                arr.append(s)
            else:
                raise BadType(s)
        return TrackTuple(arr)

    def make_order(self, src: list, main_order: list = None) -> str:
        """
        1. pista de video
        2. pistas de audio:
            1. es ac3
            2. vo ac3
            3. ** ac3
            4. es ***
            5. vo ***
            6. ** ***
        3. pistas de subtítulo:
            1. es completos
            2. es forzados
            3. vo completos
            4. vo forzados
            5. ** completos
            6. ** forzados
        """
        main_lang = set(LANG_ES)
        for s in self.get_tracks(src).video:
            if s.language_ietf:
                main_lang.add(s.language_ietf)
            if s.language:
                main_lang.add(s.language)
        main_lang = tuple(sorted(main_lang))

        def indx_s(x, *arr):
            return arr.index(x) if x in arr else len(arr)

        def sort_s(x: Track):
            return (x.source, x.number)

        orde: list[Track] = sorted(self.get_tracks(src).video, key=sort_s)
        aux: dict[str, list[Track]] = dict(
            es=[],
            mn=[],
        )
        for s in self.get_tracks(src).audio:
            if s.lang in LANG_ES:
                aux['es'].append(s)
                continue
            if s.lang in main_lang:
                aux['mn'].append(s)
                continue
            if s.lang not in aux:
                aux[s.lang] = []
            aux[s.lang].append(s)
        for k in aux.keys():
            aux[k] = sorted(aux[k], key=lambda s: (indx_s(s.file_extension, "ac3"), s.source, s.number))
        for ss in zip_longest(aux['es'], aux['mn']):
            for s in ss:
                if s is not None:
                    orde.append(s)

        hasAudEs = bool(len(aux['es']))

        def sort_s(x: SubTrack):
            return (x.source, -(x.lines or 0), x.number)
        aux: dict[str, list[Track]] = dict(
            es_ful=[],
            es_for=[],
            mn_ful=[],
            mn_for=[],
            ot_ful=[],
            ot_for=[],
        )
        for s in self.get_tracks(src).subtitles:
            if s.forced_track:
                if s.lang in LANG_ES:
                    aux['es_for'].append(s)
                    continue
                if s.lang in main_lang:
                    aux['mn_for'].append(s)
                    continue
                aux['ot_for'].append(s)
                continue
            if s.lang in LANG_ES:
                aux['es_ful'].append(s)
                continue
            if s.lang in main_lang:
                aux['mn_ful'].append(s)
                continue
            aux['ot_for'].append(s)

        for a in aux.values():
            orde.extend(sorted(a, key=sort_s))

        if main_order is not None:
            orde = sorted(orde, key=lambda s: main_order.index(f"{s.source}:{s.id}"))

        defSub = None
        if hasAudEs and aux['es_for']:
            defSub = aux['es_for'][0]
        elif not hasAudEs and aux['es_ful']:
            defSub = aux['es_ful'][0]

        defTrack = set()
        newordr = []
        for o, s in enumerate(orde):
            if s.type in ("video", "audio"):
                s.default_track = int(s.type not in defTrack)
                defTrack.add(s.type)
            elif s.type == "subtitles":
                s.default_track = int(s == defSub)
            newordr.append("{}:{}".format(s.source, s.id))

        return newordr

    def merge(self, output: str, *files: str, tracks_selected: list = None, tracks_rm: list = None, do_srt: int = -1, do_trim:str = None, no_chapters:bool = False) -> Mkv:
        src: List[Union[Mkv, Track]] = []
        fl_chapters = None
        lg_chapters = None
        fl_tags = None
        cm_tag = SetList()
        trim: Trim = None
        if do_trim:
            def to_sec(s):
                h, m, s = map(float, s.split(":"))
                return h*60*60 + m*60 + s
            start, end = map(to_sec, do_trim.split('-'))
            trim = Trim(start=start, end=end)

        for f in files:
            if basename(f) in ("chapters.xml", "chapters.txt"):
                fl_chapters = f
                continue
            m = re.match(r"^chapters.(\w+).txt$", basename(f))
            if m:
                fl_chapters = f
                lg_chapters = m.group(1)
                continue
            if basename(f) == "tags.xml":
                fl_tags = f
                continue
            ext = f.rsplit(".", 1)[-1].lower()
            if ext in ("mkv", "mp4", "avi"):
                mkv = Mkv(
                    f,
                    source=len(src),
                    und=self.und,
                    vo=self.vo,
                    tracks_selected=tracks_selected,
                    tracks_rm=tracks_rm,
                    trim=trim
                )
                src.append(mkv)
                cm_tag.extend(mkv.tags.get_tag('COMMENT', split_lines=True))
            else:
                track = Track.build(len(src), f, trim=trim)
                src.append(track)

        videos = self.get_tracks(src).video
        if len(videos) > 1:
            pxd: dict[int, dict[int, list[Track]]] = {}
            for v in videos:
                h, w = map(int, v.pixel_dimensions.split("x"))
                if w not in pxd:
                    pxd[w] = {}
                if h not in pxd[w]:
                    pxd[w][h] = []
                pxd[w][h].append(v)
            mx_w = max(pxd.keys())
            mn_h = min(pxd[mx_w].keys())
            main_video = pxd[mx_w][mn_h][0]
            print("# OK {}".format(main_video))
            for i, s in enumerate(src):
                if i != main_video.source and isinstance(s, Mkv):
                    for v in s.tracks.video:
                        v.ban("# KO {}".format(v))

        subtitles = self.get_tracks(src).subtitles

        if len(subtitles) == 1 and subtitles[0].isUnd:
            subtitles[0].set_lang("spa")

        sub_langs: dict[str, list[SubTrack]] = {}
        for s in subtitles:
            if s.lang not in sub_langs:
                sub_langs[s.lang] = []
            sub_langs[s.lang].append(s)

        for subs in sub_langs.values():
            if any(s.forced_track for s in subs):
                continue
            subs = [s for s in subs if s.text_subtitles]
            if len(subs) > 1:
                subs = sorted(subs, key=lambda x: x.lines)
                if subs[0].lines < (subs[-1].lines / 2):
                    track = subs[0]
                    print("# FT=1 {}".format(track))
                    track.forced_track = 1

        si_text = self.get_tracks(src).text_subtitles
        no_text = self.get_tracks(src).no_text_subtitles
        si_text = set((s.lang, s.forced_track) for s in si_text)
        for s in no_text:
            if (s.lang, s.forced_track) in si_text and s.mkv:
                s.ban("# RM {} por existir alternativa en texto".format(s))

        for s in self.get_tracks(src).subtitles:
            if not s.is_srt_candidate() or None in (s.source_file, s.mkv, s.collisions):
                continue
            if s.collisions <= do_srt:
                src.append(s.to_srt(source=len(src)))
                s.ban("# MV {} convertido a SRT".format(s))
                continue
            print("# ¡! {} podría ser convertido a SRT ({collisions} colisiones)".format(s, collisions=s.collisions))
        # for s in self.get_tracks(src).text_subtitles:
        #    if s.file_extension == "srt" and s.to_sub().isImprovable:
        #        src.append(s.to_srt(source=len(src)))
        #        s.ban("# MV {} limpiado SRT".format(s))
        #        continue

        newordr = self.make_order(src, main_order=tracks_selected)

        arr = Args()
        arr.extend(["--title", get_title(output)])
        for s in src:
            if isinstance(s, Mkv):
                mkv = s
                if mkv.all_tracks.video.banned:
                    nop = ",".join(map(str, mkv.all_tracks.video.banned.ids))
                    arr.extend("-d !{}", nop)
                if mkv.all_tracks.subtitles.banned:
                    nop = ",".join(map(str, mkv.all_tracks.subtitles.banned.ids))
                    arr.extend("-s !{}", nop)
                if mkv.all_tracks.audio.banned:
                    nop = ",".join(map(str, mkv.all_tracks.audio.banned.ids))
                    arr.extend("-a !{}", nop)
                if len(mkv.attachments) == 0:
                    arr.append("--no-attachments")
                elif len(mkv.attachments) < len(mkv.info.attachments):
                    sip = ",".join(map(str, sorted(a.id for a in mkv.attachments)))
                    arr.extend("-m {}", sip)
                if no_chapters or (fl_chapters is not None or mkv.num_chapters == 1 or len(mkv.tracks.video) == 0):
                    arr.extend("--no-chapters")
                for t in sorted(mkv.tracks, key=lambda x: newordr.index(f"{x.source}:{x.id}")):
                    chg = t.get_changes()
                    arr.extend("--language {}:{}", t.id, chg.language)
                    arr.extend("--default-track {}:{}", t.id, chg.default_track)
                    arr.extend("--forced-track {}:{}", t.id, chg.forced_track)
                    arr.extend(["--track-name", "{}:{}".format(t.id, chg.track_name)])
                arr.append(mkv.file)
            else:
                chg = s.get_changes()
                arr.extend("--language {}:{}", s.id, chg.language)
                arr.extend("--default-track {}:{}", s.id, chg.default_track)
                arr.extend("--forced-track {}:{}", s.id, chg.forced_track)
                arr.extend(["--track-name", "{}:{}".format(s.id, chg.track_name)])
                if no_chapters or s.rm_chapters:
                    arr.extend("--no-chapters")
                if s.type == 'subtitles':
                    arr.extend("--sub-charset {}:{}", s.id, get_encoding_type(s.source_file))
                arr.append(s.source_file)

        if fl_chapters is not None:
            if lg_chapters is not None:
                arr.extend(["--chapter-language", lg_chapters])
            arr.extend(["--chapters", fl_chapters])

        if fl_tags is None:
            fl_tags = TMP + "/tags.xml"
            cm_tag.extend((basename(a) for a in arr if isfile(a)))
            write_tags(fl_tags, COMMENT=cm_tag)

        if do_trim:
            arr.extend(["--split", "parts:"+do_trim])

        arr.extend(["--global-tags", fl_tags])

        arr.extend("--track-order " + ",".join(newordr))

        mkv = self.mkvmerge(output, *arr)
        if self.dry or mkv is None:
            return

        print("#", mkv.info.container.properties.title)
        for t in mkv.tracks:
            print(f"# {t.id}:{t.language} {t.track_name}")
        return mkv
