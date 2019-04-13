import html
from time import sleep

from django.core.management import BaseCommand

from plugins.redacted.models import RedactedTorrent
from plugins.redacted.request_cache import RedactedRequestCache
from plugins.redacted.tracker import RedactedTrackerPlugin
from plugins.redacted.utils import get_joined_artists
from plugins.redacted_uploader.create_project import TRANSCODE_TYPE_REDBOOK_FLAC, TRANSCODE_TYPE_MP3_V0, \
    TRANSCODE_TYPE_MP3_320, create_transcode_project
from torrents.add_torrent import fetch_torrent
from torrents.models import Torrent, Realm
from trackers.registry import TrackerRegistry
from upload_studio.models import Project

NUM_CONCURRENT_PROJECTS = 4


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

    def _create_transcode_project(self, torrent, transcode_type):
        printed = False
        while True:
            if Project.objects.filter(is_finished=False).count() < NUM_CONCURRENT_PROJECTS:
                break
            if not printed:
                print('  Waiting for project slots...')
                printed = True
            sleep(1)
        tracker_id = torrent.torrent_info.tracker_id
        print('  Creating project...')
        create_transcode_project(tracker_id, transcode_type)
        print('  Created project for https://redacted.ch/torrents.php?torrentid={}'.format(tracker_id))
        sleep(5)

    def _check_torrent(self, progress, torrent, transcode_type, match_fn, auto_create):
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
        if auto_create:
            self._create_transcode_project(torrent, transcode_type)
        else:
            input('  Press enter continue search')

    def _scan_torrents(self, torrents, transcode_type, match_fn, auto_create):
        print('Found {} eligible torrents.'.format(len(torrents)))
        for i, torrent in enumerate(torrents):
            self._check_torrent(
                progress='{}/{}'.format(i + 1, len(torrents)),
                torrent=torrent,
                transcode_type=transcode_type,
                match_fn=match_fn,
                auto_create=auto_create,
            )

    def add_arguments(self, parser):
        parser.add_argument('--redbook-flac', default=False, action='store_true')
        parser.add_argument('--mp3-v0', default=False, action='store_true')
        parser.add_argument('--mp3-320', default=False, action='store_true')
        parser.add_argument('--auto-create', default=False, action='store_true')

    def handle(self, *args, **options):
        self.request_cache = RedactedRequestCache()
        self.tracker = TrackerRegistry.get_plugin(RedactedTrackerPlugin.name)
        self.realm = Realm.objects.get(name=self.tracker.name)

        if options[TRANSCODE_TYPE_REDBOOK_FLAC]:
            print('Scanning for Redbook FLAC transcodes...')
            self._scan_torrents(
                torrents=list(Torrent.objects.filter(
                    realm=self.realm,
                    torrent_info__redacted_torrent__encoding=RedactedTorrent.ENCODING_24BIT_LOSSLESS,
                    torrent_info__redacted_torrent__remaster_year__gt=0,
                )),
                transcode_type=TRANSCODE_TYPE_REDBOOK_FLAC,
                match_fn=lambda t: t['encoding'] == 'Lossless',
                auto_create=options['auto_create'],
            )
        if options[TRANSCODE_TYPE_MP3_V0]:
            print('Scanning for MP3 V0 transcodes...')
            self._scan_torrents(
                torrents=list(Torrent.objects.filter(
                    realm=self.realm,
                    torrent_info__redacted_torrent__format=RedactedTorrent.FORMAT_FLAC,
                    torrent_info__redacted_torrent__remaster_year__gt=0,
                )),
                transcode_type=TRANSCODE_TYPE_MP3_V0,
                match_fn=lambda t: t['encoding'] == 'V0 (VBR)',
                auto_create=options['auto_create'],
            )
        if options[TRANSCODE_TYPE_MP3_320]:
            print('Scanning for MP3 320 transcodes...')
            self._scan_torrents(
                torrents=list(Torrent.objects.filter(
                    realm=self.realm,
                    torrent_info__redacted_torrent__format=RedactedTorrent.FORMAT_FLAC,
                    torrent_info__redacted_torrent__remaster_year__gt=0,
                )),
                transcode_type=TRANSCODE_TYPE_MP3_320,
                match_fn=lambda t: t['encoding'] == '320',
                auto_create=options['auto_create'],
            )
