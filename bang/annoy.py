import os
import subprocess
import sys
from bang import BANG_DIR, attributes as A


PLAY_CMD = 'afplay' if sys.platform == 'darwin' else 'aplay'
BANG_WAV = os.path.join(BANG_DIR, 'bang.wav')
PLAY_WAV = '%s %s' % (PLAY_CMD, BANG_WAV)


def annoy(config):
    if not config.get(A.ANNOY_ME, True):
        return
    try:
        with open(os.devnull, 'w') as dn:
            subprocess.Popen(
                    PLAY_WAV,
                    shell=True,
                    stdout=dn,
                    stderr=subprocess.STDOUT,
                    )
    except:
        pass
