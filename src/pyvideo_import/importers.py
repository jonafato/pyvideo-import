from __future__ import annotations

import datetime
import json
import re
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

from git import Repo
import frontmatter
import requests
from slugify import slugify
import jq
import yaml
import yt_dlp
from thefuzz import fuzz


# Use Django's JSONEncoder for some serialization and transformation
class DjangoJSONEncoder(json.JSONEncoder):
    """
    JSONEncoder subclass that knows how to encode date/time, decimal types, and
    UUIDs.
    """

    def default(self, o):
        # See "Date Time String Format" in the ECMA-262 specification.
        if isinstance(o, datetime.datetime):
            r = o.isoformat()
            if o.microsecond:
                r = r[:23] + r[26:]
            if r.endswith("+00:00"):
                r = r.removesuffix("+00:00") + "Z"
            return r
        elif isinstance(o, datetime.date):
            return o.isoformat()
        elif isinstance(o, datetime.time):
            if is_aware(o):
                raise ValueError("JSON can't represent timezone-aware times.")
            r = o.isoformat()
            if o.microsecond:
                r = r[:12]
            return r
        elif isinstance(o, datetime.timedelta):
            return duration_iso_string(o)
        elif isinstance(o, (decimal.Decimal, uuid.UUID, Promise)):
            return str(o)
        else:
            return super().default(o)


class YouTubeLinkBackfiller:
    def __init__(self, conference_name: str, url: str) -> None:
        self.conference_name = conference_name
        self.url = url
        self._data = None

    def fetch_data(self) -> dict[str, Any]:
        if not self._data:
            # TODO: this needs some actual logic for caching responses
            # based on URL, not a single global file that must be managed manually.
            cache_file = "/tmp/ytlbf.json"
            if Path(cache_file).exists():
                with open(cache_file) as f:
                    self._data = json.load(f)
            else:
                with yt_dlp.YoutubeDL({"ignoreerrors": True, "quiet": True}) as client:
                    self._data = client.extract_info(self.url, download=False)
                with open(cache_file, "w") as f:
                    json.dump(self._data, f)
        return self._data

    def backfill_video_url(self, obj: dict[str, Any]) -> dict[str, Any]:
        modified_talk_title = re.sub(r"[^\w]", "", obj["title"]).lower()

        data = self.fetch_data()
        for entry in data['entries']:
            if not entry:
                # It seems that sometimes the entries are None.
                # This may be due to private videos returning error responses.
                continue
            modified_video_title = entry["title"]
            modified_video_title = modified_video_title.replace(self.conference_name, "")
            for speaker_name in obj["speakers"]:
                modified_video_title = modified_video_title.replace(speaker_name, "")
            modified_video_title = re.sub(r"[^\w]", "", modified_video_title).lower()

            if fuzz.ratio(modified_talk_title, modified_video_title) > 75:
                obj["videos"] = [{
                    "type": "youtube",
                    "url": entry["webpage_url"],
                }]
                obj["thumbnail_url"] = (
                    "https://i.ytimg.com/vi/" +
                    entry["webpage_url"].split("v=")[1] +
                    "/hqdefault.jpg"
                )
                break
        return obj


class Conference:
    def __init__(
        self,
        *,
        name: str,
        downloader: Callable,
        transformer: Callable,
    ) -> None:
        self.name = name
        self.downloader = downloader
        self.transformer = transformer

    def pyvidify(self, output_directory: str) -> None:
        with TemporaryDirectory() as tmpdir:
            self.downloader.download(tmpdir)
            self.transformer.transform(tmpdir, output_directory)


class GitDownloader:
    def __init__(self, remote: str, ref: str = None) -> None:
        self.remote = remote
        self.ref = ref

    def download(self, directory: str) -> None:
        Repo.clone_from(self.remote, directory, branch=self.ref, depth=1)


class JSONAPIDownloader:
    def __init__(self, url: str, save_as="response.json") -> None:
        self.url = url
        self.save_as = save_as

    def download(self, directory: str) -> str:
        response = requests.get(self.url)
        filename = (Path(directory) / self.save_as)
        with open(filename, "w") as f:
            f.write(response.text)
        return filename


class YouTubeDownloader:
    def __init__(self, url: str) -> None:
        self.url = url

    def download(self, directory: str) -> None:
        raise NotImplementedError


class BaseTransformer:
    def __init__(
        self,
        *,
        conference_name: str,
        filter_func: Callable = None,
        postprocess: Callable | list[Callable] = None,
    ) -> None:
        # required_keys = {"title", "speakers"}
        # if (missing_keys := required_keys - set(key_map.keys())):
        #     raise ValueError(f"Missing keys: {missing_keys}")

        self.conference_name = conference_name
        self.filter_func = filter_func
        self.postprocess = postprocess

    def transform(self, input_directory: str, output_directory: str) -> None:
        """Transform the data and write it to the specified output directory.

        Args:
            input_directory: The source of the frontmatter files. This directory
                should be managed by a `Conference` object and will often contain
                a git checkout containing static site generator source files.
            output_directory: The directory that this transformer should write the
                PyVideo JSON files into.
        """
        outdir = Path(output_directory)
        outdir.mkdir()
        (outdir / "videos").mkdir()
        with open((outdir / "category.json"), "w") as f:
            json.dump({"title": self.conference_name}, f, indent=4)

        for video_json in self.extract_talk_list(input_directory):
            slug = slugify(video_json["title"])
            outfile = (outdir / "videos" / slug).with_suffix(".json")
            with open(outfile, "w") as f:
                json.dump(video_json, f, indent=4, sort_keys=True, cls=DjangoJSONEncoder)

    def extract_talk_list(self) -> list[dict[str, Any]]:
        pass


class JSONTransformer(BaseTransformer):
    def __init__(
        self,
        jq_filter: str,
        filepath: str,
        talk_list_filter: str = None,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.jq_filter = jq_filter
        self.filepath = filepath
        self.talk_list_filter = talk_list_filter
        self.load = json.load

    def extract_talk_list(self, input_directory: str):
        talk_list = []
        with open((Path(input_directory) / self.filepath)) as f:
            videos = self.load(f)

        if self.talk_list_filter is not None:
            videos = jq.all(
                self.talk_list_filter,
                text=json.dumps(videos, cls=DjangoJSONEncoder),
            )

        for video in videos:
            if self.filter_func and not self.filter_func(video):
                continue
            video = self.transform_talk_json(video)
            for func in (self.postprocess or []):
                video = func(video)
            talk_list.append(video)
        return talk_list

    def transform_talk_json(self, talk_json: dict[str, Any]) -> dict[str, Any]:
        return jq.first(
            self.jq_filter,
            text=json.dumps(talk_json, cls=DjangoJSONEncoder),
        )


class YamlTransformer(JSONTransformer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.load = partial(yaml.load, Loader=yaml.Loader)


class MultiJSONTransformer(BaseTransformer):
    def __init__(self, *, path_glob: str, jq_filter: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.path_glob = path_glob
        self.jq_filter = jq_filter
        self.load = json.load

    def convert_talk_object_to_dict(self, talk_obj: Any) -> dict[str, Any]:
        return talk_obj

    def transform_talk_json(self, talk_json: dict[str, Any]) -> dict[str, Any]:
        return jq.first(
            self.jq_filter,
            text=json.dumps(talk_json, cls=DjangoJSONEncoder),
        )

    def extract_talk_list(self, input_directory: str) -> list[dict[str, Any]]:
        talk_list = []
        for file in Path(input_directory).glob(self.path_glob):
            with open(file) as f:
                video = self.load(f)

            video = self.convert_talk_object_to_dict(video)

            if self.filter_func and not self.filter_func(video):
                continue

            video = self.transform_talk_json(video)
            for func in (self.postprocess or []):
                video = func(video)
            talk_list.append(video)
        return talk_list


class MultiYamlTransformer(MultiJSONTransformer):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.load = partial(yaml.load, Loader=yaml.Loader)


class FrontmatterTransformer(MultiJSONTransformer):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.load = frontmatter.load

    def convert_talk_object_to_dict(self, talk_obj: Any) -> dict[str, Any]:
        return talk_obj.to_dict()
