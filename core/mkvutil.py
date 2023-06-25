from .shell import Shell, Args
import json
import xmltodict
from typing import Tuple, NamedTuple, List


class Trim(NamedTuple):
    start: float
    end: float


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


class MkvInfo(dict):

    @staticmethod
    def build(file, **kwargs):
        arr = Args()
        arr.extend("mkvmerge -J")
        arr.append(file)
        js = Shell.get(*arr, **kwargs)
        js = json.loads(js)
        info = MkvInfo(**js)
        return info

    @property
    def tracks(self):
        return tuple(map(MkvInfoTrack, self['tracks']))

    @property
    def container(self):
        return MkvInfoContainer(self['container'])

    @property
    def attachments(self):
        return tuple(map(MkvInfoAttachment, self['attachments']))

    @property
    def chapters(self):
        return tuple(map(MkvInfoChapter, self.get('chapters', [])))

    @property
    def file_name(self):
        return self['file_name']

    @property
    def duration(self) -> Duration:
        if self.container.properties.duration is not None:
            return Duration(self.container.properties.duration)
        arr = "ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1".split()
        arr.append(self.file_name)
        d = Shell.get(*arr, do_print=False)
        d = float(d) * 1000000000
        return Duration(d)


class MkvInfoChapter(dict):
    @property
    def num_entries(self) -> int:
        return self.get("num_entries", 0)


class MkvInfoAttachment(dict):

    @property
    def id(self) -> int:
        return self['id']

    @property
    def content_type(self) -> str:
        return self.get('content_type')

    @property
    def file_name(self) -> str:
        return self.get('file_name')


class MkvInfoTrack(dict):
    @property
    def type(self) -> str:
        return self['type']

    @property
    def properties(self):
        return MkvInfoTrackProperties(self['properties'])

    @property
    def id(self):
        return self['id']

    @property
    def codec(self):
        return self['codec']


class MkvInfoTrackProperties(dict):
    @property
    def language(self) -> str:
        return self['language']

    @property
    def track_name(self) -> str:
        return self['track_name']

    @property
    def default_track(self):
        return int(self.get("default_track", 0))

    @property
    def forced_track(self):
        return int(self.get("forced_track", 0))


class MkvInfoContainer(dict):    
    @property
    def properties(self):
        return MkvInfoContainerProperties(self['properties'])


class MkvInfoContainerProperties(dict):

    @property
    def duration(self) -> float:
        return self.get('duration')

    @property
    def title(self) -> str:
        return self.get('title')


class MkvChapter(dict):

    @staticmethod
    def build(file, **kwargs):
        out = Shell.get("mkvextract", "chapters", file, **kwargs)
        out = out.strip()
        if len(out) == 0:
            return MkvChapter()
        js = xmltodict.parse(out)
        return MkvChapter(**js)


class MkvTags(dict):

    @staticmethod
    def build(file, **kwargs):
        out = Shell.get("mkvextract", "tags", file, **kwargs)
        out = out.strip()
        if len(out) == 0:
            return MkvTags()
        js = xmltodict.parse(out)
        return MkvTags(**js)

    def get_tag(self, name, split_lines=False) -> Tuple[str]:
        def get_arr(dct, field):
            if dct is None:
                return []
            value = dct.get(field)
            if value is None:
                return []
            if not isinstance(value, list):
                return [value]
            return value

        r_vals = []
        for tag in get_arr(self.get("Tags"), 'Tag'):
            for s in get_arr(tag, 'Simple'):
                if s.get('Name') != name:
                    continue
                vals = s.get('String')
                if vals is None:
                    continue
                vals = vals.strip()
                if split_lines:
                    vals = vals.split("\n")
                else:
                    vals = [vals]
                for val in vals:
                    val = val.strip()
                    if len(val) > 0 and val not in r_vals:
                        r_vals.append(val)
        return tuple(r_vals)

