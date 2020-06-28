# WARCIT Media Conversion Workflow

With the 0.4.0, warcit introduces a new workflow for converting video/audio files into web-friendly formats
and then placing them into WARCs along with transclusion metadata to enable access from within a containing page.

To allow for maximum flexibility, this process is split into two phases: conversion and transclusion WARC creation.

## Media Conversion

warcit includes a standalone conversion utility, `warcit-converter` which can be used to batch convert files in a directory structure based on extension/regex matching.

The conversion process can be run separately from WARC creation and outputs
converted files into a separate directory, recreating the same directory structure.

For example, given a directory structure:

```
- data/
    - videos/
         - video_file.flv
         - an_audio_rec.ra
```

Running:

```bash
warcit-converter http://www.example.com/ ./data/
```

 with the default rules will result in converted files written into `./conversions` directory (by default).

The full url of each file, as with warcit, is created by prepending the prefix to the path in the directory.

The input media in this example would have a full url of `http://example.com/media/video_file.flv` and
`http://example.com/media/an_audio_file.ra`. The converted files simply have additional extensions added
for the full url, such as: `http://example.com/media/video_file.flv.mp4`, `http://example.com/media/an_audio_file.ra.webm`, etc...

```
- data/
    - media/
         - video_file.flv
         - an_audio_rec.ra
- conversions/
    - warcit-conversion-results.yaml
    - media/
         - video_file.mp4
         - video_file.webm
         - video_file.mkv
         - an_audio_rec.mp3
         - an_audio_rec.ogg
         - an_audio_rec.opus
 
```

The results of each conversions are written into `warcit-conversion-results.yaml`. This file can
then be used to analyze the results of the conversion, and to inform the transclusion metadata workflow.

## Conversion Rules

The [default rule set](https://github.com/webrecorder/warcit/blob/video-conversion/warcit/default-conversion-rules.yaml) currently specifies conversions for .flv, .mp4, and RealMedia formats into several standardized formats, using [ffmpeg](https://www.ffmpeg.org/).

The current output formats are two web-focused formats and a preservation format:

* .webm -- vpx9 + opus encoded video + audio, an open format for the web
* .mp4 -- H.264 + AAC encoded video + audio, primarily for Safari and Apple based platforms.
* .mkv -- [FFV1](https://en.wikipedia.org/wiki/FFV1) codec in a Matroska container.

(For audio only content, .webm, .mp3 and .flac are used instead)

The first two formats are designed to be used for the web in `<video>` (or `<audio>`) tags.

The FFV1 format is a [recommended preservation
format](https://training.ashleyblewer.com/presentations/ffv1.html#3) and not designed to be shown
in the browser.

It is also possible to specify a custom rules YAML file via the `warcit-converter --rules custom-rules.yaml ...`

## WARC Conversion Record Creation

`warcit` includes the capability to write converted files as WARC `conversion` records with a reference to the original file that was the source of the conversion.

To include `conversion` record creation along with simply include the conversion results output as a parameter to `warcit`:

```bash
warcit --conversions ./conversion/warcit-conversion-results.yaml http://example.com/ ./data/ -o output.warc.gz
```

The resulting WARC will contain the original urls, eg. `http://example.com/media/video_file.flv` and `http://example.com/media/an_audio_file.ra` as `resource` records, as well as all of the converted files,
eg. `http://example.com/media/video_file.flv.mp4` and `http://example.com/media/an_audio_file.ra.mp3` as `conversion` records. The `conversion` records will refer to the record ids and urls + timestamps of the original `resource` records.

## Transclusion Manifest and Metadata

The above procedure allows for converting files in batch and adding them as WARC `conversion` records.
However, it is often useful to reference "transcluded" video and audio from another page, which embeds/transcludes the content.

The information on which resources are transcluded from which pages is not possible to deduce from the media itself, and so must be provided as an additional input to warcit.

warcit supports a transclusion manifest YAML file, which can map resources to their containing/transcluding pages. A manifest might look as follows:

transclusions.yaml:

```yaml
transclusions:
  http://example.com/media/video_file.flv:
    url: http://example.com/watch_video.html
    timestamp: 20160102
    selector: 'object, embed'

  http://example.com/media/an_audio_file.ra
    url: http://example.com/sample_audio.html
    timestamp: 20170102
    selector: 'a[id="#play"]'

```

Given this input, running `warcit --transclusions transclusions.yaml` will generate a reverse index, a `metadata` record for the containing pages, which point to the media files transcluded from that page. For the above example, two metadata records, with target uris
`metadata://example.com/watch_video.html` and `metadata//example.com/sample_audio.html` will be created.

The metadata records will simply point to the transclusions, `http://example.com/media/video_file.flv` and
`http://example.com/media/an_audio_file.ra` respectively.

However, when combining the transclusion manifest with conversion results, all of the conversion records will
also be added as metadata.

`warcit` might then be run as follows:

```bash
warcit --transclusions transclusions.yaml --conversions ./conversion/warcit-conversion-results.yaml http://example.com/ ./data/ -o output.warc.gz
```

Note that the transclusion manifest should only contain the urls of the original, not the converted records, as they will be added automatically.

## Transclusion Metadata Format(s)

The generated metadata JSON is originally modeled on the youtube-dl metadata (and has Content-Type `application/vnd.youtube-dl_formats+json`)

The JSON metadata record for `metadata://example.com/watch_video.html` might look as follows:

```json
{

  "formats": [
    {
      "command": "ffmpeg -y -i {input} -c:v vp9 -c:a libopus -speed 4 {output}",
      "ext": "webm",
      "mime": "video/webm",
      "name": "webm",
      "original_url": "http://example.com/media/video_file.flv",
      "url": "http://example.com/media/video_file.flv.webm"
    },
    {
      "command": "ffmpeg -y -i {input} -strict -2 {output}",
      "ext": "mp4",
      "mime": "video/mp4",
      "name": "mp4",
      "original_url": "http://example.com/media/video_file.flv",
      "url": "http://example.com/media/video_file.flv.mp4"
    },
    {
      "command": "ffmpeg -y -i {input} -c:v ffv1 -c:a flac {output}",
      "ext": "mkv",
      "mime": "video/x-matroska",
      "name": "ffv1_flac",
      "original_url": "http://example.com/media/video_file.flv",
      "skip_as_source": true,
      "url": "http://example.com/media/video_file.flv.mkv"
    },
    {
      "ext": "flv",
      "mime": "video/x-flv",
      "original": true,
      "url": "http://example.com/media/video_file.flv"
    }
  ],
  "selector": "object, embed",
  "webpage_timestamp": "20160102",
  "webpage_url": "http://www.example.com/watch_video.html"
}

```

This metadata includes all of the converted records and URLs to load for each format.
Based on this metadata, the pywb client side rewriting system can replace an `<object>`
or `<embed>` tag based on the selector `object,embed`
for example:

```html
<video>
  <source src="http://example.com/media/video_file.webm" type="video/webm"/>
  <source src="http://example.com/media/video_file.flv.mp4" type="video/mp4"/>
  <source src="http://example.com/media/video_file.flv" type="video/x-flv"/>
</video>
```

(The `.mkv` format is not included as its marked as `skip_as_source` while the .flv is included for completeness as the original)


## Proposal: Multiple Transcluded Objects Per Page

*This is a proposal and has not yet been implemented.*

The current format is designed for a single transcluded object. However, it is likely that there will be pages with multiple transcluded
objects. Further, it is possible that additional transclusions + conversions may be added later.
And, different versions of a page may have different numbers of videos.

For example:
- A page has multiple videos but only one was initially available. Later, additional content with two more videos was discovered.
- A page has one video that needed to be converted and one that played natively in the current browser. Later, the other video also needed to be converted.
- An initial capture of a page has two video that were converted. A later capture has only one video (the other was removed, or shifted to a new page, etc...)

To handle all of these cases, a more flexible metadata format is proposed.

The top-level JSON object in the previous example is instead placed into its own dictionary.

This format, given content-type `application/vnd.transclusions+json` might look as follows.
For a given entry, `metadata://example.com/watch_page.html`, 2 videos may be listed:

```json
{
  "transclusions":
    {"http://example.com/media/video_file.flv": {..., "formats": {...}},
    {"http://example.com/media/another_video_file.flv": {..., "formats": {...}},

  "webpage_timestamp": "20160102",
  "webpage_url": "http://www.example.com/watch_video.html",
  "creation_timestamp": "20190301",
}
```

### Multiple Transclusion Records

However, at a later time, another transclusion is discovered for the same page and 
added with a new metadata record:

```
{
  "transclusions":
    {"http://example.com/media/yet_another_video.flv": {..., "formats": {...}},

  "webpage_timestamp": "20160102",
  "webpage_url": "http://www.example.com/watch_video.html",
  "creation_timestamp": "20191001",
}
```

When loading the page `20160102/http://www.example.com/watch_video.html`, both transclusion
metadata records will be loaded, and all 3 videos will be readded to the page, if possible.

```
- "http://example.com/media/video_file.flv"
- "http://example.com/media/another_video_file.flv"
- "http://example.com/media/yet_another_video.flv"
```

The transclusion metadata `WARC-Date` is set to the date of the containing page, while
the actual creation date is set in the `WARC-Creation-Date` header.

### Transclusions for Different Timestamps of Same Page

However, if a later version of the same page contains *different* transclusions, only those transclusions
should be loaded. For example, the `20170102` version of the page may have only one video:

```
{
  "transclusions":
    {"http://example.com/media/video_file.flv": {..., "formats": {...}},

  "webpage_timestamp": "20170102",
  "webpage_url": "http://www.example.com/watch_video.html",
  "creation_timestamp": "20190105",
}
```

### Replay Lookup Behavior

When replaying a particular page, all of the exact match transclusions will be used:

* When replaying `20160203/http://www.example.com/watch_video.htm`, the closest transclusion metadata are:

```
20160102/http://www.example.com/watch_video.html -- 2 videos
20160102/http://www.example.com/watch_video.html -- 1 video
```

Since there two records at the exact same timestamp, they will be combined and 3 videos will be added.

* When replaying `20170203//http://www.example.com/watch_video.htm` the closest transclusion metadata record is:

```
20170102/http://www.example.com/watch_video.html -- 1 video
```

Since there is only one match, the 1 video from this record is used. Additional transclusion records
farther away are not searched.

If additional captures require custom sets of transclusions, additional records can be added at the exact capture time.

