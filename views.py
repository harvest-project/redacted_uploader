from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from plugins.redacted.tracker import RedactedTrackerPlugin
from plugins.redacted_uploader.executors.redacted_torrent_source import RedactedTorrentSourceExecutor
from plugins.redacted_uploader.executors.redacted_upload_transcode import RedactedUploadTranscodeExecutor
from torrents.models import TorrentInfo
from upload_studio.executors.create_torrent_file import CreateTorrentFileExecutor
from upload_studio.executors.finish_upload import FinishUploadExecutor
from upload_studio.executors.lame_transcode import LAMETranscoderExecutor
from upload_studio.models import Project, ProjectStep
from upload_studio.serializers import ProjectDeepSerializer


class TranscodeTorrent(APIView):
    @transaction.atomic
    def post(self, request):
        tracker_id = int(request.data['tracker_id'])
        try:
            torrent_info = TorrentInfo.objects.get(realm__name=RedactedTrackerPlugin.name, tracker_id=tracker_id)
        except TorrentInfo.DoesNotExist:
            raise APIException('Torrent not found in DB.', code=status.HTTP_400_BAD_REQUEST)
        project = Project.objects.create(
            media_type=Project.MEDIA_TYPE_MUSIC,
            name=torrent_info.redacted_torrent.torrent_group.name,
        )
        project.steps.append(ProjectStep(
            executor_name=RedactedTorrentSourceExecutor.name,
            executor_kwargs={
                'tracker_id': tracker_id,
            },
        ))
        project.steps.append(ProjectStep(
            executor_name=LAMETranscoderExecutor.name,
            executor_kwargs={
                'bitrate': 'V0 (VBR)',
            }
        ))
        project.steps.append(ProjectStep(
            executor_name=CreateTorrentFileExecutor.name,
            executor_kwargs={
                'torrent_name': 'NEVER UPLOAD THIS TORRENT NAME',
                'announce': 'demo fake announce',  # RedactedClient().get_announce()
            }
        ))
        project.steps.append(ProjectStep(
            executor_name=RedactedUploadTranscodeExecutor.name
        ))
        project.steps.append(ProjectStep(
            executor_name=FinishUploadExecutor.name
        ))
        project.save_steps()
        return Response(ProjectDeepSerializer(project).data)
