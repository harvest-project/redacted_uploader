import json
import os
import shutil

from Harvest.path_utils import list_src_dst_files
from Harvest.utils import get_logger
from plugins.redacted.models import RedactedTorrentGroup
from plugins.redacted_uploader.executors.utils import RedactedStepExecutorMixin
from torrents.add_torrent import fetch_torrent
from upload_studio.step_executor import StepExecutor
from upload_studio.upload_metadata import MusicMetadata

logger = get_logger(__name__)


def _has_surronding_spaces(s):
    return s != s.strip()


class RedactedTorrentSourceExecutor(RedactedStepExecutorMixin, StepExecutor):
    name = 'redacted_torrent_source'
    description = 'Source data from Redacted torrent {source_torrent.torrent_info.tracker_id}.'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.torrent = None
        self.torrent_info = None
        self.red_group = None
        self.red_torrent = None
        self.source_path = None

    def fetch_torrent(self):
        if not self.project.source_torrent:
            self.raise_error('source_torrent is NULL, but it is required for redacted_torrent_source.')
        self.torrent = self.project.source_torrent
        tracker_id = self.torrent.torrent_info.tracker_id

        logger.info('Project {} fetching Redacted torrent {}.', self.project.id, tracker_id)
        self.torrent_info = fetch_torrent(self.realm, self.tracker, tracker_id, force_fetch=False)
        if self.torrent_info.is_deleted:
            self.add_warning('Torrent already deleted at Redacted. Unable to refresh metadata.')
        red_data = json.loads(bytes(self.torrent_info.raw_response).decode())
        self.red_group = red_data['group']
        self.red_torrent = red_data['torrent']

    def check_source_warnings(self):
        if self.red_torrent['scene']:
            self.add_warning('Attention: source torrent is scene.')
        if self.red_torrent['reported']:
            self.add_warning('Source torrent is reported.')
        if _has_surronding_spaces(self.red_torrent['remasterTitle']):
            self.add_warning('Edition title has leading or trailing spaces. Fix manually now or after upload.')
        if _has_surronding_spaces(self.red_torrent['remasterRecordLabel']):
            self.add_warning('Edition record label has leading or trailing spaces. Fix manually now or after upload.')
        if _has_surronding_spaces(self.red_torrent['remasterCatalogueNumber']):
            self.add_warning('Edition catalog number has leading or trailing spaces. Fix manually now or after upload.')

    def copy_source_files(self):
        download_path = os.path.join(self.torrent.download_path, self.torrent.name)
        logger.info('{} copying source Redacted files from {} to {}.',
                    self.project, download_path, self.step.data_path)

        if os.path.isdir(download_path):
            src_dst_files = list_src_dst_files(download_path, self.step.data_path)
        elif os.path.isfile(download_path):
            src_dst_files = [(download_path, os.path.join(self.step.data_path, os.path.basename(download_path)))]
        else:
            self.raise_error('Unknown source path type.')

        num_audio_files = 0
        audio_ext = '.' + self.red_torrent['format'].lower()
        for src_file, dst_file in src_dst_files:
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            shutil.copy2(src_file, dst_file)

            if src_file.lower().endswith(audio_ext):
                num_audio_files += 1

        logger.debug('{} discovered {} source audio files.', self.project, num_audio_files)
        if num_audio_files == 0:
            self.raise_error('No audio files discovered in source directory {}.'.format(download_path))
        elif num_audio_files == 1:
            allowed_types = {RedactedTorrentGroup.RELEASE_TYPE_SINGLE, RedactedTorrentGroup.RELEASE_TYPE_MIXTAPE}
            if self.red_group['releaseType'] not in allowed_types:
                self.add_warning('Single audio file torrent with a type that is not single or mixtape.')

    def init_metadata(self):
        logger.debug('Project {} initializing metadata from Redacted torrent.', self.project)
        self.metadata = MusicMetadata(
            title=self.red_group['name'],
            edition_year=self.red_torrent['remasterYear'],
            edition_title=self.red_torrent['remasterTitle'],
            edition_record_label=self.red_torrent['remasterRecordLabel'],
            edition_catalog_number=self.red_torrent['remasterCatalogueNumber'],

            media=self.red_torrent['media'],
            format=self.red_torrent['format'],
            encoding=self.red_torrent['encoding'],

            additional_data={
                'source_red_group': self.red_group,
                'source_red_torrent': self.red_torrent,
            }
        )

    def handle_run(self):
        self.fetch_torrent()
        self.check_source_warnings()
        self.raise_warnings()
        self.copy_source_files()
        self.init_metadata()
