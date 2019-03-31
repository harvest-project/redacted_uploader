from plugins.redacted_uploader.executors.utils import RedactedStepExecutorMixin
from upload_studio.step_executor import StepExecutor


class RedactedUploadTranscodeExecutor(RedactedStepExecutorMixin, StepExecutor):
    name = 'redacted_upload_transcode'
    description = 'Upload a transcoded torrent to Redacted.'

    def handle_run(self):
        raise NotImplementedError()
