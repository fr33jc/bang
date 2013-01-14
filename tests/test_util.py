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
import bang.util as U
import nose.tools as T


def test_deep_merge_dicts():
    a = {
            'a': 1,
            'b': 2,
            'c': 3,
            'd': {
                'd1': 'one',
                'd2': 'two',
                'd3': 'three',
                },
            'e': {
                'eA': 'ay',
                'eB': {
                    'eB1': 'uno',
                    'eB2': 'dos',
                    'eB3': {
                        'eB3a': 'ah',
                        'eB3b': 'bay',
                        'eB3f': 'same',
                        },
                    },
                }
            }
    b = {
            'c': 42,
            'd': {
                'd1': 'new',
                'd3': ['replace', 'the', 'scalar'],
                'd4': 4,
                },
            'e': {
                'eB': {
                    'eB3': {
                        'eB3a': 'alpha',
                        'eB3e': 'echo',
                        'eB3f': 'same',
                        },
                    },
                },
            'z': 26,
            }
    exp = {
            'a': 1,
            'b': 2,
            'c': 42,
            'd': {
                'd1': 'new',
                'd2': 'two',
                'd3': ['replace', 'the', 'scalar'],
                'd4': 4,
                },
            'e': {
                'eA': 'ay',
                'eB': {
                    'eB1': 'uno',
                    'eB2': 'dos',
                    'eB3': {
                        'eB3a': 'alpha',
                        'eB3b': 'bay',
                        'eB3e': 'echo',
                        'eB3f': 'same',
                        },
                    },
                },
            'z': 26,
            }
    U.deep_merge_dicts(a, b)
    T.eq_(exp, a)
