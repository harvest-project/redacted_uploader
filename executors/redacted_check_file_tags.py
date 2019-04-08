import os
from itertools import groupby

from Harvest.path_utils import list_rel_files
from plugins.redacted_uploader.executors.utils import RedactedStepExecutorMixin, shorten_filename_if_necessary
from plugins.redacted_uploader.torrent_name import get_torrent_name_for_upload
from upload_studio.audio_utils import AudioDiscoveryStepMixin
from upload_studio.step_executor import StepExecutor


class RedactedCheckFileTags(AudioDiscoveryStepMixin, RedactedStepExecutorMixin, StepExecutor):
    name = 'redacted_check_file_tags'
    description = 'Check the tags of audio files for Redacted upload.'

    def generate_torrent_name(self):
        self.metadata.torrent_name = get_torrent_name_for_upload(self.metadata)
        self.metadata.processing_steps.append('Generate torrent name "{}" from metadata.'.format(
            self.metadata.torrent_name))

    def check_tags_for_file(self, audio_file):
        if not audio_file.muta.get('artist'):
            self.raise_error('Missing artist tag on {0}'.format(audio_file.rel_path))
        if not audio_file.muta.get('album'):
            self.raise_error('Missing album tag on {0}'.format(audio_file.rel_path))
        if not audio_file.muta.get('title'):
            self.raise_error('Missing title tag on {0}'.format(audio_file.rel_path))

    def check_tags(self):
        for audio_file in self.audio_files:
            self.check_tags_for_file(audio_file)

    def shorten_filenames_if_necessary(self):
        for rel_path in list_rel_files(self.step.data_path):
            shorten_filename_if_necessary(self.metadata.torrent_name, self.step.data_path, rel_path)

    def check_track_numbers_sort_order(self):
        for dir_path, dir_files in groupby(self.audio_files, lambda f: os.path.dirname(f.abs_path)):
            # Reverse tags to ensure same track/disc get inverted after stable sort
            by_filenames = list(dir_files)
            by_tags = list(reversed(by_filenames))

            by_tags.sort(key=lambda a: (a.track, a.disc))
            by_filenames.sort(key=lambda a: a.abs_path)

            if by_tags != by_filenames:
                tags_sort_str = '\n'.join(a.rel_path for a in by_tags)
                self.add_warning(
                    'Files in {} do not sort properly by tags. Please check track/disc tags and filenames.\n'
                    'Tags sort:\n'
                    '{}'.format(
                        dir_path,
                        tags_sort_str,
                    ),
                )

    def handle_run(self):
        self.copy_prev_step_files()
        self.generate_torrent_name()
        self.discover_audio_files()
        self.check_tags()
        self.shorten_filenames_if_necessary()
        self.check_track_numbers_sort_order()
