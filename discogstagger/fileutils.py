# -*- coding: utf-8 -*-
import os
from pathlib import Path
import shutil
from mutagen.flac import FLAC
import re
from discogstagger.cue import CUE, Track

import logging
logger = logging.getLogger(__name__)

class FileUtils(object):
    def __init__(self, tagger_config, options):
        self.config = tagger_config
        self.source_dirs = []
        self.cue_done_dir = self.config.get('cue', 'cue_done_dir')
        self.done_file = self.config.get("details", "done_file")
        self.forceUpdate = options.forceUpdate

    def read_id_file(self, dir, file_name, options):
        # read tags from batch file if available
        releaseid = None
        idfile = os.path.join(dir, file_name)
        if os.path.exists(idfile):
            logger.info("reading id file %s in %s" % (file_name, dir))
            self.config.read(idfile)
            source_type = self.config.get("source", "name")
            id_name = self.config.get("source", source_type)
            releaseid = self.config.get("source", id_name)
        elif options.releaseid:
            releaseid = options.releaseid

        return releaseid

    def walk_dir_tree(self, start_dir, id_file):
        source_dirs = []
        for root, dirs, files in os.walk(start_dir):
            if id_file in files:
                logger.debug("found %s in %s" % (id_file, root))
                source_dirs.append(root)

        return source_dirs

    def get_audio_dirs(self, start_dir):
        """ Returns a list of directories with audio track to be processed.
            Any CUE files encountered will be split automatically
        """
        parse_cue_files = self.config.getboolean('cue', 'parse_cue_files')
        extf = (self.cue_done_dir)
        source_dirs = []

        for root, dirs, files in os.walk(start_dir, topdown=True):
            dirs[:] = [d for d in dirs if d not in extf]
            done = []
            cue_files = []
            audio_files = []
            unwalk = []
            for dir in dirs:
                if os.path.exists(os.path.join(root, dir, self.done_file)):
                    done.append(dir)
            if len(done) > 0:
                dirs[:] = [d for d in dirs if d not in done]

            for file in files:
                if file.endswith('.cue'):
                    cue_files.append(file)
                elif file.endswith(('.flac', '.mp3', '.ape', '.wav', '.wv')):
                    audio_files.append(file)
            for dir in dirs:
                if re.search(r'(?i)^(cd|disc)\s*\d+', dir):
                    logger.debug('Directory has cd/disc subdirectories')
                    unwalk.append(dir)
                    d = Path(os.path.join(root, dir))
                    for file in d.iterdir():
                        if str(file).endswith('.cue'):
                            cue_files.append(str(file))
                        if str(file).endswith(('.flac', '.mp3', '.ape', '.wav', '.wv')):
                            audio_files.append(str(file))
            dirs[:] = [d for d in dirs if d not in unwalk]
            if parse_cue_files and len(cue_files) > 0 and len(cue_files) == len(audio_files):
                result = self._processCueFiles(root, cue_files)
                if result == 0:
                    source_dirs.append(root + '/')
            elif len(audio_files) > 0 and self.done_file not in files:
                source_dirs.append(root + '/')
                logger.debug('found %s in %s' % (file, root + '/'))

        return source_dirs

    def _processCueFiles(self, dir, files):
        """ Process CUE files.  Work out multi-disc sets
        """
        logger.debug('processing cue files found')
        files.sort()
        for idx, file in enumerate(files):
            cue_in = os.path.join(dir, file)
            cue = CUE(cue_in)
            if cue.title is not None:
                cue.title = re.sub(r'(?i)\s+(cd|disc)\s*\d+\Z', '', cue.title)
            cue.output_format = str(idx + 1) + '-%n' if len(files) > 1 else '%n'
            if len(files) > 1:
                cue.discnumber = str(idx + 1)
                cue.disctotal = str(len(files))
            result = self._splitCueFile(cue)
            if result != 0:
                logger.debug('Problem processing cue files in directory' + dir)
                return 1

        return 0

    def _tagFiles(self, cue):
        """ Tags files with the metadata present in cue file
        """
        file_path = cue.image_file_directory
        if cue.disctotal is not None and int(cue.disctotal) > 1:
            file_path = os.path.join(file_path, 'cd' + str(cue.discnumber))
        for track in cue.tracks:
            if track.number is not None:
                src_file_name = cue.discnumber + '-' + str(track.number).zfill(2)+'.flac' if cue.discnumber is not None else str(track.number).zfill(2)+'.flac'
                audio = FLAC(os.path.join(file_path, src_file_name))
                if track.title is not None:
                    audio["title"] = track.title
                if cue.performer is not None:
                    audio["artist"] = cue.performer
                if track.number is not None:
                    audio["tracknumber"] = str(track.number)
                if cue.title is not None:
                    audio["album"] = cue.title
                if track.isrc is not None:
                    audio["isrc"] = track.isrc
                if cue.genre is not None:
                    audio["genre"] = cue.genre
                if cue.date is not None:
                    audio["date"] = cue.date
                if cue.discid is not None:
                    audio["discid"] = cue.discid
                if cue.comment is not None:
                    audio["comment"] = cue.comment
                if cue.discnumber is not None:
                    audio["discnumber"] = cue.discnumber
                if cue.disctotal is not None:
                    audio["disctotal"] = cue.disctotal
                # 0th track left blank
                audio["tracktotal"] = str(len(cue.tracks) - 1)

                audio.pprint()
                audio.save()

    def _splitCueFile(self, cue):
        """ Handles the splitting and tidy up of cue files and associated audio
        """
        destination = cue.image_file_directory
        if cue.disctotal is not None and int(cue.disctotal) > 1:
            destination = os.path.join(cue.image_file_directory, 'cd' + str(cue.discnumber))
        p = Path(destination)
        if not p.exists():
            p.mkdir()

        import subprocess
        logger.debug('Splitting CUE: %s', cue.file_name)
        cmd = [
            'shntool', 'split',
            '-f', str(cue.file_name),
            str(cue.image_file_name),
            '-t', cue.output_format,
            '-o', 'flac',
            '-d', str(destination),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return_code = result.returncode

        if return_code != 0:
            logger.error('shntool split failed (exit %d):\n%s',
                         return_code, result.stderr.strip())
            return 1

        self._tagFiles(cue)

        logger.debug('Cleaning up source CUE and image files')
        done_dir = os.path.join(cue.image_file_directory, self.cue_done_dir)
        Path(done_dir).mkdir(exist_ok=True)
        for file in (cue.file_name, cue.image_file_name):
            shutil.move(str(file), str(done_dir))
        for f in Path(destination).glob('*00.flac'):
            f.unlink()
        return 0
