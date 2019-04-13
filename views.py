from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView

from Harvest.utils import CORSBrowserExtensionView
from plugins.redacted_uploader.create_project import create_transcode_project
from upload_studio.serializers import ProjectDeepSerializer


class TranscodeTorrent(CORSBrowserExtensionView, APIView):
    @transaction.atomic
    def post(self, request):
        tracker_id = int(request.data['tracker_id'])
        transcode_type = request.data['transcode_type']

        project = create_transcode_project(tracker_id, transcode_type)

        return Response(ProjectDeepSerializer(project).data)
