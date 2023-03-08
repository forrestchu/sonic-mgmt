import os
import gc

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


def ixia_check_traffic_item_rx_frame(traffic_item_name, rx_count):
    st.log("check traffic item rx frame begin")
    traffic_item_stats = ixia_controller.get_traffic_item_statistics(traffic_item_name)
    if traffic_item_stats is None:
        return False
    st.log("Get traffic item statistics {}".format(traffic_item_name))
    st.log("\n")
    st.log(traffic_item_stats)

    tmp_rx_count = traffic_item_stats['Rx Frames']
    st.log("Get traffic item {} Rx Frames count {},  expect count {}".format(traffic_item_name, tmp_rx_count, rx_count))
    if int(tmp_rx_count) == int(rx_count):
        return True
    return False


def ixia_load_config(config_file_name):
    ixia_controller.new_config()
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


def ixia_check_traffic(traffic_item_name, key="Rx frame", value="0"):
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

    if key == "Rx frame":
        return ixia_check_traffic_item_rx_frame(traffic_item_name, value)
    else:
        st.error("Unsupported check key for traffic: {}".format(key))
        return False


def ixia_config_bgp_flapping():
    # 1/1/21
    bgp_ip_route_range_1 = ixia_controller.get_bgp_ip_route_property(TOPOLOGY_3, DEVICE_GROUP_3,
                                            NETWORK_GROUP_1, IPV4_PREFIX_POOL_1, BGP_IP_ROUTE_PROPERTY_1)
    if not bgp_ip_route_range_1:
        st.error("Get bgp ip route property failed. {} {} {} {} {}".format(TOPOLOGY_3, DEVICE_GROUP_3,
                                            NETWORK_GROUP_1, IPV4_PREFIX_POOL_1, BGP_IP_ROUTE_PROPERTY_1))
        return False

    value_list = []
    flapping_list_1 = [10, 20]
    for i in range(1, 50):
        if i in flapping_list_1:
            value_list.append('true')
        else:
            value_list.append('false')

    ixia_controller.enable_bgp_ip_route_flapping(bgp_ip_route_range_1, value_list)
    st.log("Config bgp flapping for bgp ip route range 1 completed")

    # 1/1/22
    bgp_ip_route_range_2 = ixia_controller.get_bgp_ip_route_property(TOPOLOGY_4, DEVICE_GROUP_4,
                                                    NETWORK_GROUP_2, IPV4_PREFIX_POOL_2, BGP_IP_ROUTE_PROPERTY_2)
    if not bgp_ip_route_range_2:
        st.error("Get bgp ip route property failed. {} {} {} {} {}".format(TOPOLOGY_4, DEVICE_GROUP_4,
                                            NETWORK_GROUP_2, IPV4_PREFIX_POOL_2, BGP_IP_ROUTE_PROPERTY_2))
        return False

    value_list = []
    flapping_list_1 = [10]
    for i in range(1, 50):
        if i in flapping_list_1:
            value_list.append('true')
        else:
            value_list.append('false')

    ixia_controller.enable_bgp_ip_route_flapping(bgp_ip_route_range_2, value_list)
    st.log("Config bgp flapping for bgp ip route range 2 completed")
    return True



