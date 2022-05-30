# -*- coding:utf-8 -*-
import pytest
import json

from spytest import st, tgapi, SpyTestDict
import apis.routing.route_map as RouteMap
from apis.common import redis
from route_map_cli import ROUTE_MAP_CLI

# param
param_data = SpyTestDict()

# test data
data = SpyTestDict()
data.name = "test"
data.permittion = "permit"
data.sequence = "1"

data.set_metric = "20"
data.set_metric_inc = "30"

data.set_weight = "20"
data.set_weight_inc = "30"

data.set_origin = "igp"
data.set_origin_inc = "egp"

data.set_ip_nexthop = "1.1.1.1"
data.set_ip_nexthop_inc = "1.1.1.2"

data.match_tag = "100"
data.match_tag_inc = "110"

data.match_source_protocol = "bgp"
data.match_source_protocol_inc = "ospf"

data.default_rm_delay_time = "20"
data.rm_delay_time1 = "15"
data.rm_delay_time2 = "30"

def get_single_dut():
    vars = st.get_testbed_vars()
    data['dut'] = vars.D1

def config_depend_cli():
    data['rm_obj'] = ROUTE_MAP_CLI(data['dut'], data, param_data)

def restore_env():
    pass

@pytest.fixture(scope="module", autouse=True)
def cli_module_hooks(request):
    ########### module prologue #################
    st.log("pre mod config cli")
    st.ensure_min_topology("D1")
    get_single_dut()
    config_depend_cli()
    yield
    ########### module epilogue #################
    st.log("post mod config cli")
    restore_env()

# @pytest.fixture(scope='class')
# def cli_class_hooks(request):
#     ########### class prologue #################
#     yield
#     ########### class epilogue #################

@pytest.fixture(scope="function", autouse=True)
def cli_function_hooks(request):
    ########### function prologue #################
    st.log("pre func config cli")
    yield
    ########### function epilogue #################
    st.log("psot func config cli")

def get_configdb_key_routemap(route_map):
    s_list = route_map.split(' ')
    return "ROUTE_MAP|{}|{}|{}".format(s_list[1], s_list[2], s_list[3])

def get_configdb_key_rm_delay_time():
    return "ROUTE_MAP_DELAY|TIME"

def get_frr_key_routemap(route_map):
    return route_map

## check config db
## 如果checkfield 值等于checkval， 返回true， 不等返回false。 与expect比较
## 预期checkfield不存在， checkval为字符串 'null' ，存在为false
def configdb_checkpoint(dut, key, checkfield, checkval, expect = True, checkpoint = ''):
    command = redis.build(dut, redis.CONFIG_DB, 'hgetall "{}"'.format(key))
    output = st.show(dut, command)

    redis_cfg_checkpoint = False
    exist = False
    redis_cfg_exist_checkpoint = False if exist else True
    for i in range(len(output)):
        if output[i].get('donor_intf') == checkfield:
            exist = True
            if i + 1 < len(output):
                if output[i + 1].get('donor_intf') == checkval:
                    redis_cfg_checkpoint = True

    if checkval == 'null':
        redis_cfg_exist_checkpoint = False if exist else True
        if redis_cfg_exist_checkpoint != expect:
            st.report_fail("{} confg DB has {} config".format(checkpoint, checkfield))
    else:
        if redis_cfg_checkpoint != expect:
            st.report_fail("{} confg DB has no right {} config".format(checkpoint, checkfield))

def frr_config_checkpoint(obj, key, subkey, expect = True, checkpoint = ''):
    output = obj.show_frr_running_config_json()
    if key not in output:
        st.report_fail("{} frr config has no {} config".format(checkpoint, key))

    if expect == "null":
        if subkey in output[key]:
            st.report_fail("{} frr config has subkey {} config, expect null".format(checkpoint, subkey))
        else:
            return

    if subkey not in output[key]:
        st.report_fail("{} frr config has no subkey {} config".format(checkpoint, subkey))

    if output[key][subkey] != "true":
        st.report_fail("{} frr config subkey {} not equal to true".format(checkpoint, subkey))

def frr_config_checkpoint_onekey(obj, key, expect = True, checkpoint = ''):
    output = obj.show_frr_running_config_json()
    if key not in output:
        st.report_fail("{} frr config has no {} config".format(checkpoint, key))
    
    if output[key] != "true":
        st.report_fail("{} frr config key {} not equal to true".format(checkpoint, key))

    if expect == "null":
        if key in output:
            st.report_fail("{} frr config has key {} config, expect null".format(checkpoint, key))
        else:
            return


@pytest.mark.routemap_cli
def test_cli_routemap_set_metric():
    st.log("test_cli_routemap_set_metric begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    # create route-map
    st.log("create route-map")
    route_map = test_obj.create_route_map(data['name'], data['permittion'], data['sequence'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    # case 1:
    # a. set metric
    # b. no set metric
    st.log("test sub case 1...")
    test_obj.set_metric(route_map, data['set_metric'])
    configdb_checkpoint(dut, key_configdb, "set_metric", data['set_metric'], True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "set metric {}".format(data['set_metric']), True, "check2")

    test_obj.no_set_metric(route_map)
    configdb_checkpoint(dut, key_configdb, "set_metric", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "set metric {}".format(data['set_metric']), "null", "check4")

    # case 2:
    # a. set metric
    # b. no set metric with incorrect val
    st.log("test sub case 2...")
    test_obj.set_metric(route_map, data['set_metric'])
    test_obj.no_set_metric_val(route_map, data['set_metric_inc'])
    configdb_checkpoint(dut, key_configdb, "set_metric", data['set_metric'], True, "check5")
    frr_config_checkpoint(test_obj, key_frr, "set metric {}".format(data['set_metric']), True, "check6")

    # case 3:
    # a. set metric
    # b. no set metric with correct val
    st.log("test sub case 3...")
    test_obj.set_metric(route_map, data['set_metric'])
    test_obj.no_set_metric_val(route_map, data['set_metric'])
    configdb_checkpoint(dut, key_configdb, "set_metric", "null", True, "check7")
    frr_config_checkpoint(test_obj, key_frr, "set metric {}".format(data['set_metric']), "null", "check8")

    # delete route-map
    st.log("delete route-map")
    test_obj.delete_route_map(route_map)

    st.report_pass("test_case_passed")

@pytest.mark.routemap_cli
def test_cli_routemap_set_weight():
    st.log("test_cli_routemap_set_weight begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    # create route-map
    st.log("create route-map")
    route_map = test_obj.create_route_map(data['name'], data['permittion'], data['sequence'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    # case 1:
    # a. set weight
    # b. no set weight
    st.log("test sub case 1...")
    test_obj.set_weight(route_map, data['set_weight'])
    configdb_checkpoint(dut, key_configdb, "set_weight", data['set_weight'], True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "set weight {}".format(data['set_weight']), True, "check2")

    test_obj.no_set_weight(route_map)
    configdb_checkpoint(dut, key_configdb, "set_weight", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "set weight {}".format(data['set_weight']), "null", "check4")

    # case 2:
    # a. set weight
    # b. no set weight with incorrect val
    st.log("test sub case 2...")
    test_obj.set_weight(route_map, data['set_weight'])
    test_obj.no_set_weight_val(route_map, data['set_weight_inc'])
    configdb_checkpoint(dut, key_configdb, "set_weight", data['set_weight'], True, "check5")
    frr_config_checkpoint(test_obj, key_frr, "set weight {}".format(data['set_weight']), True, "check6")

    # case 3:
    # a. set weight
    # b. no set weight with correct val
    st.log("test sub case 3...")
    test_obj.set_weight(route_map, data['set_weight'])
    test_obj.no_set_weight_val(route_map, data['set_weight'])
    configdb_checkpoint(dut, key_configdb, "set_weight", "null", True, "check7")
    frr_config_checkpoint(test_obj, key_frr, "set weight {}".format(data['set_weight']), "null", "check8")

    # delete route-map
    st.log("delete route-map")
    test_obj.delete_route_map(route_map)

    st.report_pass("test_case_passed")

@pytest.mark.routemap_cli
def test_cli_routemap_set_origin():
    st.log("test_cli_routemap_set_origin begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    # create route-map
    st.log("create route-map")
    route_map = test_obj.create_route_map(data['name'], data['permittion'], data['sequence'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    # case 1:
    # a. set origin
    # b. no set origin
    st.log("test sub case 1...")
    test_obj.set_origin(route_map, data['set_origin'])
    configdb_checkpoint(dut, key_configdb, "set_origin", data['set_origin'], True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "set origin {}".format(data['set_origin']), True, "check2")

    test_obj.no_set_origin(route_map)
    configdb_checkpoint(dut, key_configdb, "set_origin", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "set origin {}".format(data['set_origin']), "null", "check4")

    # case 2:
    # a. set origin
    # b. no set origin with incorrect val
    st.log("test sub case 2...")
    test_obj.set_origin(route_map, data['set_origin'])
    test_obj.no_set_origin_val(route_map, data['set_origin_inc'])
    configdb_checkpoint(dut, key_configdb, "set_origin", data['set_origin'], True, "check5")
    frr_config_checkpoint(test_obj, key_frr, "set origin {}".format(data['set_origin']), True, "check6")

    # case 3:
    # a. set origin
    # b. no set origin with correct val
    st.log("test sub case 3...")
    test_obj.set_origin(route_map, data['set_origin'])
    test_obj.no_set_origin_val(route_map, data['set_origin'])
    configdb_checkpoint(dut, key_configdb, "set_origin", "null", True, "check7")
    frr_config_checkpoint(test_obj, key_frr, "set origin {}".format(data['set_origin']), "null", "check8")

    # delete route-map
    st.log("delete route-map")
    test_obj.delete_route_map(route_map)

    st.report_pass("test_case_passed")


@pytest.mark.routemap_cli
def test_cli_routemap_set_ip_nexthop():
    st.log("test_cli_routemap_set_ip_nexthop begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    # create route-map
    st.log("create route-map")
    route_map = test_obj.create_route_map(data['name'], data['permittion'], data['sequence'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    # case 1:
    # a. set ip_nexthop
    # b. no set ip_nexthop
    st.log("test sub case 1...")
    test_obj.set_ip_nexthop(route_map, data['set_ip_nexthop'])
    configdb_checkpoint(dut, key_configdb, "set_ip_nexthop", data['set_ip_nexthop'], True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "set ip next-hop {}".format(data['set_ip_nexthop']), True, "check2")

    test_obj.no_set_ip_nexthop(route_map)
    configdb_checkpoint(dut, key_configdb, "set_ip_nexthop", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "set ip next-hop {}".format(data['set_ip_nexthop']), "null", "check4")

    # case 2:
    # a. set ip_nexthop
    # b. no set ip_nexthop with incorrect val
    st.log("test sub case 2...")
    test_obj.set_ip_nexthop(route_map, data['set_ip_nexthop'])
    test_obj.no_set_ip_nexthop_val(route_map, data['set_ip_nexthop_inc'])
    configdb_checkpoint(dut, key_configdb, "set_ip_nexthop", data['set_ip_nexthop'], True, "check5")
    frr_config_checkpoint(test_obj, key_frr, "set ip next-hop {}".format(data['set_ip_nexthop']), True, "check6")

    # case 3:
    # a. set ip_nexthop
    # b. no set ip_nexthop with correct val
    st.log("test sub case 3...")
    test_obj.set_ip_nexthop(route_map, data['set_ip_nexthop'])
    test_obj.no_set_ip_nexthop_val(route_map, data['set_ip_nexthop'])
    configdb_checkpoint(dut, key_configdb, "set_ip_nexthop", "null", True, "check7")
    frr_config_checkpoint(test_obj, key_frr, "set ip next-hop {}".format(data['set_ip_nexthop']), "null", "check8")

    # delete route-map
    st.log("delete route-map")
    test_obj.delete_route_map(route_map)

    st.report_pass("test_case_passed")


@pytest.mark.routemap_cli
def test_cli_routemap_match_tag():
    st.log("test_cli_routemap_match_tag begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    # create route-map
    st.log("create route-map")
    route_map = test_obj.create_route_map(data['name'], data['permittion'], data['sequence'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    # case 1:
    # a. match tag
    # b. no match tag
    st.log("test sub case 1...")
    test_obj.match_tag(route_map, data['match_tag'])
    configdb_checkpoint(dut, key_configdb, "match_tag", data['match_tag'], True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "match tag {}".format(data['match_tag']), True, "check2")

    test_obj.no_match_tag(route_map)
    configdb_checkpoint(dut, key_configdb, "match_tag", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "match tag {}".format(data['match_tag']), "null", "check4")

    # case 2:
    # a. match tag
    # b. no match tag with incorrect val
    st.log("test sub case 2...")
    test_obj.match_tag(route_map, data['match_tag'])
    test_obj.no_match_tag_val(route_map, data['match_tag_inc'])
    configdb_checkpoint(dut, key_configdb, "match_tag", data['match_tag'], True, "check5")
    frr_config_checkpoint(test_obj, key_frr, "match tag {}".format(data['match_tag']), True, "check6")

    # case 3:
    # a. match tag
    # b. no match tag with correct val
    st.log("test sub case 3...")
    test_obj.match_tag(route_map, data['match_tag'])
    test_obj.no_match_tag_val(route_map, data['match_tag'])
    configdb_checkpoint(dut, key_configdb, "match_tag", "null", True, "check7")
    frr_config_checkpoint(test_obj, key_frr, "match tag {}".format(data['match_tag']), "null", "check8")

    # delete route-map
    st.log("delete route-map")
    test_obj.delete_route_map(route_map)

    st.report_pass("test_case_passed")


@pytest.mark.routemap_cli
def test_cli_routemap_match_source_protocol():
    st.log("test_cli_routemap_match_source_protocol begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    # create route-map
    st.log("create route-map")
    route_map = test_obj.create_route_map(data['name'], data['permittion'], data['sequence'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    # case 1:
    # a. match source_protocol
    # b. no match source_protocol
    st.log("test sub case 1...")
    test_obj.match_source_protocol(route_map, data['match_source_protocol'])
    configdb_checkpoint(dut, key_configdb, "match_source_protocol", data['match_source_protocol'], True, "check1")
    st.wait(2)
    frr_config_checkpoint(test_obj, key_frr, "match source-protocol {}".format(data['match_source_protocol']), True, "check2")

    test_obj.no_match_source_protocol_val(route_map, data['match_source_protocol'])
    configdb_checkpoint(dut, key_configdb, "match_source_protocol", "null", True, "check3")
    st.wait(2)
    frr_config_checkpoint(test_obj, key_frr, "match source-protocol {}".format(data['match_source_protocol']), "null", "check4")

    # case 2:
    # a. match source_protocol
    # b. no match source_protocol with incorrect val
    st.log("test sub case 2...")
    test_obj.match_source_protocol(route_map, data['match_source_protocol'])
    test_obj.no_match_source_protocol_val(route_map, data['match_source_protocol_inc'])
    configdb_checkpoint(dut, key_configdb, "match_source_protocol", data['match_source_protocol'], True, "check5")
    frr_config_checkpoint(test_obj, key_frr, "match source-protocol {}".format(data['match_source_protocol']), True, "check6")

    # delete route-map
    st.log("delete route-map")
    test_obj.delete_route_map(route_map)

    st.report_pass("test_case_passed")

@pytest.mark.routemap_cli
def test_cli_routemap_delay_time():
    st.log("test_cli_routemap_delay_time begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    # check default route-map delay-time
    st.log("check default route-map delay-time")
    frr_config_checkpoint_onekey(test_obj, 'bgp route-map delay-timer {}'.format(data['default_rm_delay_time']),
        expect = True, checkpoint = "check1")

    # config route-map delay-time
    st.log("config route-map delay-time")
    test_obj.rm_delay_time_config(data['rm_delay_time1'])
    key_configdb = get_configdb_key_rm_delay_time()
    configdb_checkpoint(dut, key_configdb, "delay_time", data['rm_delay_time1'], True, "check2")
    frr_config_checkpoint_onekey(test_obj, 'bgp route-map delay-timer {}'.format(data['rm_delay_time1']),
        expect = True, checkpoint = "check2")

    # save and reboot
    st.log("save and reboot")
    test_obj.save_config_and_reboot()
    key_configdb = get_configdb_key_rm_delay_time()
    configdb_checkpoint(dut, key_configdb, "delay_time", data['rm_delay_time1'], True, "check3")
    frr_config_checkpoint_onekey(test_obj, 'bgp route-map delay-timer {}'.format(data['rm_delay_time1']),
        expect = True, checkpoint = "check3")

    # restore to default
    st.log("restore to default")
    test_obj.rm_delay_time_config(data['default_rm_delay_time'])

    st.report_pass("test_case_passed")
