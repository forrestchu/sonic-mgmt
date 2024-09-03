import os
import pytest
from collections import OrderedDict

from spytest import st, tgapi, SpyTestDict
from spytest.utils import filter_and_select
from utilities.utils import retry_api
from apis.common import redis

import apis.common.asic as asicapi
import apis.switching.vlan as vapi
import apis.routing.ip as ipfeature
import apis.switching.mac as macapi
import apis.system.port as papi
import apis.routing.bgp as bgp_api
import apis.routing.arp as arp_obj
import apis.routing.bfd as bfdapi


def get_handles():
    tg1, tg_ph_1 = tgapi.get_handle_byname("T1D1P1")
    tg2, tg_ph_2 = tgapi.get_handle_byname("T1D1P2")
    return (tg1, tg_ph_1, tg2, tg_ph_2)


data = SpyTestDict()

@pytest.fixture(scope="module", autouse=True)
def bfd_module_hooks(request):
    #add things at the start of this module
    global vars
    vars = st.ensure_min_topology("D1T1:2")
    data.start_ip_addr = "10.2.100.1/24"
    data.vlans = []
    data.dut = vars.D1
    data.dut1_start_ip_addr = "10.2.2.1/24"
    data.v6_start_ip_addr = "2100:0:2::1/64"
    data.neigh_v6_ip_addr = "2100:0:2::2/64"
    data.neigh_ip_addr = "10.2.2.2/24"
    data.dut1_ports = [vars.D1T1P1,vars.D1T1P2]
    data.as_num = 178
    data.remote_as_num = 200
    data.new_as_num = 300
    data.vrf = "bfd-test-12345678-abcdefg"
    data.test_bgp_route_count = 100000
    data.sub_intf = 100
    data.dut_bfd_timer = "100"
    data.tg_bfd_timer = "100"

    (tg1, tg_ph_1, tg2, tg_ph_2) = get_handles()
    tg1.tg_traffic_control(action='reset',port_handle=tg_ph_1)
    tg2.tg_traffic_control(action='reset',port_handle=tg_ph_2)

    l3_base_config()
    bfd_base_config()

    yield

    l3_base_unconfig()

def l3_base_config():
    (dut) = (data.dut)
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    vrf_flag = True
    member_dut1 = vars.D1T1P1
    
    st.banner("Started doing the needed config.")

    ip_addr = data.dut1_start_ip_addr
    v6_ip_addr = data.v6_start_ip_addr
    ix_vlan_val = data.sub_intf
    command = "vrf {}\n".format(data.vrf)
    st.config(dut1, command, skip_error_check=True, type='alicli')

    command = "interface sub-interface {} {}\n".format(data.dut1_ports[0], ix_vlan_val)
    command += "vrf {}\n".format(data.vrf)
    command += "ip address {}\n".format(ip_addr)
    command += "exit\n"
    st.config(dut1, command, skip_error_check=True, type='alicli', max_time=500)

    command = "interface sub-interface {} {} \n ipv6 address {}\nexit\n".format(data.dut1_ports[0], ix_vlan_val, v6_ip_addr)
    st.config(dut1, command, skip_error_check=True, type='alicli')
 
    command = "show ndp"
    st.show(dut1, command)

    (tg1, tg_ph_1, tg2, tg_ph_2) = get_handles()

    dut1_neigh_ip_addr = data.neigh_ip_addr
    formatted_dut1_neigh_ip_addr = dut1_neigh_ip_addr.replace("/24","")
    dut1_neigh_v6_ip_addr = data.neigh_v6_ip_addr
    formatted_dut1_neigh_ipv6_addr = dut1_neigh_v6_ip_addr.replace("/64","")

    h1=tg1.tg_interface_config(port_handle=tg_ph_1, mode='config', intf_ip_addr=formatted_dut1_neigh_ip_addr,
                ipv6_intf_addr=formatted_dut1_neigh_ipv6_addr,ipv6_gateway='2100:0:2::1',
                gateway='10.2.2.1', src_mac_addr='00:0a:01:00:00:01', vlan='1', vlan_id='100', arp_send_req='1',
                vlan_user_priority = '7', vlan_user_priority_step='0')
    print(h1)
    arp_obj.show_arp(dut)

    st.banner("init ipv4 part")
    #bgp_api.create_bgp_router(dut, data.as_num, '')
    bgp_api.config_bgp(dut = dut, router_id = '192.0.0.176', local_as=data.as_num, 
        neighbor=formatted_dut1_neigh_ip_addr, remote_as=data.remote_as_num, vrf_name=data.vrf, 
        config_type_list =["neighbor", "activate"], config='yes', cli_type = "alicli")

    (_, dut1_neigh_ip_addr) = ipfeature.increment_ip_addr(dut1_neigh_ip_addr, "network")

    base_vlan = 100
    max_vlan = 101
    #max_vlan = 130
    # The below neighbor config is for inter dut links ibgp
    for index in range(base_vlan, max_vlan):
        formatted_dut1_neigh_ip_addr = dut1_neigh_ip_addr.replace("/24","")
        bgp_api.config_bgp(dut = dut, local_as=data.as_num, neighbor=formatted_dut1_neigh_ip_addr, remote_as=data.new_as_num, 
                            vrf_name=data.vrf, config_type_list =["neighbor", "activate"], config='yes', cli_type = "alicli")
        (_, dut1_neigh_ip_addr) = ipfeature.increment_ip_addr(dut1_neigh_ip_addr, "network")

    conf_var = {'mode'                 : 'enable',
                'active_connect_enable' : '1',
                'local_as'              : '200',
                'remote_as'             : '176',
                'remote_ip_addr'        : '10.2.2.1',
                'bfd_registration'      : '1',
                'bfd_registration_mode' : 'single_hop'
                }
    max_route_str = str(data.test_bgp_route_count)
    route_var = {'mode':'add', 'num_routes':max_route_str, 'prefix':'121.1.1.0', 'as_path':'as_seq:1'}
    ctrl_start = { 'mode' : 'start'}
    ctrl_stop = { 'mode' : 'stop'}


    # Configuring the BGP router.
    bgp_v4_rtr1 = tgapi.tg_bgp_config(tg = tg1,
        handle    = h1['ipv4_handle'],
        conf_var  = conf_var,
        route_var = route_var,
        ctrl_var  = ctrl_start)

    st.log("BGP_V4_HANDLE: "+str(bgp_v4_rtr1))
    # Verified at neighbor.
    st.log("BGP neighborship established.")

    st.log("BFD config start.")
    bfd_v4_rtr1 = tg1.tg_emulation_bfd_config(handle = h1['ipv4_handle'],
        control_plane_independent      = "0",
        enable_demand_mode             = "0",
        flap_tx_interval               = "0",
        min_rx_interval                = data.tg_bfd_timer,
        mode                           = "create",
        detect_multiplier              = "3",
        poll_interval                  = "0",
        tx_interval                    = data.tg_bfd_timer,
        ip_diff_serv                   = "0",
        interface_active               = "1",
        router_active                  = "1",
        session_count                  = "0",
        ip_version                     = "4",
        aggregate_bfd_session          = "1")

    st.log("BFDv4 HANDLE: "+str(bfd_v4_rtr1))
    st.wait(5)
    tg1.tg_emulation_bfd_control(handle = bfd_v4_rtr1['bfd_v4_interface_handle'], mode = "start")
    data.bfd_v4_rtr1 = bfd_v4_rtr1

    st.banner("init ipv6 part")
    v6_dut1_neigh_ip_addr = "2100:0:2::2"
    formatted_dut1_neigh_ipv6_addr = data.neigh_v6_ip_addr.replace("/64","")
    bgp_api.config_bgp(dut = dut, router_id = '192.0.0.176', local_as=data.as_num, 
        neighbor=formatted_dut1_neigh_ipv6_addr, remote_as=data.remote_as_num, vrf_name=data.vrf, 
        config_type_list =["neighbor", "activate"], config='yes', cli_type="alicli", addr_family="ipv6")

    st.log("TG BGPv6 config start.")
    conf_var = {'mode'                 : 'enable',
                'active_connect_enable' : '1',
                'local_as'              : '200',
                'remote_as'             : '176',
                'remote_ipv6_addr'      : '2100:0:2::1',
                'ip_version'            : '6',
                'bfd_registration'      : '1',
                'bfd_registration_mode' : 'single_hop'
                }
    max_route_str = str(data.test_bgp_route_count)
    route_var = {'mode':'add', 'num_routes':max_route_str, 'ip_version':'6', 'prefix':'5100:0:2::1', 'as_path':'as_seq:1'}
    ctrl_start = { 'mode' : 'start'}
    ctrl_stop = { 'mode' : 'stop'}

    # Configuring the BGP router.
    bgp_v6_rtr1 = tgapi.tg_bgp_config(tg = tg1,
        handle    = h1['ipv6_handle'],
        conf_var  = conf_var,
        route_var = route_var,
        ctrl_var  = ctrl_start)
 #   bgp_v6_rtr1=tg1.tg_emulation_bgp_config(handle=h1['ipv6_handle'], mode='enable', ip_version='6',
 #       active_connect_enable='1', local_as='200', remote_as='176', remote_ipv6_addr='2100:0:2::1',
 #       bfd_registration='1', bfd_registration_mode='single_hop')
 #       
 #   tg_emulation_bgp_control(handle=bgp_rtr1['handle'], mode='start')
    
    st.log("BGP_V6_HANDLE: "+str(bgp_v6_rtr1))
    # Verified at neighbor.
    st.log("BGP neighborship established.")

    st.log("TG BFDv6 config start.")
    bfd_v6_rtr1 = tg1.tg_emulation_bfd_config(handle = h1['ipv6_handle'],
        control_plane_independent      = "0",
        enable_demand_mode             = "0",
        flap_tx_interval               = "0",
        min_rx_interval                = data.tg_bfd_timer,
        mode                           = "create",
        detect_multiplier              = "3",
        poll_interval                  = "0",
        tx_interval                    = data.tg_bfd_timer,
        ip_diff_serv                   = "0",
        interface_active               = "1",
        router_active                  = "1",
        session_count                  = "0",
        ip_version                     = "6",
        aggregate_bfd_session          = "1")

    st.log("BFDv6 HANDLE: "+str(bfd_v6_rtr1))
    st.wait(5)
    tg1.tg_emulation_bfd_control(handle = bfd_v6_rtr1['bfd_v6_interface_handle'], mode = "start")
    data.bfd_v6_rtr1 = bfd_v6_rtr1

def l3_base_unconfig():
    (dut) = (data.dut)
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    vrf_flag = True
    member_dut1 = vars.D1T1P1

    st.log("remove l3 base config.")
    #ipfeature.clear_ip_configuration(st.get_dut_names())
    #vapi.clear_vlan_configuration(st.get_dut_names())
    command = "show arp"
    st.show(dut1, command)


def bfd_base_config():
    (dut) = (data.dut)
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut_bfd_timer = int(data.dut_bfd_timer)

    dut1_neigh_ip_addr = data.neigh_ip_addr
    formatted_dut1_neigh_ip_addr = dut1_neigh_ip_addr.replace("/24","")
    bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=formatted_dut1_neigh_ip_addr, config="yes",
                        vrf_name=data.vrf, cli_type='alicli', rx_intv=dut_bfd_timer, tx_intv=dut_bfd_timer)

    dut1_neigh_v6_ip_addr = data.neigh_v6_ip_addr
    formatted_dut1_neigh_v6_ip_addr = dut1_neigh_v6_ip_addr.replace("/64","")
    bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=formatted_dut1_neigh_v6_ip_addr, config="yes",
                        vrf_name=data.vrf, cli_type='alicli', rx_intv=dut_bfd_timer, tx_intv=dut_bfd_timer)
    

@pytest.mark.community
@pytest.mark.community_pass
def test_bfd_ipv4_base():
    (tg1, tg_ph_1, tg2, tg_ph_2) = get_handles()
    (dut) = (data.dut)
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    ip_addr = data.dut1_start_ip_addr
    formatted_dut1_ip_addr = data.dut1_start_ip_addr.replace("/24","")
    neigh_ip_addr = data.neigh_ip_addr.replace("/24","")
    dut_bfd_pps = int(1000/int(data.dut_bfd_timer))


    st.wait(10) # wait hw-bfd work
    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ip_addr, local_addr=formatted_dut1_ip_addr, vrf_name=data.vrf, 
                                rx_interval=[[data.dut_bfd_timer,data.tg_bfd_timer]], status='up', cli_type='alicli'):
        st.report_fail("bfd non-work", ip_addr, dut1)

    pkt = str(10*dut_bfd_pps)
    if not bfdapi.verify_bfd_counters(dut1,cntrlpktout=pkt,cntrlpktin=pkt, peeraddress=neigh_ip_addr, cli_type='alicli'):
        st.report_fail("bfd counter err", ip_addr, dut1)

    # stop ixia to check bfd status
    tg1.tg_emulation_bfd_control(handle = data.bfd_v4_rtr1['handle'], mode = "stop")
    st.wait(10)
    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ip_addr, local_addr=formatted_dut1_ip_addr,  vrf_name=data.vrf, 
                                rx_interval=[[data.dut_bfd_timer,data.tg_bfd_timer]], status='down', cli_type='alicli'):
        st.report_fail("bfd status error", ip_addr, dut1)

    #restart ixia bfd
    tg1.tg_emulation_bfd_control(handle = data.bfd_v4_rtr1['handle'], mode = "start")
    st.wait(10) # wait hw-bfd work
    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ip_addr, local_addr=formatted_dut1_ip_addr, vrf_name=data.vrf, 
                                rx_interval=[[data.dut_bfd_timer,data.tg_bfd_timer]], status='up', cli_type='alicli'):
        st.report_fail("bfd status error", ip_addr, dut1)

    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_bfd_ipv4_flap():
    (tg1, tg_ph_1, tg2, tg_ph_2) = get_handles()
    (dut) = (data.dut)
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    ip_addr = data.dut1_start_ip_addr
    dut1_ip_addr = data.dut1_start_ip_addr.replace("/24","")
    neigh_ip_addr = data.neigh_ip_addr.replace("/24","")

    st.wait(10) # wait hw-bfd work
    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ip_addr, local_addr=dut1_ip_addr, vrf_name=data.vrf, 
                                rx_interval=[[data.dut_bfd_timer,data.tg_bfd_timer]], status='up', cli_type='alicli'):
        st.report_fail("bfd non-work", ip_addr, dut1)


    # config ixia bfd flap
    bfd_pps = 1000/int(data.dut_bfd_timer)
    flap_timer = str(bfd_pps*5)
    st.log("config TG bfd flap timer = {}".format(flap_timer))
    tg1.tg_emulation_bfd_config(handle = data.bfd_v4_rtr1['bfd_v4_interface_handle'],
            control_plane_independent      = "0",
            enable_demand_mode             = "0",
            flap_tx_interval               = flap_timer,
            #min_rx_interval                = data.tg_bfd_timer,
            mode                           = "modify",
            detect_multiplier              = "3",
            poll_interval                  = "0",
            #tx_interval                    = data.tg_bfd_timer,
            ip_diff_serv                   = "0",
            interface_active               = "1",
            router_active                  = "1",
            session_count                  = "0",
            ip_version                     = "4",
            aggregate_bfd_session          = "1")
    tg1.tg_emulation_bfd_control(handle = data.bfd_v4_rtr1['handle'], mode = "restart")
    # wait long time to test flap
    st.wait(100)

    bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=neigh_ip_addr, 
                        config="yes",vrf_name=data.vrf, cli_type='alicli', rx_intv=200, tx_intv=200)

    # disable flap
    tg1.tg_emulation_bfd_config(handle = data.bfd_v4_rtr1['bfd_v4_interface_handle'],
            control_plane_independent      = "0",
            enable_demand_mode             = "0",
            flap_tx_interval               = "0",
            #min_rx_interval                = "200",
            mode                           = "modify",
            detect_multiplier              = "3",
            poll_interval                  = "0",
            #tx_interval                    = "200",
            ip_diff_serv                   = "0",
            interface_active               = "1",
            router_active                  = "1",
            session_count                  = "0",
            ip_version                     = "4",
            aggregate_bfd_session          = "1")
    tg1.tg_emulation_bfd_control(handle = data.bfd_v4_rtr1['handle'], mode = "restart")
    st.wait(60)

    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ip_addr, local_addr=dut1_ip_addr, rx_interval=[['200',data.tg_bfd_timer]], 
                            status='up', cli_type='alicli', vrf_name=data.vrf):
        st.report_fail("bfd status error", ip_addr, dut1)

    bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=neigh_ip_addr, 
                        config="yes",vrf_name=data.vrf, cli_type='alicli', rx_intv=100, tx_intv=100)
    st.wait(5)

    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ip_addr, local_addr=dut1_ip_addr, rx_interval=[['100',data.tg_bfd_timer]], 
                            status='up', cli_type='alicli', vrf_name=data.vrf):
        st.report_fail("bfd status error", ip_addr, dut1)

    bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=neigh_ip_addr, 
                        config="yes",vrf_name=data.vrf, cli_type='alicli', rx_intv=int(data.dut_bfd_timer), tx_intv=int(data.dut_bfd_timer))
    st.wait(5)

    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ip_addr, local_addr=dut1_ip_addr, rx_interval=[[data.dut_bfd_timer,data.tg_bfd_timer]], 
                            status='up', cli_type='alicli', vrf_name=data.vrf):
        st.report_fail("bfd status error", ip_addr, dut1)

    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_bfd_ipv4_attr_set():
    (tg1, tg_ph_1, tg2, tg_ph_2) = get_handles()
    (dut) = (data.dut)
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut1_ip_addr = data.dut1_start_ip_addr.replace("/24","")
    neigh_ip_addr = data.neigh_ip_addr.replace("/24","")

    st.wait(10) # wait hw-bfd work
    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ip_addr, local_addr=dut1_ip_addr, vrf_name=data.vrf, 
                                rx_interval=[[data.dut_bfd_timer,data.tg_bfd_timer]], status='up', cli_type='alicli'):
        st.report_fail("bfd non-work", dut1_ip_addr, dut1)

    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        st.log("bfd status check ok, set dut bfd params: multiplier=3, rx_intv=50, tx_intv=50")
        bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=neigh_ip_addr, 
                            config="yes",vrf_name=data.vrf, cli_type='alicli', multiplier=3, rx_intv=50, tx_intv=50)

        st.wait(5)

        key = "BFD_PEER:{}*".format(neigh_ip_addr)
        command = redis.build(dut1, redis.APPL_DB, "keys '{}' ".format(key))
        output = st.show(dut1, command)
        if output[0]:
            seq_key = output[0]['name']
        else:
            seq_key = ''
        command = redis.build(dut1, redis.APPL_DB, "hgetall '{}' ".format(seq_key))
        output = st.show(dut1, command)

        match_list = [{"donor_intf": '100000'}, {"donor_intf": '100000'}]
        for match in match_list:
            entries = filter_and_select(output, None, match)
            if not entries:
                st.log("{} is not match".format(match))
                st.report_fail("bfd status error", dut1_ip_addr, dut1)

    else:
        st.log("bfd status check ok, set dut bfd params: multiplier=5, rx_intv=50, tx_intv=50")
        bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=neigh_ip_addr, 
                            config="yes",vrf_name=data.vrf, cli_type='alicli', multiplier=5, rx_intv=50, tx_intv=50)
        st.wait(5)

        key = "BFD_PEER:{}*".format(neigh_ip_addr)
        command = redis.build(dut1, redis.APPL_DB, "keys '{}' ".format(key))
        output = st.show(dut1, command)
        if output[0]:
            seq_key = output[0]['name']
        else:
            seq_key = ''
        command = redis.build(dut1, redis.APPL_DB, "hgetall '{}' ".format(seq_key))
        output = st.show(dut1, command)

        match_list = [{"donor_intf": '50000'}, {"donor_intf": '60000'}]
        for match in match_list:
            entries = filter_and_select(output, None, match)
            if not entries:
                st.log("{} is not match".format(match))
                st.report_fail("bfd status error", dut1_ip_addr, dut1)

    #skip multiplier check
    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ip_addr, local_addr=dut1_ip_addr, rx_interval=[['50',data.tg_bfd_timer]], 
                            status='up', cli_type='alicli', vrf_name=data.vrf):
        st.report_fail("bfd status error", dut1_ip_addr, dut1)

    st.log("set TG bfd params")
    # TG BFD params change
    tg1.tg_emulation_bfd_config(handle = data.bfd_v4_rtr1['bfd_v4_interface_handle'],
            control_plane_independent      = "0",
            enable_demand_mode             = "0",
            flap_tx_interval               = "0",
            min_rx_interval                = "50",
            mode                           = "modify",
            detect_multiplier              = "3",
            poll_interval                  = "0",
            tx_interval                    = "50",
            ip_diff_serv                   = "0",
            interface_active               = "1",
            router_active                  = "1",
            session_count                  = "0",
            ip_version                     = "4",
            aggregate_bfd_session          = "1")
    tg1.tg_emulation_bfd_control(handle = data.bfd_v4_rtr1['handle'], mode = "restart")
    st.wait(20)

    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ip_addr, local_addr=dut1_ip_addr, rx_interval=[['50','50']], 
                            status='up', cli_type='alicli', vrf_name=data.vrf):
        st.report_fail("bfd status error", dut1_ip_addr, dut1)

    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        # TG BFD params change
        tg1.tg_emulation_bfd_config(handle = data.bfd_v4_rtr1['bfd_v4_interface_handle'],
                control_plane_independent      = "0",
                enable_demand_mode             = "0",
                flap_tx_interval               = "0",
                min_rx_interval                = "100",
                mode                           = "modify",
                detect_multiplier              = "3",
                poll_interval                  = "0",
                tx_interval                    = "100",
                ip_diff_serv                   = "0",
                interface_active               = "1",
                router_active                  = "1",
                session_count                  = "0",
                ip_version                     = "4",
                aggregate_bfd_session          = "1")
        tg1.tg_emulation_bfd_control(handle = data.bfd_v4_rtr1['handle'], mode = "restart")
        st.wait(20)

        bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=neigh_ip_addr, 
                            config="yes",vrf_name=data.vrf, cli_type='alicli', multiplier=3, rx_intv=int(data.dut_bfd_timer), tx_intv=int(data.dut_bfd_timer))
        st.wait(5)

        if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ip_addr, local_addr=dut1_ip_addr, rx_interval=[[data.dut_bfd_timer,'100']], 
                                status='up', cli_type='alicli', vrf_name=data.vrf):
            st.report_fail("bfd status error", dut1_ip_addr, dut1)

    else:
        bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=neigh_ip_addr, 
                            config="yes",vrf_name=data.vrf, cli_type='alicli', multiplier=3, rx_intv=int(data.dut_bfd_timer), tx_intv=int(data.dut_bfd_timer))
        st.wait(5)

        if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ip_addr, local_addr=dut1_ip_addr, rx_interval=[[data.dut_bfd_timer,'50']], 
                                status='up', cli_type='alicli', vrf_name=data.vrf):
            st.report_fail("bfd status error", dut1_ip_addr, dut1)

    st.report_pass("test_case_passed")


@pytest.mark.community
@pytest.mark.community_pass
def test_bfd_ipv6_base():

    (tg1, tg_ph_1, tg2, tg_ph_2) = get_handles()
    (dut) = (data.dut)
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    formatted_dut1_ipv6_addr = data.v6_start_ip_addr.replace("/64","")
    neigh_ipv6_addr = data.neigh_v6_ip_addr.replace("/64","")
    dut_bfd_pps = int(1000/int(data.dut_bfd_timer))

    st.wait(10) # wait hw-bfd work
    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ipv6_addr, local_addr=formatted_dut1_ipv6_addr, vrf_name=data.vrf, 
                                rx_interval=[[data.dut_bfd_timer,data.tg_bfd_timer]], status='up', cli_type='alicli'):
        st.report_fail("bfd non-work", formatted_dut1_ipv6_addr, dut1)

    pkt = str(10*dut_bfd_pps)
    if not bfdapi.verify_bfd_counters(dut1,cntrlpktout=pkt,cntrlpktin=pkt, peeraddress=neigh_ipv6_addr, cli_type='alicli'):
        st.report_fail("bfd counter err", formatted_dut1_ipv6_addr, dut1)

    # stop ixia to check bfd status
    st.log("stop ixia bfdv6 peer")
    tg1.tg_emulation_bfd_control(handle = data.bfd_v6_rtr1['bfd_v6_interface_handle'], mode = "stop")
    st.wait(5)

    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ipv6_addr, local_addr=formatted_dut1_ipv6_addr,  vrf_name=data.vrf, 
                                rx_interval=[[data.dut_bfd_timer,data.tg_bfd_timer]], status='down', cli_type='alicli'):
        st.report_fail("bfd status error", formatted_dut1_ipv6_addr, dut1)

    #restart ixia bfd
    st.log("start ixia bfdv6 peer")
    tg1.tg_emulation_bfd_control(handle = data.bfd_v6_rtr1['bfd_v6_interface_handle'], mode = "start")
    st.wait(10) # wait hw-bfd work
    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ipv6_addr, local_addr=formatted_dut1_ipv6_addr, vrf_name=data.vrf, 
                                rx_interval=[[data.dut_bfd_timer,data.tg_bfd_timer]], status='up', cli_type='alicli'):
        st.report_fail("bfd status error", formatted_dut1_ipv6_addr, dut1)
    st.show(dut, "show ndp")
    st.report_pass("test_case_passed")


@pytest.mark.community
@pytest.mark.community_pass
def test_bfd_ipv6_flap():
    (tg1, tg_ph_1, tg2, tg_ph_2) = get_handles()
    (dut) = (data.dut)
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut1_ipv6_addr = data.v6_start_ip_addr.replace("/64","")
    neigh_ipv6_addr = data.neigh_v6_ip_addr.replace("/64","")

    st.wait(10) # wait hw-bfd work
    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ipv6_addr, local_addr=dut1_ipv6_addr, vrf_name=data.vrf, 
                                rx_interval=[[data.dut_bfd_timer,data.tg_bfd_timer]], status='up', cli_type='alicli'):
        st.report_fail("bfd non-work", dut1_ipv6_addr, dut1)


    # config ixia bfd flap
    bfd_pps = 1000/int(data.dut_bfd_timer)
    flap_timer = str(bfd_pps*5)
    st.banner("config TG bfd flap timer = {}".format(flap_timer))
    tg1.tg_emulation_bfd_config(handle = data.bfd_v6_rtr1['bfd_v6_interface_handle'],
            control_plane_independent      = "0",
            enable_demand_mode             = "0",
            flap_tx_interval               = flap_timer,
            #min_rx_interval                = data.tg_bfd_timer,
            mode                           = "modify",
            detect_multiplier              = "3",
            poll_interval                  = "0",
            #tx_interval                    = data.tg_bfd_timer,
            ip_diff_serv                   = "0",
            interface_active               = "1",
            router_active                  = "1",
            session_count                  = "0",
            ip_version                     = "6",
            aggregate_bfd_session          = "1")
    tg1.tg_emulation_bfd_control(handle = data.bfd_v6_rtr1['bfd_v6_interface_handle'], mode = "restart")
    # wait long time to test flap
    st.wait(100)

    bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=neigh_ipv6_addr, 
                        config="yes",vrf_name=data.vrf, cli_type='alicli', rx_intv=200, tx_intv=200)

    st.banner("disable TG bfd flap")
    # disable flap
    tg1.tg_emulation_bfd_config(handle = data.bfd_v6_rtr1['bfd_v6_interface_handle'],
            control_plane_independent      = "0",
            enable_demand_mode             = "0",
            flap_tx_interval               = "0",
            #min_rx_interval                = "200",
            mode                           = "modify",
            detect_multiplier              = "3",
            poll_interval                  = "0",
            #tx_interval                    = "200",
            ip_diff_serv                   = "0",
            interface_active               = "1",
            router_active                  = "1",
            session_count                  = "0",
            ip_version                     = "6",
            aggregate_bfd_session          = "1")
    tg1.tg_emulation_bfd_control(handle = data.bfd_v6_rtr1['bfd_v6_interface_handle'], mode = "restart")
    st.wait(60)

    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ipv6_addr, local_addr=dut1_ipv6_addr, rx_interval=[['200',data.tg_bfd_timer]], 
                            status='up', cli_type='alicli', vrf_name=data.vrf):
        st.report_fail("bfd status error", dut1_ipv6_addr, dut1)

    bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=neigh_ipv6_addr, 
                        config="yes",vrf_name=data.vrf, cli_type='alicli', rx_intv=100, tx_intv=100)
    st.wait(5)

    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ipv6_addr, local_addr=dut1_ipv6_addr, rx_interval=[['100',data.tg_bfd_timer]], 
                            status='up', cli_type='alicli', vrf_name=data.vrf):
        st.report_fail("bfd status error", dut1_ipv6_addr, dut1)

    bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=neigh_ipv6_addr, 
                        config="yes",vrf_name=data.vrf, cli_type='alicli', rx_intv=int(data.dut_bfd_timer), tx_intv=int(data.dut_bfd_timer))
    st.wait(5)

    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ipv6_addr, local_addr=dut1_ipv6_addr, rx_interval=[[data.dut_bfd_timer,data.tg_bfd_timer]], 
                            status='up', cli_type='alicli', vrf_name=data.vrf):
        st.report_fail("bfd status error", dut1_ipv6_addr, dut1)

    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_bfd_ipv6_attr_set():
    (tg1, tg_ph_1, tg2, tg_ph_2) = get_handles()
    (dut) = (data.dut)
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut1_ipv6_addr = data.v6_start_ip_addr.replace("/64","")
    neigh_ipv6_addr = data.neigh_v6_ip_addr.replace("/64","")
    new_interval = 50

    st.wait(10) # wait hw-bfd work
    if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ipv6_addr, local_addr=dut1_ipv6_addr, vrf_name=data.vrf, 
                                rx_interval=[[data.dut_bfd_timer,data.tg_bfd_timer]], status='up', cli_type='alicli'):
        st.report_fail("bfd non-work", dut1_ipv6_addr, dut1)

    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        st.log("bfd status check ok, set dut bfd params: multiplier=3, rx_intv=50, tx_intv=50")
        bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=neigh_ipv6_addr, 
                            config="yes",vrf_name=data.vrf, cli_type='alicli', multiplier=3, rx_intv=new_interval, tx_intv=new_interval)
        st.wait(20)
        
        key = "BFD_PEER:{}*".format(neigh_ipv6_addr)
        command = redis.build(dut1, redis.APPL_DB, "keys '{}' ".format(key))
        output = st.show(dut1, command)
        if output[0]:
            seq_key = output[0]['name']
        else:
            seq_key = ''
        command = redis.build(dut1, redis.APPL_DB, "hgetall '{}' ".format(seq_key))
        output = st.show(dut1, command)
        # RFC 5880, Section 6.8.7.
        # transmission time will be determined by the system with the slowest rate.
        match_list = [{"donor_intf": '100000'}, {"donor_intf": '100000'}]
        for match in match_list:
            entries = filter_and_select(output, None, match)
            if not entries:
                st.log("{} is not match".format(match))
                st.report_fail("bfd status error", dut1_ipv6_addr, dut1)

        #skip multiplier check
        if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ipv6_addr, local_addr=dut1_ipv6_addr, rx_interval=[['50',data.tg_bfd_timer]], 
                                status='up', cli_type='alicli', vrf_name=data.vrf):
            st.report_fail("bfd status error", dut1_ipv6_addr, dut1)

    else:
        st.log("bfd status check ok, set dut bfd params: multiplier=5, rx_intv=50, tx_intv=50")
        bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=neigh_ipv6_addr, 
                            config="yes",vrf_name=data.vrf, cli_type='alicli', multiplier=5, rx_intv=new_interval, tx_intv=new_interval)
        st.wait(10)
        
        key = "BFD_PEER:{}*".format(neigh_ipv6_addr)
        command = redis.build(dut1, redis.APPL_DB, "keys '{}' ".format(key))
        output = st.show(dut1, command)
        if output[0]:
            seq_key = output[0]['name']
        else:
            seq_key = ''
        command = redis.build(dut1, redis.APPL_DB, "hgetall '{}' ".format(seq_key))
        output = st.show(dut1, command)
        match_list = [{"donor_intf": '50000'}, {"donor_intf": '60000'}]
        for match in match_list:
            entries = filter_and_select(output, None, match)
            if not entries:
                st.log("{} is not match".format(match))
                st.report_fail("bfd status error", dut1_ipv6_addr, dut1)

        #skip multiplier check
        if not bfdapi.verify_bfd_peer(dut1, peer=neigh_ipv6_addr, local_addr=dut1_ipv6_addr, rx_interval=[['50',data.tg_bfd_timer]], 
                                status='up', cli_type='alicli', vrf_name=data.vrf):
            st.report_fail("bfd status error", dut1_ipv6_addr, dut1)

    st.log("set TG bfd params")
    # TG BFD params change
    tg1.tg_emulation_bfd_config(handle = data.bfd_v6_rtr1['bfd_v6_interface_handle'],
            control_plane_independent      = "0",
            enable_demand_mode             = "0",
            flap_tx_interval               = "0",
            min_rx_interval                = "50",
            mode                           = "modify",
            detect_multiplier              = "3",
            poll_interval                  = "0",
            tx_interval                    = "50",
            ip_diff_serv                   = "0",
            interface_active               = "1",
            router_active                  = "1",
            session_count                  = "0",
            ip_version                     = "6",
            aggregate_bfd_session          = "1")
    tg1.tg_emulation_bfd_control(handle = data.bfd_v6_rtr1['bfd_v6_interface_handle'], mode = "restart")
    st.wait(5)

    if not retry_api(bfdapi.verify_bfd_peer, dut=dut1, peer=neigh_ipv6_addr, local_addr=dut1_ipv6_addr, rx_interval=[['50','50']], 
                            status='up', cli_type='alicli', vrf_name=data.vrf, retry_count= 3, delay= 3):
        st.report_fail("bfd status error", dut1_ipv6_addr, dut1)

    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        # TG BFD params change
        tg1.tg_emulation_bfd_config(handle = data.bfd_v4_rtr1['bfd_v4_interface_handle'],
                control_plane_independent      = "0",
                enable_demand_mode             = "0",
                flap_tx_interval               = "0",
                min_rx_interval                = "100",
                mode                           = "modify",
                detect_multiplier              = "3",
                poll_interval                  = "0",
                tx_interval                    = "100",
                ip_diff_serv                   = "0",
                interface_active               = "1",
                router_active                  = "1",
                session_count                  = "0",
                ip_version                     = "4",
                aggregate_bfd_session          = "1")
        tg1.tg_emulation_bfd_control(handle = data.bfd_v4_rtr1['handle'], mode = "restart")
        st.wait(20)

        bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=neigh_ipv6_addr, 
                            config="yes",vrf_name=data.vrf, cli_type='alicli', multiplier=3, rx_intv=int(data.dut_bfd_timer), tx_intv=int(data.dut_bfd_timer))
        st.wait(5)
        if not retry_api(bfdapi.verify_bfd_peer, dut1, peer=neigh_ipv6_addr, local_addr=dut1_ipv6_addr, rx_interval=[[data.dut_bfd_timer,'50']], 
                                status='up', cli_type='alicli', vrf_name=data.vrf, retry_count= 3, delay= 3):
            st.report_fail("bfd status error", dut1_ipv6_addr, dut1)

    else:
        bfdapi.configure_bfd(dut1, local_asn=data.as_num, neighbor_ip=neigh_ipv6_addr, 
                            config="yes",vrf_name=data.vrf, cli_type='alicli', multiplier=3, rx_intv=int(data.dut_bfd_timer), tx_intv=int(data.dut_bfd_timer))
        st.wait(5)
        if not retry_api(bfdapi.verify_bfd_peer, dut1, peer=neigh_ipv6_addr, local_addr=dut1_ipv6_addr, rx_interval=[[data.dut_bfd_timer,'50']], 
                                status='up', cli_type='alicli', vrf_name=data.vrf, retry_count= 3, delay= 3):
            st.report_fail("bfd status error", dut1_ipv6_addr, dut1)

    st.report_pass("test_case_passed")
