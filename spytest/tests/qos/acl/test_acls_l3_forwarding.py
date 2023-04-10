import pprint
import pytest
import json

from spytest import st, tgapi, SpyTestDict

import apis.qos.acl as acl_obj
import tests.qos.acl.acl_json_config as acl_data
import tests.qos.acl.acl_utils as acl_utils
import apis.switching.portchannel as pc_obj
import apis.routing.ip as ip_obj
import apis.routing.arp as arp_obj
import apis.system.basic as basic_obj
import utilities.common as utils
from utilities.parallel import ensure_no_exception
pp = pprint.PrettyPrinter(indent=4)
import apis.routing.vrf as vrf_api
from utilities import parallel

SUBPORT_PREFIX = 'Eth'
SUBPORTCHANNEL_PREFIX = 'PC'
SUB_INTERFACE_SEPARATOR = "."
vars = dict()
data = SpyTestDict()
data.rate_pps = 100
data.pkts_per_burst = 10
data.tx_timeout = 2
data.TBD = 10
data.portChannelName = "PortChannel111"
data.tg_type = 'ixia'
data.ipv4_address_D1 = "1.1.1.1"
data.ipv4_address_D2 = "2.2.2.1"
data.ipv4_portchannel_D1 = "192.168.1.1"
data.ipv4_portchannel_D2 = "192.168.1.2"
data.ipv4_network_D1 = "1.1.1.0/24"
data.ipv4_network_D2 = "2.2.2.0/24"
data.ipv6_address_D1 = "1001::1"
data.ipv6_address_D2 = "2001::1"
data.ipv6_portchannel_D1 = "3001::1"
data.ipv6_portchannel_D2 = "3001::2"
data.ipv6_network_D1 = "1001::0/64"
data.ipv6_network_D2 = "2001::0/64"
data.acl_type = "ipv6"
data.pbr_primaryport = {"IN":"Ethernet34","OUT":"Ethernet35"}
data.pbr_port = {"IN":"Eth34.100", "OUT":"Eth35.100"}
data.pbr_ipv4 = {"IN":"172.10.1.1", "OUT":"172.10.2.1"}
data.pbr_ipv6 = {"IN":"3100::1", "OUT":"3200::1"}
data.pbr_vrfname = "ACTN_TC1"
data.pbr_acl = {'V4':'PBRV4', 'V6':'PBRV6'}

def print_log(msg):
    log_start = "\n================================================================================\n"
    log_end = "\n================================================================================"
    st.log("{} {} {}".format(log_start, msg, log_end))


def get_handles():
    '''
    ######################## Topology ############################

               +---------+                  +-------+
               |         +------------------+       |
      TG1 -----|  DUT1   |  portchannel     |  DUT2 +----- TG2
               |         +------------------+       |
               +---------+                  +-------+

    ##############################################################
    '''
    global vars
    vars = st.ensure_min_topology("D1D2:2", "D1T1:1", "D2T1:1")
    tg1, tg_ph_1 = tgapi.get_handle_byname("T1D1P1")
    tg2, tg_ph_2 = tgapi.get_handle_byname("T1D2P1")
    if tg1.tg_type == 'stc': data.tg_type = 'stc'
    tg1.tg_traffic_control(action="reset", port_handle=tg_ph_1)
    tg2.tg_traffic_control(action="reset", port_handle=tg_ph_2)
    return (tg1, tg2, tg_ph_1, tg_ph_2)


def apply_module_configuration():
    print_log("Applying module configuration")

    data.dut1_lag_members = [vars.D1D2P1, vars.D1D2P2]
    data.dut2_lag_members = [vars.D2D1P1, vars.D2D1P2]

    # create portchannel
    utils.exec_all(True, [
        utils.ExecAllFunc(pc_obj.create_portchannel, vars.D1, data.portChannelName),
        utils.ExecAllFunc(pc_obj.create_portchannel, vars.D2, data.portChannelName),
    ])

    # add portchannel members
    utils.exec_all(True, [
        utils.ExecAllFunc(pc_obj.add_portchannel_member, vars.D1, data.portChannelName, data.dut1_lag_members),
        utils.ExecAllFunc(pc_obj.add_portchannel_member, vars.D2, data.portChannelName, data.dut2_lag_members),
    ])


def clear_module_configuration():
    print_log("Clearing module configuration")
    # delete Ipv4 address
    print_log("Delete ip address configuration:")
    ip_obj.clear_ip_configuration([vars.D1, vars.D2], family='ipv4')
    # delete Ipv6 address
    ip_obj.clear_ip_configuration([vars.D1, vars.D2], family='ipv6')
    # delete ipv4 static routes
    ip_obj.delete_static_route(vars.D1, data.ipv4_portchannel_D2, data.ipv4_network_D2, shell="vtysh",
                               family="ipv4")
    ip_obj.delete_static_route(vars.D2, data.ipv4_portchannel_D1, data.ipv4_network_D1, shell="vtysh",
                               family="ipv4")
    # delete ipv6 static routes
    ip_obj.delete_static_route(vars.D1, data.ipv6_portchannel_D2, data.ipv6_network_D2, shell="vtysh",
                               family="ipv6")
    ip_obj.delete_static_route(vars.D2, data.ipv6_portchannel_D1, data.ipv6_network_D1, shell="vtysh",
                               family="ipv6")
    # delete port channel members
    print_log("Deleting members from port channel:")
    utils.exec_all(True, [
        utils.ExecAllFunc(pc_obj.delete_portchannel_member, vars.D1, data.portChannelName, data.dut1_lag_members),
        utils.ExecAllFunc(pc_obj.delete_portchannel_member, vars.D2, data.portChannelName, data.dut2_lag_members),
    ])
    # delete port channel
    print_log("Deleting port channel configuration:")
    utils.exec_all(True, [
        utils.ExecAllFunc(pc_obj.delete_portchannel, vars.D1, data.portChannelName),
        utils.ExecAllFunc(pc_obj.delete_portchannel, vars.D2, data.portChannelName),
    ])
    # delete acl tables and rules
    print_log("Deleting ACLs:")

    [_, exceptions] = utils.exec_all(True, [[acl_obj.acl_delete, vars.D1], [acl_obj.acl_delete, vars.D2]])
    ensure_no_exception(exceptions)
    #Clear static arp entries
    print_log("Clearing ARP entries")
    arp_obj.clear_arp_table(vars.D1)
    arp_obj.clear_arp_table(vars.D2)
    #Clear static ndp entries
    print_log("Clearing NDP entries")
    arp_obj.clear_ndp_table(vars.D1)
    arp_obj.clear_ndp_table(vars.D2)

def add_port_to_acl_table(config, table_name, port):
    config['ACL_TABLE'][table_name]['ports'].append(port)


def apply_acl_config(dut, config):
    json_config = json.dumps(config)
    json.loads(json_config)
    st.apply_json2(dut, json_config)


def create_streams_subport(tx_tg, rx_tg, rules, match, mac_src, mac_dst, vlan_id):
    # use the ACL rule definitions to create match/non-match traffic streams
    # instead of hard coding the traffic streams
    my_args = {
        'port_handle': data.tgmap[tx_tg]['handle'], 'mode': 'create', 'frame_size': '128',
        'transmit_mode': 'continuous', 'length_mode': 'fixed', 'duration': 1,
        'l2_encap': 'ethernet_ii_vlan', 'rate_pps': data.rate_pps,
        'high_speed_result_analysis': 0, 'mac_src': mac_src, 'mac_dst': mac_dst, 'vlan_id': vlan_id, 'vlan_id_count': 1,
        'port_handle2': data.tgmap[rx_tg]['handle']
    }

    for rule, attributes in rules.items():
        if ("IP_TYPE" in attributes) or ("ETHER_TYPE" in attributes):
            continue
        if ("PermiAny" in rule):
            continue

        if match in rule:
            params = {}
            tmp = dict(my_args)
            for key, value in attributes.items():
                params.update(acl_utils.get_args_l3(key, value, attributes, data.rate_pps, data.tg_type))
            tmp.update(params)
            st.log("stream info")
            st.log(rule)
            st.log(tmp['port_handle'])
            st.log(tmp['port_handle2'])
            stream = data.tgmap[tx_tg]['tg'].tg_traffic_config(**tmp)
            stream_id = stream['stream_id']
            s = {}
            s[stream_id] = attributes
            s[stream_id]['TABLE'] = rule
            data.tgmap[tx_tg]['streams'].update(s)

def create_streams(tx_tg, rx_tg, rules, match, mac_src, mac_dst):
    # use the ACL rule definitions to create match/non-match traffic streams
    # instead of hard coding the traffic streams
    my_args = {
        'port_handle': data.tgmap[tx_tg]['handle'], 'mode': 'create', 'frame_size': '128',
        'transmit_mode': 'continuous', 'length_mode': 'fixed', 'duration': 1,
        'l2_encap': 'ethernet_ii_vlan', 'rate_pps': data.rate_pps,
        'high_speed_result_analysis': 0, 'mac_src': mac_src, 'mac_dst': mac_dst,
        'port_handle2': data.tgmap[rx_tg]['handle']
    }

    for rule, attributes in rules.items():
        if ("IP_TYPE" in attributes) or ("ETHER_TYPE" in attributes):
            continue
        if ("PermiAny" in rule):
            continue

        if match in rule:
            params = {}
            tmp = dict(my_args)
            for key, value in attributes.items():
                params.update(acl_utils.get_args_l3(key, value, attributes, data.rate_pps, data.tg_type))
            tmp.update(params)
            st.log("stream info")
            st.log(rule)
            st.log(tmp['port_handle'])
            st.log(tmp['port_handle2'])
            stream = data.tgmap[tx_tg]['tg'].tg_traffic_config(**tmp)
            stream_id = stream['stream_id']
            s = {}
            s[stream_id] = attributes
            s[stream_id]['TABLE'] = rule
            data.tgmap[tx_tg]['streams'].update(s)


def transmit(tg):
    print_log("Transmitting streams")
    data.tgmap[tg]['tg'].tg_traffic_control(action='run', stream_handle=list(data.tgmap[tg]['streams'].keys()),
                                            duration=1)


def verify_acl_hit_counters(dut, table_name, acl_type="ip"):
    result = True
    acl_rule_counters = acl_obj.show_acl_counters(dut, acl_type=acl_type, acl_table=table_name)
    for rule in acl_rule_counters:
        if 'PermiAny' not in rule['rulename'] and rule['packetscnt'] == 0:
            return False
    return result


def verify_packet_count(tx, tx_port, rx, rx_port, table):
    result = True
    tg_tx = data.tgmap[tx]
    tg_rx = data.tgmap[rx]
    exp_ratio = 0
    attr_list = []
    traffic_details = dict()
    action_list = []
    index = 0
    for s_id, attr in tg_tx['streams'].items():
        if table in attr['TABLE'] and 'PermitAny' not in attr['TABLE']:
            index = index + 1
            if attr["PACKET_ACTION"] == "FORWARD":
                exp_ratio = 1
                action = "FORWARD"
            else:
                exp_ratio = 0
                action = "DROP"
            traffic_details[str(index)] = {
                    'tx_ports': [tx_port],
                    'tx_obj': [tg_tx["tg"]],
                    'exp_ratio': [exp_ratio],
                    'rx_ports': [rx_port],
                    'rx_obj': [tg_rx["tg"]],
                    'stream_list': [[s_id]]
                }
            attr_list.append(attr)
            action_list.append(action)
    result_all = tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock',
                                    comp_type='packet_count', return_all=1, delay_factor=1.2)
    for result1, action, attr in zip(result_all[1], action_list, attr_list):
        result = result and result1
        if result1:
            if action == "FORWARD":
                msg = "Traffic successfully forwarded for the rule: {}".format(json.dumps(attr))
                print_log(msg)
            else:
                msg = "Traffic successfully dropped for the rule: {}".format(json.dumps(attr))
                print_log(msg)
        else:
            if action == "FORWARD":
                msg = "Traffic failed to forward for the rule: {}".format(json.dumps(attr))
                print_log(msg)
            else:
                msg = "Traffic failed to drop for the rule: {}".format(json.dumps(attr))
                print_log(msg)
    return result


def initialize_topology():
    print_log("Initializing Topology")
    (tg1, tg2, tg_ph_1, tg_ph_2) = get_handles()
    data.tgmap = {
        "tg1": {
            "tg": tg1,
            "handle": tg_ph_1,
            "streams": {}
        },
        "tg2": {
            "tg": tg2,
            "handle": tg_ph_2,
            "streams": {}
        }
    }
    data.vars = vars


@pytest.fixture(scope="module", autouse=True)
def acl_v4_module_hooks(request):
    # initialize topology
    initialize_topology()

    # apply module configuration
    apply_module_configuration()

    acl_config1 = acl_data.acl_json_config_v4_l3_traffic
    add_port_to_acl_table(acl_config1, 'L3_IPV4_INGRESS', vars.D1T1P1)


    acl_config2 = acl_data.acl_json_config_v6_l3_traffic
    add_port_to_acl_table(acl_config2, 'L3_IPV6_INGRESS', vars.D2T1P1)


    # creating ACL tables and rules
    print_log('Creating ACL tables and rules')
    utils.exec_all(True, [
        utils.ExecAllFunc(acl_obj.apply_acl_config, vars.D1, acl_config1),
        utils.ExecAllFunc(acl_obj.apply_acl_config, vars.D2, acl_config2),
    ])

    # create streams
    data.mac1 = basic_obj.get_ifconfig_ether(vars.D1, vars.D1T1P1)
    data.mac2 = basic_obj.get_ifconfig_ether(vars.D2, vars.D2T1P1)
    data.mac3 = basic_obj.get_ifconfig_ether(vars.D1, vars.D1T1P2)
    print_log('Creating streams')
    create_streams("tg1", "tg2", acl_config1['ACL_RULE'], "L3_IPV4_INGRESS", \
                   mac_src="00:0a:01:00:00:01", mac_dst=data.mac1)
    create_streams("tg1", "tg2", acl_config2['ACL_RULE'], "L3_IPV6_EGRESS", \
                   mac_src="00:0a:01:00:00:01", mac_dst="00:0a:01:00:11:02")
    create_streams("tg2", "tg1", acl_config2['ACL_RULE'], "L3_IPV6_INGRESS", \
                   mac_src="00:0a:01:00:11:02", mac_dst=data.mac2)
    create_streams("tg2", "tg1", acl_config1['ACL_RULE'], "L3_IPV4_EGRESS", \
                   mac_src="00:0a:01:00:11:02", mac_dst="00:0a:01:00:00:01")
    
    #pbr
    tg3, tg_ph_3 = tgapi.get_handle_byname("T1D1P2")
    tg4, tg_ph_4 = tgapi.get_handle_byname("T1D1P3")
    data.tgmap['tg3'] = {
        "tg": tg3,
        "handle": tg_ph_3,
        "streams": {}
    }
    data.tgmap['tg4'] = {
        "tg": tg4,
        "handle": tg_ph_4,
        "streams": {}
    }
    stream_v4_pbr = tg3.tg_traffic_config(port_handle=tg_ph_3, port_handle2=tg_ph_4,
                               mode='create', transmit_mode='single_burst',
                               pkts_per_burst=10000, 
                               length_mode='fixed', rate_pps=5000, l3_protocol='ipv4', 
                               mac_src="00:11:01:00:11:02", mac_dst=data.mac3, 
                               vlan_id=100, vlan_id_count=1,
                               ip_src_addr="172.10.1.2", ip_dst_addr="172.10.2.2", ip_dscp=10)

    stream_id = stream_v4_pbr['stream_id']
    s = {}
    s[stream_id] = {}
    s[stream_id]['TABLE'] = data.pbr_acl['V4']
    data.tgmap['tg3']['streams'].update(s)
    
    #pbrv6 stream
    stream_v6_pbr = tg4.tg_traffic_config(port_handle=tg_ph_3, port_handle2=tg_ph_4,
                               mode='create', transmit_mode='single_burst',
                               pkts_per_burst=10000, 
                               length_mode='fixed', rate_pps=5000, l3_protocol='ipv6', 
                               mac_src="00:22:01:00:11:02", mac_dst=data.mac3, 
                               vlan_id=100, vlan_id_count=1,
                               ipv6_src_addr="3100::2", ipv6_dst_addr="3200::2", ipv6_traffic_class=40) #dscp 10 = traffic class 40 = 1010 00 
    stream_id = stream_v6_pbr['stream_id']
    s = {}
    s[stream_id] = {}
    s[stream_id]['TABLE'] = data.pbr_acl['V6']
    data.tgmap['tg4']['streams'].update(s)

    print_log('Completed module configuration')

    st.log("Configuring ipv4 address on ixia connected interfaces and portchannels present on both the DUTs")
    ip_obj.config_ip_addr_interface(vars.D1, vars.D1T1P1, data.ipv4_address_D1, 24, family="ipv4", config='add')
    ip_obj.config_ip_addr_interface(vars.D2, vars.D2T1P1, data.ipv4_address_D2, 24, family="ipv4", config='add')
    ip_obj.config_ip_addr_interface(vars.D1, data.portChannelName, data.ipv4_portchannel_D1, 24, family="ipv4",
                                    config='add')
    ip_obj.config_ip_addr_interface(vars.D2, data.portChannelName, data.ipv4_portchannel_D2, 24, family="ipv4",
                                    config='add')

    st.log("Configuring ipv6 address on ixia connected interfaces and portchannels present on both the DUTs")
    ip_obj.config_ip_addr_interface(vars.D1, vars.D1T1P1, data.ipv6_address_D1, 64, family="ipv6", config='add')
    ip_obj.config_ip_addr_interface(vars.D2, vars.D2T1P1, data.ipv6_address_D2, 64, family="ipv6", config='add')
    ip_obj.config_ip_addr_interface(vars.D1, data.portChannelName, data.ipv6_portchannel_D1, 64, family="ipv6",
                                    config='add')
    ip_obj.config_ip_addr_interface(vars.D2, data.portChannelName, data.ipv6_portchannel_D2, 64, family="ipv6",
                                    config='add')

    #create subif
    cmd = "cli -c 'configure terminal' -c 'interface sub-interface {} 100'".format(data.pbr_primaryport['IN'])
    st.config(vars.D1, cmd)
    cmd = "cli -c 'configure terminal' -c 'interface sub-interface {} 100'".format(data.pbr_primaryport['OUT'])
    st.config(vars.D1, cmd)

    # pbr subport config
    dict1 = {'vrf_name':[data.pbr_vrfname],'skip_error':True}
    parallel.exec_parallel(True, [vars.D1], vrf_api.config_vrf, [dict1])
    dict1 = {'vrf_name':data.pbr_vrfname, 'intf_name':data.pbr_port['OUT'],'skip_error':True}
    parallel.exec_parallel(True, [vars.D1], vrf_api.bind_vrf_interface, [dict1])

    
    cmd = "cli -c 'configure terminal' -c 'interface sub-interface {} 100'".format(data.pbr_primaryport['OUT'])
    st.config(vars.D1, cmd)
    ip_obj.config_ip_addr_interface(vars.D1, data.pbr_port['IN'], data.pbr_ipv4['IN'], 24, family="ipv4", cli_type='alicli')
    ip_obj.config_ip_addr_interface(vars.D1, data.pbr_port['OUT'], data.pbr_ipv4['OUT'], 24, family="ipv4", cli_type='alicli')
    
    ip_obj.config_ip_addr_interface(vars.D1, data.pbr_port['IN'], data.pbr_ipv6['IN'], 64, family="ipv6", cli_type='alicli')
    ip_obj.config_ip_addr_interface(vars.D1, data.pbr_port['OUT'], data.pbr_ipv6['OUT'], 64, family="ipv6", cli_type='alicli')

    st.log("configuring ipv4 static routes on both the DUTs")
    cmd = "cli -c 'configure terminal'"
    st.config(vars.D1, cmd)
    ip_obj.create_static_route(vars.D1, data.ipv4_portchannel_D2, data.ipv4_network_D2, shell="vtysh",
                               family="ipv4")
    ip_obj.create_static_route(vars.D2, data.ipv4_portchannel_D1, data.ipv4_network_D1, shell="vtysh",
                               family="ipv4")

    st.log("configuring ipv6 static routes on both the DUTs")
    ip_obj.create_static_route(vars.D1, data.ipv6_portchannel_D2, data.ipv6_network_D2, shell="vtysh",
                               family="ipv6")
    ip_obj.create_static_route(vars.D2, data.ipv6_portchannel_D1, data.ipv6_network_D1, shell="vtysh",
                               family="ipv6")

    st.log("configuring static arp entries")
    arp_obj.add_static_arp(vars.D1, "1.1.1.2", "00:0a:01:00:00:01", vars.D1T1P1)
    arp_obj.add_static_arp(vars.D2, "2.2.2.2", "00:0a:01:00:11:02", vars.D2T1P1)
    arp_obj.add_static_arp(vars.D2, "2.2.2.4", "00:0a:01:00:11:02", vars.D2T1P1)
    arp_obj.add_static_arp(vars.D1, "1.1.1.4", "00:0a:01:00:00:01", vars.D1T1P1)
    arp_obj.add_static_arp(vars.D2, "2.2.2.5", "00:0a:01:00:11:02", vars.D2T1P1)
    arp_obj.add_static_arp(vars.D1, "1.1.1.5", "00:0a:01:00:00:01", vars.D1T1P1)
    arp_obj.add_static_arp(vars.D2, "2.2.2.6", "00:0a:01:00:11:02", vars.D2T1P1)
    arp_obj.add_static_arp(vars.D1, "1.1.1.6", "00:0a:01:00:00:01", vars.D1T1P1)
    # pbr
    arp_obj.add_static_arp(vars.D1, "172.10.2.2", "00:11:01:00:00:01", data.pbr_port['OUT'])

    arp_obj.show_arp(vars.D1)
    arp_obj.show_arp(vars.D2)

    st.log("configuring static ndp entries")
    arp_obj.config_static_ndp(vars.D1, "1001::2", "00:0a:01:00:00:01", vars.D1T1P1, operation="add")
    arp_obj.config_static_ndp(vars.D2, "2001::2", "00:0a:01:00:11:02", vars.D2T1P1, operation="add")
    #pbr
    arp_obj.config_static_ndp(vars.D1, "3200::2", "00:22:01:00:11:02", data.pbr_port['OUT'], operation="add")
    arp_obj.show_ndp(vars.D1)
    arp_obj.show_ndp(vars.D2)

    # Need to wait enable_counters.py to enable ACL flexcounter
    st.wait(60)

    yield
    clear_module_configuration()


def verify_rule_priority(dut, table_name):
    acl_rule = "PermitAny6" if "IPV4" in table_name else "PermitAny5"
    acl_rule_counters = acl_obj.show_acl_counters(dut, acl_table=table_name, acl_rule=acl_rule)
    if isinstance(acl_rule_counters, bool):
        print_log("Failed to read ACL counters")
        return False
    if len(acl_rule_counters) == 1:
        if (int(acl_rule_counters[0]['packetscnt']) != 0):
            print_log("ACL Rule priority test failed")
            return False
    return True


@pytest.mark.acl_test123
def test_ft_acl_ingress_ipv4_l3_forwarding():
    '''
    IPv4 Ingress ACL is applied on DUT1 port connected to TG Port#1
    Traffic is sent on TG Port #1
    Traffic is recieved at TG Port #2
    '''
    transmit('tg1')
    result1 = verify_packet_count('tg1', vars.T1D1P1, 'tg2', vars.T1D2P1, "L3_IPV4_INGRESS")
    print_log('Verifing IPv4 Ingress ACL hit counters')
    result2 = verify_acl_hit_counters(vars.D1, "L3_IPV4_INGRESS")
    result3 = verify_rule_priority(vars.D1, "L3_IPV4_INGRESS")
    acl_utils.report_result(result1 and result2 and result3)


@pytest.mark.acl_test123
def test_ft_acl_ingress_ipv6_l3_forwarding():
    '''
    IPv6 Ingress ACL is applied on DUT2 port connected to TG Port #2
    Traffic is sent on TG Port #2
    Traffic is recieved at TG Port #1
    '''

    transmit('tg2')
    result1 = verify_packet_count('tg2', vars.T1D2P1, 'tg1', vars.T1D1P1, "L3_IPV6_INGRESS")
    print_log('Verifing IPv6 Ingress ACL hit counters')
    result2 = verify_acl_hit_counters(vars.D2, "L3_IPV6_INGRESS", acl_type=data.acl_type)
    result3 = verify_rule_priority(vars.D2, "L3_IPV6_INGRESS")
    acl_utils.report_result(result1 and result2 and result3)

@pytest.mark.acl_test123
def test_ft_acl_pbr_setvrf_ipv4_l3_forwarding():
    #config acl PBRV4
    cmd = "cli -c 'config t' -c 'acl table PBRV4 stage ingress attach sub-interface Eth34.100'"
    st.config(vars.D1, cmd)
    cmd = "cli -c 'config t' -c 'acl rule  table PBRV4 index 10 action set-vrf action_object ACTN_TC1 dscp 10'"
    st.config(vars.D1, cmd)

    transmit('tg3')
    data.tgmap['tg3']['tg'].tg_traffic_control(action='run', stream_handle=list(data.tgmap['tg3']['streams'].keys()),
                                            duration=1)
    traffic_details = {
        '1' :{
                'tx_ports': [vars.T1D1P2],
                'tx_obj': [data.tgmap['tg3']['tg']],
                'exp_ratio':[1],
                'rx_ports': [vars.T1D1P3],
                'rx_obj': [data.tgmap['tg4']['tg']],
                'stream_list': [[data.tgmap['tg3']['streams'].keys()[0]]]
            }
        }

    result_all = tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock',
                                    comp_type='packet_count', return_all=1, delay_factor=1.2)
    print_log(result_all)
    print_log('Verifing PBRV4 Ingress ACL hit counters')
    result_hit = verify_acl_hit_counters(vars.D1, "PBRV4")
    acl_utils.report_result(result_all[0] and result_hit)

@pytest.mark.acl_test123
def test_ft_acl_pbr_setvrf_ipv6_l3_forwarding():
    #config acl PBRV6
    cmd = "cli -c 'config t' -c 'ipv6 acl table PBRV6 stage ingress attach sub-interface Eth34.100'"
    st.config(vars.D1, cmd)
    cmd = "cli -c 'config t' -c 'ipv6 acl rule  table PBRV6 index 10 action set-vrf action_object ACTN_TC1 dscp 10'"
    st.config(vars.D1, cmd)

    transmit('tg4')
    data.tgmap['tg4']['tg'].tg_traffic_control(action='run', stream_handle=list(data.tgmap['tg4']['streams'].keys()),
                                            duration=1)
    traffic_details = {
        '1' :{
                'tx_ports': [vars.T1D1P2],
                'tx_obj': [data.tgmap['tg3']['tg']],
                'exp_ratio':[1],
                'rx_ports': [vars.T1D1P3],
                'rx_obj': [data.tgmap['tg4']['tg']],
                'stream_list': [[data.tgmap['tg4']['streams'].keys()[0]]]
            }
        }

    result_all = tgapi.validate_tgen_traffic(traffic_details=traffic_details, mode='streamblock',
                                    comp_type='packet_count', return_all=1, delay_factor=1.2)
    print_log(result_all)
    print_log('Verifing PBRV6 Ingress ACL hit counters')
    result_hit = verify_acl_hit_counters(vars.D1, "PBRV6")
    acl_utils.report_result(result_all[0] and result_hit)

def get_subport_from_parent(port, vlan):
    if port.startswith(SUBPORT_PREFIX):
        item = SUBPORT_PREFIX + port[len("Ethernet"):] + SUB_INTERFACE_SEPARATOR + vlan
    elif port.startswith(SUBPORTCHANNEL_PREFIX):
        item = SUBPORTCHANNEL_PREFIX + port[len("PortChannel"):] + SUB_INTERFACE_SEPARATOR + vlan
    else:
        print_log("get subport from parent fail.")
        item = None
    return item
    
@pytest.mark.acl_test123
def test_ft_ipv4_acl_cli_bind_subport():
    print_log('delete parent port ip address')
    ip_obj.delete_ip_interface(vars.D1, vars.D1T1P1, data.ipv4_address_D1, 24, family="ipv4")
    ip_obj.delete_ip_interface(vars.D1, vars.D1T1P1, data.ipv6_address_D1, 64, family="ipv6")
    ip_obj.delete_ip_interface(vars.D2, vars.D2T1P1, data.ipv4_address_D2, 24, family="ipv4")
    ip_obj.delete_ip_interface(vars.D2, vars.D2T1P1, data.ipv6_address_D2, 64, family="ipv6")

    print_log('delete parent port acl table')
    st.config(vars.D1, "cli -c 'configure terminal' -c 'no acl table L3_IPV4_INGRESS'")
    st.config(vars.D1, "cli -c 'configure terminal' -c 'no ipv6 acl table L3_IPV6_INGRESS'")
    st.config(vars.D1, "cli -c 'configure terminal' -c 'no acl table L3_IPV4_EGRESS'")
    st.config(vars.D1, "cli -c 'configure terminal' -c 'no ipv6 acl table L3_IPV6_EGRESS'")

    print_log('config subport ip address')
    st.config(vars.D1, "cli -c 'configure terminal' -c 'interface sub-interface {} 200' -c 'ip address 1.1.1.1/24'".format(vars.D1T1P1))
    st.config(vars.D2, "cli -c 'configure terminal' -c 'interface sub-interface {} 200' -c 'ip address 2.2.2.1/24'".format(vars.D2T1P1))
    st.wait(5)

    acl_config3 = acl_data.acl_json_config_v4_l3_bind_subport_traffic
    sub_port = get_subport_from_parent(vars.D1T1P1, "200")
    add_port_to_acl_table(acl_config3, 'L3_IPV4_BIND_SUBPORT_ING', sub_port)
    
    # creating ACL tables and rules
    print_log('Creating ACL tables and rules')
    utils.exec_all(True, [
        utils.ExecAllFunc(acl_obj.apply_acl_config, vars.D1, acl_config3),
    ])

    #configuring static arp entries
    arp_obj.add_static_arp(vars.D2, "2.2.2.7", "00:0a:01:00:11:02", sub_port)
    arp_obj.add_static_arp(vars.D2, "2.2.2.8", "00:0a:01:00:11:02", sub_port)
    arp_obj.add_static_arp(vars.D1, "1.1.1.7", "00:0a:01:00:00:01", sub_port)
    arp_obj.add_static_arp(vars.D1, "1.1.1.8", "00:0a:01:00:00:01", sub_port)
    arp_obj.show_arp(vars.D1)
    arp_obj.show_arp(vars.D2)

    # create streams
    data.mac1 = basic_obj.get_ifconfig_ether(vars.D1, vars.D1T1P1)
    print_log('Creating streams')
    create_streams_subport("tg1", "tg2", acl_config3['ACL_RULE'], "L3_IPV4_BIND_SUBPORT_ING", \
                   mac_src="00:0a:01:00:00:01", mac_dst=data.mac1, vlan_id=200)
    print_log('Completed module configuration')

    transmit('tg1')
    st.wait(10)

    result1 = verify_packet_count('tg1', vars.T1D1P1, 'tg2', vars.T1D2P1, "L3_IPV4_BIND_SUBPORT_ING")
    print_log('Verifing IPv4 Ingress ACL bind subport hit counters')
    result2 = verify_acl_hit_counters(vars.D1, "L3_IPV4_BIND_SUBPORT_ING")
    result3 = verify_rule_priority(vars.D1, "L3_IPV4_BIND_SUBPORT_ING")
    acl_utils.report_result(result1 and result2 and result3)


def test_ft_ipv6_acl_cli_bind_subport():
    print_log('delete parent port ip address')
    ip_obj.delete_ip_interface(vars.D1, vars.D1T1P1, data.ipv4_address_D1, 24, family="ipv4")
    ip_obj.delete_ip_interface(vars.D1, vars.D1T1P1, data.ipv6_address_D1, 64, family="ipv6")
    ip_obj.delete_ip_interface(vars.D2, vars.D2T1P1, data.ipv4_address_D2, 24, family="ipv4")
    ip_obj.delete_ip_interface(vars.D2, vars.D2T1P1, data.ipv6_address_D2, 64, family="ipv6")

    print_log('delete parent port acl table')
    st.config(vars.D1, "cli -c 'configure terminal' -c 'no acl table L3_IPV4_INGRESS'")
    st.config(vars.D1, "cli -c 'configure terminal' -c 'no ipv6 acl table L3_IPV6_INGRESS'")
    st.config(vars.D1, "cli -c 'configure terminal' -c 'no acl table L3_IPV4_EGRESS'")
    st.config(vars.D1, "cli -c 'configure terminal' -c 'no ipv6 acl table L3_IPV6_EGRESS'")

    print_log('config subport ip address')
    st.config(vars.D1, "cli -c 'configure terminal' -c 'interface sub-interface {} 200' -c 'ipv6 address 1001::1/64'".format(vars.D1T1P1))
    st.config(vars.D2, "cli -c 'configure terminal' -c 'interface sub-interface {} 200' -c 'ipv6 address 2001::1/64'".format(vars.D2T1P1))
    st.wait(5)

    acl_config4 = acl_data.acl_json_config_v6_l3_bind_subport_traffic
    sub_port = get_subport_from_parent(vars.D1T1P1, "200")
    add_port_to_acl_table(acl_config4, 'L3_IPV6_BIND_SUBPORT_ING', sub_port)
    
    # creating ACL tables and rules
    print_log('Creating ACL tables and rules')
    utils.exec_all(True, [
        utils.ExecAllFunc(acl_obj.apply_acl_config, vars.D1, acl_config4),
    ])

    #configuring static ndp entries
    st.log("configuring static ndp entries")
    arp_obj.config_static_ndp(vars.D1, "1001::2", "00:0a:01:00:00:01", sub_port, operation="add")
    arp_obj.config_static_ndp(vars.D2, "2001::2", "00:0a:01:00:11:02", sub_port, operation="add")
    arp_obj.show_ndp(vars.D1)
    arp_obj.show_ndp(vars.D2)

    # create streams
    data.mac1 = basic_obj.get_ifconfig_ether(vars.D1, vars.D1T1P1)
    print_log('Creating streams')
    create_streams_subport("tg1", "tg2", acl_config4['ACL_RULE'], "L3_IPV6_BIND_SUBPORT_ING", \
                   mac_src="00:0a:01:00:00:01", mac_dst=data.mac1, vlan_id=200)
    print_log('Completed module configuration')

    transmit('tg1')
    st.wait(10)

    result1 = verify_packet_count('tg1', vars.T1D1P1, 'tg2', vars.T1D2P1, "L3_IPV6_BIND_SUBPORT_ING")
    print_log('Verifing IPv6 Ingress ACL bind subport hit counters')
    result2 = verify_acl_hit_counters(vars.D1, "L3_IPV6_BIND_SUBPORT_ING")
    result3 = verify_rule_priority(vars.D1, "L3_IPV6_BIND_SUBPORT_ING")
    acl_utils.report_result(result1 and result2 and result3)