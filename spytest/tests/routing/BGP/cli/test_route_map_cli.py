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

data.name2 = "test2"
data.sequence2 = "10"

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
    return "BGP_GLOBAL_PARAMETERS|route_map_delay"

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

def is_routemap_configdb_exist(dut, key, name):
    command = redis.build(dut, redis.CONFIG_DB, 'keys "{}"'.format(key))
    output = st.show(dut, command)

    st.log(output)
    if len(output) > 1:
        return True
    else:
        return False

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

@pytest.mark.routemap_cli
def test_cli_routemap_config_recovery():
    st.log("test_cli_routemap_config_recovery begin")
    test_obj = data['rm_obj']
    dut = data['dut']


    st.log("create route-map")
    route_map = test_obj.create_route_map(data['name'], data['permittion'], data['sequence'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    #  route-map test config
    st.log("route-map test config...")
    test_obj.set_metric(route_map, data['set_metric'])
    frr_config_checkpoint(test_obj, key_frr, "set metric {}".format(data['set_metric']), True, "check1")

    test_obj.set_weight(route_map, data['set_weight'])
    frr_config_checkpoint(test_obj, key_frr, "set weight {}".format(data['set_weight']), True, "check2")

    test_obj.match_tag(route_map, data['match_tag'])
    frr_config_checkpoint(test_obj, key_frr, "match tag {}".format(data['match_tag']), True, "check3")

    # create route-map
    st.log("create route-map 2")
    route_map = test_obj.create_route_map(data['name2'], data['permittion'], data['sequence2'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    #  route-map test config
    st.log("route-map test2 config...")
    test_obj.set_origin(route_map, data['set_origin'])
    frr_config_checkpoint(test_obj, key_frr, "set origin {}".format(data['set_origin']), True, "check4")

    test_obj.set_ip_nexthop(route_map, data['set_ip_nexthop'])
    frr_config_checkpoint(test_obj, key_frr, "set ip next-hop {}".format(data['set_ip_nexthop']), True, "check5")

    test_obj.match_source_protocol(route_map, data['match_source_protocol'])
    frr_config_checkpoint(test_obj, key_frr, "match source-protocol {}".format(data['match_source_protocol']), True, "check6")


    # save and reboot
    st.log("save and reboot")
    test_obj.save_config_and_reboot()

    # check config
    route_map1 = "route-map {} {} {}".format(data['name'], data['permittion'], data['sequence'])
    frr_config_checkpoint(test_obj, route_map1, "set metric {}".format(data['set_metric']), True, "check7")
    frr_config_checkpoint(test_obj, route_map1, "set weight {}".format(data['set_weight']), True, "check8")
    frr_config_checkpoint(test_obj, route_map1, "match tag {}".format(data['match_tag']), True, "check9")


    route_map2 = "route-map {} {} {}".format(data['name2'], data['permittion'], data['sequence2'])
    frr_config_checkpoint(test_obj, route_map2, "set origin {}".format(data['set_origin']), True, "check10")
    frr_config_checkpoint(test_obj, route_map2, "set ip next-hop {}".format(data['set_ip_nexthop']), True, "check11")
    frr_config_checkpoint(test_obj, route_map2, "match source-protocol {}".format(data['match_source_protocol']), True, "check12")

    st.report_pass("test_case_passed")

@pytest.mark.routemap_cli
def test_cli_routemap_delay_time_exception():
    st.log("test_cli_routemap_delay_time_exception begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    # check default route-map delay-time
    st.log("check default route-map delay-time")
    frr_config_checkpoint_onekey(test_obj, 'bgp route-map delay-timer {}'.format(data['default_rm_delay_time']),
        expect = True, checkpoint = "check0")

    # create route-map
    st.log("create route-map")
    route_map = test_obj.create_route_map(data['name'], data['permittion'], data['sequence'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    # set metric and no metric
    st.log("test sub case 1...")
    test_obj.set_metric(route_map, data['set_metric'])
    configdb_checkpoint(dut, key_configdb, "set_metric", data['set_metric'], True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "set metric {}".format(data['set_metric']), True, "check2")

    test_obj.no_set_metric(route_map)
    configdb_checkpoint(dut, key_configdb, "set_metric", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "set metric {}".format(data['set_metric']), "null", "check4")

    # set match tag and no match tag
    st.log("test sub case 2...")
    test_obj.match_tag(route_map, data['match_tag'])
    configdb_checkpoint(dut, key_configdb, "match_tag", data['match_tag'], True, "check5")
    frr_config_checkpoint(test_obj, key_frr, "match tag {}".format(data['match_tag']), True, "check6")

    test_obj.no_match_tag(route_map)
    configdb_checkpoint(dut, key_configdb, "match_tag", "null", True, "check7")
    frr_config_checkpoint(test_obj, key_frr, "match tag {}".format(data['match_tag']), "null", "check8")


    # set match_source_protocol and no match source_protocol
    st.log("test sub case 3...")
    test_obj.match_source_protocol(route_map, data['match_source_protocol'])
    configdb_checkpoint(dut, key_configdb, "match_source_protocol", data['match_source_protocol'], True, "check9")
    st.wait(2)
    frr_config_checkpoint(test_obj, key_frr, "match source-protocol {}".format(data['match_source_protocol']), True, "check10")

    test_obj.no_match_source_protocol_val(route_map, data['match_source_protocol'])
    configdb_checkpoint(dut, key_configdb, "match_source_protocol", "null", True, "check11")
    st.wait(2)
    frr_config_checkpoint(test_obj, key_frr, "match source-protocol {}".format(data['match_source_protocol']), "null", "check12")

    # wait 30s
    st.wait(30)

    # set metric
    test_obj.set_metric(route_map, data['set_metric'])
    st.wait(2)

    st.log("check2 default route-map delay-time")
    frr_config_checkpoint_onekey(test_obj, 'bgp route-map delay-timer {}'.format(data['default_rm_delay_time']),
        expect = True, checkpoint = "check13")

    st.report_pass("test_case_passed")

@pytest.mark.routemap_cli
def test_cli_prefix_list_base_case():
    st.log("test_cli_prefix_list_base_case begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    #  config ip prefix-list
    PREFIX_NAME = 'plv4'
    PREFIX_E1 = '1.1.1.1/32'
    PREFIX_E2 = '2.2.2.2/32'
    PREFIX_E3 = '3.3.3.3/32'

    cmd = "cli -c 'config t' -c 'ip prefix-list {} permit {}'".format(PREFIX_NAME, PREFIX_E1)
    st.config(dut, cmd)
    st.wait(2)

    cmd = "cli -c 'config t' -c 'ip prefix-list {} permit {}'".format(PREFIX_NAME, PREFIX_E2)
    st.config(dut, cmd)
    st.wait(2)

    cmd = "cli -c 'config t' -c 'ip prefix-list {} permit {}'".format(PREFIX_NAME, PREFIX_E3)
    st.config(dut, cmd)
    st.wait(2)

    #  check ip prefix-list
    configdb_checkpoint(dut, "IP_PREFIX_LIST|{}|seq|10".format(PREFIX_NAME), "permit", PREFIX_E1, True, "check1")
    configdb_checkpoint(dut, "IP_PREFIX_LIST|{}|seq|20".format(PREFIX_NAME), "permit", PREFIX_E2, True, "check2")
    configdb_checkpoint(dut, "IP_PREFIX_LIST|{}|seq|30".format(PREFIX_NAME), "permit", PREFIX_E3, True, "check3")

    frr_config_checkpoint_onekey(test_obj, "ip prefix-list {} seq 10 permit {}".format(PREFIX_NAME,PREFIX_E1), True, "check4")
    frr_config_checkpoint_onekey(test_obj, "ip prefix-list {} seq 20 permit {}".format(PREFIX_NAME,PREFIX_E2), True, "check5")
    frr_config_checkpoint_onekey(test_obj, "ip prefix-list {} seq 30 permit {}".format(PREFIX_NAME,PREFIX_E3), True, "check6")


    #  config ipv6 prefix-list
    PREFIX6_NAME = 'plv6'
    PREFIX6_E1 = '2000::1/128'
    PREFIX6_E2 = '2000::2/128'
    PREFIX6_E3 = '2000::3/128'

    cmd = "cli -c 'config t' -c 'ipv6 prefix-list {} permit {}'".format(PREFIX6_NAME, PREFIX6_E1)
    st.config(dut, cmd)
    st.wait(2)

    cmd = "cli -c 'config t' -c 'ipv6 prefix-list {} permit {}'".format(PREFIX6_NAME, PREFIX6_E2)
    st.config(dut, cmd)
    st.wait(2)

    cmd = "cli -c 'config t' -c 'ipv6 prefix-list {} permit {}'".format(PREFIX6_NAME, PREFIX6_E3)
    st.config(dut, cmd)
    st.wait(2)

    #  check ip6 prefix-list
    configdb_checkpoint(dut, "IPV6_PREFIX_LIST|{}|seq|10".format(PREFIX6_NAME), "permit", PREFIX6_E1, True, "check7")
    configdb_checkpoint(dut, "IPV6_PREFIX_LIST|{}|seq|20".format(PREFIX6_NAME), "permit", PREFIX6_E2, True, "check8")
    configdb_checkpoint(dut, "IPV6_PREFIX_LIST|{}|seq|30".format(PREFIX6_NAME), "permit", PREFIX6_E3, True, "check9")

    frr_config_checkpoint_onekey(test_obj, "ipv6 prefix-list {} seq 10 permit {}".format(PREFIX6_NAME,PREFIX6_E1), True, "check10")
    frr_config_checkpoint_onekey(test_obj, "ipv6 prefix-list {} seq 20 permit {}".format(PREFIX6_NAME,PREFIX6_E2), True, "check11")
    frr_config_checkpoint_onekey(test_obj, "ipv6 prefix-list {} seq 30 permit {}".format(PREFIX6_NAME,PREFIX6_E3), True, "check12")

    st.report_pass("test_case_passed")


@pytest.mark.routemap_cli
def test_cli_prefix_list_no_seq():
    st.log("test_cli_prefix_list_no_seq begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    #  config ip prefix-list with seq
    PREFIX_NAME = 'plv4'
    PREFIX_E1 = '1.1.1.1/32'
    PREFIX_E2 = '2.2.2.2/32'
    PREFIX_E3 = '3.3.3.3/32'

    cmd = "cli -c 'config t' -c 'ip prefix-list {} seq 90 permit {}'".format(PREFIX_NAME, PREFIX_E1)
    st.config(dut, cmd)
    st.wait(2)

    cmd = "cli -c 'config t' -c 'ip prefix-list {} seq 100 permit {}'".format(PREFIX_NAME, PREFIX_E2)
    st.config(dut, cmd)
    st.wait(2)

    # config ip prefix-list without seq
    cmd = "cli -c 'config t' -c 'ip prefix-list {} permit {}'".format(PREFIX_NAME, PREFIX_E3)
    st.config(dut, cmd)
    st.wait(2)

    #  check ip prefix-list
    configdb_checkpoint(dut, "IP_PREFIX_LIST|{}|seq|90".format(PREFIX_NAME), "permit", PREFIX_E1, True, "check1")
    configdb_checkpoint(dut, "IP_PREFIX_LIST|{}|seq|100".format(PREFIX_NAME), "permit", PREFIX_E2, True, "check2")
    configdb_checkpoint(dut, "IP_PREFIX_LIST|{}|seq|110".format(PREFIX_NAME), "permit", PREFIX_E3, True, "check3")

    frr_config_checkpoint_onekey(test_obj, "ip prefix-list {} seq 90 permit {}".format(PREFIX_NAME,PREFIX_E1), True, "check4")
    frr_config_checkpoint_onekey(test_obj, "ip prefix-list {} seq 100 permit {}".format(PREFIX_NAME,PREFIX_E2), True, "check5")
    frr_config_checkpoint_onekey(test_obj, "ip prefix-list {} seq 110 permit {}".format(PREFIX_NAME,PREFIX_E3), True, "check6")


    #  config ipv6 prefix-list
    PREFIX6_NAME = 'plv6'
    PREFIX6_E1 = '2000::1/128'
    PREFIX6_E2 = '2000::2/128'
    PREFIX6_E3 = '2000::3/128'

    cmd = "cli -c 'config t' -c 'ipv6 prefix-list {} seq 90 permit {}'".format(PREFIX6_NAME, PREFIX6_E1)
    st.config(dut, cmd)
    st.wait(2)

    cmd = "cli -c 'config t' -c 'ipv6 prefix-list {} seq 100 permit {}'".format(PREFIX6_NAME, PREFIX6_E2)
    st.config(dut, cmd)
    st.wait(2)

    cmd = "cli -c 'config t' -c 'ipv6 prefix-list {} permit {}'".format(PREFIX6_NAME, PREFIX6_E3)
    st.config(dut, cmd)
    st.wait(2)

    #  check ip6 prefix-list
    configdb_checkpoint(dut, "IPV6_PREFIX_LIST|{}|seq|90".format(PREFIX6_NAME), "permit", PREFIX6_E1, True, "check7")
    configdb_checkpoint(dut, "IPV6_PREFIX_LIST|{}|seq|100".format(PREFIX6_NAME), "permit", PREFIX6_E2, True, "check8")
    configdb_checkpoint(dut, "IPV6_PREFIX_LIST|{}|seq|110".format(PREFIX6_NAME), "permit", PREFIX6_E3, True, "check9")

    frr_config_checkpoint_onekey(test_obj, "ipv6 prefix-list {} seq 90 permit {}".format(PREFIX6_NAME,PREFIX6_E1), True, "check10")
    frr_config_checkpoint_onekey(test_obj, "ipv6 prefix-list {} seq 100 permit {}".format(PREFIX6_NAME,PREFIX6_E2), True, "check11")
    frr_config_checkpoint_onekey(test_obj, "ipv6 prefix-list {} seq 110 permit {}".format(PREFIX6_NAME,PREFIX6_E3), True, "check12")

    st.report_pass("test_case_passed")


@pytest.mark.routemap_cli
def test_cli_routemap_set_extcommunity_bandwidth():
    st.log("test_cli_routemap_set_extcommunity_bandwidth begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    # create route-map
    st.log("create route-map")
    route_map = test_obj.create_route_map(data['name'], data['permittion'], data['sequence'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    # case 1:
    st.log("test sub case 1...")
    test_obj.set_extcommunity_bandwidth(route_map, "600")
    configdb_checkpoint(dut, key_configdb, "extcommunity_bandwidth", "600", True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity bandwidth {}".format("600"), True, "check2")

    test_obj.no_set_extcommunity_bandwidth(route_map)
    configdb_checkpoint(dut, key_configdb, "extcommunity_bandwidth", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity bandwidth {}".format("600"), "null", "check4")

    # case 2:
    st.log("test sub case 2...")
    test_obj.set_extcommunity_bandwidth_cumulative(route_map)
    configdb_checkpoint(dut, key_configdb, "extcommunity_bandwidth", "cumulative", True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity bandwidth cumulative", True, "check2")

    test_obj.no_set_extcommunity_bandwidth(route_map)
    configdb_checkpoint(dut, key_configdb, "extcommunity_bandwidth", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity bandwidth cumulative", "null", "check4")

    # case 3:
    st.log("test sub case 3...")
    test_obj.set_extcommunity_bandwidth_cumulative_non_transitive(route_map)
    configdb_checkpoint(dut, key_configdb, "extcommunity_bandwidth", "cumulative non-transitive", True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity bandwidth cumulative non-transitive", True, "check2")

    test_obj.no_set_extcommunity_bandwidth(route_map)
    configdb_checkpoint(dut, key_configdb, "extcommunity_bandwidth", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity bandwidth cumulative non-transitive", "null", "check4")

    # case 4:
    st.log("test sub case 4...")
    test_obj.set_extcommunity_bandwidth_num_multipaths(route_map)
    configdb_checkpoint(dut, key_configdb, "extcommunity_bandwidth", "num-multipaths", True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity bandwidth num-multipaths", True, "check2")

    test_obj.no_set_extcommunity_bandwidth(route_map)
    configdb_checkpoint(dut, key_configdb, "extcommunity_bandwidth", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity bandwidth num-multipaths", "null", "check4")

    # case 5:
    st.log("test sub case 5...")
    test_obj.set_extcommunity_bandwidth_num_multipaths_non_transitive(route_map)
    configdb_checkpoint(dut, key_configdb, "extcommunity_bandwidth", "num-multipaths non-transitive", True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity bandwidth num-multipaths non-transitive", True, "check2")

    test_obj.no_set_extcommunity_bandwidth(route_map)
    configdb_checkpoint(dut, key_configdb, "extcommunity_bandwidth", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity bandwidth num-multipaths non-transitive", "null", "check4")

    # delete route-map
    st.log("delete route-map")
    test_obj.delete_route_map(route_map)

    st.report_pass("test_case_passed")


@pytest.mark.routemap_cli
def test_cli_routemap_set_extcommunity_color():
    st.log("test_cli_routemap_set_extcommunity_color begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    # create route-map
    st.log("create route-map")
    route_map = test_obj.create_route_map(data['name'], data['permittion'], data['sequence'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    # case 1:
    st.log("test sub case 1...")
    test_obj.set_extcommunity_color(route_map, "3")
    configdb_checkpoint(dut, key_configdb, "extcommunity_color", "3", True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity color {}".format("3"), True, "check2")

    test_obj.no_set_extcommunity_color(route_map)
    configdb_checkpoint(dut, key_configdb, "extcommunity_color", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity color {}".format("3"), "null", "check4")

    # delete route-map
    st.log("delete route-map")
    test_obj.delete_route_map(route_map)

    st.report_pass("test_case_passed")


@pytest.mark.routemap_cli
def test_cli_routemap_set_extcommunity_rt():
    st.log("test_cli_routemap_set_extcommunity_rt begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    # create route-map
    st.log("create route-map")
    route_map = test_obj.create_route_map(data['name'], data['permittion'], data['sequence'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    # case 1:
    st.log("test sub case 1...")
    test_obj.set_extcommunity_rt(route_map, "11:11")
    configdb_checkpoint(dut, key_configdb, "extcommunity_rt", "11:11", True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity rt {}".format("11:11"), True, "check2")

    test_obj.no_set_extcommunity_rt(route_map)
    configdb_checkpoint(dut, key_configdb, "extcommunity_rt", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity rt {}".format("11:11"), "null", "check4")

    # delete route-map
    st.log("delete route-map")
    test_obj.delete_route_map(route_map)

    st.report_pass("test_case_passed")


@pytest.mark.routemap_cli
def test_cli_routemap_set_extcommunity_soo():
    st.log("test_cli_routemap_set_extcommunity_soo begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    # create route-map
    st.log("create route-map")
    route_map = test_obj.create_route_map(data['name'], data['permittion'], data['sequence'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    # case 1:
    st.log("test sub case 1...")
    test_obj.set_extcommunity_soo(route_map, "11:11")
    configdb_checkpoint(dut, key_configdb, "extcommunity_soo", "11:11", True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity soo {}".format("11:11"), True, "check2")

    test_obj.no_set_extcommunity_soo(route_map)
    configdb_checkpoint(dut, key_configdb, "extcommunity_soo", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "set extcommunity soo {}".format("11:11"), "null", "check4")

    # delete route-map
    st.log("delete route-map")
    test_obj.delete_route_map(route_map)

    st.report_pass("test_case_passed")


@pytest.mark.routemap_cli
def test_cli_routemap_match_local_preference():
    st.log("test_cli_routemap_match_local_preference begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    # create route-map
    st.log("create route-map")
    route_map = test_obj.create_route_map(data['name'], data['permittion'], data['sequence'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    # case 1:
    st.log("test sub case 1...")
    test_obj.match_local_preference(route_map, "100")
    configdb_checkpoint(dut, key_configdb, "match_local_preference", "100", True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "match local-preference {}".format("100"), True, "check2")

    test_obj.no_match_local_preference(route_map)
    configdb_checkpoint(dut, key_configdb, "match_local_preference", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "match local-preference {}".format("100"), "null", "check4")

    # delete route-map
    st.log("delete route-map")
    test_obj.delete_route_map(route_map)

    st.report_pass("test_case_passed")


@pytest.mark.routemap_cli
def test_cli_routemap_match_extcommunity():
    st.log("test_cli_routemap_match_extcommunity begin")
    test_obj = data['rm_obj']
    dut = data['dut']

    # create route-map
    st.log("create route-map")
    route_map = test_obj.create_route_map(data['name'], data['permittion'], data['sequence'])
    key_configdb = get_configdb_key_routemap(route_map)
    key_frr = get_frr_key_routemap(route_map)

    # case 1:
    st.log("test sub case 1...")
    test_obj.match_extcommunity(route_map, "aa")
    configdb_checkpoint(dut, key_configdb, "match_extcommunity", "aa", True, "check1")
    frr_config_checkpoint(test_obj, key_frr, "match extcommunity {}".format("aa"), True, "check2")

    test_obj.no_match_extcommunity(route_map)
    configdb_checkpoint(dut, key_configdb, "match_extcommunity", "null", True, "check3")
    frr_config_checkpoint(test_obj, key_frr, "match extcommunity {}".format("aa"), "null", "check4")

    # delete route-map
    st.log("delete route-map")
    test_obj.delete_route_map(route_map)

    st.report_pass("test_case_passed")

@pytest.mark.routemap_cli
def test_cli_routemap_name_len():
    st.log("test_cli_routemap_name_len begin")
    dut = data['dut']

    # create route-map
    st.log("create route-map")
    long_name = '1111111111222222222233333333334444444444555555555566666666667777' # 64

    config_route_map_cli = "cli -c 'configure terminal' -c 'route-map {} {} {}'".format(long_name, data['permittion'], data['sequence'])
    st.config(dut, config_route_map_cli)


    key_configdb = "ROUTE_MAP|{}|{}|{}".format(long_name, data['permittion'], data['sequence'])

    if not is_routemap_configdb_exist(dut, key_configdb, long_name):
        st.report_fail("{} {}  check failed.".format(key_configdb, long_name))

    st.report_pass("test_case_passed")

@pytest.mark.routemap_cli
def test_cli_routemap_incomplete_key():
    st.log("test_cli_routemap_incomplete_key begin")
    dut = data['dut']

    # create route-map
    st.log("create route-map")

    routemap_name = "test_incomplete_key"
    config_route_map_cli = "cli -c 'configure terminal' -c 'route-map {} {} {}'".format(routemap_name, data['permittion'], data['sequence'])
    st.config(dut, config_route_map_cli)

    set_aspath_cmd = "{} -c '{}'".format(config_route_map_cli, "set as-path pre 45108 45108 45108 45108 45108 45108 45108 45108")
    st.config(dut, set_aspath_cmd)

    key_configdb = "ROUTE_MAP|{}|{}|{}".format(routemap_name, data['permittion'], data['sequence'])

    configdb_checkpoint(dut, key_configdb, "set_as_path", "prepend 45108 45108 45108 45108 45108 45108 45108 45108", True, "check1")

    st.report_pass("test_case_passed")

