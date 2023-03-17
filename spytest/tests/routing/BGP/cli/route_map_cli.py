
# -*- coding:utf-8 -*-
import pytest
from spytest import st, tgapi, SpyTestDict
import time
import json

ALICLI_VIEW = "cli"
CONFIG_VIEW = "configure terminal"
ROUTE_MAP_VIEW = "route-map {} {} {}"
CMD_INTERVAL = 2

class ROUTE_MAP_CLI():

    def __init__(self, dut, test_data, param_data):
        self.dut = dut
        self.data = test_data
        self.param_data = param_data

    def create_route_map(self, name, permittion, sequence):
        route_map = ROUTE_MAP_VIEW.format(name, permittion, sequence)
        cmd = "{} -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)
        return route_map

    def delete_route_map(self, route_map):
        cmd = "{} -c '{}' -c 'no {}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def set_metric(self, route_map, metric_val):
        st.log("Route-map set metric")
        sub_cmd = "set metric {}".format(metric_val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_set_metric(self, route_map):
        st.log("Route-map no set metric")
        sub_cmd = "no set metric"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_set_metric_val(self, route_map, metric_val):
        st.log("Route-map no set metric val")
        sub_cmd = "no set metric {}".format(metric_val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def set_weight(self, route_map, weight_val):
        st.log("Route-map set weight")
        sub_cmd = "set weight {}".format(weight_val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_set_weight(self, route_map):
        st.log("Route-map no set weight")
        sub_cmd = "no set weight"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_set_weight_val(self, route_map, weight_val):
        st.log("Route-map no set weight val")
        sub_cmd = "no set weight {}".format(weight_val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def set_origin(self, route_map, origin_val):
        st.log("Route-map set origin")
        sub_cmd = "set origin {}".format(origin_val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_set_origin(self, route_map):
        st.log("Route-map no set origin")
        sub_cmd = "no set origin"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_set_origin_val(self, route_map, origin_val):
        st.log("Route-map no set origin val")
        sub_cmd = "no set origin {}".format(origin_val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def set_ip_nexthop(self, route_map, ip_nexthop_val):
        st.log("Route-map set ip_nexthop")
        sub_cmd = "set ip next-hop {}".format(ip_nexthop_val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_set_ip_nexthop(self, route_map):
        st.log("Route-map no set ip_nexthop")
        sub_cmd = "no set ip next-hop"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_set_ip_nexthop_val(self, route_map, ip_nexthop_val):
        st.log("Route-map no set ip_nexthop val")
        sub_cmd = "no set ip next-hop {}".format(ip_nexthop_val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def set_extcommunity_bandwidth(self, route_map, val):
        st.log("Route-map set extcommunity bandwidth")
        sub_cmd = "set extcommunity bandwidth {}".format(val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_set_extcommunity_bandwidth(self, route_map):
        st.log("Route-map no set extcommunity bandwidth")
        sub_cmd = "no set extcommunity bandwidth"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def set_extcommunity_bandwidth_cumulative(self, route_map):
        st.log("Route-map set extcommunity bandwidth cumulative")
        sub_cmd = "set extcommunity bandwidth cumulative"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def set_extcommunity_bandwidth_cumulative_non_transitive(self, route_map):
        st.log("Route-map set extcommunity bandwidth cumulative non-transitive")
        sub_cmd = "set extcommunity bandwidth cumulative non-transitive"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def set_extcommunity_bandwidth_num_multipaths(self, route_map):
        st.log("Route-map set extcommunity bandwidth num-multipaths")
        sub_cmd = "set extcommunity bandwidth num-multipaths"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def set_extcommunity_bandwidth_num_multipaths_non_transitive(self, route_map):
        st.log("Route-map set extcommunity num-multipaths non-transitive")
        sub_cmd = "set extcommunity bandwidth num-multipaths non-transitive"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def set_extcommunity_color(self, route_map, val):
        st.log("Route-map set extcommunity color")
        sub_cmd = "set extcommunity color {}".format(val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_set_extcommunity_color(self, route_map):
        st.log("Route-map no set extcommunity color")
        sub_cmd = "no set extcommunity color"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def set_extcommunity_rt(self, route_map, val):
        st.log("Route-map set extcommunity rt")
        sub_cmd = "set extcommunity rt {}".format(val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_set_extcommunity_rt(self, route_map):
        st.log("Route-map no set extcommunity rt")
        sub_cmd = "no set extcommunity rt"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def set_extcommunity_soo(self, route_map, val):
        st.log("Route-map set extcommunity soo")
        sub_cmd = "set extcommunity soo {}".format(val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_set_extcommunity_soo(self, route_map):
        st.log("Route-map no set extcommunity soo")
        sub_cmd = "no set extcommunity soo"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def match_tag(self, route_map, tag_val):
        st.log("Route-map match tag")
        sub_cmd = "match tag {}".format(tag_val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_match_tag(self, route_map):
        st.log("Route-map match tag")
        sub_cmd = "no match tag"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_match_tag_val(self, route_map, tag_val):
        st.log("Route-map match tag")
        sub_cmd = "no match tag {}".format(tag_val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def match_source_protocol(self, route_map, source_protocol_val):
        st.log("Route-map match source_protocol")
        sub_cmd = "match source-protocol {}".format(source_protocol_val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_match_source_protocol_val(self, route_map, source_protocol_val):
        st.log("Route-map match source_protocol")
        sub_cmd = "no match source-protocol {}".format(source_protocol_val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def match_local_preference(self, route_map, val):
        st.log("Route-map match local-preference")
        sub_cmd = "match local-preference {}".format(val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_match_local_preference(self, route_map):
        st.log("Route-map no match local-preference")
        sub_cmd = "no match local-preference"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def match_extcommunity(self, route_map, val):
        st.log("Route-map match extcommunity")
        sub_cmd = "match extcommunity {}".format(val)
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def no_match_extcommunity(self, route_map):
        st.log("Route-map match extcommunity")
        sub_cmd = "no match extcommunity"
        cmd = "{} -c '{}' -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, route_map, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def rm_delay_time_config(self, delay_time):
        st.log("Route-map match source_protocol")
        sub_cmd = "bgp route-map delay-timer {}".format(delay_time)
        cmd = "{} -c '{}' -c '{}'".format(ALICLI_VIEW, CONFIG_VIEW, sub_cmd)
        st.config(self.dut, cmd)
        st.wait(CMD_INTERVAL)

    def save_config_and_reboot(self):
        cmd = "{} -c '{}' -c 'copy running-config startup-config'".format(ALICLI_VIEW, CONFIG_VIEW)
        st.config(self.dut, cmd)
        st.wait(1)
        st.log("start reboot")
        st.reboot(self.dut)
        st.wait(5)
        st.log("finish reboot")

    def show_frr_running_config_json(self):
        cmd = "vtysh -c 'show running-config json'"
        output = st.show(self.dut, cmd, skip_tmpl=True)

        st.log("===================")
        json_str = json.dumps(output).encode('utf-8')
        json_str = json_str[:json_str.rfind('end')].replace('true','"true"').replace("\\n","").replace("\\","").strip('"')
        output_json = json.loads(json_str)

        st.log(output_json)
        st.log("===================")
        return output_json
