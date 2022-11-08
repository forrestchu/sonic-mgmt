import os
import pytest
import sys
import json
import netaddr
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
from esr_lib import cli_show_json, json_cmp, configdb_checkpoint, configdb_checkarray, appdb_checkpoint, configdb_onefield_checkpoint,appdb_onefield_checkpoint
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
    tg1, tg_ph_1 = tgapi.get_handle_byname("T1D1P1")
    tg2, tg_ph_2 = tgapi.get_handle_byname("T1D1P2")
    tg3, tg_ph_3 = tgapi.get_handle_byname("T1D1P3")
    tg4, tg_ph_4 = tgapi.get_handle_byname("T1D1P4")
    tg5, tg_ph_5 = tgapi.get_handle_byname("T1D2P1")
    tg6, tg_ph_6 = tgapi.get_handle_byname("T1D2P2")
    tg7, tg_ph_7 = tgapi.get_handle_byname("T1D1P5")
    tg8, tg_ph_8 = tgapi.get_handle_byname("T1D1P6")
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

def ixia_bfd_params_modify(bfd_handler, ipver, flap_interval='0', tx_interval='100', rx_interval='100'):
    tg = data.tg_list[0]

    if ipver == "4":
        handler = bfd_handler['bfd_v4_interface_handle']
    elif ipver == "6":
        handler = bfd_handler['bfd_v6_interface_handle']

    tg.tg_emulation_bfd_config(handle = handler,
            control_plane_independent      = "0",
            flap_tx_interval               = flap_interval,
            min_rx_interval                = rx_interval,
            mode                           = "modify",
            detect_multiplier              = "3",
            poll_interval                  = "0",
            tx_interval                    = tx_interval,
            ip_diff_serv                   = "0",
            interface_active               = "1",
            router_active                  = "1",
            session_count                  = "0",
            ip_version                     = ipver,
            aggregate_bfd_session          = "1")
    tg.tg_emulation_bfd_control(handle = handler, mode = "restart")


@pytest.fixture(scope="module", autouse=True)
def esr_srvpn_module_hooks(request):
    #add things at the start of this module

    global vars
    vars = st.ensure_min_topology("D1D2:4","D1T1:6","D2T1:2")
    (data.tg_list, data.tg_ph_list) = get_handles()
    for i in range(6):
        data.tg_list[i].tg_traffic_control(action='reset',port_handle=data.tg_ph_list[i])
    
    duts_base_config()
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

def tg1_base_config():
    tg1_p_handle = dict()

    #init DUT1====TG
    for i in range(4):
        intf_handle_list = []
        bgp_v4_handle_list = []
        bgp_v6_handle_list = []
        bfd_v4_handle_list = []
        bfd_v6_handle_list = []
        tg = data.tg_list[i]
        tg_ph = data.tg_ph_list[i]
        # create 3 devicegroup per ixia port: 1.vrf503; 2.vrf504; 3.vrf_bfd_scale
        h1_1=tg.tg_interface_config(port_handle=tg_ph, mode='config', intf_ip_addr=data.tg1_vrf1_ip_addr[i], 
                                gateway=data.dut1_vrf1_ip_addr[i], vlan='1', vlan_id=data.dut1_vrf1_id[i],
                                ipv6_intf_addr=data.tg1_vrf1_ipv6_addr[i], ipv6_gateway=data.dut1_vrf1_ipv6_addr[i],ipv6_gateway_step='0::0',
                                intf_ip_addr_step='0.0.0.1', ipv6_intf_addr_step = '::1', arp_send_req='1')
        intf_handle_list.insert(0,h1_1)

        h1_2=tg.tg_interface_config(port_handle=tg_ph, mode='config', intf_ip_addr=data.tg1_vrf2_ip_addr[i], 
                                gateway=data.dut1_vrf2_ip_addr[i], vlan='1', vlan_id=data.dut1_vrf2_id[i],
                                ipv6_intf_addr=data.tg1_vrf2_ipv6_addr[i], ipv6_gateway=data.dut1_vrf2_ipv6_addr[i],ipv6_gateway_step='0::0',
                                intf_ip_addr_step='0.0.0.1', ipv6_intf_addr_step = '::1', arp_send_req='1')
        intf_handle_list.insert(1,h1_2)

        h1_3=tg.tg_interface_config(port_handle=tg_ph, mode='config', intf_ip_addr=data.tg1_bfdv4_start_ip_addr[i], 
                                gateway=data.dut1_bfdv4_start_ip_addr[i], gateway_step="0.0.0.0",vlan='1', vlan_id='600', 
                                ipv6_intf_addr=data.tg1_bfdv6_start_ip_addr[i], ipv6_gateway=data.dut1_bfdv6_start_ip_addr[i],ipv6_gateway_step='0::0',
                                intf_ip_addr_step='0.0.0.1', ipv6_intf_addr_step = '::1', arp_send_req='1', device_group_multiplier='98')
        intf_handle_list.insert(2,h1_3)

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

         # Configuring the BGP router in vrf2
        conf_var = {'mode'                 : 'enable',
                    'active_connect_enable' : '1',
                    'enable_4_byte_as'      : '1',
                    'local_as'              : data.tg1_vrf_bgp_as,
                    'remote_as'             : data.dut1_vrf_bgp_as,
                    'remote_ip_addr'        : data.dut1_vrf2_ip_addr[i],
                    'bfd_registration'      : '1',
                    'bfd_registration_mode' : 'single_hop'
                    }
        route_var = {'mode':'add', 
                    'num_routes': data.tg1_vrf2_router_count_list[i], 
                    'prefix': data.tg1_vrf2_router_prefix_list[i], 
                    'as_path':'as_seq:1'
                    }
        bgp_v4_vrf2 = tgapi.tg_bgp_config(tg = tg,
            handle    = h1_2['ipv4_handle'],
            conf_var  = conf_var,
            #route_var = route_var,
            ctrl_var  = ctrl_start)
        
        conf_var = {'mode'                 : 'enable',
                'active_connect_enable' : '1',
                'enable_4_byte_as'      : '1',
                'local_as'              : data.tg1_vrf_bgp_as,
                'remote_as'             : data.dut1_vrf_bgp_as,
                'remote_ipv6_addr'      : data.dut1_vrf2_ipv6_addr[i],
                'ip_version'            : '6',
                'bfd_registration'      : '1',
                'bfd_registration_mode' : 'single_hop'
                }
        route_var['prefix'] = data.tg1_vrf2_router_v6_prefix_list[i]
        
        bgp_v6_vrf2 = tgapi.tg_bgp_config(tg = tg,
            handle    = h1_2['ipv6_handle'],
            conf_var  = conf_var,
            #route_var = route_var,
            ctrl_var  = ctrl_start)

         # Configuring the BGP router in vrf_bfd_scale
        conf_var = {'mode'                 : 'enable',
                    'active_connect_enable' : '1',
                    'enable_4_byte_as'      : '1',
                    'local_as'              : data.tg1_vrf_bgp_as,
                    'remote_as'             : data.dut1_vrf_bgp_as,
                    'remote_ip_addr'        : data.dut1_bfdv4_start_ip_addr[i],
                    'bfd_registration'      : '1',
                    'bfd_registration_mode' : 'single_hop'
                    }
 
        bgp_v4_vrf_bfd = tgapi.tg_bgp_config(tg = tg,
            handle    = h1_3['ipv4_handle'],
            conf_var  = conf_var,
            #route_var = route_var,
            ctrl_var  = ctrl_start)

        conf_var = {'mode'                 : 'enable',
                'active_connect_enable' : '1',
                'enable_4_byte_as'      : '1',
                'local_as'              : data.tg1_vrf_bgp_as,
                'remote_as'             : data.dut1_vrf_bgp_as,
                'remote_ipv6_addr'      : data.dut1_bfdv6_start_ip_addr[i],
                'ip_version'            : '6',
                'bfd_registration'      : '1',
                'bfd_registration_mode' : 'single_hop'
                }
        route_var['prefix'] = "5001::1"
        bgp_v6_vrf_bfd = tgapi.tg_bgp_config(tg = tg,
            handle    = h1_3['ipv6_handle'],
            conf_var  = conf_var,
            #route_var = route_var,
            ctrl_var  = ctrl_start)

        #save bgp handle 
        bgp_v4_handle_list.insert(0,bgp_v4_vrf1)
        bgp_v4_handle_list.insert(1,bgp_v4_vrf2)
        bgp_v4_handle_list.insert(2,bgp_v4_vrf_bfd)
        bgp_v6_handle_list.insert(0,bgp_v6_vrf1)
        bgp_v6_handle_list.insert(1,bgp_v6_vrf2)
        bgp_v6_handle_list.insert(2,bgp_v6_vrf_bfd)

        st.log("create ipv4 bfd for each vrf")
        for j in range(3):
            bfd_v4_handle = tg.tg_emulation_bfd_config(handle = intf_handle_list[j]['ipv4_handle'],
                min_rx_interval                = data.dut_bfd_timer,
                mode                           = "create",
                detect_multiplier              = "3",
                tx_interval                    = data.dut_bfd_timer,
                interface_active               = "1",
                router_active                  = "1",
                ip_version                     = "4",
                aggregate_bfd_session          = "1")
            bfd_v4_handle_list.insert(j, bfd_v4_handle)
 
        st.log("create ipv6 bfd for each vrf")
        for j in range(3):
            bfd_v6_handle = tg.tg_emulation_bfd_config(handle = intf_handle_list[j]['ipv6_handle'],
                min_rx_interval                = data.dut_bfd_timer,
                mode                           = "create",
                detect_multiplier              = "3",
                tx_interval                    = data.dut_bfd_timer,
                interface_active               = "1",
                router_active                  = "1",
                ip_version                     = "6",
                aggregate_bfd_session          = "1")
            bfd_v6_handle_list.insert(j, bfd_v6_handle)
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

        h1_2=tg.tg_interface_config(port_handle=tg_ph, mode='config', intf_ip_addr=data.tg2_vrf2_ip_addr[i], 
                                gateway=data.dut2_vrf2_ip_addr[i], vlan='1', vlan_id=data.dut1_vrf2_id[i], 
                                ipv6_intf_addr=data.tg2_vrf2_ipv6_addr[i],ipv6_gateway=data.dut2_vrf2_ipv6_addr[i],ipv6_gateway_step='0::0',
                                intf_ip_addr_step='0.0.0.1', ipv6_intf_addr_step = '::1', arp_send_req='1')
        intf_handle_list[1] = h1_2

        h1_3=tg.tg_interface_config(port_handle=tg_ph, mode='config', intf_ip_addr=data.tg2_bfdv4_start_ip_addr[i], 
                                gateway=data.dut2_bfdv4_start_ip_addr[i], gateway_step="0.0.0.0",vlan='1', vlan_id='600', 
                                ipv6_intf_addr=data.tg2_bfdv6_start_ip_addr[i],ipv6_gateway=data.dut2_bfdv6_start_ip_addr[i],ipv6_gateway_step='0::0',
                                intf_ip_addr_step='0.0.0.1', ipv6_intf_addr_step = '::1', arp_send_req='1', device_group_multiplier='98')
        intf_handle_list[2] = h1_3

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

         # Configuring the BGP router in vrf2
        conf_var = {'mode'                 : 'enable',
                    'active_connect_enable' : '1',
                    'enable_4_byte_as'      : '1',
                    'local_as'              : data.tg2_vrf_bgp_as,
                    'remote_as'             : data.dut2_vrf_bgp_as,
                    'remote_ip_addr'        : data.dut2_vrf2_ip_addr[i],
                    'bfd_registration'      : '1',
                    'bfd_registration_mode' : 'single_hop'
                    }

        bgp_v4_vrf2 = tgapi.tg_bgp_config(tg = tg,
            handle    = h1_2['ipv4_handle'],
            conf_var  = conf_var,
            #route_var = route_var,
            ctrl_var  = ctrl_start)

        conf_var = {'mode'                 : 'enable',
                'active_connect_enable' : '1',
                'enable_4_byte_as'      : '1',
                'local_as'              : data.tg2_vrf_bgp_as,
                'remote_as'             : data.dut2_vrf_bgp_as,
                'remote_ipv6_addr'      : data.dut2_vrf2_ipv6_addr[i],
                'ip_version'            : '6',
                'bfd_registration'      : '1',
                'bfd_registration_mode' : 'single_hop'
                }
        bgp_v6_vrf2 = tgapi.tg_bgp_config(tg = tg,
            handle    = h1_2['ipv6_handle'],
            conf_var  = conf_var,
            #route_var = route_var,
            ctrl_var  = ctrl_start)

         # Configuring the BGP router in vrf_bfd_scale
        conf_var = {'mode'                 : 'enable',
                    'active_connect_enable' : '1',
                    'enable_4_byte_as'      : '1',
                    'local_as'              : data.tg2_vrf_bgp_as,
                    'remote_as'             : data.dut2_vrf_bgp_as,
                    'remote_ip_addr'        : data.dut2_bfdv4_start_ip_addr[i],
                    'bfd_registration'      : '1',
                    'bfd_registration_mode' : 'single_hop'
                    }
        route_var = {'mode':'add', 
                    'num_routes': "10000", 
                    'prefix': "210.0.0.0", 
                    'as_path':'as_seq:1'
                    }
        bgp_v4_vrf_bfd = tgapi.tg_bgp_config(tg = tg,
            handle    = h1_3['ipv4_handle'],
            conf_var  = conf_var,
            #route_var = route_var,
            ctrl_var  = ctrl_start)

        route_var['prefix'] = "4001::1"
        conf_var = {'mode'                 : 'enable',
                'active_connect_enable' : '1',
                'enable_4_byte_as'      : '1',
                'local_as'              : data.tg2_vrf_bgp_as,
                'remote_as'             : data.dut2_vrf_bgp_as,
                'remote_ipv6_addr'      : data.dut2_bfdv6_start_ip_addr[i],
                'ip_version'            : '6',
                'bfd_registration'      : '1',
                'bfd_registration_mode' : 'single_hop'
                }
        bgp_v6_vrf_bfd = tgapi.tg_bgp_config(tg = tg,
            handle    = h1_3['ipv6_handle'],
            conf_var  = conf_var,
            #route_var = route_var,
            ctrl_var  = ctrl_start)

        #save bgp handle 
        bgp_v4_handle_list[0] = bgp_v4_vrf1
        bgp_v4_handle_list[1] = bgp_v4_vrf2
        bgp_v4_handle_list[2] = bgp_v4_vrf_bfd
        bgp_v6_handle_list[0] = bgp_v6_vrf1
        bgp_v6_handle_list[1] = bgp_v6_vrf2
        bgp_v6_handle_list[2] = bgp_v6_vrf_bfd

        st.log("create ipv4 bfd for each vrf")
        for j in range(3):
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

        st.log("create ipv6 bfd for each vrf")
        for j in range(3):
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

        #save handle per port
        tg2_p_handle['intf'] = intf_handle_list
        tg2_p_handle['bgp_v4'] = bgp_v4_handle_list
        tg2_p_handle['bgp_v6'] = bgp_v6_handle_list
        tg2_p_handle['bfd_v4'] = bfd_v4_handle_list
        tg2_p_handle['bfd_v6'] = bfd_v6_handle_list
        #save handle per dut
        #data.tg1_handle.insert(i, tg1_p_handle)
        data.tg2_handle[i]  = copy.deepcopy(tg2_p_handle)

def tg3_base_config():
    tg3_p_handle = dict()
    #init dut3====TG
    for i in range(1):
        intf_handle_list = [0,0]
        bgp_v4_handle_list = [0,0]
        bgp_v6_handle_list = [0,0]
        tg = data.tg_list[i+6]
        tg_ph = data.tg_ph_list[i+6]

        # create 3 devicegroup per ixia port: 1.vrf503; 2.vrf504; 3.vrf_bfd_scale
        h1_1=tg.tg_interface_config(port_handle=tg_ph, mode='config', intf_ip_addr=data.tg3_vrf1_ip_addr[i], 
                                gateway=data.dut3_vrf1_ip_addr[i], vlan='1', vlan_id=data.dut3_vrf1_id[i], arp_send_req='1')
        intf_handle_list[0] = h1_1

        h1_2=tg.tg_interface_config(port_handle=tg_ph, mode='config', intf_ip_addr=data.tg3_vrf2_ip_addr[i], 
                                gateway=data.dut3_vrf2_ip_addr[i], vlan='1', vlan_id=data.dut3_vrf2_id[i], arp_send_req='1')
        intf_handle_list[1] = h1_2

        # Configuring the BGP router in vrf1
        conf_var = {'mode'                 : 'enable',
                    'active_connect_enable' : '1',
                    'enable_4_byte_as'      : '1',
                    'local_as'              : data.tg3_vrf_bgp_as,
                    'remote_as'             : data.dut3_vrf_bgp_as,
                    'remote_ip_addr'        : data.dut3_vrf1_ip_addr[i],
                    'bfd_registration'      : '1',
                    'bfd_registration_mode' : 'single_hop'
                    }
        route_var = {'mode':'add', 
                    'num_routes': data.tg3_router_count, 
                    'prefix': data.tg3_vrf1_router_prefix, 
                    'as_path':'as_seq:1'
                    }
        ctrl_start = { 'mode' : 'start'}
        ctrl_stop = { 'mode' : 'stop'}

        bgp_v4_vrf1 = tgapi.tg_bgp_config(tg = tg,
            handle    = h1_1['ipv4_handle'],
            conf_var  = conf_var,
            #route_var = route_var,
            ctrl_var  = ctrl_start)

         # Configuring the BGP router in vrf2
        conf_var = {'mode'                 : 'enable',
                    'active_connect_enable' : '1',
                    'enable_4_byte_as'      : '1',
                    'local_as'              : data.tg3_vrf_bgp_as,
                    'remote_as'             : data.dut3_vrf_bgp_as,
                    'remote_ip_addr'        : data.dut3_vrf2_ip_addr[i],
                    'bfd_registration'      : '1',
                    'bfd_registration_mode' : 'single_hop'
                    }
        bgp_v4_vrf2 = tgapi.tg_bgp_config(tg = tg,
            handle    = h1_2['ipv4_handle'],
            conf_var  = conf_var,
            #route_var = route_var,
            ctrl_var  = ctrl_start)
        #save bgp handle 
        bgp_v4_handle_list[0] = bgp_v4_vrf1
        bgp_v4_handle_list[1] = bgp_v4_vrf2

        #save handle per port
        tg3_p_handle['intf'] = intf_handle_list
        tg3_p_handle['bgp_v4'] = bgp_v4_handle_list

        #save handle per dut
        data.tg3_handle[i]  = copy.deepcopy(tg3_p_handle)

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

def vrfs_traffic_v6_add():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    result = 0

    # port 1(TG1_1)<===>port 5(TG2_1) vrf503
    vrf_id = 0
    src_handle = data.tg1_handle[0]['route_v6'][vrf_id]
    tg = data.tg_list[0]
    tg_ph = data.tg_ph_list[0]
    tg_ph_2 = data.tg_ph_list[4]
    dst_handle_list = [data.tg2_handle[0]['route_v6'][vrf_id]['handle'], data.tg2_handle[1]['route_v6'][vrf_id]['handle']]
    stream = tg.tg_traffic_config(port_handle=tg_ph, port_handle2=tg_ph_2, emulation_src_handle=src_handle['handle'],
                emulation_dst_handle=dst_handle_list, circuit_endpoint_type='ipv6',mode='create',
                transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent=data.traffic_rate_precent)
    data.streams['port1_to_port5_vrf_503_v6'] = stream['stream_id']

    tg = data.tg_list[4]
    vrf_id = 0
    src_handle = data.tg2_handle[0]['route_v6'][vrf_id]
    dst_handle_list = [data.tg1_handle[0]['route_v6'][vrf_id]['handle'], data.tg1_handle[1]['route_v6'][vrf_id]['handle']]
    stream = tg.tg_traffic_config(port_handle=tg_ph_2, port_handle2=tg_ph, emulation_src_handle=src_handle['handle'],
                    emulation_dst_handle=dst_handle_list, circuit_endpoint_type='ipv6',mode='create',
                    transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent=data.traffic_rate_precent)
    data.streams['port5_to_port1_vrf_503_v6'] = stream['stream_id']


    # port 2(TG1_2)<===>port 6(TG2_2) vrf504
    vrf_id = 1
    src_handle = data.tg1_handle[1]['route_v6'][vrf_id]
    dst_handle_list = [data.tg2_handle[0]['route_v6'][vrf_id]['handle'], data.tg2_handle[1]['route_v6'][vrf_id]['handle']]
    tg = data.tg_list[1]
    tg_ph = data.tg_ph_list[1]
    tg_ph_2 = data.tg_ph_list[5]
    stream = tg.tg_traffic_config(port_handle=tg_ph, port_handle2=tg_ph_2, emulation_src_handle=src_handle['handle'],
                emulation_dst_handle=dst_handle_list, circuit_endpoint_type='ipv6',mode='create',
                transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent=data.traffic_rate_precent)
    data.streams['port2_to_port6_vrf_504_v6'] = stream['stream_id']

    tg = data.tg_list[5]
    vrf_id = 1
    src_handle = data.tg2_handle[1]['route_v6'][vrf_id]
    dst_handle_list = [data.tg1_handle[0]['route_v6'][vrf_id]['handle'], data.tg1_handle[1]['route_v6'][vrf_id]['handle']]
    stream = tg.tg_traffic_config(port_handle=tg_ph_2, port_handle2=tg_ph, emulation_src_handle=src_handle['handle'],
                    emulation_dst_handle=dst_handle_list, circuit_endpoint_type='ipv6',mode='create',
                    transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent=data.traffic_rate_precent)
    data.streams['port6_to_port2_vrf_504_v6'] = stream['stream_id']


def l3_base_unconfig():

    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]

    st.log("remove l3 base config.")
    #ipfeature.clear_ip_configuration(st.get_dut_names())
    #vapi.clear_vlan_configuration(st.get_dut_names())
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

    records = st.show(dut1, "show bgp ipv4 vpn", type="alicli")

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

    records = st.show(dut1, "show bgp ipv4 vpn", type='alicli')

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
    records = st.show(dut1, "show bgp ipv4 vpn", type='alicli')
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
    records = st.show(dut2, "show bgp ipv4 vpn", type='alicli')
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
        'un':'2000::179'
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

# OSPREY-MC-B09-13-178.EU6# show bgp ipv4 vpn 192.100.1.0
# BGP routing table entry for 2:2:192.100.1.0/24, version 1
# not allocated
# Paths: (1 available, best #1)
#   Not advertised to any peer
#   Local
#     0.0.0.0 from 2000::179 (1.1.1.179)
#       Origin IGP, metric 0, localpref 100, valid, internal, best (First path received)
#       Extended Community: RT:3:3
#       Remote label: 3
#       Remote SID: fd00:201:201:fff1:11::
#       Last update: Mon Nov  7 09:12:54 2022
# OSPREY-MC-B09-13-178.EU6# 

    st.report_pass("test_case_passed")


