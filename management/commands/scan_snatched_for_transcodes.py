import html

from django.core.management import BaseCommand

from plugins.redacted.models import RedactedTorrent
from plugins.redacted.request_cache import RedactedRequestCache
from plugins.redacted.tracker import RedactedTrackerPlugin
from plugins.redacted.utils import get_joined_artists
from plugins.redacted_uploader.create_project import TRANSCODE_TYPE_REDBOOK_FLAC, TRANSCODE_TYPE_MP3_V0, \
    TRANSCODE_TYPE_MP3_320
from torrents.add_torrent import fetch_torrent
from torrents.models import Torrent, Realm
from trackers.registry import TrackerRegistry
from upload_studio.models import Project


class Command(BaseCommand):
    def _match_edition(self, redacted_torrent, torrent_dict):
        return (
                redacted_torrent.media == html.unescape(torrent_dict['media']) and
                redacted_torrent.remaster_year == int(torrent_dict['remasterYear']) and
                redacted_torrent.remaster_title == html.unescape(torrent_dict['remasterTitle']) and
                redacted_torrent.remaster_record_label == html.unescape(torrent_dict['remasterRecordLabel']) and
                redacted_torrent.remaster_catalog_number == html.unescape(torrent_dict['remasterCatalogueNumber'])
        )

    def _lookup_torrent_in_group(self, redacted_torrent, group_dict, match_fn):
        for torrent_dict in group_dict['torrents']:
            if self._match_edition(redacted_torrent, torrent_dict) and match_fn(torrent_dict):
                return True
        return False

    def _check_torrent(self, progress, torrent, transcode_type, match_fn):
        redacted_torrent = torrent.torrent_info.redacted_torrent
        print('{} checking {}: {} - {}'.format(
            progress,
            torrent.torrent_info.redacted_torrent.id,
            get_joined_artists(redacted_torrent.torrent_group.music_info),
            redacted_torrent.torrent_group.name,
        ))
        existing_projects = Project.objects.filter(
            source_torrent=torrent,
            project_type='redacted_transcode_{}'.format(transcode_type),
        )
        if existing_projects.exists():
            print('  Project exists.')
            return
        # First fetch the group with a large TTL
        group_dict = self.request_cache.get_torrent_group(redacted_torrent.torrent_group_id, 60 * 60 * 24 * 7 * 2)
        if self._lookup_torrent_in_group(redacted_torrent, group_dict, match_fn):
            print('  {} already exists (1).'.format(transcode_type))
            return
        # Fetch it again with a small TTL
        group_dict = self.request_cache.get_torrent_group(redacted_torrent.torrent_group_id, 60 * 5)
        if self._lookup_torrent_in_group(redacted_torrent, group_dict, match_fn):
            print('  {} already exists (2).'.format(transcode_type))
            return
        torrent_info = fetch_torrent(self.realm, self.tracker, redacted_torrent.id, force_fetch=True)
        redacted_torrent = torrent_info.redacted_torrent
        if self._lookup_torrent_in_group(redacted_torrent, group_dict, match_fn):
            print('  {} already exists (3).'.format(transcode_type))
            return
        print('  Found candidate for {}: https://redacted.ch/torrents.php?torrentid={}'.format(
            transcode_type, torrent_info.tracker_id))
        input('  Press enter continue search')

    def _scan_torrents(self, torrents, transcode_type, match_fn):
        print('Found {} eligible torrents.'.format(len(torrents)))
        for i, torrent in enumerate(torrents):
            self._check_torrent(
                '{}/{}'.format(i + 1, len(torrents)),
                torrent,
                transcode_type,
                match_fn,
            )

    def add_arguments(self, parser):
        parser.add_argument('--redbook-flac', default=False, action='store_true')
        parser.add_argument('--mp3-v0', default=False, action='store_true')
        parser.add_argument('--mp3-320', default=False, action='store_true')

    def handle(self, *args, **options):
        self.request_cache = RedactedRequestCache()
        self.tracker = TrackerRegistry.get_plugin(RedactedTrackerPlugin.name)
        self.realm = Realm.objects.get(name=self.tracker.name)

        if options[TRANSCODE_TYPE_REDBOOK_FLAC]:
            print('Scanning for Redbook FLAC transcodes...')
            self._scan_torrents(
                list(Torrent.objects.filter(
                    realm=self.realm,
                    torrent_info__redacted_torrent__encoding=RedactedTorrent.ENCODING_24BIT_LOSSLESS,
                    torrent_info__redacted_torrent__remaster_year__gt=0,
                )),
                TRANSCODE_TYPE_REDBOOK_FLAC,
                lambda t: t['encoding'] == 'Lossless',
            )
        if options[TRANSCODE_TYPE_MP3_V0]:
            print('Scanning for MP3 V0 transcodes...')
            self._scan_torrents(
                list(Torrent.objects.filter(
                    realm=self.realm,
                    torrent_info__redacted_torrent__format=RedactedTorrent.FORMAT_FLAC,
                    torrent_info__redacted_torrent__remaster_year__gt=0,
                )),
                TRANSCODE_TYPE_MP3_V0,
                lambda t: t['encoding'] == 'V0 (VBR)',
            )
        if options[TRANSCODE_TYPE_MP3_320]:
            print('Scanning for MP3 320 transcodes...')
            self._scan_torrents(
                list(Torrent.objects.filter(
                    realm=self.realm,
                    torrent_info__redacted_torrent__format=RedactedTorrent.FORMAT_FLAC,
                    torrent_info__redacted_torrent__remaster_year__gt=0,
                )),
                TRANSCODE_TYPE_MP3_320,
                lambda t: t['encoding'] == '320',
            )
