import os

from Harvest.utils import get_logger
from plugins.redacted.client import RedactedClient
from plugins.redacted.tracker import RedactedTrackerPlugin
from torrents.models import Realm
from trackers.registry import TrackerRegistry

logger = get_logger(__name__)


class RedactedStepExecutorMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = RedactedClient()
        self.tracker = TrackerRegistry.get_plugin(RedactedTrackerPlugin.name, 'redacted_uploader_step')
        self.realm = Realm.objects.get(name=self.tracker.name)


def shorten_filename_if_necessary(torrent_name, root, rel_path):
    len_debt = len(rel_path) + len(torrent_name) + 1 - 180  # 1 for the /
    if len_debt <= 0:
        return

    filename = os.path.basename(rel_path)
    dirname = os.path.dirname(rel_path)

    new_len = len(filename) - len_debt
    if new_len < 40:
        raise Exception('Shortening the filename will make it less than 40 chars - {0}'.format(new_len))

    filename_root, filename_ext = os.path.splitext(filename)
    new_filename = filename_root[:-(len_debt + 3)] + '...' + filename_ext
    new_rel_path = os.path.join(dirname, new_filename)

    logger.info('Shortening {} to {}.', rel_path, new_rel_path)

    src_path = os.path.join(root, rel_path)
    dst_path = os.path.join(root, new_rel_path)
    if os.path.exists(dst_path):
        raise Exception('Renaming {} to {} for shortening would case a collision'.format(src_path, dst_path))
    os.rename(src_path, dst_path)
