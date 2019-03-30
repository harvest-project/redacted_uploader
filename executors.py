import json
import os
import shutil

from plugins.redacted.tracker import RedactedTrackerPlugin
from torrents.add_torrent import fetch_torrent
from torrents.models import Torrent, Realm
from trackers.registry import TrackerRegistry
from upload_studio.step_executor import StepExecutor
from upload_studio.upload_metadata import MusicMetadata
from upload_studio.utils import copytree_into


class RedactedStepExecutorMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker = TrackerRegistry.get_plugin(RedactedTrackerPlugin.name)
        self.realm = Realm.objects.get(self.tracker.name, 'redacted_uploader_step')


class RedactedTorrentSourceExecutor(RedactedStepExecutorMixin, StepExecutor):
    name = 'redacted_torrent_source'

    def __init__(self, *args, tracker_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker_id = tracker_id

    def handle_run(self):
        self.clean_work_area()

        source_torrent = Torrent.objects.get(
            realm=self.realm,
            torrent_info__tracker_id=self.tracker_id,
        )
        torrent_info = fetch_torrent(self.realm, self.tracker, self.tracker_id, force_fetch=True)
        if torrent_info.is_deleted:
            self.add_warning('Torrent already deleted at Redacted. Unable to refresh metadata.')
        red_data = json.loads(bytes(torrent_info.raw_response).decode())
        red_group = red_data['group']
        red_torrent = red_data['torrent']

        if red_data['torrent']['scene']:
            self.add_warning('Attention: source torrent is scene.')

        self.raise_warnings()

        if os.path.isdir(source_torrent.download_path):
            copytree_into(
                source_torrent.download_path,
                self.step.data_path,
            )
        else:
            shutil.copy2(source_torrent.download_path, self.step.data_path)

        self.metadata = MusicMetadata(
            title=red_group['name'],
            edition_year=red_torrent['remasterYear'],
            edition_title=red_torrent['remasterTitle'],
            edition_record_label=red_torrent['remasterRecordLabel'],
            edition_catalog_number=red_torrent['remasterCatalogueNumber'],

            media=red_torrent['media'],
            format=red_torrent['format'],
            bitrate=red_torrent['bitrate'],

            additional_data={
                'source_group_id': red_group['id'],
                'source_torrent_id': red_torrent['id'],
            }
        )
