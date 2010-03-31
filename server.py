import pygtk
pygtk.require('2.0')
from gi.repository import GUPnP, GUPnPAV, GObject, GLib
from pandora import pandora
import os, re, atexit, sys, time

CON_ID = None
MPDCLIENT = None
LIBRARY = None
GObject.threads_init()
CONTEXT = None

def setup_server():
    global CONTEXT
    
    ctx = GUPnP.Context(interface="wlan0")

    ctx.host_path("xml/device.xml", "device.xml")
    ctx.host_path("xml/AVTransport2.xml", "AVTransport2.xml")
    ctx.host_path("xml/ContentDirectory.xml", "ContentDirectory.xml")

    ctx.host_path("/mnt/nixsys/Music/all/Seether/Seether featuring Amy Lee - Broken.mp3", "/file/test.mp3")

    desc = "device.xml"
    desc_loc = "./xml/"

    rd = GUPnP.RootDevice.new(ctx, desc, desc_loc)
    rd.set_available(True)

    CONTEXT = ctx
    return rd

def save_pandora_song_info(title, artist, album, love):
    print title, artist, album
    CLIENT.title = title
    CLIENT.artist = artist
    CLIENT.album = album

def save_pandora_time_info(timeinfo):
    stime = re.match("^.+(\d+\:\d+)\/(\d+\:\d\d)$", timeinfo)
    CLIENT.total_time = time_to_int("00:" + stime.group(2))
    CLIENT.elapsed_time = CLIENT.total_time - time_to_int("00:" + stime.group(1))

def setup_pandora():
    c = pandora.Config()
    global CLIENT
    CLIENT = pandora.Pandora(c) 
    CLIENT.start()

    CLIENT.song_callback = save_pandora_song_info
    CLIENT.second_callback = save_pandora_time_info


rd = setup_server()
print "UPnP MediaRenderer Service Exported"

setup_pandora()
print "Pandora Client Setup"

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
    item.set_album(getattr(CLIENT, "album", ""))

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

service = rd.get_service("urn:schemas-upnp-org:service:AVTransport:1")
service.connect("action-invoked::Play", pandora_play)
service.connect("action-invoked::Pause", pandora_play)
service.connect("action-invoked::Next", pandora_next)
#service.connect("action-invoked::SetAVTransportURI", handle_uri_change)
service.connect("action-invoked::GetTransportInfo", handle_state_request)
service.connect("action-invoked::GetPositionInfo",  handle_position_request)

#directory = rd.get_service("urn:schemas-upnp-org:service:ContentDirectory:1")
#directory.connect("action-invoked::Browse", browse_action)

print "Awaiting commands..."
try:
    GObject.MainLoop().run()
except KeyboardInterrupt:    
    print "Done"
    sys.exit(0)




def set_pandora_uri(service, action, uri):
    print "Playing %s" % uri
    match = re.search("/file\/(.*)$", uri)
    if not match:
        action.return_error(0, "Invalid URI")
        
    itemid = int(match.groups()[0])
    
    song = LIBRARY.get_by_id(itemid)

    if not isinstance(song, MPDSong):
        action.return_error()
        return
    
    MPDCLIENT.connect()
    songdata = MPDCLIENT.playlistfind('file', song.file)
    
    if songdata:        
        # If the song is in the current playlist move to it and play it
        MPDCLIENT.seek(songdata[0]['pos'], 0)
    else:
        # Else add it to the playlist then play it
        MPDCLIENT.add(song.file)
        songdata = MPDCLIENT.playlistfind('file', song.file)
        if not songdata:
            action.return_error()
            return
        MPDCLIENT.seek(songdata[0]['pos'], 0)

    MPDCLIENT.disconnect()
    getattr(action, "return")()


def set_http_uri(service, action, uri):
    """
    This is a bit tricker.  We need to download the file from the local network
    (hopefully its quick), add the file to MPD (the file has to be 100% downloaded first)
    then add the file to the playlist and seek to it.

    1) Download file
    2) Add file to DB
    3) Load file to local library
    4) Generate an pandora uri and then call set_pandora_uri
    """
    path = uri.replace("http:/", "")
    filename = os.path.basename(path)

    if not "." in filename:
        filename += ".mp3" # assume mp3 for now
    
    os.system("wget %s -O %s/%s" % (uri, MUSIC_PATH, filename))
    
    LIBRARY.connect()
    MPDCLIENT.update(filename)
    
    songdata = MPDCLIENT.find('file', filename)
    if not songdata:
        action.return_error(0, "Couldn't add file to MPD database")
        return
    
    song_id = LIBRARY.register_song(LIBRARY.song_from_dict(songdata[0]))

    LIBRARY.disconnect()
    set_mpd_uri(service, action, "http://%s:%s/file/%s" % (
        CONTEXT.get_host_ip(),
        CONTEXT.get_port(),
        song_id)
                )
    
def handle_uri_change(service, action):
    uri = action.get_value_type("CurrentURI", GObject.TYPE_STRING)
    if not uri:
      return None

    if CONTEXT.get_host_ip() in uri and str(CONTEXT.get_port()) in uri:
        return set_pandora_uri(service, action, uri)
    else:
        return set_http_uri(service, action, uri)


