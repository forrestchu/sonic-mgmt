import pytest
import json
from spytest import st,utils
from spytest import st, tgapi, SpyTestDict
from spytest.utils import filter_and_select
from vrf_vars import * #all the variables used for vrf testcase
from vrf_vars import data
import vrf_lib as loc_lib
from utilities import parallel
from apis.system import basic
from apis.common import redis   

import apis.switching.portchannel as pc_api
import apis.system.reboot as reboot
import apis.routing.ip as ip_api
import apis.routing.vrf as vrf_api
import apis.routing.bgp as bgp_api
import apis.routing.ip_bgp as ip_bgp
import apis.routing.arp as arp_api
import apis.system.interface as ifapi

import apis.system.reboot as reboot_api

from spytest.tgen.tg import tgen_obj_dict
from spytest.tgen.tgen_utils import validate_tgen_traffic

def get_handles():
    tg1, tg_ph_1 = tgapi.get_handle_byname("T1D1P1")
    tg2, tg_ph_2 = tgapi.get_handle_byname("T1D1P2")
    return (tg1, tg_ph_1, tg2, tg_ph_2)


data = SpyTestDict()

def apply_mgmt_vrf_json_config(dut, short_vrf, long_vrf):
    final_data, temp_data = dict(), dict()
    data = {"alias_name": long_vrf,
            "mgmtVrfEnabled": "true", 
            "vrf_name": short_vrf}
    temp_data['vrf_global'] = data
    final_data['MGMT_VRF_CONFIG'] = temp_data

    temp_data={}
    temp_data[short_vrf] = {}
    final_data['VRF'] = temp_data

    temp_data={}
    temp_data[long_vrf] = {}
    final_data['VRF_ALIAS'] = temp_data

    data_json = json.dumps(final_data)
    json.loads(data_json)
    st.apply_json(dut, data_json)

@pytest.fixture(scope="module", autouse=True)
def mgmt_vrf_module_hooks(request):
    #add things at the start of this module
    global vars
    vars = st.ensure_min_topology("D1T1:2")
    data.start_ip_addr = "10.2.2.1/24"
    data.vlans = []
    data.dut = vars.D1
    data.neigh_ip_addr = "10.2.2.2/24"
    data.dut_ports = [vars.D1T1P1,vars.D1T1P2]
    data.vrf1 = "sflow-test-12345678-abcdefg"
    data.vrf2 = "Vrf1234"
    data.streams = {}

    (tg1, tg_ph_1, tg2, tg_ph_2) = get_handles()
    tg1.tg_traffic_control(action='reset',port_handle=tg_ph_1)
    tg2.tg_traffic_control(action='reset',port_handle=tg_ph_2)

    base_config()
    yield


def base_config():
    (dut) = (data.dut)
    
    st.banner("Started doing the needed config.")

    ip_addr = data.start_ip_addr
    command = "vrf {}\n".format(data.vrf1)
    command += "vrf {}\n".format(data.vrf2)
    st.config(dut, command, skip_error_check=True, type='alicli')

    command = "interface {}\n".format(data.dut_ports[0])
    command += "vrf {}\n".format(data.vrf1)
    command += "ip address {}\n".format(ip_addr)
    command += "exit\n"
    st.config(dut, command, skip_error_check=True, type='alicli')

    (tg1, tg_ph_1, tg2, tg_ph_2) = get_handles()

    dut1_neigh_ip_addr = data.neigh_ip_addr
    formatted_dut1_neigh_ip_addr = dut1_neigh_ip_addr.replace("/24","")
    h1=tg1.tg_interface_config(port_handle=tg_ph_1, mode='config', intf_ip_addr=formatted_dut1_neigh_ip_addr,
                gateway='10.2.2.1', src_mac_addr='00:0a:01:00:00:01',arp_send_req='1')
    stream = tg2.tg_traffic_config(port_handle=tg_ph_2, mode='create', length_mode='fixed', frame_size='1500',
                                    rate_pps='25600', duration='10',l2_encap='ethernet_ii_vlan',
                                    transmit_mode='continuous', l3_protocol='ipv4',
                                    mac_src='00:0a:01:01:23:01',mac_dst='00:0a:01:01:23:02', ip_src_addr='4.4.4.4',
                                    ip_dst_addr='3.3.3.3', ip_ttl="255",l4_protocol='udp', udp_dst_port='5000')
    st.log('Stream output:{}'.format(stream))
    data.streams['sflow'] = stream['stream_id']

    print(h1)

    apply_mgmt_vrf_json_config(dut, data.vrf2, data.vrf1)
    #command = "copy run start"
    #st.config(dut, command, skip_error_check=True, type='alicli')
    #arp_api.show_arp(dut)

    #st.reboot(dut)
    reboot.config_save_reboot(dut)
    st.wait(30)
    st.log("finish need config")

@pytest.mark.community
@pytest.mark.community_pass
def test_mgmt_vrf_entry_db():
    (dut) = (data.dut)
    string = "MGMT_VRF_CONFIG|vrf_global"
    command = redis.build(dut, redis.CONFIG_DB, "hgetall '{}' ".format(string))
    output = st.show(dut, command)

    st.debug(output)
    match_list = [{"donor_intf": 'true'}, {"donor_intf": data.vrf1}, {"donor_intf": data.vrf2}]
    for match in match_list:
        entries = filter_and_select(output, None, match)
        if not entries:
            st.log("{} is not match".format(match))
            st.report_fail("mgmt long vrf config fail")
    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_mgmt_vrf_by_sflow():
    (dut) = (data.dut)
    dut1_neigh_ip_addr = data.neigh_ip_addr
    formatted_dut1_neigh_ip_addr = dut1_neigh_ip_addr.replace("/24","")

    command = "sflow enable\n"
    command += "sflow collector test1234 ip_address {}\n".format(formatted_dut1_neigh_ip_addr)
    command += "sflow interface {} enable\n".format(data.dut_ports[1])
    command += "sflow interface sample-rate {} 256".format(data.dut_ports[1])
    st.config(dut, command, skip_error_check=True, type='alicli')
    st.wait(5)
    st.show(dut, "show sflow")

    (tg1, tg_ph_1, tg2, tg_ph_2) = get_handles()
    #stats1 = tgapi.get_traffic_stats(tg1, port_handle=tg_ph_1, mode="aggregate")
    tg2.tg_traffic_control(action='clear_stats', port_handle=tg_ph_1)
    tg2.tg_traffic_control(action = 'run', stream_handle = data.streams.get('sflow'))
    st.wait(10)
    tg2.tg_traffic_control(action = 'stop', stream_handle = data.streams.get('sflow'))
    st.wait(5)

    stats1 = tgapi.get_traffic_stats(tg1, port_handle=tg_ph_2, mode="aggregate")
    stats2 = tgapi.get_traffic_stats(tg1, port_handle=tg_ph_1, mode="aggregate")
    total_tx = stats1.tx.total_packets
    total_rx = stats2.rx.total_packets
    st.log("total_tx:{}, total_rx:{}".format(total_tx, total_rx))
    if total_rx > (total_tx/256)/7.5:      #1000 pkt /7.5
        st.report_pass("test_case_passed")
    else:
        st.report_fail("TG rx count not equal with sflow pkt count")