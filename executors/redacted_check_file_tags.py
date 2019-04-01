import mutagen.easyid3
import mutagen.flac

from plugins.redacted_uploader.executors.utils import RedactedStepExecutorMixin, shorten_filename_if_necessary
from plugins.redacted_uploader.torrent_name import get_torrent_name_for_upload
from upload_studio.step_executor import StepExecutor
from upload_studio.upload_metadata import MusicMetadata
from upload_studio.utils import list_rel_files


def _try_parse(value):
    try:
        return int(value)
    except ValueError:
        return value


class RedactedCheckFileTags(RedactedStepExecutorMixin, StepExecutor):
    name = 'redacted_check_file_tags'
    description = 'Check the tags of audio files for Redacted upload.'

    def generate_torrent_name(self):
        self.metadata.torrent_name = get_torrent_name_for_upload(self.metadata)

    def check_tags_for_file(self, audio_file):
        if self.metadata.format == MusicMetadata.FORMAT_MP3:
            tags = mutagen.easyid3.EasyID3(audio_file.file)
        elif self.metadata.format == MusicMetadata.FORMAT_FLAC:
            tags = mutagen.flac.FLAC(audio_file.file)
        else:
            self.raise_error('No idea how to read tags for format {}'.format(self.metadata.format))

        if not tags.get('artist'):
            self.raise_error('Missing artist tag on {0}'.format(audio_file.file))
        if not tags.get('album'):
            self.raise_error('Missing album tag on {0}'.format(audio_file.file))
        if not tags.get('title'):
            self.raise_error('Missing title tag on {0}'.format(audio_file.file))

        disc_src = tags.get('discnumber') or tags.get('disc')
        if disc_src is None:
            audio_file.disc = 1
        elif isinstance(disc_src, str):
            audio_file.disc = _try_parse(disc_src.split('/')[0])
        elif isinstance(disc_src, list):
            audio_file.disc = _try_parse(disc_src[0])
        else:
            self.raise_error('Unable to read disc_src {}.'.format(disc_src))

        track_src = tags.get('tracknumber') or tags.get('track')
        if track_src is None:
            self.raise_error('Missing track tag on {0}'.format(audio_file.file))
        if isinstance(track_src, str):
            audio_file.track = _try_parse(track_src.split('/')[0])
        elif isinstance(track_src, list):
            audio_file.track = _try_parse(track_src[0])
        else:
            self.raise_error('Unable read track_src {}.'.format(track_src))

    def check_tags(self):
        for audio_file in self.audio_files:
            self.check_tags_for_file(audio_file)

    def shorten_filenames_if_necessary(self):
        for rel_path in list_rel_files(self.step.data_path):
            shorten_filename_if_necessary(self.metadata.torrent_name, self.step.data_path, rel_path)

    def check_track_numbers_sort_order(self):
        # Reverse tags to ensure same track/disc get inverted after stable sort
        by_tags = list(reversed(self.audio_files))
        by_filenames = list(self.audio_files)

        by_tags.sort(key=lambda a: (a.track, a.disc))
        by_filenames.sort(key=lambda a: a.file)

        if by_tags != by_filenames:
            tags_sort_str = '\n'.join(a.file for a in by_tags)
            self.add_warning(
                'Files do not sort properly by tags. Please check track/disc tags and filenames.\n'
                'Tags sort:\n'
                '{}'.format(tags_sort_str),
            )

    def handle_run(self):
        self.copy_prev_step_files()
        self.generate_torrent_name()
        self.discover_audio_files()
        self.check_tags()
        self.shorten_filenames_if_necessary()
        self.check_track_numbers_sort_order()
