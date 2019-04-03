from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from Harvest.utils import CORSBrowserExtensionView
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
from upload_studio.models import Project, ProjectStep
from upload_studio.serializers import ProjectDeepSerializer
from upload_studio.tasks import project_run_all


class TranscodeTorrent(CORSBrowserExtensionView, APIView):
    @transaction.atomic
    def post(self, request):
        tracker_id = int(request.data['tracker_id'])

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
            name='{} - {}'.format(
                get_shorter_joined_artists(torrent_group.music_info, torrent_group.name),
                torrent_group.name,
            ),
            source_torrent=torrent,
        )
        project.steps.append(ProjectStep(
            executor_name=RedactedTorrentSourceExecutor.name,
        ))
        project.steps.append(ProjectStep(
            executor_name=LAMETranscoderExecutor.name,
            executor_kwargs={
                'bitrate': 'V0 (VBR)',
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
            transaction.on_commit(lambda: project_run_all(project.id))

        return Response(ProjectDeepSerializer(project).data)
