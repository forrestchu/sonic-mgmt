from ixnetwork_restpy import SessionAssistant
from ixnetwork_restpy import Files
from ixnetwork_restpy.assistants.batch.batchadd import BatchAdd
import os
import json
import time


class IxiaController():

    def __init__(self, host, port):
        self.session_assistant = SessionAssistant(
            IpAddress=host,
            RestPort=port,
            LogLevel=SessionAssistant.LOGLEVEL_INFO,
            UserName="qingyan.gw",
            Password="ne558",
            ClearConfig=True,
        )

        self.ixnetwork = self.session_assistant.Ixnetwork

    def new_config(self):
        self.ixnetwork.NewConfig()

    def load_config(self, file_name):
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

    def traffic_apply(self):
        self.ixnetwork.Traffic.find().Apply()
        return True

    def start_stateless_traffic(self, traffic_item_name):
        traffic_item = self.get_traffic_item(traffic_item_name)
        if not traffic_item:
            return False

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

    def get_topology(self, topology_name):
        res =  self.ixnetwork.Topology.find()
        for item in res:
            if item.Name == topology_name:
                return item

        return None

    def get_device_group(self, topology_name, device_group_name):
        topology = self.get_topology(topology_name)
        if not topology:
            return None

        device_groups = topology.DeviceGroup.find()
        for item in device_groups:
            if item.Name == device_group_name:
                return item
        return None

    def get_ethernet(self, topology_name, device_group_name, ethernet_name):
        device_group = self.get_device_group(topology_name, device_group_name)
        if not device_group:
            return None

        item_list = device_group.Ethernet.find()
        for item in item_list:
            if item.Name == ethernet_name:
                return item
        return None

    def get_ipv4(self, topology_name, device_group_name, ethernet_name,
                 ipv4_name):
        parent_item = self.get_ethernet(topology_name, device_group_name, ethernet_name)
        if not parent_item:
            return None

        item_list = parent_item.Ipv4.find()
        for item in item_list:
            if item.Name == ipv4_name:
                return item
        return None

    def get_ipv4_bgp_peer(self, topology_name, device_group_name, ethernet_name,
                 ipv4_name, bgp_peer_name):
        parent_item = self.get_ipv4(topology_name, device_group_name, ethernet_name,
                                     ipv4_name)
        if not parent_item:
            return None

        item_list = parent_item.BgpIpv4Peer.find()
        for item in item_list:
            if item.Name == bgp_peer_name:
                return item
        return None

    def get_network_group(self, topology_name, device_group_name, network_group_name):
        device_group = self.get_device_group(topology_name, device_group_name)
        if not device_group:
            return None

        network_groups = device_group.NetworkGroup.find()
        for item in network_groups:
            if item.Name == network_group_name:
                return item
        return None

    def get_ipv4_prefix_pool(self, topology_name, device_group_name, network_group_name, ipv4_prefix_pool_name):
        network_group = self.get_network_group(topology_name, device_group_name, network_group_name)
        if not network_group:
            return None

        ipv4_prefix_pools = network_group.Ipv4PrefixPools.find()
        for item in ipv4_prefix_pools:
            if item.Name == ipv4_prefix_pool_name:
                return item
        return None

    def get_bgp_ip_route_property(self, topology_name, device_group_name, network_group_name, ipv4_prefix_pool_name, birp_name):
        ipv4_prefix_pool = self.get_ipv4_prefix_pool(topology_name, device_group_name, network_group_name, ipv4_prefix_pool_name)
        if not ipv4_prefix_pool:
            return None

        birps = ipv4_prefix_pool.BgpIPRouteProperty.find()
        for item in birps:
            if item.Name == birp_name:
                return item
        return None


    def enable_bgp_ip_route_flapping(self, birp, enable_list, uptime=1, downtime=1, delay=1, partial_flap='true',
                                        flap_from_route_index=1, flap_to_route_index=1):
        birp.EnableFlapping.ValueList(enable_list)
        birp.Uptime.Single(uptime)
        birp.Downtime.Single(downtime)
        birp.Delay.Single(delay)
        birp.PartialFlap.Single(partial_flap)
        birp.FlapFromRouteIndex.Single(flap_from_route_index)
        birp.FlapFromRouteIndex.Single(flap_to_route_index)

    def disable_bgp_ip_route_flapping(self, birp):
        birp.EnableFlapping.Single('false')

    def enable_ipv4_bgp_peer_flapping(self, bgp_peer, uptime_s=10, downtime_s=10):
        if not bgp_peer:
            return False

        bgp_peer.Flap.Single('true')
        bgp_peer.UptimeInSec.Single(uptime_s)
        bgp_peer.DowntimeInSec.Single(downtime_s)

    def disable_ipv4_bgp_peer_flapping(self, bgp_peer):
        if not bgp_peer:
            return False

        bgp_peer.Flap.Single('false')
