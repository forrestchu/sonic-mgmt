import os
import pytest
import sys
import json
import netaddr
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
from esr_lib import cli_show_json, json_cmp, configdb_checkpoint, configdb_checkarray, appdb_checkpoint, configdb_onefield_checkpoint,appdb_onefield_checkpoint,check_vrf_route_nums, get_random_array, check_vpn_route_nums, check_bgp_vrf_ipv4_uni_sid,appdb_get_onefield,get_vrf_realname,compare_redistribute_vrf_route, flap_lag_member,show_hw_route_count
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

def add_bmp_config_background(dut):
    st.log("config global bmp")
    st.config(dut, "cli -c 'configure terminal' -c 'bmp' -c 'bmp target bmp01' -c 'bmp connect 21.135.167.180 port 5555 min-retry 500 max-retry 2000'")
    st.config(dut, "cli -c 'configure terminal' -c 'bmp' -c 'bmp target bmp01' -c 'bmp monitor ipv4 unicast adj-in pre-policy'")
    st.config(dut, "cli -c 'configure terminal' -c 'bmp' -c 'bmp target bmp01' -c 'bmp monitor ipv6 unicast adj-in pre-policy'")
    st.config(dut, "cli -c 'configure terminal' -c 'bmp' -c 'bmp target bmp01' -c 'bmp monitor ipv4 unicast adj-in post-policy '")
    st.config(dut, "cli -c 'configure terminal' -c 'bmp' -c 'bmp target bmp01' -c 'bmp monitor ipv6 unicast adj-in post-policy '")

def check_bcmcmd_route_count(dut, loopCnt, ipType, defcount, expcount):
    flag = 0
    iter = 1
    while iter <= loopCnt:
        if ipType == "ipv4":
            curr_count = asicapi.get_ipv4_route_count(dut)
        elif ipType == "ipv6":
            curr_count = asicapi.get_ipv6_route_count(dut)

        route_cnt = int(curr_count) - int(defcount)

        st.log("Learnt route count after iteration {} : {}".format(iter,route_cnt))

        if int(route_cnt) == int(expcount):
            flag = 1
            break
        iter = iter+1
        time.sleep(1)

    if flag:
        return True
    else:
        return False

def verify_bgp_route_count(dut,family='ipv4',shell="sonic",**kwargs):
    if family.lower() == 'ipv4':
        output = bgpfeature.show_bgp_ipv4_summary(dut)
    if family.lower() == 'ipv6':
        output = bgpfeature.show_bgp_ipv6_summary(dut)
    st.debug(output)
    if 'neighbor' in kwargs and 'state' in kwargs:
        match = {'neighbor': kwargs['neighbor']}
        try:
            entries = filter_and_select(output, None, match)[0]
        except Exception:
            st.log("ERROR 1")
        if entries['state']:
            if kwargs['state'] == 'Established':
                if entries['state'].isdigit():
                    return entries['state']
                else:
                    return 0
            else:
                return 0
        else:
            return 0
    return 0

def verify_ping(src_obj,port_handle,dev_handle,dst_ip,ping_count=5,exp_count=5):
    ping_count,exp_count = int(ping_count),int(exp_count)
    if src_obj.tg_type == 'stc':
        result = src_obj.tg_emulation_ping(handle=dev_handle,host=dst_ip,count=ping_count)
        print("ping output: %s" % (result))
        return True if int(result['tx']) == ping_count and  int(result['rx']) == exp_count else False
    return True

def check_end_to_end_intf_traffic_counters(dut, port):

    DUT_tx_value = papi.get_interface_counters(dut, port, "tx_ok")
    for i in DUT_tx_value:
        p1_tx = i['tx_ok']
        p1_tx = p1_tx.replace(",","")
    st.log("tx_ok xounter value on DUT Inress port : {}".format(p1_tx))
    if (abs(int(float(p1_tx))) > 0):
        output = papi.get_interface_counters_all(dut)
        entry1 = filter_and_select(output, ["tx_bps"], {'iface': port})
        for i in entry1:
            p1_txmt = i['tx_bps']
            p1_txmt = p1_txmt.replace(" Gb/s","")
            p1_txmt = p1_txmt.replace(" Mb/s","")
            p1_txmt = p1_txmt.replace(" Kb/s","")
            p1_txmt = p1_txmt.replace(" b/s","")
        if (abs(int(float(p1_txmt))) == 0):
            st.show(dut, "show arp")
            st.error("End to End traffic is Zero")
            return False
        else:
            st.log("End to End traffic is fine")
            return True
    else:
        st.error("End to End traffic is not fine")
        return False

def intf_traffic_stats(entry_tx):
    for i in entry_tx:
        p_txmt = i['tx_bps']
        p_txmt = p_txmt.replace(" Gb/s","")
        p_txmt = p_txmt.replace(" Mb/s","")
        p_txmt = p_txmt.replace(" Kb/s","")
        p_txmt = p_txmt.replace(" b/s","")

    p_tx = abs(int(float(p_txmt)))
    return p_tx

def check_dut_intf_tx_traffic_counters(dut, portlist, expect_val):
    papi.clear_interface_counters(dut)
    st.wait(5)
    output = papi.get_interface_counters_all(dut)
    retry = 0
    while len(output) == 0 and retry < 10:
        output = papi.get_interface_counters_all(dut)
        retry += 1
        st.wait(2)
    if retry == 10:
        st.error("Error: Dut port stats")
        return False

    tx_bps_list = []
    for port in portlist:
        tx_bps = intf_traffic_stats(filter_and_select(output, ["tx_bps"], {'iface': port}))
        tx_bps_list.append(tx_bps)

    st.log("Inter Dut port stats  tx_ok xounter value on DUT Egress ports : {} expect: {}".format(tx_bps_list,expect_val))

    for tx_bps in tx_bps_list:
        if tx_bps == 0:
            st.error("Error:Inter Dut port stats tx_ok xounter value on DUT Egress port: {}".format(tx_bps))
            return False
        else:
            deviation = abs(expect_val - tx_bps)
            percent = (float(deviation)/expect_val)*100
            if percent > 10:
                st.log("Inter Dut port stats tx_ok xounter value on DUT Egress ports {}".format(tx_bps))
                return False

    st.log("All ECMP paths are utilized")
    return True

def get_handles():
    tg1, tg_ph_1 = tgapi.get_handle_byname("T1D1P1") # ixia - 179 Eth109
    tg2, tg_ph_2 = tgapi.get_handle_byname("T1D1P2") # ixia - 179 Eth110
    tg3, tg_ph_3 = tgapi.get_handle_byname("T1D1P3") # ixia - 179 Eth111
    tg4, tg_ph_4 = tgapi.get_handle_byname("T1D1P4") # ixia - 179 Eth112
    tg5, tg_ph_5 = tgapi.get_handle_byname("T1D2P1") # ixia - 178 Eth109
    tg6, tg_ph_6 = tgapi.get_handle_byname("T1D2P2") # ixia - 178 Eth110
    tg7, tg_ph_7 = tgapi.get_handle_byname("T1D1P5") # ixia - 179 Eth50
    tg8, tg_ph_8 = tgapi.get_handle_byname("T1D1P6") # ixia - 179 Eth51
    tg_list = [tg1, tg2, tg3, tg4, tg5, tg6, tg7, tg8]
    tg_ph_list = [tg_ph_1, tg_ph_2, tg_ph_3, tg_ph_4, tg_ph_5, tg_ph_6, tg_ph_7, tg_ph_8]
    return (tg_list, tg_ph_list)

def get_dut_ip():
    data.my_dut_list = st.get_dut_names()

    cmd = "cli -c 'no page' -c 'show ip interface brief'"
    output1 = st.show(dut1, cmd)
    output2 = st.show(dut2, cmd)

    data.dut1_all_ip_addr = copy.deepcopy(output1)
    data.dut2_all_ip_addr = copy.deepcopy(output2)

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
    if st.get_func_name(request) in  ["test_srvpn_mirror_config_05","test_srvpn_mirror_config_redistribute_vrf_06",
                                      "test_srvpn_mirror_config_bgp_flap_07", "test_srvpn_mirror_config_underlay_link_flap_08",
                                      "test_srvpn_mirror_config_underlay_ecmp_switch_09"]:
        st.log("esr_srvpn_func_hooks enter ")
        if data.load_mirror_config_done == False:
            load_mirro_config()
            data.load_mirror_config_done = True
        # load ixia config
        if data.load_mirror_ixia_conf_done == False:
            ixia_load_config(ESR_MIRROR_CONFIG)
            ixia_start_all_protocols()
            st.wait(60)
            data.load_mirror_ixia_conf_done = True
    yield
    pass


def duts_base_config():
    curr_path = os.getcwd()
    json_file_dut1 = curr_path+"/routing/SRv6/esr_dut1_config.json"
    json_file_dut2 = curr_path+"/routing/SRv6/esr_dut2_config.json"
    st.apply_files(dut1, [json_file_dut1])
    st.apply_files(dut2, [json_file_dut2])

    reboot.config_save_reboot(data.my_dut_list)


def l3_base_unconfig():

    st.log("remove l3 base config.")
    ipfeature.clear_ip_configuration(st.get_dut_names())
    vapi.clear_vlan_configuration(st.get_dut_names())
    #command = "show arp"
    #st.show(dut1, command)

@pytest.mark.community
@pytest.mark.community_pass
def test_base_config_srvpn_locator_01():

    duts_base_config()

    result = 0

    st.banner("test_base_config_srvpn_locator_01 begin")
    st.wait(30)
    # step 1 : check ipv6 static route
    route_entries = cli_show_json(dut1, "show ipv6 route json", type="vtysh")
    # expected json
    cwd = os.getcwd()
    expected_route_path = cwd+"/routing/SRv6/locator_static_route_expected_01.json"
    expected_route_json = json.loads(open(expected_route_path).read())
    result = json_cmp(route_entries, expected_route_json)
    if result and result.has_errors():
        st.report_fail("step 1 test_base_config_srvpn_locator_01_failed")
        for e in result.errors:
            st.log(e)

    # step 2 : check configdb mysid
    mysid_configdb_key = "SRV6_LOCATOR|{}".format("lsid1")

    checkpoint_msg = "test_base_config_srvpn_locator_01 step2"
    configdb_onefield_checkpoint(dut1, mysid_configdb_key, "block_len", data.mysid_base_prefix_len["block_len"], expect = True, checkpoint = checkpoint_msg)
    configdb_onefield_checkpoint(dut1, mysid_configdb_key, "node_len", data.mysid_base_prefix_len["node_len"], expect = True, checkpoint = checkpoint_msg)
    configdb_onefield_checkpoint(dut1, mysid_configdb_key, "func_len", data.mysid_base_prefix_len["func_len"], expect = True, checkpoint = checkpoint_msg)
    configdb_onefield_checkpoint(dut1, mysid_configdb_key, "argu_len", data.mysid_base_prefix_len["argu_len"], expect = True, checkpoint = checkpoint_msg)
    expected_prefix = data.mysid_prefix['lsid1'] + "/80"
    configdb_onefield_checkpoint(dut1, mysid_configdb_key, "prefix", expected_prefix, expect = True, checkpoint = checkpoint_msg)

    expected_op_val = '::fff1:1:0:0:0'+'|'+'end-dt46'+'|'+'Vrf1'
    configdb_checkarray(dut1, mysid_configdb_key, "opcode@", expected_op_val, expect = True, checkpoint = checkpoint_msg)
    expected_op_val = '::fff1:11:0:0:0'+'|'+'end-dt46'+'|'+'PUBLIC-TC11'
    configdb_checkarray(dut1, mysid_configdb_key, "opcode@", expected_op_val, expect = True, checkpoint = checkpoint_msg)

    # step 3 : check  appdb mysid
    checkpoint_msg = "test_base_config_srvpn_locator_01 step3"

    vrf = 'Vrf1'
    ip_str = data.mysid_prefix['lsid1'][:-1]+data.mysid_opcode[vrf][2:]
    ipaddr = netaddr.IPAddress(ip_str)
    key = 'SRV6_MY_SID_TABLE:' + ipaddr.__str__() + '/80'
    appdb_onefield_checkpoint(dut1, key, "block_len", data.mysid_base_prefix_len["block_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut1, key, "node_len", data.mysid_base_prefix_len["node_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut1, key, "func_len", data.mysid_base_prefix_len["func_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut1, key, "argu_len", data.mysid_base_prefix_len["argu_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut1, key, "action", "end.dt46", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut1, key, "vrf", vrf, expect = True, checkpoint = checkpoint_msg)

    # long vrf name
    vrf = 'PUBLIC-TC11'
    ip_str = data.mysid_prefix['lsid1'][:-1]+data.mysid_opcode[vrf][2:]
    ipaddr = netaddr.IPAddress(ip_str)
    key = 'SRV6_MY_SID_TABLE:' + ipaddr.__str__() + '/80'
    appdb_onefield_checkpoint(dut1, key, "block_len", data.mysid_base_prefix_len["block_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut1, key, "node_len", data.mysid_base_prefix_len["node_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut1, key, "func_len", data.mysid_base_prefix_len["func_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut1, key, "argu_len", data.mysid_base_prefix_len["argu_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut1, key, "action", "end.dt46", expect = True, checkpoint = checkpoint_msg)

    vrf_name = st.show(dut1, "vrfnametodevname {}".format(vrf), skip_tmpl=True, max_time=500, type="vtysh")
    last_pos = vrf_name.rfind('\n')
    vrf_name = vrf_name[:last_pos]

    appdb_onefield_checkpoint(dut1, key, "vrf", vrf_name, expect = True, checkpoint = checkpoint_msg)

    # step 4 : check  vpn router
    check_filed = ['rdroute', 'sid', 'peerv6', 'secetced']
    bgp_as = 100
    st.config(dut1, 'vtysh -c "config t" -c "vrf {}" -c "ip route 192.100.1.0/24 blackhole"'.format(vrf))
    st.config(dut1, 'vtysh -c "config t" -c "router bgp {} vrf {}" -c "address-family ipv4 unicast" -c "redistribute static"'.format(bgp_as, vrf))

    cmd = "cli -c 'no page' -c 'show bgp ipv4 vpn 192.100.1.0/24'"
    records = st.show(dut1, cmd)
    st.log(records)

    expected_vpn = {
        'rdroute':'2:2:192.100.1.0/24',
        'sid':'fd00:201:201:fff1:11::',
        'peerv6':'2000::178',
        'secetced':'1 available, best #1'
    }

    if not records or len(records)==0:
        st.report_fail("step 4 test_base_config_srvpn_locator_01_failed")

    check = False
    for re in records:
        match_cnt = 0
        st.log(re)
        for it in check_filed:
            st.log(re[it])
            if re[it] ==  expected_vpn[it]:
                match_cnt +=1

        if match_cnt == len(check_filed):
            check = True
            break

    if not check:
        st.log(records)
        st.report_fail("step 4 test_base_config_srvpn_locator_01_failed")


    # step 5 : del opcode
    locator_name = 'lsid1'
    vrf_name = 'PUBLIC-TC11'
    locator_cmd = "locator {} prefix {}/80 block-len 32 node-len 16 func-bits 32 argu-bits 48".format(locator_name, data.mysid_prefix[locator_name])
    del_opc_cmd = 'cli -c "configure terminal" -c "segment-routing" -c "srv6" -c "locators" -c  "{}" -c "no opcode {}"'.format(locator_cmd, data.mysid_opcode[vrf_name])

    st.config(dut1, del_opc_cmd)

    route_entries = cli_show_json(dut1, "show ipv6 route fd00:201:201:fff1:11::/80 json", type="vtysh")
    # expected json
    expected_route_path = cwd+"/routing/SRv6/locator_static_route_remove_01.json"
    expected_route_json = json.loads(open(expected_route_path).read())
    result = json_cmp(route_entries, expected_route_json)
    if not result:
        st.log ("step 5 test_base_config_srvpn_locator_01_failed")
        st.report_fail("step 5 test_base_config_srvpn_locator_01_failed")


    # step 6 : del locator
#    locator lsid1 prefix fd00:201:201::/80 block-len 32 node-len 16 func-bits 32 argu-bits 48
#     opcode ::FFF1:1:0:0:0 end-dt46 vrf Vrf1
#     opcode ::FFF1:11:0:0:0 end-dt46 vrf PUBLIC-TC11
#    exit

    del_loc_cmd = 'cli -c "configure terminal" -c "segment-routing" -c "srv6" -c "locators" -c "no locator {}"'.format(locator_name)
    st.config(dut1, del_loc_cmd)
    route_entries = cli_show_json(dut1, "show ipv6 route fd00:201:201:fff1:11::/80 json", type="vtysh")
    expected_route_path = cwd+"/routing/SRv6/locator_static_route_remove_01.json"
    expected_route_json = json.loads(open(expected_route_path).read())
    result = json_cmp(route_entries, expected_route_json)
    if not result:
        st.log ("step 6 test_base_config_srvpn_locator_01_failed")
        st.report_fail("step 5 test_base_config_srvpn_locator_01_failed")

    # step 7 : del srv6-locator
    vrf_name = 'Vrf1'
    bgp_as = '100'

    st.config(dut1, 'cli -c "config t" -c "router bgp {} vrf {}" -c "no srv6-locator"'.format(vrf_name, bgp_as))

    # records = st.show(dut1, "show bgp ipv4 vpn", type='alicli')
    cmd = "cli -c 'no page' -c 'show bgp ipv4 vpn 192.100.1.0/24'"
    records = st.show(dut1, cmd)
    st.log(records)

#  FCMD: cli -c 'no page' -c 'show bgp ipv4 vpn 192.100.1.0/24'
#  BGP routing table entry for 2:2:192.100.1.0/24, version 3
#  not allocated
#  Paths: (1 available, best #1)
#    Advertised to non peer-group peers:
#    2000::178
#    Local
#      0.0.0.0 from 0.0.0.0 (1.1.1.179) vrf PUBLIC-TC11(117) announce-nh-self
#        Origin incomplete, metric 0, weight 32768, valid, sourced, local, best (First path received)
#        Extended Community: RT:3:3
#        Originator: 1.1.1.179
#        Remote label: 3
#        Last update: Tue Mar 14 14:55:23 2023

    if not records or len(records)==0:
        st.log ("step 7 success")
    else:
        st.report_fail("step 7 test_base_config_srvpn_locator_01_failed")

# OSPREY-MC-B09-18-179.EU6# show bgp ipv4 vpn
# BGP table version is 1, local router ID is 1.1.1.179, vrf id 0
# Default local pref 100, local AS 100
# Status codes:  s suppressed, d damped, h history, * valid, > best, = multipath,
#                i internal, r RIB-failure, S Stale, R Removed
# Nexthop codes: @NNN nexthop's vrf id, < announce-nh-self
# Origin codes:  i - IGP, e - EGP, ? - incomplete
# RPKI validation codes: V valid, I invalid, N Not found

#    Network          Next Hop            Metric LocPrf Weight Path
# Route Distinguisher: 2:2
# *> 192.100.1.0/24   0.0.0.0@117<             0         32768 i
#     UN=0.0.0.0 EC{3:3} label=3 sid=fd00:201:201:fff1:11:: sid_structure=[32,16,32,48] type=bgp, subtype=5

# Displayed  1 routes and 1 total paths
# OSPREY-MC-B09-18-179.EU6#

    # step 8 : recover srv6 config
    bgp_as = '100'
    locator_name = 'lsid1'
    vrf_name = 'PUBLIC-TC11'
    locator_cmd = "locator {} prefix {}/80 block-len 32 node-len 16 func-bits 32 argu-bits 48".format(locator_name, data.mysid_prefix[locator_name])
    opc_cmd = 'cli -c "configure terminal" -c "segment-routing" -c "srv6" -c "locators" -c  "{}" -c "opcode {} end-dt46 vrf {}"'.format(locator_cmd, data.mysid_opcode[vrf_name], vrf_name)

    st.config(dut1, opc_cmd)
    st.config(dut1, 'cli -c "config t" -c "router bgp {} vrf {}" -c "srv6-locator {}"'.format(bgp_as, vrf_name, locator_name))
    st.wait(10)
    # records = st.show(dut1, "show bgp ipv4 vpn", type='alicli')
    cmd = "cli -c 'no page' -c 'show bgp ipv4 vpn 192.100.1.0/24'"
    records = st.show(dut1, cmd)
    st.log(records)

    expected_vpn = {
        'rdroute':'2:2:192.100.1.0/24',
        'sid':'fd00:201:201:fff1:11::',
        'peerv6':'2000::178',
        'secetced':'1 available, best #1'
    }

    if not records or len(records)==0:
        st.report_fail("step 8 test_base_config_srvpn_locator_01_failed")

    check = False
    for re in records:
        match_cnt = 0
        for it in check_filed:
            if re[it] ==  expected_vpn[it]:
                match_cnt +=1

        if match_cnt == len(check_filed):
            check = True
            break

    if not check:
        st.log(records)
        st.report_fail("step 8 test_base_config_srvpn_locator_01_failed")

# check  remote router
    # records = st.show(dut2, "show bgp ipv4 vpn", type='alicli')
    cmd = "cli -c 'no page' -c 'show bgp ipv4 vpn 192.100.1.0/24'"
    records = st.show(dut1, cmd)
    st.log(records)

# OSPREY-MC-B09-13-178.EU6# show bgp ipv4 vpn
# BGP table version is 1, local router ID is 1.1.1.178, vrf id 0
# Default local pref 100, local AS 100
# Status codes:  s suppressed, d damped, h history, * valid, > best, = multipath,
#                i internal, r RIB-failure, S Stale, R Removed
# Nexthop codes: @NNN nexthop's vrf id, < announce-nh-self
# Origin codes:  i - IGP, e - EGP, ? - incomplete
# RPKI validation codes: V valid, I invalid, N Not found

#    Network          Next Hop            Metric LocPrf Weight Path
# Route Distinguisher: 2:2
# *>i192.100.1.0/24   2000::179                0    100      0 i
#     UN=2000::179 EC{3:3} label=3 sid=fd00:201:201:fff1:11:: sid_structure=[32,16,32,48] type=bgp, subtype=0

# Displayed  1 routes and 1 total paths
    expected_vpn = {
        'rdroute':'2:2:192.100.1.0/24',
        'sid':'fd00:201:201:fff1:11::',
        'peerv6':'2000::178',
        'secetced':'1 available, best #1'
    }

    if not records or len(records)==0:
        st.report_fail("step 8 remote test_base_config_srvpn_locator_01_failed")

    check = False
    for re in records:
        match_cnt = 0
        for it in check_filed:
            if re[it] ==  expected_vpn[it]:
                match_cnt +=1

        if match_cnt == len(check_filed):
            check = True
            break

    if not check:
        st.log(records)
        st.report_fail("step 8 remote test_base_config_srvpn_locator_01_failed")

    # config locator end action
    locator_cmd = 'locator  test_end prefix fd00:301:301::/80 block-len 32 node-len 16 func-bits 32 argu-bits 48'
    end_opcode_cmd = 'opcode ::fff1:1:0:0:0 end'
    cmd = 'cli -c "configure terminal" -c "segment-routing" -c "srv6" -c "locators" -c "{}" -c "{}"'.format(locator_cmd, end_opcode_cmd)
    st.config(dut1, cmd)
    config_end_action_key = 'SRV6_LOCATOR|test_end'
    configdb_onefield_checkpoint(dut1, config_end_action_key, "opcode@", "::fff1:1:0:0:0|end", expect = True, checkpoint = "end sid configdb check failed.")

    appl_end_action_key = 'SRV6_MY_SID_TABLE:fd00:301:301:fff1:1::/80'
    appdb_onefield_checkpoint(dut1, appl_end_action_key, "action", "end", expect = True, checkpoint = "end sid appdb check failed.")
    appdb_onefield_checkpoint(dut1, appl_end_action_key, "vrf", "Default", expect = True, checkpoint = "end sid appdb check failed.")

    # show ip route
    show_cmd = "cli -c 'show ip route vrf PUBLIC-TC11 192.100.1.0/24'"
    result = st.show(dut2, show_cmd, skip_tmpl=True)
    if 'seg6 fd00:201:201:fff1:11::' not in result:
        st.report_fail("show ip route vrf cannot show right sid info.")

    st.report_pass("test_case_passed")


def load_2ksubif_100vrf(filesuffix='multi_vrf_full'):
    curr_path = os.getcwd()

    json_file_dut1_multi_vrf = curr_path+"/routing/SRv6/dut1_"+filesuffix+".json"
    st.apply_files(dut1, [json_file_dut1_multi_vrf])

    json_file_dut2_multi_vrf = curr_path+"/routing/SRv6/dut2_"+filesuffix+".json"
    st.apply_files(dut2, [json_file_dut2_multi_vrf])

    st.wait(10)

    reboot.config_reload_reboot(dut1, "/etc/spytest/SRv6/dut1_"+filesuffix+".json")
    reboot.config_reload_reboot(dut2, "/etc/spytest/SRv6/dut2_"+filesuffix+".json")

    st.banner("multi vrf config loaded completed")

def load_mirro_config(filesuffix='mirror_config'):
    curr_path = os.getcwd()

    json_file_dut1_multi_vrf = curr_path+"/routing/SRv6/dut1_"+filesuffix+".json"
    st.apply_files(dut1, [json_file_dut1_multi_vrf], method="replace_configdb")

    json_file_dut2_multi_vrf = curr_path+"/routing/SRv6/dut2_"+filesuffix+".json"
    st.apply_files(dut2, [json_file_dut2_multi_vrf], method="replace_configdb")

    st.wait(10)

    st.reboot(dut1)
    st.reboot(dut2)

    st.banner("mirror config loaded completed")

## 2k locator , base traffic and route learning
@pytest.mark.community
@pytest.mark.community_pass
def test_base_config_srvpn_2kl_route_learn_02():
    st.banner("test_base_config_srvpn_2kl_traffic_and_route_02 begin")

    # load full config
    if data.load_multi_vrf_config_done == False:
        load_2ksubif_100vrf()
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

        # def_v6_route_count_d2 = asicapi.get_ipv6_route_count(dut2)
        # if int(def_v6_route_count_d2) >= 50000 and not finish_v6_egress:
        #     end_timev6_egress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        #     finish_v6_egress = True
        #     st.log("dut2 v6 learn 5w time cost "+str(get_time_diff(str_start_time, end_timev6_egress)))
        # ingress
        def_v4_route_count_d1 = asicapi.get_ipv4_route_count(dut1)
        if int(def_v4_route_count_d1) >= 500000 and not finish_v4_ingress:
            end_timev4_ingress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            finish_v4_ingress = True
            st.log("dut1 v4 learn 50w time cost "+str(get_time_diff(str_start_time, end_timev4_ingress)))

        # def_v6_route_count_d1 = asicapi.get_ipv6_route_count(dut1)
        # if int(def_v6_route_count_d1) >= 50000 and not finish_v6_ingress:
        #     end_timev6_ingress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        #     finish_v6_ingress = True
        #     st.log("dut1 v6 learn 5w time cost "+str(get_time_diff(str_start_time, end_timev6_ingress)))

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
    st.log("dut1 v6 learn 5w time cost "+str(get_time_diff(str_start_time, end_timev4_ingress)))
    st.report_pass("test_case_passed")

## 100 vrf test
@pytest.mark.community
@pytest.mark.community_pass
def test_base_config_srvpn_multi_vrf_03():

    # ixia config 100 subinterface
    st.banner("test_base_config_srvpn_multi_vrf_03 begin")

    if data.load_multi_vrf_config_done == False:
        load_2ksubif_100vrf()
        data.load_multi_vrf_config_done = True

    # load ixia config
    ixia_load_config(ESR_MULTI_VRF_CONFIG)
    ixia_start_all_protocols()

    # step1 check vpn route learn 50w
    ret = check_vpn_route_nums(dut2, 500000, 0)
    if not ret:
        st.report_fail("step1 check_vpn_route_nums test_base_config_srvpn_multi_vrf_03")

    # check vrf vpn route
    # one vrf learn 5000 default learn 500000w
    # random check 10 vrf
    def get_check_vrf_list():
        vrf_array = []
        ra = get_random_array(0, 99, 10)
        for idx in ra:
            vrf_array.append(data.vrf_list[idx])
        return vrf_array

    # vrf_array = get_check_vrf_list()
    def check_vrf_fib():
        for chcek_vrf in data.vrf_list[0:100]:
            ret = check_vrf_route_nums(dut2, chcek_vrf, 5000, 1)
            if not ret:
                st.error("step1 check_vrf_route_nums {} 5000 test_base_config_srvpn_multi_vrf_03".format(chcek_vrf))
                return False
        return True

    if not retry_api(check_vrf_fib, retry_count= 3, delay= 5):
        st.report_fail("step1 check_vrf_fib test_base_config_srvpn_multi_vrf_03")

    st.wait(30)

    # check traffic
    ret = ixia_check_traffic(VRF_TRAFFIC_NAME, key="Rx frame", value=120000)
    if not ret:
        st.report_fail("Check traffic item {} rx frame failed".format(VRF_TRAFFIC_NAME))

    # step2: change vrf import rt withsame service-SID
    to_check_vrf = 'ACTN-TC47'
    rtlist = "1:10 1:30 1:50 1:70 1:90"

    cmd = "cli -c 'configure terminal' -c 'router bgp 100 vrf ACTN-TC47' -c 'address-family ipv4 unicast' -c 'route-target vpn import {}'".format(rtlist)
    st.config(dut2, cmd)
    st.wait(10)

    # check vrf route learn
    ret = check_vrf_route_nums(dut2, to_check_vrf, 25000, 1)
    if not ret:
        st.report_fail("step2 check_vrf_route_nums {} 5*5000 test_base_config_srvpn_multi_vrf_03".format(to_check_vrf))

    # check vrf ipv4 uni route and sid
    to_check_prefix_sid = {
        '200.10.0.1':'fd00:201:201:fff1:10::',
        '200.30.0.1':'fd00:201:201:fff1:30::',
        '200.50.0.1':'fd00:201:201:fff1:50::',
        '201.20.0.1':'fd00:201:201:fff2:6::',
        '201.40.0.1':'fd00:201:201:fff2:26::'
    }

    for (k, v) in to_check_prefix_sid.items():
        ret = check_bgp_vrf_ipv4_uni_sid(dut2, to_check_vrf, k, v)
        if not ret:
            st.report_fail("step2 check_bgp_vrf_ipv4_uni_sid failed ")


    # check vrf traffic
    # ret = ixia_add_traffic_item_for_specific_vrf()
    # if not ret:
    #     st.report_fail("Faild to add traffic item for specific vrf")

    # # check traffic
    # ret = ixia_check_traffic(SPECIFIC_VRF_TRAFFIC_NAME, key="Rx frame", value=50000)
    # if not ret:
    #     st.report_fail("Check traffic item {} rx frame failed".format(SPECIFIC_VRF_TRAFFIC_NAME))


    # step3: change vrf import rt
    # different service-SID
    # 1:30 1:70 change service-SID
    # 1:30 101|ipv4|SX-XIAN-CM-TC30
    # 1:70 101|ipv4|VPN6
    cmd = "cli -c 'configure terminal' -c 'router bgp 101 vrf SX-XIAN-CM-TC30' -c 'no srv6-locator lsid1'"
    st.config(dut1, cmd)
    cmd = "cli -c 'configure terminal' -c 'router bgp 101 vrf SX-XIAN-CM-TC30' -c 'srv6-locator lsid2'"
    st.config(dut1, cmd)
    cmd = "cli -c 'configure terminal' -c 'router bgp 101 vrf VPN6' -c 'no srv6-locator lsid1'"
    st.config(dut1, cmd)
    cmd = "cli -c 'configure terminal' -c 'router bgp 101 vrf VPN6' -c 'srv6-locator lsid3'"
    st.config(dut1, cmd)

    st.wait(10)
     #check vpn route learn 50w
    ret = check_vpn_route_nums(dut2, 500000, 0)
    if not ret:
        st.report_fail("step3 check_vpn_route_nums test_base_config_srvpn_multi_vrf_03")


    # check vrf route learn
    ret = check_vrf_route_nums(dut2, to_check_vrf, 25000, 1)
    if not ret:
        st.report_fail("step3 check_vrf_route_nums {} 5*5000 test_base_config_srvpn_multi_vrf_03".format(to_check_vrf))

    # check vrf ipv4 uni route and sid
    to_check_prefix_sid = {
        '200.10.0.1':'fd00:201:201:fff1:10::',
        '200.30.0.1':'fd00:201:202:fff1:30::',
        '200.50.0.1':'fd00:201:201:fff1:50::',
        '201.20.0.1':'fd00:201:203:fff2:6::',
        '201.40.0.1':'fd00:201:201:fff2:26::'
    }

    for (k, v) in to_check_prefix_sid.items():
        ret = check_bgp_vrf_ipv4_uni_sid(dut2, to_check_vrf, k, v)
        if not ret:
            st.report_fail("step3 check_bgp_vrf_ipv4_uni_sid failed ")

    # check vrf traffic
    ret = ixia_check_traffic(VRF_TRAFFIC_NAME, key='Rx frame', value=120000)
    if not ret:
        st.report_fail("Check traffic item {} rx frame failed".format(SPECIFIC_VRF_TRAFFIC_NAME))

    st.report_pass("test_case_passed")

## ecmp test
@pytest.mark.community
@pytest.mark.community_pass
def test_srvpn_ecmp_04():
    st.banner("test_srvpn_ecmp_04 begin")

    load_2ksubif_100vrf("multi_vrf_ecmp")

    # load ixia config
    ixia_load_config(ESR_ECMP_CONFIG)
    ixia_start_all_protocols()

    # ecmp ingress vrf
    # PRIVATE-TC10  PUBLIC-TC20  ACTN-TC60

    # step1: change vrf import rt withsame service-SID
    to_check_vrf = 'PUBLIC-TC20'
    rtlist = "1:10 1:20 1:60"

    # # check vrf route learn
    show_hw_route_count(dut2)
    ret = check_vrf_route_nums(dut2, to_check_vrf, 10000, 1)
    if not ret:
        st.report_fail("step1 check_vrf_route_nums {} 10000 test_srvpn_ecmp_04".format(to_check_vrf))

    # check vrf ipv4 uni route and sid
    # to_check_prefix_sid = {
    #     '200.10.0.1':'fd00:201:202:fff1:10::',
    #     '200.10.0.2':'fd00:201:203:fff1:60::'
    # }

    # for (k, v) in to_check_prefix_sid.items():
    #     ret = check_bgp_vrf_ipv4_uni_sid(dut2, to_check_vrf, k, v)
    #     if not ret:
    #         st.report_fail("step1 check_bgp_vrf_ipv4_uni_sid failed ")

    # check route appdb
    vrf_name = st.show(dut1, "vrfnametodevname {}".format(to_check_vrf), skip_tmpl=True, max_time=500, type="vtysh")
    last_pos = vrf_name.rfind('\n')
    vrf_name = vrf_name[:last_pos]

    key = 'ROUTE_TABLE:' + vrf_name + ':200.10.0.1/32'
    st.wait(5)
    checkpoint_msg = "step1 route appdb check failed"
    appdb_onefield_checkpoint(dut2, key, "nexthop", "2000::179,3000::179", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "ifname", "unknown,unknown", expect = True, checkpoint = checkpoint_msg)
    #appdb_onefield_checkpoint(dut2, key, "vpn_sid", "fd00:201:201:fff1:20::,fd00:201:202:fff1:10::,fd00:201:201:fff1:60::", expect = True, checkpoint = checkpoint_msg)
    #appdb_onefield_checkpoint(dut2, key, "seg_src", "3000::178,3000::178", expect = True, checkpoint = checkpoint_msg)

    vpnsid_val = appdb_get_onefield(dut2, key, "vpn_sid")
    if vpnsid_val is None:
        st.report_fail(checkpoint_msg)

    vpnsid_ecmp_list = vpnsid_val.split(",")
    for sid in ["fd00:201:202:fff1:10::", "fd00:201:201:fff1:60::"]:
        if sid not in vpnsid_ecmp_list:
            st.log("step1 route appdb check failed , sid = {}".format(sid))

    st.wait(30)

    # check interface counters
    ret = ixia_start_traffic(VRF_TRAFFIC_NAME)
    if not ret:
        st.report_fail("Start traffic item {} rx frame failed".format(VRF_TRAFFIC_NAME))

    ecmp_member_Gbps = data.ecmp_member_Gbps
    ret = check_dut_intf_tx_traffic_counters(dut2, data.ecmp_dut2_portlist, ecmp_member_Gbps)
    if not ret:
        st.report_fail("Check dut interface counters failed")

    ret = ixia_stop_traffic(VRF_TRAFFIC_NAME)
    if not ret:
        st.report_fail("Stop traffic item {} rx frame failed".format(VRF_TRAFFIC_NAME))

    st.report_pass("test_case_passed")


#
#            +--------------------+                +--------------------+
# TG (MC)  --| PC251              |                |                    |
#            |                    |                |                    | PC251
# TG (RR)  --|                    | PC161-PC161    |                    |===== TG (MC)
#            | DUT1(MC-58)        | ===========    |  DUT2(MC-59)       |
#            |                    | PC162-PC162    |                    |----- TG (RR)
#            |                    |                |                    |
#            |                    |                |                    |
#            |                    |                |                    |
#            +--------------------+                +--------------------+

def check_traffic():
    # check v4 traffic
    ret = ixia_start_traffic(TRAFFIC_MIRROR_V4)
    if not ret:
        st.log("Start traffic item {} failed".format(TRAFFIC_MIRROR_V4))
        return False
    st.wait(10)
    ret = ixia_stop_traffic(TRAFFIC_MIRROR_V4)
    if not ret:
        st.log("Stop traffic item {} failed".format(TRAFFIC_MIRROR_V4))
        return False

    traffic_v4 = ixia_get_traffic_stat(TRAFFIC_MIRROR_V4)
    if not traffic_v4:
        st.log("Get {} traffic stat failed".format(TRAFFIC_MIRROR_V4))
        return False
    # check val
    if  int(traffic_v4['Rx Frames']) > 39900 and int(traffic_v4['Tx Frames']) > 39900 and traffic_v4['Loss %'] == '0.000':
        st.log("traffic_v4 check success")
    else:
        st.log("traffic_v4 check failed")
        return False

    # check v6 traffic
    ret = ixia_start_traffic(TRAFFIC_MIRROR_V6)
    if not ret:
        st.log("Start traffic item {} failed".format(TRAFFIC_MIRROR_V6))
        return False
    st.wait(10)
    ret = ixia_stop_traffic(TRAFFIC_MIRROR_V6)
    if not ret:
        st.log("Stop traffic item {} failed".format(TRAFFIC_MIRROR_V6))
        return False

    traffic_v6 = ixia_get_traffic_stat(TRAFFIC_MIRROR_V6)
    if not traffic_v6:
        st.log("Get {} traffic stat failed".format(TRAFFIC_MIRROR_V6))
        return False
    # check val
    if  int(traffic_v6['Rx Frames']) > 39900 and int(traffic_v6['Tx Frames']) > 39900 and traffic_v6['Loss %'] == '0.000':
        st.log("traffic_v6 check success")
    else:
        st.log("traffic_v6 check failed")
        return False
    return True


def test_srvpn_mirror_config_05():
    st.banner("test_srvpn_mirror_config_05 begin")
    # wait route learning
    st.wait(30)
    show_hw_route_count(dut1)
    show_hw_route_count(dut2)

# 2023-03-30 06:29:19,820 T0000: INFO  [D1-MC-58] FCMD: curl http://127.0.0.1:12346/route -s | grep ipv4
# 2023-03-30 06:29:19,871 T0000: INFO  [D1-MC-58]     "ipv4_route_count": 384071,
# 2023-03-30 06:29:19,871 T0000: INFO  [D1-MC-58] admin@MC-58:~$
# 2023-03-30 06:29:19,872 T0000: INFO  dut1 v4 route : 384071
# 2023-03-30 06:29:20,073 T0000: INFO  [D1-MC-58] FCMD: curl http://127.0.0.1:12346/route -s | grep ipv6
# 2023-03-30 06:29:20,124 T0000: INFO  [D1-MC-58]     "ipv6_route_count": 256063
# 2023-03-30 06:29:20,124 T0000: INFO  [D1-MC-58] admin@MC-58:~$
# 2023-03-30 06:29:20,125 T0000: INFO  dut1 v6 route : 256063
    # traffic check
    if not check_traffic():
        st.report_fail("traffic check failed")

    #  check base checkout
    st.report_pass("test_case_passed")

def test_srvpn_mirror_config_redistribute_vrf_06():
    st.banner("test_srvpn_mirror_config_redistribute_vrf_06 begin")

    show_hw_route_count(dut1)
    show_hw_route_count(dut2)

    # check1 : dut1 ACTN_TC0 route ACTN_TC1 route
    st.banner("dut1 ACTN_TC0 ACTN_TC1 route")
    check_prefix = "14.1.64.1/32"
    svrf = 'ACTN_TC0'
    dvrf = 'ACTN_TC1'
    vtysh_cmd1 = "show bgp vrf  {} ipv4 unicast {}".format(svrf, check_prefix)
    vtysh_cmd2 = "show bgp vrf  {} ipv4 unicast {}".format(dvrf, check_prefix)
    output_1 = st.show(dut1, vtysh_cmd1, skip_tmpl=True, max_time=500, type="vtysh")
    print(output_1)
    output_2 = st.show(dut1, vtysh_cmd2, skip_tmpl=True, max_time=500, type="vtysh")
    print(output_2)
    # compare output, expected same
    if not compare_redistribute_vrf_route(svrf, dvrf, output_1, output_2):
        st.report_fail("{} route and {} route is diffent".format(svrf, dvrf))

    # check appdb
# root@MC-58:~# redis-cli -p 6380 -n 0 hgetall "ROUTE_TABLE:Vrf10001:14.1.64.1/32"
#  1) "nexthop"
#  2) "fd00:0:200:172::"
#  3) "ifname"
#  4) "unknown"
#  5) "vpn_sid"
#  6) "fd00:201:2022:fff0:3::"
#  7) "seg_src"
#  8) "fd00:0:200:171::"
#  9) "policy"
# 10) "na"
# 11) "blackhole"
# 12) "false"
# root@MC-58:~#

    svrf_name = get_vrf_realname(dut1,svrf)
    dvrf_name = get_vrf_realname(dut1,dvrf)

    check_val = {
        "nexthop":"fd00:0:200:172::",
        "ifname":"unknown",
        "vpn_sid":"fd00:201:2022:fff0:3::",
        "seg_src":"fd00:0:200:171::",
        "policy":"na",
        "blackhole":"false"
    }
    checkpoint_msg = "test_srvpn_mirror_config_redistribute_vrf_06 check1"
    for vrf_it in [svrf_name, dvrf_name]:
        appdb_key = "ROUTE_TABLE:{}:{}".format(vrf_it, check_prefix)
        for k in check_val.keys():
            appdb_onefield_checkpoint(dut1, appdb_key, k, check_val[k], expect = True, checkpoint = checkpoint_msg)


    # check2 : dut2 PUBLIC_TC0 PUBLIC_TC1 ipv6 route
    st.banner("dut2 PUBLIC_TC0 PUBLIC_TC1 ipv6 route")
    check_prefix = "114:0:1::18f0/128"
    svrf = 'PUBLIC_TC0'
    dvrf = 'PUBLIC_TC1'
    vtysh_cmd1 = "show bgp vrf {} ipv6 unicast {}".format(svrf, check_prefix)
    vtysh_cmd2 = "show bgp vrf {} ipv6 unicast {}".format(dvrf, check_prefix)
    output_1 = st.show(dut2, vtysh_cmd1, skip_tmpl=True, max_time=500, type="vtysh")
    print(output_1)
    output_2 = st.show(dut2, vtysh_cmd2, skip_tmpl=True, max_time=500, type="vtysh")
    print(output_2)
    # compare output, expected same
    if not compare_redistribute_vrf_route(svrf, dvrf, output_1, output_2):
        st.report_fail("{} route and {} route is diffent".format(svrf, dvrf))

# 127.0.0.1:6380> hgetall ROUTE_TABLE:Vrf10011:114:0:1::18f0/128
#  1) "nexthop"
#  2) "fd00:0:200:171::"
#  3) "ifname"
#  4) "unknown"
#  5) "vpn_sid"
#  6) "fd00:201:2021:fff0:2::"
#  7) "seg_src"
#  8) "fd00:0:200:172::"
#  9) "policy"
# 10) "na"
# 11) "blackhole"
# 12) "false"

    # check appdb
    svrf_name = get_vrf_realname(dut2, svrf)
    dvrf_name = get_vrf_realname(dut2, dvrf)

    check_val = {
        "nexthop":"fd00:0:200:171::",
        "ifname":"unknown",
        "vpn_sid":"fd00:201:2021:fff0:2::",
        "seg_src":"fd00:0:200:172::",
        "policy":"na",
        "blackhole":"false"
    }
    checkpoint_msg = "test_srvpn_mirror_config_redistribute_vrf_06 check1"
    for vrf_it in [svrf_name, dvrf_name]:
        appdb_key = "ROUTE_TABLE:{}:{}".format(vrf_it, check_prefix)
        for k in check_val.keys():
            appdb_onefield_checkpoint(dut2, appdb_key, k, check_val[k], expect = True, checkpoint = checkpoint_msg)
    # check3 : no redistribute vrf

    # check4 : recover redistribute vrf

    st.report_pass("test_case_passed")

def test_srvpn_mirror_config_bgp_flap_07():
    st.banner("test_srvpn_mirror_config_bgp_flap_07 begin")

    # flap
    show_hw_route_count(dut1)
    show_hw_route_count(dut2)
    st.log("start flap")
    ixia_config_bgp_flapping(True)
    st.wait(20)
    ixia_config_bgp_flapping(False)
    st.log("flap finish")
    show_hw_route_count(dut1)
    show_hw_route_count(dut2)

    st.log("waitting 60s")
    st.wait(60)
    show_hw_route_count(dut1)
    show_hw_route_count(dut2)

    # traffic check
    if not check_traffic():
        st.report_fail("traffic check failed")

    st.report_pass("test_case_passed")

def test_srvpn_mirror_config_underlay_link_flap_08():
    st.banner("test_srvpn_mirror_config_underlay_link_flap_08 begin")

    st.log("before flap")
    show_hw_route_count(dut1)
    show_hw_route_count(dut2)

    # flap portchannel port
    flap_lag_member(dut1, "PortChannel161", 5)
    flap_lag_member(dut1, "PortChannel162", 5)

    # check traffic after lag member flap
    show_hw_route_count(dut1)
    show_hw_route_count(dut2)
    st.log("flap finish")

    # traffic check
    if not check_traffic():
        st.report_fail("traffic check failed")

    # wait route learning
    st.report_pass("test_case_passed")

def test_srvpn_mirror_config_underlay_ecmp_switch_09():
    st.banner("test_srvpn_mirror_config_underlay_ecmp_switch_09 begin")

    ret = ixia_start_traffic(TRAFFIC_MIRROR_ULECMP)
    if not ret:
        st.log("Start traffic item {} failed".format(TRAFFIC_MIRROR_ULECMP))
        return False
    st.wait(5)

    phyif = "PortChannel161"
    cmd = "interface {}\n shutdown\n".format(phyif)
    st.config(dut2, cmd, type='alicli',skip_error_check=True)
    st.wait(5)

    ret = ixia_stop_traffic(TRAFFIC_MIRROR_ULECMP)
    if not ret:
        st.log("Stop traffic item {} failed".format(TRAFFIC_MIRROR_ULECMP))
        return False

    cmd = "interface {}\n no shutdown\n".format(phyif)
    st.config(dut2, cmd, type='alicli',skip_error_check=True)
    st.wait(5)

    traffic_ecmp = ixia_get_traffic_stat(TRAFFIC_MIRROR_ULECMP)
    if not traffic_ecmp:
        st.log("Get {} traffic stat failed {}".format(TRAFFIC_MIRROR_ULECMP))
        return False
    # check val
    if  traffic_ecmp['Loss %'] == '0.000':
        st.log("traffic_v4 check success")
    else:
        st.log("traffic_v4 check failed")
        return False

    st.report_pass("test_case_passed")


def duts_load_config(dut1_config, dut2_config):
    dut_list = st.get_dut_names()
    st.log("===== GET DUT LIST {}".format(dut_list))

    dut1_config_file_path = os.path.join(os.getcwd(), "routing/SRv6/{}".format(dut1_config))
    dut2_config_file_path = os.path.join(os.getcwd(), "routing/SRv6/{}".format(dut2_config))
    st.apply_files(dut_list[0], [dut1_config_file_path])
    st.apply_files(dut_list[1], [dut2_config_file_path])

    reboot.config_reload_reboot(dut_list[0], "/etc/spytest/{}".format(dut1_config))
    reboot.config_reload_reboot(dut_list[1], "/etc/spytest/{}".format(dut2_config))


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
    # plt.show()

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
    for i in range(cursor, len(x) - 1):
        if y[i] * 100 / max_rx_rate < 98 and start_time == cursor:
            start_time = x[i]

        if y[i] == 0 and stop_time == cursor:
            stop_time = x[i]
            break

    return stop_time - start_time


def get_log_dir_path():
    user_root = env.get("SPYTEST_USER_ROOT", os.getcwd())
    logs_path = env.get("SPYTEST_LOGS_PATH", user_root)
    return logs_path


@pytest.mark.community
@pytest.mark.community_pass
def test_srvpn_performance_500K():
    st.banner("test_srvpn_performance_500K begin")
    dut_list = st.get_dut_names()
    dut1 = dut_list[0]
    dut2 = dut_list[1]

    route_count = 500000

    # 1. load DUT config
    dut1_config = "performance/dut1_one_vrf.json"
    dut2_config = "performance/dut2_one_vrf.json"
    duts_load_config(dut1_config, dut2_config)

    # 2. load TG config
    ixia_config = os.path.join(os.getcwd(), "routing/SRv6/performance/ixia_one_vrf_500K.json")
    ixia_load_config(ixia_config)

    # 3. start traffic
    ixia_start_all_traffic()
    ixia_start_logging_port_view()

    # 4. start protocol
    ixia_start_all_protocols()
    st.wait(180)

    if not retry_api(check_vpn_route_nums, dut=dut2, expected_num=route_count, compare=0, retry_count=3, delay=180):
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
    st.wait(180)
    # 8. get perform data
    ixia_stop_logging_port_view()
    local_file = "port_statictics_{}.csv".format(route_count)
    local_file = os.path.join(os.getcwd(), "../", get_log_dir_path(), local_file)

    perf_jpg_file = 'eSR_Performance_{}.jpg'.format(route_count)
    perf_jpg_file = os.path.join(os.getcwd(), "../", get_log_dir_path(), perf_jpg_file)

    st.log("===============")
    st.log("===============")
    st.log("===============")
    st.log(local_file)
    st.log(perf_jpg_file)

    ixia_get_port_view_data(local_file)
    plot_perf(local_file, perf_jpg_file)

    load_t, cursor = get_route_load_time(0, local_file)
    covergen_t = get_route_convergence_time(cursor, local_file)

    st.log("======== {} Route Load Time =======".format(route_count))
    st.log("Load Time: {} s, Rate: {} rps".format(load_t, route_count / load_t))

    st.log("======== {} Route Convergence Time =======".format(route_count))
    st.log("Convergence Time: {} s, Rate: {} rps".format(covergen_t, route_count / covergen_t))

    # 9. stop traffic
    ixia_stop_all_traffic()
    st.report_pass("msg", "LoadPerf: {} rps, CovergePerf: {} rps".format(route_count / load_t, route_count / covergen_t))


@pytest.mark.community
@pytest.mark.community_pass
def test_srvpn_performance_1M():
    st.banner("test_srvpn_performance_1M begin")
    dut_list = st.get_dut_names()
    dut1 = dut_list[0]
    dut2 = dut_list[1]

    route_count = 1000000

    # 1. load DUT config
    dut1_config = "performance/dut1_one_vrf.json"
    dut2_config = "performance/dut2_one_vrf.json"
    duts_load_config(dut1_config, dut2_config)

    # 2. load TG config
    ixia_config = os.path.join(os.getcwd(), "routing/SRv6/performance/ixia_one_vrf_1M.json")
    ixia_load_config(ixia_config)

    # 3. start traffic
    ixia_start_all_traffic()
    ixia_start_logging_port_view()

    # 4. start protocol
    ixia_start_all_protocols()
    st.wait(300)
    if not retry_api(check_vpn_route_nums, dut=dut2, expected_num=route_count, compare=0, retry_count=3, delay=300):
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
    st.wait(300)
    # 8. get perform data
    ixia_stop_logging_port_view()
    local_file = "port_statictics_{}.csv".format(route_count)
    local_file = os.path.join(os.getcwd(), "../", get_log_dir_path(), local_file)

    perf_jpg_file = 'eSR_Performance_{}.jpg'.format(route_count)
    perf_jpg_file = os.path.join(os.getcwd(), "../", get_log_dir_path(), perf_jpg_file)

    ixia_get_port_view_data(local_file)
    plot_perf(local_file, perf_jpg_file)

    load_t, cursor = get_route_load_time(0, local_file)
    covergen_t = get_route_convergence_time(cursor, local_file)

    st.log("======== {} Route Load Time =======".format(route_count))
    st.log("Load Time: {} s, Rate: {} rps".format(load_t, route_count / load_t))

    st.log("======== {} Route Convergence Time =======".format(route_count))
    st.log("Convergence Time: {} s, Rate: {} rps".format(covergen_t, route_count / covergen_t))

    # 9. stop traffic
    ixia_stop_all_traffic()
    st.report_pass("msg", "LoadPerf: {} rps, CovergePerf: {} rps".format(route_count / load_t, route_count / covergen_t))


@pytest.mark.community
@pytest.mark.community_pass
def test_srvpn_performance_2M():
    st.banner("test_srvpn_performance_2M begin")
    dut_list = st.get_dut_names()
    dut1 = dut_list[0]
    dut2 = dut_list[1]

    route_count = 2000000

    # 1. load DUT config
    dut1_config = "performance/dut1_one_vrf.json"
    dut2_config = "performance/dut2_one_vrf.json"
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

    ixia_get_port_view_data(local_file)
    plot_perf(local_file, perf_jpg_file)

    load_t, cursor = get_route_load_time(0, local_file)
    covergen_t = get_route_convergence_time(cursor, local_file)

    st.log("======== {} Route Load Time =======".format(route_count))
    st.log("Load Time: {} s, Rate: {} rps".format(load_t, route_count / load_t))

    st.log("======== {} Route Convergence Time =======".format(route_count))
    st.log("Convergence Time: {} s, Rate: {} rps".format(covergen_t, route_count / covergen_t))

    # 9. stop traffic
    ixia_stop_all_traffic()
    st.report_pass("msg", "LoadPerf: {} rps, CovergePerf: {} rps".format(route_count / load_t, route_count / covergen_t))

