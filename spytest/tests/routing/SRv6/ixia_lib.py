from ixnetwork_restpy import SessionAssistant
from ixnetwork_restpy import Files
from ixnetwork_restpy.assistants.batch.batchadd import BatchAdd
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

    def new_config(self):
        self.ixnetwork.NewConfig()

    def load_config(self, file_name):
        self.ixnetwork.NewConfig()
        file_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), file_name
        )

        self.ixnetwork.LoadConfig(Files(file_path, local_file=True))


    def get_traffic_item_statistics(self, traffic_item_name):
        '''
        ====== Traffic Item Statictics ======
        Row:0  View:Traffic Item Statistics  Sampled:2022-11-22 09:34:13.106614 UTC
            Traffic Item: Traffic-Vrf
            Tx Frames: 80000
            Rx Frames: 60510
            Frames Delta: 19490
            Loss %: 24.363
            Tx Frame Rate: 0.000
            Rx Frame Rate: 0.000
            Tx L1 Rate (bps): 0.000
            Rx L1 Rate (bps): 0.000
            Rx Bytes: 4235700
            Tx Rate (Bps): 0.000
            Rx Rate (Bps): 0.000
            Tx Rate (bps): 0.000
            Rx Rate (bps): 0.000
            Tx Rate (Kbps): 0.000
            Rx Rate (Kbps): 0.000
            Tx Rate (Mbps): 0.000
            Rx Rate (Mbps): 0.000
            Store-Forward Avg Latency (ns): 5383
            Store-Forward Min Latency (ns): 5219
            Store-Forward Max Latency (ns): 6003
            First TimeStamp: 00:00:00.363
            Last TimeStamp: 00:00:00.366
        '''
        caption = "Traffic Item Statistics"
        view = self.session_assistant.StatViewAssistant(caption)
        view.ClearRowFilters()
        rows = view.Rows
        for row in rows:
            if row['Traffic Item'] == traffic_item_name:
                return row

        return None

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
        return topology

    def add_traffic_item(self, name, traffic_type="ipv4", traffic_item_type="l2L3"):
        traffic_item = self.ixnetwork.Traffic.TrafficItem.add(
            Name=name, TrafficType=traffic_type, TrafficItemType=traffic_item_type)

        return traffic_item

    def get_all_traffic_items(self):
        return self.ixnetwork.Traffic.TrafficItem.find()

    def get_traffic_item(self, traffic_item_name):
        traffic_items = self.get_all_traffic_items()
        for traffic_item in traffic_items:
            if traffic_item.Name == traffic_item_name:
                return traffic_item

        return None

    def get_bgp_ipv4_peer(self):
        bgp_ipv4_peer = self.ixnetwork.Globals.find().Topology.find().BgpIpv4Peer.find()
        print(bgp_ipv4_peer)

    def start_stateless_traffic(self, traffic_item_name):
        traffic_item = self.get_traffic_item(traffic_item_name)
        if not traffic_item:
            return False

        self.ixnetwork.Traffic.find().Apply()
        traffic_item.StartStatelessTraffic()
        return True

    def stop_stateless_traffic(self, traffic_item_name):
        traffic_item = self.get_traffic_item(traffic_item_name)
        if not traffic_item:
            return False
        traffic_item.StopStatelessTraffic()
        return True

    def start_all_protocols(self):
        self.ixnetwork.StartAllProtocols()
        return True

    def stop_all_protocols(self):
        self.ixnetwork.StopAllProtocols()
        return True



    # CHECK FUNCTIONS
    def check_port_rx_frame(self, port_name, rx_count):
        port_stats = self.get_port_statistics(port_name)
        if port_stats is None:
            return False

        if port_stats['Valid Frames Rx.'] == rx_count:
            return True
        return False

    def check_traffic_item_rx_frame(self, traffic_item_name, rx_count):
        traffic_item_stats = self.get_traffic_item_statistics(traffic_item_name)
        if traffic_item_stats is None:
            return False
        if traffic_item_stats['Rx Frames'] == rx_count:
            return True
        return False

ixia_controller = IxiaController()
