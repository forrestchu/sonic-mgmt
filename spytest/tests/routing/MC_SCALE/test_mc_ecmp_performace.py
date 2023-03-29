# -*- coding:utf-8 -*-
import os
import copy
import datetime
import time
import pytest
from collections import OrderedDict
from utilities import parallel

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
import mc_lib as loc_lib
from mc_vars import * #all the variables used for vrf testcase
from mc_vars import data
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
    tg1, tg_ph_1 = tgapi.get_handle_byname("T1D1P1")
    tg2, tg_ph_2 = tgapi.get_handle_byname("T1D1P2")
    tg3, tg_ph_3 = tgapi.get_handle_byname("T1D1P3")
    tg4, tg_ph_4 = tgapi.get_handle_byname("T1D1P4")
    tg5, tg_ph_5 = tgapi.get_handle_byname("T1D2P1")
    tg6, tg_ph_6 = tgapi.get_handle_byname("T1D2P2")
    tg_list = [tg1, tg2, tg3, tg4, tg5, tg6]
    tg_ph_list = [tg_ph_1, tg_ph_2, tg_ph_3, tg_ph_4, tg_ph_5, tg_ph_6]
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

# case: https://yuque.antfin.com/aone604087/rk3msk/rpdmlr#hAljL 
# TODO
#
#
@pytest.fixture(scope="module", autouse=True)
def mc_ecmp_performace_module_hooks(request):
    #add things at the start of this module
    global vars
    vars = st.ensure_min_topology("D1D2:4","D1T1:4","D2T1:2")
    (data.tg_list, data.tg_ph_list) = get_handles()
    for i in range(6):
        data.tg_list[i].tg_traffic_control(action='reset',port_handle=data.tg_ph_list[i])
    duts_base_config()
    tg1_base_config()
    tg2_base_config()
    data.tg1_vrf1_router_count_list = ["200000","200000","50000","50000"]
    tg1_bgp_router_add()
    tg2_bgp_router_add()
    data.tg_list[0].tg_test_control(action='stop_all_protocols')
    st.wait(20)
    data.tg_list[0].tg_test_control(action='start_all_protocols')
    st.wait(50)
    vrfs_traffic_add()
    vrfs_traffic_v6_add()
    get_dut_ip()

    yield

    l3_base_unconfig()

@pytest.fixture(scope="function", autouse=True)
def mc_ecmp_performace_func_hooks(request):
    # add things at the start every test case
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]

    yield
    #st.show(dut1,"show vrf")
    #st.show(dut2,"show vrf")
    #check_swichchip_route_count(dut2, 100, "ipv4", 0, 11000, add=0)

def duts_base_config():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    curr_path = os.getcwd()
    json_file_dut1 = curr_path+"/routing/MC_SCALE/dut1_bgp_performance.json"
    json_file_dut2 = curr_path+"/routing/MC_SCALE/dut2_bgp_performance.json"
    st.apply_files(dut1, [json_file_dut1])
    st.apply_files(dut2, [json_file_dut2])

    reboot.config_save_reboot(data.my_dut_list)
    #dict1 = {'command': "copy run start", 'type':'alicli','skip_error_check':True}
    #dict2 = {'command': "copy run start", 'type':'alicli','skip_error_check':True}
    #parallel.exec_parallel(True, [dut1, dut2], st.config, [dict1, dict2])

    #dict1 = {}
    #parallel.exec_parallel(True, [dut1, dut2], arp_api.show_arp, [dict1, dict1])
    #parallel.exec_parallel(True, [dut1, dut2], st.reboot, [dict1, dict1])


def tg1_base_config():
    tg1_p_handle = dict()

    #init DUT1====TG
    for i in range(2):
        intf_handle_list = []
        bgp_v4_handle_list = [0]
        bgp_v6_handle_list = [0]
        bfd_v4_handle_list = [0]
        bfd_v6_handle_list = [0]
        tg = data.tg_list[i]
        tg_ph = data.tg_ph_list[i]
        # create 3 devicegroup per ixia port: 1.vrf503; 2.vrf504; 3.vrf_bfd_scale
        h1_1=tg.tg_interface_config(port_handle=tg_ph, mode='config', intf_ip_addr=data.tg1_vrf1_ip_addr[i], 
                                gateway=data.dut1_vrf1_ip_addr[i], vlan='1', vlan_id=data.dut1_vrf1_id[i],
                                ipv6_intf_addr=data.tg1_vrf1_ipv6_addr[i], ipv6_gateway=data.dut1_vrf1_ipv6_addr[i],ipv6_gateway_step='0::0',
                                intf_ip_addr_step='0.0.0.1', ipv6_intf_addr_step = '::1', arp_send_req='1')
        intf_handle_list.insert(0,h1_1)

        # Configuring the BGP router in vrf1
        conf_var = {'mode'                 : 'enable',
                    'active_connect_enable' : '1',
                    'enable_4_byte_as'      : '1',
                    'local_as'              : data.tg1_vrf_bgp_as,
                    'remote_as'             : data.dut1_vrf_bgp_as,
                    'remote_ip_addr'        : data.dut1_vrf1_ip_addr[i],
                    'bfd_registration'      : '1',
                    'bfd_registration_mode' : 'single_hop'
                    }
        route_var = {'mode':'add', 
                    'num_routes': data.tg1_vrf1_router_count_list[i], 
                    'prefix': data.tg1_vrf1_router_prefix_list[i], 
                    'as_path':'as_seq:1'
                    }
        ctrl_start = { 'mode' : 'start'}
        ctrl_stop = { 'mode' : 'stop'}

        bgp_v4_vrf1 = tgapi.tg_bgp_config(tg = tg,
            handle    = h1_1['ipv4_handle'],
            conf_var  = conf_var,
            #route_var = route_var,
            ctrl_var  = ctrl_start)

        #save bgp handle 
        bgp_v4_handle_list.insert(0,bgp_v4_vrf1)

        st.log("create ipv4 bfd for each vrf")
        bfd_v4_handle = tg.tg_emulation_bfd_config(handle = intf_handle_list[0]['ipv4_handle'],
            min_rx_interval                = data.dut_bfd_timer,
            mode                           = "create",
            detect_multiplier              = "3",
            tx_interval                    = data.dut_bfd_timer,
            interface_active               = "1",
            router_active                  = "1",
            ip_version                     = "4",
            aggregate_bfd_session          = "1")
        bfd_v4_handle_list[0] = bfd_v4_handle
 
        conf_var = {'mode'                 : 'enable',
                'active_connect_enable' : '1',
                'enable_4_byte_as'      : '1',
                'local_as'              : data.tg1_vrf_bgp_as,
                'remote_as'             : data.dut1_vrf_bgp_as,
                'remote_ipv6_addr'      : data.dut1_vrf1_ipv6_addr[i],
                'ip_version'            : '6',
                'bfd_registration'      : '1',
                'bfd_registration_mode' : 'single_hop'
                }
        route_var['prefix'] = data.tg1_vrf1_router_v6_prefix_list[i]
        
        bgp_v6_vrf1 = tgapi.tg_bgp_config(tg = tg,
            handle    = h1_1['ipv6_handle'],
            conf_var  = conf_var,
            #route_var = route_var,
            ctrl_var  = ctrl_start)
        bgp_v6_handle_list[0] = bgp_v6_vrf1

        st.log("create ipv6 bfd for each vrf")
        bfd_v6_handle = tg.tg_emulation_bfd_config(handle = intf_handle_list[0]['ipv6_handle'],
            min_rx_interval                = data.dut_bfd_timer,
            mode                           = "create",
            detect_multiplier              = "3",
            tx_interval                    = data.dut_bfd_timer,
            interface_active               = "1",
            router_active                  = "1",
            ip_version                     = "6",
            aggregate_bfd_session          = "1")
        bfd_v6_handle_list[0] = bfd_v6_handle

        #save handle per port
        tg1_p_handle['intf'] = intf_handle_list
        tg1_p_handle['bgp_v4'] = bgp_v4_handle_list
        tg1_p_handle['bgp_v6'] = bgp_v6_handle_list
        tg1_p_handle['bfd_v4'] = bfd_v4_handle_list
        tg1_p_handle['bfd_v6'] = bfd_v6_handle_list
        #save handle per dut
        #data.tg1_handle.insert(i, tg1_p_handle)
        data.tg1_handle[i]  = copy.deepcopy(tg1_p_handle)

    
def tg1_bgp_router_add():

    #init DUT1====TG
    tg1_port_vrf_route_list=[0]
    tg1_port_vrf_route_v6_list=[0]
    for port_i in range(2):
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

        data.tg1_handle[port_i]['route'] = copy.deepcopy(tg1_port_vrf_route_list)
        data.tg1_handle[port_i]['route_v6'] = copy.deepcopy(tg1_port_vrf_route_v6_list)

def tg2_bgp_router_add():

    tg2_port_vrf_route_list=[0,0,0]
    tg2_port_vrf_route_v6_list=[0]
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

        data.tg2_handle[port_i]['route'] = copy.deepcopy(tg2_port_vrf_route_list)
        data.tg2_handle[port_i]['route_v6'] = copy.deepcopy(tg2_port_vrf_route_v6_list)

def tg2_base_config():
    tg2_p_handle = dict()
    #init DUT2====TG
    for i in range(2):
        intf_handle_list = [0,0,0]
        bgp_v4_handle_list = [0,0,0]
        bgp_v6_handle_list = [0,0,0]
        bfd_v4_handle_list = [0,0,0]
        bfd_v6_handle_list = [0,0,0]
        tg = data.tg_list[i+4]
        tg_ph = data.tg_ph_list[i+4]

        # create 3 devicegroup per ixia port: 1.vrf503; 2.vrf504; 3.vrf_bfd_scale
        h1_1=tg.tg_interface_config(port_handle=tg_ph, mode='config', intf_ip_addr=data.tg2_vrf1_ip_addr[i], 
                                gateway=data.dut2_vrf1_ip_addr[i], vlan='1', vlan_id=data.dut1_vrf1_id[i],
                                ipv6_intf_addr=data.tg2_vrf1_ipv6_addr[i],ipv6_gateway=data.dut2_vrf1_ipv6_addr[i],ipv6_gateway_step='0::0',
                                intf_ip_addr_step='0.0.0.1', ipv6_intf_addr_step = '::1', arp_send_req='1')
        intf_handle_list[0] = h1_1

        # Configuring the BGP router in vrf1
        conf_var = {'mode'                 : 'enable',
                    'active_connect_enable' : '1',
                    'enable_4_byte_as'      : '1',
                    'local_as'              : data.tg2_vrf_bgp_as,
                    'remote_as'             : data.dut2_vrf_bgp_as,
                    'remote_ip_addr'        : data.dut2_vrf1_ip_addr[i],
                    'bfd_registration'      : '1',
                    'bfd_registration_mode' : 'single_hop'
                    }

        route_var = {'mode':'add', 
                    'num_routes': data.tg2_router_count, 
                    'prefix': data.tg2_vrf1_router_prefix, 
                    'as_path':'as_seq:1'
                    }
        ctrl_start = { 'mode' : 'start'}
        ctrl_stop = { 'mode' : 'stop'}

        bgp_v4_vrf1 = tgapi.tg_bgp_config(tg = tg,
            handle    = h1_1['ipv4_handle'],
            conf_var  = conf_var,
            #route_var = route_var,
            ctrl_var  = ctrl_start)

        #save bgp handle 
        bgp_v4_handle_list[0] = bgp_v4_vrf1

        conf_var = {'mode'                 : 'enable',
                'active_connect_enable' : '1',
                'enable_4_byte_as'      : '1',
                'local_as'              : data.tg2_vrf_bgp_as,
                'remote_as'             : data.dut2_vrf_bgp_as,
                'remote_ipv6_addr'      : data.dut2_vrf1_ipv6_addr[i],
                'ip_version'            : '6',
                'bfd_registration'      : '1',
                'bfd_registration_mode' : 'single_hop'
                }
        bgp_v6_vrf1 = tgapi.tg_bgp_config(tg = tg,
            handle    = h1_1['ipv6_handle'],
            conf_var  = conf_var,
            #route_var = route_var,
            ctrl_var  = ctrl_start)
        bgp_v6_handle_list[0] = bgp_v6_vrf1

        st.log("create ipv4 bfd for each vrf")
        for j in range(1):
            bfd_v4_handle = tg.tg_emulation_bfd_config(handle = intf_handle_list[j]['ipv4_handle'],
                min_rx_interval                = data.dut_bfd_timer,
                mode                           = "create",
                detect_multiplier              = "3",
                tx_interval                    = data.dut_bfd_timer,
                interface_active               = "1",
                router_active                  = "1",
                ip_version                     = "4",
                aggregate_bfd_session          = "1")
            bfd_v4_handle_list[j] = bfd_v4_handle
            tg.tg_emulation_bfd_control(handle = bfd_v4_handle['bfd_v4_interface_handle'], mode = "restart")

        st.log("create ipv6 bfd for each vrf")
        for j in range(1):
            bfd_v6_handle = tg.tg_emulation_bfd_config(handle = intf_handle_list[j]['ipv6_handle'],
                min_rx_interval                = data.dut_bfd_timer,
                mode                           = "create",
                detect_multiplier              = "3",
                tx_interval                    = data.dut_bfd_timer,
                interface_active               = "1",
                router_active                  = "1",
                ip_version                     = "6",
                aggregate_bfd_session          = "1")
            bfd_v6_handle_list[j] = bfd_v6_handle
            tg.tg_emulation_bfd_control(handle = bfd_v6_handle['bfd_v6_interface_handle'], mode = "restart")

        #save handle per port
        tg2_p_handle['intf'] = intf_handle_list
        tg2_p_handle['bgp_v4'] = bgp_v4_handle_list
        tg2_p_handle['bgp_v6'] = bgp_v6_handle_list
        tg2_p_handle['bfd_v4'] = bfd_v4_handle_list
        tg2_p_handle['bfd_v6'] = bfd_v6_handle_list
        #save handle per dut
        #data.tg1_handle.insert(i, tg1_p_handle)
        data.tg2_handle[i]  = copy.deepcopy(tg2_p_handle)

def vrfs_traffic_add():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    result = 0
    ecmp_member_Gbps = 33

    # port 1(TG1_1)<===>port 5(TG2_1) vrf503
    vrf_id = 0
    tg = data.tg_list[0]
    tg_ph = data.tg_ph_list[0]
    tg_ph_2 = data.tg_ph_list[4]
    src_handle = data.tg2_handle[0]['route'][vrf_id]
    dst_handle_list = [data.tg1_handle[0]['route'][vrf_id]['handle'], data.tg1_handle[1]['route'][vrf_id]['handle']]
    stream = tg.tg_traffic_config(port_handle=tg_ph_2, port_handle2=tg_ph, emulation_src_handle=src_handle['handle'],
                    emulation_dst_handle=dst_handle_list, circuit_endpoint_type='ipv4',mode='create',
                    transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent='20')
    data.streams['port5_to_port1_vrf_503'] = stream['stream_id']

def vrfs_traffic_v6_add():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    result = 0

    # port 1(TG1_1)<===>port 5(TG2_1) vrf503
    vrf_id = 0
    tg = data.tg_list[0]
    tg_ph = data.tg_ph_list[0]
    tg_ph_2 = data.tg_ph_list[4]
    src_handle = data.tg2_handle[0]['route_v6'][vrf_id]
    dst_handle_list = [data.tg1_handle[0]['route_v6'][vrf_id]['handle'], data.tg1_handle[1]['route_v6'][vrf_id]['handle']]
    stream = tg.tg_traffic_config(port_handle=tg_ph_2, port_handle2=tg_ph, emulation_src_handle=src_handle['handle'],
                    emulation_dst_handle=dst_handle_list, circuit_endpoint_type='ipv6',mode='create',
                    transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent='20')
    data.streams['port5_to_port1_vrf_503_v6'] = stream['stream_id']


def l3_base_unconfig():

    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]

    st.log("remove l3 base config.")
    #ipfeature.clear_ip_configuration(st.get_dut_names())
    #vapi.clear_vlan_configuration(st.get_dut_names())

def check_swichchip_route_count(dut, loopCnt, ipType, defcount, expcount, add=1):
    flag = 0
    iter = 1
    while iter <= loopCnt:
        if ipType == "ipv4":
            curr_count = asicapi.get_ipv4_route_count(dut)
        elif ipType == "ipv6":
            curr_count = asicapi.get_ipv6_route_count(dut)

        route_cnt = int(curr_count) - int(defcount)

        st.log("Learnt route count after iteration {} : {}".format(iter,route_cnt))
        if add == 1:
            if int(route_cnt) > int(expcount):
                flag = 1
                break
        else:
            if int(route_cnt) < int(expcount):
                flag = 1
                break
        iter = iter+1
        time.sleep(1)

    if flag:
        return True
    else:
        return False

#case: https://yuque.antfin.com/aone604087/rk3msk/rpdmlr#hAljL 
# 1. section4 BGP单邻居路由学习性能 
# 2. section8 BGP单路径切换收敛
@pytest.mark.community
@pytest.mark.community_pass
def test_bgp_no_ecmp_switch():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    port_list = []
    test_vrf = data.dut_traffic_vrf_name['503']
    traffic_vrf_503_list = [data.streams['port5_to_port1_vrf_503_v6'], data.streams['port5_to_port1_vrf_503']]
    result = 0
    tg = data.tg_list[0]

    for i in range(2):
        cmd = "interface {}\n shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)

    for port_i in range(2):
        port_list.append(data.ecmp_503_504_dut1_dut2_portlist[port_i][8:])

    ecmp_member_ip_list_1 = []
    for ip in data.dut2_all_ip_addr:
        if ip['interface'].split('.')[0][3:] in port_list :
            ecmp_member_ip_list_1.append(ip)
    
    ecmp_member_ip_list_2 = []
    for ip in data.dut1_all_ip_addr:
        if ip['interface'].split('.')[0][3:] in port_list :
            ecmp_member_ip_list_2.append(ip)
    
    dict1 = {'local_as_id': data.dut1_vrf_bgp_as, 'nbr_as_id':data.dut2_vrf_bgp_as,'vrf':test_vrf,'ip_intf_list':ecmp_member_ip_list_1,'ecmp_member_num':1,'group_name':"MC-Aliyun-public"}
    dict2 = {'local_as_id': data.dut2_vrf_bgp_as, 'nbr_as_id':data.dut1_vrf_bgp_as,'vrf':test_vrf,'ip_intf_list':ecmp_member_ip_list_2,'ecmp_member_num':1,'group_name':"MC-Aliyun-public"}
    parallel.exec_parallel(True, [dut1, dut2], loc_lib.dut_load_bgp_ecmp_member, [dict1, dict2])

    st.wait(10)
    cmd = "cli -c 'no page' -c 'show ip bgp vrf {} summary'".format(test_vrf)
    st.show(dut1,cmd,skip_tmpl=True)
    st.show(dut2,cmd,skip_tmpl=True)

    for port_i in range(1,2):
        port_list.append(data.ecmp_503_504_dut1_dut2_portlist[port_i][8:])
    
    dict1 = {'local_as_id': data.dut1_vrf_bgp_as,'vrf':test_vrf,'max_paths_num':'1'}
    dict2 = {'local_as_id': data.dut2_vrf_bgp_as,'vrf':test_vrf,'max_paths_num':'1'}
    parallel.exec_parallel(True, [dut1, dut2], loc_lib.bgp_maximum_paths_set, [dict1, dict2])

    loc_lib.bgp_deny_route_map_apply(dut2, data.dut2_vrf_bgp_as, test_vrf, "MC-Aliyun-public", 'zlydeny')
    
    st.wait(10)

    for i in range(2):
        cmd = "interface {}\n no shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)
    #test 100k learn time
    st.wait(50)

    # Verify the total route count using bcmcmd
    #if not check_swichchip_route_count(dut2, 2, "ipv4", 510, 110000):
    #    st.log("check_swichchip_route_count ipv4 fail")

    #if not check_swichchip_route_count(dut2, 2, "ipv6", 570, 60000):
    #    st.log("check_swichchip_route_count ipv6 fail")
    
    bgp_shutdown_ip_list = []
    st.show(dut1, "show vrf")
    st.show(dut2, "show vrf")

    output=bgp_api.show_bgp_ipv4_summary_vtysh(dut2,vrf=test_vrf)
    for nbr in output:
        if nbr['asn'] == data.dut1_vrf_bgp_as and nbr['neighbor'].split('.')[1] in port_list:
            bgp_shutdown_ip_list.append(nbr['neighbor'])

    output=bgp_api.show_bgp_ipv6_summary_vtysh(dut2,vrf=test_vrf)
    for nbr in output:
        if nbr['asn'] == data.dut1_vrf_bgp_as and nbr['neighbor'].split(':')[2] in port_list:
            bgp_shutdown_ip_list.append(nbr['neighbor'])

    #start shutdown ecmp member
    for i in range(1):
        cmd = "interface {}\n shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)

    st.wait(5)

    for i in range(1):
        cmd = "interface {}\n no shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)
    
    #check traffic
    st.wait(60)

    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)
    tg.tg_traffic_control(action='run', stream_handle=traffic_vrf_503_list)

    st.wait(10)
    tg.tg_traffic_control(action='stop', stream_handle=traffic_vrf_503_list)

    st.banner("check dut2-->dut1 port5_to_port1_vrf_503")
    traffic_details = {
       '1': {
            'tx_ports' : [vars.T1D2P1],
            'tx_obj' : [data.tg_list[4]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D1P1, vars.T1D1P2],
            'rx_obj' : [data.tg_list[0], data.tg_list[1]],
            'stream_list': [[data.streams['port5_to_port1_vrf_503']]]
        },
       '2': {
            'tx_ports' : [vars.T1D2P1],
            'tx_obj' : [data.tg_list[4]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D1P1, vars.T1D1P2],
            'rx_obj' : [data.tg_list[0], data.tg_list[1]],
            'stream_list': [[data.streams['port5_to_port1_vrf_503_v6']]]
        }
    }
    #check ecmp port
    if not tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock', comp_type='packet_count'):
        st.log("validate_tgen_traffic failed")
        result=1

    # Verify the total route count using bcmcmd
    #if not check_swichchip_route_count(dut2, 2, "ipv4", 510, 200000):
    #    st.log("check_swichchip_route_count ipv4 fail")

    #if not check_swichchip_route_count(dut2, 2, "ipv6", 570, 50000):
    #    st.log("check_swichchip_route_count ipv6 fail")

    dict1 = {'local_as_id': data.dut1_vrf_bgp_as, 'nbr_as_id':data.dut2_vrf_bgp_as,'vrf':test_vrf,'ip_intf_list':ecmp_member_ip_list_1,'ecmp_member_num':1,'group_name':"MC-Aliyun-public",'config':'no'}
    dict2 = {'local_as_id': data.dut2_vrf_bgp_as, 'nbr_as_id':data.dut1_vrf_bgp_as,'vrf':test_vrf,'ip_intf_list':ecmp_member_ip_list_2,'ecmp_member_num':1,'group_name':"MC-Aliyun-public",'config':'no'}
    parallel.exec_parallel(True, [dut1, dut2], loc_lib.dut_load_bgp_ecmp_member, [dict1, dict2])

    dict1 = {'local_as_id': data.dut1_vrf_bgp_as,'vrf':test_vrf,'max_paths_num':'128'}
    dict2 = {'local_as_id': data.dut2_vrf_bgp_as,'vrf':test_vrf,'max_paths_num':'128'}
    parallel.exec_parallel(True, [dut1, dut2], loc_lib.bgp_maximum_paths_set, [dict1, dict2])

    if result == 0:
        st.report_pass("test_case_passed")
    else:
        cmd = "show ip bgp vrf all summary"
        st.show(dut1,cmd,type='vtysh')
        st.show(dut2,cmd,type='vtysh')
        st.report_fail("traffic_verification_failed")

#case: https://yuque.antfin.com/aone604087/rk3msk/rpdmlr#hAljL 
# 1. section5 BGP 64邻居路由学习性能
# 2. section9 BGP ECMP成员切换收敛
@pytest.mark.community
@pytest.mark.community_pass
def test_bgp_64_ecmp_member():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    port_list = []
    test_vrf = data.dut_traffic_vrf_name['503']

    for i in range(len(data.ecmp_503_504_dut1_dut2_portlist)):
        cmd = "interface {}\n shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)

    for port_i in range(1,len(data.ecmp_503_504_dut1_dut2_portlist)):
        port_list.append(data.ecmp_503_504_dut1_dut2_portlist[port_i][8:])

    # need add port eth12.503 sub intf to test_vrf ********
    ecmp_member_ip_list_1 = []
    for ip in data.dut2_all_ip_addr:
        if ip['interface'].split('.')[0][3:] in port_list :
            ecmp_member_ip_list_1.append(ip)
    
    ecmp_member_ip_list_2 = []
    for ip in data.dut1_all_ip_addr:
        if ip['interface'].split('.')[0][3:] in port_list :
            ecmp_member_ip_list_2.append(ip)

    dict1 = {'local_as_id': data.dut1_vrf_bgp_as, 'nbr_as_id':data.dut2_vrf_bgp_as,'vrf':test_vrf,'ip_intf_list':ecmp_member_ip_list_1,'ecmp_member_num':12,'group_name':"MC-Aliyun-public"}
    dict2 = {'local_as_id': data.dut2_vrf_bgp_as, 'nbr_as_id':data.dut1_vrf_bgp_as,'vrf':test_vrf,'ip_intf_list':ecmp_member_ip_list_2,'ecmp_member_num':12,'group_name':"MC-Aliyun-public"}
    parallel.exec_parallel(True, [dut1, dut2], loc_lib.dut_load_bgp_ecmp_member, [dict1, dict2])

    loc_lib.bgp_deny_route_map_apply(dut2, data.dut2_vrf_bgp_as, test_vrf, "MC-Aliyun-public", 'zlydeny')

    for port_i in range(3,len(data.ecmp_503_504_dut1_dut2_portlist)):
        port_list.append(data.ecmp_503_504_dut1_dut2_portlist[port_i][8:])
    
    st.wait(10)

    for i in range(len(data.ecmp_503_504_dut1_dut2_portlist)):
        cmd = "interface {}\n no shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)
    #test 100k learn time
    st.wait(200)

    # Verify the total route count using bcmcmd
    #if not check_swichchip_route_count(dut2, 20, "ipv4", 518, 110000):
    #    st.log("check_swichchip_route_count ipv4 fail")

    #if not check_swichchip_route_count(dut2, 20, "ipv6", 519, 60000):
    #    st.log("check_swichchip_route_count ipv6 fail")
    

    #start shutdown ecmp member
    bgp_shutdown_ip_list = []
    st.show(dut1, "show vrf")
    st.show(dut2, "show vrf")

    bgp_shutdown_nbr = 0
    output=bgp_api.show_bgp_ipv4_summary_vtysh(dut2,vrf=test_vrf)
    for nbr in output:
        if nbr['asn'] == data.dut1_vrf_bgp_as and nbr['neighbor'].split('.')[1] in port_list and bgp_shutdown_nbr < 15:
            bgp_shutdown_ip_list.append(nbr['neighbor'])
            bgp_shutdown_nbr += 1

    bgp_shutdown_nbr = 0
    output=bgp_api.show_bgp_ipv6_summary_vtysh(dut2,vrf=test_vrf)
    for nbr in output:
        if nbr['asn'] == data.dut1_vrf_bgp_as and nbr['neighbor'].split(':')[2] in port_list and bgp_shutdown_nbr < 15:
            bgp_shutdown_ip_list.append(nbr['neighbor'])
            bgp_shutdown_nbr += 1

    command = "router bgp {} vrf {}\n".format(data.dut2_vrf_bgp_as, test_vrf)
    for nbr in bgp_shutdown_ip_list:
        command += "neighbor {} shutdown\n".format(nbr)
    command += "exit\n"
    st.config(dut2, command, skip_error_check=True, type='alicli')

    for i in range(1):
        cmd = "interface {}\n shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)

    command = "router bgp {} vrf {}\n".format(data.dut2_vrf_bgp_as, test_vrf)
    for ip_addr in bgp_shutdown_ip_list:
        command += "no neighbor {} shutdown\n".format(ip_addr)
    command += "exit\n"
    st.config(dut2, command, skip_error_check=True, type='alicli')

    for i in range(1):
        cmd = "interface {}\n no shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)
    
    #check traffic
    st.wait(100)

    # Verify the total route count using bcmcmd
    #if not check_swichchip_route_count(dut2, 5, "ipv4", 517, 200000):
    #    st.log("check_swichchip_route_count ipv4 fail")

    #if not check_swichchip_route_count(dut2, 5, "ipv6", 517, 50000):
    #    st.log("check_swichchip_route_count ipv6 fail")

    dict1 = {'local_as_id': data.dut1_vrf_bgp_as, 'nbr_as_id':data.dut2_vrf_bgp_as,'vrf':test_vrf,'ip_intf_list':ecmp_member_ip_list_1,'ecmp_member_num':12,'group_name':"MC-Aliyun-public",'config':'no'}
    dict2 = {'local_as_id': data.dut2_vrf_bgp_as, 'nbr_as_id':data.dut1_vrf_bgp_as,'vrf':test_vrf,'ip_intf_list':ecmp_member_ip_list_2,'ecmp_member_num':12,'group_name':"MC-Aliyun-public",'config':'no'}
    parallel.exec_parallel(True, [dut1, dut2], loc_lib.dut_load_bgp_ecmp_member, [dict1, dict2])

    st.report_pass("test_case_passed")

#case: https://yuque.antfin.com/aone604087/rk3msk/rpdmlr#hAljL 
# 1. section10 BGP ECMP组切换收敛
@pytest.mark.community
@pytest.mark.community_pass
def test_ecmp_group_switch_test():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    port_list = []
    test_vrf = data.dut_traffic_vrf_name['503']
    traffic_vrf_503_list = [data.streams['port5_to_port1_vrf_503_v6'], data.streams['port5_to_port1_vrf_503']]
    result = 0
    tg = data.tg_list[0]

    dut1_vrf_ip_list_pre = []
    dut1_vrf_ipv6_list_pre = []

    #remove exist neighbor
    output=bgp_api.show_bgp_ipv4_summary_vtysh(dut2,vrf=test_vrf)
    for nbr in output:
        if nbr['asn'] == data.dut1_vrf_bgp_as:
            dut1_vrf_ip_list_pre.append(nbr['neighbor'])

    output=bgp_api.show_bgp_ipv6_summary_vtysh(dut2,vrf=test_vrf)
    for nbr in output:
        if nbr['asn'] == data.dut1_vrf_bgp_as:
            dut1_vrf_ipv6_list_pre.append(nbr['neighbor'])
    #loc_lib.dut_load_bgp_neigbor_to_peer_group(dut2, data.dut2_vrf_bgp_as, data.dut1_vrf_bgp_as, test_vrf, dut1_vrf_ip_list_pre, 
    #                                    dut1_vrf_ipv6_list_pre, group_name="MC-Aliyun-public", config='no')

    for i in range(len(data.ecmp_503_504_dut1_dut2_portlist)):
        cmd = "interface {}\n shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)

    dut2_vrf_ip_list_pre = []
    dut2_vrf_ipv6_list_pre = []
    output=bgp_api.show_bgp_ipv4_summary_vtysh(dut1,vrf=test_vrf)
    for nbr in output:
        if nbr['asn'] == data.dut2_vrf_bgp_as:
            dut2_vrf_ip_list_pre.append(nbr['neighbor'])

    output=bgp_api.show_bgp_ipv6_summary_vtysh(dut1,vrf=test_vrf)
    for nbr in output:
        if nbr['asn'] == data.dut2_vrf_bgp_as:
            dut2_vrf_ipv6_list_pre.append(nbr['neighbor'])
    #loc_lib.dut_load_bgp_neigbor_to_peer_group(dut1, data.dut1_vrf_bgp_as, data.dut2_vrf_bgp_as, test_vrf, dut2_vrf_ip_list_pre, 
    #                                    dut2_vrf_ipv6_list_pre, group_name="MC-Aliyun-public", config='no')

    dict1 = {'local_as_id': data.dut1_vrf_bgp_as, 'nbr_as_id':data.dut2_vrf_bgp_as,'vrf':test_vrf,'vrf_ip_list':dut1_vrf_ip_list_pre,'vrf_ipv6_list':dut1_vrf_ipv6_list_pre,'group_name':"MC-Aliyun-public",'config':'no'}
    dict2 = {'local_as_id': data.dut2_vrf_bgp_as, 'nbr_as_id':data.dut1_vrf_bgp_as,'vrf':test_vrf,'vrf_ip_list':dut2_vrf_ip_list_pre,'vrf_ipv6_list':dut2_vrf_ipv6_list_pre,'group_name':"MC-Aliyun-public",'config':'no'}
    parallel.exec_parallel(True, [dut1, dut2], loc_lib.dut_load_bgp_neigbor_to_peer_group, [dict1, dict2])

    # add work neighbor and protect neighbor
    work_port_list = []
    protect_port_list = []
    for port_i in range(0,3):
        work_port_list.append(data.ecmp_503_504_dut1_dut2_portlist[port_i][8:])

    for port_i in range(3,len(data.ecmp_503_504_dut1_dut2_portlist)):
        protect_port_list.append(data.ecmp_503_504_dut1_dut2_portlist[port_i][8:])

    #dut1 work 
    vrf_ip_list=[]
    vrf_ipv6_list = []
    for port_i in work_port_list:
        ip_num=0
        ipv6_num=0
        for ip in data.dut2_all_ip_addr:
            intf = 'Eth' + port_i +'.'
            if ip['vrf'] == test_vrf and ip['interface'].startswith(intf):
                if ':' not in ip['ip'] and ip_num < 10:
                    vrf_ip_list.append(ip['ip'].split('/')[0])
                    ip_num +=1 
                elif ':' in ip['ip'] and ipv6_num < 10:
                    vrf_ipv6_list.append(ip['ip'].split('/')[0])
                    ipv6_num +=1
    loc_lib.dut_load_bgp_neigbor_to_peer_group(dut1, data.dut1_vrf_bgp_as, data.dut2_vrf_bgp_as, test_vrf, vrf_ip_list, 
                                        vrf_ipv6_list, group_name="MC-Aliyun-working", config='yes')
    #dut1 protect
    vrf_ip_list=[]
    vrf_ipv6_list = []
    for port_i in protect_port_list:
        ip_num=0
        ipv6_num=0
        for ip in data.dut2_all_ip_addr:
            intf = 'Eth' + port_i +'.'
            if ip['vrf'] == test_vrf and ip['interface'].startswith(intf):
                if ':' not in ip['ip'] and ip_num < 10:
                    vrf_ip_list.append(ip['ip'].split('/')[0])
                    ip_num +=1 
                elif ':' in ip['ip'] and ipv6_num < 10:
                    vrf_ipv6_list.append(ip['ip'].split('/')[0])
                    ipv6_num +=1
    loc_lib.dut_load_bgp_neigbor_to_peer_group(dut1, data.dut1_vrf_bgp_as, data.dut2_vrf_bgp_as, test_vrf, vrf_ip_list, 
                                        vrf_ipv6_list, group_name="MC-Aliyun-protect", config='yes')
    #dut2 work
    vrf_ip_list=[]
    vrf_ipv6_list = []
    for port_i in work_port_list:
        ip_num=0
        ipv6_num=0
        for ip in data.dut1_all_ip_addr:
            intf = 'Eth' + port_i +'.'
            if ip['vrf'] == test_vrf and ip['interface'].startswith(intf):
                if ':' not in ip['ip'] and ip_num < 10:
                    vrf_ip_list.append(ip['ip'].split('/')[0])
                    ip_num +=1 
                elif ':' in ip['ip'] and ipv6_num < 10:
                    vrf_ipv6_list.append(ip['ip'].split('/')[0])
                    ipv6_num +=1
    loc_lib.dut_load_bgp_neigbor_to_peer_group(dut2, data.dut2_vrf_bgp_as, data.dut1_vrf_bgp_as, test_vrf, vrf_ip_list, 
                                        vrf_ipv6_list, group_name="MC-Aliyun-working", config='yes')
    #dut2 protect
    vrf_ip_list=[]
    vrf_ipv6_list = []
    for port_i in protect_port_list:
        ip_num=0
        ipv6_num=0
        for ip in data.dut1_all_ip_addr:
            intf = 'Eth' + port_i +'.'
            if ip['vrf'] == test_vrf and ip['interface'].startswith(intf):
                if ':' not in ip['ip'] and ip_num < 10:
                    vrf_ip_list.append(ip['ip'].split('/')[0])
                    ip_num +=1 
                elif ':' in ip['ip'] and ipv6_num < 10:
                    vrf_ipv6_list.append(ip['ip'].split('/')[0])
                    ipv6_num +=1
    loc_lib.dut_load_bgp_neigbor_to_peer_group(dut2, data.dut2_vrf_bgp_as, data.dut1_vrf_bgp_as, test_vrf, vrf_ip_list, 
                                        vrf_ipv6_list, group_name="MC-Aliyun-protect", config='yes')

    loc_lib.bgp_permit_route_map_set(dut1, data.dut1_vrf_bgp_as, test_vrf, "MC-Aliyun-protect", 'protecting', '1111 2222 3333')
    loc_lib.bgp_permit_route_map_set(dut2, data.dut2_vrf_bgp_as, test_vrf, "MC-Aliyun-protect", 'protecting', '4444 5555 6666')
    
    for i in range(len(data.ecmp_503_504_dut1_dut2_portlist)):
        cmd = "interface {}\n no shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)

    #reboot.config_save_reboot(data.my_dut_list)
    st.wait(150)

     # Verify the total route count using bcmcmd
    #if not check_swichchip_route_count(dut2, 5, "ipv4", 517, 200000):
    #    st.log("check_swichchip_route_count ipv4 fail")

    #if not check_swichchip_route_count(dut2, 5, "ipv6", 517, 50000):
    #    st.log("check_swichchip_route_count ipv6 fail")


    for i in range(1):
        cmd = "interface {}\n shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)

    for i in range(1):
        cmd = "interface {}\n no shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)
    
    for i in range(3):
        cmd = "interface {}\n shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)

    for i in range(3):
        cmd = "interface {}\n no shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)
    
    st.wait(50)
    #traffic check
    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)
    tg.tg_traffic_control(action='run', stream_handle=traffic_vrf_503_list)

    st.wait(10)
    tg.tg_traffic_control(action='stop', stream_handle=traffic_vrf_503_list)

    st.banner("check dut2-->dut1 port5_to_port1_vrf_503")
    traffic_details = {
       '1': {
            'tx_ports' : [vars.T1D2P1],
            'tx_obj' : [data.tg_list[4]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D1P1, vars.T1D1P2],
            'rx_obj' : [data.tg_list[0], data.tg_list[1]],
            'stream_list': [[data.streams['port5_to_port1_vrf_503']]]
        },
       '2': {
            'tx_ports' : [vars.T1D2P1],
            'tx_obj' : [data.tg_list[4]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D1P1, vars.T1D1P2],
            'rx_obj' : [data.tg_list[0], data.tg_list[1]],
            'stream_list': [[data.streams['port5_to_port1_vrf_503_v6']]]
        }
    }
    #check ecmp port
    if not tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock', comp_type='packet_count'):
        st.log("validate_tgen_traffic failed")
        result=1

     # Verify the total route count using bcmcmd
    if not check_swichchip_route_count(dut2, 5, "ipv4", 517, 200000):
        st.log("check_swichchip_route_count ipv4 fail")

    if not check_swichchip_route_count(dut2, 5, "ipv6", 517, 50000):
        st.log("check_swichchip_route_count ipv6 fail")


    #remove test neighbor
    st.show(dut1, "show vrf")
    st.show(dut2, "show vrf")
    vrf_ip_list_post = []
    vrf_ipv6_list_post = []
    output=bgp_api.show_bgp_ipv4_summary_vtysh(dut2,vrf=test_vrf)
    for nbr in output:
        if nbr['asn'] == data.dut1_vrf_bgp_as:
            vrf_ip_list_post.append(nbr['neighbor'])

    output=bgp_api.show_bgp_ipv6_summary_vtysh(dut2,vrf=test_vrf)
    for nbr in output:
        if nbr['asn'] == data.dut1_vrf_bgp_as:
            vrf_ipv6_list_post.append(nbr['neighbor'])
    loc_lib.dut_load_bgp_neigbor_to_peer_group(dut2, data.dut2_vrf_bgp_as, data.dut1_vrf_bgp_as, test_vrf, vrf_ip_list_post, 
                                        vrf_ipv6_list_post, group_name="MC-Aliyun-public", config='no')

    vrf_ip_list_post = []
    vrf_ipv6_list_post = []
    output=bgp_api.show_bgp_ipv4_summary_vtysh(dut1,vrf=test_vrf)
    for nbr in output:
        if nbr['asn'] == data.dut2_vrf_bgp_as:
            vrf_ip_list_post.append(nbr['neighbor'])

    output=bgp_api.show_bgp_ipv6_summary_vtysh(dut1,vrf=test_vrf)
    for nbr in output:
        if nbr['asn'] == data.dut2_vrf_bgp_as:
            vrf_ipv6_list_post.append(nbr['neighbor'])
    loc_lib.dut_load_bgp_neigbor_to_peer_group(dut1, data.dut1_vrf_bgp_as, data.dut2_vrf_bgp_as, test_vrf, vrf_ip_list_post, 
                                        vrf_ipv6_list_post, group_name="MC-Aliyun-public", config='no')

    dict1 = {'local_as_id': data.dut1_vrf_bgp_as, 'nbr_as_id':data.dut2_vrf_bgp_as,'vrf':test_vrf,'vrf_ip_list':dut1_vrf_ip_list_pre,'vrf_ipv6_list':dut1_vrf_ipv6_list_pre,'group_name':"MC-Aliyun-public"}
    dict2 = {'local_as_id': data.dut2_vrf_bgp_as, 'nbr_as_id':data.dut1_vrf_bgp_as,'vrf':test_vrf,'vrf_ip_list':dut2_vrf_ip_list_pre,'vrf_ipv6_list':dut2_vrf_ipv6_list_pre,'group_name':"MC-Aliyun-public"}
    parallel.exec_parallel(True, [dut1, dut2], loc_lib.dut_load_bgp_neigbor_to_peer_group, [dict1, dict2])

    if result == 0:
        st.report_pass("test_case_passed")
    else:
        cmd = "show ip bgp vrf all summary"
        st.show(dut1,cmd,type='vtysh')
        st.show(dut2,cmd,type='vtysh')
        st.report_fail("traffic_verification_failed")

    st.report_pass("test_case_passed")
