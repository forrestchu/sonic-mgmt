
# -*- coding:utf-8 -*-
import pytest
from spytest import st, tgapi, SpyTestDict
import time
import json
import re

ALICLI_VIEW = "cli"
CONFIG_VIEW = "configure terminal"
ROUTE_BGP_VIEW = "router bgp {}"
BGP_RID_CONFIG = "bgp router-id {}"

BGP_COMMUNITY_LIST_CONFIG = "bgp community-list {} {} {}"
BGP_ASPATH_ACCESS_LIST_CONFIG = "bgp as-path access-list {} {} {}"

class BGP_CLI():

    def __init__(self, dut, test_data, param_data):
        self.data = test_data
        self.param_data = param_data
        self.dut = dut
        self.peers_v4 = []
        self.peers_v6 = []
        self.community_list = []
        self.aspath_access_list = []

    def get_local_as(self):
        return self.local_as

    def config_bgp_community_list(self, name, type, num):
        comm_lst = BGP_COMMUNITY_LIST_CONFIG.format(name, type, num)
        command = "{} -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, comm_lst)
        st.config(self.dut, command)
        self.community_list.append(comm_lst)

    def del_config_bgp_community_list(self, name, type, num):
        comm_lst = BGP_COMMUNITY_LIST_CONFIG.format(name, type, num)
        command = "{} -c '{}' -c 'no {}'".format(ALICLI_VIEW, CONFIG_VIEW, comm_lst)
        st.config(self.dut, command)
        if (comm_lst in  self.community_list):
            self.community_list.remove(comm_lst)

    def flush_bgp_community_list(self):
        st.log("Flush bgp community-list")

        for it in self.community_list:
            cmd = "{} -c '{}' -c 'no {}'".format(ALICLI_VIEW, CONFIG_VIEW, it)
            st.config(self.dut, cmd)

    def config_bgp_aspath_access_list(self, name, type, num):
        access_lst = BGP_ASPATH_ACCESS_LIST_CONFIG.format(name, type, num)
        command = "{} -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, access_lst)
        st.config(self.dut, command)
        self.aspath_access_list.append(access_lst)

    def del_config_bgp_aspath_access_list(self, name, type, num):
        access_lst = BGP_ASPATH_ACCESS_LIST_CONFIG.format(name, type, num)
        command = "{} -c '{}' -c 'no {}'".format(ALICLI_VIEW, CONFIG_VIEW, access_lst)
        st.config(self.dut, command)
        self.aspath_access_list.remove(access_lst)

    def flush_bgp_aspath_access_lists(self):
        st.log("Flush bgp as-path access-list")
        
        for it in self.aspath_access_list:
            cmd = "{} -c '{}' -c 'no {}'".format(ALICLI_VIEW, CONFIG_VIEW, it)
            st.config(self.dut, cmd)

    def create_bgp_route(self, as_num):
        router_bgp = ROUTE_BGP_VIEW.format(as_num)
        create_bgp_route = "{} -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, router_bgp)
        st.config(self.dut, create_bgp_route)
        self.local_as = as_num
        self.router_view = router_bgp

    def config_bgp_router_id(self, rid):
        bgp_rid = BGP_RID_CONFIG.format(rid)
        config_bgp_rid = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, bgp_rid)
        st.config(self.dut, config_bgp_rid)

    def clear_bgp_router_id(self, rid):
        bgp_rid = BGP_RID_CONFIG.format(rid)
        config_bgp_rid = "{} -c '{}' -c '{}' -c 'no {}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, bgp_rid)
        st.config(self.dut, config_bgp_rid)

    def create_neighbor_v4(self, ip4_addr, remote_as):
        peer_v4_ip = ip4_addr
        peer_v4_config = "neighbor {} remote-as {}".format(peer_v4_ip, remote_as)
        peer_v4_cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, peer_v4_config)
        st.config(self.dut, peer_v4_cmd)
        self.peers_v4.append(peer_v4_config)

    def create_neighbor_v6(self, ip6_addr, remote_as):
        peer_v6_ip = ip6_addr
        peer_v6_config = "neighbor {} remote-as {}".format(peer_v6_ip, remote_as)
        peer_v6_cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, peer_v6_config)
        st.config(self.dut, peer_v6_cmd)
        self.peers_v6.append(peer_v6_config)

    def config_neighbor(self, peer, **kwargs):
        st.log("Configuring the BGP neighbor properties ..")
        properties = kwargs

        ebgp_mhop = properties.get('ebgp_multihop', None)
        if ebgp_mhop is not None:
            ebgp_mhop_cmd = "{} neighbor {} ebgp-multihop {}".format(
                'no' if ebgp_mhop == 'false' else '', peer, '' if ebgp_mhop in ['true','false'] else ebgp_mhop)
            cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, ebgp_mhop_cmd)
            st.config(self.dut, cmd)

        af = properties.get('address_family', None)
        af_pro = properties.get('af_pro', None)
        af_mod = properties.get('af_modifier', None)
        if af is not None and af_pro is not None and af_mod is not None :
            af_cmd = "{} {} {}".format('address-family', af_pro, af_mod)
            cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, af_cmd)
            st.config(self.dut, cmd)
        
        activate = properties.get('activate', None)
        if activate is not None:
            act_cmd = "{} neighbor {} activate".format('no' if activate=='false' else '', peer)
            cmd = ''
            if af is not None:
                af_cmd = "{} {} {}".format('address-family', af_pro, af_mod)
                cmd = "{} -c '{}' -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, af_cmd, act_cmd)
            else:
                cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, act_cmd)
            st.config(self.dut, cmd)
        
        ## bgp af-ip view
        remove_private_as = properties.get('remove_private_as', None)
        if remove_private_as is not None:
            t_cmd = "{} neighbor {} remove-private-AS".format('no' if remove_private_as=='false' else '', peer)
            cmd = ''
            if af is not None:
                cmd = "{} -c '{}' -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, af_cmd, t_cmd)
                st.config(self.dut, cmd)
        ## bgp af-ip view
        send_community = properties.get('send_community', None)
        if send_community is not None:
            t_cmd = "{} neighbor {} send-community".format('no' if send_community=='false' else '', peer)
            cmd = ''
            if af is not None:
                cmd = "{} -c '{}' -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, af_cmd, t_cmd)
                st.config(self.dut, cmd)
        ## bgp af-ip view
        next_hop_self = properties.get('next_hop_self', None)
        if next_hop_self is not None:
            t_cmd = "{} neighbor {} next-hop-self".format('no' if next_hop_self=='false' else '', peer)
            cmd = ''
            if af is not None:
                cmd = "{} -c '{}' -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, af_cmd, t_cmd)
                st.config(self.dut, cmd)
        
        bfd = properties.get('bfd', None)
        detect_multiplier = properties.get('detect_multiplier', None)
        tx_timer = properties.get('tx_timer', None)
        rx_timer = properties.get('rx_timer', None)
        if bfd is not None:
            if detect_multiplier is not None and tx_timer is not None and rx_timer is not None :
                t_cmd = "{} neighbor {} bfd {} {} {}".format('no' if bfd=='false' else '', peer, detect_multiplier, tx_timer, rx_timer)
            else:
                t_cmd = "{} neighbor {} bfd".format('no' if bfd=='false' else '', peer)
            cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, t_cmd)
            st.config(self.dut, cmd)

    def flush_neighbors(self):
        st.log("Flush BGP neighbors")
        
        for it in self.peers_v4:
            cmd = "{} -c '{}' -c '{}' -c 'no {}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, it)
            st.config(self.dut, cmd)
        for it in self.peers_v6:
            cmd = "{} -c '{}' -c '{}' -c 'no {}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, it)
            st.config(self.dut, cmd)

    def show_frr_bgp_running(self):
        cmd = "vtysh -c 'show running-config bgpd json'"
        #output = st.show(self.dut, cmd)
        output = st.show(self.dut, cmd, skip_tmpl=True)
        json_str = json.dumps(output).encode('utf-8')
        json_str = json_str.replace('end\\n','').replace('true','"true"').replace("\\n","").replace("\\","").strip('"')
        json_str = re.sub(r"[A-Za-z]*@\S*\$", '', json_str)
        output_json = json.loads(json_str)
        return output_json

    def save_config_and_reboot(self):
        cmd = "{} -c '{}' -c 'copy running-config startup-config'".format(ALICLI_VIEW, CONFIG_VIEW)
        st.config(self.dut, cmd)
        st.wait(1)
        st.log("start reboot")
        st.reboot(self.dut)
        st.wait(5)
        st.log("finish reboot")
