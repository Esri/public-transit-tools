#   Copyright 2015 Esri
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#
#   you may not use this file except in compliance with the License.
#
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#
#   distributed under the License is distributed on an "AS IS" BASIS,
#
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#
#   See the License for the specific language governing permissions and
#
#   limitations under the License.

def main():

    # need the GTFS Python bindings
    from google.transit import gtfs_realtime_pb2
    import urllib
    import json
    import socket
    import time

    # create socket connection to hostname/port on which a TCP GeoEvent input is running
    tcpSocket = socket.create_connection(("<hostname>", 5565))

    # polling model - run, wait 5 seconds, run, wait, run, wait, etc
    while True:

        feed = gtfs_realtime_pb2.FeedMessage()

        # this particular feed is from CT Transit (http://www.cttransit.com/about/developers/gtfsdata/)
        response = urllib.urlopen('http://65.213.12.244/realtimefeed/vehicle/vehiclepositions.pb')

        # read the Protocal Buffers (.pb) file
        feed.ParseFromString(response.read())

        # loop through feed entities
        for entity in feed.entity:

            # check for a vehicle in feed entity
            if entity.HasField('vehicle'):

                # build a simple id,lon,lat message to send to GeoEvent.
                msg = str(entity.vehicle.vehicle.label) + "," + \
                str(entity.vehicle.position.longitude) + "," + \
                str(entity.vehicle.position.latitude) + "\n"

                # send message
                tcpSocket.send(msg)

        time.sleep(5)

if __name__ == '__main__':
    main()


