import html

from django.core.management import BaseCommand

from plugins.redacted.models import RedactedTorrent
from plugins.redacted.request_cache import RedactedRequestCache
from plugins.redacted.tracker import RedactedTrackerPlugin
from plugins.redacted.utils import get_joined_artists
from torrents.add_torrent import fetch_torrent
from torrents.models import Torrent, Realm
from trackers.registry import TrackerRegistry
from upload_studio.models import Project


class Command(BaseCommand):
    def _match_edition(self, redacted_torrent, torrent_dict):
        return (
                redacted_torrent.remaster_year == int(torrent_dict['remasterYear']) and
                redacted_torrent.remaster_title == html.unescape(torrent_dict['remasterTitle']) and
                redacted_torrent.remaster_record_label == html.unescape(torrent_dict['remasterRecordLabel']) and
                redacted_torrent.remaster_catalog_number == html.unescape(torrent_dict['remasterCatalogueNumber'])
        )

    def _can_transcode(self, redacted_torrent, group_dict):
        for torrent_dict in group_dict['torrents']:
            if self._match_edition(redacted_torrent, torrent_dict) and torrent_dict['encoding'] == 'Lossless':
                return False
        return True

    def _check_torrent(self, progress, torrent):
        redacted_torrent = torrent.torrent_info.redacted_torrent
        print('{} checking {}: {} - {}'.format(
            progress,
            torrent.torrent_info.redacted_torrent.id,
            get_joined_artists(redacted_torrent.torrent_group.music_info),
            redacted_torrent.torrent_group.name,
        ))
        existing_projects = Project.objects.filter(
            source_torrent=torrent,
            project_type='redacted_transcode_redbook_flac',
        )
        if existing_projects.exists():
            print('  Project exists.')
            return
        # First fetch the group with a large TTL
        group_dict = self.request_cache.get_torrent_group(redacted_torrent.torrent_group_id, 60 * 60 * 24 * 7 * 2)
        if not self._can_transcode(redacted_torrent, group_dict):
            print('  Lossless already exists (1).')
            return
        # Fetch it again with a small TTL
        group_dict = self.request_cache.get_torrent_group(redacted_torrent.torrent_group_id, 60 * 5)
        if not self._can_transcode(redacted_torrent, group_dict):
            print('  Lossless already exists (2).')
            return
        torrent_info = fetch_torrent(self.realm, self.tracker, redacted_torrent.id, force_fetch=True)
        redacted_torrent = torrent_info.redacted_torrent
        if not self._can_transcode(redacted_torrent, group_dict):
            print('  Lossless already exists (3).')
            return
        print('  Found candidate: https://redacted.ch/torrents.php?torrentid={}'.format(torrent_info.tracker_id))
        input('  Press enter continue search')

    def handle(self, *args, **options):
        self.request_cache = RedactedRequestCache()
        self.tracker = TrackerRegistry.get_plugin(RedactedTrackerPlugin.name)
        self.realm = Realm.objects.get(name=self.tracker.name)
        eligible_torrents = list(Torrent.objects.filter(
            realm=self.realm,
            torrent_info__redacted_torrent__encoding=RedactedTorrent.ENCODING_24BIT_LOSSLESS,
        ))
        print('Found {} eligible torrents.'.format(len(eligible_torrents)))
        for i, torrent in enumerate(eligible_torrents):
            self._check_torrent(
                '{}/{}'.format(i + 1, len(eligible_torrents)),
                torrent,
            )
