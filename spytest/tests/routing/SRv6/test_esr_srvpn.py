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
from utilities.utils import retry_api

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
from esr_lib import cli_show_json, json_cmp, configdb_checkpoint, configdb_checkarray, appdb_checkpoint, configdb_onefield_checkpoint,appdb_onefield_checkpoint,check_vrf_route_nums, get_random_array, check_vpn_route_nums
import esr_lib as loc_lib
from esr_vars import * #all the variables used for vrf testcase
from esr_vars import data
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

def add_bmp_config_background(dut):
    st.log("config global bmp")
    st.config(dut, "cli -c 'configure terminal' -c 'bmp' -c 'bmp target bmp01' -c 'bmp connect 192.0.0.250 port 5555 min-retry 500 max-retry 2000'")
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
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]

    cmd = "cli -c 'no page' -c 'show ip interface brief'"
    output1 = st.show(dut1, cmd)
    output2 = st.show(dut2, cmd)

    data.dut1_all_ip_addr = copy.deepcopy(output1)
    data.dut2_all_ip_addr = copy.deepcopy(output2)

def egress_dut_ixia_config():
    tg_dut2_eth109, tg_ph_dut2_eth109 = tgapi.get_handle_byname("T1D2P1") # ixia - 178 Eth109
    tg_dut2_eth110, tg_ph_dut2_eth110 = tgapi.get_handle_byname("T1D2P2") # ixia - 178 Eth110

    tg_result1 = tg_dut2_eth109.tg_interface_config(port_handle=tg_ph_dut2_eth109, mode='config', 
        intf_ip_addr='100.1.0.2', 
        gateway='100.1.0.1',
        arp_send_req='1')
    
    st.log("Topology - Port ip Unconfig tg api result = {}".format(tg_result1))

    tg_result2 = tg_dut2_eth110.tg_interface_config(port_handle=tg_ph_dut2_eth110, mode='config', 
        intf_ip_addr='100.2.0.2', 
        gateway='100.2.0.1',
        arp_send_req='1')
    
    st.log("Topology - Port ip Unconfig tg api result = {}".format(tg_result2))

    # Configuring the BGP router in vrf
    conf_var = {'mode'                 : 'enable',
                'active_connect_enable' : '1',
                'enable_4_byte_as'      : '1',
                'local_as'              : 999,
                'remote_as'             : 100,
                'remote_ip_addr'        : '100.1.0.1'
                }

    ctrl_start = { 'mode' : 'start'}
    ctrl_stop = { 'mode' : 'stop'}

    tg_dut2_eth109_bgp_v4_vrf = tgapi.tg_bgp_config(tg = tg_dut2_eth109,
        handle    = tg_result1['ipv4_handle'],
        conf_var  = conf_var,
        #route_var = route_var,
        ctrl_var  = ctrl_start)
    
    st.log("tg_bgp_config result {}".format(tg_dut2_eth109_bgp_v4_vrf))

    # Configuring the BGP router in vrf
    conf_var = {'mode'                 : 'enable',
                'active_connect_enable' : '1',
                'enable_4_byte_as'      : '1',
                'local_as'              : 998,
                'remote_as'             : 100,
                'remote_ip_addr'        : '100.2.0.1'
                }

    ctrl_start = { 'mode' : 'start'}
    ctrl_stop = { 'mode' : 'stop'}

    tg_dut2_eth110_bgp_v4_vrf = tgapi.tg_bgp_config(tg = tg_dut2_eth110,
        handle    = tg_result2['ipv4_handle'],
        conf_var  = conf_var,
        #route_var = route_var,
        ctrl_var  = ctrl_start)

    st.log("tg_bgp_config result {}".format(tg_dut2_eth110_bgp_v4_vrf))

    data.srv6['tg_dut2_eth109']=tg_dut2_eth109
    data.srv6['tg_dut2_eth110']=tg_dut2_eth110
    data.srv6['tg_ph_dut2_eth109']=tg_ph_dut2_eth109
    data.srv6['tg_ph_dut2_eth110']=tg_ph_dut2_eth110
    data.srv6['bgpv4_handle_dut2_eth109']=tg_result1['ipv4_handle']
    data.srv6['bgpv4_handle_dut2_eth110']=tg_result2['ipv4_handle']

def ingress_dut_ixia_config():
    tg_dut1_eth109, tg_ph_dut1_eth109 = tgapi.get_handle_byname("T1D1P1") # ixia - 179 Eth109
    tg_dut1_eth110, tg_ph_dut1_eth110 = tgapi.get_handle_byname("T1D1P2") # ixia - 179 Eth110

    tg_result1 = tg_dut1_eth109.tg_interface_config(port_handle=tg_ph_dut1_eth109, mode='config', 
        intf_ip_addr='101.1.0.2', 
        gateway='101.1.0.1',
        ipv6_intf_addr='2000:0:1:1:0:0:0:2', 
        ipv6_gateway='2000:0:1:1:0:0:0:1',
        arp_send_req='1')
    
    st.log("Topology - Port ip Unconfig tg api result = {}".format(tg_result1))

    tg_result2 = tg_dut1_eth110.tg_interface_config(port_handle=tg_ph_dut1_eth110, mode='config', 
        intf_ip_addr='101.2.0.2', 
        gateway='101.2.0.1',
        ipv6_intf_addr='2000:0:0:1:0:0:0:2', 
        ipv6_gateway='2000:0:0:1:0:0:0:1',
        arp_send_req='1')
    
    st.log("Topology - Port ip Unconfig tg api result = {}".format(tg_result2))

    # Configuring the BGP router in vrf
    conf_var = {'mode'                 : 'enable',
                'active_connect_enable' : '1',
                'enable_4_byte_as'      : '1',
                'local_as'              : 999,
                'remote_as'             : 100,
                'remote_ip_addr'        : '101.1.0.1'
                }
    route_var = [{'mode':'add', 
                'ip_version':'6', 
                'num_routes':'100', 
                'prefix':'3400:1::', 
                'as_path':'as_seq:1', 
                'ipv6_prefix_length': 128
                }, 
                {'mode':'add', 
                'ip_version':'6', 
                'num_routes':'100', 
                'prefix':'3300:1::', 
                'as_path':'as_seq:1', 
                'ipv6_prefix_length': 64
                }]
    ctrl_start = { 'mode' : 'start'}
    ctrl_stop = { 'mode' : 'stop'}

    tg_dut1_eth109_bgp_v4_vrf = tgapi.tg_bgp_config(tg = tg_dut1_eth109,
        handle    = tg_result1['ipv4_handle'],
        conf_var  = conf_var,
        route_var = route_var,
        ctrl_var  = ctrl_start)
    
    st.log("tg_bgp_config result {}".format(tg_dut1_eth109_bgp_v4_vrf))

    # Configuring the BGP router in vrf
    conf_var = {'mode'                 : 'enable',
                'active_connect_enable' : '1',
                'enable_4_byte_as'      : '1',
                'local_as'              : 998,
                'remote_as'             : 100,
                'remote_ip_addr'        : '101.2.0.1'
                }
    route_var = {'mode':'add', 
                'num_routes': '100', 
                'prefix': '202.1.0.0', 
                'as_path':'as_seq:1'
                }
    ctrl_start = { 'mode' : 'start'}
    ctrl_stop = { 'mode' : 'stop'}

    tg_dut1_eth110_bgp_v4_vrf = tgapi.tg_bgp_config(tg = tg_dut1_eth110,
        handle    = tg_result2['ipv4_handle'],
        conf_var  = conf_var,
        route_var = route_var,
        ctrl_var  = ctrl_start)

    st.log("tg_bgp_config result {}".format(tg_dut1_eth110_bgp_v4_vrf))

    data.srv6['tg_dut1_eth109']=tg_dut1_eth109
    data.srv6['tg_dut1_eth110']=tg_dut1_eth110
    data.srv6['tg_ph_dut1_eth109']=tg_ph_dut1_eth109
    data.srv6['tg_ph_dut1_eth110']=tg_ph_dut1_eth110
    data.srv6['tg_dut1_eth109_result1']=tg_result1
    data.srv6['tg_dut1_eth110_result1']=tg_result2
    data.srv6['bgpv4_handle_dut1_eth109']=tg_result1['ipv4_handle']
    data.srv6['bgpv4_handle_dut1_eth110']=tg_result2['ipv4_handle']
    data.srv6['tg_dut1_eth109_bgp_v4_vrf']=tg_dut1_eth109_bgp_v4_vrf
    data.srv6['tg_dut1_eth110_bgp_v4_vrf']=tg_dut1_eth110_bgp_v4_vrf


@pytest.fixture(scope="module", autouse=True)
def esr_srvpn_module_hooks(request):
    #add things at the start of this module

    global vars
    vars = st.ensure_min_topology("D1D2:4","D1T1:6","D2T1:2")
    (data.tg_list, data.tg_ph_list) = get_handles()
    for i in range(6):
        data.tg_list[i].tg_traffic_control(action='reset',port_handle=data.tg_ph_list[i])
    
    duts_base_config()
    egress_dut_ixia_config()
    ingress_dut_ixia_config()
    # tg1_base_config()
    # tg2_base_config()
    # tg3_base_config()
    # data.tg_list[0].tg_test_control(action='stop_all_protocols')
    # st.wait(20)
    # tg1_bgp_router_add()
    # tg2_bgp_router_add()
    # tg3_bgp_router_add()    
    # data.tg_list[0].tg_test_control(action='start_all_protocols')
    # st.wait(150)
    # vrfs_traffic_add()
    # vrfs_traffic_v6_add()
    # get_dut_ip()
    yield
    # l3_base_unconfig()

@pytest.fixture(scope="function", autouse=True)
def esr_srvpn_func_hooks(request):
    # add things at the start every test case
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]

    yield
    # if st.get_func_name(request) == 'test_bgp_fast_isolate_and_recover':
    #     if not loc_lib.check_bgp_isolate(dut1, 'no-isolate'):
    #         no_isolate_cmd = "no isolate fast"
    #         st.config(dut1, no_isolate_cmd, type='alicli')
    # else:
    #     st.show(dut1,"show vrf")
    #     st.show(dut2,"show vrf")

def duts_base_config():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    curr_path = os.getcwd()
    json_file_dut1 = curr_path+"/routing/SRv6/esr_dut1_config.json"
    json_file_dut2 = curr_path+"/routing/SRv6/esr_dut2_config.json"
    st.apply_files(dut1, [json_file_dut1])
    st.apply_files(dut2, [json_file_dut2])

    reboot.config_save_reboot(data.my_dut_list)
    #dict1 = {'command': "copy run start", 'type':'alicli','skip_error_check':True}
    #dict2 = {'command': "copy run start", 'type':'alicli','skip_error_check':True}
    #parallel.exec_parallel(True, [dut1, dut2], st.config, [dict1, dict2])

    #dict1 = {}
    #parallel.exec_parallel(True, [dut1, dut2], arp_api.show_arp, [dict1, dict1])
    #parallel.exec_parallel(True, [dut1, dut2], st.reboot, [dict1, dict1])
    
def tg1_bgp_router_add():

    #init DUT1====TG
    tg1_port_vrf_route_list=[0,0,0]
    tg1_port_vrf_route_v6_list=[0,0,0]
    for port_i in range(4):
        tg = data.tg_list[port_i]
        tg_ph = data.tg_ph_list[port_i]
        port_handle = data.tg1_handle[port_i]

        #create vrf1 route
        vrf_id = 0
        route1 = tg.tg_emulation_bgp_route_config(handle=port_handle['bgp_v4'][vrf_id]['conf']['handle'], mode='add', 
                                    num_routes=data.tg1_vrf1_router_count_list[port_i],
                                    prefix=data.tg1_vrf1_router_prefix_list[port_i], 
                                    prefix_from=data.tg1_router_prefix_length, as_path='as_seq:1', active='1')
        tg1_port_vrf_route_list[0] = route1

        route1_v6 = tg.tg_emulation_bgp_route_config(handle=port_handle['bgp_v6'][vrf_id]['conf']['handle'], mode='add', 
                                    num_routes=data.tg1_vrf1_router_v6_count_list[port_i],
                                    prefix=data.tg1_vrf1_router_v6_prefix_list[port_i], 
                                    prefix_from=data.tg1_router_v6_prefix_length, as_path='as_seq:1', active='1', ip_version='6')
        tg1_port_vrf_route_v6_list[0] = route1_v6

        #create vrf2 route
        vrf_id = 1
        route2 = tg.tg_emulation_bgp_route_config(handle=port_handle['bgp_v4'][vrf_id]['conf']['handle'], mode='add', 
                                    num_routes=data.tg1_vrf2_router_count_list[port_i],
                                    prefix=data.tg1_vrf2_router_prefix_list[port_i],
                                    prefix_from=data.tg1_router_prefix_length, as_path='as_seq:1', active='1')
        tg1_port_vrf_route_list[1] = route2

        route2_v6 = tg.tg_emulation_bgp_route_config(handle=port_handle['bgp_v6'][vrf_id]['conf']['handle'], mode='add', 
                                    num_routes=data.tg1_vrf2_router_v6_count_list[port_i],
                                    prefix=data.tg1_vrf2_router_v6_prefix_list[port_i], 
                                    prefix_from=data.tg1_router_v6_prefix_length, as_path='as_seq:1', active='1', ip_version='6')
        tg1_port_vrf_route_v6_list[1] = route2_v6
        data.tg1_handle[port_i]['route'] = copy.deepcopy(tg1_port_vrf_route_list)
        data.tg1_handle[port_i]['route_v6'] = copy.deepcopy(tg1_port_vrf_route_v6_list)


def tg2_bgp_router_add():

    tg2_port_vrf_route_list=[0,0,0]
    tg2_port_vrf_route_v6_list=[0,0,0]
    for port_i in range(2):
        tg = data.tg_list[port_i+4]
        tg_ph = data.tg_ph_list[port_i+4]
        port_handle = data.tg2_handle[port_i]

        #create vrf1 route
        vrf_id = 0
        route1 = tg.tg_emulation_bgp_route_config(handle=port_handle['bgp_v4'][vrf_id]['conf']['handle'], mode='add', 
                                    num_routes=data.tg2_router_count,prefix=data.tg2_vrf1_router_prefix, 
                                    prefix_from=data.tg2_router_prefix_length, as_path='as_seq:1', active='1')
        tg2_port_vrf_route_list[0] = route1

        route1_v6 = tg.tg_emulation_bgp_route_config(handle=port_handle['bgp_v6'][vrf_id]['conf']['handle'], mode='add', 
                                    num_routes=data.tg2_router_count,
                                    prefix=data.tg2_vrf1_router_v6_prefix, 
                                    prefix_from=data.tg2_router_v6_prefix_length, as_path='as_seq:1', active='1', ip_version='6')
        tg2_port_vrf_route_v6_list[0] = route1_v6

        #create vrf2 route
        vrf_id = 1
        route2 = tg.tg_emulation_bgp_route_config(handle=port_handle['bgp_v4'][vrf_id]['conf']['handle'], mode='add', 
                                    num_routes=data.tg2_router_count,prefix=data.tg2_vrf2_router_prefix, 
                                    prefix_from=data.tg2_router_prefix_length, as_path='as_seq:1', active='1')
        tg2_port_vrf_route_list[1] = route2

        route2_v6 = tg.tg_emulation_bgp_route_config(handle=port_handle['bgp_v6'][vrf_id]['conf']['handle'], mode='add', 
                                    num_routes=data.tg2_router_count,
                                    prefix=data.tg2_vrf1_router_v6_prefix,  
                                    prefix_from=data.tg2_router_v6_prefix_length, as_path='as_seq:1', active='1', ip_version='6')
        tg2_port_vrf_route_v6_list[1] = route2_v6

        data.tg2_handle[port_i]['route'] = copy.deepcopy(tg2_port_vrf_route_list)
        data.tg2_handle[port_i]['route_v6'] = copy.deepcopy(tg2_port_vrf_route_v6_list)

def tg3_bgp_router_add():

    tg3_port_vrf_route_list=[0,0,0]
    for port_i in range(1):
        tg = data.tg_list[port_i+6]
        tg_ph = data.tg_ph_list[port_i+6]
        port_handle = data.tg3_handle[port_i]

        #create vrf1 route
        vrf_id = 0
        route1 = tg.tg_emulation_bgp_route_config(handle=port_handle['bgp_v4'][vrf_id]['conf']['handle'], mode='add', 
                                    num_routes=data.tg3_router_count,prefix=data.tg3_vrf1_router_prefix, 
                                    prefix_from=data.tg3_router_prefix_length, as_path='as_seq:1', active='1')
        tg3_port_vrf_route_list[0] = route1

        #create vrf2 route
        vrf_id = 1
        route2 = tg.tg_emulation_bgp_route_config(handle=port_handle['bgp_v4'][vrf_id]['conf']['handle'], mode='add', 
                                    num_routes=data.tg3_router_count,prefix=data.tg3_vrf2_router_prefix, 
                                    prefix_from=data.tg3_router_prefix_length, as_path='as_seq:1', active='1')
        tg3_port_vrf_route_list[1] = route2

        data.tg3_handle[port_i]['route'] = copy.deepcopy(tg3_port_vrf_route_list)


def vrfs_traffic_add():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    result = 0

    # port 1(TG1_1)<===>port 5(TG2_1) vrf503
    vrf_id = 0
    src_handle = data.tg1_handle[0]['route'][vrf_id]
    tg = data.tg_list[0]
    tg_ph = data.tg_ph_list[0]
    tg_ph_2 = data.tg_ph_list[4]
    dst_handle_list = [data.tg2_handle[0]['route'][vrf_id]['handle'], data.tg2_handle[1]['route'][vrf_id]['handle']]
    stream = tg.tg_traffic_config(port_handle=tg_ph, port_handle2=tg_ph_2, emulation_src_handle=src_handle['handle'],
                emulation_dst_handle=dst_handle_list, circuit_endpoint_type='ipv4',mode='create',
                transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent=data.traffic_rate_precent)
    data.streams['port1_to_port5_vrf_503'] = stream['stream_id']

    tg = data.tg_list[4]
    vrf_id = 0
    src_handle = data.tg2_handle[0]['route'][vrf_id]
    dst_handle_list = [data.tg1_handle[0]['route'][vrf_id]['handle'], data.tg1_handle[1]['route'][vrf_id]['handle']]
    stream = tg.tg_traffic_config(port_handle=tg_ph_2, port_handle2=tg_ph, emulation_src_handle=src_handle['handle'],
                    emulation_dst_handle=dst_handle_list, circuit_endpoint_type='ipv4',mode='create',
                    transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent=data.traffic_rate_precent)
    data.streams['port5_to_port1_vrf_503'] = stream['stream_id']


     # port 2(TG1_2)<===>port 6(TG2_2) vrf504
    vrf_id = 1
    src_handle = data.tg1_handle[1]['route'][vrf_id]
    dst_handle_list = [data.tg2_handle[0]['route'][vrf_id]['handle'], data.tg2_handle[1]['route'][vrf_id]['handle']]
    tg = data.tg_list[1]
    tg_ph = data.tg_ph_list[1]
    tg_ph_2 = data.tg_ph_list[5]
    stream = tg.tg_traffic_config(port_handle=tg_ph, port_handle2=tg_ph_2, emulation_src_handle=src_handle['handle'],
                emulation_dst_handle=dst_handle_list, circuit_endpoint_type='ipv4',mode='create',
                transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent=data.traffic_rate_precent)
    data.streams['port2_to_port6_vrf_504'] = stream['stream_id']

    tg = data.tg_list[5]
    vrf_id = 1
    src_handle = data.tg2_handle[1]['route'][vrf_id]
    dst_handle_list = [data.tg1_handle[0]['route'][vrf_id]['handle'], data.tg1_handle[1]['route'][vrf_id]['handle']]
    stream = tg.tg_traffic_config(port_handle=tg_ph_2, port_handle2=tg_ph, emulation_src_handle=src_handle['handle'],
                    emulation_dst_handle=dst_handle_list, circuit_endpoint_type='ipv4',mode='create',
                    transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent=data.traffic_rate_precent)
    data.streams['port6_to_port2_vrf_504'] = stream['stream_id']


    #TG1_3 <====> TG 3_1 vrf 501
    vrf_id = 0
    src_handle = data.tg1_handle[2]['route'][vrf_id]
    dst_handle = data.tg3_handle[0]['route'][vrf_id]
    tg = data.tg_list[2]
    tg_ph = data.tg_ph_list[2]
    tg_ph_2 = data.tg_ph_list[6]
    stream = tg.tg_traffic_config(port_handle=tg_ph, port_handle2=tg_ph_2, emulation_src_handle=src_handle['handle'],
                emulation_dst_handle=dst_handle['handle'], circuit_endpoint_type='ipv4',mode='create',
                transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent=data.traffic_rate_precent)
    data.streams['port3_to_port7_vrf_501'] = stream['stream_id']

    tg = data.tg_list[5]
    vrf_id = 0
    src_handle = data.tg3_handle[0]['route'][vrf_id]
    dst_handle_list = [data.tg1_handle[2]['route'][vrf_id]['handle'], data.tg1_handle[3]['route'][vrf_id]['handle']]
    stream = tg.tg_traffic_config(port_handle=tg_ph_2, port_handle2=tg_ph, emulation_src_handle=src_handle['handle'],
                    emulation_dst_handle=dst_handle_list, circuit_endpoint_type='ipv4',mode='create',
                    transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent=data.traffic_rate_precent)
    data.streams['port7_to_port3_vrf_501'] = stream['stream_id']

    #TG1_4 <====> TG 3_1 vrf 502
    vrf_id = 1
    src_handle = data.tg1_handle[3]['route'][vrf_id]
    dst_handle = data.tg3_handle[0]['route'][vrf_id]
    tg = data.tg_list[3]
    tg_ph = data.tg_ph_list[3]
    tg_ph_2 = data.tg_ph_list[6]
    stream = tg.tg_traffic_config(port_handle=tg_ph, port_handle2=tg_ph_2, emulation_src_handle=src_handle['handle'],
                emulation_dst_handle=dst_handle['handle'], circuit_endpoint_type='ipv4',mode='create',
                transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent=data.traffic_rate_precent)
    data.streams['port4_to_port7_vrf_502'] = stream['stream_id']

    tg = data.tg_list[5]
    vrf_id = 1
    src_handle = data.tg3_handle[0]['route'][vrf_id]
    dst_handle_list = [data.tg1_handle[2]['route'][vrf_id]['handle'], data.tg1_handle[3]['route'][vrf_id]['handle']]
    stream = tg.tg_traffic_config(port_handle=tg_ph_2, port_handle2=tg_ph, emulation_src_handle=src_handle['handle'],
                    emulation_dst_handle=dst_handle_list, circuit_endpoint_type='ipv4',mode='create',
                    transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent=data.traffic_rate_precent)
    data.streams['port7_to_port4_vrf_502'] = stream['stream_id']


def l3_base_unconfig():

    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]

    st.log("remove l3 base config.")
    ipfeature.clear_ip_configuration(st.get_dut_names())
    vapi.clear_vlan_configuration(st.get_dut_names())
    #command = "show arp"
    #st.show(dut1, command)

@pytest.mark.community
@pytest.mark.community_pass
def test_base_config_srvpn_locator_01():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    # tg = data.tg_list[0]
    # tg_ph = data.tg_ph_list[0]
    # tg_ph_2 = data.tg_ph_list[4]
    result = 0
    
    st.banner("test_base_config_srvpn_locator_01 begin")
    
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
    
    expected_op_val = data.mysid_opcode['Vrf1']+'|'+'end-dt46'+'|'+'Vrf1'
    configdb_checkarray(dut1, mysid_configdb_key, "opcode@", expected_op_val, expect = True, checkpoint = checkpoint_msg)
    expected_op_val = data.mysid_opcode['PUBLIC-TC11']+'|'+'end-dt46'+'|'+'PUBLIC-TC11'
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
    bgp_as = 100
    st.config(dut1, 'vtysh -c "config t" -c "vrf {}" -c "ip route 192.100.1.0/24 blackhole"'.format(vrf))
    st.config(dut1, 'vtysh -c "config t" -c "router bgp {} vrf {}" -c "address-family ipv4 unicast" -c "network 192.100.1.0/24"'.format(bgp_as, vrf))

    cmd = "cli -c 'no page' -c 'show bgp ipv4 vpn'"
    records = st.show(dut1, cmd)

    expected_vpn = {
        'ip_address':'192.100.1.0/24',
        'sid':'fd00:201:201:fff1:11::',
        'label':'3',
        'status_code':'*>',
        'rd':'2:2'
    }

    if not records or len(records)==0:
        st.report_fail("step 4 test_base_config_srvpn_locator_01_failed")
    
    check = False
    for re in records:
        match_cnt = 0
        for it in ['ip_address', 'sid', 'label', 'status_code', 'rd']:
            if re[it] ==  expected_vpn[it]:
                match_cnt +=1

        if match_cnt == 5:
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
    cmd = "cli -c 'no page' -c 'show bgp ipv4 vpn'"
    records = st.show(dut1, cmd)

    expected_vpn = {
        'ip_address':'192.100.1.0/24',
        'label':'3',
        'status_code':'*>',
        'rd':'2:2'
    }

    if not records or len(records)==0:
        st.log ("step 7 test_base_config_srvpn_locator_01_failed")
        st.report_fail("step 7 test_base_config_srvpn_locator_01_failed")

    
    if 'sid' in records:
        st.log ("step 7 test_base_config_srvpn_locator_01_failed")
        st.report_fail("step 7 test_base_config_srvpn_locator_01_failed")

    check = False
    
    for re in records:
        match_cnt = 0
        for it in ['ip_address', 'label', 'status_code', 'rd']:
            if re[it] ==  expected_vpn[it]:
                match_cnt +=1

        if match_cnt == 5:
            check = True
            break
    
    if not check:
        st.log(records)
        # TODO
        #st.report_fail("step 7 test_base_config_srvpn_locator_01_failed")
        st.log ("step 7 test_base_config_srvpn_locator_01_failed")

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
    st.config(dut1, 'cli -c "config t" -c "router bgp {} vrf {}" -c "srv6-locator {}"'.format(bgp_as, vrf_name, locator_name))
    st.wait(10)
    # records = st.show(dut1, "show bgp ipv4 vpn", type='alicli')
    cmd = "cli -c 'no page' -c 'show bgp ipv4 vpn'"
    records = st.show(dut1, cmd)

    expected_vpn = {
        'ip_address':'192.100.1.0/24',
        'sid':'fd00:201:201:fff1:11::',
        'label':'3',
        'status_code':'*>',
        'rd':'2:2',
        'un':'0.0.0.0'
    }

    if not records or len(records)==0:
        st.report_fail("step 8 test_base_config_srvpn_locator_01_failed")
    
    check = False
    for re in records:
        match_cnt = 0
        for it in ['ip_address', 'sid', 'label', 'status_code', 'rd']:
            if re[it] ==  expected_vpn[it]:
                match_cnt +=1

        if match_cnt == 5:
            check = True
            break
    
    if not check:
        st.log(records)
        st.report_fail("step 8 test_base_config_srvpn_locator_01_failed")

# check  remote router 
    # records = st.show(dut2, "show bgp ipv4 vpn", type='alicli')
    cmd = "cli -c 'no page' -c 'show bgp ipv4 vpn'"
    records = st.show(dut1, cmd)

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
        'ip_address':'192.100.1.0/24',
        'sid':'fd00:201:201:fff1:11::',
        'label':'3',
        'status_code':'*>i',
        'rd':'2:2',
        'un':'0.0.0.0'
    }

    if not records or len(records)==0:
        st.report_fail("step 8 remote test_base_config_srvpn_locator_01_failed")
    
    check = False
    for re in records:
        match_cnt = 0
        for it in ['ip_address', 'sid', 'label', 'status_code', 'rd']:
            if re[it] ==  expected_vpn[it]:
                match_cnt +=1

        if match_cnt == 5:
            check = True
            break
    
    if not check:
        st.log(records)
        st.report_fail("step 8 remote test_base_config_srvpn_locator_01_failed")

    st.report_pass("test_case_passed")


## 2k locator , base traffic and route learning
@pytest.mark.community
@pytest.mark.community_pass
def test_base_config_srvpn_2kl_traffic_and_route_02():
    # data.srv6['tg_dut2_eth109']=tg_dut2_eth109
    # data.srv6['tg_dut2_eth110']=tg_dut2_eth110
    # data.srv6['tg_ph_dut2_eth109']=tg_ph_dut2_eth109
    # data.srv6['tg_ph_dut2_eth110']=tg_ph_dut2_eth110
    # data.srv6['bgpv4_handle_dut2_eth109']=tg_result1['ipv4_handle']
    # data.srv6['bgpv4_handle_dut2_eth110']=tg_result2['ipv4_handle']
    # data.srv6['tg_dut1_eth109']=tg_dut1_eth109
    # data.srv6['tg_dut1_eth110']=tg_dut1_eth110
    # data.srv6['tg_ph_dut1_eth109']=tg_ph_dut1_eth109
    # data.srv6['tg_ph_dut1_eth110']=tg_ph_dut1_eth110
    # data.srv6['bgpv4_handle_dut1_eth109']=tg_result1['ipv4_handle']
    # data.srv6['bgpv4_handle_dut1_eth110']=tg_result2['ipv4_handle']

    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0] #179
    dut2 = data.my_dut_list[1] #178
    st.banner("test_base_config_srvpn_2kl_traffic_and_route_02 begin")

    # 179 load 2k locator config
    curr_path = os.getcwd()
    json_file_dut = curr_path+"/routing/SRv6/2k_locators.json"
    st.apply_files(dut1, [json_file_dut])
    reboot.config_save_reboot(dut1)
    st.banner("2k locators Loaded completed")
    

    def_v4_route_count_d1 = asicapi.get_ipv4_route_count(dut1)
    def_v6_route_count_d1 = asicapi.get_ipv6_route_count(dut1)
    def_v4_route_count_d2 = asicapi.get_ipv4_route_count(dut2)
    def_v6_route_count_d2 = asicapi.get_ipv6_route_count(dut2)

    # check redis db , check route 

    # Time taken for route installation
    # Taking the start time timestamp
    tg1 = data.srv6['tg_dut1_eth109']
    tg2 = data.srv6['tg_dut1_eth110']
    ingress_bgp_rtr1 = data.srv6['tg_dut1_eth109_bgp_v4_vrf']
    ingress_bgp_rtr2 = data.srv6['tg_dut1_eth110_bgp_v4_vrf']

    # st.banner("Time taken for intsalling {} v4 routes ".format('50w') +str(time_in_secs.seconds))
    # st.banner("Measuring time taken for route withdraw of {} ipv4 routes on HWSKU {}".format(data.test_bgp_route_count,hwsku_under_test))


    start_time = datetime.datetime.now()

    # Starting the BGP router on TG.

    # Withdraw the routes.
    ctrl1=tg1.tg_bgp_routes_control(handle=ingress_bgp_rtr1['conf']['handle'], route_handle=ingress_bgp_rtr1['route'][0]['handle'], mode='withdraw')
    st.log("TR_CTRL: "+str(ctrl1))

    # config ixia route and check route learning performance
    if not check_bcmcmd_route_count(dut1, 100, "ipv4", def_v4_route_count_d1, 0):
        #st.report_fail("route_table_not_cleared_by_withdraw_from_tg")
        st.log("route_table_not_cleared_by_withdraw_from_tg")

    # config ixia route and check route learning performance
    if not check_bcmcmd_route_count(dut2, 100, "ipv4", def_v4_route_count_d2, 0):
        #st.report_fail("route_table_not_cleared_by_withdraw_from_tg")
        st.log("route_table_not_cleared_by_withdraw_from_tg")

    count = verify_bgp_route_count(dut1, family='ipv4', neighbor=data.neigh_ip_addr, state='Established')
    st.log("Route count: "+str(count))
    if int(count) != 0:
        st.report_fail("route_table_not_cleared_by_withdraw_from_tg")
  
    end_time = datetime.datetime.now()

    st.log("Start Time: {}".format(start_time))
    st.log("End Time: {}".format(end_time))
    time_in_secs = end_time - start_time

     
    # traffic test
    tr1 = tg1.tg_traffic_config(port_handle=data.srv6['tg_ph_dut2_eth109'],
        emulation_src_handle=data.srv6['interface_dut2_eth109']['handle'],
        emulation_dst_handle=ingress_bgp_rtr2['route'][0]['handle'],
        circuit_endpoint_type='ipv4',mode='create',
        transmit_mode='continuous', length_mode='fixed',
        rate_percent=data.traffic_rate_precent,
        enable_stream_only_gen='0')

    # Starting the TG traffic after clearing the DUT counters
    papi.clear_interface_counters(dut1)
    tg1.tg_traffic_control(action="run",handle=tr1['stream_id'])    


## 100 vrf test
@pytest.mark.community
@pytest.mark.community_pass
def test_base_config_srvpn_multi_vrf_03():
    
    # ixia config 100 subinterface 
    
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0] #179
    dut2 = data.my_dut_list[1] #178
    st.banner("test_base_config_srvpn_2kl_traffic_and_route_02 begin")

    # 179 load 2k locator config
    curr_path = os.getcwd()

    json_file_dut1_multi_vrf = curr_path+"/routing/SRv6/dut1_multi_vrf_full.json"
    st.apply_files(dut1, [json_file_dut1_multi_vrf])

    json_file_dut2_multi_vrf = curr_path+"/routing/SRv6/dut2_multi_vrf_full.json"
    st.apply_files(dut1, [json_file_dut2_multi_vrf])
    
    st.wait(10)
    
    reboot.config_reload_reboot(dut1, "/etc/spytest/SRv6/dut1_multi_vrf_full.json")
    reboot.config_reload_reboot(dut2, "/etc/spytest/SRv6/dut2_multi_vrf_full.json")

    st.banner("multi vrf config loaded completed")
     
    # load ixia config
    # TODO

    # check vpn route learn 50w
    ret = check_vpn_route_nums(dut2, 500000, 0)
    if not ret:
        st.report_fail("check_vpn_route_nums test_base_config_srvpn_multi_vrf_03")
        
    # check vrf vpn route 
    # one vrf learn 5000 ， default learn 500000w
    # random check 10 vrf
    def get_check_vrf_list():
        vrf_array = []
        ra = get_random_array(0, 99, 10)
        for idx in ra:
            vrf_array.append(data.mysid_opcode.keys()[idx])
        return vrf_array
        
    vrf_array = get_check_vrf_list()
    
    for chcek_vrf in vrf_array:
        ret = check_vrf_route_nums(dut2, chcek_vrf, 5000, 1)
        if not ret:
            st.report_fail("check_vrf_route_nums {} test_base_config_srvpn_multi_vrf_03".format(chcek_vrf))

    # check traffic


    # change vrf import rt 


    # check vrf route learn

    # check vrf traffic 


    # ecmp check

    # ecmp stability test

    # modify ingress srv6 locator  
     
    st.report_fail("test_base_config_srvpn_multi_vrf_03")

