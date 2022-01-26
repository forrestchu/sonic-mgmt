
# -*- coding:utf-8 -*-
import pytest
from spytest import st, tgapi, SpyTestDict
import time

ALICLI_VIEW = "cli"
CONFIG_VIEW = "configure terminal"
ROUTE_BGP_VIEW = "router bgp {}"
BGP_RID_CONFIG = "bgp router-id {}"


class BGP_CLI():

    def __init__(self, dut, test_data, param_data):
        self.data = test_data
        self.param_data = param_data
        self.dut = dut
        self.peers_v4 = []
        self.peers_v6 = []

    def create_bgp_route(self, as_num):
        router_bpg = ROUTE_BGP_VIEW.format(as_num)
        create_bgp_route = "{} -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, router_bpg)
        st.config(self.dut, create_bgp_route)
        self.local_as = as_num
        self.router_view = router_bpg

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
                cmd = "{} -c '{}' -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, af_cmd, act_cmd)
            else:
                cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, act_cmd)
            st.config(self.dut, cmd)
        
        remove_private_as = properties.get('remove_private_as', None)
        if remove_private_as is not None:
            t_cmd = "{} neighbor {} remove-private-AS".format('no' if remove_private_as=='false' else '', peer)
            cmd = ''
            if af is not None:
                cmd = "{} -c '{}' -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, self.router_view, af_cmd, t_cmd)
            else:
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
        output = st.show(self.dut, cmd)
        return output

    def save_config_and_reboot(self):
        cmd = "{} -c '{}' -c 'copy running-config startup-config'".format(ALICLI_VIEW, CONFIG_VIEW)
        st.config(self.dut, cmd)
        st.wait(1)
        st.log("start reboot")
        st.reboot(self.dut)
        st.wait(5)
        st.log("finisg reboot")