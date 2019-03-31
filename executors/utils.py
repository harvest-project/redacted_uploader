from plugins.redacted.tracker import RedactedTrackerPlugin
from torrents.models import Realm
from trackers.registry import TrackerRegistry


class RedactedStepExecutorMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker = TrackerRegistry.get_plugin(RedactedTrackerPlugin.name, 'redacted_uploader_step')
        self.realm = Realm.objects.get(name=self.tracker.name)
