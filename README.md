# discogstagger3

 [![Build Status](https://travis-ci.org/triplem/discogstagger.png)](http://travis-ci.org/triplem/discogstagger) [![Coverage Status](https://coveralls.io/repos/triplem/discogstagger/badge.png)](https://coveralls.io/r/triplem/discogstagger)


## What is it

discogstagger3 is a console based audio meta-data tagger. Release data is
retrieved via the discogs.com API.

discogstagger3 is based on the great work of [jesseward](https://github.com/jesseward/discogstagger)
and forked from the work done by [triplem](https://github.com/triplem/discogstagger).

Simply provide the script with a base directory, that contains an album
consisting of either FLAC or MP3 media files and the discogs.com
release-id. discogstagger2 calls out to the discogs.com API and updates the
audio meta-data accordingly.

If no release-id is given, the application checks, if a file "id.txt" exists
(the name of this file can be configured in the configuration) and if this file
contains a specific property (id_tag). If both is true the release-id from this
file is used. This is useful for batch processing.

During the process, album images (if present and if configured) are retrieved from the API.
To avoid a huge damage to your RateLimit, you can configure, that only the cover image and not all
are loaded from the Discogs servers.
As well, a play-list (.m3u) and an information file (.nfo) are generated per
each release.

Optionally discogstagger will embed the found album art into the file meta data

For detailed configuration options, take a look in the conf/default.conf file, there you will be
able to see default values as well as a short explanation for each config option.

Added support for loudgain: https://wiki.hydrogenaud.io/index.php?title=Loudgain

## Why this version?

I have the ambition of setting this script running as a cron job, so that it proccesses any new releases that are dropped into a folder.  I have used other tagging tools in the past, mp3tag being my favourite, but they all still require a lot of manual input.

I am used to the powerful string formatting functions available to FooBar2000 and mp3tag, and wanted to bring them to an automated script. See http://wiki.hydrogenaud.io/index.php?title=Foobar2000:Title_Formatting_Reference

I also have a large collection of music in cue files, so I wanted to automate their processing too.

With this version I am developing:

  * string formatting functions (Foobar2000 & mp3Tag style)
  * making technical information available using placeholders (Foobar2000 & mp3Tag style)
  * cue* file processing
  * searching discogs for release data (based on existing metadata)
  * choice of replaygain processors (metaflac & loudgain)

* This version uses a modified version of the CUE library from the lolcut project: https://pypi.org/project/lolcut/

Useful links:
  * http://wiki.hydrogenaud.io/index.php?title=Foobar2000:Title_Formatting_Reference
  * https://docs.google.com/spreadsheets/d/1afugW3R1FRDN-mwt5SQLY4R7aLAu3RqzjN3pR1497Ok/htmlview
  * https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping


## Develop on discogstagger

If you are developing on discogstagger, please do not forget to check, if the
given tests (and you should add your own unit tests as well) are still running,
by invoking

```
invoke test
```

## Requirements

* Mutagen for easy accessing meta-tags
* discogs-client for access to the discogs api
* requests for access to the discogs api ;-)
* nose for unit tests
* mako for easy templating (e.g. nfo and m3u files) >=0.8.1
* rauth for oauth authentication to discogs
* coverage for coverage reporting
* invoke to make running tests easier

discogstagger is also packaging/reusing the MediaFile library from the "beets"
project. This package is already externalized in beets, but we have adopted this
package and are therefor providing our own version.

## Installation

Fetch the repo from github
```
git clone https://github.com/triplem/discogstagger.git
```

Install the script requirements
```
sudo pip install -r requirements.txt
```

Run through set-up script
```
sudo python setup.py install
```

## Configuration

DiscogsTagger always loads the default options from the conf/default.conf file, furthermore, you are able to
overwrite those using your own file, which can be given on the command line using the '-c' switch.

The default configuration file must be present to execute the script. The default
settings (as shipped), should work without any modifications.

Note that you may wish to modify the following default configuration options.
The defaults are shipped as such in attempt to be as non destructive as possible

```
# True/False : leaves a copy of the original audio files on disk, untouched after
keep_original=True
# Embed cover art. Include album art from discogs.com in the metadata tags
embed_coverart=False
```

To specify genre in your tags, review the use_style option. With use_style
set to True, you're instructing discogstagger to pull the "Style" field. The style field
is typically more genre specific than the discogs "Genre" field. In the example below (40522),
with use_style=True, the genre field is tagged as "House".

```
Use Discogs "style" elements instead of the genre as the genre Meta-Tag in files (True)
Example http://www.discogs.com/Blunted-Dummies-House-For-All/release/40522
Style = House
Genre = Electronic
use_style=True
```

To keep already existing tags, you can include these tags in the configuration as well.
Usually Rippers (e.g. RubyRipper) do include the freedb_id, which could be kept using
the following configuration. The list of all tags could be taken from the file
discogstagger/ext/mediafile.py.

```
# Keep the following tags
keep_tags=freedb_id
```

Furthermore you can use lowercase directory and filenames using the following configuration:

```
# Use lowercase filenames
use_lower_filenames=True
```

For batch-mode tagging, it is not necessary anymore to provide the release-id via the
'-r' parameter on the commandline. The same is possible by using a file (by default: id.txt)
with the following structure:

```
[source]
discogs_id=RELEASE_ID
```

The name of this file and the name of the id tag can be configured in your configuration file
 as well.

```
[batch]
# batch
# if no release id is given, the application checks if a file with the
# name id_file (in this case id.txt) is in the source directory,
# if it is there the id_tag is checked (discogs_id) and assigned to the
# release id
id_file=id.txt

[source]
# source
# defines a mapping between the name of the source and the corresponding
# id tag in the media file
discogs=discogs_id
```

All command line options are shown, if the program (discogstagger2.py) is called without any further command
line options. Please note, that we are using python 2.7.

The command line takes the following parameters:

```
Usage: discogstagger2.py [options]

Options:
  --version             show program's version number and exit
  -h, --help            show this help message and exit
  -r RELEASEID, --releaseid=RELEASEID
                        The release id of the target album
  -s SOURCEDIR, --source=SOURCEDIR
                        The directory that you wish to tag
  -d DESTDIR, --destination=DESTDIR
                        The (base) directory to copy the tagged files to
  -c CONFFILE, --conf=CONFFILE
                        The discogstagger configuration file.
  --recursive           Should albums be searched recursive in the source
                        directory?
  -f, --force           Should albums be updated even though the done token
                        exists?
  -g, --replay-gain     Should replaygain tags be added to the album?
                        (metaflac needs to be installed)
  -w, --watch           Daemon mode, will watch for changes to the source
                        directory
```
