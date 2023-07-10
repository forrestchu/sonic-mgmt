#
# test_route_miscellaneous.py - some other functions about route test in this file.
#
import pytest
import time
import json
import os

from spytest import st, tgapi, SpyTestDict

import apis.routing.arp as arp_obj
import apis.routing.ip as ip_obj
import apis.system.interface as interface_obj
import apis.switching.vlan as vlan_obj
import apis.switching.mac as mac
import apis.common.wait as waitapi
import BGP.bgplib as bgplib

data = SpyTestDict()
data.d1t1_ip_addr = "192.168.11.1"
data.t1d1_ip_addr = "192.168.11.2"
data.t1d1_mac_addr = "00:00:00:00:00:01"
data.d1t2_ip_addr = "192.168.12.1"
data.t2d1_ip_addr = "192.168.12.2"
data.t2d1_mac_addr = "00:00:00:00:00:02"
data.static_arp_ip_1 = "192.168.11.4"
data.static_arp_mac = "00:00:00:00:00:66"
data.static_arp_ip = "192.168.12.3"
data.static_arp_mac_1 = "00:00:00:00:00:77"
data.mask = "24"
data.vlan_1 = 64
data.vlan_int_1 = "Vlan{}".format(data.vlan_1)
data.clear_parallel = False
data.cli_type = ""
data.dut_asn = 65021
data.tg_asn = 65001
data.dut_max_fib = 64 * 1024 #By default
data.route_count1 = data.dut_max_fib + 100

bgp_json_config = {
    "BGP_NEIGHBOR": {
        "192.168.11.2|global": {
            "in_group": "to_tc"
        },
        "to_tc|global": {
            "admin_status": "up",
            "advertisement_interval": "0",
            "asn": "65001",
            "peer_group": "true"
        },
        "to_tc|ipv4": {
            "activate": "true",
            "soft_reconfiguration_inbound": "true"
        }
    },
    "BGP_PARAMETERS": {
        "65021|global": {
            "bgp_peer_up_delay": "120",
            "bgp_router_id": "10.0.0.191",
            "bgp_timers": "10 30"
        },
        "65021|ipv4": {
            "bgp_maximum_paths": "64"
        },
        "65021|ipv6": {
            "bgp_maximum_paths": "64"
        }
    }
}

def get_zebra_max_fib(dut):
    st.log("start get_bgp_max_fib")
    output = st.show(dut, "ps aux | grep zebra", type= 'click', skip_error_check=True, skip_tmpl=True)
    for line in output.split('\n'):
        if "zebra.conf" not in line:
            continue
        strs = line.split(' ')
        for i in range(0, len(strs)):
            if strs[i] == "-L":
                data.dut_max_fib = int(strs[i + 1])
                data.route_count = data.dut_max_fib + 100

    st.log("max fib: " + str(data.dut_max_fib) + ", test fib: " + str(data.route_count))

def apply_config(dut, config):
    json_config = json.dumps(config)
    json.loads(json_config)
    st.apply_json2(dut, json_config)

def apply_bgp_config(dut, config):
    apply_config(dut, config)
    st.config(dut, "service bgp restart", type= 'click')


@pytest.fixture(scope="module", autouse=True)
def miscellaneous_module_hooks(request):
    ########### module prologue #################
    global vars, tg_handler, tg, dut1, d1_mac_addr, h1, h2
    st.log("pre mod config cli")

    # Min topology verification
    vars = st.ensure_min_topology("D1T1:1")

    # Initialize TG and TG port handlers
    tg_handler = tgapi.get_handles_byname("T1D1P1")
    tg = tg_handler["tg"]

    # Test setup details
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]

    # Test variables
    d1_mac_addr = mac.get_sbin_intf_mac(dut1, "eth0")

    # config DUT IP/BGP
    get_zebra_max_fib(dut1)
    st.log("ARP module configuration.")
    ip_obj.clear_ip_configuration(dut1, family='all', cli_type='alicli', thread=True)
    ip_obj.config_ip_addr_interface(dut1, vars.D1T1P1, data.d1t1_ip_addr, data.mask)
    apply_bgp_config(dut1, bgp_json_config)

    # TG ports reset
    st.log("Resetting the TG ports")
    tg.tg_traffic_control(action="reset", port_handle=tg_handler["tg_ph_list"])

    #config TG interface
    st.log("TG protocol interface creation")
    h1 = tg.tg_interface_config(port_handle=tg_handler["tg_ph_1"], mode='config',
            intf_ip_addr=data.t1d1_ip_addr,gateway=data.d1t1_ip_addr,
            src_mac_addr=data.t1d1_mac_addr,arp_send_req='1')

    yield
    ########### module epilogue #################
    st.log("post mod config cli")

@pytest.fixture(scope="function", autouse=True)
def miscellaneous_func_hooks(request):
    yield

def test_ip_route_and_fib_with_large_routes():
    ################# Author Details ################
    # Name: Yubin Li
    #################################################
    #
    # Objective - 600k routes advertise with BGP, show ip route and ip fib, can see pending route
    #
    ############### Test bed details ################
    #  DUT-----TG
    #################################################
    st.log("start to do route test")

    #config TG BGP
    conf_var = {'mode':'enable', 'active_connect_enable':'1', 'local_as':data.tg_asn, 'remote_as':data.dut_asn, 'remote_ip_addr':data.d1t1_ip_addr}
    route_var = {'mode':'add', 'num_routes':data.route_count, 'prefix':'121.1.1.0', 'as_path':'as_seq:1'}
    ctrl_start = {'mode':'start'}
    bgp_rtr = tgapi.tg_bgp_config(tg=tg, handle=h1, conf_var=conf_var, route_var = route_var, ctrl_var=ctrl_start)
    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        time.sleep(40)
    else:
        time.sleep(10)

    command = 'show ip route | grep -c pending'
    output = st.show(dut1, command, type="alicli", skip_error_check=True, skip_tmpl=True)
    output = output.split('\n')[0]
    if int(output) < data.route_count - data.dut_max_fib:
        st.report_fail("test_case_passed, pending route num is " + output + ", expected " + str(data.route_count - data.dut_max_fib))

    command = 'show ip fib | grep -c pending'
    output = st.show(dut1, command, type="alicli", skip_error_check=True, skip_tmpl=True)
    output = output.split('\n')[0]
    if int(output) < data.route_count - data.dut_max_fib:
        st.report_fail("test_case_passed, pending fib num is " + output + ", expected " + str(data.route_count - data.dut_max_fib))

    command = 'show ip route summary | grep ebgp | awk \'{print $NF}\''
    output = st.show(dut1, command, type="alicli", skip_error_check=True, skip_tmpl=True)
    output = output.split('\n')[0]
    if int(output) != data.route_count:
        st.report_fail("test_case_passed, zebra route num is " + output + ", expected " + str(data.route_count))

    command = 'show ip route summary | grep Dataplane | awk \'{print $NF}\''
    output = st.show(dut1, command, type="alicli", skip_error_check=True, skip_tmpl=True)
    output = output.split('\n')[0]
    expected_max_fib = data.dut_max_fib - 4
    if int(output) != expected_max_fib: # 2 ipv6 default route minus 4
        st.report_fail("test_case_passed, dataplane route num is " + output + ", expected " + str(expected_max_fib))

    st.report_pass("test_case_passed")
