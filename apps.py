from django.apps import AppConfig

from upload_studio.executor_registry import ExecutorRegistry


class RedactedUploaderConfig(AppConfig):
    name = 'plugins.redacted_uploader'

    def ready(self):
        from .executors import redacted_torrent_source, redacted_upload_transcode
        ExecutorRegistry.register_executor(redacted_torrent_source.RedactedTorrentSourceExecutor)
        ExecutorRegistry.register_executor(redacted_upload_transcode.RedactedUploadTranscodeExecutor)
