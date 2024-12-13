from pyvideo_import.importers import (
    Conference,
    FrontmatterTransformer,
    GitDownloader,
    JSONAPIDownloader,
    JSONTransformer,
    MultiJSONTransformer,
    MultiYamlTransformer,
    YamlTransformer,
    YouTubeLinkBackfiller,
)
import pypandoc


# Some conferences use the schedule widget from pretalx for their schedule
# and talk list webpages. This means that talk information is not available
# directly on a conference webpage but gets served via a pretalx widget and
# export APIs. The jq filters below can be used to fetch details for
# multiple different events.
PRETALX_SCHEDULE_EXPORT_TALK_LIST_FILTER = ".schedule.conference.days[].rooms[][]"
PRETALX_TALK_TRANSFORM_FILTER = """
{
    "description": (.abstract + "\\n\\n" + .description),
    "recorded": (.date | strptime("%Y-%m-%dT%H:%M:%S%z") | strftime("%Y-%m-%d")),
    "speakers": [.persons[].public_name],
    "title": .title,
}
"""

pycon_uk_2022 = Conference(
    name="PyCon UK 2022",
    downloader=JSONAPIDownloader(url="https://pretalx.com/pycon-uk-2022/schedule/export/schedule.json"),
    transformer=JSONTransformer(
        conference_name="PyCon UK 2022",
        filepath="response.json",
        # Here we used the canned pretalx filter to combine and reformat the general
        # shape of the data coming from the pretalx API response.
        talk_list_filter=PRETALX_SCHEDULE_EXPORT_TALK_LIST_FILTER,
        # The jq_filter allows us to add additional data such as conference website URLs,
        # language information, and any other per-conference or per-talk details.
        jq_filter=PRETALX_TALK_TRANSFORM_FILTER + """ + {
            "language": "eng",
            "related_urls": [{"label": "Conference Website", "url": "https://2022.pyconuk.org/"}],
        }""",
        # PyCon UK 2022 published its videos across three playlists.
        # We can use multiple backfiller instances to fill in youtube links
        # based on each playlist.
        postprocess=[
            YouTubeLinkBackfiller(
                conference_name="PyCon UK 2022",
                url="https://www.youtube.com/watch?v=YUoKAl6-w5I&list=PLrkpavSsBQZ7tc0-bTaIPKj4rsPFwWtYn",
            ).backfill_video_url,
            YouTubeLinkBackfiller(
                conference_name="PyCon UK 2022",
                url="https://www.youtube.com/watch?v=mRm9AjnGoBs&list=PLrkpavSsBQZ4ImE1qyyUkHOcRfHD8J5KZ",
            ).backfill_video_url,
            YouTubeLinkBackfiller(
                conference_name="PyCon UK 2022",
                url="https://www.youtube.com/watch?v=5JeO7nToajk&list=PLrkpavSsBQZ4MmQ6oa27kvMrx7JNzVaBG",
            ).backfill_video_url,
        ]
    )
)


# The PyGotham 2023 site shows an example of transforming a Jekyll site with
# files stored in a GitLab repository and transforming Frontmatter content
# into PyVideo's JSON format. The jq filter used here is mostly mapping inputs
# to outputs, but there exists some logic to extract and transform dates and
# YouTube video IDs.
pygotham_2023 = Conference(
    name="PyGotham 2023",
    downloader=GitDownloader(remote="https://gitlab.com/pygotham/2023.git"),
    transformer=FrontmatterTransformer(
        conference_name="PyGotham 2023",
        path_glob="_talks/*.md",
        filter_func=lambda talk: talk["type"] == "talk" and talk["video_url"],
        jq_filter='''{
            "title": .title,
            "speakers": .speakers,
            "description": .content,
            "videos": [{"type": "youtube", "url": .video_url}],
            "thumbnail_url": ("https://i.ytimg.com/vi/" + (.video_url | split("/")[-1]) + "/maxresdefault.jpg"),
            "copyright_text": "Creative Commons Attribution license (reuse allowed)",
            "language": "eng",
            "recorded": (.slot | strptime("%Y-%m-%dT%H:%M:%S%z") | strftime("%Y-%m-%d")),
        }''',
    ),
)

# The DjangoCon US 2023 example looks a lot like the PyGotham 2023 example.
# It includes a few minor changes and references a GitHub repository instead
# of GitLab.
djangocon_us_2023 = Conference(
    name="DjangoCon US 2023",
    downloader=GitDownloader(remote="https://github.com/djangocon/2023.djangocon.us.git"),
    transformer=FrontmatterTransformer(
        conference_name="DjangoCon US 2023",
        path_glob="_schedule/talks/*.md",
        filter_func=lambda talk: talk["category"] == "talks" and talk.get("video_url") not in [None, ""],
        jq_filter='''{
            "title": .title,
            "speakers": .presenter_slugs,
            "description": .content,
            "videos": [{"type": "youtube", "url": .video_url}],
            "thumbnail_url": ("https://i.ytimg.com/vi/" + (.video_url | split("/")[-1]) + "/maxresdefault.jpg"),
            "language": "eng",
            "recorded": (.date | strptime("%Y-%m-%dT%H:%M:%S%z") | strftime("%Y-%m-%d")),
            "related_urls": [{"label": "Conference Website", "url": "https://2023.djangocon.us"}],
        }''',
    ),
)


# This is a postprocessing function used to replace HTML content with
# reStructuredText. Some conferences include APIs or serialized data
# that include HTML markup, so this needs to be converted back to something
# like reST in order for PyVideo to render it without escaping HTML tags.
def convert_description_from_html_to_rst(obj: dict) -> dict:
    obj['description'] = pypandoc.convert_text(
        obj['description'],
        format='html',
        to='rst',
        # extra_args=["--reference-links"],
    )
    return obj


# The PyOhio 2022 site uses the MultiJSONTransformer instead of the
# FrontmatterTransformer. The website for this conference is based on a static
# site that stores data as a JSON file for each page. It also includes an
# example of using a postprocess function.
pyohio_2022 = Conference(
    name="PyOhio 2022",
    downloader=GitDownloader(remote="https://github.com/pyohio/pyohio-archive.git"),
    transformer=MultiJSONTransformer(
        conference_name="PyOhio 2022",
        path_glob="2022/page-data/program/talks/*/page-data.json",
        filter_func=lambda talk: talk["result"]["data"]["talksYaml"]["type"] != "Break",
        jq_filter='''{
            "title": .result.data.talksYaml.title,
            "speakers": [.result.data.talksYaml.speakers[].name],
            "description": .result.data.talksYaml.description,
            "videos": [{"type": "youtube", "url": .result.data.talksYaml.youtube_url}],
            "thumbnail_url": ("https://i.ytimg.com/vi/" + (.result.data.talksYaml.youtube_url | split("/")[-1]) + "/maxresdefault.jpg"),
            "language": "eng",
            "recorded": "2022-07-30",
            "related_urls": [{"label": "Conference Website", "url": "https://www.pyohio.org/2022/"}],
        }''',
        postprocess=[convert_description_from_html_to_rst],
    ),
)

# The PyOhio 2023 example below is functionally very similar to the 2022
# site but uses multiple YAML files instead of multiple JSON files.
pyohio_2023 = Conference(
    name="PyOhio 2023",
    downloader=GitDownloader(remote="https://github.com/pyohio/pyohio-static-website.git", ref="2023"),
    transformer=MultiYamlTransformer(
        conference_name="PyOhio 2023",
        path_glob="2023/src/content/talks/*.yaml",
        filter_func=lambda talk: talk["type"] != "Break",
        jq_filter='''{
            "title": .title,
            "speakers": [.speakers[].name],
            "description": .description,
            "videos": [{"type": "youtube", "url": .youtube_url}],
            "thumbnail_url": ("https://i.ytimg.com/vi/" + (.youtube_url | split("/")[-1]) + "/maxresdefault.jpg"),
            "language": "eng",
            "recorded": "2023-12-16",
            "related_urls": [{"label": "Conference Website", "url": "https://www.pyohio.org/2023/"}],
        }''',
        postprocess=[convert_description_from_html_to_rst],
    ),
)


# PyCon US provides a JSON API for its session data. We use an instance of
# the JSONAPIDownloader to fetch it and then operate on the single JSON
# file output to extract and transform talk data.
#
# Additionally, PyCon US does not include video links in its API data.
# A not-very-sophisticated postprocessing function is included here to
# do a bunch of matching of YouTube URLs to PyVideo JSON objects via
# fuzzy matching of titles. This process is not perfect (in part because
# of limitations on the length of YouTube video titles), so this approach
# often requires some manual work to fill in missing details and / or correct
# incorrectly matched videos.
pycon_us_2023 = Conference(
    name="PyCon US 2023",
    downloader=JSONAPIDownloader(url="https://us.pycon.org/2023/schedule/conference.json"),
    transformer=JSONTransformer(
        conference_name="PyCon US 2023",
        filepath="response.json",
        filter_func=lambda talk: talk["kind"] in ["talk", "tutorial", "plenary", "charla", "sponsor-workshop"],
        talk_list_filter=".schedule[]",
        jq_filter='''{
            "title": .name,
            "speakers": (. | if has("speakers") then [.speakers[].name] else [] end),
            "description": .description,
            "copyright_text": .license,
            "recorded": (.start | strptime("%Y-%m-%dT%H:%M:%S%z") | strftime("%Y-%m-%d")),
            "related_urls": [{"label": "Conference Website", "url": "https://us.pycon.org/2023/"}, {"label": "Presentation Webpage", "url": .conf_url}],
            "language": (. | if .kind == "charla" then "spa" else "eng" end),
        }''',
        postprocess=[
            convert_description_from_html_to_rst,
            YouTubeLinkBackfiller(
                conference_name="PyCon US 2023",
                url="https://www.youtube.com/playlist?list=PL2Uw4_HvXqvY2zhJ9AMUa_Z6dtMGF3gtb",
            ).backfill_video_url
        ],
    )
)

pycon_us_2024 = Conference(
    name="PyCon US 2024",
    downloader=JSONAPIDownloader(url="https://us.pycon.org/2024/schedule/conference.json"),
    transformer=JSONTransformer(
        conference_name="PyCon US 2024",
        filepath="response.json",
        filter_func=lambda talk: talk["kind"] in ["talk", "tutorial", "plenary", "charla", "sponsor-workshop"],
        talk_list_filter=".schedule[]",
        jq_filter='''{
            "title": .name,
            "speakers": (. | if has("speakers") then [.speakers[].name] else [] end),
            "description": .description,
            "copyright_text": .license,
            "recorded": (.start | strptime("%Y-%m-%dT%H:%M:%S%z") | strftime("%Y-%m-%d")),
            "related_urls": [{"label": "Conference Website", "url": "https://us.pycon.org/2024/"}, {"label": "Presentation Webpage", "url": .conf_url}],
            "language": (. | if .kind == "charla" then "spa" else "eng" end),
        }''',
        postprocess=[
            convert_description_from_html_to_rst,
            YouTubeLinkBackfiller(
                conference_name="PyCon US 2024",
                url="https://www.youtube.com/playlist?list=PL2Uw4_HvXqvYhjub9bw4uDAmNtprgAvlJ",
            ).backfill_video_url
        ],
    )
)
