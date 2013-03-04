from gi.repository import GUPnP, GUPnPAV, GObject, GLib
from pandora import pandora
import os, re, atexit, sys, time

CLIENT = None
CON_ID = None
MPDCLIENT = None
LIBRARY = None
GObject.threads_init()
CONTEXTS = []
MGR = None
SERVICES = []
proto = GUPnPAV.ProtocolInfo()
proto.set_mime_type("audio/mp3")
proto.set_network("*")
proto.set_protocol("http-get")

def context_available(mgr, ctx, data=None):
    global CONTEXTS
    CONTEXTS.append(ctx)
    ctx.host_path("xml/device.xml", "device.xml")
    ctx.host_path("xml/AVTransport2.xml", "AVTransport2.xml")
    ctx.host_path("xml/ContentDirectory.xml", "ContentDirectory.xml")
    ctx.host_path("xml/ConnectionManager.xml", "ConnectionManager.xml")

    server_desc = "server.xml"
    renderer_desc = "renderer.xml"
    desc_loc = "./xml/"

    mediaserver = GUPnP.RootDevice.new(ctx, server_desc, desc_loc)
    mediaserver.set_available(True)

    mediarenderer = GUPnP.RootDevice.new(ctx, renderer_desc, desc_loc)
    mediarenderer.set_available(True)

    avtransport = mediarenderer.get_service("urn:schemas-upnp-org:service:AVTransport:1")
    avtransport.connect("action-invoked::Play", pandora_play)
    avtransport.connect("action-invoked::Pause", pandora_play)
    avtransport.connect("action-invoked::Next", pandora_next)
    avtransport.connect("action-invoked::SetAVTransportURI", handle_uri_change)
    avtransport.connect("action-invoked::GetTransportInfo", handle_state_request)
    avtransport.connect("action-invoked::GetPositionInfo",  handle_position_request)
    avtransport.connect("action-invoked::GetMediaInfo",  av_get_mediainfo)
    avtransport.connect("action-invoked::SetNextAVTransportURI", handle_noop)
    avtransport.connect("action-invoked::GetMediaInfo_Ext", handle_noop)
    avtransport.connect("action-invoked::GetDeviceCapabilities", handle_noop)
    avtransport.connect("action-invoked::GetTransportSettings", handle_noop)
    avtransport.connect("action-invoked::Stop", handle_noop)
    avtransport.connect("action-invoked::Record", handle_noop)
    avtransport.connect("action-invoked::Seek", handle_noop)
    avtransport.connect("action-invoked::Previous", handle_noop)
    avtransport.connect("action-invoked::SetPlayMode", handle_noop)
    avtransport.connect("action-invoked::SetRecordQualityMode", handle_noop)
    avtransport.connect("action-invoked::GetCurrentTransportActions", handle_noop)
    avtransport.connect("action-invoked::GetDRMState", handle_noop)
    avtransport.connect("action-invoked::GetStateVariables", handle_noop)
    avtransport.connect("action-invoked::SetStateVariables", handle_noop)

    renderctl = mediarenderer.get_service("urn:schemas-upnp-org:service:RenderingControl:1")

    directory = mediaserver.get_service("urn:schemas-upnp-org:service:ContentDirectory:1")
    directory.connect("action-invoked::Browse", list_stations)

    connmgr = mediarenderer.get_service("urn:schemas-upnp-org:service:ConnectionManager:1")
    connmgr.connect("action-invoked::GetCurrentConnectionIDs", conn_get_ids)
    connmgr.connect("action-invoked::GetCurrentConnectionInfo", conn_get_info)
    connmgr.connect("action-invoked::GetProtocolInfo", conn_get_protocol)

    connmgr2 = mediaserver.get_service("urn:schemas-upnp-org:service:ConnectionManager:1")
    connmgr2.connect("action-invoked::GetCurrentConnectionIDs", conn_get_ids)
    connmgr2.connect("action-invoked::GetCurrentConnectionInfo", conn_get_info)
    connmgr2.connect("action-invoked::GetProtocolInfo", conn_get_protocol)
	
    SERVICES.append(avtransport)
    SERVICES.append(renderctl)
    SERVICES.append(directory)
    SERVICES.append(connmgr)
    SERVICES.append(connmgr2)

    MGR.manage_root_device(mediarenderer)
    MGR.manage_root_device(mediaserver)

    print "Context setup for %s" % ctx.get_interface()

def debug_service_call(func):
    def wrapper(service, action, *args, **kwargs):
        typ = service.get_service_type() 
        typ = typ.split(":")[-2:-1][0]
        device = service.props.root_device.get_device_type()
        device = device.split(":")[-2:-1][0]
        print "%s on %s/%s" % (action.get_name(), typ, device)
        return func(service, action, *args, **kwargs)

    return wrapper

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
    stime = timeinfo.split("/")
    CLIENT.total_time = time_to_int(stime[1])
    CLIENT.elapsed_time = (CLIENT.total_time - 
                           time_to_int(stime[0]))


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
    if time.count(":") == 2:
        (hour, min, sec) = time.split(":")
        return (int(hour) * 3600) + (int(min) * 60) + int(sec) 
    else:
        (min, sec) = time.split(":")
        return (int(min) * 60) + int(sec)
        
        
@debug_service_call
def handle_noop(service, action):
    getattr(action, "return")()

@debug_service_call
def av_get_mediainfo(service, action):
    getattr(action, "return")()

@debug_service_call
def handle_position_request(service, action):   
    w = GUPnPAV.DIDLLiteWriter.new("English")   

    item = w.add_item()
    item.set_title(getattr(CLIENT, "title", ""))
    item.set_artist(getattr(CLIENT, "artist", ""))
    item.set_album("%s (%s)" % (getattr(CLIENT, "album", ""),
                                getattr(CLIENT, "station", "")))

    action.set_value("Track", "0")
    action.set_value("TrackMetaData", w.get_string())
    ctx = service.get_context()
    uri = "http://%s:%s/station/%s" % (
            ctx.get_host_ip(),
            ctx.get_port(),
            CLIENT.station,
            )

    action.set_value("TrackURI", uri)

    action.set_value("TrackDuration",
                    int_to_time(getattr(CLIENT, "total_time", 0)))
    
    curtime = int_to_time(getattr(CLIENT, "elapsed_time", 0))
    action.set_value("RelTime", curtime)
    action.set_value("AbsTime", curtime)
    
    getattr(action, "return")()

@debug_service_call
def handle_state_request(service, action):
    if CLIENT and CLIENT.playing:
        state = "PLAYING"
    else:
        state = "PAUSED_PLAYBACK"

    action.set_value("CurrentTransportState", state)
    action.set_value("CurrentTransportStatus", "OK")
    action.set_value("CurrentSpeed", "1")
    
    getattr(action, "return")()


@debug_service_call
def conn_get_protocol(service, action, data=None):
  proto = "http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_LRG,http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_MED,http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_SM,http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_TN,http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_LRG_ICO,http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_SM_ICO,http-get:*:audio/L16;rate=48000;channels=2:DLNA.ORG_PN=LPCM,http-get:*:audio/L16;rate=48000;channels=1:DLNA.ORG_PN=LPCM,http-get:*:audio/L16;rate=44100;channels=1:DLNA.ORG_PN=LPCM,http-get:*:image/png:DLNA.ORG_PN=PNG_LRG,http-get:*:image/png:DLNA.ORG_PN=PNG_TN,http-get:*:image/png:DLNA.ORG_PN=PNG_LRG_ICO,http-get:*:image/png:DLNA.ORG_PN=PNG_SM_ICO,http-get:*:video/mpeg:DLNA.ORG_PN=MPEG_TS_SD_NA_ISO,http-get:*:audio/mp4:DLNA.ORG_PN=AMR_WBplus,http-get:*:audio/3gpp:DLNA.ORG_PN=AMR_3GPP,http-get:*:audio/mp4:DLNA.ORG_PN=AMR_3GPP,http-get:*:video/mpeg:DLNA.ORG_PN=MPEG1,http-get:*:video/mp4:DLNA.ORG_PN=AVC_MP4_MP_HD_1080i_AAC,http-get:*:video/mp4:DLNA.ORG_PN=AVC_MP4_MP_HD_720p_AAC,http-get:*:video/mp4:DLNA.ORG_PN=AVC_MP4_MP_SD_AC3,http-get:*:video/mp4:DLNA.ORG_PN=AVC_MP4_MP_SD_MPEG1_L3,http-get:*:video/mp4:DLNA.ORG_PN=AVC_MP4_MP_SD_AAC_MULT5,http-get:*:video/mp4:DLNA.ORG_PN=AVC_MP4_BL_L3_SD_AAC,http-get:*:video/mp4:DLNA.ORG_PN=AVC_MP4_BL_L3L_SD_AAC,http-get:*:video/mp4:DLNA.ORG_PN=AVC_MP4_BL_CIF15_AAC,http-get:*:video/mp4:DLNA.ORG_PN=AVC_MP4_BL_CIF15_AAC_520,http-get:*:audio/vnd.dolby.dd-raw:DLNA.ORG_PN=AC3,http-get:*:audio/mpeg:DLNA.ORG_PN=MP3X,http-get:*:video/3gpp:DLNA.ORG_PN=MPEG4_H263_MP4_P0_L10_AAC_LTP,http-get:*:video/3gpp:DLNA.ORG_PN=MPEG4_H263_MP4_P0_L10_AAC,http-get:*:video/mp4:DLNA.ORG_PN=MPEG4_P2_MP4_SP_L6_AAC,http-get:*:video/mp4:DLNA.ORG_PN=MPEG4_P2_MP4_SP_L5_AAC,http-get:*:video/mp4:DLNA.ORG_PN=MPEG4_P2_MP4_SP_L2_AAC,http-get:*:video/mp4:DLNA.ORG_PN=MPEG4_P2_MP4_SP_VGA_AAC,http-get:*:video/mp4:DLNA.ORG_PN=MPEG4_P2_MP4_SP_AAC_LTP,http-get:*:video/mp4:DLNA.ORG_PN=MPEG4_P2_MP4_SP_AAC,http-get:*:audio/3gpp:DLNA.ORG_PN=AAC_MULT5_ISO,http-get:*:audio/mp4:DLNA.ORG_PN=AAC_MULT5_ISO,http-get:*:audio/vnd.dlna.adts:DLNA.ORG_PN=AAC_MULT5_ADTS,http-get:*:audio/3gpp:DLNA.ORG_PN=AAC_ISO,http-get:*:audio/mp4:DLNA.ORG_PN=AAC_ISO,http-get:*:audio/vnd.dlna.adts:DLNA.ORG_PN=AAC_ADTS,http-get:*:audio/3gpp:DLNA.ORG_PN=AAC_ISO_320,http-get:*:audio/mp4:DLNA.ORG_PN=AAC_ISO_320,http-get:*:audio/vnd.dlna.adts:DLNA.ORG_PN=AAC_ADTS_320,http-get:*:audio/x-ms-wma:DLNA.ORG_PN=WMAPRO,http-get:*:audio/x-ms-wma:DLNA.ORG_PN=WMAFULL,http-get:*:audio/x-ms-wma:DLNA.ORG_PN=WMABASE,http-get:*:audio/L16;rate=44100;channels=2:DLNA.ORG_PN=LPCM,http-get:*:audio/mpeg:DLNA.ORG_PN=MP3,http-get:*:video/mpeg:DLNA.ORG_PN=MPEG_TS_SD_EU_ISO,http-get:*:video/mpeg:DLNA.ORG_PN=MPEG_TS_HD_NA_ISO,http-get:*:video/x-ms-wmv:DLNA.ORG_PN=WMVHIGH_FULL,http-get:*:*:*"
  action.set_value("Source", proto)
  action.set_value("Sink", proto)
  getattr(action, "return")()

@debug_service_call
def conn_get_info(service, action, data=None):
    pass

@debug_service_call
def conn_get_ids(*args):
    pass

@debug_service_call
def pandora_play(service, action):
  CLIENT.toggle()
  getattr(action, "return")()

@debug_service_call
def pandora_next(service, action, data=None):
  CLIENT.next()
  getattr(action, "return")()


@debug_service_call
def set_pandora_uri(service, action, uri):
    print "Playing %s" % uri
    match = re.search("/station\/(.*)$", uri)
    if not match:
        action.return_error(0, "Invalid URI")
        
    station = match.groups()[0]
    print station
    CLIENT.setStation(station)

    getattr(action, "return")()

@debug_service_call
def list_stations(service, action, *args):
    w = GUPnPAV.DIDLLiteWriter.new("en")

    ctx = service.get_context()

    station_list = []
    container_id = "stations"
    objectid = action.get_value("ObjectID", GObject.TYPE_STRING) 
    
    if objectid == container_id:
        station_list = CLIENT.stations
    else:
        stations = w.add_container()
        stations.set_title("Stations")
        stations.set_parent_id("0")
        stations.set_child_count(len(CLIENT.stations))
        stations.set_id(container_id)

    for index, station in enumerate(station_list):
        item = w.add_item()
        item.set_parent_id(container_id)
        item.set_id(str(index))
        item.set_title(station)
        item.set_upnp_class("object.item.audioItem.musicTrack")
        item.set_album("unknown")
        item.set_artist(station)
        item.set_restricted("0")

        uri = "http://%s:%s/station/%s" % (
            ctx.get_host_ip(),
            ctx.get_port(),
            station,
            )

        res = item.add_resource()
        res.set_uri(uri)
        res.set_protocol_info(proto)

    action.set_value("Result", w.get_string())
    action.set_value("NumberReturned", len(CLIENT.stations))
    action.set_value("TotalMatches", len(CLIENT.stations))
    action.set_value("UpdateID", "0")

    getattr(action, "return")()


@debug_service_call
def handle_uri_change(service, action):
    uri = action.get_value("CurrentURI", GObject.TYPE_STRING)
    print "Change URI: %s" % uri
    if not uri:
        getattr(action, "return")()
        return None
    ctx = service.get_context()
    if ctx.get_host_ip() in uri and str(ctx.get_port()) in uri:
        return set_pandora_uri(service, action, uri)
    else:
        action.return_error(0, "Invalid URI")


if __name__ == '__main__':
    rd = setup_server()
    print "UPnP MediaRenderer Service Exported"

    setup_pandora()
    print "Pandora Client Setup"

    print "Awaiting commands..."
    try:
        GObject.MainLoop().run()
    except KeyboardInterrupt:    
        print "Done"
        os._exit(0)



