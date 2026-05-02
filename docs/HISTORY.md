## Changelog

Version 3.0-alpha

* feature: add Discogs searching based on original metadata

* feature: add CUE file parsing, using the CUE libary from lolcut project: https://pypi.org/project/lolcut/

* feature: daemon mode, watches for changes to the source directory

* feature: add Foobar2000-style string formatting commands (basics)

* improvement: refactored replaygain, now works with loudgain or metaflac

* improvement: updated to python3

* improvement: updated metadata fields:
               * added MEDIA - original media information
               * updated ALBUMARTIST and ARTIST storage as lists, now able to save multiple artists e.g. on split discs
               * removed ALBUM ARTIST from MediaFile library, was causing duplication and not in the mapping on Hydrogen Audio (https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping#cite_note-vorbis-field-names-13)
               * added CATNUMBERS_SORTED - available in tagging fields




Version 2.2.1

* improvement: Use field mapping used by Jaikoz (https://docs.google.com/spreadsheets/d/1afugW3R1FRDN-mwt5SQLY4R7aLAu3RqzjN3pR1497Ok/htmlview),
               this means specifially:
               * DISCOGSID is still used (which is an additional field only used by discogstagger2)
               * GROUPING used for Style grouping (using styles from Discogs)
               * FOLDER is still used (another additonal field only used by discogstagger2)
               * DISCNUMBER instead of the below mentioned DISC
               * TRACKNUMBER instead of the below mentioned TRACK
               * ENCODER instead of the below mentioned ENCODEDBY
               * URL_DISCOGS_RELEASE_SITE, the url to the discogs release
               * DISCID instead of the formerly used freedb_id
               * URL and URLTAGS are not used anymore

* improvement: provide script for tag update

* improvement: refactored replay gain

* improvement: version bump uses bumpversion

* improvement: remove unnecessary enumeration class

* improvement: use genres instead of genre to allow multiple genre fields, the same for GROUPING, ARTIST and ALBUMARTIST
               Note: this is just tested for FLAC files

Version 2.2.0

* improvement: be able to store and re-use tokens for the access to discogs (these are stored
               in the file .token in the current directory

* improvement: use latest version of the ext/mediafile (cloned from https://raw.githubusercontent.com/beetbox/mediafile/master/mediafile.py)

* improvement: cleanup storeage of Metadata of flacs, the following fields are used now:
               TRACK (TRACKNUMBER is not used anymore), TRACKTOTAL (TRACKC and TOTALTRACKS are not used anymore),
               DISC (DISCNUMBER is not used anymore), DISCTOTAL (DISCC and TOTALDISCS are not used anymore),
               COMMENT (DESCRIPTION is not used anymore), ALBUMARTIST (ALBUM ARTIST is not used anymore),
               LABEL (PUBLISHER is not used anymore), ENCODEDBY (ENCODER is not used anymore),
               DISCOGSID (was DiscogsId), DISCID (for freedb) added, FOLDER (for grouping purposes) added

Version 2.1.1

* improvement: This release contains some fixes for #14 and #16. Furthermore there is already a first draft for #7 included.

Version 2.0.1

* improvement: add new script to add folder tag to all selected files, so that the
               sorting of those files will be easier in BubbleUpnp, this new tag
               has to be added to minimserver to be sortable

Version 2.0.0

* improvement: remove group-config tag, as this could be easily added in the
               dir-format
* improvement: replace id.txt structure with usual config structure, to be able
               to overwrite config options in batch mode for each album/release

Version 1.2.0

* improvement: add several new tags (e.g. artist_sort, url) to the tracks
* improvement: add possibility to use '/' in dir-property, to allow subdirectory
               creation (e.g. %ARTIST%/%ALBUM%)
* feature: add possibility to name the first image folder.jpg, so that clients
           recognize this picture, even though it is not embedded (Issue #12)
* feature: add multi disc support (Issue #14), this does right now covers
           the handling of tags (discnumber, discstotal) and splitting folders
           for multiple discs based on a configuration parameter
* feature: copy files already existing in source directory (using config option
           copy_other_files)
* feature: add additional tags for all tracks in configuration (see section tags
           in discogs_tagger.conf - tagname: encoder) - right now not all tags
           are supported, to see a list of supported tags, please see
           discogstagger/ext/mediafile.py (Issue #11)
* feature: add possibility to adopt config options for each release via the id.txt
           file (Issue #17), this allows also to adopt certain tags via the
           config-option-prefix "tag:" (e.g. tag:artist will replace the artist
           of the current album with the given value)

Version 1.1.0

* improvement: use genre from discogs as the genre (configurable, so that you are still
               able to use style like in previous versions)
* improvement: provide the picture type "cover image" for flac as well
* improvement: add discogs_id as a tag to each file (as discogs_id for flac and mp3),
               some taggers (e.g. puddletag) need this information
* improvement: add some translations for german umlauts
* feature: add possiblity to provide a separate destination directory (-d)
* feature: add possiblity to provide the release id via a file in the source
           directory. The name of the file as well as the name of the used key
           is configurable, a default configuration is provided
* feature: add possibility to use lower case file and directory names via config option
* feature: add possibility to keep already existing tags in the file (e.g. freedb_id)

Version 1.0.1

* style clean-up

Version 1.0.0
* feature : options to embed cover art into metadata (issue #4)
* feature : now supports mp4/asf formats (in addition to mp3/flac) via
                the inclusion of the mediafile.py library. (not yet tested)
* improvement : clean up code base and installer
* improvement : remove comments from metadata (issue #6)

Version 0.8

* fix : bug in discogs_tagger.py . song_format initialized incorrectly.

Version 0.6

* fix : artist name is now accessed from the release class, and not the Artist
class (reported by cmaussan)
* improvement : Release names now support multiple artists in release names.
Multiple artist names are statically joined with an ampersand (&).

Version 0.5

* Included updated version of discogs_client.py (1.1.1)
* minimal style cleanup in discogs_tagger.py

Version 0.4

A couple minor bugfixes, and feature enhancements.
    - FIX : incorrect handling of directory names, when the basename was not in the
      immediate path.
    - Added a new filename tag. %LABEL% now allows the record label name in the filename
    - Improvement : using the unicodedata library to convert unicode values to their
      known ASCII counterpart. Reduction the CHAR_EXCEPTION dict, which will eventually
      move to the configuration file.

Version 0.3

Add a couple requests from dimitry_ghost and Dec via discogs.com
http://www.discogs.com/help/forums/topic/251892?page=1#msg2950783

    - Writes the master release id to the .nfo file if present.
    - Option to allow the original directory to be kept on FS (keep_original=True in
      config file)

Version 0.2
    - Documentation updates
    - Very basic logging and error handling added to discogs_tagger
    - Providing script to a wider audience.

Version 0.1

    - An initial, very basic working release. Minimal testing was performed.
