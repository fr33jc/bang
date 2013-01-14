# Copyright 2012 - John Calixto
#
# This file is part of bang.
#
# bang is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# bang is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with bang.  If not, see <http://www.gnu.org/licenses/>.
import os.path

try:
    import bang.version
    VERSION = bang.version.VERSION
except ImportError:
    VERSION = 'badonkadonk'

BANG_DIR = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            '..',
            )
        )

WORK_DIR = os.path.join(BANG_DIR, 'work')

CONFIG_DIR = os.path.join(BANG_DIR, 'config')


class BangError(Exception):
    pass


class TimeoutError(BangError):
    pass
