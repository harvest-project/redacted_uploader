from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import APIException

from plugins.redacted.client import RedactedClient
from plugins.redacted.tracker import RedactedTrackerPlugin
from plugins.redacted.utils import get_shorter_joined_artists
from plugins.redacted_uploader.executors.redacted_check_file_tags import RedactedCheckFileTags
from plugins.redacted_uploader.executors.redacted_torrent_source import RedactedTorrentSourceExecutor
from plugins.redacted_uploader.executors.redacted_upload_transcode import RedactedUploadTranscodeExecutor
from torrents.add_torrent import add_torrent_from_tracker, fetch_torrent
from torrents.models import Torrent, Realm
from trackers.registry import TrackerRegistry
from upload_studio.executors.create_torrent_file import CreateTorrentFileExecutor
from upload_studio.executors.finish_upload import FinishUploadExecutor
from upload_studio.executors.lame_transcode import LAMETranscoderExecutor
from upload_studio.executors.sox_process import SoxProcessExecutor
from upload_studio.models import Project, ProjectStep
from upload_studio.tasks import project_run_all
from upload_studio.upload_metadata import MusicMetadata

TRANSCODE_TYPE_MP3_V0 = 'mp3_v0'
TRANSCODE_TYPE_MP3_320 = 'mp3_320'
TRANSCODE_TYPE_REDBOOK_FLAC = 'redbook_flac'
TRANSCODE_TYPES = {
    TRANSCODE_TYPE_MP3_V0,
    TRANSCODE_TYPE_MP3_320,
    TRANSCODE_TYPE_REDBOOK_FLAC,
}


@transaction.atomic
def create_transcode_project(tracker_id, transcode_type):
    if transcode_type not in TRANSCODE_TYPES:
        raise APIException(
            'Unknown transcode type. Supported types: {}'.format(TRANSCODE_TYPES),
            code=status.HTTP_400_BAD_REQUEST,
        )
    tracker = TrackerRegistry.get_plugin(RedactedTrackerPlugin.name, 'transcode_torrent')
    realm = Realm.objects.get(name=RedactedTrackerPlugin.name)
    download_location = realm.get_preferred_download_location()
    if not download_location:
        raise APIException(
            'No download location available for realm {}'.format(realm.name),
            code=status.HTTP_400_BAD_REQUEST,
        )
    torrent_info = fetch_torrent(
        realm=realm,
        tracker=tracker,
        tracker_id=tracker_id,
        force_fetch=True,
    )
    try:
        torrent = torrent_info.torrent
    except Torrent.DoesNotExist:
        torrent = add_torrent_from_tracker(
            tracker=tracker,
            tracker_id=tracker_id,
            download_path_pattern=download_location.pattern,
            force_fetch=False,
        )
    torrent_group = torrent_info.redacted_torrent.torrent_group
    project = Project.objects.create(
        media_type=Project.MEDIA_TYPE_MUSIC,
        project_type='redacted_transcode_{}'.format(transcode_type),
        name='{} - {} ({})'.format(
            get_shorter_joined_artists(torrent_group.music_info, torrent_group.name),
            torrent_group.name,
            transcode_type,
        ),
        source_torrent=torrent,
    )
    project.steps.append(ProjectStep(
        executor_name=RedactedTorrentSourceExecutor.name,
    ))
    project.steps.append(ProjectStep(
        executor_name=SoxProcessExecutor.name,
        executor_kwargs={
            'target_sample_rate': SoxProcessExecutor.TARGET_SAMPLE_RATE_44100_OR_4800,
            'target_bits_per_sample': 16,
            'target_channels': 2,
        },
    ))
    if transcode_type in {TRANSCODE_TYPE_MP3_V0, TRANSCODE_TYPE_MP3_320}:
        project.steps.append(ProjectStep(
            executor_name=LAMETranscoderExecutor.name,
            executor_kwargs={
                'bitrate': {
                    TRANSCODE_TYPE_MP3_V0: MusicMetadata.ENCODING_V0,
                    TRANSCODE_TYPE_MP3_320: MusicMetadata.ENCODING_320,
                }[transcode_type],
            },
        ))
    project.steps.append(ProjectStep(
        executor_name=RedactedCheckFileTags.name,
    ))
    project.steps.append(ProjectStep(
        executor_name=CreateTorrentFileExecutor.name,
        executor_kwargs={
            'announce': RedactedClient().get_announce(),
            'extra_info_keys': {
                'source': 'RED',
            }
        },
    ))
    project.steps.append(ProjectStep(
        executor_name=RedactedUploadTranscodeExecutor.name,
    ))
    project.steps.append(ProjectStep(
        executor_name=FinishUploadExecutor.name,
    ))
    project.save_steps()
    # If the torrent is complete, launch it. Otherwise the torrent_finished receiver will start it when received.
    if torrent.progress == 1:
        project_run_all.delay(project.id)
    return project
