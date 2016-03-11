################################################################################
# hms.py, originally written by Luitien Pan
# Functions for handling HH:MM:SS time strings.
################################################################################
'''Copyright 2016 Esri
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.'''
################################################################################

def sec2hms(seconds):
	H = int(seconds) / 3600
	t = seconds % 3600
	M = int(t) / 60
	S = t % 60
	return H,M,S

def sec2str(seconds):
    return "%02d:%02d:%02d" % sec2hms (seconds)

def hms2sec(H, M = 0, S = 0):
	return float(H) * 3600 + float(M) * 60 + float(S)

def str2sec(HMS):
	'''"H:M:S" -> seconds'''
	while HMS.count(':') < 2:
		HMS = '0:' + HMS
	return hms2sec( *HMS.split(':') )

def hmsdiff(str1, str2):
    '''Returns str1 - str2, in seconds.'''
    return str2sec(str1) - str2sec(str2)
