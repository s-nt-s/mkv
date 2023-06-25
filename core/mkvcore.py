from typing import List
from .mkvutil import MkvInfo, MkvChapter, MkvTags
from functools import cached_property
from dataclasses import dataclass


@dataclass(frozen=True)
class MkvCore:
    file: str

    @cached_property
    def info(self):
        return MkvInfo.build(self.file)
    
    @cached_property
    def tags(self):
        if self.extension not in ("mkv",):
            return MkvTags()
        return MkvTags.build(self.file, do_print=False)

    @cached_property
    def num_chapters(self):
        if len(self.info.chapters) == 0:
            return 0
        return self.info.chapters[-1].num_entries
    
    @cached_property
    def chapters(self):
        if self.num_chapters == 0:
            return None
        return MkvChapter.build(self.file, do_print=False)

    @cached_property
    def extension(self) -> str:
        return self.file.rsplit(".")[-1].lower()

    @property
    def duration(self):
        return self.info.duration
