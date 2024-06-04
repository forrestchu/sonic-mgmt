import os
import gc
import re

from spytest import st, tgapi, SpyTestDict
from ixia_vars import *
from ixia_lib import IxiaController
from ixnetwork_restpy.assistants.batch.batchadd import BatchAdd


ixia_controller = None

def ixia_controller_init():
    global ixia_controller
    st.log("Ixia controller init start")
    ixia_controller = IxiaController(IXIA_HOST, IXIA_PORT)
    st.log("Ixia controller init completed")


def ixia_controller_deinit():
    global ixia_controller
    st.log("Ixia controller deinit start")
    ixia_controller = None
    gc.collect()
    st.log("Ixia controller deinit completed")

def ixia_add_traffic_item_for_specific_vrf():
    traffic_item = ixia_controller.add_traffic_item(SPECIFIC_VRF_TRAFFIC_NAME)
    st.log("Add IXIA traffic item {} completed.".format(SPECIFIC_VRF_TRAFFIC_NAME))

    # generate 5 endpoint for endpoint
    endpoint_range = [
        #
        [ DEVICE_1_IPV4, "1", DEVICE_3_IPV4_PREFIX_POOL, "10" ],
        [ DEVICE_1_IPV4, "1", DEVICE_3_IPV4_PREFIX_POOL, "30" ],
        [ DEVICE_1_IPV4, "1", DEVICE_3_IPV4_PREFIX_POOL, "50" ],
        [ DEVICE_1_IPV4, "1", DEVICE_4_IPV4_PREFIX_POOL, "70" ],
        [ DEVICE_1_IPV4, "1", DEVICE_4_IPV4_PREFIX_POOL, "90" ],
    ]

    for item in endpoint_range:
        scalable_sources = [
            {"arg1": item[0], "arg2": "1", "arg3": "1", "arg4": item[1], "arg5": "1"},
        ]
        scalable_destionations = [
            {"arg1": item[2], "arg2": "1", "arg3": "1", "arg4": item[3], "arg5": "1"},
        ]
        endpoint_set = traffic_item.EndpointSet.add(
            ScalableSources=scalable_sources, ScalableDestinations=scalable_destionations
        )

    st.log("Add IXIA traffic item {} endpoints completed.".format(SPECIFIC_VRF_TRAFFIC_NAME))
    with BatchAdd(ixia_controller.ixnetwork):
        config_element = traffic_item.ConfigElement.add()
        config_element.FrameRate.Type = "percentLineRate"
        config_element.FrameRate.Rate = 50
        config_element.TransmissionControl.Type = "fixedFrameCount"
        config_element.TransmissionControl.FrameCount = 10000
        config_element.FrameSize.FixedSize = 64

    st.log("Add IXIA traffic item {} config element completed.".format(SPECIFIC_VRF_TRAFFIC_NAME))
    return True


def ixia_check_port_rx_frame(port_name, rx_count):
    port_stats = ixia_controller.get_port_statistics(port_name)
    if port_stats is None:
        return False

    tmp_rx_count = port_stats['Valid Frames Rx.']
    st.log("Get port Rx {} Frames count {},  expect count {}".format(port_name, tmp_rx_count, rx_count))
    if tmp_rx_count == rx_count:
        return True
    return False


def ixia_check_traffic_item_rx_frame(traffic_item_name, key, rx_count, exact_match):
    st.log("check traffic item rx frame begin")
    traffic_item_stats = ixia_controller.get_traffic_item_statistics(traffic_item_name)
    if traffic_item_stats is None:
        return False
    st.log("Get traffic item statistics {}".format(traffic_item_name))
    st.log("\n")
    st.log(traffic_item_stats)

    tmp_rx_count = traffic_item_stats[key]
    st.log("Get traffic item {} Rx Frames count {},  expect count {}".format(traffic_item_name, tmp_rx_count, rx_count))

    match = re.match("\d+", tmp_rx_count)
    if match:
        tmp_rx_count_int = int(match.group())
    else:
        raise ValueError("Invalid integer format")

    if exact_match is True:
        if int(tmp_rx_count_int) == int(rx_count):
            return True
    else:
        deviation = abs(tmp_rx_count_int - rx_count)
        percent = (float(deviation)/rx_count)*100
        if percent < 10:
            return True
    return False

def ixia_get_traffic_stat(traffic_item_name):
    st.log("get traffic stat begin")
    traffic_item_stats = ixia_controller.get_traffic_item_statistics(traffic_item_name)
    if traffic_item_stats is None:
        return None
    st.log("Get traffic item statistics {}".format(traffic_item_name))
    st.log("\n")
    st.log(traffic_item_stats)
    return traffic_item_stats

def ixia_load_config(config_file_name):
    ixia_controller.new_config()
    st.wait(20)
    st.log("load config {} begin".format(config_file_name))
    ixia_controller.load_config(config_file_name)
    # wait 10 sec for config load
    st.wait(30)
    st.log("load config {} completed".format(config_file_name))
    return True


def ixia_start_all_protocols():
    st.log("IXIA start all protocols begin")
    ixia_controller.start_all_protocols()
    # wait 20 sec for vrf bgp established
    st.wait(20)
    st.log("IXIA start all protocols completed.")
    return True


def ixia_stop_all_protocols():
    st.log("IXIA stop all protocols begin")
    ixia_controller.stop_all_protocols()
    # wait 20 sec for vrf bgp drop
    st.wait(20)
    st.log("IXIA stop all protocols completed.")
    return True


def ixia_check_traffic(traffic_item_name, key="Rx Frames", value="0", exact_match=True):
    st.wait(10)
    st.log("Get traffic item {}".format(traffic_item_name))
    st.log("Apply traffic item {}".format(traffic_item_name))
    ixia_controller.traffic_apply()
    st.wait(10)
    st.log("Start traffic item {}".format(traffic_item_name))
    ret = ixia_controller.start_stateless_traffic(traffic_item_name)
    if not ret:
        st.error("Start traffic item {} failed".format(traffic_item_name))
        return False
    # wait until traffic end
    st.log("Wait traffic item completed...{}".format(traffic_item_name))
    st.wait(20)
    ret = ixia_controller.stop_stateless_traffic(traffic_item_name)
    if not ret:
        st.error("Start traffic item {} failed".format(traffic_item_name))
        return False

    if key == "Rx Frames" or key == "Rx Frame Rate":
        return ixia_check_traffic_item_rx_frame(traffic_item_name, key, value, exact_match)
    else:
        st.error("Unsupported check key for traffic: {}".format(key))
        return False


def ixia_config_bgp_flapping(topology_name, device_group_name, ethernet_name,
                 ipv4_name, bgp_peer_name, enable):

    item = ixia_controller.get_ipv4_bgp_peer(topology_name, device_group_name, ethernet_name,
                 ipv4_name, bgp_peer_name)
    if not item:
        print("Failed to get ipv4 bgp peer")

    if enable:
        res = ixia_controller.enable_ipv4_bgp_peer_flapping(item, 10, 10)
    else:
        res = ixia_controller. disable_ipv4_bgp_peer_flapping(item)
    if not res:
        st.log("Set bgp peer flapping failed")

    topology = ixia_controller.ixnetwork.Globals.find().Topology.find()
    topology.ApplyOnTheFly()

def ixia_start_traffic(traffic_item_name):
    st.wait(10)
    st.log("Get traffic item {}".format(traffic_item_name))
    st.log("Apply traffic item {}".format(traffic_item_name))
    ixia_controller.traffic_apply()
    st.wait(10)
    st.log("Start traffic item {}".format(traffic_item_name))
    ret = ixia_controller.start_stateless_traffic(traffic_item_name)
    if not ret:
        st.error("Start traffic item {} failed".format(traffic_item_name))
        return False
    st.wait(20)
    return True


def ixia_stop_traffic(traffic_item_name):
    ret = ixia_controller.stop_stateless_traffic(traffic_item_name)
    if not ret:
        st.error("stop traffic item {} failed".format(traffic_item_name))
        return False
    st.wait(10)
    return True


def ixia_start_all_traffic():
    st.log("Generate traffic item")
    ixia_controller.generate_traffic()
    st.wait(10)
    st.log("Apply traffic item")
    ixia_controller.traffic_apply()
    st.wait(10)
    st.log("Start all traffic item")
    ret = ixia_controller.start_all_stateless_traffic()
    if not ret:
        st.error("Start all traffic item failed")
        return False
    st.wait(10)
    return True


def ixia_stop_all_traffic():
    ret = ixia_controller.stop_all_stateless_traffic()
    if not ret:
        st.error("Stop all traffic item failed")
        return False
    st.wait(10)
    return True


def ixia_start_logging_port_view():
    ixia_controller.enable_csv_logging(caption="Port Statistics")
    st.wait(10)
    return True


def ixia_stop_logging_port_view():
    ixia_controller.disable_csv_logging(caption="Port Statistics")
    st.wait(10)
    return True


def ixia_get_port_view_data(local_file):
    csv_file_name = "Port Statistics.csv"
    st.log("Remote dir path: {}".format(ixia_controller.get_csv_file_path(caption="Port Statistics")))
    remote_file_path = "{}/{}".format(ixia_controller.get_csv_file_path(caption="Port Statistics"), csv_file_name)
    ixia_controller.download_file(remote_file_path, local_file)
    return True

def ixia_disable_traffic(traffic_item_name):
    traffic_item = ixia_controller.get_traffic_item(traffic_item_name)
    if traffic_item.Enabled:
        traffic_item.Enabled = False
def ixia_enable_traffic(traffic_item_name):
    traffic_item = ixia_controller.get_traffic_item(traffic_item_name)
    if not traffic_item.Enabled:
        traffic_item.Enabled = True
