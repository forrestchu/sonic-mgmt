from ixnetwork_restpy import SessionAssistant
from ixnetwork_restpy import Files
import os
import json
import time


IXIA_HOST = "10.97.244.219"
IXIA_PORT = 12020

IXIA_CONFIG_FILE = "esr_multi_vrf.ixncfg"

class IxiaController():

    def __init__(self):
        self.session_assistant = SessionAssistant(
            IpAddress=IXIA_HOST,
            RestPort=IXIA_PORT,
            LogLevel=SessionAssistant.LOGLEVEL_INFO,
            # ClearConfig=True,
        )

        self.ixnetwork = self.session_assistant.Ixnetwork

    def load_config(self, file_name):
        file_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), file_name
        )

        self.ixnetwork.LoadConfig(Files(file_path, local_file=True))


    def get_traffic_item_statistics(self):
        caption = "Traffic Item Statistics"
        view = self.session_assistant.StatViewAssistant(caption)
        print("====== Traffic Item Statictics ======")
        print(view)

    def get_port_statistics(self, port_name):
        '''
        Row:0  View:Port Statistics  Sampled:2022-11-21 08:04:35.394276 UTC
            Stat Name: 11.167.132.12/Card01/Port15
            Port Name: 1/1/15
            Line Speed: 200GE
            Link State: Link Up
            Frames Tx.: 107
            Valid Frames Rx.: 7344
            Frames Tx. Rate: 0
            Valid Frames Rx. Rate: 0
            Data Integrity Frames Rx.: 0
            Data Integrity Errors: 0
            Bytes Tx.: 10486
            Bytes Rx.: 521291
            Bits Sent: 83888
            Bits Received: 4170328
            Bytes Tx. Rate: 0
            Tx. Rate (bps): 0.000
            Tx. Rate (Kbps): 0.000
            Tx. Rate (Mbps): 0.000
            Bytes Rx. Rate: 0
            Rx. Rate (bps): 0.000
            Rx. Rate (Kbps): 0.000
            Rx. Rate (Mbps): 0.000
            Scheduled Frames Tx.: 0
            Scheduled Frames Tx. Rate: 0
            Control Frames Tx: 107
            Control Frames Rx: 7265
            Ethernet OAM Information PDUs Sent: 0
            Ethernet OAM Information PDUs Received: 0
            Ethernet OAM Event Notification PDUs Received: 0
            Ethernet OAM Loopback Control PDUs Received: 0
            Ethernet OAM Organisation PDUs Received: 0
            Ethernet OAM Variable Request PDUs Received: 0
            Ethernet OAM Variable Response Received: 0
            Ethernet OAM Unsupported PDUs Received: 0
            Rx Pause Priority Group 0 Frames: 0
            Rx Pause Priority Group 1 Frames: 0
            Rx Pause Priority Group 2 Frames: 0
            Rx Pause Priority Group 3 Frames: 0
            Rx Pause Priority Group 4 Frames: 0
            Rx Pause Priority Group 5 Frames: 0
            Rx Pause Priority Group 6 Frames: 0
            Rx Pause Priority Group 7 Frames: 0
            Misdirected Packet Count: 0
            CRC Errors: 0
            Fragments: 0
            Undersize: 0
            Oversize: 0
        '''
        caption = "Port Statistics"
        view = self.session_assistant.StatViewAssistant(caption)
        view.ClearRowFilters()
        rows = view.Rows
        for row in rows:
            if row['Port Name'] == port_name:
                return row

        return None


    def get_topology_status(self):
        topology = self.ixnetwork.GetTopologyStatus()
        print(json.dumps(topology, indent=4))


    def add_traffic_item(self, name, traffic_type="ipv4", traffic_item_type="l2L3"):
        traffic_item = self.ixnetwork.Traffic.TrafficItem.add(
            Name=name, TrafficType=traffic_type, TrafficItemType=traffic_item_type)

        traffic_config = traffic_item.ConfigElement.find()
        traffic_config.FrameRate.update(Type='percentLineRate', Rate='100')
        traffic_config.TransmissionControl.update(Type='continuous')

        return True


    def get_traffic_items(self):
        traffic_items = self.ixnetwork.Traffic.TrafficItem.find()
        return traffic_items[0]


    def get_bgp_ipv4_peer(self):
        bgp_ipv4_peer = self.ixnetwork.Globals.find().Topology.find().BgpIpv4Peer.find()
        print(bgp_ipv4_peer)

    def start_stateless_traffic(self, traffic_item):
        traffic_item.StartStatelessTraffic()

    def stop_stateless_traffic(self, traffic_item):
        traffic_item.StopStatelessTraffic()

    def start_all_protocols(self):
        self.ixnetwork.StartAllProtocols()

    def stop_all_protocols(self):
        self.ixnetwork.StopAllProtocols()



    # CHECK FUNCTIONS
    def check_port_rx_frame(self, port_name, rx_count):
        port_stats = self.get_port_statistics(port_name)
        if port_stats is None:
            return False

        if port_stats['Valid Frames Rx.'] == rx_count:
            return True
        return False


ixia_controller = IxiaController()

# ixia_controller.load_config(IXIA_CONFIG_FILE)
# ixia_controller.get_port_statistics()
# ixia_controller.get_traffic_item_statistics()
# ixia_controller.get_traffic_item()

# ixia_controller.get_topology_status()

# ixia_controller.get_bgp_ipv4_peer()

