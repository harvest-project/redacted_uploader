import os
import time

from Harvest.path_utils import copytree_into
from Harvest.utils import get_logger
from plugins.redacted.exceptions import RedactedUploadException, RedactedException
from plugins.redacted_uploader.executors.utils import RedactedStepExecutorMixin
from torrents import add_torrent
from upload_studio.audio_utils import AudioDiscoveryStepMixin
from upload_studio.step_executor import StepExecutor
from upload_studio.upload_metadata import MusicMetadata

logger = get_logger(__name__)

PRE_EMPHASIS_TERMS = {'pre-emphasized', 'pre-emphasis', 'preemphasized', 'pre-emphasis'}


class RedactedUploadTranscodeExecutor(AudioDiscoveryStepMixin, RedactedStepExecutorMixin, StepExecutor):
    name = 'redacted_upload_transcode'
    description = 'Upload a transcoded torrent to Redacted.'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.uploaded_torrent_id = None

    def check_downsampling_rules(self):
        red_torrent = self.metadata.additional_data['source_red_torrent']
        downsample = self.metadata.additional_data.get('downsample_data')
        if not downsample:
            logger.info('Detected no downsampling.')
            return

        logger.info('Detected downsampling. Verifying rules.')

        bits_per_sample = self.stream_info.bits_per_sample
        is_inconsistent = (
                downsample['dst_sample_rate'] != self.stream_info.sample_rate or
                (bits_per_sample and downsample['dst_bits_per_sample'] != bits_per_sample) or
                downsample['dst_channels'] != self.stream_info.channels
        )
        if is_inconsistent:
            self.raise_error('Inconsistent downsample data and current file metadata.')

        changed_sample_rate = downsample['src_sample_rate'] != self.stream_info.sample_rate
        changed_channels = downsample['src_channels'] != self.stream_info.channels
        changed_bits_per_sample = bits_per_sample and downsample['src_bits_per_sample'] != bits_per_sample
        is_redbook = (
                downsample['dst_sample_rate'] == 44100 and
                downsample['dst_bits_per_sample'] == 16 and
                downsample['dst_channels'] == 2
        )

        if changed_sample_rate and downsample['src_sample_rate'] < 88200:
            self.raise_error('Downsampling is only allowed from 88.2khz or more.')

        if red_torrent['media'] == MusicMetadata.MEDIA_CD:
            if not is_redbook:
                self.raise_error('Non-redbook format CD sources are suspicious.')
            if changed_sample_rate or changed_channels or changed_bits_per_sample:
                self.raise_error('Downmixing/resampling CD sources is prohibited.')
        elif red_torrent['media'] == MusicMetadata.MEDIA_WEB:
            pass  # Downsampling from less than 88.2khz is already covered generally
        elif red_torrent['media'] == MusicMetadata.MEDIA_SACD:
            if changed_channels:
                self.raise_error('Downmixing of SACD is prohibited.')
            if MusicMetadata.format_is_lossy and not is_redbook:
                self.raise_error('SACD lossy data must be uploaded in redbook format.')
        elif red_torrent['media'] == MusicMetadata.MEDIA_BLU_RAY:
            if changed_channels:
                self.raise_error('Downmixing of Blu-Ray is prohibited.')
            if MusicMetadata.format_is_lossy and not is_redbook:
                self.raise_error('Blu-Ray lossy data must be uploaded in redbook format.')

    def check_metadata(self):
        red_torrent = self.metadata.additional_data['source_red_torrent']

        is_preemphasized = (any(term in red_torrent['remasterTitle'].lower() for term in PRE_EMPHASIS_TERMS) or
                            any(term in red_torrent['description'].lower() for term in PRE_EMPHASIS_TERMS))
        if is_preemphasized:
            self.add_warning('Source torrent looks like it might be pre-emphasized. De-emphasizing is not supported.'
                             ' Please check the source torrent and do it manually if needed.')

        if not self.metadata.edition_year:
            self.add_warning('Metadata has empty year.')
        has_any_edition_information = (
                self.metadata.edition_title or
                self.metadata.edition_record_label or
                self.metadata.edition_catalog_number
        )
        if not has_any_edition_information:
            self.add_warning('Metadata has empty title/label/catalog number.')

    def detect_duplicates(self):
        red_group = self.client.get_torrent_group(self.metadata.additional_data['source_red_group']['id'])
        for t in red_group['torrents']:
            is_same = (
                    t['format'] == self.metadata.format and
                    t['media'] == self.metadata.media and
                    t['encoding'] == self.metadata.encoding and
                    t['remastered'] == True and  # Can remastered be False with newer Red Gazelle?
                    t['remasterYear'] == self.metadata.edition_year and
                    t['remasterTitle'] == self.metadata.edition_title and
                    t['remasterRecordLabel'] == self.metadata.edition_record_label and
                    t['remasterCatalogueNumber'] == self.metadata.edition_catalog_number
            )
            if is_same:
                self.add_warning('Torrent will potentially duplicate Red torrent {}. Please confirm manually.'.format(
                    t['id']))

    def _get_torrent_file(self):
        torrent_area = self.step.get_area_path('torrent_file')
        files = os.listdir(torrent_area)
        if len(files) != 1:
            self.raise_error('Expected exactly 1 file in {}.'.format(torrent_area))
        with open(os.path.join(torrent_area, files[0]), 'rb') as f:
            return f.read()

    def upload_torrent(self):
        logger.info('{} sending request for upload to Redacted.'.format(self.project))

        self.metadata.processing_steps.append(
            'Upload to Redacted group {} with year "{}", title "{}", record label "{}" and catalog number "{}".'.format(
                self.metadata.additional_data['source_red_group']['id'],
                self.metadata.edition_year,
                self.metadata.edition_title,
                self.metadata.edition_record_label,
                self.metadata.edition_catalog_number
            ),
        )

        torrent_file = self._get_torrent_file()

        steps_desc = '\n'.join('- {}'.format(s) for s in self.metadata.processing_steps)
        release_desc = 'Made with Harvest\'s Upload Studio. Creation process: \n\n{}'.format(steps_desc)

        payload = {
            'submit': 'true',
            'type': 'Music',
            'groupid': self.metadata.additional_data['source_red_group']['id'],
            'format': self.metadata.format,
            'bitrate': self.metadata.encoding,
            'media': self.metadata.media,
            'release_desc': release_desc,

            'remaster': 'on',
            'remaster_year': self.metadata.edition_year,
            'remaster_title': self.metadata.edition_title,
            'remaster_record_label': self.metadata.edition_record_label,
            'remaster_catalogue_number': self.metadata.edition_catalog_number,
        }

        try:
            self.client.perform_upload(payload, torrent_file)
        except RedactedUploadException as exc:
            area = self.step.get_area_path('redacted_error')
            os.makedirs(area, exist_ok=True)
            with open(os.path.join(area, 'redacted_upload.html'), 'w') as f:
                f.write(exc.raw_response)
            # If this warning is not acked, a potentially uploaded torrent could be uploaded again.
            self.add_warning(
                'Error uploading to Redacted: {}. HTML error file saved to redacted_error.'.format(
                    exc.parsed_error),
                acked=True
            )

    def discover_torrent(self):
        for _ in range(3):
            try:
                red_data = self.client.get_torrent_by_info_hash(self.metadata.torrent_info_hash)
                break
            except RedactedException:
                time.sleep(2)
        else:
            self.raise_error('Unable to find uploaded torrent. Upload failed.')

        self.uploaded_torrent_id = red_data['torrent']['id']

    def _store_files(self, torrent_info, download_path):
        logger.info('Moving torrent files into final destination.')
        dest = os.path.join(download_path, self.metadata.torrent_name)
        copytree_into(self.step.data_path, dest)

    def add_torrent(self):
        logger.info('Adding torrent to Harvest.')
        download_location = self.realm.get_preferred_download_location()
        add_torrent.add_torrent_from_tracker(
            tracker=self.tracker,
            tracker_id=str(self.uploaded_torrent_id),
            download_path_pattern=download_location.pattern,
            store_files_hook=self._store_files,
        )

    def handle_run(self):
        self.copy_prev_step_files()
        self.discover_audio_files()
        self.check_downsampling_rules()
        self.check_metadata()
        self.detect_duplicates()
        self.raise_warnings()
        self.upload_torrent()
        self.discover_torrent()
        self.add_torrent()
