import pygtk
pygtk.require('2.0')
from gi.repository import GUPnP, GUPnPAV, GObject, GLib
from pandora import pandora
import os, re, atexit, sys, time

CON_ID = None
MPDCLIENT = None
LIBRARY = None
GObject.threads_init()
CONTEXTS = []
MGR = None
SERVICES = []

def context_available(mgr, ctx, data=None):
    global CONTEXTS
    CONTEXTS.append(ctx)
    ctx.host_path("xml/device.xml", "device.xml")
    ctx.host_path("xml/AVTransport2.xml", "AVTransport2.xml")
    ctx.host_path("xml/ContentDirectory.xml", "ContentDirectory.xml")

    desc = "device.xml"
    desc_loc = "./xml/"

    rd = GUPnP.RootDevice.new(ctx, desc, desc_loc)
    rd.set_available(True)

    service = rd.get_service("urn:schemas-upnp-org:service:AVTransport:1")
    service.connect("action-invoked::Play", pandora_play)
    service.connect("action-invoked::Pause", pandora_play)
    service.connect("action-invoked::Next", pandora_next)
    service.connect("action-invoked::SetAVTransportURI", handle_uri_change)
    service.connect("action-invoked::GetTransportInfo", handle_state_request)
    service.connect("action-invoked::GetPositionInfo",  handle_position_request)

    directory = rd.get_service("urn:schemas-upnp-org:service:ContentDirectory:1")
    directory.connect("action-invoked::Browse", list_stations)

    SERVICES.append(service)
    SERVICES.append(directory)

    MGR.manage_root_device(rd)

    print "Context setup for %s" % ctx.get_interface()

def setup_server():
    global MGR
    
    MGR = GUPnP.ContextManager.create(0)
    MGR.connect("context-available", context_available)

def save_pandora_song_info(title, artist, album, love):
    print title, artist, album
    CLIENT.title = title
    CLIENT.artist = artist
    CLIENT.album = album

def save_pandora_time_info(timeinfo):
    stime = re.match("^.+(\d+\:\d+)\/(\d+\:\d\d)$", timeinfo)
    CLIENT.total_time = time_to_int("00:" + stime.group(2))
    CLIENT.elapsed_time = (CLIENT.total_time - 
                           time_to_int("00:" + stime.group(1)))


def setup_pandora():
    c = pandora.Config()
    c.load()
    if not c.user:
	c.user = raw_input("Pandora Username:")
	import getpass
	c.password = getpass.getpass()
	c.write()

    global CLIENT
    CLIENT = pandora.Pandora(c) 
    CLIENT.start()

    CLIENT.song_callback = save_pandora_song_info
    CLIENT.second_callback = save_pandora_time_info

def int_to_time(timevalue):
    timevalue = int(timevalue)
    return "%.2d:%.2d:%.2d" % (int(timevalue / 3600),
                               int(timevalue / 60),
                               timevalue % 60)

def time_to_int(time):
    (hour, min, sec) = time.split(":")
    return (int(hour) * 3600) + (int(min) * 60) + int(sec)
    
        
def handle_position_request(service, action):
    print "Position"
    
    w = GUPnPAV.GUPnPDIDLLiteWriter.new("English")   

    item = w.add_item()
    item.set_title(getattr(CLIENT, "title", ""))
    item.set_artist(getattr(CLIENT, "artist", ""))
    item.set_album("%s (%s)" % (getattr(CLIENT, "album", ""),
                                getattr(CLIENT, "station")))

    action.set_value("Track", "0")
    action.set_value("TrackMetaData", w.get_string())
    action.set_value("TrackURI", "") #getattr(song, "url", ""))

    action.set_value("TrackDuration",
                    int_to_time(getattr(CLIENT, "total_time", 0)))
    
    curtime = int_to_time(getattr(CLIENT, "elapsed_time", 0))
    action.set_value("RelTime", curtime)
    action.set_value("AbsTime", curtime)
    
    getattr(action, "return")()

def handle_state_request(service, action):
    print "Status"

    if CLIENT.playing:
        state = "PLAYING"
    else:
        state = "PAUSED_PLAYBACK"

    action.set_value("CurrentTransportState", state)
    action.set_value("CurrentTransportStatus", "OK")
    action.set_value("CurrentSpeed", "1")
    
    getattr(action, "return")()


def pandora_play(service, action):
  print "Play"
  CLIENT.toggle()
  getattr(action, "return")()

def pandora_next(service, action):
  print "Next"
  CLIENT.next()
  getattr(action, "return")()

def set_pandora_uri(service, action, uri):
    print "Playing %s" % uri
    match = re.search("/station\/(.*)$", uri)
    if not match:
        action.return_error(0, "Invalid URI")
        
    station = match.groups()[0]
    print station
    CLIENT.setStation(station)

    getattr(action, "return")()

def list_stations(service, action):
    w = GUPnPAV.GUPnPDIDLLiteWriter.new("English")

    for station in CLIENT.stations:
        item = w.add_item()
        item.set_title(station)
        uri = "http://%s:%s/station/%s" % (
            CONTEXT.get_host_ip(),
            CONTEXT.get_port(),
            station
            )

        res = item.add_resource()
        res.set_uri(uri)
        
    action.set_value("Result", w.get_string())
    action.set_value("NumberReturned", len(CLIENT.stations))
    action.set_value("TotalMatches", len(CLIENT.stations))
    action.set_value("UpdateID", "0")

    getattr(action, "return")()

def handle_uri_change(service, action):
    uri = action.get_value("CurrentURI", GObject.TYPE_STRING)
    print "Change URI: %s" % uri
    if not uri:
        getattr(action, "return")()
        return None

    if CONTEXT.get_host_ip() in uri and str(CONTEXT.get_port()) in uri:
        return set_pandora_uri(service, action, uri)
    else:
        action.return_error(0, "Invalid URI")


rd = setup_server()
print "UPnP MediaRenderer Service Exported"

setup_pandora()
print "Pandora Client Setup"


print "Awaiting commands..."
try:
    GObject.MainLoop().run()
except KeyboardInterrupt:    
    print "Done"
    sys.exit(0)



