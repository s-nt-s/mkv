import re
import subprocess
import sys
from itertools import zip_longest
from os.path import basename

import xmltodict
from munch import DefaultMunch, Munch

from .shell import Shell, Args
from .track import Track
from .util import LANG_ES, TMP, get_title, get_encoding_type, my_filter


class Duration:
    def __init__(self, nano):
        self.nano = nano

    @property
    def seconds(self):
        return self.nano / 1000000000

    @property
    def minutes(self):
        return round(self.seconds / 60)

    def __eq__(self, other):
        return self.nano == other.nano


class Mkv:
    def __init__(self, file: str, vo: str = None, und: str = None, source: int = 0, tracks_selected: list = None):
        self.file = file
        self._core = DefaultMunch()
        self.und = und
        self.vo = vo
        self.source = source
        self.tracks_selected = tracks_selected

    def mkvextract(self, *args, model="tracks", **kwargs):
        if len(args) > 0:
            Shell.run("mkvextract", self.file, model, *args, **kwargs)

    def mkvpropedit(self, *args, **kwargs):
        if len(args) == 0:
            return
        Shell.run("mkvpropedit", self.file, *args, **kwargs)
        self._core = DefaultMunch()

    @property
    def extension(self) -> str:
        return self.file.rsplit(".")[-1].lower()

    @property
    def duration(self):
        d = self._core.info.container.properties.duration
        if d is None:
            arr = "ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1".split()
            arr.append(self.file)
            d = Shell.get(*arr, do_print=False)
            d = float(d) * 1000000000
        return Duration(d)

    @property
    def info(self) -> Munch:
        if self._core.info is None:
            self._core.info = Shell.mkvinfo(self.file)
        return self._core.info

    @property
    def attachments(self) -> tuple:
        arr = []
        for a in self.info.attachments:
            if a.id in self.ban.attachments:
                continue
            arr.append(a)
        return tuple(arr)

    @property
    def num_chapters(self):
        ch = 0
        for c in self.info.get("chapters", []):
            ch = c.get("num_entries", 0)
        return ch

    @property
    def chapters(self):
        if self.num_chapters == 0:
            return None
        if self._core.chapters is None:
            out = Shell.get("mkvextract", "chapters", self.file)
            out = out.strip()
            if len(out) == 0:
                self._core.chapters = dict()
            else:
                self._core.chapters = xmltodict.parse(out.strip())
        return self._core.chapters

    @property
    def main_lang(self) -> tuple:
        langs = set(LANG_ES)
        for s in self.tracks:
            if s.type == 'video':
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
                out = "{tmp}/{src}_{id}_{name}.{file_extension}".format(name=name, tmp=TMP, src=self.source,
                                                                        **track.to_dict())
            else:
                model = "attachments"
                out = "{tmp}/{src}_{id}_{name}_{file_name}".format(name=name, tmp=TMP, src=self.source, **dict(track))
            if lastModel != model:
                arrg.append(model)
                lastModel = model
            outs.append(out)
            arrg.append(str(track.id) + ":" + out)

        Shell.run("mkvextract", self.file, *arrg, **kwargs)
        return tuple(outs)

    @property
    def tracks(self) -> tuple:
        """
        :return: Lista de Track no baneadas
        """
        fl_name = self.file.lower()
        fl_name = set(n.strip() for n in re.split(r'(\W+)', fl_name) if n.strip())
        if self._core.tracks is None:
            arr = []
            for t in self.info.tracks:
                track = Track.build(self.source, t)
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
                    print("# {source}:{id} {track_name}: lat -> es".format(**dict(track)))
                    track.set_lang("spa")
                if track.isUnd and track.track_name is not None:
                    st_name = set(track.track_name.lower().split())
                    if st_name.intersection({"español", "castellano", "latino"}):
                        print("# {source}:{id} {track_name}: und -> es".format(**dict(track)))
                        track.set_lang("spa")
                    if st_name.intersection({"ingles", "english"}):
                        print("# {source}:{id} {track_name}: und -> en".format(**dict(track)))
                        track.set_lang("spa")
                arr.append(track)
            isAud = [t for t in arr if t.type == 'audio']
            if len(isAud) == 1 and isAud[0].lang == 'und' and fl_name.intersection({"español", "castellano"}):
                track = isAud[0]
                print("# {source}:{id} {track_name}: und -> es".format(**dict(track)))
                track.set_lang("spa")
            for track in arr:
                if track.isUnd and self.und:
                    track.set_lang(self.und)
            isUnd = [t for t in arr if t.isUnd]
            if len(isUnd):
                print("Es necesario pasar el parámetro --und")
                for s in isUnd:
                    print("# {source}:{id} {track_name} {codec}".format(**dict(s)))
                sys.exit()

            sub_trck = [s for s in arr if s.type == "subtitles"]
            att_font = [a for a in self._core.info.get("attachments", []) if
                        a.get('content_type') in ("application/x-truetype-font", "application/vnd.ms-opentype")]
            fls = self.extract(*sub_trck, *att_font, stdout=subprocess.DEVNULL)
            for f, s in zip(fls, sub_trck + att_font):
                if isinstance(s, Track):
                    s.source_file = f
                else:
                    out = Shell.safe_get("otfinfo", "--info", f, do_print=False, stderr=subprocess.DEVNULL)
                    if out is None:
                        continue
                    s.font = out.strip().split("\n")[0].split(":")[1].strip()

            subtitles = [s for s in arr if s.type == "subtitles" and s.lines != 0]
            if subtitles:
                sub_langs = {}
                for s in subtitles:
                    if s.lang not in sub_langs:
                        sub_langs[s.lang] = []
                    sub_langs[s.lang].append(s)

                for subs in sub_langs.values():
                    if any(s.forced_track for s in subs):
                        continue
                    forced_done = False
                    for s in subs:
                        if s.track_name is None:
                            continue
                        tn = s.track_name.lower()
                        if s.track_name and ("forzados" in tn or "forced" in tn) and not s.forced_track:
                            print("# {source}:{id} {track_name}: forced_track=1".format(**dict(track)))
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
                                print("# {source}:{id} {track_name}: forced_track=1".format(**dict(track)))
                                track.forced_track = 1
            audLang = set(s.lang for s in arr if s.type == 'audio')
            if not audLang.intersection(LANG_ES):
                esSub = [s for s in arr if s.type == 'subtitles' and s.lang in LANG_ES]
                if len(esSub) == 1 and esSub[0].forced_track:
                    s = esSub[0]
                    s.forced_track = 0
                    print("# {source}:{id} {track_name}: forced_track=0".format(**dict(track)))
            self._core.tracks = arr

        arr = []
        ban = set().union(self.ban.audio, self.ban.subtitles, self.ban.video)
        for t in self._core.tracks:
            if t.id in ban:
                continue
            arr.append(t)
        return tuple(arr)

    @property
    def ban(self) -> Munch:
        if self._core.ban is None:
            self._core.ban = Munch(
                audio=set(),
                subtitles=set(),
                video=set(),
                attachments=set()
            )
            if self.tracks_selected is True:
                return
            for s in self._core.tracks:
                if self.tracks_selected is not None:
                    srcid = "{}:{}".format(self.source, s.id)
                    if srcid not in self.tracks_selected:
                        print("# RM {} {track_name} {lang} {codec}".format(srcid, lang=s.lang, **dict(s)))
                        self._core.ban[s.type].add(s.id)
                    continue
                if s.type not in ('audio', 'subtitles'):
                    continue
                if s.type == 'subtitles' and s.lines == 0:
                    print("# RM {source}:{id}:{file_extension} {track_name} por estar vacio".format(**s.to_dict()))
                    self._core.ban.subtitles.add(s.id)
                    continue
                if s.lang and (s.isLatino or s.lang not in self.main_lang):
                    latino = " - latino" if s.isLatino else ""
                    if s.type == 'subtitles':
                        self._core.ban.subtitles.add(s.id)
                        print("# RM {source}:{id}:{file_extension} {track_name} por idioma ({lang}{latino})".format(
                            latino=latino,
                            **s.to_dict()))
                    if s.type == 'audio':
                        self._core.ban.audio.add(s.id)
                        print("# RM {source}:{id}:{file_extension} {track_name} por idioma ({lang}{latino})".format(
                            latino=latino,
                            **s.to_dict()))

            txt_sub = [c for c in self._core.tracks if
                       c.type == "subtitles" and c.text_subtitles and c.file_extension != 'srt' and c.id not in self._core.ban.subtitles]

            fonts = set()
            for s in txt_sub:
                if s.fonts is not None:
                    fonts = fonts.union(s.fonts)

            for a in self.info.attachments:
                if len(txt_sub) == 0 or a.get('content_type') not in (
                        "application/x-truetype-font", "application/vnd.ms-opentype"):
                    self.ban.attachments.add(a.id)
                    print("# RM {}:{id}:{content_type} {file_name} por tipo o falta de subtitulos != srt".format(
                        self.source, **a))
                elif a.font is not None:
                    sp_font = a.font.split()
                    sp_font = [" ".join(sp_font[:i]) for i in range(1, len(sp_font) + 1)]
                    if not fonts.intersection(sp_font):
                        self.ban.attachments.add(a.id)
                        print("# RM {}:{id}:{content_type} {file_name} {font} por no usarse en subtitulos".format(
                            self.source, **a))

        return self._core.ban

    def get_tracks(self, *typeids) -> tuple:
        ids = set()
        tys = set()
        for it in typeids:
            if isinstance(it, int):
                ids.add(it)
            else:
                tys.add(it)
        arr = []
        for t in self.tracks:
            if t.id in ids or t.type in tys:
                arr.append(t)
        return tuple(arr)

    def fix_tracks(self, mini=False, dry=False):
        arr = Args()
        title = get_title(self.file)
        if title != self.info.container.properties.title or not mini:
            arr.extend("--edit info --set")
            arr.append("title=" + title)

        defSub = None
        isAudEs = any(s for s in self.get_tracks('audio') if s.lang in LANG_ES)
        subEs = DefaultMunch()
        for s in self.get_tracks('subtitles'):
            if s.lang in LANG_ES:
                if s.forced_track and subEs.forc is None:
                    subEs.forc = s.number
                if not s.forced_track and subEs.full is None:
                    subEs.full = s.number
        if isAudEs:
            defSub = -1
            if subEs.forc is not None:
                defSub = subEs.forc
        elif subEs.full is not None:
            defSub = subEs.full

        doDefault = DefaultMunch()
        for s in self.tracks:
            if s.type in ("video", "audio"):
                if doDefault[s.type] is None:
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
        trg = {}
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
                      "->", "{}.{}".format(name, track.file_extension))
            return
        out = "{0}:{1}.{2}".format(track.id, name, track.file_extension)
        self.mkvextract(out)

    def sub_extract(self):
        isEs = False
        for a in self.get_tracks('audio'):
            if a.lang in LANG_ES:
                isEs = True
        full = None
        forc = None
        for s in self.get_tracks('subtitles'):
            if s.codec == "SubRip/SRT" and s.lang in LANG_ES:
                if s.forced_track:
                    forc = s
                else:
                    full = s
        track = None
        if isEs and forc:
            track = forc
        if track is None and full:
            track = full
        if track is not None:
            name = self.file.rsplit(".", 1)[0]
            out = "{0}:{1}.{2}".format(track.id, name, track.file_extension)
            print("# Para extraer el subtítulo principal haz:")
            print("$", Shell.to_str("mkvextract", "tracks", self.file, out))


class MkvMerge:
    def __init__(self, vo: str = None, und: str = None, dry: bool = False):
        self.vo = vo
        self.und = und
        self.dry = dry
        str(TMP)

    def mkvmerge(self, output: str, *args) -> Mkv:
        if len(args) == 0 or len(args) == 1 and args[0] == self.file:
            return
        Shell.run("mkvmerge", "-o", output, *args, dry=self.dry)
        if self.dry:
            return
        mkv = Mkv(output)
        mkv.fix_tracks(mini=True)
        return mkv

    def get_tracks(self, typ: str, src: list) -> tuple:
        arr = []
        for s in src:
            if isinstance(s, Mkv):
                arr.extend(s.get_tracks(typ))
            elif s.type == typ:
                arr.append(s)
        return tuple(arr)

    def get_extract(self, src: list, track: list) -> tuple:
        arr = []
        sources = sorted(set(s.source for s in track))
        for s in sources:
            t = sorted((t for t in track if t.source == s), key=lambda x: x.id)
            s = src[s]
            if isinstance(s, Mkv):
                fls = s.extract(*t)
                arr.extend(list(zip(t, fls)))
            else:
                arr.append((s, s.source_file))
        return tuple(arr)

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
        for s in self.get_tracks('video', src):
            if s.language_ietf:
                main_lang.add(s.language_ietf)
            if s.language:
                main_lang.add(s.language)
        main_lang = tuple(sorted(main_lang))

        indx_s = lambda x, *arr: arr.index(x) if x in arr else len(arr)
        sort_s = lambda x: (x.source, -(x.lines or 0), x.number)
        orde = sorted(self.get_tracks('video', src), key=sort_s)
        aux = Munch(
            es=[],
            mn=[],
        )
        for s in self.get_tracks('audio', src):
            if s.lang in LANG_ES:
                aux.es.append(s)
                continue
            if s.lang in main_lang:
                aux.mn.append(s)
                continue
            if s.lang not in aux:
                aux[s.lang] = []
            aux[s.lang].append(s)
        for k in aux.keys():
            aux[k] = sorted(aux[k], key=lambda s: (indx_s(s.file_extension, "ac3"), s.source, s.number))
        for ss in zip_longest(aux.es, aux.mn):
            for s in ss:
                if s is not None:
                    orde.append(s)

        hasAudEs = bool(len(aux.es))

        sort_s = lambda x: (x.source, -(x.lines or 0), x.number)
        aux = Munch(
            es_ful=[],
            es_for=[],
            mn_ful=[],
            mn_for=[],
            ot_ful=[],
            ot_for=[],
        )
        for s in self.get_tracks('subtitles', src):
            if s.forced_track:
                if s.lang in LANG_ES:
                    aux.es_for.append(s)
                    continue
                if s.lang in main_lang:
                    aux.mn_for.append(s)
                    continue
                aux.ot_for.append(s)
                continue
            if s.lang in LANG_ES:
                aux.es_ful.append(s)
                continue
            if s.lang in main_lang:
                aux.mn_ful.append(s)
                continue
            aux.ot_for.append(s)

        for a in aux.values():
            orde.extend(sorted(a, key=sort_s))

        if main_order is not None:
            orde = sorted(orde, key=lambda s: main_order.index("{source}:{id}".format(**dict(s))))

        defSub = None
        if hasAudEs and aux.es_for:
            defSub = aux.es_for[0]
        elif not hasAudEs and aux.es_ful:
            defSub = aux.es_ful[0]

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

    def merge(self, output: str, *files: Track, tracks_selected: list = None) -> Mkv:
        src = []
        fl_chapters = None
        for f in files:
            if basename(f) == "chapters.xml":
                fl_chapters = f
                continue
            ext = f.rsplit(".", 1)[-1].lower()
            if ext in ("mkv", "mp4", "avi"):
                mkv = Mkv(f, source=len(src), und=self.und, vo=self.vo, tracks_selected=tracks_selected)
                src.append(mkv)
            else:
                track = Track.build(len(src), f)
                src.append(track)

        videos = self.get_tracks('video', src)
        if len(videos) > 1:
            pxd = {}
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
            print("# OK {source}:{id} {pixel_dimensions}".format(**main_video))
            for i, s in enumerate(src):
                if i != main_video.source and isinstance(s, Mkv):
                    for v in s.get_tracks('video'):
                        print("# KO {source}:{id} {pixel_dimensions}".format(**v))
                        s.ban.video.add(v.id)

        subtitles = self.get_tracks('subtitles', src)

        if len(subtitles) == 1 and subtitles[0].isUnd:
            subtitles[0].set_lang("spa")

        sub_langs = {}
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
                    print("# {source}:{id} {track_name}: forced_track=1".format(**dict(track)))
                    track.forced_track = 1

        si_text, no_text = my_filter(self.get_tracks('subtitles', src), lambda s: s.text_subtitles)
        si_text = set((s.lang, s.forced_track) for s in si_text)
        for s in no_text:
            if (s.lang, s.forced_track) in si_text and s.mkv:
                print("# RM {source}:{id}:{file_extension} {new_name} por existir alternativa en texto".format(
                    **s.to_dict()))
                s.mkv.ban[s.type].add(s.id)

        for s in self.get_tracks('subtitles', src):
            if s.is_srt_candidate():
                print(
                    "# ¡! {source}:{id}:{file_extension} {new_name} podría ser convertido a SRT ({collisions} colisiones)".format(
                        **s.to_dict()))

        newordr = self.make_order(src, main_order=tracks_selected)

        arr = Args()
        arr.extend(["--title", get_title(output)])
        for s in src:
            if isinstance(s, Mkv):
                mkv = s
                if mkv.ban.video:
                    nop = ",".join(map(str, sorted(mkv.ban.video)))
                    arr.extend("-d !{}", nop)
                if mkv.ban.subtitles:
                    nop = ",".join(map(str, sorted(mkv.ban.subtitles)))
                    arr.extend("-s !{}", nop)
                if mkv.ban.audio:
                    nop = ",".join(map(str, sorted(mkv.ban.audio)))
                    arr.extend("-a !{}", nop)
                if len(mkv.ban.attachments) == 0:
                    pass
                if len(mkv.attachments) == 0:
                    arr.append("--no-attachments")
                elif len(mkv.attachments) < len(mkv.info.attachments):
                    sip = ",".join(map(str, sorted(a.id for a in mkv.attachments)))
                    arr.extend("-m {}", sip)
                if fl_chapters is not None or mkv.num_chapters == 1 or len(mkv.get_tracks('video'))==0:
                    arr.extend("--no-chapters")
                for t in sorted(mkv.tracks, key=lambda x: newordr.index("{source}:{id}".format(**dict(x)))):
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
                if s.rm_chapters:
                    arr.extend("--no-chapters")
                if s.type == 'subtitles':
                    arr.extend("--sub-charset {}:{}", s.id, get_encoding_type(s.source_file))
                arr.append(s.source_file)

        if fl_chapters is not None:
            arr.extend(["--chapters", fl_chapters])
        arr.extend("--track-order " + ",".join(newordr))
        mkv = self.mkvmerge(output, *arr)
        if self.dry:
            return

        print("#", mkv.info.container.properties.title)
        for t in mkv.tracks:
            print("# {id}:{language} {track_name}".format(**dict(t)))
        mkv.sub_extract()
        return mkv
