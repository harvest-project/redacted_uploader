import json
import os
import shutil

from Harvest.utils import get_logger
from plugins.redacted.models import RedactedTorrentGroup
from plugins.redacted_uploader.executors.utils import RedactedStepExecutorMixin
from torrents.add_torrent import fetch_torrent
from torrents.models import Torrent
from upload_studio.step_executor import StepExecutor
from upload_studio.upload_metadata import MusicMetadata
from upload_studio.utils import list_src_dst_files

logger = get_logger(__name__)


class RedactedTorrentSourceExecutor(RedactedStepExecutorMixin, StepExecutor):
    name = 'redacted_torrent_source'
    description = 'Source data from Redacted torrent {tracker_id}.'

    def __init__(self, *args, tracker_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker_id = tracker_id

        self.torrent = None
        self.torrent_info = None
        self.red_group = None
        self.red_torrent = None
        self.source_path = None

    def fetch_torrent(self):
        logger.info('Project {} fetching Redacted torrent {}.', self.project.id, self.tracker_id)
        self.torrent = Torrent.objects.get(
            realm=self.realm,
            torrent_info__tracker_id=self.tracker_id,
        )
        self.torrent_info = fetch_torrent(self.realm, self.tracker, self.tracker_id, force_fetch=False)
        if self.torrent_info.is_deleted:
            self.add_warning('Torrent already deleted at Redacted. Unable to refresh metadata.')
        red_data = json.loads(bytes(self.torrent_info.raw_response).decode())
        self.red_group = red_data['group']
        self.red_torrent = red_data['torrent']

    def check_scene(self):
        if self.red_torrent['scene']:
            self.add_warning('Attention: source torrent is scene.')

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
            self.raise_error('{}: no audio files discovered in source directory.'.format(self.project))
        elif num_audio_files == 1:
            allowed_types = {RedactedTorrentGroup.RELEASE_TYPE_SINGLE, RedactedTorrentGroup.RELEASE_TYPE_MIXTAPE}
            if self.red_group['releaseType'] not in allowed_types:
                self.add_warning('{}: single audio file torrent with a type that is not single or mixtape.'.format(
                    self.project))

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
                'source_group_id': self.red_group['id'],
                'source_torrent_id': self.red_torrent['id'],
            }
        )

    def handle_run(self):
        self.clean_work_area()
        self.fetch_torrent()
        self.check_scene()
        self.raise_warnings()
        self.copy_source_files()
        self.init_metadata()
