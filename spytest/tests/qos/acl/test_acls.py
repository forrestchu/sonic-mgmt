import pprint
import pytest
import json

from spytest import st, tgapi, SpyTestDict

import apis.switching.vlan as vlan_obj
import apis.qos.acl as acl_obj
import tests.qos.acl.acl_json_config as acl_data
import tests.qos.acl.acl_rules_data as acl_rules_data
import tests.qos.acl.acl_utils as acl_utils
import apis.switching.portchannel as pc_obj
import apis.routing.ip as ipobj
import apis.system.gnmi as gnmiapi
from apis.system.interface import clear_interface_counters,get_interface_counters,show_queue_counters
from apis.system.rest import rest_status
import apis.system.basic as basic_obj
import apis.routing.ip as ip_obj
import apis.routing.arp as arp_obj

from utilities.parallel import ensure_no_exception
import utilities.common as utils

YANG_MODEL = "sonic-acl:sonic-acl"
pp = pprint.PrettyPrinter(indent=4)

vars = dict()
data = SpyTestDict()
data.rate_pps = 100
data.pkts_per_burst = 10
data.tx_timeout = 2
data.TBD = 10
data.portChannelName = "PortChannel1"
data.tg_type = 'ixia'
data.cli_type = ""
data.ipv4_address_D1 = "1.0.0.1"
data.ipv4_address_D2 = "2.0.0.1"
data.ipv4_address_D3 = "100.0.0.1"
data.ipv4_address_D4 = "200.0.0.1"
data.ipv4_portchannel_D1 = "192.168.1.1"
data.ipv4_portchannel_D2 = "192.168.1.2"
data.ipv4_network_D1 = "1.0.0.0/24"
data.ipv4_network_D2 = "2.0.0.0/24"
data.ipv4_network_D3 = "100.0.0.0/24"
data.ipv4_network_D4 = "200.0.0.0/24"
data.ipv6_address_D1 = "1000::1"
data.ipv6_address_D2 = "2000::1"
data.ipv6_address_D3 = "100::1"
data.ipv6_address_D4 = "200::1"
data.ipv6_portchannel_D1 = "3001::1"
data.ipv6_portchannel_D2 = "3001::2"
data.ipv6_network_D1 = "1000::0/64"
data.ipv6_network_D2 = "2000::0/64"
data.ipv6_network_D3 = "100::0/64"
data.ipv6_network_D4 = "200::0/64"
# For Acl capacity 
data.ipv4_src_ip_base = "1.0.0.2"
data.ipv4_dst_ip_base = "2.0.0.2"
data.ipv6_src_ip_base = "100::0:2"
data.ipv6_dst_ip_base = "200::0:2"
data.ipv4_default_network = "2.0.0.0/8"
data.ipv6_default_network = "200::/48"

def print_log(msg):
    log_start = "\n================================================================================\n"
    log_end = "\n================================================================================"
    st.log("{} {} {}".format(log_start, msg, log_end))


def get_handles():
    '''
    ######################## Topology ############################

               +---------+
               |         +
      TG1 -----|  DUT1   |----- TG2
               |         +
               +---------+

    ##############################################################
    '''
    global vars, tg_port_list
    vars = st.ensure_min_topology("D1T1:2", "D1T1:2")
    tg1, tg_ph_1 = tgapi.get_handle_byname("T1D1P1")
    tg2, tg_ph_2 = tgapi.get_handle_byname("T1D1P2")
    if tg1.tg_type == 'stc': data.tg_type = 'stc'
    tg_port_list = [tg_ph_1, tg_ph_2]
    tg1.tg_traffic_control(action="reset", port_handle=tg_ph_1)
    tg2.tg_traffic_control(action="reset", port_handle=tg_ph_2)
    return (tg1, tg2, tg_ph_1, tg_ph_2)



def apply_module_configuration():
    print_log("Applying module configuration")



def clear_module_configuration():
    # delete Ipv4 address
    print_log("Delete ip address configuration:")
    ip_obj.clear_ip_configuration([vars.D1], family='ipv4')
    # delete Ipv6 address
    ip_obj.clear_ip_configuration([vars.D1], family='ipv6')

    #clear acl table wull take too much time
    #print_log("Clearing module configuration")
    #[_, exceptions] = utils.exec_all(True, [[acl_obj.acl_delete, vars.D1]])

    #Clear static arp entries
    print_log("Clearing ARP entries")
    arp_obj.clear_arp_table(vars.D1)
    #Clear static ndp entries
    print_log("Clearing NDP entries")
    arp_obj.clear_ndp_table(vars.D1)


def add_port_to_acl_table(config, table_name, port):
    config['ACL_TABLE'][table_name]['ports'] = []
    config['ACL_TABLE'][table_name]['ports'].append(port)

def add_port_to_acl_table_rules(config, port):
    rules = config["ACL_RULE"]
    for rule, attributes in rules.items():
        if ("in_ports" not in attributes):
            continue
        config["ACL_RULE"][rule]["in_ports"].append(port)

def change_acl_rules(config, rule_name, attribute, value):
    config["ACL_RULE"][rule_name][attribute] = value


def apply_acl_config(dut, config):
    json_config = json.dumps(config)
    json.loads(json_config)
    st.apply_json2(dut, json_config)


def create_streams(tx_tg, rx_tg, rules, match, mac_src, mac_dst,dscp=None,tc=None):
    # use the ACL rule definitions to create match/non-match traffic streams
    # instead of hardcoding the traffic streams
    my_args = {
        'port_handle': data.tgmap[tx_tg]['handle'], 'mode': 'create', 'frame_size': '128',
        'transmit_mode': 'continuous', 'length_mode': 'fixed',
        'l2_encap': 'ethernet_ii_vlan', 'duration': '1',
        'rate_pps': data.rate_pps,
        'high_speed_result_analysis': 0, 'mac_src': mac_src, 'mac_dst': mac_dst,
        'port_handle2': data.tgmap[rx_tg]['handle']
    }
    if dscp:
        my_args.update({"ip_dscp": dscp})
    if tc:
        my_args.update({"ipv6_traffic_class": tc})

    for rule, attributes in rules.items():
        if ("IP_TYPE" in attributes) or ("ETHER_TYPE" in attributes):
            continue
        if ("PermitAny" in rule):
            continue

        if match in rule:
            params = {}
            tmp = dict(my_args)
            for key, value in attributes.items():
                params.update(acl_utils.get_args_l3(key, value, attributes, data.rate_pps, data.tg_type))
            tmp.update(params)
            print(params)
            stream = data.tgmap[tx_tg]['tg'].tg_traffic_config(**tmp)
            stream_id = stream['stream_id']
            s = {}
            s[stream_id] = attributes
            s[stream_id]['TABLE'] = rule
            data.tgmap[tx_tg]['streams'].update(s)

def create_streams_for_qos(tx_tg, rx_tg, rules, match, mac_src, mac_dst):
    # use the ACL rule definitions to create match/non-match traffic streams
    # instead of hardcoding the traffic streams
    my_args = {
        'port_handle': data.tgmap[tx_tg]['handle'], 'mode': 'create', 'frame_size': '128',
        'transmit_mode': 'continuous', 'length_mode': 'fixed',
        'l2_encap': 'ethernet_ii_vlan', 'duration': '1',
        'rate_pps': data.rate_pps,
        'high_speed_result_analysis': 0, 'mac_src': mac_src, 'mac_dst': mac_dst,
        'port_handle2': data.tgmap[rx_tg]['handle']
    }

    for rule, attributes in rules.items():
        if ("IP_TYPE" in attributes) or ("ETHER_TYPE" in attributes):
            continue
        if match in rule:
            params = {}
            tmpv4 = dict(my_args)
            tmpv6 = tmpv4.copy()
            for key, value in attributes.items():
                params.update(acl_utils.get_args_l3(key, value, attributes, data.rate_pps, data.tg_type))
            # ipv4 + ipv6
            tmpv4.update(params)
            tmpv6.update(params)

            v4 = {'ip_src_addr':'100.0.0.2', 'ip_dst_addr':'200.0.0.2', 'l3_protocol':'ipv4', 'ip_dst_mode':"fixed", "ip_src_mode":"fixed"}
            tmpv4.update(v4)
            v6 = {'ipv6_src_addr':'100::2', 'ipv6_dst_addr':'200::2', 'l3_protocol':'ipv6', 'ipv6_dst_mode':"fixed", "ipv6_src_mode":"fixed"}
            if tmpv6.has_key('ip_dscp'):
                dscp = tmpv6['ip_dscp']
                tmpv6.pop('ip_dscp')
                tmpv6.update({'ipv6_traffic_class':dscp*4})
            tmpv6.update(v6)
            streamv4 = data.tgmap[tx_tg]['tg'].tg_traffic_config(**tmpv4)
            stream_id4 = streamv4['stream_id']
            streamv6 = data.tgmap[tx_tg]['tg'].tg_traffic_config(**tmpv6)
            stream_id6 = streamv6['stream_id']
            s = {}
            s[stream_id4] = attributes
            s[stream_id4]['TABLE'] = rule
            data.tgmap[tx_tg]['streams'].update(s)
            s = {}
            s[stream_id6] = attributes
            s[stream_id6]['TABLE'] = rule
            data.tgmap[tx_tg]['streams'].update(s)

def transmit(tg):
    print_log("Transmitting streams")
    data.tgmap[tg]['tg'].tg_traffic_control(action='clear_stats', port_handle=tg_port_list)
    data.tgmap[tg]['tg'].tg_traffic_control(action='run', stream_handle = list(data.tgmap[tg]['streams'].keys()),
                                            duration=1)


def verify_acl_hit_counters(dut, table_name, acl_type="ip"):
    result = True
    acl_rule_counters = acl_obj.show_acl_counters(dut, acl_table=table_name, acl_type=acl_type)
    for rule in acl_rule_counters:
        if 'PermitAny' in rule['rulename']:
            continue
        if not rule['packetscnt'] or int(rule['packetscnt']) == 0 or 'N/A' in rule['packetscnt']:
            return False
    return result


def verify_packet_count(tx, tx_port, rx, rx_port, table):
    result = True
    tg_tx = data.tgmap[tx]
    tg_rx = data.tgmap[rx]
    exp_ratio = 0
    #action = "DROP"
    attr_list = []
    traffic_details = dict()
    action_list = []
    index = 0
    for s_id, attr in tg_tx['streams'].items():
        if table in attr['TABLE']:
            index = index + 1
            if attr["PACKET_ACTION"] == "FORWARD" or "QUEUE" in attr["PACKET_ACTION"] or "REMARK-DSCP" in attr["PACKET_ACTION"]:
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
                                    comp_type='packet_count', return_all=1, delay_factor=1, retry=1)
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

    acl_config1 = acl_data.acl_json_config_d1
    add_port_to_acl_table(acl_config1, 'IN4', vars.D1T1P2)
    add_port_to_acl_table(acl_config1, 'EGR4', vars.D1T1P1)
    acl_config2 = acl_data.acl_json_config_d2
    add_port_to_acl_table(acl_config2, 'IN6', vars.D1T1P2)
    add_port_to_acl_table(acl_config2, 'EGR6', vars.D1T1P1)

    add_port_to_acl_table_rules(acl_config1, vars.D1T1P2)
    add_port_to_acl_table_rules(acl_config2, vars.D1T1P2)

    print_log('Creating ACL tables and rules')
    utils.exec_all(True, [
        utils.ExecAllFunc(acl_obj.apply_acl_config, vars.D1, acl_config1)
    ])

    utils.exec_all(True, [
        utils.ExecAllFunc(acl_obj.apply_acl_config, vars.D1, acl_config2)
    ])
    # create streams
    data.mac1 = basic_obj.get_ifconfig_ether(vars.D1, vars.D1T1P1)

    print_log('Creating streams')
    create_streams("tg2", "tg1", acl_config1['ACL_RULE'], "IN4", \
                   mac_src="00:0a:01:00:00:01", mac_dst=data.mac1, dscp=62)
    create_streams("tg2", "tg1", acl_config2['ACL_RULE'], "IN6", \
                   mac_src="00:0a:01:00:00:01", mac_dst=data.mac1, tc=248)

    print_log('Completed module configuration')

    st.log("Configuring ipv4 address on ixia connected interfaces and portchannels present on both the DUTs")
    ip_obj.config_ip_addr_interface(vars.D1, vars.D1T1P1, data.ipv4_address_D1, 24, family="ipv4", config='add')
    ip_obj.config_ip_addr_interface(vars.D1, vars.D1T1P2, data.ipv4_address_D2, 24, family="ipv4", config='add')

    st.log("Configuring ipv6 address on ixia connected interfaces and portchannels present on both the DUTs")
    ip_obj.config_ip_addr_interface(vars.D1, vars.D1T1P1, data.ipv6_address_D1, 64, family="ipv6", config='add')
    ip_obj.config_ip_addr_interface(vars.D1, vars.D1T1P2, data.ipv6_address_D2, 64, family="ipv6", config='add')

    st.log("configuring static arp entries")
    arp_obj.add_static_arp(vars.D1, "2.0.0.2", "00:0a:01:00:11:02", vars.D1T1P2)
    arp_obj.add_static_arp(vars.D1, "1.0.0.2", "00:0a:01:00:00:01", vars.D1T1P1)

    arp_obj.show_arp(vars.D1)

    st.log("configuring static ndp entries")
    arp_obj.config_static_ndp(vars.D1, "1000::2", "00:0a:01:00:00:01", vars.D1T1P1, operation="add")
    arp_obj.config_static_ndp(vars.D1, "2000::2", "00:0a:01:00:11:02", vars.D1T1P2, operation="add")

    arp_obj.show_ndp(vars.D1)

    yield
    clear_module_configuration()

@pytest.fixture(scope="function", autouse=True)
def acl_function_hooks(request):
    yield
    if st.get_func_name(request) == "test_ft_acl_ipv6":
        print_log("Clearing module configuration")
        [_, exceptions] = utils.exec_all(True, [[acl_obj.clear_acl_counter, vars.D1]])
        [_, exceptions] = utils.exec_all(True, [[acl_obj.acl_delete, vars.D1]])


def verify_rule_priority(dut, table_name, acl_type="ip"):
    acl_rule_counters = acl_obj.show_acl_counters(dut, acl_table=table_name, acl_rule='PermitAny', acl_type=acl_type)
    print (acl_rule_counters)
    if len(acl_rule_counters) == 1:
        print (int(acl_rule_counters[0]['packetscnt']))
        if (int(acl_rule_counters[0]['packetscnt']) != 0):
            print_log("ACL Rule priority test failed")
            return False
        else:
            return True
    else:
        return True

def verify_queue_counters_pps_match(dut, port, q, expect):
    counter = show_queue_counters(dut, port, queue='UC{}'.format(q))
    if (counter[0]['pkts_count'] >= expect):
        return True
    return False

@pytest.mark.acl_test345654
def test_ft_acl_ipv4():
    '''
    IPv4 Ingress ACL is applied on DUT1 port connected to TG Port#1
    Traffic is sent on TG Port #1
    Traffic is recieved at TG Port #2
    '''
    [_, exceptions] = utils.exec_all(True, [[acl_obj.clear_acl_counter, vars.D1]])
    ensure_no_exception(exceptions)
    transmit('tg1')
    result1 = verify_packet_count('tg1', vars.T1D1P1, 'tg2', vars.T1D1P2, "IN4")
    result2 = verify_packet_count('tg1', vars.T1D1P1, 'tg2', vars.T1D1P2, "EGR4")

    print_log('Verifing IPv4 Ingress ACL hit counters')
    result3 = verify_acl_hit_counters(vars.D1, "IN4")
    result4 = verify_acl_hit_counters(vars.D1, "EGR4")
    result5 = verify_rule_priority(vars.D1, "IN4")
    result6 = verify_rule_priority(vars.D1, "EGR4")
    print(result1, result2, result3, result4, result5, result6)

    acl_utils.report_result(result1 and result2 and result3 and result4 and result5 and result6)

@pytest.mark.acl_test678
def test_ft_acl_ipv6():
    '''
    IPv6 Egress ACL is applied on DUT2 port connected to TG Port #2
    Traffic is sent on TG Port #1
    Traffic is recieved at TG Port #2
    '''
    [_, exceptions] = utils.exec_all(True, [[acl_obj.clear_acl_counter, vars.D1]])
    transmit('tg1')
    result1 = verify_packet_count('tg1', vars.T1D1P1, 'tg2', vars.T1D1P2, "IN6")
    result2 = verify_packet_count('tg1', vars.T1D1P1, 'tg2', vars.T1D1P2, "EGR6")

    print_log('Verifing IPv6 Egress ACL hit counters')
    result3 = verify_acl_hit_counters(vars.D1, "IN6", acl_type="ipv6")
    result4 = verify_acl_hit_counters(vars.D1, "EGR6", acl_type="ipv6")
    result5 = verify_rule_priority(vars.D1, "IN6")
    result6 = verify_rule_priority(vars.D1, "EGR6")
    print(result1, result2, result3, result4, result5, result6)

    acl_utils.report_result(result1 and result2 and result3 and result4 and result5 and result6)

#@pytest.mark.acl_test345654
def test_ft_acl_capacity():
    acl_config1 = acl_data.acl_json_capacity
    add_port_to_acl_table(acl_config1, 'IN4', vars.D1T1P2)
    add_port_to_acl_table(acl_config1, 'IN6', vars.D1T1P2)

    print_log('Creating ACL Capacity tables and rules')
    utils.exec_all(True, [
        utils.ExecAllFunc(acl_obj.apply_acl_config, vars.D1, acl_config1)
    ])
    st.wait(180)

    #create static route
    ip_obj.create_static_route(vars.D1, '2.0.0.2', data.ipv4_default_network, family = 'ipv4')
    ip_obj.create_static_route(vars.D1, '2000::2', data.ipv6_default_network, family = 'ipv6')

    s1 = data.tgmap['tg2']['tg'].tg_traffic_config(port_handle = data.tgmap['tg2']['handle'], mode = 'create', duration = '1', transmit_mode = 'continuous', length_mode = 'fixed', port_handle2 = data.tgmap['tg1']['handle'], rate_pps = 102400, mac_src = "00:0a:01:00:00:01", mac_dst = data.mac1, ip_src_addr = data.ipv4_src_ip_base, ip_dst_addr=data.ipv4_dst_ip_base, l3_protocol='ipv4',ip_src_mode = 'increment', ip_src_count = 1024, ip_src_step ='0.0.1.0',ip_dst_mode = 'increment', ip_dst_count = 1024, ip_dst_step ='0.0.1.0')
    s2 = data.tgmap['tg2']['tg'].tg_traffic_config(port_handle = data.tgmap['tg2']['handle'], mode = 'create', duration = '1', transmit_mode = 'continuous', length_mode = 'fixed', port_handle2 = data.tgmap['tg1']['handle'], rate_pps = 102400, mac_src = "00:0a:01:00:00:01", mac_dst = data.mac1, ipv6_src_addr = data.ipv6_src_ip_base, ipv6_dst_addr=data.ipv6_dst_ip_base, l3_protocol='ipv6',ipv6_src_mode = 'increment', ipv6_src_count = 1024, ipv6_src_step ='::1:0',ipv6_dst_mode = 'increment', ipv6_dst_count = 1024, ipv6_dst_step ='::1:0')

    [_, exceptions] = utils.exec_all(True, [[acl_obj.clear_acl_counter, vars.D1]])
    data.tgmap['tg2']['tg'].tg_traffic_control(action="run", stream_handle=s1['stream_id'])
    data.tgmap['tg2']['tg'].tg_traffic_control(action="run", stream_handle=s2['stream_id'])
    st.wait(10)
    data.tgmap['tg2']['tg'].tg_traffic_control(action="stop", stream_handle=s1['stream_id'])
    data.tgmap['tg2']['tg'].tg_traffic_control(action="stop", stream_handle=s2['stream_id'])
    st.wait(5)

    result1 = verify_acl_hit_counters(vars.D1, "IN4")
    result2 = verify_acl_hit_counters(vars.D1, "IN6", acl_type="ipv6")
    print(result1, result2)

    acl_utils.report_result(result1 and result2)

