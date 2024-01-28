import os
import pytest
import sys
import json
import netaddr
import re
import time,datetime
from collections import OrderedDict
from utilities import parallel
import apis.routing.bgp as bgpfeature

from spytest import st, tgapi, SpyTestDict
from spytest.utils import filter_and_select
import spytest.env as env

from utilities.utils import retry_api
import pandas as pd
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt

import apis.common.asic as asicapi
import apis.switching.vlan as vapi
import apis.routing.ip as ipfeature
import apis.switching.mac as macapi
import apis.system.reboot as reboot
import apis.system.port as papi
import apis.system.interface as intfapi
import apis.routing.bgp as bgp_api
import apis.routing.arp as arp_obj
import apis.routing.bfd as bfdapi
import apis.routing.ip_bgp as ip_bgp
from esr_lib import cli_show_json, json_cmp, configdb_checkarray, configdb_onefield_checkpoint,appdb_onefield_checkpoint,check_vrf_route_nums, get_random_array, check_vpn_route_nums, check_bgp_vrf_ipv4_uni_sid,appdb_get_onefield,get_vrf_realname,compare_redistribute_vrf_route, flap_lag_member,show_hw_route_count
import esr_lib as loc_lib
from esr_vars import * #all the variables used for vrf testcase
from esr_vars import data
from ixia_vars import *
from ixia_helper import *
#
#            +-------------------+                 +-------------------+
# TG1_1====  |                    |                |                    |
#            |                    |                |                    |
# TG1_2====  |                    |                |                    |=====TG2_1
#            | DUT1(192.0.0.179)  | ===========    |  DUT2(192.0.0.178) |
#            |                    |                |                    |=====TG2_2
# TG1_3====  |                    |                |                    |
#            |                    |                |                    |
# TG1_4====  |                    |                |                    |
#            +-------------------+                  +-------------------+
#                                                     ||
#                                                     ||
#                                                     ||
#                                                +-----------+
#                                                |           |
#                                                |    RJ     |
#                                                |           |
#                                                |           |
#                                                +-----------+
#                                                     ||
#                                                     ||
#                                                     ||
#                                                     TG3_1#

#data = SpyTestDict()

data.srv6 = {}

dut1 = 'MC-58'
dut2 = 'MC-59'
data.my_dut_list = [dut1, dut2]
data.load_multi_vrf_config_done = False
data.load_mirror_config_done = False
data.load_mirror_ixia_conf_done = False

@pytest.fixture(scope="module", autouse=True)
def esr_srvpn_module_hooks(request):
    #add things at the start of this module
    # add bmp
    ixia_controller_init()
    yield
    ixia_stop_all_protocols()
    ixia_controller_deinit()
    # tgapi.set_reconnect_tgen(True)
    # del bmp log

@pytest.fixture(scope="function", autouse=True)
def esr_srvpn_func_hooks(request):
    if st.get_func_name(request) in ["test_base_config_sr_te_2kl_route_learn_03",
                                     "test_srvpn_performance_2M"]:
        st.log("esr_srvpn_func_hooks enter ")
        if data.load_multi_vrf_config_done == False:
            load_json_config("multi_vrf_ecmp")
            data.load_multi_vrf_config_done = True
        # load ixia config
        if data.load_multi_vrf_ixia_conf_done == False and st.get_func_name(request) in ["test_base_config_srvpn_2kl_route_learn_02",
                                                                                            "test_base_config_srvpn_multi_vrf_03"]:
            ixia_load_config(ESR_MULTI_VRF_CONFIG)
            ixia_start_all_protocols()
            st.wait(60)
            data.load_multi_vrf_ixia_conf_done = True

    if st.get_func_name(request) in ["test_srvpn_mirror_config_05","test_srvpn_mirror_config_redistribute_vrf_06",
                                      "test_srvpn_mirror_config_bgp_flap_07", "test_srvpn_mirror_config_underlay_link_flap_08",
                                      "test_srvpn_mirror_config_underlay_ecmp_switch_09", "test_srvpn_mirror_16nexthops_10"]:
        st.log("esr_srvpn_func_hooks enter ")
        if data.load_mirror_config_done == False:
            load_json_config('mirror_config_16nht')
            data.load_mirror_config_done = True
        # load ixia config
        if st.get_func_name(request) == "test_srvpn_mirror_16nexthops_10":
            ixia_config = os.path.join(os.getcwd(), "routing/SRv6/esr_mirror_16nexthop.json")
            ixia_load_config(ixia_config)
            ixia_start_all_protocols()
            st.wait(60)
        elif data.load_mirror_ixia_conf_done == False:
            ixia_load_config(ESR_MIRROR_CONFIG)
            ixia_start_all_protocols()
            st.wait(60)
            data.load_mirror_ixia_conf_done = True

    yield
    pass

def duts_base_config():
    curr_path = os.getcwd()
    json_file_dut1 = curr_path+"/routing/SRv6/esr_te_dut1_config.json"
    json_file_dut2 = curr_path+"/routing/SRv6/esr_te_dut2_config.json"
    st.apply_files(dut1, [json_file_dut1], method="replace_configdb")
    st.apply_files(dut2, [json_file_dut2], method="replace_configdb")
    st.reboot([dut1, dut2])

@pytest.mark.community
@pytest.mark.community_pass
def test_base_config_sr_te_config_check_01():

    duts_base_config()

    result = 0

    st.banner("test_base_config_sr_te_config_check_01 begin")
    st.wait(30)

    # step 1 : check bgp state
    def check_bgp_state():
        output=st.show(dut1,'show bgp neighbors {}'.format('2000::178'), type='vtysh')
        bgp_state = output[0]['state']
        if bgp_state != 'Established':
            return False
        else:    
            return True

    if not retry_api(check_bgp_state, retry_count= 10, delay= 10):
        st.report_fail("step1 pre check bgp state failed")

    # step 3 : add vpn route
    vrf = 'PUBLIC-TC11'
    check_fields = ['rdroute', 'sid', 'color', 'peerv6', 'secetced', 'policy']
    bgp_as = 100
    st.config(dut1, 'vtysh -c "config t" -c "vrf {}" -c "ip route 192.100.1.0/24 blackhole"'.format(vrf))
    st.config(dut1, 'vtysh -c "config t" -c "router bgp {} vrf {}" -c "address-family ipv4 unicast" -c "redistribute static"'.format(bgp_as, vrf))
    st.config(dut1, 'vtysh -c "config t" -c "vrf {}" -c "ipv6 route 192:100:1::/64 blackhole"'.format(vrf))
    st.config(dut1, 'vtysh -c "config t" -c "router bgp {} vrf {}" -c "address-family ipv6 unicast" -c "redistribute static"'.format(bgp_as, vrf))

    show_cmd = "cli -c 'no page' -c 'show bgp ipv4 vpn 192.100.1.0/24'"

    result = st.show(dut2, show_cmd, skip_tmpl=True)
    if 'fd00:201:201:fff1:11::' not in result:
        st.report_fail("step 3 test_base_config_sr_te_config_check_01_failed, check sid")
    if 'srv6-tunnel:1000::179|1(endpoint|color)' not in result:
        st.report_fail("step 3 test_base_config_sr_te_config_check_01_failed, check policy")
    if 'srv6-tunnel:2000::179|1(endpoint|color)' not in result:
        st.report_fail("step 3 test_base_config_sr_te_config_check_01_failed, check policy")

    cmd = "cli -c 'no page' -c 'show bgp ipv6 vpn  192:100:1::'"

    result = st.show(dut2, show_cmd, skip_tmpl=True)
    if 'fd00:201:201:fff1:11::' not in result:
        st.report_fail("step 3 test_base_config_sr_te_config_check_01_failed, check sid")
    if 'srv6-tunnel:1000::179|1(endpoint|color)' not in result:
        st.report_fail("step 3 test_base_config_sr_te_config_check_01_failed, check policy")
    if 'srv6-tunnel:2000::179|1(endpoint|color)' not in result:
        st.report_fail("step 3 test_base_config_sr_te_config_check_01_failed, check policy")

    # step 4 : check vpn route
    show_cmd = "cli -c 'show ip route vrf PUBLIC-TC11 192.100.1.0/24'"
    result = st.show(dut2, show_cmd, skip_tmpl=True)

    if 'srv6tunnel(endpoint|color):1000::179|1' not in result:
        st.report_fail("step 4 test_base_config_sr_te_config_check_01_failed, check policy")
    if 'srv6tunnel(endpoint|color):2000::179|1' not in result:
        st.report_fail("step 4 test_base_config_sr_te_config_check_01_failed, check policy")

    show_cmd = "cli -c 'show ipv6 route vrf PUBLIC-TC11 192:100:1::/64'"
    result = st.show(dut2, show_cmd, skip_tmpl=True)

    if 'srv6tunnel(endpoint|color):1000::179|1' not in result:
        st.report_fail("step 4 test_base_config_sr_te_config_check_01_failed, check policy")
    if 'srv6tunnel(endpoint|color):2000::179|1' not in result:
        st.report_fail("step 4 test_base_config_sr_te_config_check_01_failed, check policy")

    # step 5 : check app db
    key = 'ROUTE_TABLE:' + 'Vrf10000' + ':192.100.1.0/24'
    nhg_id = appdb_get_onefield(dut2, key, "nexthop_group")
    group_table_key = 'NEXTHOP_GROUP_TABLE:' + nhg_id

    nexthop_val = appdb_get_onefield(dut2, group_table_key, "nexthop")
    if "1000::179" not in nexthop_val:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_ipv6_failed, check nexthop")
    if "2000::179" not in nexthop_val:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_ipv6_failed, check nexthop")

    segment_val = appdb_get_onefield(dut2, group_table_key, "segment")
    if "a" not in segment_val:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_ipv6_failed, check segment")
    if "b" not in segment_val:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_ipv6_failed, check segment")

    pic_id = appdb_get_onefield(dut2, key, "pic_context_id")
    pic_table_key = 'PIC_CONTEXT_TABLE:' + pic_id

    vpn_sid_val = appdb_get_onefield(dut2, pic_table_key, "vpn_sid")
    if "fd00:201:201:fff1:11::" not in vpn_sid_val:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_failed, check vpn sid")

    key = 'ROUTE_TABLE:' + 'Vrf10000' + ':192:100:1::/64'
    nhg_id = appdb_get_onefield(dut2, key, "nexthop_group")
    group_table_key = 'NEXTHOP_GROUP_TABLE:' + nhg_id

    nexthop_val = appdb_get_onefield(dut2, group_table_key, "nexthop")
    if "1000::179" not in nexthop_val:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_ipv6_failed, check nexthop")
    if "2000::179" not in nexthop_val:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_ipv6_failed, check nexthop")

    segment_val = appdb_get_onefield(dut2, group_table_key, "segment")
    if "a" not in segment_val:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_ipv6_failed, check segment")
    if "b" not in segment_val:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_ipv6_failed, check segment")

    pic_id = appdb_get_onefield(dut2, key, "pic_context_id")
    pic_table_key = 'PIC_CONTEXT_TABLE:' + pic_id

    vpn_sid_val = appdb_get_onefield(dut2, pic_table_key, "vpn_sid")
    if "fd00:201:201:fff1:11::" not in vpn_sid_val:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_failed, check vpn sid")

    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_base_config_sr_te_config_check_02():

    st.banner("test_base_config_sr_te_config_check_02 begin")
    #shutdown interface, test one policy
    st.config(dut1, 'cli -c "configure terminal" -c "interface Ethernet4" -c "shutdown"')
    st.wait(30)

    # step 2 : check bgp state
    def check_bgp_state():
        output=st.show(dut1,'show bgp neighbors {}'.format('2000::178'), type='vtysh')
        bgp_state = output[0]['state']
        if bgp_state != 'Active':
            return False
        else:    
            return True

    if not retry_api(check_bgp_state, retry_count= 5, delay= 10):
        st.report_fail("step2 pre check bgp state failed")

   # step 3 : check vpn route
    show_cmd = "cli -c 'show ip route vrf PUBLIC-TC11 192.100.1.0/24'"
    result = st.show(dut2, show_cmd, skip_tmpl=True)

    if 'srv6tunnel(endpoint|color):1000::179|1' not in result:
        st.report_fail("step 3 test_base_config_sr_te_config_check_02_failed, check policy")
    if 'srv6tunnel(endpoint|color):2000::179|1' in result:
        st.report_fail("step 3 test_base_config_sr_te_config_check_02_failed, check policy")

    show_cmd = "cli -c 'show ipv6 route vrf PUBLIC-TC11 192:100:1::/64'"
    result = st.show(dut2, show_cmd, skip_tmpl=True)

    if 'srv6tunnel(endpoint|color):1000::179|1' not in result:
        st.report_fail("step 3 test_base_config_sr_te_config_check_02_failed, check policy")
    if 'srv6tunnel(endpoint|color):2000::179|1' in result:
        st.report_fail("step 3 test_base_config_sr_te_config_check_02_failed, check policy")

    # step 4 : check app db
    key = 'ROUTE_TABLE:' + 'Vrf10000' + ':192.100.1.0/24'
    nhg_id = appdb_get_onefield(dut2, key, "nexthop_group")
    group_table_key = 'NEXTHOP_GROUP_TABLE:' + nhg_id

    nexthop_val = appdb_get_onefield(dut2, group_table_key, "nexthop")
    if "1000::179" not in nexthop_val:
        st.report_fail("step 4 test_base_config_sr_te_config_check_02_ipv6_failed, check nexthop")
    if "2000::179" in nexthop_val:
        st.report_fail("step 4 test_base_config_sr_te_config_check_02_ipv6_failed, check nexthop")

    segment_val = appdb_get_onefield(dut2, group_table_key, "segment")
    if "a" not in segment_val:
        st.report_fail("step 4 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")
    if "b" in segment_val:
        st.report_fail("step 4 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")

    pic_id = appdb_get_onefield(dut2, key, "pic_context_id")
    pic_table_key = 'PIC_CONTEXT_TABLE:' + pic_id

    vpn_sid_val = appdb_get_onefield(dut2, pic_table_key, "vpn_sid")
    if "fd00:201:201:fff1:11::" not in vpn_sid_val:
        st.report_fail("step 4 test_base_config_sr_te_config_check_02_failed, check vpn sid")

    key = 'ROUTE_TABLE:' + 'Vrf10000' + ':192:100:1::/64'
    nhg_id = appdb_get_onefield(dut2, key, "nexthop_group")
    group_table_key = 'NEXTHOP_GROUP_TABLE:' + nhg_id

    nexthop_val = appdb_get_onefield(dut2, group_table_key, "nexthop")
    if "1000::179" not in nexthop_val:
        st.report_fail("step 4 test_base_config_sr_te_config_check_02_ipv6_failed, check nexthop")
    if "2000::179" in nexthop_val:
        st.report_fail("step 4 test_base_config_sr_te_config_check_02_ipv6_failed, check nexthop")

    segment_val = appdb_get_onefield(dut2, group_table_key, "segment")
    if "a" not in segment_val:
        st.report_fail("step 4 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")
    if "b" in segment_val:
        st.report_fail("step 4 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")

    pic_id = appdb_get_onefield(dut2, key, "pic_context_id")
    pic_table_key = 'PIC_CONTEXT_TABLE:' + pic_id

    vpn_sid_val = appdb_get_onefield(dut2, pic_table_key, "vpn_sid")
    if "fd00:201:201:fff1:11::" not in vpn_sid_val:
        st.report_fail("step 4 test_base_config_sr_te_config_check_02_failed, check vpn sid")

    # setp 5: add cpath
    st.config(dut1, 'vtysh -c "config t" -c "segment-routing" -c "traffic-eng" -c "policy color 1 endpoint 1000::179" -c "candidate-path preference 1 name b explicit segment-list b weight 1"')

    group_table_key = 'NEXTHOP_GROUP_TABLE:' + nhg_id
    nexthop_val = appdb_get_onefield(dut2, group_table_key, "nexthop")
    if "1000::179" not in nexthop_val:
        st.report_fail("step 5 test_base_config_sr_te_config_check_02_ipv6_failed, check nexthop")

    segment_val = appdb_get_onefield(dut2, group_table_key, "segment")
    if "a" not in segment_val:
        st.report_fail("step 5 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")
    if "b" not in segment_val:
        st.report_fail("step 5 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")

    # setp 6: del cpath
    st.config(dut1, 'vtysh -c "config t" -c "segment-routing" -c "traffic-eng" -c "policy color 1 endpoint 1000::179" -c "no candidate-path preference 1 name b explicit segment-list b"')

    group_table_key = 'NEXTHOP_GROUP_TABLE:' + nhg_id
    nexthop_val = appdb_get_onefield(dut2, group_table_key, "nexthop")
    if "1000::179" not in nexthop_val:
        st.report_fail("step 6 test_base_config_sr_te_config_check_02_ipv6_failed, check nexthop")

    segment_val = appdb_get_onefield(dut2, group_table_key, "segment")
    if "a" not in segment_val:
        st.report_fail("step 6 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")
    if "b" in segment_val:
        st.report_fail("step 6 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")

    # setp 7: add high preference cpath
    st.config(dut1, 'vtysh -c "config t" -c "segment-routing" -c "traffic-eng" -c "policy color 1 endpoint 1000::179" -c "candidate-path preference 2 name b explicit segment-list b weight 2"')

    group_table_key = 'NEXTHOP_GROUP_TABLE:' + nhg_id
    nexthop_val = appdb_get_onefield(dut2, group_table_key, "nexthop")
    if "1000::179" not in nexthop_val:
        st.report_fail("step 7 test_base_config_sr_te_config_check_02_ipv6_failed, check nexthop")

    segment_val = appdb_get_onefield(dut2, group_table_key, "segment")
    if "a" in segment_val:
        st.report_fail("step 7 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")
    if "b" not in segment_val:
        st.report_fail("step 7 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")

    # setp 8: add high preference cpath
    st.config(dut1, 'vtysh -c "config t" -c "segment-routing" -c "traffic-eng" -c "policy color 1 endpoint 1000::179" -c "no candidate-path preference 2 name b explicit segment-list b"')

    group_table_key = 'NEXTHOP_GROUP_TABLE:' + nhg_id
    nexthop_val = appdb_get_onefield(dut2, group_table_key, "nexthop")
    if "1000::179" not in nexthop_val:
        st.report_fail("step 8 test_base_config_sr_te_config_check_02_ipv6_failed, check nexthop")

    segment_val = appdb_get_onefield(dut2, group_table_key, "segment")
    if "a" not in segment_val:
        st.report_fail("step 8 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")
    if "b" in segment_val:
        st.report_fail("step 8 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")

    pic_table_key = 'PIC_CONTEXT_TABLE:' + pic_id

    vpn_sid_val = appdb_get_onefield(dut2, pic_table_key, "vpn_sid")
    if "fd00:201:201:fff1:11::" not in vpn_sid_val:
        st.report_fail("step 4 test_base_config_sr_te_config_check_02_failed, check vpn sid")

    #no shutdown interface, test one policy
    st.config(dut1, 'cli -c "configure terminal" -c "interface Ethernet4" -c "shutdown"')
    st.wait(30)

    # step 9 : check bgp state
    def check_bgp_state():
        output=st.show(dut1,'show bgp neighbors {}'.format('2000::178'), type='vtysh')
        bgp_state = output[0]['state']
        if bgp_state != 'Established':
            return False
        else:    
            return True

    if not retry_api(check_bgp_state, retry_count= 5, delay= 10):
        st.report_fail("step9 pre check bgp state failed")

    # step 10 :check db
    key = 'ROUTE_TABLE:' + 'Vrf10000' + ':192.100.1.0/24'
    nhg_id = appdb_get_onefield(dut2, key, "nexthop_group")
    group_table_key = 'NEXTHOP_GROUP_TABLE:' + nhg_id

    nexthop_val = appdb_get_onefield(dut2, group_table_key, "nexthop")
    if "1000::179" not in nexthop_val:
        st.report_fail("step 10 test_base_config_sr_te_config_check_02_ipv6_failed, check nexthop")
    if "2000::179" not in nexthop_val:
        st.report_fail("step 10 test_base_config_sr_te_config_check_02_ipv6_failed, check nexthop")

    segment_val = appdb_get_onefield(dut2, group_table_key, "segment")
    if "a" not in segment_val:
        st.report_fail("step 10 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")
    if "b" not in segment_val:
        st.report_fail("step 10 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")

    pic_id = appdb_get_onefield(dut2, key, "pic_context_id")
    pic_table_key = 'PIC_CONTEXT_TABLE:' + pic_id

    vpn_sid_val = appdb_get_onefield(dut2, pic_table_key, "vpn_sid")
    if "fd00:201:201:fff1:11::" not in vpn_sid_val:
        st.report_fail("step 10 test_base_config_sr_te_config_check_02_failed, check vpn sid")

    # step 11 :two policy add cpath
    st.config(dut1, 'vtysh -c "config t" -c "segment-routing" -c "traffic-eng" -c "policy color 1 endpoint 1000::179" -c "candidate-path preference 1 name c explicit segment-list c weight 1"')
    group_table_key = 'NEXTHOP_GROUP_TABLE:' + nhg_id

    nexthop_val = appdb_get_onefield(dut2, group_table_key, "nexthop")
    if "1000::179" not in nexthop_val:
        st.report_fail("step 11 test_base_config_sr_te_config_check_02_ipv6_failed, check nexthop")
    if "2000::179" not in nexthop_val:
        st.report_fail("step 11 test_base_config_sr_te_config_check_02_ipv6_failed, check nexthop")

    segment_val = appdb_get_onefield(dut2, group_table_key, "segment")
    if "a" not in segment_val:
        st.report_fail("step 11 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")
    if "b" not in segment_val:
        st.report_fail("step 11 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")
    if "c" not in segment_val:
        st.report_fail("step 11 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")

    # step 12 :two policy del cpath
    st.config(dut1, 'vtysh -c "config t" -c "segment-routing" -c "traffic-eng" -c "policy color 1 endpoint 1000::179" -c "no candidate-path preference 1 name a explicit segment-list a"')
    group_table_key = 'NEXTHOP_GROUP_TABLE:' + nhg_id

    nexthop_val = appdb_get_onefield(dut2, group_table_key, "nexthop")
    if "1000::179" not in nexthop_val:
        st.report_fail("step 12 test_base_config_sr_te_config_check_02_ipv6_failed, check nexthop")
    if "2000::179" not in nexthop_val:
        st.report_fail("step 12 test_base_config_sr_te_config_check_02_ipv6_failed, check nexthop")

    segment_val = appdb_get_onefield(dut2, group_table_key, "segment")
    if "a" in segment_val:
        st.report_fail("step 12 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")
    if "b" not in segment_val:
        st.report_fail("step 12 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")
    if "c" not in segment_val:
        st.report_fail("step 12 test_base_config_sr_te_config_check_02_ipv6_failed, check segment")

    st.report_pass("test_case_passed")

def load_json_config(filesuffix='te_multi_vrf_full'):
    curr_path = os.getcwd()

    json_file_dut1_multi_vrf = curr_path+"/routing/SRv6/dut1_"+filesuffix+".json"
    st.apply_files(dut1, [json_file_dut1_multi_vrf], method="replace_configdb")

    json_file_dut2_multi_vrf = curr_path+"/routing/SRv6/dut2_"+filesuffix+".json"
    st.apply_files(dut2, [json_file_dut2_multi_vrf], method="replace_configdb")

    st.wait(10)

    st.reboot([dut1, dut2])

    st.banner("%s json config loaded completed" % (filesuffix))

def get_kernel_ip_route(dut, number):
    command = "ip route show vrf Vrf{}| wc -l".format(number)
    output = st.show(dut, command, skip_tmpl=True, skip_error_check=True)
    x = re.findall(r"\d+", output)
    if x:
        return int(x[0])
    else:
        return 0

def get_kernel_ipv6_route(dut, number):
    command = "ip -6 route show vrf Vrf{}| wc -l".format(number)
    output = st.show(dut, command, skip_tmpl=True, skip_error_check=True)
    x = re.findall(r"\d+", output)
    if x:
        return int(x[0])
    else:
        return 0

@pytest.mark.community
@pytest.mark.community_pass
def test_base_config_sr_te_2kl_route_learn_03():
    st.banner("test_base_config_sr_te_2kl_route_learn_03 begin")

    # load full config
    if data.load_multi_vrf_config_done == False:
        load_json_config()
        data.load_multi_vrf_config_done = True

    # load ixia config
    ixia_load_config(ESR_MULTI_VRF_CONFIG)
    ixia_start_all_protocols()

    # check redis db , check route
    finish_v4_egress = False
    finish_v6_egress = True
    finish_v4_ingress = False
    finish_v6_ingress = True

    str_start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    end_timev4_ingress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    end_timev6_ingress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    end_timev4_egress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    end_timev6_egress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    str_end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    def get_time_diff(start, end):
        start_sec = time.mktime(time.strptime(start, "%Y-%m-%d %X"))
        end_sec = time.mktime(time.strptime(end, "%Y-%m-%d %X"))
        return end_sec-start_sec

    # 5 min check route count
    while get_time_diff(str_start_time, str_end_time) < (5*60):
        # egress
        def_v4_route_count_d2 = asicapi.get_ipv4_route_count(dut2)
        if int(def_v4_route_count_d2) >= 500000 and not finish_v4_egress:
            end_timev4_egress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            finish_v4_egress = True
            st.log("dut2 v4 learn 50w time cost "+str(get_time_diff(str_start_time, end_timev4_egress)))

        def_v4_route_count_d1 = asicapi.get_ipv4_route_count(dut1)
        if int(def_v4_route_count_d1) >= 500000 and not finish_v4_ingress:
            end_timev4_ingress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            finish_v4_ingress = True
            st.log("dut1 v4 learn 50w time cost "+str(get_time_diff(str_start_time, end_timev4_ingress)))

        if finish_v4_egress and finish_v6_egress and finish_v4_ingress and finish_v6_ingress:
            break

        st.wait(1)
        str_end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


    if not finish_v4_egress:
        st.report_fail("dut2 v4 learn 50w route slower than 5 min")

    if not finish_v6_egress:
        st.report_fail("dut2 v6 learn 5w route slower than 5 min")

    if not finish_v4_ingress:
        st.report_fail("dut1 v6 learn 5w route slower than 5 min")

    if not finish_v6_ingress:
        st.report_fail("dut1 v6 learn 5w route slower than 5 min")

    st.log("dut2 v4 learn 50w time cost "+str(get_time_diff(str_start_time, end_timev4_egress)))
    st.log("dut2 v6 learn 5w time cost "+str(get_time_diff(str_start_time, end_timev6_egress)))
    st.log("dut1 v4 learn 50w time cost "+str(get_time_diff(str_start_time, end_timev4_ingress)))
    st.log("dut1 v6 learn 5w time cost "+str(get_time_diff(str_start_time, end_timev6_ingress)))
    
    for num in range(1, 100):
        vrf_name = data.vrf_list[num]
        prefix = data.vrf_prefix[vrf_name]
        key = "ROUTE_TABLE:Vrf{}:{}".format(10000+num, prefix)
        nhg_id = appdb_get_onefield(dut2, key, "nexthop_group")
        group_table_key = 'NEXTHOP_GROUP_TABLE:' + nhg_id

        segment_val = appdb_get_onefield(dut2, group_table_key, "segment")
        if segment_val == "na":
            cmd ='cli -c "no page" -c "show ip route vrf {} {}"'.format(vrf_name, prefix)
            st.show(dut2, cmd, skip_tmpl=True, skip_error_check=True)
            st.report_fail("test_base_config_sr_te_2kl_route_learn_02_failed, vrf {} prefix {}".format(vrf_name, prefix))

    st.report_pass("test_case_passed")


def duts_load_config(dut1_config, dut2_config):
    dut_list = st.get_dut_names()
    st.log("===== GET DUT LIST {}".format(dut_list))

    dut1_config_file_path = os.path.join(os.getcwd(), "routing/SRv6/{}".format(dut1_config))
    dut2_config_file_path = os.path.join(os.getcwd(), "routing/SRv6/{}".format(dut2_config))
    st.apply_files(dut_list[0], [dut1_config_file_path], method="replace_configdb")
    st.apply_files(dut_list[1], [dut2_config_file_path], method="replace_configdb")

    st.wait(10)

    st.reboot([dut1, dut2])

    st.banner("config loaded %s and %s completed" % (dut1_config, dut2_config))


def duts_get_memory(dut, progress):
    cmd = "cat /proc/`pidof {}`/status | grep VmRSS".format(progress)
    memory = st.show(dut, cmd, skip_tmpl=True, skip_error_check=True).split("\n")
    return memory

def plot_perf(csv_file, jpg_file):

    data_df = pd.read_csv(csv_file)

    for col in data_df.columns:
        if col == u"~ElapsedTime":
            x = data_df[col]
        elif col == u"21.135.163.53/Card01/Port33:Valid Frames Rx. Rate":
            y = data_df[col]

    plt.clf()
    plt.style.use('seaborn-colorblind')
    plt.xlabel("timestamp", fontsize=11)
    plt.ylabel("Frames Rx. Rate", fontsize=11)
    plt.ylim(ymin=0, ymax=max(y)+100000)
    plt.plot(x, y, color='blue')
    plt.savefig(jpg_file, dpi=1200)
    #plt.show()

def get_route_load_time(cursor, csv_file):
    data_df = pd.read_csv(csv_file)

    for col in data_df.columns:
        if col == u"~ElapsedTime":
            x = data_df[col]
        elif col == u"21.135.163.53/Card01/Port33:Valid Frames Rx. Rate":
            y = data_df[col]

    start_time = cursor
    stop_time = cursor
    max_rx_rate = max(y) + 1
    for i in range(0, len(x) - 1):
        if y[i] != 0 and start_time == cursor:
            start_time = x[i]
        if y[i] * 100 / max_rx_rate > 98 and stop_time == cursor:
            stop_time = x[i]
            break
    st.log("get_route_load_time start = {}, stop = {}, i = {}".format(start_time, stop_time, i))
    return stop_time - start_time, i


def get_route_convergence_time(cursor, csv_file):
    data_df = pd.read_csv(csv_file)

    for col in data_df.columns:
        if col == u"~ElapsedTime":
            x = data_df[col]
        elif col == u"21.135.163.53/Card01/Port33:Valid Frames Rx. Rate":
            y = data_df[col]

    start_time = cursor
    stop_time = cursor
    max_rx_rate = max(y) + 1
    for i in range(cursor - 1, len(x) + 1):
        if y[i] * 100 / max_rx_rate < 98 and start_time == cursor:
            start_time = x[i]

        if y[i] == 0 and stop_time == cursor:
            stop_time = x[i]
            break
    st.log("get_route_convergence_time start = {}, stop = {}, i = {}".format(start_time, stop_time, i))
    if (stop_time == start_time):
        return 1;
    return stop_time - start_time


def get_log_dir_path():
    user_root = env.get("SPYTEST_USER_ROOT", os.getcwd())
    logs_path = env.get("SPYTEST_LOGS_PATH", user_root)
    return logs_path

@pytest.mark.community
@pytest.mark.community_pass
def test_sr_te_performance_2M():
    st.banner("test_sr_te_performance_2M begin")
    dut_list = st.get_dut_names()
    dut1 = dut_list[0]
    dut2 = dut_list[1]

    route_count = 2000000

    # 1. load DUT config
    dut1_config = "performance/dut1_te_one_vrf.json"
    dut2_config = "performance/dut2_te_one_vrf.json"
    duts_load_config(dut1_config, dut2_config)

    # 2. load TG config
    ixia_config = os.path.join(os.getcwd(), "routing/SRv6/performance/ixia_one_vrf_2M.json")
    ixia_load_config(ixia_config)

    # 3. start traffic
    ixia_start_all_traffic()
    ixia_start_logging_port_view()

    # 4. start protocol
    ixia_start_all_protocols()
    st.wait(400)
    if not retry_api(check_vpn_route_nums, dut=dut2, expected_num=route_count, compare=0, retry_count=3, delay=400):
        st.report_fail("check vpn route_nums failed")

    # 5. get memory info for DUT1 bgpd,zebra,orchagent,syncd
    st.log("====== DUT1 ======")
    memory = duts_get_memory(dut1, 'bgpd')
    st.log("====== Memory bgpd ======")
    st.log(memory)
    memory = duts_get_memory(dut1, 'zebra')
    st.log("====== Memory zebra ======")
    st.log(memory)
    memory = duts_get_memory(dut1, 'orchagent')
    st.log("====== Memory orchagent ======")
    st.log(memory)
    memory = duts_get_memory(dut1, 'syncd')
    st.log("====== Memory syncd ======")
    st.log(memory)

    # 6. get memory info for DUT2 bgpd,zebra,orchagent,syncd
    st.log("====== DUT2 ======")
    memory = duts_get_memory(dut2, 'bgpd')
    st.log("====== Memory bgpd ======")
    st.log(memory)
    memory = duts_get_memory(dut2, 'zebra')
    st.log("====== Memory zebra ======")
    st.log(memory)
    memory = duts_get_memory(dut2, 'orchagent')
    st.log("====== Memory orchagent ======")
    st.log(memory)
    memory = duts_get_memory(dut2, 'syncd')
    st.log("====== Memory syncd ======")
    st.log(memory)

    # 7. stop protocol
    ixia_stop_all_protocols()
    st.wait(400)
    # 8. get perform data
    ixia_stop_logging_port_view()
    local_file = "port_statictics_{}.csv".format(route_count)
    local_file = os.path.join(os.getcwd(), "../", get_log_dir_path(), local_file)

    perf_jpg_file = 'eSR_Performance_{}.jpg'.format(route_count)
    perf_jpg_file = os.path.join(os.getcwd(), "../", get_log_dir_path(), perf_jpg_file)

    st.log(local_file)
    st.log(perf_jpg_file)

    ixia_get_port_view_data(local_file)
    plot_perf(local_file, perf_jpg_file)

    load_t, cursor = get_route_load_time(0, local_file)
    covergen_t = get_route_convergence_time(cursor, local_file)

    st.log("======== {} Route Load Time {} =======".format(route_count, load_t))
    st.log("Load Time: {} s, Rate: {} rps".format(load_t, route_count / load_t))

    st.log("======== {} Route Convergence Time {} =======".format(route_count, covergen_t))
    st.log("Convergence Time: {} s, Rate: {} rps".format(covergen_t, route_count / covergen_t))

    # 9. stop traffic
    ixia_stop_all_traffic()
    st.report_pass("msg", "LoadPerf: {} rps, CovergePerf: {} rps".format(route_count / load_t, route_count / covergen_t))
    