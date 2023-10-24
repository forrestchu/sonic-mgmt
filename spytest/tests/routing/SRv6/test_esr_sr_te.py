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
def duts_base_config():
    curr_path = os.getcwd()
    json_file_dut1 = curr_path+"/routing/SRv6/esr_te_dut1_config.json"
    json_file_dut2 = curr_path+"/routing/SRv6/esr_te_dut2_config.json"
    st.apply_files(dut1, [json_file_dut1])
    st.apply_files(dut2, [json_file_dut2])

    reboot.config_save_reboot(data.my_dut_list)

@pytest.mark.community
@pytest.mark.community_pass
def test_base_config_sr_te_config_check_01():

    duts_base_config()

    result = 0

    st.banner("test_base_config_sr_te_config_check_01 begin")
    st.wait(30)

    # step 1 : check ipv6 static route
    route_entries = cli_show_json(dut1, "show ipv6 route json", type="vtysh")
    # expected json
    cwd = os.getcwd()
    expected_route_path = cwd+"/routing/SRv6/locator_static_route_expected_01.json"
    expected_route_json = json.loads(open(expected_route_path).read())
    result = json_cmp(route_entries, expected_route_json)
    if result and result.has_errors():
        st.report_fail("step 1 test_base_config_sr_te_config_check_01_failed")
        for e in result.errors:
            st.log(e)

    # step 2 : check bgp state
    def check_bgp_state():
        output=st.show(dut1,'show bgp neighbors {}'.format('2000::178'), type='vtysh')
        bgp_state = output[0]['state']
        if bgp_state != 'Established':
            return False
        else:    
            return True

    if not retry_api(check_bgp_state, retry_count= 10, delay= 10):
        st.report_fail("step2 pre check bgp state failed")

    # step 3 :check te-policy
    output = st.show(dut1, "show sr-te policy detail", type='vtysh')
    if len(output) == 0:
        st.error("Output is Empty")
        return False
    for a in output:
        for key in a:
            output[output.index(a)][key]=output[output.index(a)][key].lstrip()
            output[output.index(a)][key]=output[output.index(a)][key].rstrip()
            if key in data.te_policy_key:
                if (output[output.index(a)][key] != data.dut1_policy[output.index(a)][key]):
                    print("output:{} != data:{}".format(output[output.index(a)][key],data.dut1_policy[output.index(a)][key]))
                    st.report_fail("step3 check te-policy failed")

    # step 4 : add vpn route
    vrf = 'PUBLIC-TC11'
    check_fields = ['rdroute', 'sid', 'color', 'peerv6', 'secetced', 'policy']
    bgp_as = 100
    st.config(dut1, 'vtysh -c "config t" -c "vrf {}" -c "ip route 192.100.1.0/24 blackhole"'.format(vrf))
    st.config(dut1, 'vtysh -c "config t" -c "router bgp {} vrf {}" -c "address-family ipv4 unicast" -c "redistribute static"'.format(bgp_as, vrf))

    cmd = "cli -c 'no page' -c 'show bgp ipv4 vpn 192.100.1.0/24'"
    records = st.show(dut2, cmd)
    st.log(records)

    expected_vpn = {
        'rdroute':'2:2:192.100.1.0/24',
        'sid':'fd00:201:201:fff1:11::',
        'color':'1',
        'peerv6':'',
        'policy':'2000::179|1',
        'secetced':'1 available, best #1',
    }

    if not records or len(records)==0:
        st.report_fail("step 4 test_base_config_sr_te_config_check_01_failed")

    check = False
    for re in records:
        match_cnt = 0
        st.log(re)
        for it in check_fields:
            st.log(re[it])
            if re[it] ==  expected_vpn[it]:
                match_cnt +=1

        if match_cnt == len(check_fields):
            check = True
            break

    if not check:
        st.log(records)
        st.report_fail("step 4 test_base_config_sr_te_config_check_01_failed")

    # step 5 : check vpn route
    show_cmd = "cli -c 'show ip route vrf PUBLIC-TC11 192.100.1.0/24'"
    result = st.show(dut2, show_cmd, skip_tmpl=True)
    if 'seg6 fd00:201:201:fff1:11::' not in result:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_failed, check sid")

    if 'srv6tunnel(endpoint|color):2000::179|1' not in result:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_failed, check policy")

    # step 6 : check app db
    key = 'ROUTE_TABLE:' + 'Vrf10000' + ':192.100.1.0/24'

    nexthop_val = appdb_get_onefield(dut2, key, "nexthop")
    if nexthop_val != "2000::179":
        st.report_fail("step 6 test_base_config_sr_te_config_check_01_failed, check nexthop")

    vpn_sid_val = appdb_get_onefield(dut2, key, "vpn_sid")
    if vpn_sid_val != "fd00:201:201:fff1:11::":
        st.report_fail("step 6 test_base_config_sr_te_config_check_01_failed, check vpn sid")

    seg_src_val = appdb_get_onefield(dut2, key, "seg_src")
    if seg_src_val != "2000::178":
        st.report_fail("step 6 test_base_config_sr_te_config_check_01_failed, check seg")

    policy_val = appdb_get_onefield(dut2, key, "policy")
    if policy_val != "2000::179_1":
        st.report_fail("step 6 test_base_config_sr_te_config_check_01_failed, check policy")

    # step 7 : check app db
    vrf_name = 'PUBLIC-TC11'
    st.config(dut1, 'cli -c "config t" -c "router bgp {} vrf {}" -c "address-family ipv4 unicast" -c "no route-map vpn export sr1"'.format(bgp_as, vrf_name))
    st.wait(10)
    cmd = "cli -c 'no page' -c 'show bgp ipv4 vpn 192.100.1.0/24'"
    records = st.show(dut2, cmd)
    st.log(records)

    expected_vpn = {
        'rdroute':'2:2:192.100.1.0/24',
        'sid':'fd00:201:201:fff1:11::',
        'peerv6':'',
        'secetced':'1 available, best #1',
    }

    if not records or len(records)==0:
        st.report_fail("step 7 test_base_config_sr_te_config_check_01_failed, len = 0")

    check = False
    for re in records:
        match_cnt = 0
        st.log(re)
        for it in check_fields:
            st.log(re[it])
            if re[it] ==  expected_vpn[it]:
                match_cnt +=1

        if match_cnt == len(check_fields):
            check = True
            break

    if not check:
        st.log(records)
        st.report_fail("step 7 test_base_config_sr_te_config_check_01_failed, check failed")

    # step 8 : check app db
    key = 'ROUTE_TABLE:' + 'Vrf10000' + ':192.100.1.0/24'
    policy_val = appdb_get_onefield(dut2, key, "policy")
    if policy_val != "na":
        st.report_fail("step 8 test_base_config_sr_te_config_check_01_failed, check policy")

    # step 9 : recover srv6 config
    st.config(dut1, 'cli -c "config t" -c "router bgp {} vrf {}" -c "address-family ipv4 unicast" -c "route-map vpn export sr1"'.format(bgp_as, vrf_name))
    st.wait(10)
    key = 'ROUTE_TABLE:' + 'Vrf10000' + ':192.100.1.0/24'
    policy_val = appdb_get_onefield(dut2, key, "policy")
    if policy_val != "2000::179_1":
        st.report_fail("step 9 test_base_config_sr_te_config_check_01_failed, check policy")

    st.banner("test_base_config_sr_te_config_check_01 after")