import os
import copy
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
def mc_scale_module_hooks(request):
    #add things at the start of this module

    global vars
    vars = st.ensure_min_topology("D1D2:4","D1T1:6","D2T1:2")
    (data.tg_list, data.tg_ph_list) = get_handles()
    for i in range(6):
        data.tg_list[i].tg_traffic_control(action='reset',port_handle=data.tg_ph_list[i])
    
    duts_base_config()
    tg1_base_config()
    tg2_base_config()
    tg3_base_config()
    data.tg_list[0].tg_test_control(action='stop_all_protocols')
    st.wait(20)
    tg1_bgp_router_add()
    tg2_bgp_router_add()
    tg3_bgp_router_add()    
    data.tg_list[0].tg_test_control(action='start_all_protocols')
    st.wait(150)
    vrfs_traffic_add()
    vrfs_traffic_v6_add()
    get_dut_ip()
    yield
    l3_base_unconfig()

@pytest.fixture(scope="function", autouse=True)
def mc_scale_func_hooks(request):
    # add things at the start every test case
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]

    yield
    if st.get_func_name(request) == 'test_bgp_fast_isolate_and_recover':
        if not loc_lib.check_bgp_isolate(dut1, 'no-isolate'):
            no_isolate_cmd = "no isolate fast"
            st.config(dut1, no_isolate_cmd, type='alicli')
    else:
        st.show(dut1,"show vrf")
        st.show(dut2,"show vrf")

def duts_base_config():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    curr_path = os.getcwd()
    json_file_dut1 = curr_path+"/routing/MC_SCALE/dut1_mc_scale.json"
    json_file_dut2 = curr_path+"/routing/MC_SCALE/dut2_mc_scale.json"
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
                    transmit_mode='continuous', length_mode='fixed',frame_size='1500', rate_percent=data.ruijie_traffic_rate_precent)
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
def test_subintf_503_504_traffic():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    tg = data.tg_list[0]
    tg_ph = data.tg_ph_list[0]
    tg_ph_2 = data.tg_ph_list[4]
    result = 0

    bandwidth = 2*float(data.traffic_rate_precent)
    ecmp_member_Gbps = int(bandwidth/len(data.ecmp_503_504_dut1_dut2_portlist))
    ixia_ecmp_Gbps = int(bandwidth/len(data.ecmp_503_504_dut_tg_portlist))
    traffic_vrf_503_list = [data.streams['port5_to_port1_vrf_503'], data.streams['port1_to_port5_vrf_503']]
    traffic_vrf_504_list = [data.streams['port6_to_port2_vrf_504'], data.streams['port2_to_port6_vrf_504']]
    traffic_vrf_503_v6_list = [data.streams['port5_to_port1_vrf_503_v6'], data.streams['port1_to_port5_vrf_503_v6']]

    #step1 check lb in ecmp_503_504_dut1_dut2_portlist and end-to-end traffic statistic in vrf 503
    st.banner("step1: test traffic in vrf_503")
    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)
    tg.tg_traffic_control(action='run', stream_handle=traffic_vrf_503_list)

    st.wait(10)
    if not check_dut_intf_tx_traffic_counters(dut2,data.ecmp_503_504_dut1_dut2_portlist,ecmp_member_Gbps):
        st.log("dut2 dut-to-dut ecmp members rate check failed")
        result=1

    if not check_dut_intf_tx_traffic_counters(dut1,data.ecmp_503_504_dut1_dut2_portlist,ecmp_member_Gbps):
        st.log("dut1 dut-to-dut ecmp members rate check failed")
        result=1

    st.wait(10)
    tg.tg_traffic_control(action='stop', stream_handle=traffic_vrf_503_list)

    st.banner("step1.1: check dut2-->dut1 port5_to_port1_vrf_503")
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
            'tx_ports' : [vars.T1D1P1],
            'tx_obj' : [data.tg_list[0]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D2P1, vars.T1D2P2],
            'rx_obj' : [data.tg_list[4],data.tg_list[5]],
            'stream_list': [[data.streams['port1_to_port5_vrf_503']]]
        }
    }
    #check ecmp port
    if not tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock', comp_type='packet_count'):
        st.log("validate_tgen_traffic failed")
        result=1

    traffic_vrf_503_v6_list = [data.streams['port5_to_port1_vrf_503_v6'], data.streams['port1_to_port5_vrf_503_v6']]

    #step1 check lb in ecmp_503_504_dut1_dut2_portlist and end-to-end traffic v6 statistic in vrf 503
    st.banner("step1.2: check dut2-->dut1 port5_to_port1_vrf_503_v6")
    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)
    tg.tg_traffic_control(action='run', stream_handle=traffic_vrf_503_v6_list)

    st.wait(10)
    if not check_dut_intf_tx_traffic_counters(dut2,data.ecmp_503_504_dut1_dut2_portlist,ecmp_member_Gbps):
        st.log("dut2 dut-to-dut ecmp members rate check failed")
        result=1

    if not check_dut_intf_tx_traffic_counters(dut1,data.ecmp_503_504_dut1_dut2_portlist,ecmp_member_Gbps):
        st.log("dut1 dut-to-dut ecmp members rate check failed")
        result=1

    st.wait(10)
    tg.tg_traffic_control(action='stop', stream_handle=traffic_vrf_503_v6_list)

    traffic_details = {
       '1': {
            'tx_ports' : [vars.T1D2P1],
            'tx_obj' : [data.tg_list[4]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D1P1, vars.T1D1P2],
            'rx_obj' : [data.tg_list[0], data.tg_list[1]],
            'stream_list': [[data.streams['port5_to_port1_vrf_503_v6']]]
        },
       '2': {
            'tx_ports' : [vars.T1D1P1],
            'tx_obj' : [data.tg_list[0]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D2P1, vars.T1D2P2],
            'rx_obj' : [data.tg_list[4],data.tg_list[5]],
            'stream_list': [[data.streams['port1_to_port5_vrf_503_v6']]]
        }
    }
    #check ecmp port
    if not tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock', comp_type='packet_count'):
        st.log("validate_tgen_traffic failed")
        result=1

    #step2: shutdown/no shutdown ecmp_503_504_dut1_dut2_portlist in vrf 504
    st.banner("step2: test traffic in vrf_504")
    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)
    tg.tg_traffic_control(action='run', stream_handle=traffic_vrf_504_list)

    conf_var = {'mode'              : 'modify',
                'enable_flap'       : '1',
                'flap_up_time'      : '30',
                'flap_down_time'    : '10',
            }
    ctrl_start = { 'mode' : 'start'}
    route_var = {'mode':'modify', 
                'enable_route_flap': '1', 
                'flap_up_time': '20' ,
                'flap_down_time':'20',
                }
    # enable BGP flap
    tg.tg_emulation_bgp_route_config(handle=data.tg1_handle[1]['route'][1]['ip_routes'], mode='modify', enable_route_flap='1', 
                                    flap_up_time = '10', flap_down_time='10', active='1')
    tg.tg_emulation_bgp_route_config(handle=data.tg1_handle[0]['route'][1]['ip_routes'], mode='modify', enable_route_flap='1', 
                                    flap_up_time = '10', flap_down_time='10', active='1')
    tg.tg_emulation_bgp_route_config(handle=data.tg2_handle[1]['route'][1]['ip_routes'], mode='modify', enable_route_flap='1', 
                                    flap_up_time = '10', flap_down_time='10', active='1')
    tg.tg_emulation_bgp_route_config(handle=data.tg2_handle[1]['route'][1]['ip_routes'], mode='modify', enable_route_flap='1', 
                                    flap_up_time = '10', flap_down_time='10', active='1')
    tgapi.tg_bgp_config(tg = tg, handle=data.tg1_handle[1]['bgp_v4'][1]['conf'], conf_var=conf_var)
    tgapi.tg_bgp_config(tg = tg, handle=data.tg2_handle[1]['bgp_v4'][1]['conf'], conf_var=conf_var)
    tgapi.tg_bgp_config(tg = tg, handle=data.tg1_handle[0]['bgp_v4'][1]['conf'], conf_var=conf_var)
    tgapi.tg_bgp_config(tg = tg, handle=data.tg2_handle[0]['bgp_v4'][1]['conf'], conf_var=conf_var)
    tg.tg_emulation_bgp_control(handle=data.tg1_handle[1]['bgp_v4'][1]['conf']['handle'],mode = 'restart')
    tg.tg_emulation_bgp_control(handle=data.tg2_handle[1]['bgp_v4'][1]['conf']['handle'],mode = 'restart')
    tg.tg_emulation_bgp_control(handle=data.tg1_handle[0]['bgp_v4'][1]['conf']['handle'],mode = 'restart')
    tg.tg_emulation_bgp_control(handle=data.tg2_handle[0]['bgp_v4'][1]['conf']['handle'],mode = 'restart')

    #shut/no shut port
    for i in range(4):
        cmd = "interface {}\n shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut1, cmd, type='alicli',skip_error_check=True)
        st.wait(5)
        cmd = "interface {}\n no shutdown\n".format(data.ecmp_503_504_dut1_dut2_portlist[i])
        st.config(dut1, cmd, type='alicli',skip_error_check=True)
        st.wait(5)

    #flaping 200s
    st.wait(200)

    #disable BGP flap
    conf_var = {'mode'              : 'modify',
                'enable_flap'       : '0',
            }
    ctrl_start = { 'mode' : 'start'}
    tg.tg_emulation_bgp_route_config(handle=data.tg1_handle[1]['route'][1]['ip_routes'], mode='modify', enable_route_flap='0', active='1')
    tg.tg_emulation_bgp_route_config(handle=data.tg2_handle[1]['route'][1]['ip_routes'], mode='modify', enable_route_flap='0', active='1')
    tg.tg_emulation_bgp_route_config(handle=data.tg1_handle[0]['route'][1]['ip_routes'], mode='modify', enable_route_flap='0', active='1')
    tg.tg_emulation_bgp_route_config(handle=data.tg2_handle[0]['route'][1]['ip_routes'], mode='modify', enable_route_flap='0', active='1')
    tgapi.tg_bgp_config(tg = tg, handle=data.tg1_handle[1]['bgp_v4'][1]['conf'], conf_var=conf_var)
    tgapi.tg_bgp_config(tg = tg, handle=data.tg2_handle[1]['bgp_v4'][1]['conf'], conf_var=conf_var)
    tgapi.tg_bgp_config(tg = tg, handle=data.tg1_handle[0]['bgp_v4'][1]['conf'], conf_var=conf_var)
    tgapi.tg_bgp_config(tg = tg, handle=data.tg2_handle[0]['bgp_v4'][1]['conf'], conf_var=conf_var)
    tg.tg_emulation_bgp_control(handle=data.tg1_handle[1]['bgp_v4'][1]['conf']['handle'],mode = 'restart')
    tg.tg_emulation_bgp_control(handle=data.tg2_handle[1]['bgp_v4'][1]['conf']['handle'],mode = 'restart')
    tg.tg_emulation_bgp_control(handle=data.tg1_handle[0]['bgp_v4'][1]['conf']['handle'],mode = 'restart')
    tg.tg_emulation_bgp_control(handle=data.tg2_handle[0]['bgp_v4'][1]['conf']['handle'],mode = 'restart')
    st.wait(100)

    #check traffic after flaping disable
    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)
    st.wait(30)

    st.banner("step2.1: check dut<-->ixia ecmp member")
    if not check_dut_intf_tx_traffic_counters(dut2,data.ecmp_503_504_dut_tg_portlist,ixia_ecmp_Gbps):
        st.log("dut2 dut-to-ixia ecmp members rate check failed")
        result=1

    if not check_dut_intf_tx_traffic_counters(dut1,data.ecmp_503_504_dut_tg_portlist,ixia_ecmp_Gbps):
        st.log("dut1 dut-to-ixia ecmp members rate check failed")
        #result=1
    
    st.banner("step2.2: check dut1<-->dut2 ecmp member")
    if not check_dut_intf_tx_traffic_counters(dut2,data.ecmp_503_504_dut1_dut2_portlist,ecmp_member_Gbps):
        st.log("dut2 dut-to-dut ecmp members rate check failed")
        #result=1

    if not check_dut_intf_tx_traffic_counters(dut1,data.ecmp_503_504_dut1_dut2_portlist,ecmp_member_Gbps):
        st.log("dut1 dut-to-dut ecmp members rate check failed")
        #result=1

    tg.tg_traffic_control(action='stop', stream_handle=traffic_vrf_504_list)

    traffic_details = {
    '1': {
        'tx_ports' : [vars.T1D2P2],
        'tx_obj' : [data.tg_list[5]],
        'exp_ratio' : [1],
        'rx_ports' : [vars.T1D1P1, vars.T1D1P2],
        'rx_obj' : [data.tg_list[0],data.tg_list[1]],
        'stream_list': [[data.streams['port6_to_port2_vrf_504']]]
        },
    '2': {
        'tx_ports' : [vars.T1D1P2],
        'tx_obj' : [data.tg_list[1]],
        'exp_ratio' : [1],
        'rx_ports' : [vars.T1D2P1, vars.T1D2P2],
        'rx_obj' : [data.tg_list[4],data.tg_list[5]],
        'stream_list': [[data.streams['port2_to_port6_vrf_504']]]
        }
    }
    if not tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock', comp_type='packet_count'):
        st.log("validate_tgen_traffic port2 port6 failed")
        result=1
    
    if result == 0:
        st.report_pass("test_case_passed")
    else:
        cmd = "show ip bgp vrf all summary"
        st.show(dut1,cmd,type='vtysh')
        st.show(dut2,cmd,type='vtysh')
        st.report_fail("traffic_verification_failed")

@pytest.mark.community
@pytest.mark.community_pass
def test_subintf_501_502_traffic():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    tg = data.tg_list[0]
    tg_ph = data.tg_ph_list[0]
    tg_ph_2 = data.tg_ph_list[6]
    result = 0
    dut1_ecmp_member_Gbps = 65
    dut2_ecmp_member_Gbps = 50
    bandwidth = 2*float(data.traffic_rate_precent)
    dut1_dut2_ecmp_member_Gbps = int(bandwidth/len(data.ecmp_501_502_dut1_dut2_portlist))
    dut2_RJ_ecmp_member_Gbps = int(bandwidth/len(data.ecmp_501_502_dut_RJ_portlist))
    dut1_tg_ecmp_member_Gbps = int(bandwidth/len(data.ecmp_501_502_dut_tg_portlist))
    traffic_vrf_501_list = [data.streams['port7_to_port3_vrf_501'], data.streams['port3_to_port7_vrf_501']]
    traffic_vrf_502_list = [data.streams['port7_to_port4_vrf_502'], data.streams['port4_to_port7_vrf_502']]

    #step1 check lb in ecmp_501_502_dut1_dut2_portlist and end-to-end traffic statistic in vrf 501
    st.banner("step1: test traffic in vrf_501")
    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)
    tg.tg_traffic_control(action='run', stream_handle=traffic_vrf_501_list)
    st.wait(10)
    if not retry_api(check_dut_intf_tx_traffic_counters,dut=dut2,portlist=data.ecmp_501_502_dut1_dut2_portlist,expect_val=dut1_dut2_ecmp_member_Gbps,retry_count= 3,delay= 3):
        st.log("dut2 dut-to-dut ecmp members rate check failed")
        result=1

    if not retry_api(check_dut_intf_tx_traffic_counters,dut=dut1,portlist=data.ecmp_501_502_dut1_dut2_portlist,expect_val=dut1_dut2_ecmp_member_Gbps,retry_count= 3,delay= 3):
        st.log("dut1 dut-to-dut ecmp members rate check failed")
        result=1

    st.wait(10)
    tg.tg_traffic_control(action='stop', stream_handle=traffic_vrf_501_list)

    st.banner("step1.1: check TG3-->dut1 port7_to_port3_vrf_501")
    traffic_details = {
       '1': {
            'tx_ports' : [vars.T1D1P5],
            'tx_obj' : [data.tg_list[6]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D1P3, vars.T1D1P4],
            'rx_obj' : [data.tg_list[2], data.tg_list[3]],
            'stream_list': [[data.streams['port7_to_port3_vrf_501']]]
        },
       '2': {
            'tx_ports' : [vars.T1D1P3],
            'tx_obj' : [data.tg_list[2]],
            'exp_ratio' : [1],        #TG3 use only one 200G port
            'rx_ports' : [vars.T1D1P5],
            'rx_obj' : [data.tg_list[6]],
            'stream_list': [[data.streams['port3_to_port7_vrf_501']]]
        }
    }
    #check traffic
    if not tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock', comp_type='packet_count'):
        st.log("validate_tgen_traffic failed")
        result=1

    #step2: shutdown/no shutdown ecmp_501_502_dut_RJ_portlist in vrf 502
    st.banner("step2: test traffic in vrf_502")
    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)
    tg.tg_traffic_control(action='run', stream_handle=traffic_vrf_502_list)

    conf_var = {'mode'              : 'modify',
                'enable_flap'       : '1',
                'flap_up_time'      : '20',
                'flap_down_time'    : '10',
            }
    ctrl_start = { 'mode' : 'start'}
    route_var = {'mode':'modify', 
                'enable_route_flap': '1', 
                'flap_up_time': '20' ,
                'flap_down_time':'20',
                }
    # enable BGP flap
    tg.tg_emulation_bgp_route_config(handle=data.tg1_handle[2]['route'][1]['ip_routes'], mode='modify', enable_route_flap='1', 
                                    flap_up_time = '20', flap_down_time='10', active='1')
    tg.tg_emulation_bgp_route_config(handle=data.tg1_handle[3]['route'][1]['ip_routes'], mode='modify', enable_route_flap='1', 
                                    flap_up_time = '20', flap_down_time='10', active='1')
    tg.tg_emulation_bgp_route_config(handle=data.tg3_handle[0]['route'][1]['ip_routes'], mode='modify', enable_route_flap='1', 
                                    flap_up_time = '20', flap_down_time='10', active='1')
    tgapi.tg_bgp_config(tg = tg, handle=data.tg1_handle[2]['bgp_v4'][1]['conf'], conf_var=conf_var, ctrl_var=ctrl_start)
    tgapi.tg_bgp_config(tg = tg, handle=data.tg1_handle[3]['bgp_v4'][1]['conf'], conf_var=conf_var, ctrl_var=ctrl_start)
    tgapi.tg_bgp_config(tg = tg, handle=data.tg3_handle[0]['bgp_v4'][1]['conf'], conf_var=conf_var, ctrl_var=ctrl_start)
    tg.tg_emulation_bgp_control(handle=data.tg1_handle[2]['bgp_v4'][1]['conf']['handle'],mode = 'restart')
    tg.tg_emulation_bgp_control(handle=data.tg1_handle[3]['bgp_v4'][1]['conf']['handle'],mode = 'restart')
    tg.tg_emulation_bgp_control(handle=data.tg3_handle[0]['bgp_v4'][1]['conf']['handle'],mode = 'restart')

    for i in range(2):
        cmd = "interface {}\n shutdown\n".format(data.ecmp_501_502_dut_RJ_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)
        st.wait(5)
        cmd = "interface {}\n no shutdown\n".format(data.ecmp_501_502_dut_RJ_portlist[i])
        st.config(dut2, cmd, type='alicli',skip_error_check=True)
        st.wait(5)

    st.wait(100)
    #disable BGP flap
    conf_var = {'mode'              : 'modify',
                'enable_flap'       : '0',
            }
    ctrl_start = { 'mode' : 'start'}
    tg.tg_emulation_bgp_route_config(handle=data.tg1_handle[2]['route'][1]['ip_routes'], mode='modify', enable_route_flap='0', active='1')
    tg.tg_emulation_bgp_route_config(handle=data.tg1_handle[3]['route'][1]['ip_routes'], mode='modify', enable_route_flap='0', active='1')
    tg.tg_emulation_bgp_route_config(handle=data.tg3_handle[0]['route'][1]['ip_routes'], mode='modify', enable_route_flap='0', active='1')
    tgapi.tg_bgp_config(tg = tg, handle=data.tg1_handle[2]['bgp_v4'][1]['conf'], conf_var=conf_var)
    tgapi.tg_bgp_config(tg = tg, handle=data.tg1_handle[3]['bgp_v4'][1]['conf'], conf_var=conf_var)
    tgapi.tg_bgp_config(tg = tg, handle=data.tg3_handle[0]['bgp_v4'][1]['conf'], conf_var=conf_var)
    tg.tg_emulation_bgp_control(handle=data.tg1_handle[2]['bgp_v4'][1]['conf']['handle'],mode = 'restart')
    tg.tg_emulation_bgp_control(handle=data.tg1_handle[3]['bgp_v4'][1]['conf']['handle'],mode = 'restart')
    tg.tg_emulation_bgp_control(handle=data.tg3_handle[0]['bgp_v4'][1]['conf']['handle'],mode = 'restart')
    st.wait(100)

    #check traffic after flaping disable
    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)
    st.wait(30)

    st.banner("step2.1: check dut<-->ixia ecmp member")
    RJ_RATE = 0.8
    if not check_dut_intf_tx_traffic_counters(dut1,data.ecmp_501_502_dut_tg_portlist, RJ_RATE * dut1_tg_ecmp_member_Gbps):
        st.log("dut1 dut-to-ixia ecmp members rate check failed")
        result=1
    
    st.banner("step2.2: check dut2<-->RJ ecmp member")
    if not check_dut_intf_tx_traffic_counters(dut2,data.ecmp_501_502_dut_RJ_portlist,dut2_RJ_ecmp_member_Gbps):
        st.log("dut2 dut-to-RJ ecmp members rate check failed")
        #result=1

    if not check_dut_intf_tx_traffic_counters(dut2,data.ecmp_501_502_dut1_dut2_portlist,dut1_dut2_ecmp_member_Gbps):
        st.log("dut2 dut-to-dut ecmp members rate check failed")
        #result=1

    tg.tg_traffic_control(action='stop', stream_handle=traffic_vrf_502_list)

    traffic_details = {
    '1': {
        'tx_ports' : [vars.T1D1P5],
        'tx_obj' : [data.tg_list[6]],
        'exp_ratio' : [1],        #two ecmp port, each is 50%
        'rx_ports' : [vars.T1D1P3, vars.T1D1P4],
        'rx_obj' : [data.tg_list[2],data.tg_list[3]],
        'stream_list': [[data.streams['port7_to_port4_vrf_502']]]
        },
    '2': {
        'tx_ports' : [vars.T1D1P4],
        'tx_obj' : [data.tg_list[3]],
        'exp_ratio' : [1],
        'rx_ports' : [vars.T1D1P5],
        'rx_obj' : [data.tg_list[6]],
        'stream_list': [[data.streams['port4_to_port7_vrf_502']]]
        }
    }
    if not tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock', comp_type='packet_count'):
        st.log("validate_tgen_traffic port4 port7 failed")
        result=1

    if result == 0:
        st.report_pass("test_case_passed")
    else:
        cmd = "show ip bgp vrf all summary"
        st.show(dut1,cmd,type='vtysh')
        st.show(dut2,cmd,type='vtysh')
        st.report_fail("traffic_verification_failed")

@pytest.mark.community
@pytest.mark.community_pass
def test_read_all_bfd_counter():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    err_status_session = 0
    err_tx_session = 0
    interval = int(data.dut_bfd_timer)
    sample_time =30
    result = 0

    output1 = bfdapi.get_bfd_peer_counters(dut1, cli_type='alicli')
    st.wait(sample_time)
    output2 = bfdapi.get_bfd_peer_counters(dut1, cli_type='alicli')
    all_session = len(output2)
    st.log("get bfd sessions {}".format(all_session))
    for i in range(all_session):
        tx_counter1 = output1[i]['cntrlpktout']
        tx_counter2 = output2[i]['cntrlpktout']
        down_env1 = output1[i]['sessiondownev']
        down_env2 = output2[i]['sessiondownev']
        tx_pps = (int(tx_counter2) - int(tx_counter1))/sample_time
        if tx_pps > 2*(1000/interval) or tx_pps < (1000/interval)/2:
            st.log("current bfd session {} tx pps:{}".format(output1[i]['peeraddress'], tx_pps))
            err_tx_session += 1
        elif down_env1 != down_env2:
            st.log("current bfd session {} down notfiy occur".format(output1[i]['peeraddress']))
            err_status_session += 1

    if err_status_session > 0 or err_tx_session > 0:
        st.log("error bfd session, status err:{} tx err:{}".format(err_status_session, err_tx_session))
        result = 1

    if result == 0:
        st.report_pass("test_case_passed")
    else:
        st.report_fail("bfd counter check failed")

@pytest.mark.community
@pytest.mark.community_pass
def test_bfd_attr_set():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    tg = data.tg_list[0]
    err_session = 0
    interval = int(data.dut_bfd_timer)
    new_interval = '50'

    st.wait(10) # wait hw-bfd work
    #mod vrf [long-vrf-503,long-vrf-TG-bfd1]
    vrf = [data.dut_traffic_vrf_name["503"], data.dut_tg_bfd_vrf_name["TG1_1"]]
    peer_group = ['TC2_TO_MC', 'ixia1_v6']
    local_ip_list = [data.dut1_vrf1_ip_addr[0], data.dut1_bfdv6_start_ip_addr[0]]
    remote_ip_list = [data.tg1_vrf1_ip_addr[0], data.tg1_bfdv6_start_ip_addr[0]]
    bfd_handler_list = [data.tg1_handle[0]['bfd_v4'][0], 
                        data.tg1_handle[0]['bfd_v6'][2]]
    ip_version = ['4', '6']
    for i in range(2):
        if not retry_api(bfdapi.verify_bfd_peer, dut1, peer=remote_ip_list[i], local_addr=local_ip_list[i], vrf_name=vrf[i], 
                                    rx_interval=[[data.dut_bfd_timer,data.tg_bfd_timer]], status='up', retry_count= 3, delay= 3):
            st.log("verify_bfd_peer {} failed".format(remote_ip_list[i]))
            st.report_fail("bfd non-work", local_ip_list[i], dut1)

        st.log("bfd status check ok, set dut bfd params: multiplier=5, rx_intv=50, tx_intv=50")
        cmd = "router bgp {} vrf {}\n".format(data.dut1_vrf_bgp_as, vrf[i])
        cmd += "neighbor {} bfd 5 {} {}\n".format(peer_group[i],new_interval,new_interval)
        cmd += "exit\n"
        st.config(dut1, cmd, skip_error_check=True, type='alicli')
        st.wait(5)

        #skip multiplier check
        if not retry_api(bfdapi.verify_bfd_peer, dut1, peer=remote_ip_list[i], local_addr=local_ip_list[i], vrf_name=vrf[i], 
                            rx_interval=[[new_interval,data.tg_bfd_timer]], status='up', retry_count= 3, delay= 3):
            st.log("verify_bfd_peer {} failed".format(remote_ip_list[i]))
            st.report_fail("bfd status error", local_ip_list[i], dut1)

        st.log("set TG bfd params")
        # TG BFD params change
        ixia_bfd_params_modify(bfd_handler = bfd_handler_list[i], ipver=ip_version[i], tx_interval=new_interval, rx_interval=new_interval)
        st.wait(20)

        if not retry_api(bfdapi.verify_bfd_peer, dut1, peer=remote_ip_list[i], local_addr=local_ip_list[i], vrf_name=vrf[i], 
                                    rx_interval=[[new_interval,new_interval]], status='up', retry_count= 3, delay= 3):
            st.log("verify_bfd_peer {} failed".format(remote_ip_list[i]))
            st.report_fail("bfd status error", local_ip_list[i], dut1)

        cmd = "router bgp {} vrf {}\n".format(data.dut1_vrf_bgp_as, vrf[i])
        cmd += "neighbor {} bfd 3 {} {}\n".format(peer_group[i], data.dut_bfd_timer, data.dut_bfd_timer)
        cmd += "exit\n"
        st.config(dut1, cmd, skip_error_check=True, type='alicli')
        st.wait(5)

        if not retry_api(bfdapi.verify_bfd_peer, dut1, peer=remote_ip_list[i], local_addr=local_ip_list[i], rx_interval=[[data.dut_bfd_timer,new_interval]], 
                                status='up', vrf_name=vrf[i], retry_count= 3, delay= 3):
            st.log("verify_bfd_peer {} failed".format(remote_ip_list[i]))
            st.report_fail("bfd status error", local_ip_list[i], dut1)

        ixia_bfd_params_modify(bfd_handler = bfd_handler_list[i], ipver=ip_version[i], tx_interval=data.dut_bfd_timer, rx_interval=data.dut_bfd_timer)

    # dut2 mod long-vrf-dut-bfd1 
    vrf = [data.dut_traffic_vrf_name["501"], data.dut_traffic_vrf_name["502"]]
    peer_group = ['RJ-MC-Aliyun-public', 'RJ-MC-Aliyun']
    local_ip_list = ['11.8.100.1', '11.8.102.1']
    remote_ip_list = ['11.8.100.2', '11.8.102.2']
    bfd_interval = ['200','100']
    for i in range(2):
        if not retry_api(bfdapi.verify_bfd_peer, dut2, peer=remote_ip_list[i], local_addr=local_ip_list[i], vrf_name=vrf[i], 
                            status='up', retry_count= 3, delay= 3):
            st.log("verify_bfd_peer {} failed".format(remote_ip_list[i]))
            st.report_fail("bfd non-work", local_ip_list[i], dut2)

        st.log("bfd status check ok, set dut bfd params: multiplier=5, rx_intv=50, tx_intv=50")
        cmd = "router bgp {} vrf {}\n".format(data.dut2_vrf_bgp_as, vrf[i])
        cmd += "neighbor {} bfd 5 {} {}\n".format(peer_group[i],new_interval,new_interval)
        cmd += "exit\n"
        st.config(dut2, cmd, skip_error_check=True, type='alicli')
        st.wait(5)

        #skip multiplier check
        if not retry_api(bfdapi.verify_bfd_peer, dut2, peer=remote_ip_list[i], local_addr=local_ip_list[i], vrf_name=vrf[i], 
                                    rx_interval=[[new_interval, bfd_interval[i]]], status='up', retry_count= 3, delay= 3):
            st.log("verify_bfd_peer {} failed".format(remote_ip_list[i]))
            st.report_fail("bfd status error", local_ip_list[i], dut2)

        cmd = "router bgp {} vrf {}\n".format(data.dut2_vrf_bgp_as, vrf[i])
        cmd += "neighbor {} bfd 3 {} {}\n".format(peer_group[i], bfd_interval[i], bfd_interval[i])
        cmd += "exit\n"
        st.config(dut2, cmd, skip_error_check=True, type='alicli')
        st.wait(5)

        if not retry_api(bfdapi.verify_bfd_peer, dut2, peer=remote_ip_list[i], local_addr=local_ip_list[i], rx_interval=[[bfd_interval[i], bfd_interval[i]]], 
                                status='up', vrf_name=vrf[i], retry_count= 3, delay= 3):
            st.log("verify_bfd_peer {} failed".format(remote_ip_list[i]))
            st.report_fail("bfd status error", local_ip_list[i], dut2)
    
    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_ixia_bfd_flap_in_bfd_vrf():
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    tg = data.tg_list[0]
    tg_ph = data.tg_ph_list[0]
    tg_ph_2 = data.tg_ph_list[6]
    result = 0
    init_down_session = 0
    traffic_list = [data.streams['port5_to_port1_vrf_503'], data.streams['port1_to_port5_vrf_503'],
                    data.streams['port3_to_port7_vrf_501'], data.streams['port7_to_port3_vrf_501']]

    cmd = "show bfd peers"
    output1 = st.show(dut1, cmd, type='vtysh')
    all_session = len(output1)
    st.log("get bfd sessions {}".format(all_session))
    for i in range(all_session):
        if 'down' == output1[i]['status']:
            init_down_session += 1
            st.log("peer {} status down before bfd vrf test".format(output1[i]['peer']))

    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)
    tg.tg_traffic_control(action='run', stream_handle=traffic_list)

    bfd_pps = 1000/int(data.dut_bfd_timer)
    flap_timer = str(bfd_pps*10)
    st.log("config TG bfd flap timer = {}".format(flap_timer))
    for i in range(4):
        #ixia_bfd_params_modify(bfd_handler = data.tg1_handle[0]['bfd_v4'][0], flap_interval = flap_timer, ipver='4')
        ixia_bfd_params_modify(bfd_handler = data.tg1_handle[i]['bfd_v4'][2], flap_interval = flap_timer, ipver='4')
        ixia_bfd_params_modify(bfd_handler = data.tg1_handle[i]['bfd_v6'][2], flap_interval = flap_timer, ipver='6')
    st.wait(100)

    st.log("disable TG bfd flap")
    for i in range(4):
        #ixia_bfd_params_modify(bfd_handler = data.tg1_handle[0]['bfd_v4'][0], ipver='4')
        ixia_bfd_params_modify(bfd_handler = data.tg1_handle[i]['bfd_v4'][2], ipver='4')
        ixia_bfd_params_modify(bfd_handler = data.tg1_handle[i]['bfd_v6'][2], ipver='6')

    st.wait(30)

    loop = 0
    loop_max = 3
    while loop < loop_max:
        current_down_session = 0
        current_up_session = 0
        output2  = st.show(dut1, cmd, type='vtysh')
        for i in range(all_session):
            if 'down' == output2[i]['status']:
                current_down_session += 1
                st.log("peer {} status down after bfd vrf test".format(output2[i]['peer']))
            else:
                current_up_session += 1
        if current_down_session > init_down_session:
            loop += 1
            st.wait(30)
        else:
            break

    if current_down_session > init_down_session:
        result=1
        st.log("check bfd status failed")
    
    tg.tg_traffic_control(action='stop', stream_handle=traffic_list)

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
            'tx_ports' : [vars.T1D1P1],
            'tx_obj' : [data.tg_list[0]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D2P1, vars.T1D2P2],
            'rx_obj' : [data.tg_list[4],data.tg_list[5]],
            'stream_list': [[data.streams['port1_to_port5_vrf_503']]]
        },
        '3': {
            'tx_ports' : [vars.T1D1P3],
            'tx_obj' : [data.tg_list[2]],
            'exp_ratio' : [1],        #TG3 use only one 200G port
            'rx_ports' : [vars.T1D1P5],
            'rx_obj' : [data.tg_list[6]],
            'stream_list': [[data.streams['port3_to_port7_vrf_501']]]
        },
        '4': {
            'tx_ports' : [vars.T1D1P5],
            'tx_obj' : [data.tg_list[6]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D1P3, vars.T1D1P4],
            'rx_obj' : [data.tg_list[2], data.tg_list[3]],
            'stream_list': [[data.streams['port7_to_port3_vrf_501']]]
        }
    }
    #check ecmp port
    if not tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock', comp_type='packet_count'):
        st.log("validate_tgen_traffic failed")
        result=1

    if result == 0:
        st.report_pass("test_case_passed")
    else:
        st.report_fail("bfd counter check failed")

@pytest.mark.community
@pytest.mark.community_pass
def test_dut_bfd_flap_in_vrf_503():
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    tg = data.tg_list[0]
    tg_ph = data.tg_ph_list[0]
    result = 0
    init_down_session = 0
    traffic_vrf_503_list = [data.streams['port5_to_port1_vrf_503'], data.streams['port1_to_port5_vrf_503']]
    traffic_vrf_503_v6_list = [data.streams['port5_to_port1_vrf_503_v6'], data.streams['port1_to_port5_vrf_503_v6']]

    cmd = "show bfd peers"
    output1 = st.show(dut1, cmd, type='vtysh')
    all_session = len(output1)
    st.log("get bfd sessions {}".format(all_session))
    for i in range(all_session):
        if 'down' == output1[i]['status']:
            init_down_session += 1
            st.log("peer {} status down before vrf 503 test".format(output1[i]['peer']))

    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)
    tg.tg_traffic_control(action='run', stream_handle=traffic_vrf_503_list)

    flap_timer = '100'
    st.log("config TG bfd flap timer = {}".format(flap_timer))
    ixia_bfd_params_modify(bfd_handler = data.tg1_handle[0]['bfd_v4'][0], flap_interval = flap_timer, ipver='4')
    ixia_bfd_params_modify(bfd_handler = data.tg1_handle[1]['bfd_v4'][0], flap_interval = flap_timer, ipver='4')

    for i in range(5):
        flap_cmd = "router bgp {} vrf {}\n".format(data.dut2_vrf_bgp_as, data.dut1_dut2_bfd_vrf_name[0])
        flap_cmd += "no neighbor dut1_v4 bfd\n"   
        st.config(dut2,flap_cmd, type='alicli',skip_error_check=True)
        st.wait(6)
        flap_cmd = "router bgp {} vrf {}\n".format(data.dut2_vrf_bgp_as, data.dut1_dut2_bfd_vrf_name[0])
        flap_cmd += "neighbor dut1_v4 bfd 3 100 100\n"
        st.config(dut2,flap_cmd, type='alicli',skip_error_check=True)
        st.wait(6)
    #for i in range(5):
    #    flap_cmd = "interface {}\n shutdown\n".format(data.dut_bfd_port_list[0])
    #    st.config(dut2, flap_cmd, type='alicli',skip_error_check=True)
    #    st.wait(5)
    #    flap_cmd = "interface {}\n no shutdown\n".format(data.dut_bfd_port_list[0])
    #    st.config(dut2, flap_cmd, type='alicli',skip_error_check=True)
    #    st.wait(6)
        
    st.log("disable TG bfd flap")
    ixia_bfd_params_modify(bfd_handler = data.tg1_handle[0]['bfd_v4'][0], ipver='4')
    ixia_bfd_params_modify(bfd_handler = data.tg1_handle[1]['bfd_v4'][0], ipver='4')
    st.wait(90)

    loop = 0
    loop_max = 3
    current_down_session = 0
    while loop < loop_max:
        current_up_session = 0
        output2  = st.show(dut1, cmd, type='vtysh')
        for i in range(all_session):
            if 'down' == output2[i]['status']:
                current_down_session += 1
                st.log("peer {} status down after vrf 503 test".format(output2[i]['peer']))
            else:
                current_up_session += 1
        if current_down_session > init_down_session:
            loop += 1
            st.wait(30)
        else:
            break

    if current_down_session > init_down_session:
        result=1
        st.log("check bfd status failed")

    st.log("get bfd status up sessions {} after flap".format(current_up_session))

    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)
    st.wait(20)
    tg.tg_traffic_control(action='stop', stream_handle=traffic_vrf_503_list)
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
            'tx_ports' : [vars.T1D1P1],
            'tx_obj' : [data.tg_list[0]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D2P1, vars.T1D2P2],
            'rx_obj' : [data.tg_list[4],data.tg_list[5]],
            'stream_list': [[data.streams['port1_to_port5_vrf_503']]]
        },
    }
    #check ecmp port
    if not tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock', comp_type='packet_count'):
        st.log("validate_tgen_traffic failed")
        result=2

    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)
    tg.tg_traffic_control(action='run', stream_handle=traffic_vrf_503_v6_list)
    st.wait(20)
    tg.tg_traffic_control(action='stop', stream_handle=traffic_vrf_503_v6_list)
    traffic_details = {
       '1': {
            'tx_ports' : [vars.T1D2P1],
            'tx_obj' : [data.tg_list[4]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D1P1, vars.T1D1P2],
            'rx_obj' : [data.tg_list[0], data.tg_list[1]],
            'stream_list': [[data.streams['port5_to_port1_vrf_503_v6']]]
        },
        '2': {
            'tx_ports' : [vars.T1D1P1],
            'tx_obj' : [data.tg_list[0]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D2P1, vars.T1D2P2],
            'rx_obj' : [data.tg_list[4],data.tg_list[5]],
            'stream_list': [[data.streams['port1_to_port5_vrf_503_v6']]]
        },
    }
    #check ecmp port
    if not tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock', comp_type='packet_count'):
        st.log("validate_tgen_traffic failed")
        result=2
    
    if result == 0:
        st.report_pass("test_case_passed")
    elif result == 1:
        st.report_fail("bfd statue check failed")
    elif result == 2:
        st.report_fail("validate_tgen_traffic failed")

@pytest.mark.community
@pytest.mark.community_pass
def test_bgp_fast_isolate_and_recover():

    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    tg = data.tg_list[0]
    traffic_list = [data.streams['port5_to_port1_vrf_503'], data.streams['port1_to_port5_vrf_503'],
                    data.streams['port3_to_port7_vrf_501'], data.streams['port7_to_port3_vrf_501']]
    test_vrf = data.dut_traffic_vrf_name['503']
    all_route = dict()
    vrf_route = dict()

    loc_lib.dut_load_bgp_isolate_peer_group(dut1, data.dut1_vrf_bgp_as, data.dut2_vrf_bgp_as, test_vrf, data.dut2_all_ip_addr, config='yes')
    loc_lib.dut_load_bgp_isolate_peer_group(dut2, data.dut2_vrf_bgp_as, data.dut1_vrf_bgp_as, test_vrf, data.dut1_all_ip_addr, config='yes')
    st.wait(60)

    for vrf in data.dut_traffic_vrf_name.keys():
        publish_route = 0
        vrf_neigh_list = []
        vrf_route_list = []
        vrf_isolate_route_list = []
        output=bgp_api.show_bgp_ipv4_summary_vtysh(dut2,vrf=data.dut_traffic_vrf_name[vrf])
        for nbr in output:
            if nbr['asn'] == data.dut1_vrf_bgp_as:
                vrf_neigh_list.append(nbr['neighbor'])
                vrf_route_list.append(nbr['state'])
        for ip in data.dut1_all_ip_addr:
            if ip['interface'].startswith('Loopback') and (ip['vrf'] == data.dut_traffic_vrf_name[vrf]):
                publish_route += 1
        for i in range(len(vrf_neigh_list)):
            vrf_isolate_route_list.append(str(publish_route))
        vrf_route['neighbor'] = vrf_neigh_list
        vrf_route['state'] = vrf_route_list
        vrf_route['isolate_state'] = vrf_isolate_route_list
        all_route[data.dut_traffic_vrf_name[vrf]] = copy.deepcopy(vrf_route)

    st.banner("precheck bgp status")
    loc_lib.precheck_bgp_isolate(dut1)
    
    st.banner("start isolate and check")
    isolate_cmd = "isolate fast"
    st.config(dut1, isolate_cmd, type='alicli')
    st.wait(20)

    if not retry_api(loc_lib.check_bgp_isolate, dut=dut1, check_status='isolate', retry_count= 3, delay= 3):
        st.report_fail("bgp isolate execute failed")

    st.wait(90)
    for vrf in data.dut_traffic_vrf_name.keys():
        name = data.dut_traffic_vrf_name[vrf]
        if not retry_api(ip_bgp.check_bgp_session, dut=dut2,nbr_list=all_route[name]['neighbor'], state_list=all_route[name]['isolate_state'], vrf_name=name, retry_count= 5, delay= 10):
            st.report_fail("bgp isolate failed")

    st.wait(30)
    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)
    tg.tg_traffic_control(action='run', stream_handle=traffic_list)
    st.wait(10)
    traffic_details = {
    '1': {
            'tx_ports' : [vars.T1D2P1],
            'tx_obj' : [data.tg_list[4]],
            'exp_ratio' : [0],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D1P1, vars.T1D1P2],
            'rx_obj' : [data.tg_list[0], data.tg_list[1]],
            'stream_list': [[data.streams['port5_to_port1_vrf_503']]]
        },
        '2': {
            'tx_ports' : [vars.T1D1P1],
            'tx_obj' : [data.tg_list[0]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D2P1, vars.T1D2P2],
            'rx_obj' : [data.tg_list[4],data.tg_list[5]],
            'stream_list': [[data.streams['port1_to_port5_vrf_503']]]
        },
        '3': {
            'tx_ports' : [vars.T1D1P3],
            'tx_obj' : [data.tg_list[2]],
            'exp_ratio' : [1],        #TG3 use only one 200G port
            'rx_ports' : [vars.T1D1P5],
            'rx_obj' : [data.tg_list[6]],
            'stream_list': [[data.streams['port3_to_port7_vrf_501']]]
        },
        '4': {
            'tx_ports' : [vars.T1D1P5],
            'tx_obj' : [data.tg_list[6]],
            'exp_ratio' : [0],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D1P3, vars.T1D1P4],
            'rx_obj' : [data.tg_list[2], data.tg_list[3]],
            'stream_list': [[data.streams['port7_to_port3_vrf_501']]]
        }
    }

    #check ecmp port
    if not tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock', comp_type='packet_count'):
        st.report_fail("validate_tgen_traffic failed")
    

    st.banner("recover isolate and check")
    no_isolate_cmd = "no isolate fast"
    st.config(dut1, no_isolate_cmd, type='alicli')
    st.wait(10)

    if not retry_api(loc_lib.check_bgp_isolate, dut=dut1, check_status='no-isolate', retry_count= 3, delay= 3):
        st.report_fail("bgp isolate recover failed")
    
    st.wait(150)
    
    for vrf in data.dut_traffic_vrf_name.keys():
        name = data.dut_traffic_vrf_name[vrf]
        if not retry_api(ip_bgp.check_bgp_session, dut=dut2, nbr_list=all_route[name]['neighbor'], state_list=all_route[name]['state'], vrf_name=name, retry_count= 3, delay= 10):
            st.report_fail("bgp isolate recover failed")
    st.wait(60)

    tg.tg_traffic_control(action='clear_stats', port_handle=data.tg_ph_list)

    st.wait(10)
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
            'tx_ports' : [vars.T1D1P1],
            'tx_obj' : [data.tg_list[0]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D2P1, vars.T1D2P2],
            'rx_obj' : [data.tg_list[4],data.tg_list[5]],
            'stream_list': [[data.streams['port1_to_port5_vrf_503']]]
        },
        '3': {
            'tx_ports' : [vars.T1D1P3],
            'tx_obj' : [data.tg_list[2]],
            'exp_ratio' : [1],        #TG3 use only one 200G port
            'rx_ports' : [vars.T1D1P5],
            'rx_obj' : [data.tg_list[6]],
            'stream_list': [[data.streams['port3_to_port7_vrf_501']]]
        },
        '4': {
            'tx_ports' : [vars.T1D1P5],
            'tx_obj' : [data.tg_list[6]],
            'exp_ratio' : [1],        #two ecmp port, each is 50%
            'rx_ports' : [vars.T1D1P3, vars.T1D1P4],
            'rx_obj' : [data.tg_list[2], data.tg_list[3]],
            'stream_list': [[data.streams['port7_to_port3_vrf_501']]]
        }
    }

    tg.tg_traffic_control(action='stop', stream_handle=traffic_list)

    #check ecmp port
    if not tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock', comp_type='packet_count'):
        st.report_fail("validate_tgen_traffic failed")

    st.report_pass("test_case_passed")
