"""
Processes a CPTV file identifying and tracking regions of interest, and saving them in the 'trk' format.
"""

# we need to use a non GUI backend.  AGG works but is quite slow so I used SVG instead.
import matplotlib
matplotlib.use("SVG")

import matplotlib.pyplot as plt
import matplotlib.animation as manimation
import pickle
import os
import Tracker
import ast


class TrackEntry:
    """ Database entry for a track """

    def __init__(self):
        pass


class TrackDatabase:
    """ Database to record processed tracks. """

    def __init__(self, filename):
        self.filename = filename

        # clips by filename
        self.clips = {}

        # tracks by filename
        self.tracks = {}

        self.revision = 0
        self.load()

    def load(self):
        """ Loads database from disk. """
        if (os.path.exists(self.filename)):
            save_object = pickle.load(open(self.filename, 'rb'))
            self.tracks = save_object['tracks']
            self.clips = save_object['clips']
            self.revision = save_object['revision']
        else:
            self.tracks = {}
            self.clips = {}
            self.revision = 0

    def save(self, safe_write = True):
        """
        Saves database to disk.
        :param safe_write: If enabled makes sure database hasn't been changed before saving.  If it has been changed
            throws an exception
        """

        # make sure no unexpected changes occured
        if os.path.exists(self.filename):
            db = pickle.load(open(self.filename, 'rb'))
            if db['revision'] != self.revision:
                raise Exception("Database modified by another program.")

        # increment our revision counter, this helps use detect unexpected changes.
        self.revision = self.revision + 1

        save_object = {}
        save_object['tracks'] = self.tracks
        save_object['clips'] = self.clips
        save_object['revision'] = self.revision

        # save to temp file first so if there is an error we don't loose our database.
        pickle.dump(save_object, open(self.filename+".tmp", 'wb'))
        os.remove(self.filename)
        os.rename(self.filename + ".tmp", self.filename)


    def has_clip(self, filename):
        """ Returns if database contains an entry for given track or not. """
        return filename in self.tracks

    def add_clip(self, filename, stats):
        """ Returns if database contains an entry for given track or not. """
        self.clips[filename] = stats


class CPTVTrackExtractor:
    """
    Handles extracting tracks from CPTV files.
    Maintains a database recording which files have already been processed, and some statistics parameters used
    during processing.
    """

    def __init__(self, out_folder):
        self.hints = {}
        self.colormap = plt.cm.jet
        self.verbose = True
        self.out_folder = out_folder
        self._init_MpegWriter()
        self.db = TrackDatabase(os.path.join(self.out_folder, "tracks.db"))


    def _init_MpegWriter(self):
        """ setup our MPEG4 writer.  Requires FFMPEG to be installed. """
        plt.rcParams['animation.ffmpeg_path'] = 'C:\\ffmpeg\\bin\\ffmpeg.exe'
        try:
            self.MpegWriter = manimation.writers['ffmpeg']
        except:
            self.log_warning("FFMPEG is not installed.  MPEG output disabled")
            self.MpegWriter = None


    def load_custom_colormap(self, filename):
        """ Loads a custom colormap used for creating MPEG previews of tracks. """

        if not os.path.exists(filename):
            return

        self.colormap = pickle.load(open(filename, 'rb'))


    def load_hints(self, filename):
        """ Read in hints file from given path.  If file is not found an empty hints dictionary set."""

        self.hints = {}

        if not os.path.exists(filename):
            return

        f = open(filename)
        for line_number, line in enumerate(f):
            line = line.strip()
            # comments
            if line == '' or line[0] == '#':
                continue
            try:
                (filename, file_max_tracks) = line.split()[:2]
            except:
                raise Exception("Error on line {0}: {1}".format(line_number, line))
            self.hints[filename] = int(file_max_tracks)

    def process(self, root_folder):
        """ Process all files in root folder.  CPTV files are expected to be found in folders corresponding to their
            class name. """

        folders = [os.path.join(root_folder, f) for f in os.listdir(root_folder) if
                   os.path.isdir(os.path.join(root_folder, f))]

        for folder in folders:
            print("Processing folder {0}".format(folder))
            self.process_folder(folder)
        print("Done.")

    def process_folder(self, folder_path, tag = None):
        """ Extract tracks from all videos in given folder.
            All tracks will be tagged with 'tag', which defaults to the folder name if not specified."""

        if tag is None:
            tag = os.path.basename(folder_path).upper()

        for file_name in os.listdir(folder_path):
            full_path = os.path.join(folder_path, file_name)
            if os.path.isfile(full_path) and os.path.splitext(full_path )[1].lower() == '.cptv':
                self.process_file(full_path, tag)

    def log_message(self, message):
        """ Record message in log.  Will be printed if verbose is enabled. """
        # note, python has really good logging... I should probably make use of this.
        if self.verbose: print(message)

    def log_warning(self, message):
        """ Record warning message in log.  Will be printed if verbose is enabled. """
        # note, python has really good logging... I should probably make use of this.
        print("Warning:",message)

    def process_file(self, full_path, tag, overwrite=False):
        """
        Extract tracks from specific file, and assign given tag.
        :param full: path: path to CPTV file to be processed
        :param tag: the tag to assign all tracks from this CPTV files
        :param overwrite: if true destination file will be overwritten
        """

        self.db.load()

        filename = os.path.split(full_path)[1]
        destination_folder = os.path.join(self.out_folder, tag.lower())

        # read additional information from hints file
        if filename in self.hints:
            max_tracks = self.hints[filename]
            if max_tracks == 0:
                return
        else:
            max_tracks = None

        # make destination folder if required
        try:
            os.stat(destination_folder)
        except:
            self.log_message(" Making path " +destination_folder)
            os.mkdir(destination_folder)

        # check if we have already processed this file
        if filename in self.db.clips:
            if overwrite:
                self.log_message("Overwritting {0} [{1}]".format(filename, tag))
            else:
                # skip this file
                return
        else:
            self.log_message("Processing {0} [{1}]".format(filename, tag))

        # read metadata
        meta_data_filename = os.path.splitext(full_path)[0] + ".dat"
        if os.path.exists(meta_data_filename):

            meta_data = eval(open(meta_data_filename,'r').read())

            tag_count = len(meta_data['Tags'])

            # we can only handle one tagged animal at a time here.
            if tag_count != 1:
                return

            confidence = meta_data['Tags'][0]['confidence']
        else:
            print(" - Warning: no metadata found for file.")

        tracker = Tracker.Tracker(full_path)
        tracker.max_tracks = max_tracks
        tracker.tag = tag

        # save stats to text file for reference
        with open(os.path.join(self.out_folder, tag, filename) + '.txt', 'w') as stats_file:
            # add in some metadata stats
            tracker.stats['confidence'] = confidence
            stats_file.write(str(tracker.stats))

        tracker.extract()

        tracker.export(os.path.join(self.out_folder, tag, filename))

        mpeg_filename = os.path.splitext(filename)[0]+".mp4"
        tracker.display(os.path.join(self.out_folder, tag.lower(), mpeg_filename), self.colormap)

        self.db.add_clip(filename, tracker.stats)

        self.db.save()


def main():

    extractor = CPTVTrackExtractor('d:\cac\\tracks')

    print("Database contains {0} clips.".format(len(extractor.db.clips)))

    # this colormap is specially designed for heat maps
    extractor.load_custom_colormap('custom_colormap.dat')

    # load hints.  Hints are a way to give extra information to the tracker when necessary.
    extractor.load_hints("hints.txt")

    #extractor.process('d:\\cac\\out')
    extractor.process_file('d:\\cac\out\\possum\\20171101-150843-akaroa03.cptv', 'test', overwrite=True)

main()
