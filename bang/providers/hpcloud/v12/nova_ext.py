import urllib
from novaclient import base
from novaclient.v1_1.volumes import VolumeManager


VOLUMES_ENDPOINT = '/os-volumes'


class DiabloVolumeManager(VolumeManager):
    """
    The volumes extension deployed by HP Cloud uses an older endpoint,
    ``/os-volumes``, from the OpenStack Diablo timeframe.  Unfortunately, the
    endpoint in ``python-novaclient`` is hardcoded.  This class overrides any
    methods that specify an endpoint of ``/volumes``.

    Besides the use of the ``/os-volumes`` endpoint, the methods in this class
    were mostly pinched from its base,
    :class:`novaclient.v1_1.volumes.VolumeManager`.

    """
    def create(self, size, snapshot_id=None, display_name=None,
            display_description=None, volume_type=None, availability_zone=None,
            imageRef=None):
        body = {
                'volume': {
                    'size': size,
                    'snapshot_id': snapshot_id,
                    'display_name': display_name,
                    'display_description': display_description,
                    'volume_type': volume_type,
                    'availability_zone': availability_zone,
                    'imageRef': imageRef,
                    }
                }
        return self._create(VOLUMES_ENDPOINT, body, 'volume')

    def get(self, volume_id):
        return self._get("%s/%s" % (VOLUMES_ENDPOINT, volume_id), "volume")

    def list(self, detailed=True, search_opts=None):
        path = VOLUMES_ENDPOINT + '/detail' if detailed else VOLUMES_ENDPOINT

        if search_opts:
            qparams = dict((k, v) for (k, v) in search_opts.iteritems() if v)
            url = '%s?%s' % (path, urllib.urlencode(qparams))
        else:
            url = path

        return self._list(url, "volumes")

    def delete(self, volume):
        self._delete("%s/%s" % (VOLUMES_ENDPOINT, base.getid(volume)))
